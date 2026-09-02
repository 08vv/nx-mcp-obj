import os
from typing import Literal

from ..bridge import runner
from ..tools.registry import mcp_tool
from ..nx_session import NXSession
from ..response import ToolResult, ToolError


def _use_mock_nxopen():
    return os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1"


def _bridge_result(result):
    if result.get("ok"):
        return ToolResult(result.get("message", "OK"))
    return ToolError(result.get("error", "NX bridge command failed"))


@mcp_tool(
    "create_sketch",
    "Create a new 2D sketch plane (XY, XZ, or YZ) with optional z_offset, origin offsets, and rotation. "
    "All subsequent 2D drawing calls will be positioned on this sketch plane."
)
def create_sketch(
    plane: str = "XY",
    z_offset: float = 0.0,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    rotate_z_deg: float = 0.0,
):
    try:
        z_offset = float(z_offset)
        origin_x = float(origin_x)
        origin_y = float(origin_y)
        rotate_z_deg = float(rotate_z_deg)
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_sketch",
                    {
                        "plane": plane,
                        "z_offset": z_offset,
                        "origin_x": origin_x,
                        "origin_y": origin_y,
                        "rotate_z_deg": rotate_z_deg,
                    },
                )
            )
        return ToolResult(f"Sketch created on {plane} plane (z_offset={z_offset})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("draw_line", "Draw a line from x1 y1 to x2 y2 with optional z coordinate override. Curves accumulate in the active sketch profile.")
def draw_line(x1: float, y1: float, x2: float, y2: float, z: float = None):
    try:
        payload = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        if z is not None:
            payload["z"] = float(z)
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("draw_line", payload))
        nxopen = NXSession.nxopen()
        part = NXSession.work_part()
        z_val = float(z) if z is not None else 0.0
        part.Curves.CreateLine(nxopen.Point3d(x1, y1, z_val), nxopen.Point3d(x2, y2, z_val))
        return ToolResult(f"Line {x1},{y1} to {x2},{y2}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("draw_rectangle", "Draw rectangle from corner x y with width and height and optional z coordinate override. Curves accumulate in the active sketch profile.")
def draw_rectangle(x: float, y: float, width: float, height: float, z: float = None):
    try:
        payload = {"x": x, "y": y, "width": width, "height": height}
        if z is not None:
            payload["z"] = float(z)
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("draw_rectangle", payload))
        nxopen = NXSession.nxopen()
        part = NXSession.work_part()
        z_val = float(z) if z is not None else 0.0
        corners = [(x,y),(x+width,y),(x+width,y+height),(x,y+height),(x,y)]
        for i in range(4):
            part.Curves.CreateLine(
                nxopen.Point3d(corners[i][0], corners[i][1], z_val),
                nxopen.Point3d(corners[i+1][0], corners[i+1][1], z_val)
            )
        return ToolResult(f"Rectangle {x},{y} size {width}x{height}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("draw_circle", "Draw circle at cx cy with radius and optional z coordinate override. Curves accumulate in the active sketch profile.")
def draw_circle(cx: float, cy: float, radius: float, z: float = None):
    try:
        payload = {"cx": cx, "cy": cy, "radius": radius}
        if z is not None:
            payload["z"] = float(z)
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("draw_circle", payload))
        nxopen = NXSession.nxopen()
        part = NXSession.work_part()
        z_val = float(z) if z is not None else 0.0
        part.Curves.CreateArc(nxopen.Point3d(cx, cy, z_val), nxopen.Vector3d(0, 0, 1), radius, 0.0, 6.28318)
        return ToolResult(f"Circle {cx},{cy} R={radius}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("draw_arc", "Draw arc at cx cy with radius from start_angle to end_angle degrees with optional z coordinate override. Curves accumulate in the active sketch profile.")
def draw_arc(cx: float, cy: float, radius: float, start_angle: float, end_angle: float, z: float = None):
    try:
        payload = {
            "cx": cx,
            "cy": cy,
            "radius": radius,
            "start_angle": start_angle,
            "end_angle": end_angle,
        }
        if z is not None:
            payload["z"] = float(z)
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("draw_arc", payload))
        import math
        nxopen = NXSession.nxopen()
        part = NXSession.work_part()
        z_val = float(z) if z is not None else 0.0
        part.Curves.CreateArc(
            nxopen.Point3d(cx, cy, z_val), nxopen.Vector3d(0, 0, 1),
            radius, math.radians(start_angle), math.radians(end_angle)
        )
        return ToolResult(f"Arc {cx},{cy} r={radius} {start_angle} to {end_angle} deg")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "draw_rounded_rectangle",
    "Draw a closed rounded-rectangle (stadium/oblong) profile with 2 semicircular arc ends and 2 straight lines. "
    "arm_length = total tip-to-tip length, arm_width = total width, end_radius = arc radius at each end. "
    "cx_left = X of left arc center (default 0), cy = Y center (default 0), z = Z plane (default 0). "
    "Curves accumulate in the active sketch profile."
)
def draw_rounded_rectangle(
    arm_length: float,
    arm_width: float,
    end_radius: float,
    cx_left: float = 0.0,
    cy: float = 0.0,
    z: float = 0.0,
):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "draw_rounded_rectangle",
                    {
                        "arm_length": arm_length,
                        "arm_width": arm_width,
                        "end_radius": end_radius,
                        "cx_left": cx_left,
                        "cy": cy,
                        "z": z,
                    },
                )
            )
        return ToolResult(
            f"Rounded rectangle: L={arm_length} W={arm_width} R={end_radius} "
            f"center_left=({cx_left},{cy}) z={z}"
        )
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "create_offset_linkage_arm",
    "Create a fully parametric offset linkage arm consisting of two identical rounded-end arms connected by "
    "a vertical cylindrical spacer. The upper arm is rotated 180° relative to the lower arm. "
    "All dimensions are NX Expressions: ARM_LENGTH=90, ARM_WIDTH=24, ARM_THICK=8, END_RADIUS=12, "
    "HOLE_DIA=10, HOLE_OFFSET=12, CYLINDER_DIA=22, CYLINDER_HEIGHT=55, BLEND_RADIUS=2, CHAMFER_OFFSET=0.5. "
    "output_path: full path to the .prt file (optional if a part is already open)."
)
def create_offset_linkage_arm(output_path: str = ""):
    try:
        if not _use_mock_nxopen():
            args = {}
            if output_path:
                args["output_path"] = output_path
            return _bridge_result(runner.call_nx("create_offset_linkage_arm", args))
        return ToolResult(f"Offset linkage arm created (mock mode)")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("create_offset_plane", "Create an offset datum plane from XY, XZ, or YZ plane")
