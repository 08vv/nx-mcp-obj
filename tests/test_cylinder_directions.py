"""Unit tests for Bug 6 fix: create_cylinder bounding box contracts for X, Y, and Z directions."""

import sys
from unittest.mock import MagicMock, patch
import pytest

# Ensure NXOpen and NXOpen.UF are mocked before importing nx_bridge
mock_nxopen = MagicMock()
mock_uf_session = MagicMock()
mock_nxopen.UF.UFSession.GetUFSession.return_value = mock_uf_session
mock_nxopen.Session.GetSession.return_value = MagicMock()
if "NXOpen" not in sys.modules:
    sys.modules["NXOpen"] = mock_nxopen
if "NXOpen.UF" not in sys.modules:
    sys.modules["NXOpen.UF"] = mock_nxopen.UF

from nx_mcp.bridge import nx_bridge
from nx_mcp.response import ToolResult
from nx_mcp.tools import modeling


class TestUFModlProxy:
    """Verify _UFModlProxy correctly delegates across NXOpen.UF submodules."""

    def test_proxy_delegates_to_modlgeneral(self):
        mock_uf = MagicMock()
        mock_uf.ModlGeneral.AskBoundingBox.return_value = [-10.0, -10.0, 0.0, 10.0, 10.0, 30.0]
        mock_uf.Modl = MagicMock(spec=[])

        proxy = nx_bridge._UFModlProxy(mock_uf)
        assert hasattr(proxy, "AskBoundingBox")
        res = proxy.AskBoundingBox(12345)
        assert res == [-10.0, -10.0, 0.0, 10.0, 10.0, 30.0]
        mock_uf.ModlGeneral.AskBoundingBox.assert_called_once_with(12345)

    def test_proxy_delegates_to_modeling(self):
        mock_uf = MagicMock()
        mock_uf.ModlGeneral = MagicMock(spec=[])
        mock_uf.Modeling.AskFaceData.return_value = (22, (15.0, 0.0, 0.0), (1.0, 0.0, 0.0), [15.0, -10.0, -10.0, 15.0, 10.0, 10.0])
        mock_uf.Modl = MagicMock(spec=[])

        proxy = nx_bridge._UFModlProxy(mock_uf)
        assert hasattr(proxy, "AskFaceData")
        res = proxy.AskFaceData(54321)
        assert res[0] == 22
        mock_uf.Modeling.AskFaceData.assert_called_once_with(54321)

    def test_proxy_raises_attribute_error_for_unknown(self):
        mock_uf = MagicMock()
        mock_uf.ModlGeneral = MagicMock(spec=[])
        mock_uf.Modeling = MagicMock(spec=[])
        mock_uf.ModlFeatures = MagicMock(spec=[])
        mock_uf.Modl = MagicMock(spec=[])

        proxy = nx_bridge._UFModlProxy(mock_uf)
        assert not hasattr(proxy, "NonExistentMethod")
        with pytest.raises(AttributeError, match="has no attribute 'NonExistentMethod'"):
            proxy.NonExistentMethod()


class TestParseBboxResult:
    """Verify _parse_bbox_result correctly parses bounding box returns."""

    def test_shape_1_six_elements(self):
        raw = [15.0, -10.0, -10.0, 30.0, 10.0, 10.0]
        parsed = nx_bridge._parse_bbox_result(raw)
        assert parsed == ((15.0, -10.0, -10.0), (30.0, 10.0, 10.0))

    def test_shape_2_two_tuples(self):
        raw = [(15.0, -10.0, -10.0), (30.0, 10.0, 10.0)]
        parsed = nx_bridge._parse_bbox_result(raw)
        assert parsed == ((15.0, -10.0, -10.0), (30.0, 10.0, 10.0))

    def test_shape_3_uf_modl_distances(self):
        # Shape 3: (min_corner, directions_matrix, distances)
        # Verify Y coordinate uses p_min[1] rather than p_min[0]
        min_corner = (15.0, 20.0, 30.0)
        matrix = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        distances = (10.0, 15.0, 20.0)
        raw = (min_corner, matrix, distances)
        parsed = nx_bridge._parse_bbox_result(raw)
        assert parsed == ((15.0, 20.0, 30.0), (25.0, 35.0, 50.0))


