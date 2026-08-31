"""Unit tests for post-execution verification (src/nx_mcp/spec/postcheck.py)."""

import pytest
from nx_mcp.spec.postcheck import verify_postexecution
from nx_mcp.state.dependency_graph import GeometryDependencyGraph


def test_valid_postcheck_execution():
    spec = {
        "part_name": "postcheck_valid",
        "nodes": [
            {"id": "base", "op": "create_cuboid", "params": {"length": 100, "width": 50, "height": 20}},
            {"id": "hole", "op": "add_hole", "params": {"target": "$base.body_id", "diameter": 10, "depth": 10}},
        ],
    }

    graph = GeometryDependencyGraph(part_name="postcheck_valid")
    graph.record_operation(
        op="create_cuboid",
        spec_node_id="base",
        produced=["body_1"],
        feature_id="feature_1",
    )
    graph.record_operation(
        op="add_hole",
        spec_node_id="hole",
        modified=["body_1"],
        consumed=["body_2"],
        feature_id="feature_2",
    )

    exec_report = {
        "ok": True,
        "executed_nodes": ["base", "hole"],
        "symbol_table": {
            "base": {"body_id": "body_1", "feature_id": "feature_1"},
            "hole": {"body_id": "body_1", "feature_id": "feature_2"},
        },
    }

    res = verify_postexecution(spec, graph, exec_report, live_check=False)
    assert res["valid"] is True
    assert res["violations_count"] == 0
    assert len(res["passed_checks"]) >= 3


def test_missing_produced_body_violation():
    spec = {
        "part_name": "missing_body",
        "nodes": [
            {"id": "base", "op": "create_cuboid", "params": {"length": 100, "width": 50, "height": 20}},
        ],
    }

    graph = GeometryDependencyGraph(part_name="missing_body")
    # Empty graph where body_1 was never registered

    exec_report = {
        "ok": True,
        "executed_nodes": ["base"],
        "symbol_table": {
            "base": {"body_id": "body_1", "feature_id": "feature_1"},
        },
    }

    res = verify_postexecution(spec, graph, exec_report, live_check=False)
    assert res["valid"] is False
    assert res["violations_count"] >= 1
    assert any(v["check"] == "body_lifecycle" for v in res["violations"])


def test_orphan_feature_violation():
    spec = {
        "part_name": "orphan_feat",
        "nodes": [
            {"id": "base", "op": "create_cuboid", "params": {"length": 100, "width": 50, "height": 20}},
        ],
    }

    graph = GeometryDependencyGraph(part_name="orphan_feat")
    graph.record_operation(
        op="create_cuboid",
        spec_node_id="base",
        produced=["body_1"],
        feature_id="feature_1",
    )
    # Register a feature claiming to be from unexecuted node 'unexecuted_node_x'
    graph.record_operation(
        op="add_fillet",
        spec_node_id="unexecuted_node_x",
        modified=["body_1"],
        feature_id="feature_2",
    )

    exec_report = {
        "ok": True,
        "executed_nodes": ["base"],  # unexecuted_node_x was not executed
        "symbol_table": {
            "base": {"body_id": "body_1", "feature_id": "feature_1"},
        },
    }

    res = verify_postexecution(spec, graph, exec_report, live_check=False)
    assert res["valid"] is False
    assert any(v["check"] == "orphan_feature" for v in res["violations"])


def test_graph_integrity_violation_in_postcheck():
    spec = {
        "part_name": "double_consume",
        "nodes": [
            {"id": "base", "op": "create_cuboid", "params": {"length": 100, "width": 50, "height": 20}},
        ],
    }

    graph = GeometryDependencyGraph(part_name="double_consume")
    graph.record_operation(
        op="create_cuboid",
        spec_node_id="base",
        produced=["body_1"],
        feature_id="feature_1",
    )
    # Manually corrupt graph: mark body_1 as consumed twice
    graph.record_operation(
        op="boolean_subtract",
        spec_node_id="cut1",
        consumed=["body_1"],
        feature_id="feature_2",
    )
    try:
        graph.record_operation(
            op="boolean_subtract",
            spec_node_id="cut2",
            consumed=["body_1"],
            feature_id="feature_3",
        )
    except Exception:
        pass

    exec_report = {
        "ok": True,
        "executed_nodes": ["base"],
        "symbol_table": {
            "base": {"body_id": "body_1", "feature_id": "feature_1"},
        },
    }

    res = verify_postexecution(spec, graph, exec_report, live_check=False)
    assert res["valid"] is False
    assert any(v["check"] == "graph_integrity" for v in res["violations"])


def test_complex_multi_op_postcheck():
    spec = {
        "part_name": "complex_part",
        "nodes": [
            {"id": "sec1", "op": "create_profile", "params": {"points": [[0, 0], [10, 0], [10, 10], [0, 10]]}},
            {"id": "sec2", "op": "create_profile", "params": {"points": [[0, 0, 20], [10, 0, 20], [10, 10, 20], [0, 10, 20]]}},
            {"id": "loft1", "op": "loft", "params": {"profile_ids": ["$sec1.profile_id", "$sec2.profile_id"]}},
            {"id": "hole1", "op": "add_hole", "params": {"target": "$loft1.body_id", "diameter": 4, "depth": 10}},
            {"id": "shell1", "op": "shell", "params": {"body_id": "$loft1.body_id", "thickness": 1.0}},
        ],
    }

    graph = GeometryDependencyGraph(part_name="complex_part")
    graph.record_operation(op="create_profile", spec_node_id="sec1", produced=["profile_1"])
    graph.record_operation(op="create_profile", spec_node_id="sec2", produced=["profile_2"])
    graph.record_operation(op="loft", spec_node_id="loft1", consumed=["profile_1", "profile_2"], produced=["body_1"], feature_id="feature_1")
    graph.record_operation(op="add_hole", spec_node_id="hole1", modified=["body_1"], consumed=["body_2"], feature_id="feature_2")
    graph.record_operation(op="shell", spec_node_id="shell1", modified=["body_1"], feature_id="feature_3")

    exec_report = {
        "ok": True,
        "executed_nodes": ["sec1", "sec2", "loft1", "hole1", "shell1"],
        "symbol_table": {
            "sec1": {"profile_id": "profile_1"},
            "sec2": {"profile_id": "profile_2"},
            "loft1": {"body_id": "body_1", "feature_id": "feature_1"},
            "hole1": {"body_id": "body_1", "feature_id": "feature_2"},
            "shell1": {"body_id": "body_1", "feature_id": "feature_3"},
        },
    }

    res = verify_postexecution(spec, graph, exec_report, live_check=False)
    assert res["valid"] is True
    assert res["metrics"]["alive_bodies"] == ["body_1"]
    assert res["metrics"]["consumed_bodies"] == ["body_2"]
    assert res["violations_count"] == 0

