import os
from typing import Literal

from ..bridge import runner
from ..response import ToolError, ToolResult
from ..tools.registry import mcp_tool
from nx_mcp.tools._common import _bridge_result, _use_mock_nxopen




@mcp_tool(
    "create_base_surface",
    "Create a rectangular planar sheet body on XY/XZ/YZ plane for surface modeling workflows. "
    "Note: This creates a permanent reference sheet body (for trim/sew/thicken), not a 2D sketch plane. "
    "For 2D sketch offset positioning, use create_sketch(plane='XY', z_offset=...) or create_real_sketch(z_offset=...)."
)
def create_base_surface(plane: Literal["XY", "XZ", "YZ"] = "XY", width: float = None, height: float = None):
    """
    Create a base bounded plane surface (sheet body) on XY/XZ/YZ plane for surface modeling operations.

    Args:
        plane (str): Plane orientation ('XY', 'XZ', or 'YZ').
        width (float): Width in millimeters.
        height (float): Height in millimeters.

    Returns:
        ToolResult: Confirmation message of the created sheet body.
    """
    try:
        if width is None or height is None:
            return ToolError("Base surface width and height must be positive")
        width = float(width)
        height = float(height)
        if width <= 0 or height <= 0:
            return ToolError("Base surface width and height must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_base_surface",
                    {"plane": plane, "width": width, "height": height},
                )
            )
        return ToolResult(f"Created base surface {width}x{height} on {plane}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("extrude_surface", "Extrude active sketch curves to create a sheet body")
def extrude_surface(distance: float, start: float = 0.0, direction: str = "auto"):
    """
    Extrude active sketch curves to create a sheet body.

    Args:
        distance (float): Parameter distance.
        start (float): Parameter start.
        direction (str): Parameter direction.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    distance = float(distance)
    try:
        if distance <= 0:
            return ToolError("Extrude distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "extrude_surface",
                    {"distance": distance, "start": start, "direction": direction},
                )
            )
        return ToolResult(f"Extruded surface {distance}mm along {direction}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "create_swept", "Create a swept surface from section curves along guide curves"
)
def create_swept(section: str = "last", guide: str = "last"):
    """
    Create a swept surface from section curves along guide curves.

    Args:
        section (str): Parameter section.
        guide (str): Parameter guide.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("create_swept", {"section": section, "guide": guide})
            )
        return ToolResult("Swept surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("create_through_curves", "Create a surface through section curves")
def create_through_curves(sections: str = "last"):
    """
    Create a surface through section curves.

    Args:
        sections (str): Parameter sections.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("create_through_curves", {"sections": sections})
            )
        return ToolResult("Through curves surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "create_through_curve_mesh", "Create a surface using primary and cross sections"
)
def create_through_curve_mesh(primary: str = "last", cross: str = "last"):
    """
    Create a surface using primary and cross sections.

    Args:
        primary (str): Parameter primary.
        cross (str): Parameter cross.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_through_curve_mesh", {"primary": primary, "cross": cross}
                )
            )
        return ToolResult("Through curve mesh created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("add_face_blend", "Create a blend between two faces of a body")
def add_face_blend(
    face1_x: float,
    face1_y: float,
    face1_z: float,
    face2_x: float,
    face2_y: float,
    face2_z: float,
    radius: float,
    body: str = "last",
):
    """
    Create a blend between two faces of a body.

    Args:
        face1_x (float): Parameter face1_x.
        face1_y (float): Parameter face1_y.
        face1_z (float): Parameter face1_z.
        face2_x (float): Parameter face2_x.
        face2_y (float): Parameter face2_y.
        face2_z (float): Parameter face2_z.
        radius (float): Parameter radius.
        body (str): Parameter body.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    face1_x = float(face1_x)
    face1_y = float(face1_y)
    face1_z = float(face1_z)
    face2_x = float(face2_x)
    face2_y = float(face2_y)
    face2_z = float(face2_z)
    radius = float(radius)
    try:
        if radius <= 0:
            return ToolError("Radius must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "add_face_blend",
                    {
                        "face1_x": face1_x,
                        "face1_y": face1_y,
                        "face1_z": face1_z,
                        "face2_x": face2_x,
                        "face2_y": face2_y,
                        "face2_z": face2_z,
                        "radius": radius,
                        "body": body,
                    },
                )
            )
        return ToolResult(f"Face blend R{radius}mm added between faces")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("offset_surface", "Create an offset surface from a face")
def offset_surface(
    distance: float,
    body: str = "last",
    face_x: float = 0.0,
    face_y: float = 0.0,
    face_z: float = 0.0,
):
    """
    Create an offset surface from a face.

    Args:
        distance (float): Parameter distance.
        body (str): Parameter body.
        face_x (float): Parameter face_x.
        face_y (float): Parameter face_y.
        face_z (float): Parameter face_z.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    distance = float(distance)
    face_x = float(face_x)
    face_y = float(face_y)
    face_z = float(face_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "offset_surface",
                    {
                        "distance": distance,
                        "body": body,
                        "face_x": face_x,
                        "face_y": face_y,
                        "face_z": face_z,
                    },
                )
            )
        return ToolResult(f"Created offset surface of {distance}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("thicken_sheet", "Thicken a sheet body to create a solid body")
def thicken_sheet(thickness: float, direction: str = "auto", body: str = "last"):
    """
    Thicken a sheet body to create a solid body.

    Args:
        thickness (float): Parameter thickness.
        direction (str): Parameter direction.
        body (str): Parameter body.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    thickness = float(thickness)
    try:
        if thickness <= 0:
            return ToolError("Thickness must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "thicken_sheet",
                    {"thickness": thickness, "direction": direction, "body": body},
                )
            )
        return ToolResult(f"Thickened sheet body '{body}' by {thickness}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("sweep_along_guide", "Sweep profile curves along guide curves")
def sweep_along_guide(section: str = "last", guide: str = "last"):
    """
    Sweep profile curves along guide curves.

    Args:
        section (str): Parameter section.
        guide (str): Parameter guide.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "sweep_along_guide", {"section": section, "guide": guide}
                )
            )
        return ToolResult("Sweep along guide created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("variational_sweep", "Variational sweep of sketch profile along guide curves")
def variational_sweep(section: str = "last", guide: str = "last"):
    """
    Variational sweep of sketch profile along guide curves.

    Args:
        section (str): Parameter section.
        guide (str): Parameter guide.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "variational_sweep", {"section": section, "guide": guide}
                )
            )
        return ToolResult("Variational sweep created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("create_tube", "Create a tube along guide curves")
def create_tube(
    guide: str = "last", outer_diameter: float = None, inner_diameter: float = 0.0
):
    """
    Create a tube along guide curves.

    Args:
        guide (str): Parameter guide.
        outer_diameter (float): Parameter outer_diameter.
        inner_diameter (float): Parameter inner_diameter.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if outer_diameter is None:
            return ToolError("Tube outer_diameter must be positive")
        outer_diameter = float(outer_diameter)
        inner_diameter = float(inner_diameter)
        if outer_diameter <= 0 or inner_diameter < 0:
            return ToolError("Tube diameters must be positive or zero")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_tube",
                    {
                        "guide": guide,
                        "outer_diameter": outer_diameter,
                        "inner_diameter": inner_diameter,
                    },
                )
            )
        return ToolResult(
            f"Tube created along guide (OD={outer_diameter}, ID={inner_diameter})"
        )
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("swept_volume", "Swept volume generated by moving a body along a path")
def swept_volume(tool_body: str = "last", guide: str = "last"):
    """
    Swept volume generated by moving a body along a path.

    Args:
        tool_body (str): Parameter tool_body.
        guide (str): Parameter guide.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("swept_volume", {"tool_body": tool_body, "guide": guide})
            )
        return ToolResult("Swept volume created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("create_ruled", "Create ruled surface between two section curves")
def create_ruled(section1: str = "last", section2: str = "last"):
    """
    Create ruled surface between two section curves.

    Args:
        section1 (str): Parameter section1.
        section2 (str): Parameter section2.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_ruled", {"section1": section1, "section2": section2}
                )
            )
        return ToolResult("Ruled surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("n_sided_surface", "Create N-Sided patch surface bounded by curves")
def n_sided_surface(boundary: str = "last"):
    """
    Create N-Sided patch surface bounded by curves.

    Args:
        boundary (str): Parameter boundary.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("n_sided_surface", {"boundary": boundary})
            )
        return ToolResult("N-Sided surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("fill_surface", "Create fill patch bounded by curves")
def fill_surface(boundary: str = "last"):
    """
    Create fill patch bounded by curves.

    Args:
        boundary (str): Parameter boundary.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("fill_surface", {"boundary": boundary})
            )
        return ToolResult("Fill surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("bounded_plane", "Create a planar sheet body bounded by curves")
def bounded_plane(boundary: str = "last"):
    """
    Create a planar sheet body bounded by curves.

    Args:
        boundary (str): Parameter boundary.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("bounded_plane", {"boundary": boundary})
            )
        return ToolResult("Bounded plane created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("patch_openings", "Patch openings in a sheet body")
def patch_openings(body: str = "last", boundary: str = "last"):
    """
    Patch openings in a sheet body.

    Args:
        body (str): Parameter body.
        boundary (str): Parameter boundary.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("patch_openings", {"body": body, "boundary": boundary})
            )
        return ToolResult("Patched openings on sheet body")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("variable_offset", "Offset a face by variable distance")
