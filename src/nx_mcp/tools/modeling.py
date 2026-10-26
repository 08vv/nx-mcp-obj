import os
from typing import Literal

from ..bridge import runner
from ..nx_session import NXSession
from ..response import ToolError, ToolResult
from ..tools.registry import mcp_tool
from nx_mcp.tools._common import _bridge_result, _use_mock_nxopen




@mcp_tool(
    "create_cube",
    "Create a cube with side length (required) mm from origin x y z",
)
def create_cube(size: float, x: float = 0.0, y: float = 0.0, z: float = 0.0, centered: bool = False):
    """Creates a cube solid body feature in the active part.

    Args:
        size (float): The length of the cube edges in millimeters (required).
        x (float): The X coordinate of the cube's corner (or center if centered=True) in millimeters.
        y (float): The Y coordinate of the cube's corner (or center if centered=True) in millimeters.
        z (float): The Z coordinate of the cube's corner (or center if centered=True) in millimeters.
        centered (bool): If True, (x, y, z) is treated as the cube's center rather than its corner. Defaults to False.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    size = float(size)
    x = float(x)
    y = float(y)
    z = float(z)
    centered = bool(centered)
    try:
        if size <= 0:
            return ToolError("Cube size must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_cube",
                    {"size": size, "x": x, "y": y, "z": z, "centered": centered},
                )
            )

        # Mock implementation centering adjustment
        x_origin = x - size / 2.0 if centered else x
        y_origin = y - size / 2.0 if centered else y
        z_origin = z - size / 2.0 if centered else z

        b = NXSession.work_part().Features.CreateExtrudeBuilder(None)
        b.Limits.StartExtend.Value.RightHandSide = str(z_origin)
        b.Limits.EndExtend.Value.RightHandSide = str(z_origin + size)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Cube {size}mm at ({x_origin},{y_origin},{z_origin})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "create_cuboid",
    "Create a cuboid with length width height (all required) mm from origin x y z",
)
def create_cuboid(
    length: float,
    width: float,
    height: float,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    centered: bool = False,
):
    """Creates a cuboid solid body feature in the active part.

    Args:
        length (float): The length of the cuboid along the X-axis in millimeters (required).
        width (float): The width of the cuboid along the Y-axis in millimeters (required).
        height (float): The height of the cuboid along the Z-axis in millimeters (required).
        x (float): The X coordinate of the origin point in millimeters.
        y (float): The Y coordinate of the origin point in millimeters.
        z (float): The Z coordinate of the origin point in millimeters.
        centered (bool): If True, (x, y, z) is treated as the block's center rather than its corner. Defaults to False.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    length = float(length)
    width = float(width)
    height = float(height)
    x = float(x)
    y = float(y)
    z = float(z)
    centered = bool(centered)
    try:
        if length <= 0 or width <= 0 or height <= 0:
            return ToolError("Cuboid dimensions must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_cuboid",
                    {
                        "length": length,
                        "width": width,
                        "height": height,
                        "x": x,
                        "y": y,
                        "z": z,
                        "centered": centered,
                    },
                )
            )
        
        # Mock implementation centering adjustment
        x_origin = x - length / 2.0 if centered else x
        y_origin = y - width / 2.0 if centered else y
        z_origin = z - height / 2.0 if centered else z
        
        b = NXSession.work_part().Features.CreateExtrudeBuilder(None)
        b.Limits.StartExtend.Value.RightHandSide = str(z_origin)
        b.Limits.EndExtend.Value.RightHandSide = str(z_origin + height)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Cuboid {length}x{width}x{height}mm centered at ({x_origin},{y_origin},{z_origin})" if centered else f"Cuboid {length}x{width}x{height}mm at ({x},{y},{z})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("create_two_cuboids", "Create two cuboids next to each other")
