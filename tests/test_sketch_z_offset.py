"""Unit and regression tests for Bug 5: 2D Sketch and Curve Z-offset positioning."""

import math, sys
from unittest.mock import MagicMock, patch
import pytest


class FakePoint3d:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X = float(x)
        self.Y = float(y)
        self.Z = float(z)

    def __repr__(self):
        return f"Point3d({self.X}, {self.Y}, {self.Z})"


class FakeVector3d:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X = float(x)
        self.Y = float(y)
        self.Z = float(z)

    def __repr__(self):
        return f"Vector3d({self.X}, {self.Y}, {self.Z})"


@pytest.fixture(autouse=True)
def setup_mock_nxopen():
    from nx_mcp.bridge import nx_bridge

    orig_pt = getattr(nx_bridge.NXOpen, "Point3d", None)
    orig_vec = getattr(nx_bridge.NXOpen, "Vector3d", None)

    nx_bridge.NXOpen.Point3d = FakePoint3d
    nx_bridge.NXOpen.Vector3d = FakeVector3d

    yield

    if orig_pt:
        nx_bridge.NXOpen.Point3d = orig_pt
    if orig_vec:
        nx_bridge.NXOpen.Vector3d = orig_vec


def test_create_sketch_with_z_offset_and_origin():
    """Verify create_sketch updates _state sketch_origin and sketch_rotation."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    part = MagicMock()
    with patch.object(nx_bridge, "_ensure_work_part", return_value=part):
        r = nx_bridge.create_sketch(plane="XY", z_offset=39.0, origin_x=5.0, origin_y=10.0, rotate_z_deg=45.0)
        assert r["ok"] is True
        assert nx_bridge._state["sketch_origin"] == [5.0, 10.0, 39.0]
        assert nx_bridge._state["sketch_rotation"] == 45.0
        assert nx_bridge.ACTIVE_SKETCH_PLANE == "XY"


def test_point_on_active_plane_with_z_offset_and_override():
    """Verify _point_on_active_plane correctly transforms 2D points to 3D."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    part = MagicMock()
    with patch.object(nx_bridge, "_ensure_work_part", return_value=part):
        nx_bridge.create_sketch(plane="XY", z_offset=39.0)

        # Standard point at Z=39.0
        pt = nx_bridge._point_on_active_plane(10.0, 20.0)
        assert pt.X == 10.0
        assert pt.Y == 20.0
        assert pt.Z == 39.0

        # Point with explicit z_override=50.0
        pt_override = nx_bridge._point_on_active_plane(10.0, 20.0, z_override=50.0)
        assert pt_override.X == 10.0
        assert pt_override.Y == 20.0
        assert pt_override.Z == 50.0


def test_draw_rounded_rectangle_passes_z_offset():
    """Verify draw_rounded_rectangle applies z parameter to curve vertices."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    part = MagicMock()
    created_points = []

    def fake_create_line(p1, p2):
        created_points.extend([p1, p2])
        line = MagicMock()
        return line

    def fake_create_arc(center, xdir, ydir, radius, start_rad, end_rad):
        created_points.append(center)
        arc = MagicMock()
        return arc

    part.Curves.CreateLine.side_effect = fake_create_line
    part.Curves.CreateArc.side_effect = fake_create_arc

    with patch.object(nx_bridge, "_ensure_work_part", return_value=part):
        nx_bridge.create_sketch(plane="XY", z_offset=0.0)
        r = nx_bridge.draw_rounded_rectangle(arm_length=40.0, arm_width=16.0, end_radius=8.0, z=39.0)
        assert r["ok"] is True
        assert len(created_points) > 0
        assert all(pt.Z == 39.0 for pt in created_points)


def test_draw_primitives_accept_z_override():
    """Verify draw_rectangle, draw_circle, draw_line, draw_arc, draw_spline accept z."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    part = MagicMock()
    builder = MagicMock()
    feat = MagicMock()
    feat.GetEntities.return_value = [MagicMock()]
    builder.CommitFeature.return_value = feat
    part.Features.CreateStudioSplineBuilderEx.return_value = builder

    with patch.object(nx_bridge, "_ensure_work_part", return_value=part):
        nx_bridge.create_sketch(plane="XY")

        r_rect = nx_bridge.draw_rectangle(x=0, y=0, width=10, height=10, z=39.0)
        assert r_rect["ok"] is True

        r_circ = nx_bridge.draw_circle(cx=0, cy=0, radius=5, z=39.0)
        assert r_circ["ok"] is True

        r_line = nx_bridge.draw_line(x1=0, y1=0, x2=10, y2=10, z=39.0)
        assert r_line["ok"] is True

        r_arc = nx_bridge.draw_arc(cx=0, cy=0, radius=5, start_angle=0, end_angle=90, z=39.0)
        assert r_arc["ok"] is True

        r_spline = nx_bridge.draw_spline(points=[[0, 0], [5, 5], [10, 5], [15, 0]], degree=3, z=39.0)
        assert r_spline["ok"] is True, f"draw_spline error: {r_spline.get('error')}"


