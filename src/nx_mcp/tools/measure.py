import math
import os
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


@mcp_tool("measure_distance", "Straight-line distance between two 3D points")
def measure_distance(x1: float, y1: float, z1: float, x2: float, y2: float, z2: float):
    try:
        d = math.sqrt((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2)
        return ToolResult(f"Distance: {d:.4f} mm")
    except Exception as e: return ToolError(str(e))

@mcp_tool("measure_angle", "Angle in degrees between two vectors")
def measure_angle(x1: float, y1: float, z1: float, x2: float, y2: float, z2: float):
    try:
        mag1 = math.sqrt(x1**2+y1**2+z1**2)
        mag2 = math.sqrt(x2**2+y2**2+z2**2)
        if mag1 == 0 or mag2 == 0: return ToolError("Zero-length vector")
        dot = x1*x2 + y1*y2 + z1*z2
        angle = math.degrees(math.acos(max(-1.0, min(1.0, dot/(mag1*mag2)))))
        return ToolResult(f"Angle: {angle:.4f}°")
    except Exception as e: return ToolError(str(e))

@mcp_tool("measure_volume", "Volume of a box (width × height × depth) in mm")
def measure_volume(width: float, height: float, depth: float):
    try:
        v = width * height * depth
        return ToolResult(f"Volume: {v:.4f} mm³  ({v/1000:.4f} cm³)")
    except Exception as e: return ToolError(str(e))

@mcp_tool("get_bounding_box", "Get bounding box of a target body (default 'last')")
def get_bounding_box(body_reference: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("get_bounding_box", {"body_reference": body_reference}))
        part = NXSession.work_part()
        return ToolResult(f"Bounding box computed for: {part}")
    except Exception as e: return ToolError(str(e))

@mcp_tool("measure_body_volume", "Measure the volume of a target body in the model")
def measure_body_volume(body_reference: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("measure_body_volume", {"body_reference": body_reference}))
        return ToolResult("Volume: 1000.0000 mm³ (mock mode)")
    except Exception as e: return ToolError(str(e))