class TestBodyBoundsGeometryContracts:
    """Verify _body_bounds yields correct geometry contracts for X, Y, and Z cylinders."""

    def test_cylinder_direction_z_bounding_box(self):
        """Z-direction cylinder at (0, 0, 0) with r=10, h=30 -> X=[-10,10], Y=[-10,10], Z=[0,30]."""
        mock_body = MagicMock()
        mock_body.Tag = 1001

        mock_uf = MagicMock()
        mock_uf.ModlGeneral.AskBoundingBox.return_value = [-10.0, -10.0, 0.0, 10.0, 10.0, 30.0]
        mock_uf.Modl = MagicMock(spec=[])

        with patch.object(nx_bridge, "_get_uf", return_value=mock_uf):
            min_pt, max_pt = nx_bridge._body_bounds(mock_body)
            assert min_pt == (-10.0, -10.0, 0.0)
            assert max_pt == (10.0, 10.0, 30.0)

    def test_cylinder_direction_x_bounding_box(self):
        """X-direction cylinder at (15, 0, 0) with r=10, h=15 -> X=[15,30], Y=[-10,10], Z=[-10,10]."""
        mock_body = MagicMock()
        mock_body.Tag = 1002

        mock_uf = MagicMock()
        mock_uf.ModlGeneral.AskBoundingBox.return_value = [15.0, -10.0, -10.0, 30.0, 10.0, 10.0]
        mock_uf.Modl = MagicMock(spec=[])

        with patch.object(nx_bridge, "_get_uf", return_value=mock_uf):
            min_pt, max_pt = nx_bridge._body_bounds(mock_body)
            assert min_pt == (15.0, -10.0, -10.0)
            assert max_pt == (30.0, 10.0, 10.0)

    def test_cylinder_direction_y_bounding_box(self):
        """Y-direction cylinder at (0, 15, 0) with r=10, h=15 -> X=[-10,10], Y=[15,30], Z=[-10,10]."""
        mock_body = MagicMock()
        mock_body.Tag = 1003

        mock_uf = MagicMock()
        mock_uf.ModlGeneral.AskBoundingBox.return_value = [-10.0, 15.0, -10.0, 10.0, 30.0, 10.0]
        mock_uf.Modl = MagicMock(spec=[])

        with patch.object(nx_bridge, "_get_uf", return_value=mock_uf):
            min_pt, max_pt = nx_bridge._body_bounds(mock_body)
            assert min_pt == (-10.0, 15.0, -10.0)
            assert max_pt == (10.0, 30.0, 10.0)

    def test_cylinder_nonzero_origin_x_direction(self):
        """X-direction cylinder at (10, 20, 30) with r=5, h=25 -> X=[10,35], Y=[15,25], Z=[25,35]."""
        mock_body = MagicMock()
        mock_body.Tag = 1004

        mock_uf = MagicMock()
        mock_uf.ModlGeneral.AskBoundingBox.return_value = [10.0, 15.0, 25.0, 35.0, 25.0, 35.0]
        mock_uf.Modl = MagicMock(spec=[])

        with patch.object(nx_bridge, "_get_uf", return_value=mock_uf):
            min_pt, max_pt = nx_bridge._body_bounds(mock_body)
            assert min_pt == (10.0, 15.0, 25.0)
            assert max_pt == (35.0, 25.0, 35.0)

    def test_edge_fallback_uses_true_3d_center_and_radius(self):
        """When UF AskBoundingBox is unavailable, edge fallback bounds circle around its true center."""
        mock_body = MagicMock()
        mock_body.Tag = 1005
        mock_edge = MagicMock()
        mock_edge.Tag = 2001
        mock_edge.GetVertices.return_value = []
        mock_body.GetEdges.return_value = [mock_edge]
        mock_body.GetFaces.return_value = []

        mock_uf = MagicMock()
        # ModlGeneral has no AskBoundingBox to trigger edge fallback
        mock_uf.ModlGeneral = MagicMock(spec=[])
        mock_uf.Modeling = MagicMock(spec=[])
        mock_uf.Modl = MagicMock(spec=[])

        # Mock Eval.AskArc to return circle centered at (15, 0, 0) with radius 10 in YZ plane
        mock_arc = MagicMock()
        mock_arc.Center = (15.0, 0.0, 0.0)
        mock_arc.Radius = 10.0
        mock_uf.Eval.Initialize.return_value = 999
        mock_uf.Eval.IsArc.return_value = True
        mock_uf.Eval.AskArc.return_value = mock_arc

        with patch.object(nx_bridge, "_get_uf", return_value=mock_uf):
            min_pt, max_pt = nx_bridge._body_bounds(mock_body)
            assert min_pt == (5.0, -10.0, -10.0)
            assert max_pt == (25.0, 10.0, 10.0)


class TestModelingToolDirections:
    """Verify modeling.create_cylinder accepts and passes X, Y, Z directions."""

    @pytest.mark.parametrize("dir_arg", ["X", "Y", "Z", "+X", "-X", "+Y", "-Y", "+Z", "-Z"])
    def test_create_cylinder_accepts_directions_mock(self, dir_arg):
        with patch("nx_mcp.tools.modeling._use_mock_nxopen", return_value=True):
            res = modeling.create_cylinder(radius=10.0, height=25.0, x=15.0, y=0.0, z=0.0, direction=dir_arg)
            assert isinstance(res, ToolResult)
            assert "Cylinder R10.0 height 25.0 at (15.0,0.0,0.0)" in res.message