def create_two_cuboids():
    """Creates two separate cuboid solid body features adjacent to each other.

    Args:

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("create_two_cuboids", {}))
        first = create_cuboid(40.0, 25.0, 20.0, 0.0, 0.0, 0.0)
        if isinstance(first, ToolError):
            return first
        second = create_cuboid(30.0, 25.0, 20.0, 45.0, 0.0, 0.0)
        if isinstance(second, ToolError):
            return second
        return ToolResult("Created two cuboids next to each other")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "create_cylinder",
    "Create a cylinder with radius height (both required) mm from origin x y z along direction X Y or Z",
)
def create_cylinder(
    radius: float,
    height: float,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    direction: str = "Z",
):
    """Creates a cylinder solid body feature in the active part using an NXOpen CylinderBuilder.

    Args:
        radius (float): The cylinder radius in millimeters.
        height (float): The cylinder height in millimeters.
        x (float): The X coordinate of the cylinder base center in millimeters.
        y (float): The Y coordinate of the cylinder base center in millimeters.
        z (float): The Z coordinate of the cylinder base center in millimeters.
        direction (str): The axis direction string ('X', 'Y', or 'Z') for the cylinder's height.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    radius = float(radius)
    height = float(height)
    x = float(x)
    y = float(y)
    z = float(z)
    try:
        if radius <= 0 or height <= 0:
            return ToolError("Cylinder radius and height must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_cylinder",
                    {
                        "radius": radius,
                        "height": height,
                        "x": x,
                        "y": y,
                        "z": z,
                        "direction": direction,
                    },
                )
            )
        return ToolResult(f"Cylinder R{radius} height {height} at ({x},{y},{z})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "extrude",
    "Extrude active sketch curves by distance mm. Extrudes perpendicular to active sketch plane.",
)
def extrude(distance: float, start: float = 0.0):
    """Creates an NXOpen Extrude feature from the active sketch curves.

    Args:
        distance (float): The ending extrude limit distance in millimeters.
        start (float): The starting extrude limit distance in millimeters.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    distance = float(distance)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("extrude", {"distance": distance, "start": start})
            )
        b = NXSession.work_part().Features.CreateExtrudeBuilder(None)
        b.Limits.StartExtend.Value.RightHandSide = str(start)
        b.Limits.EndExtend.Value.RightHandSide = str(distance)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Extruded {distance}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "revolve",
    "Revolve active sketch around axis by angle_deg. Axis defaults to 'auto' which resolves to sketch plane vertical direction.",
)
def revolve(axis: str = "auto", angle_deg: float = 360.0):
    """Creates an NXOpen Revolve feature from the active sketch curves rotated around an axis.

    Args:
        axis (str): The rotation axis name ('X', 'Y', 'Z') or 'auto' to use the sketch vertical.
        angle_deg (float): The rotation sweep angle in degrees.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    angle_deg = float(angle_deg)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("revolve", {"axis": axis, "angle_deg": angle_deg})
            )
        b = NXSession.work_part().Features.CreateRevolveBuilder(None)
        b.Limits.EndExtend.Value.RightHandSide = str(angle_deg)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Revolved {angle_deg} degrees around {axis}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("boolean_unite", "Unite two solid bodies")
