#!/usr/bin/env python3
"""
examples/analyze_mesh_intent.py
===============================
Example demonstrating the standalone geometric analysis pipeline:
  1. Primitive Surface Segmentation (planes, cylinders, freeforms)
  2. Mechanical Feature Extraction (extrusion, revolve, loft, holes, pockets, bosses)
  3. Feature Dependency Graph & Parametric Intent IR (driving expressions)

Runs entirely in Python without requiring a running Siemens NX license.

Usage:
    python examples/analyze_mesh_intent.py [path_to_mesh.obj] [--output intent.json]

Example:
    python examples/analyze_mesh_intent.py Axe3.obj
    python examples/analyze_mesh_intent.py TRESemme6.obj
    python examples/analyze_mesh_intent.py Surfexcel2_reduced.obj
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add src/ to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import trimesh
from nx_mcp.mesh_analyzer.primitive_segmenter import PrimitiveSegmenter
from nx_mcp.mesh_analyzer.primitive_feature_extractor import PrimitiveFeatureExtractor
from nx_mcp.mesh_analyzer.feature_graph import FeatureGraphBuilder


def analyze_mesh(mesh_path: Path, output_json: Path | None = None) -> dict:
    """Analyzes a 3D mesh and generates the parametric Reconstruction Intent IR."""
    print("=" * 70)
    print(f"ANALYZING MESH: {mesh_path.name}")
    print("=" * 70)

    mesh = trimesh.load(str(mesh_path), process=False)
    print(f"Mesh Geometry: {len(mesh.vertices):,} vertices, {len(mesh.faces):,} faces")
    print(f"Bounding Box:  {mesh.extents[0]:.2f} x {mesh.extents[1]:.2f} x {mesh.extents[2]:.2f} mm")

    # Phase 1: Primitive Segmentation
    print("\n[Phase 1] Primitive Surface Segmentation...")
    segmenter = PrimitiveSegmenter(mesh)
    patches = segmenter.segment()
    cyls = [p for p in patches if p.primitive_type == "CYLINDER"]
    planes = [p for p in patches if p.primitive_type == "PLANE"]
    freeforms = [p for p in patches if p.primitive_type == "UNCLASSIFIED_FREEFORM"]
    print(f"  -> Total Patches: {len(patches)}")
    print(f"     * Cylinders: {len(cyls)}")
    print(f"     * Planes:    {len(planes)}")
    print(f"     * Freeforms: {len(freeforms)}")

    # Phase 2: Feature Extraction
    print("\n[Phase 2] Topological Feature Extraction...")
    extractor = PrimitiveFeatureExtractor(mesh, patches)
    features = extractor.extract_features()
    for i, feat in enumerate(features):
        print(f"  [{i + 1}] {feat.feature_type}: id={feat.feature_id} (confidence={feat.confidence:.2f})")

    # Phase 3: Feature Dependency Graph & Intent IR
    print("\n[Phase 3] Feature Dependency Graph & Intent IR...")
    builder = FeatureGraphBuilder(mesh, features)
    dag = builder.build_dag()
    ir = dag.to_reconstruction_intent()

    print(f"  -> Shape Family:      {ir['global_shape_family']}")
    print(f"  -> Feature Tree Size: {ir['node_count']} nodes")
    print(f"  -> Driving Expressions ({len(ir['expressions'])}):")
    for name, val in ir["expressions"].items():
        print(f"     * {name} = {val}")

    if output_json:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(ir, f, indent=2)
        print(f"\n[OK] Intent IR saved to: {output_json}")

    print("=" * 70)
    return ir


def main():
    parser = argparse.ArgumentParser(
        description="Inspect mesh segmentation, feature extraction, and intent IR."
    )
    parser.add_argument(
        "mesh_path",
        type=str,
        nargs="?",
        default=str(REPO_ROOT / "Axe3.obj"),
        help="Path to .obj file to analyze (defaults to Axe3.obj).",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Optional path to save generated Intent IR JSON.",
    )
    args = parser.parse_args()

    input_file = Path(args.mesh_path).resolve()
    out_file = Path(args.output).resolve() if args.output else None

    if not input_file.exists():
        print(f"[ERROR] File not found: {input_file}")
        sys.exit(1)

    analyze_mesh(input_file, out_file)


if __name__ == "__main__":
    main()
