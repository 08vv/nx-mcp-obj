"""
scripts/extract_and_plot_outlines.py
====================================
Extracts, resamples, and plots zero-twist cross-section outlines for non-round meshes
(Vaseline5_reduced.obj and Ellie_18_reduced.obj).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.nx_mcp.mesh_analyzer.loft_profile_extractor import (
    DEFAULT_LOFT_STATIONS,
    DEFAULT_POINTS_PER_OUTLINE,
    extract_cross_section_outlines,
    save_outlines_to_json,
    plot_outlines_overlay,
)


def process_mesh(mesh_name: str, output_dir: Path):
    mesh_path = REPO_ROOT / "obj" / mesh_name
    print(f"\n" + "=" * 75)
    print(f"PROCESSING MESH: {mesh_name}")
    print(f"=" * 75)
    print(f"  Mesh file: {mesh_path}")
    print(f"  Stations:  {DEFAULT_LOFT_STATIONS} (named constant DEFAULT_LOFT_STATIONS)")
    print(f"  Points:    {DEFAULT_POINTS_PER_OUTLINE} per station (named constant DEFAULT_POINTS_PER_OUTLINE)")

    data = extract_cross_section_outlines(
        mesh_path=mesh_path,
        n_stations=DEFAULT_LOFT_STATIONS,
        n_points=DEFAULT_POINTS_PER_OUTLINE,
    )

    stem = mesh_path.stem
    json_path = output_dir / f"{stem}_outlines.json"
    plot_path = output_dir / f"{stem}_outlines.png"

    save_outlines_to_json(data, json_path)
    plot_outlines_overlay(mesh_path, data, plot_path)

    print(f"\n  Extracted {data['n_stations']} Cross-Section Stations:")
    print(f"  Primary Height Axis: {data['primary_axis']} (Height Span: {data['total_height_mm']} mm)")
    print(f"  Transverse Axes:     {data['transverse_axes'][0]} and {data['transverse_axes'][1]}")
    print(f"  Points Per Outline:  {data['points_per_station']}")
    print(f"\n  Station Elevations, Dimensions, Smoothing Loss, and Start Point Z-Drift:")
    print(f"    {'St':<3} | {'Elev(mm)':<9} | {'T1_W(mm)':<9} | {'T2_W(mm)':<9} | {'Area(mm2)':<10} | {'AreaLoss%':<10} | {'W1Loss%':<8} | {'W2Loss%':<8} | {'Start_Z_Drift':<13} | {'StartPt'}")
    print("    " + "-"*115)
    for st in data["stations"]:
        idx = st["station_index"]
        elev = st["elevation"]
        w1 = st["width_t1"]
        w2 = st["width_t2"]
        area = st["area_mm2"]
        sp = st["start_point"]
        sm = st.get("smoothing_metrics", {})
        a_loss = sm.get("area_loss_pct", 0.0)
        w1_loss = sm.get("w1_loss_pct", 0.0)
        w2_loss = sm.get("w2_loss_pct", 0.0)
        z_drift = sm.get("start_z_drift_mm", 0.0)
        print(f"    [{idx:2d}] | {elev:9.2f} | {w1:9.2f} | {w2:9.2f} | {area:10.2f} | {a_loss:9.3f}% | {w1_loss:7.3f}% | {w2_loss:7.3f}% | {z_drift:10.4f} mm | {sp}")

    print(f"\n  Saved JSON: {json_path}")
    print(f"  Saved Plot: {plot_path}")
    return json_path, plot_path


def main():
    out_dir = REPO_ROOT / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = ["Ellie_18_reduced.obj", "Vaseline5_reduced.obj"]
    for t in targets:
        process_mesh(t, out_dir)


if __name__ == "__main__":
    main()