def boolean_unite(target: str, tool: str):
    """Unites two solid bodies into a single body using an NXOpen BooleanBuilder.

    Args:
        target (str): The target body reference name or index string (e.g. 'last' or 'body_1').
        tool (str): The tool body reference name or index string (e.g. 'body_2') to merge into target.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("boolean_unite", {"target": target, "tool": tool})
            )
        nxopen = NXSession.nxopen()
        b = NXSession.work_part().Features.CreateBooleanBuilder(None)
        b.Operation = nxopen.Features.BooleanBuilder.BooleanType.Unite
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"United '{target}' + '{tool}'")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("boolean_subtract", "Subtract tool body from target body")
def boolean_subtract(target: str, tool: str):
    """Subtracts a tool solid body from a target solid body using an NXOpen BooleanBuilder.

    Args:
        target (str): The target body reference name or index string (e.g. 'last' or 'body_1') to keep.
        tool (str): The tool body reference name or index string (e.g. 'body_2') to remove.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("boolean_subtract", {"target": target, "tool": tool})
            )
        nxopen = NXSession.nxopen()
        b = NXSession.work_part().Features.CreateBooleanBuilder(None)
        b.Operation = nxopen.Features.BooleanBuilder.BooleanType.Subtract
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Subtracted '{tool}' from '{target}'")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "add_fillet",
    "Add edge fillet with radius mm to edges (a spatial hint like outer_edges/top_edges/vertical_edges OR a specific prior feature name)",
)
def add_fillet(radius: float, body: str = "last", edges: str = "outer_edges"):
    """Applies a fillet radius to the selected edges of a body using an NXOpen EdgeBlendBuilder.

    Args:
        radius (float): The fillet blend radius in millimeters.
        body (str): The reference name or index string of the target solid body (default 'last').
        edges (str): A spatial hint (outer_edges, top_edges, vertical_edges, etc.) OR the name of a specific prior feature to fillet only that feature's edges.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    radius = float(radius)
    try:
        if radius <= 0:
            return ToolError("Fillet radius must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "add_fillet",
                    {"radius": radius, "body": body, "edges": edges},
                )
            )
        b = NXSession.work_part().Features.CreateEdgeBlendBuilder(None)
        b.Tolerance = 0.01
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Fillet R{radius}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "add_chamfer",
    "Add chamfer with offset mm to edges (a spatial hint like outer_edges/top_edges/vertical_edges OR a specific prior feature name)",
)
def add_chamfer(offset: float, body: str = "last", edges: str = "outer_edges"):
    """Applies a symmetric chamfer to the selected edges of a body using an NXOpen ChamferBuilder.

    Args:
        offset (float): The chamfer distance/offset in millimeters.
        body (str): The reference name or index string of the target solid body (default 'last').
        edges (str): A spatial hint (outer_edges, top_edges, vertical_edges, etc.) OR the name of a specific prior feature to chamfer only that feature's edges.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    offset = float(offset)
    try:
        if offset <= 0:
            return ToolError("Chamfer offset must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "add_chamfer",
                    {"offset": offset, "body": body, "edges": edges},
                )
            )
        b = NXSession.work_part().Features.CreateChamferBuilder(None)
        b.FirstOffset = str(offset)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Chamfer {offset}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "add_hole",
    "Add hole at x y z with diameter and depth in mm on a target body. Direction 'auto' drills into active sketch plane.",
)
def add_hole(
    x: float,
    y: float,
    z: float,
    diameter: float,
    depth: float,
    target: str = "last",
    direction: str = "auto",
    placement_face: str = "top",
):
    """Creates a blind hole feature on a target body using an NXOpen HolePackageBuilder.

    (x, y, z) are absolute 3D coordinates - NOT transformed by the active sketch plane.

    Args:
        x (float): The X coordinate of the hole position in millimeters.
        y (float): The Y coordinate of the hole position in millimeters.
        z (float): The Z coordinate of the hole position in millimeters.
        diameter (float): The diameter of the hole in millimeters.
        depth (float): The depth of the hole in millimeters.
        target (str): The reference name or index string of the target solid body (default 'last').
        direction (str): The drilling axis direction ('X', 'Y', 'Z') or 'auto' to use normal direction.
        placement_face (str): The placement face hint string (e.g. 'top', 'bottom', 'left', 'right').

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    x = float(x)
    y = float(y)
    z = float(z)
    diameter = float(diameter)
    depth = float(depth)
    try:
        if diameter <= 0 or depth <= 0:
            return ToolError("Hole diameter and depth must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "add_hole",
                    {
                        "x": x,
                        "y": y,
                        "z": z,
                        "diameter": diameter,
                        "depth": depth,
                        "target": target,
                        "direction": direction,
                        "placement_face": placement_face,
                    },
                )
            )
        b = NXSession.work_part().Features.CreateHoleBuilder(None)
        b.Diameter.RightHandSide = str(diameter)
        b.Depth.RightHandSide = str(depth)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Hole D={diameter} depth={depth} at ({x},{y},{z})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("mirror_feature", "Mirror a feature across a datum plane")
def mirror_feature(feature_name: str, plane: Literal["XY", "XZ", "YZ"] = "XZ"):
    """Mirrors an existing feature across a datum plane using an NXOpen MirrorFeatureBuilder.

    Args:
        feature_name (str): The reference name of the feature to mirror (e.g. 'extrusion_1').
        plane (str): The plane keyword ('XY', 'XZ', or 'YZ') to mirror across.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "mirror_feature",
                    {"feature_name": feature_name, "plane": plane},
                )
            )
        b = NXSession.work_part().Features.CreateMirrorFeatureBuilder(None)
        b.MirrorPlane = plane
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Mirrored '{feature_name}' about {plane}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "pattern_feature", "Linear pattern: count items spaced pitch mm along direction"
)
def pattern_feature(
    feature_name: str, direction: str = "X", count: int = 3, pitch: float = 10.0
):
    """Creates a linear pattern of a feature using an NXOpen LinearPatternBuilder.

    Args:
        feature_name (str): The reference name of the feature to pattern.
        direction (str): The direction vector axis keyword ('X', 'Y', or 'Z').
        count (int): The total number of pattern instances (must be 2 or more).
        pitch (float): The distance between adjacent patterned instances in millimeters.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    pitch = float(pitch)
    try:
        if count < 2:
            return ToolError("Pattern count must be at least 2")
        if pitch == 0:
            return ToolError("Pattern pitch must be non-zero")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "pattern_feature",
                    {
                        "feature_name": feature_name,
                        "direction": direction,
                        "count": count,
                        "pitch": pitch,
                    },
                )
            )
        b = NXSession.work_part().Features.CreateLinearPatternBuilder(None)
        b.PatternService.PatternCount.RightHandSide = str(count)
        b.PatternService.Pitch.RightHandSide = str(pitch)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(
            f"Pattern '{feature_name}' {count}x @ {pitch}mm along {direction}"
        )
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "edit_expression",
    "Edit a named expression inside the work part and update the model in place",
)
def edit_expression(name: str, value: str):
    """Modifies or updates the value of a named NX parameter expression.

    Args:
        name (str): The exact name of the NX expression to edit.
        value (str): The new value or formula string to assign to the expression.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "edit_expression",
                    {
                        "name": name,
                        "value": value,
                    },
                )
            )
        return ToolResult(f"Expression '{name}' updated to '{value}'")
    except Exception as e:
        return ToolError(str(e))


