"""Unit tests for CAD Spec schema and offline static validator."""

import pytest
from nx_mcp.spec.schema import CADSpec, SpecNode, parse_symbolic_ref, parse_expr_ref, parse_calc_ref
from nx_mcp.spec.validator import validate_spec


def test_symbolic_ref_parsers():
    assert parse_symbolic_ref("$n1.body_id") == ("n1", "body_id")
    assert parse_symbolic_ref("$loft_op.feature_id") == ("loft_op", "feature_id")
    assert parse_symbolic_ref("not_a_ref") is None
    assert parse_symbolic_ref(123) is None

    assert parse_expr_ref("$expr:CUBOID_1_L") == "CUBOID_1_L"
    assert parse_expr_ref("not_expr") is None

    assert parse_calc_ref("$calc:50 * 2") == "50 * 2"
    assert parse_calc_ref("$calc:") == ""
    assert parse_calc_ref("not_calc") is None


def test_dependency_auto_inference():
    node = SpecNode.from_dict({
        "id": "n2",
        "op": "add_hole",
        "params": {
            "x": 10.0,
            "y": 10.0,
            "z": 0.0,
            "diameter": 5.0,
            "depth": 10.0,
            "target": "$n1.body_id",
        }
    })
    assert node.depends_on == ["n1"]


def test_valid_spec():
    spec_data = {
        "part_name": "bracket_test",
        "units": "mm",
        "nodes": [
            {
                "id": "n1",
                "op": "create_cuboid",
                "params": {"length": 100.0, "width": 60.0, "height": 20.0},
            },
            {
                "id": "n2",
                "op": "add_hole",
                "params": {
                    "x": 35.0,
                    "y": 20.0,
                    "z": 0.0,
                    "diameter": 8.0,
                    "depth": 20.0,
                    "target": "$n1.body_id",
                },
            },
        ],
    }
    res = validate_spec(spec_data)
    assert res["valid"] is True
    assert res["errors"] == []
    assert res["topological_order"] == ["n1", "n2"]


def test_cycle_detection():
    spec_data = {
        "part_name": "cyclic_test",
        "nodes": [
            {
                "id": "n1",
                "op": "create_cuboid",
                "params": {"length": 100.0, "width": 60.0, "height": 20.0},
                "depends_on": ["n2"],
            },
            {
                "id": "n2",
                "op": "add_hole",
                "params": {"x": 0.0, "y": 0.0, "z": 0.0, "diameter": 8.0, "depth": 20.0, "target": "$n1.body_id"},
                "depends_on": ["n1"],
            },
        ],
    }
    res = validate_spec(spec_data)
    assert res["valid"] is False
    assert any("Cyclic dependency" in e["message"] for e in res["errors"])


def test_missing_and_invalid_reference():
    spec_data = {
        "part_name": "bad_refs",
        "nodes": [
            {
                "id": "n1",
                "op": "create_cuboid",
                "params": {"length": 100.0, "width": 60.0, "height": 20.0},
            },
            {
                "id": "n2",
                "op": "add_hole",
                "params": {"x": 0.0, "y": 0.0, "z": 0.0, "diameter": 8.0, "depth": 20.0, "target": "$n1.non_existent_field"},
            },
            {
                "id": "n3",
                "op": "shell",
                "params": {"body_id": "$ghost_node.body_id", "thickness": 2.0},
            }
        ],
    }
    res = validate_spec(spec_data)
    assert res["valid"] is False
    assert any("non-existent node 'ghost_node'" in e["message"] for e in res["errors"])
    assert any("not known to produce field 'non_existent_field'" in e["message"] for e in res["errors"])


def test_calc_syntax_well_formedness():
    # Valid calc reference is permitted
    valid_spec = {
        "part_name": "calc_test",
        "nodes": [
            {
                "id": "n1",
                "op": "create_cuboid",
                "params": {"length": "$calc:100 * 2", "width": 50.0, "height": 20.0},
            }
        ]
    }
    res = validate_spec(valid_spec)
    assert res["valid"] is True

    # Empty calc reference is rejected
    invalid_spec = {
        "part_name": "calc_bad",
        "nodes": [
            {
                "id": "n1",
                "op": "create_cuboid",
                "params": {"length": "$calc:", "width": 50.0, "height": 20.0},
            }
        ]
    }
    res_bad = validate_spec(invalid_spec)
    assert res_bad["valid"] is False
    assert any("Empty or malformed $calc reference" in e["message"] for e in res_bad["errors"])


