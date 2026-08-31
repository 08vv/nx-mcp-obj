"""Pure deterministic geometry math functions for CAD Spec computation.

These functions are callable from spec parameter values via the "$fn:<name>(...)" syntax.
All functions are pure (no side effects, no NX dependency) and fully unit-tested.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

# ── Registry of callable geometry functions ──
# Maps function name -> callable. Used by the validator and executor.
GEOMETRY_FUNCTIONS: Dict[str, callable] = {}


def _register(fn):
    """Decorator to register a geometry math function."""
    GEOMETRY_FUNCTIONS[fn.__name__] = fn
    return fn


@_register
def polar_to_cartesian(
    radius: float,
    angle_deg: float,
    center_x: float = 0.0,
    center_y: float = 0.0,
) -> List[float]:
    """Convert polar coordinates to cartesian [x, y].

    :param radius: Radial distance from center.
    :param angle_deg: Angle in degrees (0 = +X axis, CCW positive).
    :param center_x: X coordinate of the center point.
    :param center_y: Y coordinate of the center point.
    """
    angle_rad = math.radians(angle_deg)
    x = center_x + radius * math.cos(angle_rad)
    y = center_y + radius * math.sin(angle_rad)
    return [round(x, 10), round(y, 10)]


@_register
def cartesian_to_polar(
    x: float,
    y: float,
    center_x: float = 0.0,
    center_y: float = 0.0,
) -> Dict[str, float]:
    """Convert cartesian coordinates to polar {radius, angle_deg}.

    :param x: X coordinate.
    :param y: Y coordinate.
    :param center_x: X coordinate of the center point.
    :param center_y: Y coordinate of the center point.
    """
    dx = x - center_x
    dy = y - center_y
    radius = math.sqrt(dx * dx + dy * dy)
    angle_deg = math.degrees(math.atan2(dy, dx))
    return {"radius": round(radius, 10), "angle_deg": round(angle_deg, 10)}


@_register
def bolt_circle(
    count: int,
    pcd: float,
    start_angle_deg: float = 0.0,
    center_x: float = 0.0,
    center_y: float = 0.0,
) -> List[List[float]]:
    """Generate evenly spaced bolt hole coordinates on a pitch circle diameter.

    Returns a list of [x, y] coordinate pairs suitable for direct use as
    create_profile points or as individual add_hole x/y parameters.

    :param count: Number of bolt holes.
    :param pcd: Pitch circle diameter.
    :param start_angle_deg: Starting angle in degrees (0 = +X axis, CCW positive).
    :param center_x: X coordinate of the circle center.
    :param center_y: Y coordinate of the circle center.
    """
    if count < 1:
        raise ValueError("bolt_circle count must be >= 1")
    radius = pcd / 2.0
    step_deg = 360.0 / count
    points = []
    for i in range(count):
        angle_deg = start_angle_deg + i * step_deg
        pt = polar_to_cartesian(radius, angle_deg, center_x, center_y)
        points.append(pt)
    return points


@_register
def linear_spacing(
    count: int,
    pitch: float,
    start_x: float = 0.0,
    start_y: float = 0.0,
    direction_deg: float = 0.0,
) -> List[List[float]]:
    """Generate linearly spaced point coordinates along a direction.

    Returns a list of [x, y] coordinate pairs.

    :param count: Number of points.
    :param pitch: Distance between consecutive points.
    :param start_x: X coordinate of the first point.
    :param start_y: Y coordinate of the first point.
    :param direction_deg: Direction angle in degrees (0 = +X axis, CCW positive).
    """
    if count < 1:
        raise ValueError("linear_spacing count must be >= 1")
    angle_rad = math.radians(direction_deg)
    dx = pitch * math.cos(angle_rad)
    dy = pitch * math.sin(angle_rad)
    points = []
    for i in range(count):
        x = start_x + i * dx
        y = start_y + i * dy
        points.append([round(x, 10), round(y, 10)])
    return points


@_register
def offset_point_along_vector(
    x: float,
    y: float,
    distance: float,
    direction_deg: float,
) -> List[float]:
    """Offset a point by a distance along a direction vector.

    Returns [x, y] of the offset point.

    :param x: X coordinate of the starting point.
    :param y: Y coordinate of the starting point.
    :param distance: Offset distance.
    :param direction_deg: Direction angle in degrees (0 = +X axis, CCW positive).
    """
    angle_rad = math.radians(direction_deg)
    new_x = x + distance * math.cos(angle_rad)
    new_y = y + distance * math.sin(angle_rad)
    return [round(new_x, 10), round(new_y, 10)]


@_register
def lerp(a: float, b: float, t: float) -> float:
    """Linearly interpolate between a and b at parameter t.

    :param a: Start value (at t=0).
    :param b: End value (at t=1).
    :param t: Interpolation factor (0.0 to 1.0, but extrapolates linearly beyond).
    """
    val = float(a) + float(t) * (float(b) - float(a))
    return round(val, 10)


@_register
def deg_to_rad(degrees: float) -> float:
    """Convert angle in degrees to radians.

    :param degrees: Angle in degrees.
    """
    return round(math.radians(float(degrees)), 10)


@_register
def rad_to_deg(radians: float) -> float:
    """Convert angle in radians to degrees.

    :param radians: Angle in radians.
    """
    return round(math.degrees(float(radians)), 10)