# ---------------------------------------------------------------------------
# NEW TOOLS (10)
# ---------------------------------------------------------------------------


@mcp_tool("create_real_sketch", "Create a proper constrained NX Sketch object")
def create_real_sketch(
    plane: Literal["XY", "XZ", "YZ"] = "XY",
    z_offset: float = 0.0,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
    rotate_z_deg: float = 0.0,
):
    """Creates a Sketch object on a planar reference face or datum using an NXOpen SketchBuilder.

    Args:
        plane (str): The plane keyword ('XY', 'XZ', or 'YZ') where the sketch is created.
        z_offset (float): Z-axis offset of the sketch plane relative to the WCS origin in millimeters. Defines the plane's origin, not a shape's position.
        origin_x (float): Local X offset for the sketch coordinate system origin in millimeters. Defines the plane's origin, not a shape's position.
        origin_y (float): Local Y offset for the sketch coordinate system origin in millimeters. Defines the plane's origin, not a shape's position.
        rotate_z_deg (float): Rotation angle around the sketch plane normal in degrees. Defines the plane's orientation, not a shape's position.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    z_offset = float(z_offset)
    origin_x = float(origin_x)
    origin_y = float(origin_y)
    rotate_z_deg = float(rotate_z_deg)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_real_sketch",
                    {
                        "plane": plane,
                        "z_offset": z_offset,
                        "origin_x": origin_x,
                        "origin_y": origin_y,
                        "rotate_z_deg": rotate_z_deg,
                    },
                )
            )
        return ToolResult(
            f"Sketch created on {plane} plane with offset z={z_offset} origin=({origin_x},{origin_y}) rotation={rotate_z_deg}"
        )
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "extrude_from_sketch",
    "Extrude a named sketch profile by distance mm along direction. Direction 'auto' extrudes normal to sketch plane.",
)
def extrude_from_sketch(
    distance: float,
    sketch_name: str = "last",
    start: float = 0.0,
    direction: str = "auto",
):
    """Creates an NXOpen Extrude feature from a named sketch using an NXOpen ExtrudeBuilder.

    Args:
        distance (float): The ending limit extrusion distance in millimeters.
        sketch_name (str): The exact name or reference string of the sketch to extrude (default 'last').
        start (float): The starting limit extrusion distance in millimeters.
        direction (str): The direction vector axis keyword ('X', 'Y', 'Z') or 'auto' to use plane normal.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    distance = float(distance)
    try:
        if distance <= 0:
            return ToolError("Extrude distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "extrude_from_sketch",
                    {
                        "sketch_name": sketch_name,
                        "distance": distance,
                        "start": start,
                        "direction": direction,
                    },
                )
            )
        return ToolResult(
            f"Extruded sketch '{sketch_name}' {distance}mm along {direction}"
        )
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "add_hole_nx",
    "Alias for add_hole. Create a simple hole at x y z with diameter and depth. Direction 'auto' drills into active sketch plane.",
)
def add_hole_nx(
    x: float,
    y: float,
    z: float,
    diameter: float,
    depth: float,
    target: str = "last",
    direction: str = "auto",
    hole_type: str = "simple",
):
    """Creates a simple hole feature (alias compatibility function) using an NXOpen HolePackageBuilder.

    (x, y) are 2D coordinates on the ACTIVE SKETCH PLANE and are transformed to 3D automatically. z is used as a raw 3D coordinate, not sketch-plane-relative.

    Args:
        x (float): The X coordinate of the hole center in millimeters.
        y (float): The Y coordinate of the hole center in millimeters.
        z (float): The Z coordinate of the hole center in millimeters.
        diameter (float): The diameter of the hole in millimeters.
        depth (float): The depth of the hole in millimeters.
        target (str): The reference name or index string of the target solid body (default 'last').
        direction (str): The drilling axis direction ('X', 'Y', 'Z') or 'auto' to use normal direction.
        hole_type (str): The type of hole ('simple').

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    x = float(x)
    y = float(y)
    z = float(z)
    diameter = float(diameter)
    depth = float(depth)
    return add_hole(x, y, z, diameter, depth, target, direction)


@mcp_tool(
    "create_rib",
    "Create a rib/web feature from the active sketch profile with a given thickness mm. Direction 'auto' is perpendicular to rib profile plane.",
)
def create_rib(
    thickness: float,
    direction: str = "auto",
    body: str = "last",
    flip: bool = False,
):
    """Creates a solid rib/web support feature from sketch curves using an NXOpen RibBuilder.

    Args:
        thickness (float): The thickness of the rib in millimeters.
        direction (str): The projection direction axis keyword ('X', 'Y', 'Z') or 'auto' for sketch normal.
        body (str): The reference name or index string of the target solid body (default 'last').
        flip (bool): Set to True to flip the projection direction.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    thickness = float(thickness)
    try:
        if thickness <= 0:
            return ToolError("Rib thickness must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_rib",
                    {
                        "thickness": thickness,
                        "direction": direction,
                        "body": body,
                        "flip": flip,
                    },
                )
            )
        return ToolResult(f"Rib T={thickness}mm along {direction}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "pattern_circular",
    "Circular pattern of a feature: count instances evenly spaced over angle_total degrees about axis. Axis 'auto' is normal to active sketch plane.",
)
def pattern_circular(
    feature_name: str,
    axis: str = "auto",
    count: int = 4,
    angle_total: float = 360.0,
):
    """Creates a circular pattern of a feature about a rotational axis using an NXOpen CircularPatternBuilder.

    Rotation axis always passes through the world origin (0,0,0), not through the feature's own position. If the feature is not centered on the origin, it will orbit around (0,0,0) rather than spinning in place.

    Args:
        feature_name (str): The reference name of the feature to pattern.
        axis (str): The rotational axis keyword ('X', 'Y', 'Z') or 'auto' for sketch normal.
        count (int): The total number of patterned instances (must be 2 or more).
        angle_total (float): The total spacing angle in degrees.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    angle_total = float(angle_total)
    try:
        if count < 2:
            return ToolError("Circular pattern count must be at least 2")
        if angle_total == 0:
            return ToolError("angle_total must be non-zero")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "pattern_circular",
                    {
                        "feature_name": feature_name,
                        "axis": axis,
                        "count": count,
                        "angle_total": angle_total,
                    },
                )
            )
        return ToolResult(
            f"Circular pattern '{feature_name}' {count}x over {angle_total}° about {axis}"
        )
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "edge_blend",
    "Fillet edges by selection with a given radius mm (uses outer_edges/vertical_edges/top_edges/bottom_edges/x_aligned_edges/y_aligned_edges/z_aligned_edges/min_z_edges/max_z_edges hints)",
)
def edge_blend(radius: float, body: str = "last", edges: str = "outer_edges"):
    """Applies a fillet blend to selected body edges (alias function) using an NXOpen EdgeBlendBuilder.

    Args:
        radius (float): The blend radius in millimeters.
        body (str): The reference name or index string of the target solid body (default 'last').
        edges (str): The edge selection hint string (e.g. 'outer_edges', 'vertical_edges').

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    radius = float(radius)
    try:
        if radius <= 0:
            return ToolError("Edge blend radius must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "edge_blend",
                    {"radius": radius, "body": body, "edges": edges},
                )
            )
        return ToolResult(f"Edge blend R{radius}mm on {edges}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "chamfer",
    "Chamfer edges by selection with a given offset mm (uses outer_edges/vertical_edges/top_edges/bottom_edges/x_aligned_edges/y_aligned_edges/z_aligned_edges/min_z_edges/max_z_edges hints)",
)
def chamfer(offset: float, body: str = "last", edges: str = "outer_edges"):
    """Applies a chamfer to selected body edges (alias function) using an NXOpen ChamferBuilder.

    Args:
        offset (float): The chamfer offset/distance in millimeters.
        body (str): The reference name or index string of the target solid body (default 'last').
        edges (str): The edge selection hint string (e.g. 'outer_edges', 'vertical_edges').

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    offset = float(offset)
    try:
        if offset <= 0:
            return ToolError("Chamfer offset must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "chamfer_edges",
                    {"offset": offset, "body": body, "edges": edges},
                )
            )
        return ToolResult(f"Chamfer {offset}mm on {edges}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "revolve_cut",
    "Revolve the active sketch profile around axis by angle_deg to cut/remove material from target body. Axis 'auto' is sketch plane vertical direction.",
)
def revolve_cut(axis: str = "auto", angle_deg: float = 360.0, target: str = "last"):
    """Revolves active sketch curves to subtract material from a target solid body using an NXOpen RevolveBuilder.

    Args:
        axis (str): The rotation axis name ('X', 'Y', 'Z') or 'auto' to use sketch vertical.
        angle_deg (float): The sweep rotation angle in degrees.
        target (str): The reference name or index string of the target solid body (default 'last').

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    angle_deg = float(angle_deg)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "revolve_cut",
                    {"axis": axis, "angle_deg": angle_deg, "target": target},
                )
            )
        return ToolResult(f"Revolve-cut {angle_deg}° about {axis}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "extrude_cut",
    "Extrude the active sketch profile by distance mm to cut/remove material from an existing body. Direction 'auto' extrudes normal to sketch plane.",
)
def extrude_cut(
    distance: float,
    start: float = 0.0,
    target: str = "last",
    direction: str = "auto",
):
    """Extrudes active sketch curves to subtract material from a target solid body using an NXOpen ExtrudeBuilder.

    Args:
        distance (float): The ending limit extrusion cut distance in millimeters.
        start (float): The starting limit extrusion cut distance in millimeters.
        target (str): The reference name or index string of the target solid body (default 'last').
        direction (str): The direction vector axis keyword ('X', 'Y', 'Z') or 'auto' to use plane normal.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    distance = float(distance)
    try:
        if distance <= 0:
            return ToolError("Extrude-cut distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "extrude_cut",
                    {
                        "distance": distance,
                        "start": start,
                        "target": target,
                        "direction": direction,
                    },
                )
            )
        return ToolResult(f"Extrude-cut {distance}mm from '{target}' along {direction}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "mirror_body_feature",
    "Mirror a feature about a plane (XY/XZ/YZ) — same as mirror_feature but with intent-specific name",
)
def mirror_body_feature(feature_name: str, plane: str = "XZ"):
    """Mirrors a body feature across a datum plane (alias function) using an NXOpen MirrorFeatureBuilder.

    Args:
        feature_name (str): The reference name of the feature to mirror.
        plane (str): The plane keyword ('XY', 'XZ', or 'YZ') to mirror across.

    Returns:
        ToolResult or ToolError: A success message or failure explanation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "mirror_feature",
                    {"feature_name": feature_name, "plane": plane},
                )
            )
        return ToolResult(f"Mirrored '{feature_name}' about {plane}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "create_gear",
    "Builds a full parametric spur gear: outer_diameter, tooth_count, face_width, hub_diameter, hub_length, bore_diameter, lightening_hole_diameter, lightening_hole_pcd, lightening_hole_count",
)
def create_gear(
    outer_diameter: float,
    tooth_count: int,
    face_width: float,
    hub_diameter: float,
    hub_length: float,
    bore_diameter: float,
    lightening_hole_diameter: float,
    lightening_hole_pcd: float,
    lightening_hole_count: int,
):
    """Builds a full parametric spur gear with teeth, hub, bore, and circular lightening holes.
    
    All inputs are mapped to NX expressions, making the model parametric and dynamically adjustable inside NX.

    Args:
        outer_diameter (float): The outer/addendum tip diameter of the gear in mm.
        tooth_count (int): The total number of gear teeth.
        face_width (float): The thickness/width of the gear face in mm.
        hub_diameter (float): The diameter of the central coaxial hub in mm.
        hub_length (float): The length/extension height of the hub from the gear face in mm.
        bore_diameter (float): The diameter of the central hole through the gear in mm.
        lightening_hole_diameter (float): The diameter of the lightening holes in mm.
        lightening_hole_pcd (float): Pitch Circle Diameter (PCD) / bolt circle diameter for lightening holes in mm.
        lightening_hole_count (int): The number of lightening holes in the circular pattern.

    Returns:
        ToolResult or ToolError: Confirmation message.
    """
    outer_diameter = float(outer_diameter)
    tooth_count = int(tooth_count)
    face_width = float(face_width)
    hub_diameter = float(hub_diameter)
    hub_length = float(hub_length)
    bore_diameter = float(bore_diameter)
    lightening_hole_diameter = float(lightening_hole_diameter)
    lightening_hole_pcd = float(lightening_hole_pcd)
    lightening_hole_count = int(lightening_hole_count)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_gear",
                    {
                        "outer_diameter": outer_diameter,
                        "tooth_count": tooth_count,
                        "face_width": face_width,
                        "hub_diameter": hub_diameter,
                        "hub_length": hub_length,
                        "bore_diameter": bore_diameter,
                        "lightening_hole_diameter": lightening_hole_diameter,
                        "lightening_hole_pcd": lightening_hole_pcd,
                        "lightening_hole_count": lightening_hole_count,
                    },
                ),
                auto_open=True
            )
        return ToolResult(
            f"Created spur gear with {tooth_count} teeth, OD={outer_diameter}mm, face={face_width}mm (mock mode)"
        )
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "extrude_profile",
    "Extrude a profile by profile_id with distance, direction, and optional boolean operation.",
)
def extrude_profile(
    profile_id: str = "last",
    distance: float = 10.0,
    start: float = 0.0,
    direction: str = "auto",
    boolean: Literal["none", "unite", "subtract", "intersect"] = "none",
    target: str = None,
):
    """Extrudes an existing 2D profile into a 3D solid feature.

    Args:
        profile_id (str): Identifier of the profile (e.g. 'profile_1', 'last').
        distance (float): Extrusion distance in millimeters.
        start (float): Extrusion start offset in millimeters (default 0.0).
        direction (str): Extrusion direction vector ('auto', 'X', 'Y', 'Z', '-Z', etc.).
        boolean (str): Optional boolean operation against target body ('none', 'unite', 'subtract', 'intersect').
        target (str): Target body identifier (e.g. 'body_1', 'last').

    Returns:
        ToolResult or ToolError: Result containing the body_id and feature_id.
    """
    try:
        distance = float(distance)
        start = float(start)
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "extrude_profile",
                    {
                        "profile_id": profile_id,
                        "distance": distance,
                        "start": start,
                        "direction": direction,
                        "boolean": boolean,
                        "target": target,
                    },
                )
            )
        return ToolResult(f"Extruded profile '{profile_id}' {distance}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "loft",
    "Create a solid loft / through-curves feature through an ordered list of profile sections.",
)
def loft(
    profile_ids: list,
    guide_curve_ids: list = None,
    body_type: Literal["solid", "sheet"] = "solid",
):
    """Creates a loft / through-curves feature through an ordered list of profiles.

    Args:
        profile_ids (list): Ordered list of profile identifiers (e.g. ['profile_1', 'profile_2']).
        guide_curve_ids (list): Optional list of guide curve identifiers.
        body_type (str): Output geometry type ('solid' or 'sheet').

    Returns:
        ToolResult or ToolError: Result containing the body_id and feature_id.
    """
    try:
        if not isinstance(profile_ids, list) or len(profile_ids) < 2:
            return ToolError("loft requires a list of at least 2 profile_ids")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "loft",
                    {
                        "profile_ids": profile_ids,
                        "guide_curve_ids": guide_curve_ids,
                        "body_type": body_type,
                    },
                )
            )
        return ToolResult(f"Lofted through {len(profile_ids)} profiles")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "pattern",
    "Unified pattern feature supporting both linear and circular modes.",
)
def pattern(
    feature_ref: str = "last",
    mode: Literal["linear", "circular"] = "linear",
    count: int = 4,
    pitch: float = 10.0,
    angle_total: float = 360.0,
    axis: str = "Z",
    direction: str = "X",
):
    """Creates a linear or circular pattern of a target feature.

    Args:
        feature_ref (str): Target feature to pattern (e.g. 'feature_1', 'last').
        mode (str): Pattern mode ('linear' or 'circular').
        count (int): Number of pattern instances (>= 2).
        pitch (float): Pitch distance in mm (for linear mode).
        angle_total (float): Total angle in degrees (for circular mode).
        axis (str): Rotational axis for circular mode ('X', 'Y', 'Z', 'auto').
        direction (str): Translation direction for linear mode ('X', 'Y', 'Z').

    Returns:
        ToolResult or ToolError: Result containing feature_id and body_ids.
    """
    try:
        count = int(count)
        if count < 2:
            return ToolError("Pattern count must be at least 2")
        pitch = float(pitch)
        angle_total = float(angle_total)
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "pattern",
                    {
                        "feature_ref": feature_ref,
                        "mode": mode,
                        "count": count,
                        "pitch": pitch,
                        "angle_total": angle_total,
                        "axis": axis,
                        "direction": direction,
                    },
                )
            )
        return ToolResult(f"Patterned feature '{feature_ref}' ({mode} mode, {count}x)")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "delete_body",
    "Delete a body and its associated geometry by body_id or 'last'",
)
def delete_body(body_id: str = "last"):
    """Deletes a solid or sheet body from the active part.

    Args:
        body_id (str): The identifier of the body to delete (e.g. 'body_1', or 'last'). Defaults to 'last'.

    Returns:
        ToolResult or ToolError: Confirmation message or error explanation.
    """
    body_id = str(body_id or "last").strip()
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("delete_body", {"body_id": body_id})
            )
        # Mock implementation
        wp = NXSession.work_part()
        if hasattr(wp, "Bodies") and wp.Bodies:
            wp.Bodies.pop()
        return ToolResult(f"Deleted body {body_id}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "delete_feature",
    "Delete a feature from the active part feature tree by feature_id or 'last'",
)
def delete_feature(feature_id: str = "last"):
    """Deletes a feature from the active part feature tree.

    Args:
        feature_id (str): The identifier or name of the feature to delete (e.g. 'feature_1', 'BLOCK(1)', or 'last'). Defaults to 'last'.

    Returns:
        ToolResult or ToolError: Confirmation message or error explanation.
    """
    feature_id = str(feature_id or "last").strip()
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("delete_feature", {"feature_id": feature_id})
            )
        # Mock implementation
        wp = NXSession.work_part()
        if hasattr(wp, "Features") and hasattr(wp.Features, "ToArray"):
            feats = list(wp.Features.ToArray())
            if feats:
                pass
        return ToolResult(f"Deleted feature {feature_id}")
    except Exception as e:
        return ToolError(str(e))