def variable_offset(
    distance_start: float,
    distance_end: float,
    body: str = "last",
    face_x: float = 0.0,
    face_y: float = 0.0,
    face_z: float = 0.0,
):
    """
    Offset a face by variable distance.

    Args:
        distance_start (float): Parameter distance_start.
        distance_end (float): Parameter distance_end.
        body (str): Parameter body.
        face_x (float): Parameter face_x.
        face_y (float): Parameter face_y.
        face_z (float): Parameter face_z.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    distance_start = float(distance_start)
    distance_end = float(distance_end)
    face_x = float(face_x)
    face_y = float(face_y)
    face_z = float(face_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "variable_offset",
                    {
                        "distance_start": distance_start,
                        "distance_end": distance_end,
                        "body": body,
                        "face_x": face_x,
                        "face_y": face_y,
                        "face_z": face_z,
                    },
                )
            )
        return ToolResult(
            f"Variable offset surface ({distance_start}mm to {distance_end}mm) created"
        )
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("sheet_from_curve", "Create sheet body from curves")
def sheet_from_curve(boundary: str = "last"):
    """
    Create sheet body from curves.

    Args:
        boundary (str): Parameter boundary.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("sheet_from_curve", {"boundary": boundary})
            )
        return ToolResult("Sheet from curves created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "law_extension",
    "Create extension from sheet boundary matching angle and length laws",
)
def law_extension(
    distance: float,
    angle: float,
    boundary_edge_x: float = 0.0,
    boundary_edge_y: float = 0.0,
    boundary_edge_z: float = 0.0,
    body: str = "last",
):
    """
    Create extension from sheet boundary matching angle and length laws.

    Args:
        distance (float): Parameter distance.
        angle (float): Parameter angle.
        boundary_edge_x (float): Parameter boundary_edge_x.
        boundary_edge_y (float): Parameter boundary_edge_y.
        boundary_edge_z (float): Parameter boundary_edge_z.
        body (str): Parameter body.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    distance = float(distance)
    angle = float(angle)
    boundary_edge_x = float(boundary_edge_x)
    boundary_edge_y = float(boundary_edge_y)
    boundary_edge_z = float(boundary_edge_z)
    try:
        if distance <= 0:
            return ToolError("Distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "law_extension",
                    {
                        "distance": distance,
                        "angle": angle,
                        "boundary_edge_x": boundary_edge_x,
                        "boundary_edge_y": boundary_edge_y,
                        "boundary_edge_z": boundary_edge_z,
                        "body": body,
                    },
                )
            )
        return ToolResult("Law extension surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("studio_surface", "Create clean lofted surface matching continuity bounds")
def studio_surface(section1: str = "last", section2: str = "last"):
    """
    Create clean lofted surface matching continuity bounds.

    Args:
        section1 (str): Parameter section1.
        section2 (str): Parameter section2.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "studio_surface", {"section1": section1, "section2": section2}
                )
            )
        return ToolResult("Studio surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("styled_sweep", "Create styled sweep surface")
def styled_sweep(section: str = "last", guide: str = "last"):
    """
    Create styled sweep surface.

    Args:
        section (str): Parameter section.
        guide (str): Parameter guide.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("styled_sweep", {"section": section, "guide": guide})
            )
        return ToolResult("Styled sweep surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("section_surface", "Create surface by interpolating sections")
def section_surface(section1: str = "last", section2: str = "last"):
    """
    Create surface by interpolating sections.

    Args:
        section1 (str): Parameter section1.
        section2 (str): Parameter section2.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "section_surface", {"section1": section1, "section2": section2}
                )
            )
        return ToolResult("Section surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("aesthetic_face_blend", "Create highly styled aesthetic blend between faces")
def aesthetic_face_blend(
    radius: float,
    body: str = "last",
    face1_x: float = 0.0,
    face1_y: float = 0.0,
    face1_z: float = 0.0,
    face2_x: float = 0.0,
    face2_y: float = 0.0,
    face2_z: float = 0.0,
):
    """
    Create highly styled aesthetic blend between faces.

    Args:
        radius (float): Parameter radius.
        body (str): Parameter body.
        face1_x (float): Parameter face1_x.
        face1_y (float): Parameter face1_y.
        face1_z (float): Parameter face1_z.
        face2_x (float): Parameter face2_x.
        face2_y (float): Parameter face2_y.
        face2_z (float): Parameter face2_z.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    radius = float(radius)
    face1_x = float(face1_x)
    face1_y = float(face1_y)
    face1_z = float(face1_z)
    face2_x = float(face2_x)
    face2_y = float(face2_y)
    face2_z = float(face2_z)
    try:
        if radius <= 0:
            return ToolError("Radius must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "aesthetic_face_blend",
                    {
                        "radius": radius,
                        "body": body,
                        "face1_x": face1_x,
                        "face1_y": face1_y,
                        "face1_z": face1_z,
                        "face2_x": face2_x,
                        "face2_y": face2_y,
                        "face2_z": face2_z,
                    },
                )
            )
        return ToolResult(f"Aesthetic face blend R{radius}mm created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("bridge_surface", "Create bridge surface between two boundary edges")
def bridge_surface(
    edge1_x: float = 0.0,
    edge1_y: float = 0.0,
    edge1_z: float = 0.0,
    edge2_x: float = 0.0,
    edge2_y: float = 0.0,
    edge2_z: float = 0.0,
    body: str = "last",
):
    """
    Create bridge surface between two boundary edges.

    Args:
        edge1_x (float): Parameter edge1_x.
        edge1_y (float): Parameter edge1_y.
        edge1_z (float): Parameter edge1_z.
        edge2_x (float): Parameter edge2_x.
        edge2_y (float): Parameter edge2_y.
        edge2_z (float): Parameter edge2_z.
        body (str): Parameter body.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    edge1_x = float(edge1_x)
    edge1_y = float(edge1_y)
    edge1_z = float(edge1_z)
    edge2_x = float(edge2_x)
    edge2_y = float(edge2_y)
    edge2_z = float(edge2_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "bridge_surface",
                    {
                        "edge1_x": edge1_x,
                        "edge1_y": edge1_y,
                        "edge1_z": edge1_z,
                        "edge2_x": edge2_x,
                        "edge2_y": edge2_y,
                        "edge2_z": edge2_z,
                        "body": body,
                    },
                )
            )
        return ToolResult("Bridge surface created between edges")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("blend_corner", "Create spherical corner blend on sharp intersections")
