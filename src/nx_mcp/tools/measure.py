import math
import os

from ..bridge import runner
from ..nx_session import NXSession
from ..response import ToolError, ToolResult
from ..tools.registry import mcp_tool
from nx_mcp.tools._common import _bridge_result, _use_mock_nxopen




@mcp_tool("measure_distance", "Straight-line distance between two 3D points")
def measure_distance(x1: float, y1: float, z1: float, x2: float, y2: float, z2: float):
    """
    Calculates the straight-line distance between two 3D points.

    Args:
        x1 (float): The X coordinate of the first point.
        y1 (float): The Y coordinate of the first point.
        z1 (float): The Z coordinate of the first point.
        x2 (float): The X coordinate of the second point.
        y2 (float): The Y coordinate of the second point.
        z2 (float): The Z coordinate of the second point.

    Returns:
        ToolResult: The calculated distance in millimeters.
    """
    x1 = float(x1)
    y1 = float(y1)
    x2 = float(x2)
    y2 = float(y2)
    try:
        d = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)
        return ToolResult(f"Distance: {d:.4f} mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("measure_angle", "Angle in degrees between two vectors")
def measure_angle(x1: float, y1: float, z1: float, x2: float, y2: float, z2: float):
    """
    Calculates the angle in degrees between two 3D vectors.

    Args:
        x1 (float): The X component of the first vector.
        y1 (float): The Y component of the first vector.
        z1 (float): The Z component of the first vector.
        x2 (float): The X component of the second vector.
        y2 (float): The Y component of the second vector.
        z2 (float): The Z component of the second vector.

    Returns:
        ToolResult: The calculated angle in degrees.
    """
    x1 = float(x1)
    y1 = float(y1)
    x2 = float(x2)
    y2 = float(y2)
    try:
        mag1 = math.sqrt(x1**2 + y1**2 + z1**2)
        mag2 = math.sqrt(x2**2 + y2**2 + z2**2)
        if mag1 == 0 or mag2 == 0:
            return ToolError("Zero-length vector")
        dot = x1 * x2 + y1 * y2 + z1 * z2
        angle = math.degrees(math.acos(max(-1.0, min(1.0, dot / (mag1 * mag2)))))
        return ToolResult(f"Angle: {angle:.4f}°")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("measure_volume", "Volume of a box (width × height × depth) in mm")
def measure_volume(width: float, height: float, depth: float):
    """
    Calculates the volume of a basic bounding box given its dimensions.

    Args:
        width (float): The width of the box in millimeters.
        height (float): The height of the box in millimeters.
        depth (float): The depth of the box in millimeters.

    Returns:
        ToolResult: The calculated volume in cubic millimeters and cubic centimeters.
    """
    width = float(width)
    height = float(height)
    depth = float(depth)
    try:
        v = width * height * depth
        return ToolResult(f"Volume: {v:.4f} mm³  ({v / 1000:.4f} cm³)")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("get_bounding_box", "Get bounding box of a target body (default 'last')")
def get_bounding_box(body_reference: str = "last"):
    """
    Retrieves the bounding box coordinates and dimensions for a specified body.

    Args:
        body_reference (str): The identifier of the body to measure.

    Returns:
        ToolResult: The bounding box data for the specified body.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("get_bounding_box", {"body_reference": body_reference})
            )
        part = NXSession.work_part()
        return ToolResult(f"Bounding box computed for: {part}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("measure_body_volume", "Measure the volume of a target body in the model")
def measure_body_volume(body_reference: str = "last"):
    """
    Measures the exact volume of a specific solid or sheet body in the model.

    Args:
        body_reference (str): The identifier of the body to measure.

    Returns:
        ToolResult: The measured volume of the body in cubic millimeters.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "measure_body_volume", {"body_reference": body_reference}
                )
            )
        return ToolResult("Volume: 1000.0000 mm³ (mock mode)")
    except Exception as e:
        return ToolError(str(e))
