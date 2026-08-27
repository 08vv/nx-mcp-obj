import os

from ..bridge import runner
from ..nx_session import NXSession
from ..response import ToolError, ToolResult
from ..tools.registry import mcp_tool
from nx_mcp.tools._common import _bridge_result, _use_mock_nxopen




@mcp_tool("add_component", "Add a component part into assembly at (x,y,z)")
def add_component(part_path: str, x: float = 0.0, y: float = 0.0, z: float = 0.0):
    """Adds a component part into the current assembly at the specified absolute coordinates.

    (x, y, z) is the absolute world-coordinate position.

    Args:
        part_path (str): The file path to the part to be added as a component.
        x (float): The absolute X coordinate for insertion in millimeters.
        y (float): The absolute Y coordinate for insertion in millimeters.
        z (float): The absolute Z coordinate for insertion in millimeters.

    Returns:
        ToolResult: A confirmation message with the part path and coordinates.
    """
    x = float(x)
    y = float(y)
    z = float(z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "add_component", {"part_path": part_path, "x": x, "y": y, "z": z}
                )
            )
        b = NXSession.work_part().AssemblyManager.CreateAddComponentBuilder()
        b.ReferenceSet = "MODEL"
        b.Commit()
        b.Destroy()
        return ToolResult(f"Added '{part_path}' at ({x},{y},{z})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("list_components", "List all components in the current assembly")
def list_components():
    """
    Lists all components present in the current assembly's root component.

    Returns:
        ToolResult: A comma-separated list of component display names, or 'none' if empty.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("list_components", {}))
        comps = NXSession.work_part().ComponentAssembly.RootComponent.GetChildren()
        names = [c.DisplayName for c in comps] if comps else []
        return ToolResult("Components: " + (", ".join(names) if names else "none"))
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("mate_components", "Add a constraint between two component faces")
def mate_components(
    comp1: str, face1: str, comp2: str, face2: str, constraint_type: str = "Coincident"
):
    """
    Adds an assembly constraint between faces of two different components.

    Args:
        comp1 (str): The name or identifier of the first component.
        face1 (str): The name or identifier of the face on the first component.
        comp2 (str): The name or identifier of the second component.
        face2 (str): The name or identifier of the face on the second component.
        constraint_type (str): The type of constraint to apply (e.g., 'Coincident', 'Concentric').

    Returns:
        ToolResult: A confirmation message detailing the constraint created.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "mate_components",
                    {
                        "comp1": comp1,
                        "face1": face1,
                        "comp2": comp2,
                        "face2": face2,
                        "constraint_type": constraint_type,
                    },
                )
            )
        b = NXSession.work_part().AssemblyManager.CreateAssemblyConstraintBuilder()
        b.ConstraintType = constraint_type
        b.Commit()
        b.Destroy()
        return ToolResult(f"{constraint_type}: {comp1}.{face1} ↔ {comp2}.{face2}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("reposition_component", "Move a component to absolute position (x,y,z)")
def reposition_component(component_name: str, x: float, y: float, z: float):
    """Moves an existing component in the assembly to the specified absolute coordinates.

    (x, y, z) is the absolute world-coordinate position.

    Args:
        component_name (str): The display name of the component to move.
        x (float): The new absolute X coordinate in millimeters.
        y (float): The new absolute Y coordinate in millimeters.
        z (float): The new absolute Z coordinate in millimeters.

    Returns:
        ToolResult: A confirmation message indicating the new position.
    """
    x = float(x)
    y = float(y)
    z = float(z)
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "reposition_component",
                    {"component_name": component_name, "x": x, "y": y, "z": z},
                )
            )
        b = NXSession.work_part().AssemblyManager.CreateRepositionBuilder(None)
        b.TranslationX = x
        b.TranslationY = y
        b.TranslationZ = z
        b.Commit()
        b.Destroy()
        return ToolResult(f"Repositioned '{component_name}' to ({x},{y},{z})")
    except Exception as e:
        return ToolError(str(e))
