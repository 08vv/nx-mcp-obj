#!/usr/bin/env python3
"""
analyze_obj.py — Geometric & Topological Mesh Analyzer for OBJ-to-Parametric CAD Pipeline

Powered by the nx_mcp.mesh_analyzer engine.
Ingests any Wavefront OBJ mesh file and performs comprehensive geometric analysis:
1. Ingestion, vertex welding, repair, bounding box, extents, volume, and watertightness.
2. Topological genus calculation and handle pass-through opening detection.
3. PCA principal axis alignment & rotational symmetry classification.
4. Connected components decomposition (main body vs accessories/sub-meshes).
5. Cross-section slicing along height axis & silhouette profile extraction.
6. Base loft reconstruction & residual deviation surface mapping.
7. Secondary feature detection:
   - Fluted neck collar / cap ribs
   - Recessed front/back label panels
   - Periodic side ribs / grip grooves (pitch, count, depth, width)
   - Upper front V-features (emboss / deboss)
   - DBSCAN clustered discrete local features & circular pattern layout
8. CAD synthesis recommendation: classification, tool sequence, and NX parametric expressions.

Usage:
    python scripts/analyze_obj.py <path_to_obj_file> [--json] [--slices N] [--output <path>]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure src/ is on sys.path so nx_mcp can be imported directly
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import numpy as np
import trimesh

from nx_mcp.mesh_analyzer import ComprehensiveMeshAnalyzer, analyze_mesh


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze an OBJ mesh file for parametric NX CAD reconstruction."
    )
    parser.add_argument("obj_file", type=str, help="Path to the .obj file.")
    parser.add_argument(
        "--json", action="store_true", help="Output only pure JSON to stdout."
    )
    parser.add_argument(
        "--slices",
        type=int,
        default=21,
        help="Number of cross-section slices along primary axis (default: 21).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional path to save analysis JSON result.",
    )
    return parser.parse_args()


def extract_planar_patches(mesh: trimesh.Trimesh, max_patches: int = 10) -> List[Dict[str, Any]]:
    """Extract significant planar face facets for backward compatibility."""
    planar_patches = []
    try:
        facets = mesh.facets
        facet_areas = []
        for f_indices in facets:
            if len(f_indices) > 20:
                pts = mesh.vertices[mesh.faces[f_indices].flatten()]
                area = float(mesh.area_faces[f_indices].sum() * 10000.0)  # dm² -> mm²
                mean_normal = mesh.face_normals[f_indices].mean(axis=0)
                mean_normal = mean_normal / (np.linalg.norm(mean_normal) + 1e-9)
                facet_areas.append(
                    {
                        "face_count": int(len(f_indices)),
                        "area_mm2": round(area, 2),
                        "normal": [round(float(n), 4) for n in mean_normal],
                        "centroid_mm": [
                            round(float(c * 100.0), 2) for c in pts.mean(axis=0)
                        ],
                    }
                )
        facet_areas.sort(key=lambda x: x["area_mm2"], reverse=True)
        planar_patches = facet_areas[:max_patches]
    except Exception:
        pass
    return planar_patches


def run_analysis(obj_path: str, num_slices: int = 21) -> Dict[str, Any]:
    """Runs complete analysis through the nx_mcp.mesh_analyzer engine with backwards-compatible aliases."""
    p = Path(obj_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"OBJ file not found: {p}")

    analyzer = ComprehensiveMeshAnalyzer(p, num_slices=num_slices, detect_residuals=True)
    report = analyzer.run()

    # Add backwards-compatible aliases for older scripts/skills
    dims = report["dimensions"]
    mesh_info = report["mesh_info"]
    cad_synth = report["cad_synthesis"]
    topology = report["topology"]
    sec_features = report.get("secondary_features", {})

    planar_patches = extract_planar_patches(analyzer.mesh)

    report["file_name"] = p.name
    report["bounding_box"] = {
        "min_corner": dims["bounds_mm"][0],
        "max_corner": dims["bounds_mm"][1],
        "extents": [dims["width_x_mm"], dims["height_y_mm"], dims["depth_z_mm"]],
        "center": dims["centroid_mm"],
        "primary_axis": "Y",
        "primary_length": dims["height_y_mm"],
    }
    report["mesh_stats"] = {
        "vertex_count": mesh_info["vertex_count"],
        "face_count": mesh_info["face_count"],
        "is_watertight": mesh_info["is_watertight"],
        "surface_area": dims["surface_area_mm2"],
        "volume": dims["volume_mm3"],
    }
    report["significant_planar_patches"] = planar_patches

    # Add backward compatibility for CAD synthesis recommended_expressions and recommended_primary_tools
    cad_synth["recommended_expressions"] = cad_synth["expressions"]
    cad_synth["recommended_primary_tools"] = [
        {"tool": t, "args": {}} for t in cad_synth.get("suggested_tools", [])
    ]

    return report


def print_human_readable_report(result: Dict[str, Any]) -> None:
    stats = result["mesh_stats"]
    bbox = result["bounding_box"]
    synth = result["cad_synthesis"]
    topo = result["topology"]
    sec = result.get("secondary_features", {})

    print("=" * 75)
    print(f"OBJ MESH ANALYSIS REPORT: {result.get('file_name', 'Unknown')}")
    print("=" * 75)
    print(f"Vertices:        {stats['vertex_count']:,}")
    print(f"Faces:           {stats['face_count']:,}")
    print(f"Watertight:      {stats['is_watertight']}")
    print(f"Volume:          {stats['volume']:,.2f} mm^3")
    print(f"Surface Area:    {stats['surface_area']:,.2f} mm^2")
    print("-" * 75)
    print("TOPOLOGY & GENUS:")
    print(f"  Euler Char (chi):  {topo.get('euler_characteristic')}")
    print(f"  Genus:             {topo.get('genus', 0)}")
    print(f"  Handle Loop:       {topo.get('has_handle_loop', False)}")
    if topo.get("has_handle_loop") and topo.get("handle_details"):
        hd = topo["handle_details"]
        print(f"  Handle Void Size:  W={hd.get('width_mm', 0):.1f} mm, H={hd.get('height_mm', 0):.1f} mm")
        print(f"  Handle Tilt Angle: {hd.get('tilt_angle_deg', 0):.1f} deg")
    print("-" * 75)
    print("BOUNDING BOX & DIMENSIONS (mm):")
    print(f"  Width (X):         {bbox['extents'][0]:.2f} mm")
    print(f"  Height (Y):        {bbox['extents'][1]:.2f} mm")
    print(f"  Depth (Z):         {bbox['extents'][2]:.2f} mm")
    print(f"  Centroid:          {bbox['center']}")
    print(f"  Is Axisymmetric:   {result.get('alignment', {}).get('is_axisymmetric', False)}")
    print("-" * 75)
    print("SECONDARY FEATURE DETECTION:")
    if not sec:
        print("  None detected.")
    else:
        if "cap_ribs" in sec:
            cap = sec["cap_ribs"]
            print(f"  [CAP ASSEMBLY]     D={cap.get('cap_diameter_mm', 0):.1f}mm, H={cap.get('cap_height_mm', 0):.1f}mm, {cap.get('rib_count')} fluted ribs (pitch={cap.get('rib_pitch_deg', 0):.1f} deg)")
        if "side_ribs" in sec:
            ribs = sec["side_ribs"]
            print(f"  [SIDE RIBS]        {ribs.get('rib_count')} horizontal ribs, pitch={ribs.get('pitch_mm', 0):.1f}mm, groove depth={ribs.get('groove_depth_mm', 0):.1f}mm")
        if "v_feature" in sec:
            v_feat = sec["v_feature"]
            print(f"  [V-FEATURE]        Direction={v_feat.get('direction')}, apex={v_feat.get('apex_position')}, W={v_feat.get('width_mm', 0):.1f}mm, H={v_feat.get('height_mm', 0):.1f}mm")
        if "recessed_panel" in sec:
            panel = sec["recessed_panel"]
            print(f"  [RECESSED PANEL]   W={panel.get('width_mm', 0):.1f}mm, H={panel.get('height_mm', 0):.1f}mm, recess depth={panel.get('recess_depth_mm', 0):.1f}mm")
        if "discrete_clusters" in sec:
            dc = sec["discrete_clusters"]
            print(f"  [DBSCAN CLUSTERS]  {dc.get('feature_count', 0)} discrete features, pattern={dc.get('pattern', {}).get('type', 'none')}")
    print("-" * 75)
    print("PARAMETRIC CAD SYNTHESIS RECOMMENDATION:")
    print(f"  Classification:    {synth['classification']}")
    print(f"  Base Feature:      {synth['base_feature']}")
    print("  Feature Sequence:")
    for step in synth.get("feature_sequence", []):
        print(f"    - {step}")
    print("  Recommended Expressions:")
    for k, v in synth["expressions"].items():
        print(f"    {k} = {v}")
    print("  Suggested Tools:")
    print(f"    {', '.join(synth.get('suggested_tools', []))}")
    print("=" * 75)


def main():
    args = parse_arguments()
    try:
        res = run_analysis(args.obj_file, num_slices=args.slices)
        if args.output:
            out_p = Path(args.output).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            with open(out_p, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2)
            sys.stderr.write(f"Saved analysis to {out_p}\n")

        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print_human_readable_report(res)
    except Exception as e:
        sys.stderr.write(f"Error analyzing OBJ mesh: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
