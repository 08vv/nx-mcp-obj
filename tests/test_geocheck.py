"""Unit tests for geocheck.py — geometric and visual verification."""

import pytest
from nx_mcp.spec.geocheck import verify_geometry
from nx_mcp.spec.schema import CADSpec
from nx_mcp.state.dependency_graph import GeometryDependencyGraph


def test_geocheck_basic_spec_passes():
    """Verify basic solid spec passes geometric checks in mock mode."""
    spec = {
        "part_name": "geocheck_basic",
        "nodes": [
            {"id": "base", "op": "create_cuboid", "params": {"length": 50, "width": 50, "height": 20}},
            {"id": "hole", "op": "add_hole", "params": {"diameter": 10, "depth": 10, "target": "$base.body_id"}},
        ],
    }
    graph = GeometryDependencyGraph(part_name="geocheck_basic")
    graph.record_operation("create_cuboid", spec_node_id="base", produced=["body_1"])
    graph.record_operation("add_hole", spec_node_id="hole", modified=["body_1"], feature_id="feature_1")

    exec_report = {
        "executed_nodes": ["base", "hole"],
        "symbol_table": {"base": {"body_id": "body_1"}, "hole": {"feature_id": "feature_1"}},
        "node_results": {},
    }

    report = verify_geometry(spec, graph, exec_report, capture_screenshot=True, live_check=False)
    assert report["valid"] is True
    assert report["violations_count"] == 0
    assert report["screenshot_path"] is not None
    assert report["screenshot_path"].endswith(".png")
    assert len(report["passed_checks"]) >= 3


def test_geocheck_pattern_symmetry():
    """Verify pattern symmetry check tracks instance count."""
    spec = {
        "part_name": "geocheck_pattern",
        "nodes": [
            {"id": "base", "op": "create_cuboid", "params": {"length": 50, "width": 50, "height": 20}},
            {"id": "pat", "op": "pattern", "params": {"count": 4, "feature_ref": "$base.body_id"}},
        ],
    }
    graph = GeometryDependencyGraph(part_name="geocheck_pattern")
    graph.record_operation("create_cuboid", spec_node_id="base", produced=["body_1"])
    graph.record_operation("pattern", spec_node_id="pat", produced=["body_2", "body_3", "body_4", "body_5"])

    exec_report = {
        "executed_nodes": ["base", "pat"],
        "symbol_table": {"base": {"body_id": "body_1"}},
        "node_results": {"pat": {"body_ids": ["body_2", "body_3", "body_4", "body_5"]}},
    }

    report = verify_geometry(spec, graph, exec_report, live_check=False)
    assert report["valid"] is True
    passed_pattern = any(c["check"] == "pattern_symmetry" for c in report["passed_checks"])
    assert passed_pattern is True
