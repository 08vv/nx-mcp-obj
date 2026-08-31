"""Unit tests for pre-execution plausibility validation (src/nx_mcp/spec/plausibility.py)."""

import pytest
from nx_mcp.spec.plausibility import validate_plausibility


def test_valid_spec_plausibility():
    spec = {
        "part_name": "valid_bracket",
        "nodes": [
            {
                "id": "base",
                "op": "create_cuboid",
                "params": {"length": 100.0, "width": 60.0, "height": 20.0},
            },
            {
                "id": "hole1",
                "op": "add_hole",
                "params": {"target": "$base.body_id", "diameter": 10.0, "depth": 15.0},
            },
            {
                "id": "blend",
                "op": "add_fillet",
                "params": {"body": "$base.body_id", "radius": 2.0},
            },
        ],
    }
    res = validate_plausibility(spec)
    assert res["plausible"] is True
    assert len(res["errors"]) == 0
    assert res["checks_performed"] >= 5


def test_negative_or_zero_dimension_error():
    spec = {
        "part_name": "bad_dim",
        "nodes": [
            {
                "id": "base",
                "op": "create_cuboid",
                "params": {"length": 100.0, "width": -50.0, "height": "$calc:10 - 10"},
            }
        ],
    }
    res = validate_plausibility(spec)
    assert res["plausible"] is False
    assert len(res["errors"]) == 2
    err_params = [e["param"] for e in res["errors"]]
    assert "width" in err_params
    assert "height" in err_params


def test_hole_diameter_exceeding_body_error():
    spec = {
        "part_name": "oversized_hole",
        "nodes": [
            {
                "id": "base",
                "op": "create_cuboid",
                "params": {"length": 50.0, "width": 30.0, "height": 20.0},
            },
            {
                "id": "huge_hole",
                "op": "add_hole",
                "params": {"target": "$base.body_id", "diameter": 35.0, "depth": 15.0},
            },
        ],
    }
    res = validate_plausibility(spec)
    assert res["plausible"] is False
    assert len(res["errors"]) == 1
    assert res["errors"][0]["check"] == "hole_diameter_vs_body"


def test_hole_diameter_warning_and_strict_mode():
    spec = {
        "part_name": "tight_hole",
        "nodes": [
            {
                "id": "base",
                "op": "create_cuboid",
                "params": {"length": 100.0, "width": 50.0, "height": 20.0},
            },
            {
                "id": "tight_hole",
                "op": "add_hole",
                "params": {"target": "$base.body_id", "diameter": 45.0, "depth": 10.0},
            },
        ],
    }
    res_normal = validate_plausibility(spec, strict=False)
    assert res_normal["plausible"] is True
    assert len(res_normal["errors"]) == 0
    assert len(res_normal["warnings"]) == 1

    res_strict = validate_plausibility(spec, strict=True)
    assert res_strict["plausible"] is False
    assert len(res_strict["warnings"]) == 1


def test_shell_thickness_exceeding_half_dimension_error():
    spec = {
        "part_name": "thick_shell",
        "nodes": [
            {
                "id": "base",
                "op": "create_cuboid",
                "params": {"length": 100.0, "width": 60.0, "height": 20.0},
            },
            {
                "id": "bad_shell",
                "op": "shell",
                "params": {"body_id": "$base.body_id", "thickness": 12.0},  # 12 >= 0.5 * 20
            },
        ],
    }
    res = validate_plausibility(spec)
    assert res["plausible"] is False
    assert any(e["check"] == "shell_thickness_vs_body" for e in res["errors"])


def test_blend_radius_exceeding_half_dimension_error():
    spec = {
        "part_name": "excessive_fillet",
        "nodes": [
            {
                "id": "cyl",
                "op": "create_cylinder",
                "params": {"radius": 10.0, "height": 30.0},  # min_dim = 20.0
            },
            {
                "id": "bad_fillet",
                "op": "add_fillet",
                "params": {"body": "$cyl.body_id", "radius": 15.0},  # 15 >= 0.5 * 20
            },
        ],
    }
    res = validate_plausibility(spec)
    assert res["plausible"] is False
    assert any(e["check"] == "blend_radius_vs_body" for e in res["errors"])


def test_pattern_count_error():
    spec = {
        "part_name": "bad_pattern",
        "nodes": [
            {
                "id": "box",
                "op": "create_cuboid",
                "params": {"length": 50.0, "width": 50.0, "height": 10.0},
            },
            {
                "id": "pat",
                "op": "pattern",
                "params": {"feature_ref": "$box.feature_id", "mode": "circular", "count": 1},
            },
        ],
    }
    res = validate_plausibility(spec)
    assert res["plausible"] is False
    assert any(e["check"] == "pattern_count" for e in res["errors"])


def test_unresolvable_target_recorded_as_not_checked():
    spec = {
        "part_name": "loft_hole",
        "nodes": [
            {
                "id": "sec1",
                "op": "create_profile",
                "params": {"points": [[0, 0], [10, 0], [10, 10], [0, 10]], "plane": "XY"},
            },
            {
                "id": "sec2",
                "op": "create_profile",
                "params": {"points": [[0, 0, 20], [10, 0, 20], [10, 10, 20], [0, 10, 20]], "plane": "XY"},
            },
            {
                "id": "loft1",
                "op": "loft",
                "params": {"profile_ids": ["$sec1.profile_id", "$sec2.profile_id"]},
            },
            {
                "id": "hole1",
                "op": "add_hole",
                "params": {"target": "$loft1.body_id", "diameter": 5.0, "depth": 10.0},
            },
        ],
    }
    res = validate_plausibility(spec)
    assert res["plausible"] is True
    assert res["checks_not_checked"] >= 1
    assert any(d["status"] == "not_checked" for d in res["details"])