def create_offset_plane(base_plane: str = "XY", offset: float = 10.0):
    offset = float(offset)
    if offset == 0.0:
        return ToolError("Offset distance must be non-zero to create an offset plane")
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("create_offset_plane", {"base_plane": base_plane, "offset": offset}))
        return ToolResult(f"Offset plane created from {base_plane} with offset {offset}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("add_constraint_horizontal", "Add a horizontal constraint to a sketch curve by index (0-based)")
def add_constraint_horizontal(curve_index: int = 0):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("add_constraint_horizontal", {"curve_index": curve_index}))
        return ToolResult(f"Added horizontal constraint to curve {curve_index}")
    except Exception as e: return ToolError(str(e))


@mcp_tool("add_constraint_vertical", "Add a vertical constraint to a sketch curve by index (0-based)")
def add_constraint_vertical(curve_index: int = 0):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("add_constraint_vertical", {"curve_index": curve_index}))
        return ToolResult(f"Added vertical constraint to curve {curve_index}")
    except Exception as e: return ToolError(str(e))


@mcp_tool("add_constraint_fixed", "Add a fixed/anchor constraint to a sketch curve by index (0-based)")
def add_constraint_fixed(curve_index: int = 0):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("add_constraint_fixed", {"curve_index": curve_index}))
        return ToolResult(f"Added fixed constraint to curve {curve_index}")
    except Exception as e: return ToolError(str(e))


@mcp_tool(
    "draw_spline",
    "Draw a spline curve passing through 2D or 3D interpolation points with optional z coordinate override. Points can be [[x,y],...] or [{'x':..,'y':..},...].",
)
def draw_spline(points: list, degree: int = 3, closed: bool = False, plane: str = "active", z: float = None):
    try:
        if not points or len(points) < 2:
            return ToolError("Spline requires at least 2 points")
        payload = {"points": points, "degree": degree, "closed": closed, "plane": plane}
        if z is not None:
            payload["z"] = float(z)
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("draw_spline", payload)
            )
        return ToolResult(f"Spline with {len(points)} points created (mock mode)")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "offset_curve",
    "Offset a spline curve with variable offset width from start_width to end_width.",
)
def offset_curve(start_width: float, end_width: float, curve_reference: str = "last"):
    try:
        start_width = float(start_width)
        end_width = float(end_width)
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "offset_curve",
                    {
                        "start_width": start_width,
                        "end_width": end_width,
                        "curve_reference": curve_reference,
                    },
                )
            )
        return ToolResult(f"Offset curve created (width {start_width}->{end_width})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "close_curve_region",
    "Bridge or connect end points of two curves to create a closed profile.",
)
def close_curve_region(
    curve2: str,
    curve1: str = "last",
    method: Literal["tangent_lines", "straight_lines"] = "tangent_lines",
):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "close_curve_region",
                    {"curve2": curve2, "curve1": curve1, "method": method},
                )
            )
        return ToolResult(f"Closed curve region using {method}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "create_profile",
    "Create an explicit 2D/3D profile from an ordered list of points with persistent profile_id.",
)
def create_profile(
    points: list,
    plane: Literal["XY", "XZ", "YZ"] = "XY",
    closed: bool = True,
):
    """Creates a 2D or 3D wireframe profile from an ordered list of points.

    Args:
        points (list): Ordered list of [x, y] or [x, y, z] coordinate points.
        plane (str): Sketch plane orientation ('XY', 'XZ', or 'YZ').
        closed (bool): If True, connects the last point back to the first.

    Returns:
        ToolResult or ToolError: Result containing the registered profile_id and curve_ids.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_profile",
                    {"points": points, "plane": plane, "closed": closed},
                )
            )
        return ToolResult(f"Created profile with {len(points)} points on {plane}")
    except Exception as e:
        return ToolError(str(e))


