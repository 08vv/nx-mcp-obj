"""Unit tests for geometry_math.py — pure functions, no NX, no mocking."""

import math
import pytest
from nx_mcp.spec.geometry_math import (
    polar_to_cartesian,
    cartesian_to_polar,
    bolt_circle,
    linear_spacing,
    offset_point_along_vector,
    lerp,
    deg_to_rad,
    rad_to_deg,
    GEOMETRY_FUNCTIONS,
)


class TestPolarToCartesian:
    def test_zero_angle(self):
        result = polar_to_cartesian(10.0, 0.0)
        assert result == [10.0, 0.0]

    def test_90_degrees(self):
        result = polar_to_cartesian(10.0, 90.0)
        assert abs(result[0]) < 1e-9
        assert abs(result[1] - 10.0) < 1e-9

    def test_180_degrees(self):
        result = polar_to_cartesian(5.0, 180.0)
        assert abs(result[0] - (-5.0)) < 1e-9
        assert abs(result[1]) < 1e-9

    def test_with_center(self):
        result = polar_to_cartesian(10.0, 0.0, center_x=5.0, center_y=3.0)
        assert abs(result[0] - 15.0) < 1e-9
        assert abs(result[1] - 3.0) < 1e-9

    def test_45_degrees(self):
        result = polar_to_cartesian(math.sqrt(2), 45.0)
        assert abs(result[0] - 1.0) < 1e-9
        assert abs(result[1] - 1.0) < 1e-9


class TestCartesianToPolar:
    def test_on_x_axis(self):
        result = cartesian_to_polar(10.0, 0.0)
        assert abs(result["radius"] - 10.0) < 1e-9
        assert abs(result["angle_deg"]) < 1e-9

    def test_on_y_axis(self):
        result = cartesian_to_polar(0.0, 5.0)
        assert abs(result["radius"] - 5.0) < 1e-9
        assert abs(result["angle_deg"] - 90.0) < 1e-9

    def test_with_center(self):
        result = cartesian_to_polar(10.0, 5.0, center_x=10.0, center_y=0.0)
        assert abs(result["radius"] - 5.0) < 1e-9
        assert abs(result["angle_deg"] - 90.0) < 1e-9

    def test_roundtrip(self):
        """polar -> cartesian -> polar roundtrip."""
        pt = polar_to_cartesian(25.0, 37.5, center_x=10.0, center_y=20.0)
        back = cartesian_to_polar(pt[0], pt[1], center_x=10.0, center_y=20.0)
        assert abs(back["radius"] - 25.0) < 1e-6
        assert abs(back["angle_deg"] - 37.5) < 1e-6


class TestBoltCircle:
    def test_4_holes(self):
        pts = bolt_circle(4, 100.0)
        assert len(pts) == 4
        # First hole at 0 degrees = (50, 0)
        assert abs(pts[0][0] - 50.0) < 1e-9
        assert abs(pts[0][1]) < 1e-9
        # Second hole at 90 degrees = (0, 50)
        assert abs(pts[1][0]) < 1e-9
        assert abs(pts[1][1] - 50.0) < 1e-9

    def test_6_holes_with_offset(self):
        pts = bolt_circle(6, 50.0, start_angle_deg=30.0)
        assert len(pts) == 6
        # Each point should be on a circle of radius 25
        for pt in pts:
            r = math.sqrt(pt[0] ** 2 + pt[1] ** 2)
            assert abs(r - 25.0) < 1e-6

    def test_with_center(self):
        pts = bolt_circle(3, 20.0, center_x=100.0, center_y=50.0)
        assert len(pts) == 3
        for pt in pts:
            r = math.sqrt((pt[0] - 100.0) ** 2 + (pt[1] - 50.0) ** 2)
            assert abs(r - 10.0) < 1e-6

    def test_single_hole(self):
        pts = bolt_circle(1, 40.0)
        assert len(pts) == 1
        assert abs(pts[0][0] - 20.0) < 1e-9
        assert abs(pts[0][1]) < 1e-9

    def test_zero_count_raises(self):
        with pytest.raises(ValueError, match="count must be >= 1"):
            bolt_circle(0, 50.0)

    def test_output_is_list_of_lists(self):
        """Confirm output format matches create_profile's expected points param."""
        pts = bolt_circle(4, 100.0)
        assert isinstance(pts, list)
        for pt in pts:
            assert isinstance(pt, list)
            assert len(pt) == 2
            assert all(isinstance(v, float) for v in pt)


