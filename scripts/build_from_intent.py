#!/usr/bin/env python3
"""
build_from_intent.py — Unified End-to-End Parametric NX CAD Builder (v2)

Takes ANY Wavefront OBJ mesh (or pre-computed v2 Intent IR JSON),
runs it through the generic primitive pipeline:
    OBJ → PrimitiveSegmenter → PrimitiveFeatureExtractor → FeatureGraphBuilder → v2 IR → NX

No domain-specific logic. No per-object scripts.

Usage:
    python scripts/build_from_intent.py <mesh_or_intent> [--output <output.prt>] [--legacy]

Examples:
    python scripts/build_from_intent.py Axe3.obj --output Axe3_Parametric.prt
    python scripts/build_from_intent.py TRESemme6.obj --output TRESemme6_Parametric.prt
    python scripts/build_from_intent.py mechanical_bracket.obj
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure license server is set if not already in environment
os.environ.setdefault("SPLM_LICENSE_SERVER", "28000@SunFibo19")

# Add src/ to path
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from nx_mcp import cli_validate as nx_bridge


def parse_args():
    parser = argparse.ArgumentParser(
        description="Unified End-to-End Parametric NX CAD Rebuilder from Mesh or Intent IR."
    )
    parser.add_argument("input_path", type=str, help="Path to input .obj mesh or intent .json file.")
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Optional output path for the generated .prt file.",
    )
    parser.add_argument(
        "--legacy", action="store_true",
        help="Use legacy ComprehensiveMeshAnalyzer pipeline instead of primitive pipeline.",
    )
    return parser.parse_args()


def analyze_with_primitive_pipeline(obj_path: Path) -> dict:
    """
    Runs the generic primitive pipeline: Segmentation → Feature Extraction → DAG → v2 IR.
    """
    import trimesh
    from nx_mcp.mesh_analyzer.primitive_segmenter import PrimitiveSegmenter
    from nx_mcp.mesh_analyzer.primitive_feature_extractor import PrimitiveFeatureExtractor
    from nx_mcp.mesh_analyzer.feature_graph import FeatureGraphBuilder

    print(f"[PIPELINE] Loading mesh: {obj_path.name}")
    mesh = trimesh.load(str(obj_path), process=False)

    print(f"[PIPELINE] Phase 1: Primitive Surface Segmentation...")
    segmenter = PrimitiveSegmenter(mesh)
    patches = segmenter.segment()
    print(f"  -> {len(patches)} patches: "
          f"{sum(1 for p in patches if p.primitive_type == 'CYLINDER')} cylinders, "
          f"{sum(1 for p in patches if p.primitive_type == 'PLANE')} planes, "
          f"{sum(1 for p in patches if p.primitive_type == 'UNCLASSIFIED_FREEFORM')} freeform")

    print(f"[PIPELINE] Phase 2: Feature Extraction...")
    extractor = PrimitiveFeatureExtractor(mesh, patches)
    features = extractor.extract_features()
    print(f"  -> {len(features)} features: "
          + ", ".join(f"{f.feature_type}({f.feature_id})" for f in features))

    print(f"[PIPELINE] Phase 3: Feature Dependency Graph...")
    builder = FeatureGraphBuilder(mesh, features)
    dag = builder.build_dag()
    ir = dag.to_reconstruction_intent()
    print(f"  -> Shape Family: {ir['global_shape_family']}")
    print(f"  -> Feature Tree: {ir['node_count']} nodes")
    print(f"  -> Expressions: {list(ir['expressions'].keys())}")

    # Enrich the IR with cross-section data for lofted bodies
    if ir["global_shape_family"] == "LOFTED_SOLID":
        try:
            from nx_mcp.mesh_analyzer.section_extractor import MultiSliceCrossSectionSlicer
            from nx_mcp.mesh_analyzer.pca_align import align_to_principal_axes
            aligned = align_to_principal_axes(mesh)
            slicer = MultiSliceCrossSectionSlicer(aligned)
            tiers = slicer.detect_axial_tiers()
            if len(tiers) > 1:
                base_tier = tiers[0]
                sections = slicer.slice_heights(axis="Y", n_slices=21, y_range=(base_tier["y_start"], base_tier["y_end"]))
                ir["cross_sections"] = sections
                ir["axial_tiers"] = tiers
                print(f"  -> Detected {len(tiers)} axial tiers. Base stock loft spans [{base_tier['y_start']:.1f}, {base_tier['y_end']:.1f}]mm")
                for t in tiers[1:]:
                    tier_node = {
                        "node_id": f"tier_{t['tier_index']}_{t['tier_type'].lower()}",
                        "node_type": "SECONDARY_FEATURE",
                        "operation": "CYLINDER" if t["tier_type"] == "TIER_CYLINDER" else "BOSS",
                        "parent_id": "base_solid_1",
                        "parameters": {
                            "diameter_mm": t["diameter_mm"],
                            "height_mm": t["height_mm"],
                            "y_start_mm": t["y_start"],
                            "y_end_mm": t["y_end"],
                            "center": t["center"],
                        },
                        "expressions": {
                            f"P_TIER_{t['tier_index']}_DIAMETER": t["diameter_mm"],
                            f"P_TIER_{t['tier_index']}_HEIGHT": t["height_mm"],
                        }
                    }
                    ir["feature_tree"].append(tier_node)
                    ir["expressions"].update(tier_node["expressions"])
                ir["node_count"] = len(ir["feature_tree"])
            else:
                sections = slicer.extract_sections(n_stations=21)
                ir["cross_sections"] = sections
                print(f"  -> Extracted {len(sections)} cross-sections for loft")

            # Detect through-voids / genus-1 cutouts (e.g. handle openings)
            voids = slicer.detect_through_voids(axis="Y")
            if voids:
                print(f"  -> Detected {len(voids)} through-void cutouts (genus-1 handle openings)")
                for v in voids:
                    void_node = {
                        "node_id": f"through_cutout_{v['void_index'] + 1}",
                        "node_type": "SECONDARY_FEATURE",
                        "operation": "THROUGH_CUTOUT",
                        "parent_id": "base_solid_1",
                        "parameters": {
                            "sketch_pts_2d": v["polygon_2d"],
                            "depth_mm": v["depth_mm"],
                            "start_offset_mm": v["start_offset_mm"],
                            "direction": [0.0, 1.0, 0.0],
                        },
                        "expressions": {
                            f"P_VOID_{v['void_index'] + 1}_HEIGHT": v["height_mm"],
                            f"P_VOID_{v['void_index'] + 1}_DEPTH": v["depth_mm"],
                        }
                    }
                    ir["feature_tree"].append(void_node)
                    ir["expressions"].update(void_node["expressions"])
                ir["node_count"] = len(ir["feature_tree"])
        except Exception as e:
            print(f"  [WARN] Cross-section or void extraction failed: {e}")

    # Enrich the IR with revolve profile for axisymmetric bodies
    if ir["global_shape_family"] == "AXISYMMETRIC_REVOLVE":
        try:
            from nx_mcp.mesh_analyzer.section_extractor import PureRevolveExtractor
            from nx_mcp.mesh_analyzer.pca_align import align_to_principal_axes
            aligned = align_to_principal_axes(mesh)
            rev_ext = PureRevolveExtractor(aligned)
            profile = rev_ext.extract_silhouette_profile(n_samples=80, adaptive=True)
            ir["revolve_profile"] = profile
            print(f"  -> Extracted revolve profile with {len(profile.get('profile_points', []))} points")
        except Exception as e:
            print(f"  [WARN] Revolve profile extraction failed: {e}")

    return ir


def analyze_with_legacy_pipeline(obj_path: Path, num_slices: int = 21) -> dict:
    """Falls back to the original ComprehensiveMeshAnalyzer for backward compatibility."""
    from nx_mcp.mesh_analyzer import ComprehensiveMeshAnalyzer

    print(f"[PIPELINE] Running LEGACY ComprehensiveMeshAnalyzer on {obj_path.name}...")
    analyzer = ComprehensiveMeshAnalyzer(
        obj_path, num_slices=num_slices, detect_residuals=True, adaptive_profile=True,
    )
    report = analyzer.run()
    intent = report.get("reconstruction_intent", {})
    return intent


def main():
    args = parse_args()
    in_path = Path(args.input_path).resolve()
    if not in_path.exists():
        print(f"[ERROR] Input file does not exist: {in_path}")
        sys.exit(1)

    # 1. Determine Output PRT Path
    if args.output:
        out_prt = Path(args.output).resolve()
    else:
        stem = in_path.stem.replace("_intent", "")
        out_prt = _REPO_ROOT / f"{stem}_Parametric.prt"

    print("=" * 75)
    print("UNIFIED PARAMETRIC NX CAD REBUILD PIPELINE (v2 — Generic Primitives)")
    print(f"  Input:  {in_path}")
    print(f"  Target: {out_prt}")
    print("=" * 75)

    # 2. Extract or Load Intent IR
    if in_path.suffix.lower() == ".json":
        intent_json = in_path
    else:
        if args.legacy:
            intent = analyze_with_legacy_pipeline(in_path)
        else:
            intent = analyze_with_primitive_pipeline(in_path)

        # Save staged intent JSON next to output
        intent_json = out_prt.parent / f"{in_path.stem}_v2_intent.json"
        with open(intent_json, "w", encoding="utf-8") as f:
            json.dump(intent, f, indent=2)
        print(f"[PIPELINE] Saved Intent IR: {intent_json}")

    # 3. Execute Generic NX Builder Journal
    if args.legacy:
        engine_journal = _SRC_DIR / "nx_mcp" / "intent_builder.py"
    else:
        engine_journal = _SRC_DIR / "nx_mcp" / "generic_nx_builder.py"

    if not engine_journal.exists():
        print(f"[ERROR] Builder journal not found: {engine_journal}")
        sys.exit(1)

    print(f"[PIPELINE] Executing NX Builder: {engine_journal.name}...")
    result = nx_bridge.run_journal(
        engine_journal,
        str(intent_json),
        str(out_prt),
        timeout=600,
    )

    print(f"Return code: {result.returncode}")
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if not result.ok:
        print(f"[FAIL] Build failed for {out_prt.name}!")
        sys.exit(1)

    print(f"[OK] Parametric model constructed: {out_prt}")
    print("=" * 75)


if __name__ == "__main__":
    main()
