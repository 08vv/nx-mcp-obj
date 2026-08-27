import os

from ..bridge import runner
from ..response import ToolError, ToolResult
from ..tools.registry import mcp_tool
from nx_mcp.tools._common import _bridge_result, _use_mock_nxopen




@mcp_tool("boolean_combine", "Perform combine operations (Unite, Subtract, Intersect)")
def boolean_combine(
    operation: str = "intersect", target: str = "last", tool: str = "last"
):
    """
    Performs a Boolean operation (Unite, Subtract, Intersect) between two bodies.

    Args:
        operation (str): The type of Boolean operation ('unite', 'subtract', 'intersect').
        target (str): The identifier of the target body.
        tool (str): The identifier of the tool body.

    Returns:
        ToolResult: A confirmation message of the completed Boolean operation.
    """
    try:
        if operation.lower() not in {"unite", "subtract", "intersect"}:
            return ToolError(f"Unsupported combine operation: {operation}")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "boolean_combine",
                    {"operation": operation, "target": target, "tool": tool},
                )
            )
        return ToolResult(f"Boolean {operation} completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("trim_sheet", "Trim a sheet body using a boundary curve or sheet")
def trim_sheet(target_body: str = "last", boundary_sketch: str = "last"):
    """
    Trims a target sheet body using a specified boundary sketch or sheet.

    Args:
        target_body (str): The identifier of the sheet body to be trimmed.
        boundary_sketch (str): The identifier of the boundary curve or sheet to trim with.

    Returns:
        ToolResult: A confirmation message of the trim operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "trim_sheet",
                    {"target_body": target_body, "boundary_sketch": boundary_sketch},
                )
            )
        return ToolResult("Trimmed sheet body")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("extend_sheet", "Extend a sheet boundary edge by a distance")
def extend_sheet(
    distance: float,
    boundary_edge_x: float = 0.0,
    boundary_edge_y: float = 0.0,
    boundary_edge_z: float = 0.0,
    body: str = "last",
):
    """
    Extends a sheet body's boundary edge by a specified distance.

    Args:
        distance (float): The extension distance in millimeters (must be positive).
        boundary_edge_x (float): The X coordinate to identify the boundary edge.
        boundary_edge_y (float): The Y coordinate to identify the boundary edge.
        boundary_edge_z (float): The Z coordinate to identify the boundary edge.
        body (str): The identifier of the sheet body to extend.

    Returns:
        ToolResult: A confirmation message indicating the extended distance.
    """
    distance = float(distance)
    boundary_edge_x = float(boundary_edge_x)
    boundary_edge_y = float(boundary_edge_y)
    boundary_edge_z = float(boundary_edge_z)
    try:
        if distance <= 0:
            return ToolError("Extend distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "extend_sheet",
                    {
                        "distance": distance,
                        "boundary_edge_x": boundary_edge_x,
                        "boundary_edge_y": boundary_edge_y,
                        "boundary_edge_z": boundary_edge_z,
                        "body": body,
                    },
                )
            )
        return ToolResult(f"Extended sheet edge by {distance}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("trim_and_extend", "Trim and extend two intersecting sheet bodies")
def trim_and_extend(target_body: str = "last", tool_body: str = "last"):
    """
    Simultaneously trims and extends two intersecting sheet bodies to form a corner.

    Args:
        target_body (str): The identifier of the first sheet body.
        tool_body (str): The identifier of the second sheet body.

    Returns:
        ToolResult: A confirmation message of the trim and extend operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "trim_and_extend",
                    {"target_body": target_body, "tool_body": tool_body},
                )
            )
        return ToolResult("Trim and extend operation completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("sew_sheets", "Sew multiple sheet bodies together along edges")
def sew_sheets(target_sheet: str = "last", tool_sheets: str = "last"):
    """
    Sews multiple sheet bodies together along coincident edges to form a single sheet or solid.

    Args:
        target_sheet (str): The primary sheet body to sew.
        tool_sheets (str): The secondary sheet bodies to attach.

    Returns:
        ToolResult: A confirmation message of the sew operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "sew_sheets",
                    {"target_sheet": target_sheet, "tool_sheets": tool_sheets},
                )
            )
        return ToolResult("Sheets sewn successfully")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("split_body", "Split a solid or sheet body using a plane or face")
def split_body(
    target_body: str = "last",
    tool_face_x: float = 0.0,
    tool_face_y: float = 0.0,
    tool_face_z: float = 0.0,
):
    """
    Splits a solid or sheet body into separate bodies using a tool face or plane.

    Args:
        target_body (str): The identifier of the body to split.
        tool_face_x (float): The X coordinate of the tool face or plane.
        tool_face_y (float): The Y coordinate of the tool face or plane.
        tool_face_z (float): The Z coordinate of the tool face or plane.

    Returns:
        ToolResult: A confirmation message of the split operation.
    """
    tool_face_x = float(tool_face_x)
    tool_face_y = float(tool_face_y)
    tool_face_z = float(tool_face_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "split_body",
                    {
                        "target_body": target_body,
                        "tool_face_x": tool_face_x,
                        "tool_face_y": tool_face_y,
                        "tool_face_z": tool_face_z,
                    },
                )
            )
        return ToolResult("Body split successfully")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("divide_face", "Divide a face using projecting curves or edges")
def divide_face(
    target_face_x: float = 0.0,
    target_face_y: float = 0.0,
    target_face_z: float = 0.0,
    boundary_sketch: str = "last",
    body: str = "last",
):
    """
    Divides a specific face on a body into multiple faces using projecting boundary curves.

    Args:
        target_face_x (float): The X coordinate to identify the target face.
        target_face_y (float): The Y coordinate to identify the target face.
        target_face_z (float): The Z coordinate to identify the target face.
        boundary_sketch (str): The identifier of the projecting sketch or curve.
        body (str): The identifier of the body containing the face.

    Returns:
        ToolResult: A confirmation message of the divide operation.
    """
    target_face_x = float(target_face_x)
    target_face_y = float(target_face_y)
    target_face_z = float(target_face_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "divide_face",
                    {
                        "target_face_x": target_face_x,
                        "target_face_y": target_face_y,
                        "target_face_z": target_face_z,
                        "boundary_sketch": boundary_sketch,
                        "body": body,
                    },
                )
            )
        return ToolResult("Divide face completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "snip_surface", "Snip or split a surface face at specified UV coordinates or points"
)
def snip_surface(
    target_face_x: float = 0.0,
    target_face_y: float = 0.0,
    target_face_z: float = 0.0,
    body: str = "last",
):
    """
    Snips or splits a surface face at the specified coordinates or points.

    Args:
        target_face_x (float): The X coordinate to identify the target face.
        target_face_y (float): The Y coordinate to identify the target face.
        target_face_z (float): The Z coordinate to identify the target face.
        body (str): The identifier of the body containing the face.

    Returns:
        ToolResult: A confirmation message of the snip operation.
    """
    target_face_x = float(target_face_x)
    target_face_y = float(target_face_y)
    target_face_z = float(target_face_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "snip_surface",
                    {
                        "target_face_x": target_face_x,
                        "target_face_y": target_face_y,
                        "target_face_z": target_face_z,
                        "body": body,
                    },
                )
            )
        return ToolResult("Snip surface completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("untrim_sheet", "Remove trim boundaries from sheet body faces")
def untrim_sheet(
    target_edge_x: float = 0.0,
    target_edge_y: float = 0.0,
    target_edge_z: float = 0.0,
    body: str = "last",
):
    """
    Removes trim boundaries from a sheet body's faces, restoring them to untrimmed base states.

    Args:
        target_edge_x (float): The X coordinate to identify the trimmed edge.
        target_edge_y (float): The Y coordinate to identify the trimmed edge.
        target_edge_z (float): The Z coordinate to identify the trimmed edge.
        body (str): The identifier of the target sheet body.

    Returns:
        ToolResult: A confirmation message of the untrim operation.
    """
    target_edge_x = float(target_edge_x)
    target_edge_y = float(target_edge_y)
    target_edge_z = float(target_edge_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "untrim_sheet",
                    {
                        "target_edge_x": target_edge_x,
                        "target_edge_y": target_edge_y,
                        "target_edge_z": target_edge_z,
                        "body": body,
                    },
                )
            )
        return ToolResult("Untrimmed sheet successfully")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("delete_edge", "Delete an edge of a sheet face to combine faces")
def delete_edge(
    target_edge_x: float = 0.0,
    target_edge_y: float = 0.0,
    target_edge_z: float = 0.0,
    body: str = "last",
):
    """
    Deletes an edge from a sheet face to combine adjacent faces or remove features.

    Args:
        target_edge_x (float): The X coordinate of the edge to delete.
        target_edge_y (float): The Y coordinate of the edge to delete.
        target_edge_z (float): The Z coordinate of the edge to delete.
        body (str): The identifier of the body containing the edge.

    Returns:
        ToolResult: A confirmation message of the edge deletion.
    """
    target_edge_x = float(target_edge_x)
    target_edge_y = float(target_edge_y)
    target_edge_z = float(target_edge_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "delete_edge",
                    {
                        "target_edge_x": target_edge_x,
                        "target_edge_y": target_edge_y,
                        "target_edge_z": target_edge_z,
                        "body": body,
                    },
                )
            )
        return ToolResult("Delete edge completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("emboss_body", "Emboss sheet profiles into solid/sheet body")
def emboss_body(
    target_body: str = "last", boundary_sketch: str = "last", depth: float = None
):
    """
    Embosses a sheet profile into a solid or sheet body by a specified depth.

    Args:
        target_body (str): The identifier of the target body to emboss.
        boundary_sketch (str): The identifier of the profile sketch to emboss.
        depth (float): The depth of the emboss in millimeters (must be positive).

    Returns:
        ToolResult: A confirmation message indicating the emboss operation completed.
    """
    try:
        if depth is None:
            return ToolError("Emboss depth must be positive")
        depth = float(depth)
        if depth <= 0:
            return ToolError("Emboss depth must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "emboss_body",
                    {
                        "target_body": target_body,
                        "boundary_sketch": boundary_sketch,
                        "depth": depth,
                    },
                )
            )
        return ToolResult(f"Emboss body completed by {depth}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("patch_body", "Patch a sheet body into a solid target body")
def patch_body(target_body: str = "last", tool_sheet: str = "last"):
    """
    Patches a sheet body into a target body to modify its topology or fill regions.

    Args:
        target_body (str): The identifier of the body to patch into.
        tool_sheet (str): The identifier of the sheet body acting as the patch.

    Returns:
        ToolResult: A confirmation message of the patch operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "patch_body", {"target_body": target_body, "tool_sheet": tool_sheet}
                )
            )
        return ToolResult("Body patched successfully")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("unsew_sheets", "Unsew or disconnect sheet boundaries along edges")
