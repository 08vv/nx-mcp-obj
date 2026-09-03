"""Unit and regression tests for RC3 Root Fix: feature and body state registration integrity."""

import sys
from unittest.mock import MagicMock, patch
import pytest


def test_register_body_set_last_flag():
    """Verify _register_body respects set_last flag."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    b1 = MagicMock()
    b1.Tag = 101
    b2 = MagicMock()
    b2.Tag = 102

    # Register b1 as last_body
    bid1 = nx_bridge._register_body(b1, set_last=True)
    assert nx_bridge._state["last_body"] == b1
    assert nx_bridge._state["last_body_id"] == bid1

    # Register b2 with set_last=False (e.g. secondary/tool body)
    bid2 = nx_bridge._register_body(b2, set_last=False)
    assert bid2 == "body_2"
    assert nx_bridge._state["last_body"] == b1
    assert nx_bridge._state["last_body_id"] == bid1


def test_register_feature_does_not_hijack_last_body():
    """Verify modifying feature with multiple bodies does not corrupt last_body."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    target_body = MagicMock()
    target_body.Tag = 201
    tool_body = MagicMock()
    tool_body.Tag = 202

    with patch.object(nx_bridge, "_is_real_solid_body", return_value=True):
        # Initial target body
        t_id = nx_bridge._register_body(target_body, set_last=True)

        feat = MagicMock()
        feat.Tag = 501
        # Feature returns tool body and target body
        feat.GetBodies.return_value = [tool_body, target_body]
        feat.GetEntities.return_value = []

        # Modifying feature with explicit target_body
        fid = nx_bridge._register_feature(feat, target_body=target_body, is_creation=False)
        assert fid == "feature_1"
        assert nx_bridge._state["last_body"] == target_body
        assert nx_bridge._state["last_body_id"] == t_id


def test_sequential_holes_state_tracking_mock():
    """Verify sequential holes on a target body maintain stable last_body_id."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    mock_wp = MagicMock()
    target_body = MagicMock()
    target_body.Tag = 301
    target_body.GetEdges.return_value = []

    with patch.object(nx_bridge, "_ensure_work_part", return_value=mock_wp), \
         patch.object(nx_bridge, "_is_real_solid_body", return_value=True), \
         patch.object(nx_bridge, "_resolve_hole_direction", return_value="-Z"), \
         patch.object(nx_bridge, "_body_bounds", return_value=((0, 0, 0), (20, 20, 20))):

        # Initial solid creation
        t_id = nx_bridge._register_body(target_body, set_last=True)
        assert t_id == "body_1"

        # Mock HoleBuilder
        builder = MagicMock()
        feat_hole = MagicMock()
        feat_hole.Tag = 601
        feat_hole.GetBodies.return_value = [target_body]
        feat_hole.GetEntities.return_value = []
        builder.CommitFeature.return_value = feat_hole
        mock_wp.Features.CreateHoleBuilder.return_value = builder

        # Sequential Hole 1
        r1 = nx_bridge.add_hole(x=10, y=10, z=20, diameter=4, depth=10, target="last")
        assert r1["ok"] is True
        assert r1["body_id"] == "body_1"
        assert nx_bridge._state["last_body_id"] == "body_1"

        # Sequential Hole 2
        feat_hole2 = MagicMock()
        feat_hole2.Tag = 602
        feat_hole2.GetBodies.return_value = [target_body]
        feat_hole2.GetEntities.return_value = []
        builder.CommitFeature.return_value = feat_hole2

        r2 = nx_bridge.add_hole(x=5, y=5, z=20, diameter=4, depth=10, target="last")
        assert r2["ok"] is True
        assert r2["body_id"] == "body_1"
        assert nx_bridge._state["last_body_id"] == "body_1"
