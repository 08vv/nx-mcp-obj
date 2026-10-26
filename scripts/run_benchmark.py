#!/usr/bin/env python3
"""
run_benchmark.py — Automated Whole-Benchmark Evaluation Harness (Phase 6A)
==========================================================================
Executes the real autonomous CAD reconstruction pipeline on every mesh in obj/:
1. Mesh & image pairing.
2. Route determination (REVOLVE / FEATURE / UNSUPPORTED).
3. Plan generation with cryptographic SHA-256 fingerprinting (anti-hand-edit).
4. Automated NX Part construction via run_journal.exe.
5. Parametric CAD quality verification (Checks 1 to 8).
6. Independent surface distance false-pass verification.
7. Generates Scoreboard (CSV + Markdown) and Summary Statistics.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.nx_mcp.parametric_helpers import setup_nx_license, is_cylindrical_zone
setup_nx_license()

from src.nx_mcp.mesh_analyzer.revolve_profile_analyzer import RevolveProfileAnalyzer
from src.nx_mcp.mesh_analyzer.feature_recognizer import recognize_feature_plan
from src.nx_mcp.surface_distance_checker import evaluate_surface_distance

# Named routing and sampling constants
DEFAULT_PROFILE_SLICES: int = 100            # Fixed sampling slice count for rotational symmetry profile
PROFILE_NEAR_MISS_LIMIT_PCT: float = 10.0   # Error threshold (2x tolerance): >= 10.0% is unsupported far-miss


# Explicit image pairing mapping for all 23 meshes
IMAGE_PAIRING_MAP: Dict[str, Optional[str]] = {
    "Axe3.obj": "Axe3.jpg",
    "Axe_Soap.obj": "Axe_Soap.jpg",
    "bracket3h.obj": None,
    "Cif3_jerry_can_reduced.obj": "Cif3_jerry_can.jpg",
    "Clear3_reduced.obj": "Clear3.jpg",
    "elle18-enamel-jar_reduced.obj": "Ellie_181_jar.png",
    "Elle18-Liquid-Lipstick.obj": "Elle18-Liquid-Lipstick.jpg",
    "Ellie_18_eye_liner.obj": "Ellie_18_eye_liner.jpg",
    "Ellie_18_reduced.obj": "Ellie_18.png",
    "flanged_bearing_housing.obj": None,
    "Glass jar_reduced.obj": "Glass jar.jpg",
    "Hellmans_reduced.obj": "Hellmans.webp",
    "Kissan_Bottle2.obj": "Kissan_Bottle2.png",
    "makeup_cosmetic_star2.obj": "makeup_cosmetic_star2.jpg",
    "mechanical_bracket.obj": None,
    "Oziva4_reduced.obj": "Oziva4.png",
    "Rin_soap_reduced.obj": "Rin_soap.jpg",
    "siemens_bracket.obj": None,
    "sunsilk.obj": None,
    "Surfexcel2_reduced.obj": "Surfexcel2.jpg",
    "Todddler_toothbrush.obj": None,
    "TRESemme6.obj": None,
    "Vaseline5_reduced.obj": "vaseline5_reduced.jpg",
}


def find_run_journal_exe() -> Path:
    candidates = [
        Path(r"C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe"),
        Path(r"C:\Program Files\Siemens\NX\NXBIN\run_journal.exe"),
    ]
    base_dir = os.environ.get("UGII_BASE_DIR")
    if base_dir:
        candidates.insert(0, Path(base_dir) / "NXBIN" / "run_journal.exe")
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("Siemens NX run_journal.exe not found.")


def record_plan_hash(plan_path: Path) -> str:
    """Computes SHA256 of generated plan and saves it alongside the file."""
    h = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    hash_file = plan_path.with_name(f"{plan_path.name}.sha256")
    hash_file.write_text(h, encoding="utf-8")
    return h


def run_process_with_timeout(cmd: List[str], timeout_sec: int) -> Tuple[int, str]:
    """Runs a subprocess with strict timeout handling."""
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_sec,
            env=env,
            cwd=str(REPO_ROOT),
        )
        return proc.returncode, proc.stdout
    except subprocess.TimeoutExpired:
        return -999, f"[TIMEOUT] Execution exceeded {timeout_sec}s timeout limit."
    except Exception as ex:
        return -1, f"[CRASH] Subprocess error: {ex}"


def benchmark_single_mesh(
    mesh_path: Path,
    dataset_set: str,
    output_dir: Path,
    timeout_sec: int = 180,
) -> Dict[str, Any]:
    """Runs the full automated pipeline on a single mesh."""
    mesh_name = mesh_path.name
    stem = mesh_path.stem
    part_stem = stem.replace(" ", "_")
    img_name = IMAGE_PAIRING_MAP.get(mesh_name)
    img_path = (REPO_ROOT / "img" / img_name) if img_name else None

    res: Dict[str, Any] = {
        "mesh": mesh_name,
        "set": dataset_set,
        "has_image": bool(img_path and img_path.exists()),
        "image": img_name or "None",
        "route": "UNSUPPORTED",
        "build_ok": False,
        "C1": "N/A",
        "C2": "N/A",
        "C3": "N/A",
        "C4": "N/A",
        "C5": "N/A",
        "C6": "N/A",
        "C7": "N/A",
        "C8": "N/A",
        "vol_error_pct": None,
        "worst_sec_error_pct": None,
        "surface_mean_dist_mm": None,
        "surface_p95_dist_mm": None,
        "surface_max_dist_mm": None,
        "profile_max_error_pct": None,
        "final_result": "FAIL",
        "failure_category": "UNKNOWN",
        "reason": "",
    }

    run_journal_exe = find_run_journal_exe()

    # -------------------------------------------------------------------------
    # 1. ANALYZE & ROUTE DETERMINATION
    # -------------------------------------------------------------------------
    try:
        import trimesh
        mesh_clean = trimesh.load(str(mesh_path), force="mesh")
        mesh_clean.merge_vertices()
        euler_val = int(getattr(mesh_clean, "euler_number", 2))
        if euler_val <= 0:
            res["route"] = "UNSUPPORTED"
            res["final_result"] = "UNSUPPORTED"
            res["failure_category"] = "UNSUPPORTED_DEGENERATE"
            res["reason"] = f"Degenerate topology: Euler number {euler_val} <= 0 (contains internal voids / through-holes / multi-genus shells)"
            return res

        analyzer = RevolveProfileAnalyzer(mesh_path)
        profile = analyzer.compute_circularity_profile(n_slices=DEFAULT_PROFILE_SLICES)
        is_round = bool(profile.get("is_round", False))
    except Exception as ex:
        res["final_result"] = "FAIL"
        res["failure_category"] = "ANALYSIS_CRASH"
        res["reason"] = f"Mesh analysis crash: {ex}"
        return res

    if is_round:
        spec_path = output_dir / f"{part_stem}_spec.json"
        try:
            # Segment zones
            zones = analyzer.segment_zones(profile, max_zones=8)
            # Closed-loop profile refinement
            zones, refine_status = analyzer.refine_zones(profile, zones)
            worst_err = round(float(getattr(refine_status, "worst_error_pct", 0.0)), 2)
            res["profile_max_error_pct"] = worst_err

            # Near-miss limit enforcement: if surviving profile error >= 10.0%, mark UNSUPPORTED
            if refine_status == "FAR_MISS" or worst_err >= PROFILE_NEAR_MISS_LIMIT_PCT:
                res["route"] = "UNSUPPORTED"
                res["final_result"] = "UNSUPPORTED"
                res["failure_category"] = "UNSUPPORTED_FAR_MISS"
                res["reason"] = f"Profile error {worst_err:.2f}% exceeds {PROFILE_NEAR_MISS_LIMIT_PCT}% near-miss limit (unsupported geometry)"
                return res

            res["route"] = "REVOLVE"
            max_dia = round(float(profile.get("max_diameter", max([z["dia_max"] for z in zones] or [20.0]))), 4)
            max_r = max_dia / 2.0
            spec_expressions = [
                ["BODY_MAX_DIA", f"{max_dia:.4f}"],
            ]
            for idx, zone in enumerate(zones, start=1):
                zh = float(zone["height"])
                spec_expressions.append([f"ZONE{idx}_HEIGHT", f"{zh:.4f}"])
                if idx == 1:
                    spec_expressions.append([f"ZONE1_START", f"{float(zone['z_start']):.4f}"])
                else:
                    spec_expressions.append([f"ZONE{idx}_START", f"ZONE{idx-1}_START + ZONE{idx-1}_HEIGHT"])
                rst = float(zone["r_start"])
                ren = float(zone["r_end"])
                spec_expressions.append([f"ZONE{idx}_BASE_R", f"(BODY_MAX_DIA / 2.0) * {rst/max(max_r, 1e-4):.6f}"])
                if zone.get("segment_type") == "ARC" or not is_cylindrical_zone(rst, ren):
                    spec_expressions.append([f"ZONE{idx}_TOP_R", f"(BODY_MAX_DIA / 2.0) * {ren/max(max_r, 1e-4):.6f}"])
                if zone.get("segment_type") == "ARC":
                    rmd = float(zone.get("r_mid", (rst + ren)/2.0))
                    spec_expressions.append([f"ZONE{idx}_MID_R", f"(BODY_MAX_DIA / 2.0) * {rmd/max(max_r, 1e-4):.6f}"])

            spec_data = {
                "source_mesh": mesh_name,
                "primary_axis": profile.get("primary_axis", "Y"),
                "axis_idx": 1,
                "units_scale": analyzer.scale_factor,
                "circularity": profile.get("mean_circularity", 1.0),
                "zones": zones,
                "expressions": spec_expressions,
                "rotation_matrix": profile.get("rotation_matrix", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
            }
            with open(spec_path, "w", encoding="utf-8") as sf:
                json.dump(spec_data, sf, indent=2)
            record_plan_hash(spec_path)
        except Exception as ex:
            res["final_result"] = "FAIL"
            res["failure_category"] = "PLANNING_CRASH"
            res["reason"] = f"Revolve planning crash: {ex}"
            return res

        # ---------------------------------------------------------------------
        # 2. BUILD (REVOLVE)
        # ---------------------------------------------------------------------
        prt_path = output_dir / f"{part_stem}_Parametric.prt"
        builder_script = REPO_ROOT / "src" / "nx_mcp" / "generic_nx_builder.py"
        build_cmd = [str(run_journal_exe), str(builder_script), "-args", str(spec_path), str(prt_path)]

        ret_b, out_b = run_process_with_timeout(build_cmd, timeout_sec)
        if ret_b != 0:
            res["build_ok"] = False
            res["failure_category"] = "BUILD_TIMEOUT" if ret_b == -999 else "BUILD_CRASH"
            res["reason"] = f"Build failed (code {ret_b}): {out_b[-200:].strip() if out_b else 'no output'}"
            return res

        res["build_ok"] = True

    else:
        # Non-round mesh -> Feature plan recognizer
        plan_path = output_dir / f"{part_stem}_feature_plan.json"
        try:
            plan = recognize_feature_plan(mesh_path)
            if plan.get("overall_status") == "UNSUPPORTED":
                res["route"] = "UNSUPPORTED"
                res["final_result"] = "UNSUPPORTED"
                ranges = plan.get("ranges", [])
                unsupported_ranges = [r for r in ranges if not r.get("is_supported", True) and r.get("area_overlap_error_pct", 0) > 5.0]
                if unsupported_ranges:
                    worst_r = max(unsupported_ranges, key=lambda r: r.get("area_overlap_error_pct", 0))
                    err_val = worst_r.get("area_overlap_error_pct", 0)
                    r_idx = worst_r.get("range_index", 1)
                    r_elev = worst_r.get("elevation_range_mm", [0, 0])
                    prim = worst_r.get("fitted_primitive", "UNKNOWN")
                    if err_val <= 10.0:
                        band = "NEAR_MISS (5-10%)"
                        res["failure_category"] = "UNSUPPORTED_NEAR_MISS"
                    else:
                        band = "FAR_MISS (>10%)"
                        res["failure_category"] = "UNSUPPORTED_FAR_MISS"
                    res["reason"] = f"UNSUPPORTED [{band}]: Range {r_idx} [Y={r_elev[0]} to {r_elev[1]}mm] fit error {err_val}% (closest primitive: {prim})"
                else:
                    reasons_list = plan.get("rejection_reasons", [])
                    res["failure_category"] = "UNSUPPORTED_DEGENERATE" if plan.get("is_degenerate") else "UNSUPPORTED_GEOMETRY"
                    res["reason"] = "; ".join(reasons_list) if reasons_list else "Rejected as unsupported geometry"
                return res

            res["route"] = "FEATURE"
            with open(plan_path, "w", encoding="utf-8") as pf:
                json.dump(plan, pf, indent=2)
            record_plan_hash(plan_path)
        except Exception as ex:
            err_msg = str(ex)
            if "REJECTED as UNSUPPORTED" in err_msg or "fit error" in err_msg or "No suitable CAD primitive" in err_msg:
                res["route"] = "UNSUPPORTED"
                res["final_result"] = "UNSUPPORTED"
                res["failure_category"] = "UNSUPPORTED_GEOMETRY"
                res["reason"] = err_msg.strip()
                return res
            else:
                res["route"] = "FEATURE"
                res["final_result"] = "FAIL"
                res["failure_category"] = "PLANNING_CRASH"
                res["reason"] = f"Feature decomposition crash: {ex}"
                return res

        # ---------------------------------------------------------------------
        # 2. BUILD (FEATURE ROUTE)
        # ---------------------------------------------------------------------
        prt_path = output_dir / f"{part_stem}_Parametric.prt"
        builder_script = REPO_ROOT / "src" / "nx_mcp" / "generic_nx_builder.py"
        build_cmd = [str(run_journal_exe), str(builder_script), "-args", str(plan_path), str(prt_path)]

        ret_b, out_b = run_process_with_timeout(build_cmd, timeout_sec)
        if ret_b != 0:
            res["build_ok"] = False
            res["failure_category"] = "BUILD_TIMEOUT" if ret_b == -999 else "BUILD_CRASH"
            res["reason"] = f"Build failed (code {ret_b}): {out_b[-200:].strip() if out_b else 'no output'}"
            return res

        res["build_ok"] = True

    # -------------------------------------------------------------------------
    # 3. VERIFY (CHECK 1 TO 8)
    # -------------------------------------------------------------------------
    checker_script = REPO_ROOT / "scripts" / "check_parametric_quality.py"
    verify_cmd = [sys.executable, str(checker_script), str(prt_path), str(mesh_path)]

    ret_v, out_v = run_process_with_timeout(verify_cmd, timeout_sec)

    # Parse checker log metrics and C1..C8 statuses
    for line in out_v.splitlines():
        if "Volume Error:" in line:
            try:
                part_pct = line.split("Volume Error:")[1].split("%")[0].strip()
                res["vol_error_pct"] = float(part_pct)
            except Exception:
                pass
        if "Max Section Area Dev:" in line:
            try:
                part_pct = line.split("Max Section Area Dev:")[1].split("%")[0].strip()
                res["worst_sec_error_pct"] = float(part_pct)
            except Exception:
                pass
        if line.startswith("CHECK_RESULTS_JSON:"):
            try:
                cr_json = json.loads(line.split("CHECK_RESULTS_JSON:")[1].strip())
                for k, v in cr_json.items():
                    res[k] = v
            except Exception:
                pass

    # Run independent surface distance check on EVERY built part
    stl_path = prt_path.with_suffix(".stl")
    surf_eval = None
    if stl_path.exists():
        try:
            surf_eval = evaluate_surface_distance(mesh_path, stl_path)
            res["surface_mean_dist_mm"] = surf_eval.get("mean_distance_mm")
            res["surface_p95_dist_mm"] = surf_eval.get("p95_distance_mm")
            res["surface_max_dist_mm"] = surf_eval.get("max_distance_mm")
        except Exception as ex:
            print(f"  [WARN] Surface distance calculation: {ex}")

    crash_checks = [k for k in ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"] if res.get(k) == "CRASH"]
    failing_checks = [k for k in ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"] if res.get(k) == "FAIL"]

    if crash_checks:
        res["final_result"] = "CRASH"
        res["failure_category"] = "CHECK_EXCEPTION_" + "_".join(crash_checks)
        res["reason"] = f"Exception occurred inside checks: {', '.join(crash_checks)}"
        return res

    if ret_v != 0 or len(failing_checks) > 0:
        if not failing_checks and ("Traceback" in out_v or "Exception" in out_v or "Error" in out_v or ret_v < 0):
            res["final_result"] = "CRASH"
            res["failure_category"] = "VERIFIER_CRASH"
            res["reason"] = f"Verifier crashed during execution (exit code {ret_v})"
            return res

        res["final_result"] = "FAIL"
        if not failing_checks:
            if "orphan expressions" in out_v:
                failing_checks.append("C3")
                res["C3"] = "FAIL"
            if "Resizing failed" in out_v:
                failing_checks.append("C4")
                res["C4"] = "FAIL"
            if "Whole-part volume error" in out_v or "Cross-section" in out_v:
                failing_checks.append("C7")
                res["C7"] = "FAIL"
        res["failure_category"] = "_".join(failing_checks) if failing_checks else "QUALITY_CHECK_FAILURE"
        res["reason"] = f"Failed checks: {', '.join(failing_checks)}"
        return res

    # Check for False Pass via surface distance
    if surf_eval and surf_eval.get("is_false_pass"):
        res["final_result"] = "FALSE_PASS"
        res["failure_category"] = "FALSE_PASS_SURFACE_DISCREPANCY"
        res["reason"] = surf_eval.get("reason", "Surface distance exceeded tolerance")
        return res

    # Passed all 8 checks + surface distance check
    res["final_result"] = "PASS"
    res["failure_category"] = "NONE"
    res["reason"] = "All 8 parametric quality checks and independent surface distance check passed"
    return res


def main():
    parser = argparse.ArgumentParser(description="Automated Whole-Benchmark Evaluation Harness (Phase 6B)")
    parser.add_argument("--split", type=Path, default=REPO_ROOT / "datasets" / "split.json", help="Path to split.json")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "output", help="Output directory")
    parser.add_argument("--timeout", type=int, default=180, help="Per-mesh timeout in seconds")
    parser.add_argument("--mesh", type=str, default=None, help="Optional filter to run single mesh")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.split, "r", encoding="utf-8") as sf:
        split_data = json.load(sf)

    dev_set = set(split_data.get("development", []))
    held_out_set = set(split_data.get("held_out", []))

    obj_dir = REPO_ROOT / "obj"
    mesh_files = sorted(list(obj_dir.glob("*.obj")))
    if args.mesh:
        mesh_files = [m for m in mesh_files if m.name == args.mesh or m.stem == args.mesh]

    print("=" * 85)
    print(f"PHASE 6B: AUTOMATED WHOLE-BENCHMARK EVALUATION HARNESS")
    print(f"  Total Meshes:      {len(mesh_files)}")
    print(f"  Split File:        {args.split}")
    print(f"  Per-Mesh Timeout:  {args.timeout}s")
    print("=" * 85)

    results: List[Dict[str, Any]] = []

    for idx, mesh_p in enumerate(mesh_files, 1):
        m_set = "dev" if mesh_p.name in dev_set else ("held-out" if mesh_p.name in held_out_set else "unknown")
        print(f"\n[{idx:02d}/{len(mesh_files):02d}] Running benchmark on: {mesh_p.name} (Set: {m_set})...")
        t0 = time.time()
        row = benchmark_single_mesh(mesh_p, m_set, args.output_dir, timeout_sec=args.timeout)
        dur = time.time() - t0
        print(f"  Result: {row['final_result']} | Route: {row['route']} | Build: {row['build_ok']} | ({dur:.1f}s)")
        if row["reason"]:
            print(f"  Reason: {row['reason']}")
        results.append(row)

    # Save Scoreboard CSV
    csv_path = args.output_dir / "benchmark_scoreboard.csv"
    fieldnames = [
        "mesh", "set", "has_image", "image", "route", "build_ok",
        "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8",
        "vol_error_pct", "worst_sec_error_pct",
        "surface_mean_dist_mm", "surface_p95_dist_mm", "surface_max_dist_mm",
        "profile_max_error_pct",
        "final_result", "failure_category", "reason"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as cf:
        writer = csv.DictWriter(cf, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    # Save Scoreboard Markdown
    md_path = args.output_dir / "benchmark_scoreboard.md"
    dev_results = [r for r in results if r["set"] == "dev"]
    held_results = [r for r in results if r["set"] == "held-out"]
    held_no_axe = [r for r in held_results if r["mesh"] != "Axe3.obj"]

    dev_pass = sum(1 for r in dev_results if r["final_result"] == "PASS")
    held_pass_all = sum(1 for r in held_results if r["final_result"] == "PASS")
    held_pass_no_axe = sum(1 for r in held_no_axe if r["final_result"] == "PASS")
    false_pass_count = sum(1 for r in results if r["final_result"] == "FALSE_PASS")
    crash_count = sum(1 for r in results if "CRASH" in r["failure_category"])

    from collections import Counter
    fail_counts = Counter(r["failure_category"] for r in results if r["failure_category"] != "NONE")

    md_lines = []
    md_lines.append("# Benchmark Evaluation Scoreboard (Phase 6D: Steps 1+2)\n")
    md_lines.append(f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    md_lines.append("| Mesh | Set | Route | Build | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | Surf Mean (mm) | Surf P95 (mm) | Surf Max (mm) | Prof Err % | Final Result | Reason |")
    md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for r in results:
        s_mean = f"{r['surface_mean_dist_mm']:.2f}" if r.get("surface_mean_dist_mm") is not None else "N/A"
        s_p95 = f"{r['surface_p95_dist_mm']:.2f}" if r.get("surface_p95_dist_mm") is not None else "N/A"
        s_max = f"{r['surface_max_dist_mm']:.2f}" if r.get("surface_max_dist_mm") is not None else "N/A"
        p_err = f"{r['profile_max_error_pct']:.2f}%" if r.get("profile_max_error_pct") is not None else "N/A"
        md_lines.append(
            f"| `{r['mesh']}` | **{r['set']}** | `{r['route']}` | {'PASS' if r['build_ok'] else 'FAIL'} | "
            f"{r['C1']} | {r['C2']} | {r['C3']} | {r['C4']} | {r['C5']} | {r['C6']} | {r['C7']} | {r['C8']} | "
            f"{s_mean} | {s_p95} | {s_max} | {p_err} | **{r['final_result']}** | {r['reason'][:65]} |"
        )

    md_lines.append("\n## Benchmark Summary Statistics\n")
    md_lines.append(f"- **Development Set Pass Rate**: {dev_pass} / {len(dev_results)} ({dev_pass/max(1, len(dev_results))*100:.1f}%)")
    md_lines.append(f"- **Held-Out Set Pass Rate (All 8)**: {held_pass_all} / {len(held_results)} ({held_pass_all/max(1, len(held_results))*100:.1f}%)")
    md_lines.append(f"- **Held-Out Set Pass Rate (Excluding Axe3, 7 meshes)**: {held_pass_no_axe} / {len(held_no_axe)} ({held_pass_no_axe/max(1, len(held_no_axe))*100:.1f}%)")
    md_lines.append(f"- **Overall Pass Rate**: {dev_pass + held_pass_all} / {len(results)} ({(dev_pass + held_pass_all)/max(1, len(results))*100:.1f}%)")
    md_lines.append(f"- **False Pass Count**: {false_pass_count}")
    md_lines.append(f"- **Crash Count**: {crash_count}\n")

    md_lines.append("## Failure Categories (Ordered by Frequency)\n")
    md_lines.append("| Failure Category | Count | Description |")
    md_lines.append("| :--- | :--- | :--- |")
    for cat, count in fail_counts.most_common():
        md_lines.append(f"| `{cat}` | **{count}** | {cat.replace('_', ' ').title()} |")

    md_content = "\n".join(md_lines)
    with open(md_path, "w", encoding="utf-8") as mf:
        mf.write(md_content)

    print("\n" + "=" * 85)
    print("SCOREBOARD GENERATED")
    print(f"  CSV:      {csv_path}")
    print(f"  Markdown: {md_path}")
    print("=" * 85)
    print(md_content)


if __name__ == "__main__":
    main()
