"""
test_feature_graph.py
=====================
Unit tests for Phase 3: Multi-Axis Feature Dependency Graph (CAD DAG).
Verifies:
- Multi-axis local coordinate frame generation.
- Strict topological sort build order: Base Solid -> Subtractive -> Additive -> Pattern -> Blend.
- Cycle detection.
- Geometry-derived Intent IR export.
- Real object graph generation on Axe3 and TRESemme6.
"""

import sys
from pathlib import Path
import numpy as np
import pytest
import trimesh

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from nx_mcp.mesh_analyzer.primitive_segmenter import PrimitiveSegmenter
from nx_mcp.mesh_analyzer.primitive_feature_extractor import PrimitiveFeatureExtractor, ExtractedFeature
from nx_mcp.mesh_analyzer.feature_graph import (
    CADFeatureDAG,
    CADFeatureNode,
    CADNodeType,
    CADOperationType,
    FeatureGraphBuilder,
    LocalDatumFrame,
)


def test_multi_axis_local_datum_frame():
    """Verify arbitrary 3D axis produces orthonormal local frame."""
    # Inclined axis (e.g. 45 degrees in X-Z plane)
    inclined_normal = [0.7071, 0.0, 0.7071]
    origin = [10.0, 20.0, 30.0]
    frame = LocalDatumFrame.from_normal_and_origin(inclined_normal, origin)

    n = np.array(frame.normal)
    u = np.array(frame.x_axis)
    w = np.array(frame.y_axis)

    # Unit lengths
    assert abs(np.linalg.norm(n) - 1.0) < 1e-4
    assert abs(np.linalg.norm(u) - 1.0) < 1e-4
    assert abs(np.linalg.norm(w) - 1.0) < 1e-4

    # Mutual orthogonality
    assert abs(np.dot(n, u)) < 1e-4
    assert abs(np.dot(n, w)) < 1e-4
    assert abs(np.dot(u, w)) < 1e-4


def test_topological_sort_ordering():
    """Verify CAD DAG orders features strictly in dependency hierarchy."""
    dag = CADFeatureDAG()

    # Create Base Solid
    base = CADFeatureNode(
        node_id="base_solid_1",
        node_type=CADNodeType.BASE_SOLID,
        operation=CADOperationType.REVOLVE,
        parent_id=None,
        datum_frame=LocalDatumFrame.from_normal_and_origin([0, 1, 0], [0, 0, 0]),
        parameters={"diameter_mm": 50.0, "length_mm": 100.0},
    )

    # Create Hole attached to Base
    hole = CADFeatureNode(
        node_id="hole_1",
        node_type=CADNodeType.SUBTRACTIVE_FEATURE,
        operation=CADOperationType.HOLE,
        parent_id="base_solid_1",
        datum_frame=LocalDatumFrame.from_normal_and_origin([0, 1, 0], [15, 100, 0]),
        parameters={"diameter_mm": 6.0, "depth_mm": 15.0},
    )

    # Create Pattern replicating Hole
    pattern = CADFeatureNode(
        node_id="pattern_1",
        node_type=CADNodeType.PATTERN_FEATURE,
        operation=CADOperationType.CIRCULAR_PATTERN,
        parent_id="hole_1",
        datum_frame=LocalDatumFrame.from_normal_and_origin([0, 1, 0], [0, 0, 0]),
        parameters={"instance_count": 6, "pitch_deg": 60.0},
    )

    # Add in reverse order to ensure sort reorganizes properly
    dag.add_node(pattern)
    dag.add_node(hole)
    dag.add_node(base)

    sorted_nodes = dag.topological_sort()
    node_ids = [n.node_id for n in sorted_nodes]

    assert node_ids == ["base_solid_1", "hole_1", "pattern_1"]


