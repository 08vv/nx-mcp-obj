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


@mcp_tool("add_component", "Add a component part into assembly at (x,y,z)")
def add_component(part_path: str, x: float = 0.0, y: float = 0.0, z: float = 0.0):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("add_component", {"part_path": part_path, "x": x, "y": y, "z": z}))
        b = NXSession.work_part().AssemblyManager.CreateAddComponentBuilder()
        b.ReferenceSet = "MODEL"
        b.Commit(); b.Destroy()
        return ToolResult(f"Added '{part_path}' at ({x},{y},{z})")
    except Exception as e: return ToolError(str(e))

@mcp_tool("list_components", "List all components in the current assembly")
def list_components():
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("list_components", {}))
        comps = NXSession.work_part().ComponentAssembly.RootComponent.GetChildren()
        names = [c.DisplayName for c in comps] if comps else []
        return ToolResult("Components: " + (", ".join(names) if names else "none"))
    except Exception as e: return ToolError(str(e))

@mcp_tool("mate_components", "Add a constraint between two component faces")
def mate_components(comp1: str, face1: str, comp2: str, face2: str, constraint_type: str = "Coincident"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("mate_components", {
                "comp1": comp1, "face1": face1, "comp2": comp2, "face2": face2, "constraint_type": constraint_type
            }))
        b = NXSession.work_part().AssemblyManager.CreateAssemblyConstraintBuilder()
        b.ConstraintType = constraint_type
        b.Commit(); b.Destroy()
        return ToolResult(f"{constraint_type}: {comp1}.{face1} ↔ {comp2}.{face2}")
    except Exception as e: return ToolError(str(e))

@mcp_tool("reposition_component", "Move a component to absolute position (x,y,z)")
def reposition_component(component_name: str, x: float, y: float, z: float):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("reposition_component", {
                "component_name": component_name, "x": x, "y": y, "z": z
            }))
        b = NXSession.work_part().AssemblyManager.CreateRepositionBuilder(None)
        b.TranslationX = x; b.TranslationY = y; b.TranslationZ = z
        b.Commit(); b.Destroy()
        return ToolResult(f"Repositioned '{component_name}' to ({x},{y},{z})")
    except Exception as e: return ToolError(str(e))