class TestLinearSpacing:
    def test_horizontal(self):
        pts = linear_spacing(4, 10.0)
        assert len(pts) == 4
        assert pts[0] == [0.0, 0.0]
        assert abs(pts[1][0] - 10.0) < 1e-9
        assert abs(pts[2][0] - 20.0) < 1e-9
        assert abs(pts[3][0] - 30.0) < 1e-9

    def test_vertical(self):
        pts = linear_spacing(3, 15.0, direction_deg=90.0)
        assert len(pts) == 3
        assert abs(pts[0][0]) < 1e-9
        assert abs(pts[1][1] - 15.0) < 1e-9
        assert abs(pts[2][1] - 30.0) < 1e-9

    def test_with_start_offset(self):
        pts = linear_spacing(2, 20.0, start_x=5.0, start_y=10.0, direction_deg=45.0)
        assert len(pts) == 2
        assert pts[0] == [5.0, 10.0]
        dx = 20.0 * math.cos(math.radians(45.0))
        assert abs(pts[1][0] - (5.0 + dx)) < 1e-6

    def test_zero_count_raises(self):
        with pytest.raises(ValueError, match="count must be >= 1"):
            linear_spacing(0, 10.0)


class TestOffsetPointAlongVector:
    def test_along_x(self):
        result = offset_point_along_vector(0.0, 0.0, 10.0, 0.0)
        assert abs(result[0] - 10.0) < 1e-9
        assert abs(result[1]) < 1e-9

    def test_along_y(self):
        result = offset_point_along_vector(5.0, 5.0, 20.0, 90.0)
        assert abs(result[0] - 5.0) < 1e-9
        assert abs(result[1] - 25.0) < 1e-9

    def test_negative_distance(self):
        result = offset_point_along_vector(10.0, 0.0, -5.0, 0.0)
        assert abs(result[0] - 5.0) < 1e-9

    def test_diagonal(self):
        result = offset_point_along_vector(0.0, 0.0, math.sqrt(2), 45.0)
        assert abs(result[0] - 1.0) < 1e-9
        assert abs(result[1] - 1.0) < 1e-9


class TestLerp:
    def test_midpoint(self):
        assert abs(lerp(10.0, 20.0, 0.5) - 15.0) < 1e-9

    def test_start_and_end(self):
        assert abs(lerp(0.0, 100.0, 0.0) - 0.0) < 1e-9
        assert abs(lerp(0.0, 100.0, 1.0) - 100.0) < 1e-9

    def test_extrapolation(self):
        assert abs(lerp(0.0, 50.0, 2.0) - 100.0) < 1e-9


class TestAngleConversions:
    def test_deg_to_rad(self):
        assert abs(deg_to_rad(180.0) - math.pi) < 1e-9
        assert abs(deg_to_rad(90.0) - (math.pi / 2.0)) < 1e-9
        assert abs(deg_to_rad(0.0)) < 1e-9

    def test_rad_to_deg(self):
        assert abs(rad_to_deg(math.pi) - 180.0) < 1e-9
        assert abs(rad_to_deg(math.pi / 2.0) - 90.0) < 1e-9
        assert abs(rad_to_deg(0.0)) < 1e-9


class TestRegistry:
    def test_all_functions_registered(self):
        assert "polar_to_cartesian" in GEOMETRY_FUNCTIONS
        assert "cartesian_to_polar" in GEOMETRY_FUNCTIONS
        assert "bolt_circle" in GEOMETRY_FUNCTIONS
        assert "linear_spacing" in GEOMETRY_FUNCTIONS
        assert "offset_point_along_vector" in GEOMETRY_FUNCTIONS
        assert "lerp" in GEOMETRY_FUNCTIONS
        assert "deg_to_rad" in GEOMETRY_FUNCTIONS
        assert "rad_to_deg" in GEOMETRY_FUNCTIONS
        assert len(GEOMETRY_FUNCTIONS) == 8

