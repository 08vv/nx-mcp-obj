import os
from typing import Literal

from ..bridge import runner
from ..response import ToolError, ToolResult
from ..tools.registry import mcp_tool
from nx_mcp.tools._common import _bridge_result, _use_mock_nxopen




@mcp_tool("reverse_normal", "Reverse the surface normal direction of sheet body faces")
def reverse_normal(body: str = "last"):
    """
    Reverses the surface normal direction of a specified sheet body's faces.

    Args:
        body (str): The identifier of the sheet body.

    Returns:
        ToolResult: A confirmation message of the normal reversal.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("reverse_normal", {"body": body}))
        return ToolResult("Reversed sheet normal direction")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("local_untrim_extend", "Locally untrim and extend a sheet edge boundary")
def local_untrim_extend(
    boundary_edge_x: float = 0.0,
    boundary_edge_y: float = 0.0,
    boundary_edge_z: float = 0.0,
    distance: float = 10.0,
    body: str = "last",
):
    """
    Locally untrims and extends a specific sheet edge boundary by a given distance.

    Args:
        boundary_edge_x (float): The X coordinate of the boundary edge.
        boundary_edge_y (float): The Y coordinate of the boundary edge.
        boundary_edge_z (float): The Z coordinate of the boundary edge.
        distance (float): The extension distance in millimeters (must be positive).
        body (str): The identifier of the sheet body.

    Returns:
        ToolResult: A confirmation message indicating the extended distance.
    """
    boundary_edge_x = float(boundary_edge_x)
    boundary_edge_y = float(boundary_edge_y)
    boundary_edge_z = float(boundary_edge_z)
    distance = float(distance)
    try:
        if distance <= 0:
            return ToolError("Extension distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "local_untrim_extend",
                    {
                        "boundary_edge_x": boundary_edge_x,
                        "boundary_edge_y": boundary_edge_y,
                        "boundary_edge_z": boundary_edge_z,
                        "distance": distance,
                        "body": body,
                    },
                )
            )
        return ToolResult(f"Untrimmed and extended face by {distance}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "replace_edge", "Replace a face boundary edge using projecting curve geometries"
)
def replace_edge(
    target_edge_x: float = 0.0,
    target_edge_y: float = 0.0,
    target_edge_z: float = 0.0,
    tool_sketch: str = "last",
    body: str = "last",
):
    """
    Replaces a face boundary edge using projecting curve geometries from a tool sketch.

    Args:
        target_edge_x (float): The X coordinate of the edge to replace.
        target_edge_y (float): The Y coordinate of the edge to replace.
        target_edge_z (float): The Z coordinate of the edge to replace.
        tool_sketch (str): The identifier of the tool sketch providing the new geometry.
        body (str): The identifier of the body containing the edge.

    Returns:
        ToolResult: A confirmation message of the edge replacement.
    """
    target_edge_x = float(target_edge_x)
    target_edge_y = float(target_edge_y)
    target_edge_z = float(target_edge_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "replace_edge",
                    {
                        "target_edge_x": target_edge_x,
                        "target_edge_y": target_edge_y,
                        "target_edge_z": target_edge_z,
                        "tool_sketch": tool_sketch,
                        "body": body,
                    },
                )
            )
        return ToolResult("Replaced edge completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("x_form", "Modify freeform sheet faces using X-Form pole grid translation")
def x_form(body: str = "last"):
    """
    Modifies freeform sheet faces using X-Form pole grid translation for conceptual design.

    Args:
        body (str): The identifier of the sheet body to modify.

    Returns:
        ToolResult: A confirmation message of the X-Form deformation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("x_form", {"body": body}))
        return ToolResult("X-Form deformation applied")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("i_form", "Modify freeform sheet faces using I-Form shape matching")
