import os

from ..bridge import runner
from ..nx_session import NXSession
from ..response import ToolError, ToolResult
from ..tools.registry import mcp_tool
from nx_mcp.tools._common import _bridge_result, _use_mock_nxopen




@mcp_tool("set_view", "Set viewport to TOP / FRONT / RIGHT / ISO")
def set_view(view_name: str = "ISO"):
    """
    Set viewport to TOP / FRONT / RIGHT / ISO.

    Args:
        view_name (str): Parameter view_name.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    valid = {"TOP", "FRONT", "RIGHT", "BACK", "LEFT", "BOTTOM", "ISO"}
    view_name = view_name.upper()
    if view_name not in valid:
        return ToolError(f"Invalid view '{view_name}'. Choose: {', '.join(valid)}")
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("set_view", {"view_name": view_name}))
        NXSession.ui().ModelingViews.WorkView.Orient(view_name)
        return ToolResult(f"View set to {view_name}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("fit_view", "Fit model to fill the NX viewport")
def fit_view():
    """
    Fit model to fill the NX viewport.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("fit_view", {}))
        NXSession.ui().ModelingViews.WorkView.Fit()
        return ToolResult("View fitted")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("reset_nx_bridge", "Restart the live NX automation bridge")
def reset_nx_bridge():
    """
    Restart the live NX automation bridge.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        runner.reset_nx_bridge()
        return ToolResult("NX bridge reset")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("take_screenshot", "Save viewport screenshot to PNG")
def take_screenshot(output_path: str = "screenshot.png", filepath: str = None, filename: str = None):
    """
    Save viewport screenshot to PNG.

    Args:
        output_path (str): Path to save the PNG image.
        filepath (str): Optional alias for output_path.
        filename (str): Optional alias for output_path.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    target_path = output_path or filepath or filename or "screenshot.png"
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("take_screenshot", {"output_path": target_path})
            )
        NXSession.ui().ModelingViews.WorkView.SaveImage(target_path, 1920, 1080)
        return ToolResult(f"Screenshot saved: {target_path}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("list_features", "List all features in the part feature tree")
def list_features():
    """
    List all features in the part feature tree.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("list_features", {}))
        features = NXSession.work_part().Features.ToArray()
        names = [f.GetFeatureName() for f in features] if features else []
        return ToolResult("Features: " + (", ".join(names) if names else "none"))
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("get_active_part", "Returns identity/state of the currently active NX work part")
def get_active_part():
    """
    Returns identity/state of the currently active NX work part.

    Returns:
        ToolResult: Information about the active part.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("get_active_part", {}))
        
        work_part = NXSession.work_part()
        if work_part is None:
            return ToolResult("No active part in session")
            
        comps = 0
        try:
            if hasattr(work_part, "ComponentAssembly") and work_part.ComponentAssembly and work_part.ComponentAssembly.RootComponent:
                comps = len(work_part.ComponentAssembly.RootComponent.GetChildren())
        except:
            pass
            
        try:
            full_path = work_part.FullPath
        except:
            try:
                full_path = work_part.FullName
            except:
                full_path = "Unknown (Unsaved)"
                
        try:
            leaf_name = work_part.Leaf
        except:
            leaf_name = "Unknown"
            
        try:
            is_mod = work_part.IsModified
        except:
            is_mod = "Unknown"
            
        msg = (
            f"Active part = {full_path}\n"
            f"Display name = {leaf_name}\n"
            f"Modified = {is_mod}\n"
            f"Components = {comps}"
        )
        return ToolResult(msg)
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("get_last_operation_status", "Returns the status of the last operation or feature applied")
def get_last_operation_status():
    """
    Returns the status of the last operation or feature applied to the part.

    Returns:
        ToolResult: Information about the last operation.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("get_last_operation_status", {}))
            
        work_part = NXSession.work_part()
        if work_part is None:
            return ToolResult("No active part in session")
            
        features = list(work_part.Features.ToArray() or [])
        if not features:
            return ToolResult("No features in active part")
            
        last_feat = features[-1]
        try:
            feat_name = last_feat.GetFeatureName()
        except:
            feat_name = str(last_feat)
            
        return ToolResult(f"Last feature created/modified: {feat_name}\nStatus: OK")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("run_nx_journal_code", "Execute a complete NXOpen Python script inside the active NX session")
def run_nx_journal_code(python_code: str, description: str = "Dynamic NXOpen script"):
    """
    Executes a complete, self-contained Python script inside the active NX session.
    USE THIS INSTEAD OF low-level tools (draw_line, extrude) for complex geometry
    like gears, splines, or mathematical surfaces.

    The script has access to these pre-injected variables:
    - NXOpen (Main API)
    - SESSION (NXOpen.Session)
    - UF_SESSION (NXOpen.UF)
    - work_part (Active NXOpen.Part)
    - math (Python math library)
    - Point3d, Vector3d

    Args:
        python_code (str): Complete Python script using the NXOpen API.
        description (str): Human-readable description of what the script does.

    Returns:
        ToolResult: A confirmation message of the operation.
    """
    if not python_code or not python_code.strip():
        return ToolError("python_code cannot be empty")

    return _bridge_result(
        runner.call_nx("exec_python_code", {"code": python_code, "desc": description})
    )


@mcp_tool("inspect_part", "Inspect features, bodies, expressions, and sketches in the active part")
def inspect_part():
    """
    Inspect features, bodies, expressions, and sketches in the active part.

    Returns:
        ToolResult: Part inspection details.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("inspect_part", {}))
        return ToolResult("Mock inspect_part: 0 features, 0 bodies, 0 expressions")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("create_expression", "Create a named expression driving model parameters")
def create_expression(name: str, value: float):
    """
    Create a named expression driving model parameters.

    :param name: Name of the expression, e.g. LENGTH or WIDTH.
    :param value: Numeric value for the expression.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_expression", {"name": name, "value": value}
                )
            )
        return ToolResult(f"Expression {name} = {value} created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("list_expressions", "List all expressions in the active part")
def list_expressions():
    """
    List all expressions in the active part.

    Returns:
        ToolResult: Dictionary of expressions and their values.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("list_expressions", {}))
        return ToolResult("Expressions: none")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("inspect_api", "Inspect methods on NXOpen API objects")
def inspect_api(target: str = "work_part", callable_only: bool = True):
    """
    Inspect methods on NXOpen API objects.

    :param target: API target path, e.g. work_part, SESSION, NXOpen, work_part.Features.
    :param callable_only: Whether to filter for callable methods only.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "inspect_api", {"target": target, "callable_only": callable_only}
                )
            )
        return ToolResult(f"Mock inspect_api: target {target}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "list_feature_edges",
    "List edge count and edge tags for a specific named feature",
)
def list_feature_edges(feature_name: str):
    """
    Returns the edge count and edge tags tracked for a named feature.

    :param feature_name: The name or identifier of the feature (e.g. 'cylinder_1', 'extrude_2').
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("list_feature_edges", {"feature_name": feature_name})
            )
        return ToolResult(f"Mock list_feature_edges: feature '{feature_name}'")
    except Exception as e:
        return ToolError(str(e))

