"""Unit tests for Bug 2 fix: pattern_circular/pattern_feature -> add_fillet / get_bounding_box."""

import sys
from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture(autouse=True)
def setup_mock_nxopen():
    mock_nxopen = MagicMock()
    mock_uf_session = MagicMock()
    mock_nxopen.UF.UFSession.GetUFSession.return_value = mock_uf_session
    mock_nxopen.Session.GetSession.return_value = MagicMock()

    orig_nxopen = sys.modules.get("NXOpen")
    orig_nxopen_uf = sys.modules.get("NXOpen.UF")

    sys.modules["NXOpen"] = mock_nxopen
    sys.modules["NXOpen.UF"] = mock_nxopen.UF

    yield

    if orig_nxopen:
        sys.modules["NXOpen"] = orig_nxopen
    else:
        sys.modules.pop("NXOpen", None)
    if orig_nxopen_uf:
        sys.modules["NXOpen.UF"] = orig_nxopen_uf
    else:
        sys.modules.pop("NXOpen.UF", None)


def test_pattern_feature_preserves_target_body_when_no_new_solid_bodies():
    """Verify feature patterns on an existing body do not clobber _state['last_body']."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    part = MagicMock()
    disk_body = MagicMock()
    disk_body.Tag = 1001
    disk_body.GetEdges.return_value = [MagicMock()]
    disk_body.IsSolidBody = True

    # Register disk body
    bid = nx_bridge._register_body(disk_body)
    assert nx_bridge._state["last_body"] == disk_body

    # Setup feature to pattern
    hole_feat = MagicMock()
    hole_feat.Tag = 2001
    hole_feat.GetFeatureName.return_value = "HOLE(1)"
    nx_bridge._register_feature(hole_feat)

    # When pattern commits, part.Bodies still returns disk_body plus a zero-extent tool instance
    tool_body = MagicMock()
    tool_body.Tag = 3001
    tool_body.IsSolidBody = False  # Or degenerate extent

    part.Bodies.ToArray.return_value = [disk_body, tool_body]

    builder = MagicMock()
    pat_feat = MagicMock()
    pat_feat.Tag = 4001
    pat_feat.GetBodies.return_value = []
    builder.CommitFeature.return_value = pat_feat
    part.Features.CreatePatternFeatureBuilder.return_value = builder

    with patch.object(nx_bridge, "_ensure_work_part", return_value=part), \
         patch.object(nx_bridge, "_body_bounds") as mock_bounds:
        
        # Disk body has real extent, tool body has 0 extent
        def bounds_fn(b):
            if b == disk_body:
                return ((-60.0, -60.0, 0.0), (60.0, 60.0, 16.0))
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

        mock_bounds.side_effect = bounds_fn

        res = nx_bridge.pattern_circular(feature_name="last", count=6, angle_total=360.0, axis="Z")
        assert res["ok"] is True
        assert res["produced"] == []
        assert res["modified"] == [bid]

        # Crucial check: _state["last_body"] is STILL the disk body, not tool_body!
        assert nx_bridge._state["last_body"] == disk_body
        assert nx_bridge._resolve_body("last") == disk_body


def test_get_bounding_box_returns_total_part_bounds():
    """Verify get_bounding_box returns bounding box and bounds dict."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    part = MagicMock()
    disk_body = MagicMock()
    disk_body.Tag = 1001
    part.Bodies.ToArray.return_value = [disk_body]
    nx_bridge._register_body(disk_body)

    with patch.object(nx_bridge, "_ensure_work_part", return_value=part), \
         patch.object(nx_bridge, "_body_bounds", return_value=((-60.0, -60.0, 0.0), (60.0, 60.0, 16.0))):
        
        res = nx_bridge.get_bounding_box(body_reference="last")
        assert res["ok"] is True
        assert "bounding_box" in res
        assert res["bounding_box"]["min"] == [-60.0, -60.0, 0.0]
        assert res["bounding_box"]["max"] == [60.0, 60.0, 16.0]
