"""Unit tests for Bug 1 fix: draw_spline -> offset_curve -> close_curve_region."""

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


def test_resolve_single_curve_unrolls_nested_lists():
    """Verify _resolve_single_curve unwraps curve objects from list-of-lists curve_history."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    c1 = MagicMock()
    c1.Tag = 101
    c2 = MagicMock()
    c2.Tag = 102

    nx_bridge._state["curve_history"] = [[c1], [c2]]
    nx_bridge._state["last_curves"] = [c2]

    # Resolve last
    res_last = nx_bridge._resolve_single_curve("last")
    assert res_last == c2
    assert getattr(res_last, "Tag") == 102

    # Resolve previous
    res_prev = nx_bridge._resolve_single_curve("previous")
    assert res_prev == c1
    assert getattr(res_prev, "Tag") == 101


def test_draw_spline_offset_close_region_sequence():
    """Verify draw_spline -> offset_curve -> close_curve_region resolves correctly."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    # Mock work_part points and studio spline builder
    part = MagicMock()
    nx_bridge._state["work_part"] = part
    builder = MagicMock()
    feat = MagicMock()
    curve = MagicMock()
    curve.Tag = 555
    feat.GetEntities.return_value = [curve]
    builder.CommitFeature.return_value = feat
    part.Features.CreateStudioSplineBuilderEx.return_value = builder

    pts = [
        {"x": 10.0, "y": 0.0},
        {"x": 20.0, "y": 5.0},
        {"x": 30.0, "y": 15.0},
        {"x": 40.0, "y": 30.0},
    ]

    with patch.object(nx_bridge, "_ensure_work_part", return_value=part):
        res1 = nx_bridge.draw_spline(points=pts, degree=3, closed=False)
        assert res1["ok"] is True

        res2 = nx_bridge.offset_curve(curve_reference="last", start_width=5.0, end_width=7.0)
        assert res2["ok"] is True

        res3 = nx_bridge.close_curve_region(curve1="last", curve2="previous", method="tangent_lines")
        assert res3["ok"] is True
        assert res3["curve_count"] == 4