def test_cycle_detection():
    """Verify that circular dependencies in the DAG are detected and rejected."""
    dag = CADFeatureDAG()

    n1 = CADFeatureNode(
        node_id="n1",
        node_type=CADNodeType.SUBTRACTIVE_FEATURE,
        operation=CADOperationType.HOLE,
        parent_id="n2",
        datum_frame=LocalDatumFrame.from_normal_and_origin([0, 1, 0], [0, 0, 0]),
        parameters={},
    )
    n2 = CADFeatureNode(
        node_id="n2",
        node_type=CADNodeType.SUBTRACTIVE_FEATURE,
        operation=CADOperationType.HOLE,
        parent_id="n1",
        datum_frame=LocalDatumFrame.from_normal_and_origin([0, 1, 0], [0, 0, 0]),
        parameters={},
    )

    dag.add_node(n1)
    dag.add_node(n2)

    with pytest.raises(ValueError, match="Cycle or unresolved dependency"):
        dag.topological_sort()


def test_axe3_feature_graph_generation():
    """Verify DAG generation on Axe3.obj."""
    axe_path = repo_root / "obj" / "Axe3.obj"
    if not axe_path.exists():
        pytest.skip("Axe3.obj not found")

    mesh = trimesh.load(str(axe_path), process=False)
    segmenter = PrimitiveSegmenter(mesh)
    patches = segmenter.segment()

    extractor = PrimitiveFeatureExtractor(mesh, patches)
    features = extractor.extract_features()

    builder = FeatureGraphBuilder(mesh, features)
    dag = builder.build_dag()
    ir = dag.to_reconstruction_intent()

    assert ir["global_shape_family"] == "AXISYMMETRIC_REVOLVE"
    assert "P1_BASE_DIAMETER" in ir["expressions"]
    assert "P2_BASE_HEIGHT" in ir["expressions"]
    assert ir["expressions"]["P1_BASE_DIAMETER"] > 70.0
    assert ir["node_count"] >= 1


def test_tresemme6_feature_graph_generation():
    """Verify DAG generation on TRESemme6.obj."""
    tre_path = repo_root / "obj" / "TRESemme6.obj"
    if not tre_path.exists():
        pytest.skip("TRESemme6.obj not found")

    mesh = trimesh.load(str(tre_path), process=False)
    segmenter = PrimitiveSegmenter(mesh)
    patches = segmenter.segment()

    extractor = PrimitiveFeatureExtractor(mesh, patches)
    features = extractor.extract_features()

    builder = FeatureGraphBuilder(mesh, features)
    dag = builder.build_dag()
    ir = dag.to_reconstruction_intent()

    assert ir["global_shape_family"] == "LOFTED_SOLID"
    assert "P1_LOFT_SPAN_X" in ir["expressions"]
    assert "P2_LOFT_SPAN_Y" in ir["expressions"]
    assert ir["expressions"]["P2_LOFT_SPAN_Y"] > 180.0
    assert ir["node_count"] >= 1


def test_mechanical_bracket_pipeline():
    """Verify Phase 1-3 pipeline on third non-bottle mechanical object."""
    bracket_path = repo_root / "mechanical_bracket.obj"
    if not bracket_path.exists():
        plate = trimesh.creation.box(extents=[100.0, 80.0, 15.0])
        cyl = trimesh.creation.cylinder(radius=20.0, height=30.0)
        cyl.apply_translation([0, 0, 10.0])
        m_combined = plate.union(cyl)
        hole = trimesh.creation.cylinder(radius=10.0, height=50.0)
        bracket_mesh = m_combined.difference(hole)
        bracket_mesh.export(str(bracket_path))

    mesh = trimesh.load(str(bracket_path), process=False)
    segmenter = PrimitiveSegmenter(mesh)
    patches = segmenter.segment()

    extractor = PrimitiveFeatureExtractor(mesh, patches)
    features = extractor.extract_features()

    builder = FeatureGraphBuilder(mesh, features)
    dag = builder.build_dag()
    ir = dag.to_reconstruction_intent()

    assert ir["global_shape_family"] == "PRISMATIC_EXTRUSION"
    assert ir["expressions"]["P1_EXTRUDE_HEIGHT"] in (15.0, 100.0)
    assert ir["node_count"] >= 2