def i_form(body: str = "last"):
    """
    Modifies freeform sheet faces using I-Form shape matching techniques.

    Args:
        body (str): The identifier of the sheet body to modify.

    Returns:
        ToolResult: A confirmation message of the I-Form deformation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("i_form", {"body": body}))
        return ToolResult("I-Form deformation applied")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "match_edge",
    "Deform a sheet face boundary edge to match target edge curvature continuity",
)
def match_edge(
    target_edge_x: float = 0.0,
    target_edge_y: float = 0.0,
    target_edge_z: float = 0.0,
    tool_edge_x: float = 0.0,
    tool_edge_y: float = 0.0,
    tool_edge_z: float = 0.0,
    body: str = "last",
):
    """
    Deforms a sheet face boundary edge to match the curvature continuity of a target edge.

    Args:
        target_edge_x (float): The X coordinate of the target edge to match.
        target_edge_y (float): The Y coordinate of the target edge to match.
        target_edge_z (float): The Z coordinate of the target edge to match.
        tool_edge_x (float): The X coordinate of the edge to be deformed.
        tool_edge_y (float): The Y coordinate of the edge to be deformed.
        tool_edge_z (float): The Z coordinate of the edge to be deformed.
        body (str): The identifier of the sheet body to deform.

    Returns:
        ToolResult: A confirmation message of the edge matching operation.
    """
    target_edge_x = float(target_edge_x)
    target_edge_y = float(target_edge_y)
    target_edge_z = float(target_edge_z)
    tool_edge_x = float(tool_edge_x)
    tool_edge_y = float(tool_edge_y)
    tool_edge_z = float(tool_edge_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "match_edge",
                    {
                        "target_edge_x": target_edge_x,
                        "target_edge_y": target_edge_y,
                        "target_edge_z": target_edge_z,
                        "tool_edge_x": tool_edge_x,
                        "tool_edge_y": tool_edge_y,
                        "tool_edge_z": tool_edge_z,
                        "body": body,
                    },
                )
            )
        return ToolResult("Match edge feature created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("edge_symmetry", "Apply symmetric boundary constraints to face edges")
def edge_symmetry(
    target_edge_x: float = 0.0,
    target_edge_y: float = 0.0,
    target_edge_z: float = 0.0,
    body: str = "last",
):
    """
    Applies symmetric boundary constraints to face edges for symmetrical deformation.

    Args:
        target_edge_x (float): The X coordinate of the edge to constrain.
        target_edge_y (float): The Y coordinate of the edge to constrain.
        target_edge_z (float): The Z coordinate of the edge to constrain.
        body (str): The identifier of the body containing the edge.

    Returns:
        ToolResult: A confirmation message of the applied symmetry.
    """
    target_edge_x = float(target_edge_x)
    target_edge_y = float(target_edge_y)
    target_edge_z = float(target_edge_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "edge_symmetry",
                    {
                        "target_edge_x": target_edge_x,
                        "target_edge_y": target_edge_y,
                        "target_edge_z": target_edge_z,
                        "body": body,
                    },
                )
            )
        return ToolResult("Edge symmetry applied")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("global_shaping", "Apply global shaping deform maps across sheet faces")
def global_shaping(body: str = "last"):
    """
    Applies global shaping deform maps across the specified sheet faces.

    Args:
        body (str): The identifier of the sheet body to shape.

    Returns:
        ToolResult: A confirmation message of the global shaping operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("global_shaping", {"body": body}))
        return ToolResult("Global shaping applied to sheet")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("global_deformation", "Deform a sheet body using displacement points/regions")