def test_create_real_sketch_mock():
    """Verify create_real_sketch commits sketch without type mismatch error."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    mock_wp = MagicMock()
    mock_builder = MagicMock()
    mock_sketch = MagicMock()
    mock_sketch.GetFeatureName.return_value = "SKETCH_001"
    mock_builder.Commit.return_value = mock_sketch
    mock_wp.Sketches.CreateNewSketchInPlaceBuilder.return_value = mock_builder
    mock_wp.Planes.CreatePlane.return_value = MagicMock()

    with patch.object(nx_bridge, "_ensure_work_part", return_value=mock_wp):
        r = nx_bridge.create_real_sketch(plane="XY", z_offset=39.0)
        assert r["ok"] is True, f"create_real_sketch error: {r.get('error')}"
        assert nx_bridge._state["sketch_origin"] == [0.0, 0.0, 39.0]


def test_sequential_sketches_z_offset_retention():
    """Verify sequential create_sketch calls update sketch_origin and draw_rounded_rectangle inherits active Z."""
    from nx_mcp.bridge import nx_bridge
    nx_bridge._state.clear()

    part = MagicMock()
    points_by_sketch = []

    def fake_create_line(p1, p2):
        points_by_sketch.append(p1)
        return MagicMock()

    def fake_create_arc(center, xdir, ydir, radius, start_rad, end_rad):
        points_by_sketch.append(center)
        return MagicMock()

    part.Curves.CreateLine.side_effect = fake_create_line
    part.Curves.CreateArc.side_effect = fake_create_arc

    with patch.object(nx_bridge, "_ensure_work_part", return_value=part):
        # Sketch 1 at Z=0.0
        nx_bridge.create_sketch(plane="XY", z_offset=0.0)
        points_by_sketch.clear()
        nx_bridge.draw_rounded_rectangle(arm_length=40.0, arm_width=16.0, end_radius=8.0)
        assert len(points_by_sketch) > 0
        assert all(pt.Z == 0.0 for pt in points_by_sketch)

        # Sketch 2 at Z=39.0
        nx_bridge.create_sketch(plane="XY", z_offset=39.0)
        points_by_sketch.clear()
        nx_bridge.draw_rounded_rectangle(arm_length=40.0, arm_width=16.0, end_radius=8.0)
        assert len(points_by_sketch) > 0
        assert all(pt.Z == 39.0 for pt in points_by_sketch)

        # Sketch 3 at Z=55.0
        nx_bridge.create_sketch(plane="XY", z_offset=55.0)
        points_by_sketch.clear()
        nx_bridge.draw_rounded_rectangle(arm_length=30.0, arm_width=10.0, end_radius=5.0)
        assert len(points_by_sketch) > 0
        assert all(pt.Z == 55.0 for pt in points_by_sketch)


def test_draw_rounded_rectangle_tool_wrapper_omits_z_by_default():
    """Verify MCP tool wrapper does not inject z=0.0 when z is omitted."""
    from nx_mcp.tools import sketch

    with patch.object(sketch, "_use_mock_nxopen", return_value=False), \
         patch("nx_mcp.bridge.runner.call_nx") as mock_call:
        mock_call.return_value = {"ok": True, "message": "OK"}
        sketch.draw_rounded_rectangle(arm_length=40.0, arm_width=16.0, end_radius=8.0)
        mock_call.assert_called_once()
        cmd, payload = mock_call.call_args[0]
        assert cmd == "draw_rounded_rectangle"
        assert "z" not in payload, f"Expected 'z' not in payload, got: {payload}"