def test_loft_to_shell_chain_validation():
    """Verify Phase 3 Loft -> Shell lineage and reference validation."""
    spec_data = {
        "part_name": "loft_shell_spec",
        "nodes": [
            {
                "id": "sec1",
                "op": "create_profile",
                "params": {"points": [[0.0, 0.0], [40.0, 0.0], [40.0, 40.0], [0.0, 40.0]], "plane": "XY"},
            },
            {
                "id": "sec2",
                "op": "create_profile",
                "params": {"points": [[10.0, 10.0, 50.0], [30.0, 10.0, 50.0], [30.0, 30.0, 50.0], [10.0, 30.0, 50.0]], "plane": "XY"},
            },
            {
                "id": "loft1",
                "op": "loft",
                "params": {"profile_ids": ["$sec1.profile_id", "$sec2.profile_id"], "body_type": "solid"},
            },
            {
                "id": "shell1",
                "op": "shell",
                "params": {"body_id": "$loft1.body_id", "thickness": 2.0},
            },
        ]
    }
    res = validate_spec(spec_data)
    assert res["valid"] is True
    assert res["topological_order"] == ["sec1", "sec2", "loft1", "shell1"]


def test_fn_shape_mismatch_rejected():
    """Verify that passing an array-returning $fn: to a scalar number parameter is rejected."""
    spec_data = {
        "part_name": "shape_mismatch",
        "nodes": [
            {
                "id": "n1",
                "op": "create_cuboid",
                "params": {
                    "length": "$fn:bolt_circle(count=4, pcd=50.0)",  # Array into scalar number!
                    "width": 50.0,
                    "height": 20.0,
                },
            }
        ],
    }
    res = validate_spec(spec_data)
    assert res["valid"] is False
    assert any("expects a number, but $fn:bolt_circle(...) produces an array" in e["message"] for e in res["errors"])


def test_calc_shape_mismatch_rejected():
    """Verify that passing a scalar-returning $calc: to an array parameter is rejected."""
    spec_data = {
        "part_name": "calc_shape_mismatch",
        "nodes": [
            {
                "id": "n1",
                "op": "create_profile",
                "params": {
                    "points": "$calc:50.0",  # Scalar number into array!
                    "plane": "XY",
                },
            }
        ],
    }
    res = validate_spec(spec_data)
    assert res["valid"] is False
    assert any("expects a list/array, but $calc:... produces a scalar number" in e["message"] for e in res["errors"])


def test_calc_embedded_invalid_reference_rejected():
    """Verify that $calc: referencing a non-existent node fails validation."""
    spec_data = {
        "part_name": "calc_bad_node",
        "nodes": [
            {
                "id": "n1",
                "op": "create_cuboid",
                "params": {
                    "length": "$calc:$nonexistent_node.body_id + 10",
                    "width": 50.0,
                    "height": 20.0,
                },
            }
        ],
    }
    res = validate_spec(spec_data)
    assert res["valid"] is False
    assert any("references non-existent node 'nonexistent_node'" in e["message"] for e in res["errors"])


def test_fn_missing_required_arg_rejected():
    """Verify that $fn: missing a required argument fails validation."""
    spec_data = {
        "part_name": "fn_missing_arg",
        "nodes": [
            {
                "id": "n1",
                "op": "create_profile",
                "params": {
                    "points": "$fn:bolt_circle(pcd=50.0)",  # Missing required 'count'
                    "plane": "XY",
                },
            }
        ],
    }
    res = validate_spec(spec_data)
    assert res["valid"] is False
    assert any("missing required argument 'count'" in e["message"] for e in res["errors"])


def test_fn_unknown_function_rejected():
    """Verify that $fn: referencing an unknown function name fails validation."""
    spec_data = {
        "part_name": "fn_unknown",
        "nodes": [
            {
                "id": "n1",
                "op": "create_profile",
                "params": {
                    "points": "$fn:make_gear_teeth(n=20)",
                    "plane": "XY",
                },
            }
        ],
    }
    res = validate_spec(spec_data)
    assert res["valid"] is False
    assert any("Unknown geometry function 'make_gear_teeth'" in e["message"] for e in res["errors"])

