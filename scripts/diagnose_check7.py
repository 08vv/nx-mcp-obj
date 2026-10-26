"""
scripts/diagnose_check7.py
Diagnoses CHECK 7 failures across every built part in output/:
1. Evaluates all CHECK 7 sub-gates (volume, bbox, end gap, X width, Z thickness, section area, surface distance).
2. For failing sub-gates, prints the worst station (axial pos, OBJ val, CAD val, % error).
3. Prints absolute area (mm^2), absolute area diff (mm^2), and equivalent distance error (mm).
4. Prints the per-station table for failing parts.
"""
import json
import math
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from src.nx_mcp.fidelity_checker import run_fidelity_check
from src.nx_mcp.surface_distance_checker import evaluate_surface_distance

targets = [
    ("Axe3", "obj/Axe3.obj", "output/Axe3_Parametric.prt", "output/Axe3_spec.json"),
    ("enamel jar", "obj/elle18-enamel-jar_reduced.obj", "output/elle18-enamel-jar_reduced_Parametric.prt", "output/elle18-enamel-jar_reduced_spec.json"),
    ("lipstick", "obj/Elle18-Liquid-Lipstick.obj", "output/Elle18-Liquid-Lipstick_Parametric.prt", "output/Elle18-Liquid-Lipstick_spec.json"),
    ("eye liner", "obj/Ellie_18_eye_liner.obj", "output/Ellie_18_eye_liner_Parametric.prt", "output/Ellie_18_eye_liner_spec.json"),
    ("Ellie", "obj/Ellie_18_reduced.obj", "output/Ellie_18_reduced_Parametric.prt", "output/Ellie_18_reduced_feature_plan.json"),
    ("Hellmans", "obj/Hellmans_reduced.obj", "output/Hellmans_reduced_Parametric.prt", "output/Hellmans_reduced_spec.json"),
    ("Kissan", "obj/Kissan_Bottle2.obj", "output/Kissan_Bottle2_Parametric.prt", "output/Kissan_Bottle2_spec.json"),
    ("star2", "obj/makeup_cosmetic_star2.obj", "output/makeup_cosmetic_star2_Parametric.prt", "output/makeup_cosmetic_star2_spec.json"),
    ("Oziva", "obj/Oziva4_reduced.obj", "output/Oziva4_reduced_Parametric.prt", "output/Oziva4_reduced_spec.json"),
    ("Vaseline", "obj/Vaseline5_reduced.obj", "output/Vaseline5_reduced_Parametric.prt", "output/Vaseline5_reduced_feature_plan.json"),
]

print("=" * 90)
print("CHECK 7 COMPREHENSIVE SUB-GATE DIAGNOSIS")
print("=" * 90)

diag_summary = []

