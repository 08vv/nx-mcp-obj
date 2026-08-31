"""Unit tests for CAD Spec operation graph executor (mock mode)."""

import pytest
from nx_mcp.spec.executor import SpecExecutor, execute_spec, SpecExecutionError
from nx_mcp.spec.schema import CADSpec


def test_executor_steppable_execution():
    spec_data = {
        "part_name": "steppable_test",
        "units": "mm",
        "nodes": [
            {
                "id": "n1",
                "op": "create_cuboid",
                "params": {"length": 100.0, "width": 50.0, "height": 30.0},
            },
            {
                "id": "n2",
                "op": "add_hole",
                "params": {
                    "x": 20.0,
                    "y": 20.0,
                    "z": 0.0,
                    "diameter": 10.0,
                    "depth": 15.0,
                    "target": "$n1.body_id",
                },
            },
        ],
    }
    executor = SpecExecutor(spec_data)
    assert executor.has_next()
    assert executor.status == "pending"

    # Step 1: execute n1
    step1 = executor.execute_next_node()
    assert step1["ok"] is True
    assert step1["node_id"] == "n1"
    assert "body_id" in executor.symbol_table["n1"]
    assert executor.has_next()

    # Step 2: execute n2
    step2 = executor.execute_next_node()
    assert step2["ok"] is True
    assert step2["node_id"] == "n2"
    assert not executor.has_next()
    assert executor.status == "completed"


def test_execute_spec_atomic_and_symbol_resolution():
    spec_data = {
        "part_name": "atomic_test",
        "nodes": [
            {
                "id": "base",
                "op": "create_cuboid",
                "params": {"length": 80.0, "width": 40.0, "height": 20.0},
            },
            {
                "id": "cut",
                "op": "add_hole",
                "params": {
                    "x": 10.0,
                    "y": 10.0,
                    "z": 0.0,
                    "diameter": 6.0,
                    "depth": 10.0,
                    "target": "$base.body_id",
                },
            },
            {
                "id": "hollow",
                "op": "shell",
                "params": {
                    "body_id": "$base.body_id",
                    "thickness": 2.0,
                },
            },
        ],
    }
    report = execute_spec(spec_data)
    assert report["ok"] is True
    assert report["status"] == "completed"
    assert report["total_nodes"] == 3
    assert report["executed_nodes"] == ["base", "cut", "hollow"]
    assert report["skipped_nodes"] == []
    assert "base" in report["symbol_table"]
    assert "cut" in report["symbol_table"]
    assert "hollow" in report["symbol_table"]


def test_calc_reference_evaluates():
    """Phase 5: $calc:... expressions are now evaluated by the calc engine."""
    spec_data = {
        "part_name": "calc_eval_test",
        "nodes": [
            {
                "id": "n1",
                "op": "create_cuboid",
                "params": {
                    "length": "$calc:100 * 2",
                    "width": "$calc:60 / 2 + 5",
                    "height": 20.0,
                },
            }
        ],
    }
    report = execute_spec(spec_data)
    assert report["ok"] is True
    assert report["status"] == "completed"


def test_fn_bolt_circle_resolves():
    """Phase 5: $fn:bolt_circle(...) resolves to a list of [x, y] coordinates."""
    spec_data = {
        "part_name": "fn_test",
        "nodes": [
            {
                "id": "n1",
                "op": "create_profile",
                "params": {
                    "points": "$fn:bolt_circle(count=4, pcd=100.0)",
                    "plane": "XY",
                    "closed": True,
                },
            }
        ],
    }
    report = execute_spec(spec_data)
    assert report["ok"] is True
    assert report["status"] == "completed"


def test_fn_linear_spacing_resolves():
    """Phase 5: $fn:linear_spacing(...) resolves to a list of [x, y] coordinates."""
    spec_data = {
        "part_name": "linear_test",
        "nodes": [
            {
                "id": "n1",
                "op": "create_profile",
                "params": {
                    "points": "$fn:linear_spacing(count=3, pitch=25.0)",
                    "plane": "XY",
                },
            }
        ],
    }
    report = execute_spec(spec_data)
    assert report["ok"] is True


def test_fillet_and_chamfer_produces_symbols():
    """Verify that fillet and chamfer nodes populate feature_id and body_id in symbol table."""
    spec_data = {
        "part_name": "fillet_chamfer_symbols",
        "nodes": [
            {
                "id": "base",
                "op": "create_cuboid",
                "params": {"length": 100.0, "width": 60.0, "height": 20.0},
            },
            {
                "id": "blend",
                "op": "add_fillet",
                "params": {"radius": 2.0, "body": "$base.body_id"},
            },
            {
                "id": "bevel",
                "op": "add_chamfer",
                "params": {"offset": 1.0, "body": "$blend.body_id"},
            },
        ],
    }
    report = execute_spec(spec_data)
    assert report["ok"] is True
    assert "blend" in report["symbol_table"]
    assert "feature_id" in report["symbol_table"]["blend"]
    assert "body_id" in report["symbol_table"]["blend"]
    assert "bevel" in report["symbol_table"]
    assert "feature_id" in report["symbol_table"]["bevel"]
    assert "body_id" in report["symbol_table"]["bevel"]


def test_executor_populates_dependency_graph():
    """Verify that SpecExecutor populates the GeometryDependencyGraph and includes it in report."""
    spec_data = {
        "part_name": "graph_exec_test",
        "nodes": [
            {
                "id": "sec1",
                "op": "create_profile",
                "params": {"points": [[0.0, 0.0], [50.0, 0.0], [50.0, 50.0], [0.0, 50.0]], "plane": "XY"},
            },
            {
                "id": "sec2",
                "op": "create_profile",
                "params": {"points": [[10.0, 10.0, 30.0], [40.0, 10.0, 30.0], [40.0, 40.0, 30.0], [10.0, 40.0, 30.0]], "plane": "XY"},
            },
            {
                "id": "loft1",
                "op": "loft",
                "params": {"profile_ids": ["$sec1.profile_id", "$sec2.profile_id"], "body_type": "solid"},
            },
            {
                "id": "cut1",
                "op": "add_hole",
                "params": {"x": 25.0, "y": 25.0, "z": 0.0, "diameter": 10.0, "depth": 15.0, "target": "$loft1.body_id"},
            },
            {
                "id": "shell1",
                "op": "shell",
                "params": {"body_id": "$loft1.body_id", "thickness": 2.0},
            },
        ],
    }
    report = execute_spec(spec_data)
    assert report["ok"] is True
    assert "dependency_graph" in report
    graph_dict = report["dependency_graph"]
    assert graph_dict["part_name"] == "graph_exec_test"
    assert graph_dict["total_nodes"] >= 5
    assert len(graph_dict["edges"]) >= 4

    # Verify query tools work on the resulting session graph
    from nx_mcp.tools.state_tools import get_dependency_graph, get_downstream, get_upstream, validate_dependency_graph

    graph_res = get_dependency_graph()
    assert not graph_res.is_error if hasattr(graph_res, "is_error") else True
    assert "Geometry Dependency Graph" in str(graph_res)

    val_res = validate_dependency_graph()
    assert "VALID" in str(val_res)

    # Check upstream of body_1
    loft_body_id = report["symbol_table"]["loft1"]["body_id"]
    upstream_res = get_upstream(loft_body_id)
    assert not upstream_res.is_error if hasattr(upstream_res, "is_error") else True
    assert loft_body_id in str(upstream_res)