def blend_corner(
    radius: float,
    corner_vertex_x: float = 0.0,
    corner_vertex_y: float = 0.0,
    corner_vertex_z: float = 0.0,
    body: str = "last",
):
    """
    Create spherical corner blend on sharp intersections.

    Args:
        radius (float): Parameter radius.
        corner_vertex_x (float): Parameter corner_vertex_x.
        corner_vertex_y (float): Parameter corner_vertex_y.
        corner_vertex_z (float): Parameter corner_vertex_z.
        body (str): Parameter body.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    radius = float(radius)
    corner_vertex_x = float(corner_vertex_x)
    corner_vertex_y = float(corner_vertex_y)
    corner_vertex_z = float(corner_vertex_z)
    try:
        if radius <= 0:
            return ToolError("Radius must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "blend_corner",
                    {
                        "radius": radius,
                        "corner_vertex_x": corner_vertex_x,
                        "corner_vertex_y": corner_vertex_y,
                        "corner_vertex_z": corner_vertex_z,
                        "body": body,
                    },
                )
            )
        return ToolResult("Blend corner feature created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("styled_corner", "Create styled corner transient surface")
def styled_corner(
    corner_vertex_x: float = 0.0,
    corner_vertex_y: float = 0.0,
    corner_vertex_z: float = 0.0,
    body: str = "last",
):
    """
    Create styled corner transient surface.

    Args:
        corner_vertex_x (float): Parameter corner_vertex_x.
        corner_vertex_y (float): Parameter corner_vertex_y.
        corner_vertex_z (float): Parameter corner_vertex_z.
        body (str): Parameter body.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    corner_vertex_x = float(corner_vertex_x)
    corner_vertex_y = float(corner_vertex_y)
    corner_vertex_z = float(corner_vertex_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "styled_corner",
                    {
                        "corner_vertex_x": corner_vertex_x,
                        "corner_vertex_y": corner_vertex_y,
                        "corner_vertex_z": corner_vertex_z,
                        "body": body,
                    },
                )
            )
        return ToolResult("Styled corner created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("four_point_surface", "Create sheet body passing through four 3D points")
def four_point_surface(
    x1: float,
    y1: float,
    z1: float,
    x2: float,
    y2: float,
    z2: float,
    x3: float,
    y3: float,
    z3: float,
    x4: float,
    y4: float,
    z4: float,
):
    """
    Create sheet body passing through four 3D points.

    Args:
        x1 (float): Parameter x1.
        y1 (float): Parameter y1.
        z1 (float): Parameter z1.
        x2 (float): Parameter x2.
        y2 (float): Parameter y2.
        z2 (float): Parameter z2.
        x3 (float): Parameter x3.
        y3 (float): Parameter y3.
        z3 (float): Parameter z3.
        x4 (float): Parameter x4.
        y4 (float): Parameter y4.
        z4 (float): Parameter z4.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    x1 = float(x1)
    y1 = float(y1)
    x2 = float(x2)
    y2 = float(y2)
    x3 = float(x3)
    y3 = float(y3)
    z3 = float(z3)
    x4 = float(x4)
    y4 = float(y4)
    z4 = float(z4)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "four_point_surface",
                    {
                        "x1": x1,
                        "y1": y1,
                        "z1": z1,
                        "x2": x2,
                        "y2": y2,
                        "z2": z2,
                        "x3": x3,
                        "y3": y3,
                        "z3": z3,
                        "x4": x4,
                        "y4": y4,
                        "z4": z4,
                    },
                )
            )
        return ToolResult("Four point surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("rapid_surfacing", "Create freeform face matching boundary bounds")
def rapid_surfacing(boundary: str = "last"):
    """
    Create freeform face matching boundary bounds.

    Args:
        boundary (str): Parameter boundary.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("rapid_surfacing", {"boundary": boundary})
            )
        return ToolResult("Rapid surfacing sheet created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("fit_surface", "Fit new face geometries to target body faces")
def fit_surface(
    target_face_x: float = 0.0,
    target_face_y: float = 0.0,
    target_face_z: float = 0.0,
    body: str = "last",
):
    """
    Fit new face geometries to target body faces.

    Args:
        target_face_x (float): Parameter target_face_x.
        target_face_y (float): Parameter target_face_y.
        target_face_z (float): Parameter target_face_z.
        body (str): Parameter body.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    target_face_x = float(target_face_x)
    target_face_y = float(target_face_y)
    target_face_z = float(target_face_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "fit_surface",
                    {
                        "target_face_x": target_face_x,
                        "target_face_y": target_face_y,
                        "target_face_z": target_face_z,
                        "body": body,
                    },
                )
            )
        return ToolResult("Fit surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("variable_offset_face", "Offset face using variable profile scaling")
def variable_offset_face(
    distance: float,
    body: str = "last",
    face_x: float = 0.0,
    face_y: float = 0.0,
    face_z: float = 0.0,
):
    """
    Offset face using variable profile scaling.

    Args:
        distance (float): Parameter distance.
        body (str): Parameter body.
        face_x (float): Parameter face_x.
        face_y (float): Parameter face_y.
        face_z (float): Parameter face_z.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    distance = float(distance)
    face_x = float(face_x)
    face_y = float(face_y)
    face_z = float(face_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "variable_offset_face",
                    {
                        "distance": distance,
                        "body": body,
                        "face_x": face_x,
                        "face_y": face_y,
                        "face_z": face_z,
                    },
                )
            )
        return ToolResult(f"Variable offset face by {distance}mm created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("extension_surface", "Extend a surface face geometry along custom bounds")
def extension_surface(
    distance: float,
    boundary_edge_x: float = 0.0,
    boundary_edge_y: float = 0.0,
    boundary_edge_z: float = 0.0,
    body: str = "last",
):
    """
    Extend a surface face geometry along custom bounds.

    Args:
        distance (float): Parameter distance.
        boundary_edge_x (float): Parameter boundary_edge_x.
        boundary_edge_y (float): Parameter boundary_edge_y.
        boundary_edge_z (float): Parameter boundary_edge_z.
        body (str): Parameter body.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    distance = float(distance)
    boundary_edge_x = float(boundary_edge_x)
    boundary_edge_y = float(boundary_edge_y)
    boundary_edge_z = float(boundary_edge_z)
    try:
        if distance <= 0:
            return ToolError("Distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "extension_surface",
                    {
                        "distance": distance,
                        "boundary_edge_x": boundary_edge_x,
                        "boundary_edge_y": boundary_edge_y,
                        "boundary_edge_z": boundary_edge_z,
                        "body": body,
                    },
                )
            )
        return ToolResult(f"Extension surface of {distance}mm created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("silhouette_flange", "Create flange sheet matching body silhouettes")
def silhouette_flange(
    distance: float,
    body: str = "last",
    face_x: float = 0.0,
    face_y: float = 0.0,
    face_z: float = 0.0,
):
    """
    Create flange sheet matching body silhouettes.

    Args:
        distance (float): Parameter distance.
        body (str): Parameter body.
        face_x (float): Parameter face_x.
        face_y (float): Parameter face_y.
        face_z (float): Parameter face_z.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    distance = float(distance)
    face_x = float(face_x)
    face_y = float(face_y)
    face_z = float(face_z)
    try:
        if distance <= 0:
            return ToolError("Distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "silhouette_flange",
                    {
                        "distance": distance,
                        "body": body,
                        "face_x": face_x,
                        "face_y": face_y,
                        "face_z": face_z,
                    },
                )
            )
        return ToolResult(f"Silhouette flange of {distance}mm created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("face_pairs", "Create pairing relationships between adjacent face contours")
def face_pairs(distance: float, body: str = "last"):
    """
    Create pairing relationships between adjacent face contours.

    Args:
        distance (float): Parameter distance.
        body (str): Parameter body.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    distance = float(distance)
    try:
        if distance <= 0:
            return ToolError("Distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("face_pairs", {"distance": distance, "body": body})
            )
        return ToolResult(f"Face pairs analysis created at distance {distance}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "user_defined_surface", "Create custom user-defined mathematical surface face"
)
def user_defined_surface(boundary: str = "last"):
    """
    Create custom user-defined mathematical surface face.

    Args:
        boundary (str): Parameter boundary.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("user_defined_surface", {"boundary": boundary})
            )
        return ToolResult("User-defined surface created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("offset_surface_advanced", "Advanced freeform variable law surface offset")
def offset_surface_advanced(
    distance: float,
    body: str = "last",
    face_x: float = 0.0,
    face_y: float = 0.0,
    face_z: float = 0.0,
):
    """
    Advanced freeform variable law surface offset.

    Args:
        distance (float): Parameter distance.
        body (str): Parameter body.
        face_x (float): Parameter face_x.
        face_y (float): Parameter face_y.
        face_z (float): Parameter face_z.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    distance = float(distance)
    face_x = float(face_x)
    face_y = float(face_y)
    face_z = float(face_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "offset_surface_advanced",
                    {
                        "distance": distance,
                        "body": body,
                        "face_x": face_x,
                        "face_y": face_y,
                        "face_z": face_z,
                    },
                )
            )
        return ToolResult(f"Advanced offset surface of {distance}mm created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "bisector_surface", "Create bisecting symmetry plane surface sheet between faces"
)
def bisector_surface(
    face1_x: float = 0.0,
    face1_y: float = 0.0,
    face1_z: float = 0.0,
    face2_x: float = 0.0,
    face2_y: float = 0.0,
    face2_z: float = 0.0,
    body: str = "last",
):
    """
    Create bisecting symmetry plane surface sheet between faces.

    Args:
        face1_x (float): Parameter face1_x.
        face1_y (float): Parameter face1_y.
        face1_z (float): Parameter face1_z.
        face2_x (float): Parameter face2_x.
        face2_y (float): Parameter face2_y.
        face2_z (float): Parameter face2_z.
        body (str): Parameter body.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    face1_x = float(face1_x)
    face1_y = float(face1_y)
    face1_z = float(face1_z)
    face2_x = float(face2_x)
    face2_y = float(face2_y)
    face2_z = float(face2_z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "bisector_surface",
                    {
                        "face1_x": face1_x,
                        "face1_y": face1_y,
                        "face1_z": face1_z,
                        "face2_x": face2_x,
                        "face2_y": face2_y,
                        "face2_z": face2_z,
                        "body": body,
                    },
                )
            )
        return ToolResult("Bisector surface created between faces")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "surface_from_poles",
    "Create control-point splined sheet body directly from grid poles",
)
def surface_from_poles(boundary: str = "last"):
    """
    Create control-point splined sheet body directly from grid poles.

    Args:
        boundary (str): Parameter boundary.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("surface_from_poles", {"boundary": boundary})
            )
        return ToolResult("Surface from poles created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "surface_through_points",
    "Create splined sheet body passing exactly through custom coordinates",
)
def surface_through_points(boundary: str = "last"):
    """
    Create splined sheet body passing exactly through custom coordinates.

    Args:
        boundary (str): Parameter boundary.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("surface_through_points", {"boundary": boundary})
            )
        return ToolResult("Surface through points created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "ribbon_builder", "Build ribbon extension sweeps directly matching edge parameters"
)
def ribbon_builder(
    width: float,
    boundary_edge_x: float = 0.0,
    boundary_edge_y: float = 0.0,
    boundary_edge_z: float = 0.0,
    body: str = "last",
):
    """
    Build ribbon extension sweeps directly matching edge parameters.

    Args:
        width (float): Parameter width.
        boundary_edge_x (float): Parameter boundary_edge_x.
        boundary_edge_y (float): Parameter boundary_edge_y.
        boundary_edge_z (float): Parameter boundary_edge_z.
        body (str): Parameter body.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    width = float(width)
    boundary_edge_x = float(boundary_edge_x)
    boundary_edge_y = float(boundary_edge_y)
    boundary_edge_z = float(boundary_edge_z)
    try:
        if width <= 0:
            return ToolError("Width must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "ribbon_builder",
                    {
                        "width": width,
                        "boundary_edge_x": boundary_edge_x,
                        "boundary_edge_y": boundary_edge_y,
                        "boundary_edge_z": boundary_edge_z,
                        "body": body,
                    },
                )
            )
        return ToolResult(f"Ribbon surface of {width}mm width created along edge")
    except Exception as e:
        return ToolError(str(e))
