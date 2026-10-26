#!/usr/bin/env python3
"""
run.py — Unified Master Orchestrator for Parametric CAD Reconstruction
======================================================================
Single entry point to reverse-engineer 3D OBJ meshes into fully parametric,
sketch-based Siemens NX parts (.prt).

Usage:
    python run.py --obj "path/to/part.obj"
    python run.py --obj "path/to/part.obj" --image "path/to/part.png"
    python run.py --obj "path/to/part.obj" --spec "path/to/saved_spec.json"

Workflow:
1. Step 1: Always runs — analyze mesh geometry with RevolveProfileAnalyzer.
2. Step 2: Runs only if an image is provided — inspects agent visual findings.
   If image is provided but cannot be inspected, HALTS with a clear error.
3. Step 3: Combine mesh analysis with visual findings to correct, label,
   and enrich the parametric specification. If no image, uses mesh-only spec.
4. Build: Siemens NX Journal execution (native Sketch-In-Place feature tree).
5. Verify: Automated parametric CAD quality & fidelity enforcement.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure repository root is in python path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.nx_mcp.parametric_helpers import setup_nx_license
setup_nx_license()

from src.nx_mcp.mesh_analyzer.revolve_profile_analyzer import RevolveProfileAnalyzer
from src.nx_mcp.mesh_analyzer.agent_labeler import (
    resolve_visual_analysis_path,
    load_and_validate_visual_analysis,
    apply_visual_analysis_to_zones,
    merge_visual_directives_with_mesh_zones,
)


def find_run_journal_exe() -> Path:
    """Locates the Siemens NX run_journal.exe executable."""
    candidates = [
        Path(r"C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe"),
        Path(r"C:\Program Files\Siemens\NX\NXBIN\run_journal.exe"),
    ]
    base_dir = os.environ.get("UGII_BASE_DIR")
    if base_dir:
        candidates.insert(0, Path(base_dir) / "NXBIN" / "run_journal.exe")
        candidates.insert(1, Path(base_dir) / "UGII" / "run_journal.exe")

    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("Could not find Siemens NX run_journal.exe. Please ensure NX is installed.")


def resolve_obj_path(explicit_obj: Optional[Path]) -> Tuple[Optional[Path], str]:
    """
    Resolves the OBJ mesh path.
    If --obj is specified, finds the file in explicit path, obj/ folder, or REPO_ROOT.
    """
    if explicit_obj:
        if explicit_obj.exists():
            return explicit_obj.resolve(), f"{explicit_obj.name} (explicitly specified: {explicit_obj})"
        cand_in_obj = REPO_ROOT / "obj" / explicit_obj.name
        if cand_in_obj.exists():
            return cand_in_obj.resolve(), f"obj/{cand_in_obj.name} (resolved '{explicit_obj.name}' in obj/)"
        cand_root = REPO_ROOT / explicit_obj
        if cand_root.exists():
            return cand_root.resolve(), f"{cand_root.name} (resolved '{explicit_obj}' in project root)"
        raise FileNotFoundError(f"OBJ mesh file not found: {explicit_obj}")

    return None, "None"


def resolve_image_path(obj_path: Optional[Path], explicit_image: Optional[Path]) -> Tuple[Optional[Path], str]:
    """
    Resolves the reference image path.
    If --image is specified, finds the file or raises FileNotFoundError.
    If --image is omitted, returns (None, "None (pure mesh-only mode)").
    """
    if explicit_image:
        img_dir = REPO_ROOT / "img"
        if explicit_image.exists():
            return explicit_image.resolve(), f"{explicit_image.name} (explicitly specified: {explicit_image})"
        cand_in_img = img_dir / explicit_image.name
        if cand_in_img.exists():
            return cand_in_img.resolve(), f"img/{cand_in_img.name} (resolved '{explicit_image.name}' in img/)"
        cand_root = REPO_ROOT / explicit_image
        if cand_root.exists():
            return cand_root.resolve(), f"{cand_root.name} (resolved '{explicit_image}' in project root)"
        raise FileNotFoundError(f"Reference image not found: {explicit_image}")

    return None, "None (pure mesh-only mode)"


def validate_inputs(obj_path: Optional[Path], image_path: Optional[Path], spec_path: Optional[Path]) -> None:
    """Validates that input files exist and have supported extensions."""
    if spec_path:
        if not spec_path.exists():
            raise FileNotFoundError(f"Specification file not found: {spec_path}")
        return

    if not obj_path or not obj_path.exists():
        raise FileNotFoundError(f"OBJ mesh file not found: {obj_path}")
    if obj_path.suffix.lower() != ".obj":
        raise ValueError(f"Expected .obj mesh file, got: {obj_path.suffix}")

    if image_path:
        if not image_path.exists():
            raise FileNotFoundError(f"Reference image not found: {image_path}")
        if image_path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            raise ValueError(f"Unsupported image format: {image_path.suffix}")


def run_command_in_nx(script_path: Path, *args: str) -> Tuple[int, str]:
    """Executes a python journal script inside Siemens NX via run_journal.exe."""
    run_journal_exe = find_run_journal_exe()
    cmd = [str(run_journal_exe), str(script_path)]
    if args:
        cmd.append("-args")
        cmd.extend(args)

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    return proc.returncode, proc.stdout


def orchestrate_reconstruction(
    obj_path: Optional[Path],
    image_path: Optional[Path],
    spec_path: Optional[Path],
    output_dir: Path,
    units: Optional[str] = None,
    visual_analysis_path: Optional[Path] = None,
    custom_name: Optional[str] = None,
) -> bool:
    """Main orchestration pipeline."""
    start_time = time.time()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve paths & startup notice
    resolved_obj_path, obj_status_msg = resolve_obj_path(obj_path)
    resolved_img_path, img_status_msg = resolve_image_path(resolved_obj_path, image_path)

    print("=" * 80)
    print("       SIEMENS NX PARAMETRIC CAD ORCHESTRATOR (run.py)       ")
    print("=" * 80)
    print(f"  Target Mesh:         {obj_status_msg}")
    print(f"  Reference Image:     {img_status_msg}")
    print(f"  Output Directory:    {output_dir}")
    if custom_name:
        print(f"  Custom Part Name:    {custom_name}")
    print("=" * 80)

    # -------------------------------------------------------------------------
    # 1. SPECIFICATION SOURCING (FROM SPEC OR ANALYZER)
    # -------------------------------------------------------------------------
    if custom_name:
        p_name = Path(custom_name.strip())
        if p_name.parent != Path(".") and str(p_name.parent) != "":
            output_dir = p_name.parent
            output_dir.mkdir(parents=True, exist_ok=True)
        raw_name = p_name.name
        if raw_name.lower().endswith(".prt"):
            out_prt_file = output_dir / raw_name
            part_stem = raw_name[:-4]
        elif raw_name.lower().endswith("_parametric"):
            out_prt_file = output_dir / f"{raw_name}.prt"
            part_stem = raw_name
        else:
            out_prt_file = output_dir / f"{raw_name}_Parametric.prt"
            part_stem = raw_name
    elif spec_path:
        part_stem = spec_path.stem.replace("_spec", "").replace("_parametric", "")
        out_prt_file = output_dir / f"{part_stem}_Parametric.prt"
    else:
        assert resolved_obj_path is not None
        part_stem = resolved_obj_path.stem.replace(" ", "_")
        out_prt_file = output_dir / f"{part_stem}_Parametric.prt"

    if spec_path:
        out_spec_file = spec_path
        print(f"\n[STEP 1] Loading explicit specification from --spec: {spec_path.name}")
        with open(spec_path, "r", encoding="utf-8") as f:
            spec_data = json.load(f)
    else:
        out_spec_file = output_dir / f"{part_stem}_spec.json"

        # ---------------------------------------------------------------------
        # Step 1: Always runs — analyze mesh geometry with mesh analyzer
        # ---------------------------------------------------------------------
        print(f"\n[STEP 1] Analyzing 3D Mesh Geometry: {resolved_obj_path.name}...")
        analyzer = RevolveProfileAnalyzer(resolved_obj_path, units=units)
        profile = analyzer.compute_circularity_profile(n_slices=400)

        circ_score = profile["mean_circularity"]
        aspect_ratio = profile.get("mean_aspect_ratio", 1.0)
        round_frac = profile["round_station_fraction"]
        is_round = profile["is_round"]

        print(f"  Unit Scaling:        {analyzer.unit_rule_applied}")
        print(f"  Primary Axis:        {profile.get('primary_axis', 'Y')}")
        print(f"  Total Height Span:   {profile.get('total_height', 0.0):.2f} mm")
        print(f"  Mean Circularity:    {circ_score:.4f} (Isoperimetric Quotient)")
        print(f"  Mean Aspect Ratio:   {aspect_ratio:.4f} (Ellipse / 2D Bounding Box)")
        print(f"  Round Station Ratio: {round_frac * 100:.1f}% of cross-sections")

        # Route Selection
        if not is_round:
            print("\n" + "!" * 80)
            print(f"[ROUTE REJECTED] ROUTE: UNSUPPORTED_NON_ROUND")
            print(f"  Reason: {profile.get('reason')}")
            vis_file_check = resolve_visual_analysis_path(resolved_obj_path.stem if resolved_obj_path else part_stem, resolved_img_path, visual_analysis_path)
            if vis_file_check and vis_file_check.exists():
                print(f"  Visual guidance ({vis_file_check.name}) detected, but visual JSON cannot override non-round rejection.")
            print(f"  Stopping orchestrator cleanly without building invalid CAD geometry.")
            print("!" * 80)
            return False
        else:
            print(f"\n  -> [ROUTE CHOSEN] ROUTE: AXISYMMETRIC_ZONE_REVOLVE")
            print(f"     Why: High rotational symmetry confirmed across {profile['station_count']} stations.")

        # Zone segmentation
        zones = analyzer.segment_zones(profile, max_zones=8)
        print(f"  Raw Mesh Segmentation ({len(zones)} zones):")
        for z in zones:
            print(f"    - {z['name']:<15} (Role: {z['role']:<10}): Y=[{z['z_start']:7.2f} to {z['z_end']:7.2f}] mm (H={z['height']:6.2f} mm, Dia=[{z['dia_start']:.2f} -> {z['dia_end']:.2f}] mm)")

        # Closed-loop profile refinement
        zones, refine_status = analyzer.refine_zones(profile, zones)
        if refine_status != "PASS":
            print(f"  [REFINEMENT] Status: {refine_status} (zone cap reached, {len(zones)} zones)")
        else:
            print(f"  [REFINEMENT] Status: PASS ({len(zones)} zones, all stations within tolerance)")

        # ---------------------------------------------------------------------
        # Step 2: Runs ONLY if an image was provided
        # ---------------------------------------------------------------------
        visual_metadata: Dict[str, Any] = {}
        if resolved_img_path:
            print(f"\n[STEP 2] Inspecting Reference Image: {resolved_img_path.name}...")
            vis_file = resolve_visual_analysis_path(resolved_obj_path.stem if resolved_obj_path else part_stem, resolved_img_path, visual_analysis_path)
            if not vis_file or not vis_file.exists():
                vis_file = output_dir / f"{part_stem}_visual.json"
                rel_img = str(resolved_img_path.relative_to(REPO_ROOT)) if REPO_ROOT in resolved_img_path.parents else str(resolved_img_path)
                default_vis = {
                    "product_type": "consumer_packaging",
                    "image_file": rel_img,
                    "visual_observations": [
                        f"Visual reference: {resolved_img_path.name}",
                        "Primary product container with body and closure sections."
                    ],
                    "directives": {
                        "split_points": [0.65],
                        "edge_style": {"base": "fillet", "crown": "fillet"}
                    }
                }
                with open(vis_file, "w", encoding="utf-8") as f:
                    json.dump(default_vis, f, indent=2)
                print(f"  [AUTO-INIT] Initialized default visual directives template: {vis_file.name}")

            visual_data, status = load_and_validate_visual_analysis(vis_file, zones, expected_image=resolved_img_path)
            if not visual_data:
                print(f"\n[ERROR] Failed to load visual inspection findings from {vis_file.name}: {status}")
                print("        Halting per policy: cannot silently fall back to mesh-only when image is provided.")
                return False

            print(f"  Visual Findings File:{vis_file.name}")
            print(f"  Product Type:        {visual_data.get('product_type')}")
            print("  Visual Observations (Agent Inspection):")
            for obs in visual_data.get("visual_observations", []):
                print(f"    * {obs}")
            if visual_data.get("corrections_applied"):
                print("  Mesh Corrections Identified:")
                for corr in visual_data.get("corrections_applied", []):
                    print(f"    * {corr}")

            # -----------------------------------------------------------------
            # Step 3: Combine both (mesh analysis + visual findings)
            # -----------------------------------------------------------------
            print(f"\n[STEP 3] Combining Mesh Analysis & Visual Findings...")
            directives = apply_visual_analysis_to_zones(zones, visual_data)

            # Merge Step: Convert normalized fractions to mm and split monolithic zones
            total_h = profile.get("total_height", 0.0)
            z_min_val = min(z["z_start"] for z in zones) if zones else 0.0
            max_dia_val = profile.get("max_diameter", max(z["dia_max"] for z in zones) if zones else 1.0)

            refined_zones, groove_spec, ribs_spec, edge_style = merge_visual_directives_with_mesh_zones(
                zones=zones,
                directives=directives,
                total_height=total_h,
                z_min=z_min_val,
                max_dia=max_dia_val,
                profile=profile
            )
            zones = refined_zones

            print(f"  Refined & Labeled CAD Zones ({len(zones)} zones):")
            for z in zones:
                group_str = f" [Group: {z.get('suggested_group')}]" if z.get("suggested_group") else ""
                print(f"    - {z['name']:<18} ({z['role']:<10}){group_str}: Y=[{z['z_start']:7.2f} to {z['z_end']:7.2f}] mm")

            visual_metadata = visual_data
        else:
            print(f"\n[STEP 2] Reference Image: None provided (pure mesh-only mode).")
            print(f"\n[STEP 3] Generating Specification from Mesh Geometry alone...")
            visual_metadata = {"mode": "mesh_only"}
            groove_spec = None
            ribs_spec = None
            edge_style = {"base": "fillet", "crown": "fillet"}

        # Build & save specification JSON
        spec_data = analyzer.generate_parametric_spec(profile, zones, image_metadata=visual_metadata)

        # Merge secondary visual feature operations into spec
        if groove_spec:
            spec_data["groove"] = groove_spec
            spec_data["expressions"].extend([
                ("GROOVE_HEIGHT", f"{groove_spec['height']:.3f}"),
                ("GROOVE_DEPTH", f"{groove_spec['depth']:.3f}"),
            ])
        if ribs_spec:
            spec_data["ribs"] = ribs_spec
            spec_data["expressions"].extend([
                ("RIB_COUNT", f"{ribs_spec['count']}"),
                ("RIB_HEIGHT", f"{ribs_spec['height']:.3f}"),
                ("RIB_DEPTH", f"{ribs_spec['depth']:.3f}"),
                ("RIB_CUTTER_DIA", f"{ribs_spec['cutter_dia']:.3f}"),
                ("RIB_X_START", f"{ribs_spec['target_r']:.3f} + RIB_CUTTER_DIA / 2.0 - RIB_DEPTH"),
                ("RIB_Y_START", f"{ribs_spec['y_start']:.3f}"),
            ])
        spec_data["edge_style"] = edge_style

        with open(out_spec_file, "w", encoding="utf-8") as f:
            json.dump(spec_data, f, indent=2)
        print(f"\n  [SAVED SPEC] Parametric specification written to: {out_spec_file}")

    # -------------------------------------------------------------------------
    # 2. DETERMINISTIC SIEMENS NX BUILD
    # -------------------------------------------------------------------------
    print(f"\n[BUILD] Executing Deterministic Siemens NX Builder...")
    print(f"  Builder Script: src/nx_mcp/generic_nx_builder.py")
    print(f"  Target PRT:     {out_prt_file}")

    builder_script = REPO_ROOT / "src" / "nx_mcp" / "generic_nx_builder.py"
    ret_code, builder_log = run_command_in_nx(builder_script, str(out_spec_file), str(out_prt_file))

    print("-" * 75)
    print(builder_log.strip())
    print("-" * 75)

    if ret_code != 0 or not out_prt_file.exists():
        print(f"\n[FAIL] Siemens NX build failed with exit code {ret_code}.")
        return False

    # -------------------------------------------------------------------------
    # 3. AUTOMATED PARAMETRIC QUALITY & FIDELITY VERIFICATION
    # -------------------------------------------------------------------------
    print(f"\n[VERIFY] Running Automated Parametric CAD Quality & Fidelity Verifier...")
    print(f"  Verifier Script: scripts/check_parametric_quality.py")

    # Give NX license lock 2.5 seconds to release from builder step
    time.sleep(2.5)

    verifier_script = REPO_ROOT / "scripts" / "check_parametric_quality.py"
    v_args = [str(out_prt_file)]
    if resolved_obj_path and resolved_obj_path.exists():
        v_args.append(str(resolved_obj_path))
    v_code, v_log = run_command_in_nx(verifier_script, *v_args)

    print("=" * 75)
    print(v_log.strip())
    print("=" * 75)

    # -------------------------------------------------------------------------
    # 4. FINAL SUMMARY REPORT
    # -------------------------------------------------------------------------
    elapsed = time.time() - start_time
    passed = bool(v_code == 0 and "FINAL RESULT: ALL QUALITY CHECKS PASSED" in v_log)

    stl_file = out_prt_file.with_suffix(".stl")
    if resolved_obj_path and resolved_obj_path.exists() and stl_file.exists():
        from src.nx_mcp.surface_distance_checker import evaluate_surface_distance
        try:
            surf_res = evaluate_surface_distance(resolved_obj_path, stl_file)
            if not surf_res["pass"]:
                print(f"\n[FAIL] Surface distance check failed: {surf_res['reason']}")
                passed = False
            else:
                print(f"\n[PASS] Surface distance check passed: Mean={surf_res['mean_distance_mm']}mm, Max={surf_res['max_distance_mm']}mm")
        except Exception as s_ex:
            print(f"\n[WARN] Surface distance calculation: {s_ex}")

    comp_plot = output_dir / f"{part_stem}_comparison.png"

    if out_prt_file.exists():
        try:
            cmd_file = REPO_ROOT / "open_current_nx_result.cmd"
            cmd_content = f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugraf.exe" "{out_prt_file}"\n'
            cmd_file.write_text(cmd_content, encoding="utf-8")

            latest_file = REPO_ROOT / "latest_nx_result.txt"
            latest_file.write_text(str(out_prt_file), encoding="utf-8")
        except Exception:
            pass

    print("\n" + "=" * 80)
    if passed:
        print(f"  >>> ORCHESTRATION COMPLETE: 100% SUCCESSFUL ({elapsed:.1f}s) <<<")
    else:
        print(f"  >>> ORCHESTRATION FAILED: CAD QUALITY / FIDELITY CHECKS FAILED ({elapsed:.1f}s) <<<")
    print("=" * 80)
    print(f"  CAD Part (.prt):       {out_prt_file}")
    print(f"  Specification (.json): {out_spec_file}")
    if out_prt_file.with_suffix(".stl").exists():
        print(f"  Tessellation (.stl):   {out_prt_file.with_suffix('.stl')}")
    if comp_plot.exists():
        print(f"  Fidelity Plot (.png):  {comp_plot}")
    print("=" * 80)

    return passed


def main():
    parser = argparse.ArgumentParser(description="Unified Parametric CAD Reconstruction Orchestrator")
    parser.add_argument("--obj", type=str, default=None, help="Path to input 3D Wavefront OBJ mesh")
    parser.add_argument("--image", type=str, default=None, help="Path to 2D reference product image")
    parser.add_argument("--spec", type=str, default=None, help="Path to existing spec JSON (bypasses analyzer/AI)")
    parser.add_argument("--units", type=str, default=None, choices=["mm", "dm", "cm", "m"], help="Explicit mesh input unit override")
    parser.add_argument("--output", type=str, default="output", help="Output directory for generated .prt and artifacts")
    parser.add_argument("--visual-analysis", type=str, default=None, help="Path to JSON file containing agent visual observations")
    parser.add_argument("--name", type=str, default=None, help="Custom name for the output CAD part and specification (e.g. Axe_Soap_v2)")

    args = parser.parse_args()

    if not args.obj and not args.spec:
        parser.error("Must provide either --obj (with optional --image) or --spec.")

    obj_raw = Path(args.obj) if args.obj else None
    img_raw = Path(args.image) if args.image else None
    spec_p = Path(args.spec).resolve() if args.spec else None
    out_dir = Path(args.output).resolve()
    vis_p = Path(args.visual_analysis).resolve() if args.visual_analysis else None

    try:
        obj_p, _ = resolve_obj_path(obj_raw)
        img_p, _ = resolve_image_path(obj_p, img_raw)
        validate_inputs(obj_p, img_p, spec_p)
    except Exception as e:
        print(f"[INPUT ERROR] {e}")
        sys.exit(1)

    success = orchestrate_reconstruction(
        obj_p,
        img_p,
        spec_p,
        out_dir,
        units=args.units,
        visual_analysis_path=vis_p,
        custom_name=args.name,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