def global_deformation(body: str = "last"):
    """
    Deforms a sheet body using advanced displacement points or regions.

    Args:
        body (str): The identifier of the sheet body to deform.

    Returns:
        ToolResult: A confirmation message of the global deformation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("global_deformation", {"body": body}))
        return ToolResult("Global deformation applied")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "flattening_forming", "Flatten highly curved sheets or form curves back onto sheets"
)
def flattening_forming(body: str = "last"):
    """
    Flattens highly curved sheets or forms curves back onto sheets for manufacturability analysis.

    Args:
        body (str): The identifier of the sheet body to process.

    Returns:
        ToolResult: A confirmation message of the flattening or forming operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("flattening_forming", {"body": body}))
        return ToolResult("Flattening and forming completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "heal_surface", "Heal topological errors and gaps inside open sheet geometries"
)
def heal_surface(body: str = "last"):
    """
    Heals topological errors and gaps within open sheet geometries.

    Args:
        body (str): The identifier of the sheet body to heal.

    Returns:
        ToolResult: A confirmation message of the surface healing.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("heal_surface", {"body": body}))
        return ToolResult("Surface healed successfully")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "edit_uv_direction", "Edit or transpose surface coordinate UV directions on faces"
)
def edit_uv_direction(body: str = "last"):
    """
    Edits or transposes the surface coordinate UV directions on faces.

    Args:
        body (str): The identifier of the sheet body face to edit.

    Returns:
        ToolResult: A confirmation message of the UV direction edit.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("edit_uv_direction", {"body": body}))
        return ToolResult("Edited face UV direction")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "enlarge_face", "Enlarge a sheet face boundary proportionally by scale distance"
)
def enlarge_face(
    body: str = "last",
    distance: float = 5.0,
    face_x: float = 0.0,
    face_y: float = 0.0,
    face_z: float = 0.0,
):
    """
    Enlarges a sheet face boundary proportionally by a specified scale distance.

    Args:
        body (str): The identifier of the sheet body containing the face.
        distance (float): The enlargement distance in millimeters (must be positive).
        face_x (float): The X coordinate of the face to enlarge.
        face_y (float): The Y coordinate of the face to enlarge.
        face_z (float): The Z coordinate of the face to enlarge.

    Returns:
        ToolResult: A confirmation message indicating the enlarged distance.
    """
    distance = float(distance)
    face_x = float(face_x)
    face_y = float(face_y)
    face_z = float(face_z)
    try:
        if distance <= 0:
            return ToolError("Enlarge distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "enlarge_face",
                    {
                        "body": body,
                        "distance": distance,
                        "face_x": face_x,
                        "face_y": face_y,
                        "face_z": face_z,
                    },
                )
            )
        return ToolResult(f"Enlarged face by {distance}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("snip_into_patches", "Snip sheet faces into rectangular patch subdivisions")
def snip_into_patches(body: str = "last"):
    """
    Snips sheet faces into rectangular patch subdivisions for downstream operations.

    Args:
        body (str): The identifier of the sheet body to subdivide.

    Returns:
        ToolResult: A confirmation message of the patch subdivision.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("snip_into_patches", {"body": body}))
        return ToolResult("Snipped surface into patches")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("smooth_poles", "Smooth control points of freeform sheet boundaries")
def smooth_poles(body: str = "last"):
    """
    Smooths control points (poles) of freeform sheet boundaries to improve surface quality.

    Args:
        body (str): The identifier of the sheet body to smooth.

    Returns:
        ToolResult: A confirmation message of the smoothing operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("smooth_poles", {"body": body}))
        return ToolResult("Smoothed poles of freeform face")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "refit_face", "Refit sheet face boundary geometries to match exact constraints"
)
def refit_face(body: str = "last"):
    """
    Refits sheet face boundary geometries to match exact surrounding constraints.

    Args:
        body (str): The identifier of the sheet body face to refit.

    Returns:
        ToolResult: A confirmation message of the face refitting.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("refit_face", {"body": body}))
        return ToolResult("Refitted face geometry")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "variable_offset",
    "Offset curves (constant or linear law) or offset a face by distance.",
)
def variable_offset(
    target_ref: str = "last",
    offset_start: float = 5.0,
    offset_end: float = None,
    law: Literal["linear", "constant"] = "linear",
    body: str = "last",
):
    """Offsets curves or faces using NXOpen OffsetCurve/OffsetFace builders.

    Args:
        target_ref (str): Identifier of the curve/profile or face to offset (e.g. 'profile_1', 'curve_1', 'last').
        offset_start (float): Start offset distance in millimeters.
        offset_end (float): Optional end offset distance in millimeters for linear law.
        law (str): Offset law type ('linear' or 'constant').
        body (str): Body identifier if target_ref refers to a face on a body.

    Returns:
        ToolResult or ToolError: Result containing feature_id and updated profile_id / body_id.
    """
    try:
        offset_start = float(offset_start)
        if offset_end is not None:
            offset_end = float(offset_end)
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "variable_offset",
                    {
                        "target_ref": target_ref,
                        "offset_start": offset_start,
                        "offset_end": offset_end,
                        "law": law,
                        "body": body,
                    },
                )
            )
        return ToolResult(f"Variable offset applied to '{target_ref}' (start={offset_start})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "shell",
    "Hollow / Shell a solid body with a uniform wall thickness and optional open/removed faces.",
)
def shell(
    body_id: str = "last",
    thickness: float = 2.0,
    faces_to_remove: list = None,
):
    """Hollows a solid body into a thin-walled shell using NXOpen ShellBuilder.

    Args:
        body_id (str): Target body identifier (e.g. 'body_1', 'last').
        thickness (float): Wall thickness in millimeters.
        faces_to_remove (list): Optional list of coordinate dicts [{'x':0,'y':0,'z':50}] indicating faces to pierce/open.

    Returns:
        ToolResult or ToolError: Result containing the body_id and feature_id.
    """
    try:
        thickness = float(thickness)
        if thickness <= 0.0:
            return ToolError("Shell thickness must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "shell",
                    {
                        "body_id": body_id,
                        "thickness": thickness,
                        "faces_to_remove": faces_to_remove,
                    },
                )
            )
        return ToolResult(f"Shelled body '{body_id}' with thickness {thickness}mm")
    except Exception as e:
        return ToolError(str(e))