for label, obj_rel, prt_rel, spec_rel in targets:
    obj_p = repo_root / obj_rel
    prt_p = repo_root / prt_rel
    stl_p = prt_p.with_suffix(".stl")
    spec_p = repo_root / spec_rel
    if not spec_p.exists():
        # fallback
        spec_p = None

    print(f"\n" + "-" * 85)
    print(f"PART: {label} ({obj_p.name})")
    print(f"  PRT:  {prt_p.name}")
    print(f"  STL:  {stl_p.name} (exists={stl_p.exists()})")
    print(f"  SPEC: {spec_p.name if spec_p else 'None'}")

    if not prt_p.exists() or not stl_p.exists() or not obj_p.exists():
        print("  [ERROR] File missing, skipping.")
        continue

    # Run fidelity check
    f_res = run_fidelity_check(
        obj_path=obj_p,
        spec_path=spec_p,
        stl_path=stl_p,
        output_dir=repo_root / "output",
        cad_bounds=None,
        n_stations=50,
    )

    # Sub-gates
    vol_pass = f_res.get("volume_pass", False)
    vol_err = f_res.get("vol_error_pct", 999.0)

    bbox_pass = f_res.get("bbox_pass", False)
    bbox_errs = f_res.get("bbox_errors", {})

    end_gap_pass = f_res.get("end_gap_pass", False)
    gap_bot = f_res.get("gap_bottom_mm", 0.0)
    gap_top = f_res.get("gap_top_mm", 0.0)
    max_gap_allowed = f_res.get("max_axial_gap_allowed_mm", 0.0)

    max_x_pct = f_res.get("max_x_deviation_pct", 0.0)
    max_z_pct = f_res.get("max_z_deviation_pct", 0.0)
    max_area_pct = f_res.get("max_area_deviation_pct", 0.0)

    # Surface check
    surf_eval = evaluate_surface_distance(obj_p, stl_p)
    surf_pass = surf_eval.get("pass", False)

    bot_s = f"{gap_bot:.2f}mm" if gap_bot is not None else "N/A"
    top_s = f"{gap_top:.2f}mm" if gap_top is not None else "N/A"
    max_g_s = f"{max_gap_allowed:.2f}mm" if max_gap_allowed is not None else "N/A"

    sub_gates = {
        "Volume (<=10%)": (vol_pass, f"{vol_err:.2f}%"),
        "BBox (<=10%)": (bbox_pass, f"X:{bbox_errs.get('X',{}).get('error_pct','?')}% Y:{bbox_errs.get('Y',{}).get('error_pct','?')}% Z:{bbox_errs.get('Z',{}).get('error_pct','?')}%"),
        "End Gap (<=1% H)": (end_gap_pass, f"Bot={bot_s} Top={top_s} (Max={max_g_s})"),
        "X Width (<=10%)": (max_x_pct <= 10.0, f"{max_x_pct:.2f}%"),
        "Z Thick (<=10%)": (max_z_pct <= 10.0, f"{max_z_pct:.2f}%"),
        "Section Area (<=10%)": (max_area_pct <= 10.0, f"{max_area_pct:.2f}%"),
        "Surface Dist": (surf_pass, f"Mean={surf_eval.get('mean_distance_mm'):.2f}mm P95={surf_eval.get('p95_distance_mm'):.2f}mm Max={surf_eval.get('max_distance_mm'):.2f}mm"),
    }

    print("  SUB-GATES STATUS:")
    failing_gates = []
    for gname, (gpass, gdetail) in sub_gates.items():
        st = "PASS" if gpass else "FAIL"
        if not gpass:
            failing_gates.append(gname)
        print(f"    - {gname:<22}: [{st}] {gdetail}")

    # Station table analysis
    st_rows = f_res.get("station_rows", [])
    worst_row = None
    worst_area_err = -1.0
    for r in st_rows:
        if r["area_err_pct"] > worst_area_err:
            worst_area_err = r["area_err_pct"]
            worst_row = r

    if worst_row:
        axial_pos = worst_row["axial_mm"]
        obj_area = worst_row["obj_area"]
        cad_area = worst_row["cad_area"]
        area_diff = abs(cad_area - obj_area)
        # Equivalent distance error: radius difference for circles
        r_obj = math.sqrt(obj_area / math.pi) if obj_area > 0 else 0.0
        r_cad = math.sqrt(cad_area / math.pi) if cad_area > 0 else 0.0
        equiv_dist_err = abs(r_cad - r_obj)

        # Check relative height position
        obj_range = f_res.get("obj_axial_range_mm", [0, 100])
        h_span = obj_range[1] - obj_range[0]
        rel_pos = (axial_pos - obj_range[0]) / max(h_span, 1e-4)

        is_end_station = (rel_pos < 0.05 or rel_pos > 0.95)

        print(f"\n  WORST SECTION STATION:")
        print(f"    - Axial Position:       {axial_pos:.2f} mm (relative height: {rel_pos*100:.1f}%, is_end={is_end_station})")
        print(f"    - OBJ Area:             {obj_area:.2f} mm^2")
        print(f"    - CAD Area:             {cad_area:.2f} mm^2")
        print(f"    - Absolute Area Diff:   {area_diff:.2f} mm^2")
        print(f"    - Area Relative Error:  {worst_area_err:.2f}%")
        print(f"    - Equiv Radial Distance Error: {equiv_dist_err:.3f} mm")
        print(f"    - Widths: OBJ={worst_row['obj_width']:.2f} mm, CAD={worst_row['cad_width']:.2f} mm (diff: {abs(worst_row['cad_width']-worst_row['obj_width']):.3f} mm)")

        diag_summary.append({
            "part": label,
            "failing_gates": failing_gates,
            "worst_axial": axial_pos,
            "rel_pos_pct": rel_pos * 100,
            "is_end": is_end_station,
            "obj_area": obj_area,
            "cad_area": cad_area,
            "area_diff": area_diff,
            "area_err_pct": worst_area_err,
            "equiv_dist_err": equiv_dist_err,
        })

    # Print station rows exceeding 10%
    failing_stations = [r for r in st_rows if r["area_err_pct"] > 10.0 or abs(r["cad_width"] - r["obj_width"])/max(r["obj_width"],1e-4) > 0.10]
    if failing_stations:
        print(f"\n  FAILING STATIONS TABLE ({len(failing_stations)} of {len(st_rows)} stations > 10%):")
        print(f"    {'axial':>8} {'OBJ_W':>8} {'CAD_W':>8} {'OBJ_area':>11} {'CAD_area':>11} {'diff_mm2':>10} {'err%':>7} {'equiv_dr':>9} {'pos%':>6}")
        for fs in failing_stations:
            oa, ca = fs["obj_area"], fs["cad_area"]
            diff_a = abs(ca - oa)
            ro = math.sqrt(oa / math.pi) if oa > 0 else 0.0
            rc = math.sqrt(ca / math.pi) if ca > 0 else 0.0
            edr = abs(rc - ro)
            obj_range = f_res.get("obj_axial_range_mm", [0, 100])
            rp = (fs["axial_mm"] - obj_range[0]) / max(obj_range[1] - obj_range[0], 1e-4) * 100
            print(f"    {fs['axial_mm']:>8.2f} {fs['obj_width']:>8.2f} {fs['cad_width']:>8.2f} {oa:>11.2f} {ca:>11.2f} {diff_a:>10.2f} {fs['area_err_pct']:>6.2f}% {edr:>8.3f}mm {rp:>5.1f}%")

print("\n" + "=" * 90)
print("DIAGNOSIS SUMMARY TABLE")
print("=" * 90)
print(f"{'Part':<12} {'Failing Gates':<32} {'Worst Ax':>9} {'RelPos':>7} {'OBJ Area':>10} {'CAD Area':>10} {'Diff mm2':>10} {'Err %':>8} {'Eq Dist':>9}")
for d in diag_summary:
    gates_str = ", ".join(d["failing_gates"])
    print(f"{d['part']:<12} {gates_str:<32} {d['worst_axial']:>9.2f} {d['rel_pos_pct']:>6.1f}% {d['obj_area']:>10.1f} {d['cad_area']:>10.1f} {d['area_diff']:>10.1f} {d['area_err_pct']:>7.2f}% {d['equiv_dist_err']:>8.3f}mm")