def unsew_sheets(
    target_body: str = "last",
    split_edge_x: float = 0.0,
    split_edge_y: float = 0.0,
    split_edge_z: float = 0.0,
):
    """
    Unsews or disconnects previously sewn sheet boundaries along specified edges.

    Args:
        target_body (str): The identifier of the sewn sheet or solid body.
        split_edge_x (float): The X coordinate of the edge to unsew.
        split_edge_y (float): The Y coordinate of the edge to unsew.
        split_edge_z (float): The Z coordinate of the edge to unsew.

    Returns:
        ToolResult: A confirmation message of the unsew operation.
    """
    split_edge_x = float(split_edge_x)
    split_edge_y = float(split_edge_y)
    split_edge_z = float(split_edge_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "unsew_sheets",
                    {
                        "target_body": target_body,
                        "split_edge_x": split_edge_x,
                        "split_edge_y": split_edge_y,
                        "split_edge_z": split_edge_z,
                    },
                )
            )
        return ToolResult("Unsewed sheet body")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("make_solid", "Convert closed sewn sheet body to solid body")
def make_solid(target_sheet: str = "last"):
    """
    Converts a fully closed and sewn sheet body into a solid body.

    Args:
        target_sheet (str): The identifier of the closed sheet body to convert.

    Returns:
        ToolResult: A confirmation message of the solid conversion.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("make_solid", {"target_sheet": target_sheet})
            )
        return ToolResult("Sewn sheet body successfully converted to Solid body")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("sheet_boundary_analysis", "Analyze sheet body perimeter to find open edges")
def sheet_boundary_analysis(body: str = "last"):
    """
    Analyzes the perimeter of a sheet body to identify any open, unsewn edges.

    Args:
        body (str): The identifier of the sheet body to analyze.

    Returns:
        ToolResult: A report of the analysis, indicating the number of open edges found.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("sheet_boundary_analysis", {"body": body})
            )
        return ToolResult("Sheet boundary analysis: 0 open edges found")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("quilt_sheets", "Quilt sheet boundaries together")
def quilt_sheets(target_sheet: str = "last"):
    """
    Quilts sheet boundaries together to form connected geometry from detached faces.

    Args:
        target_sheet (str): The identifier of the primary sheet to quilt.

    Returns:
        ToolResult: A confirmation message of the quilting operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("quilt_sheets", {"target_sheet": target_sheet})
            )
        return ToolResult("Sheets quilted successfully")
    except Exception as e:
        return ToolError(str(e))
