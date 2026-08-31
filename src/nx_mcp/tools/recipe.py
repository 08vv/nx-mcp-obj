"""Recipe tool for executing a sequence of tool calls server-side."""

from typing import Any, Dict, List, Optional, Union
from ..response import ToolError, ToolResult
from .registry import ToolRegistry, mcp_tool


def _is_step_success(res: Any) -> bool:
    if isinstance(res, ToolResult) or type(res).__name__ == "ToolResult":
        return True
    if isinstance(res, ToolError) or type(res).__name__ == "ToolError":
        return False
    if hasattr(res, "is_ok") and callable(getattr(res, "is_ok")):
        return bool(res.is_ok())
    if isinstance(res, dict):
        return bool(res.get("ok", True))
    if isinstance(res, str):
        return not res.startswith("ERROR")
    return True


@mcp_tool("run_recipe", "Execute a sequence of tool calls in order on the server")
def run_recipe(steps: List[Dict[str, Any]], stop_on_error: bool = True):
    """
    Execute a sequence of tool calls in order on the server.

    :param steps: A JSON array of step objects. Each step must have a "tool" key
        (the tool name) and an optional "args" key (a dict of arguments).
        Example: [{"tool": "create_cuboid", "args": {"length": 100, "width": 50, "height": 30}},
                  {"tool": "add_fillet", "args": {"radius": 2.0}}]
    :param stop_on_error: Whether to stop execution on the first step failure.
    """
    if not isinstance(steps, list):
        return {"ok": False, "completed": [], "failed_step": 0, "error": "steps must be a list"}

    completed = []
    failed_step = None
    last_error = None

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            failed_step = i
            last_error = f"Step {i} must be a dictionary"
            completed.append({"step": i, "tool": "unknown", "result": last_error})
            if stop_on_error:
                break
            continue

        tool_name = step.get("tool")
        args = step.get("args", {}) or {}

        if tool_name == "run_recipe":
            failed_step = i
            last_error = "Recursive call to 'run_recipe' is not allowed"
            completed.append({"step": i, "tool": tool_name, "result": last_error})
            if stop_on_error:
                break
            continue

        tool_entry = ToolRegistry.get(tool_name)
        if not tool_entry:
            failed_step = i
            last_error = f"Unknown tool: {tool_name}"
            completed.append({"step": i, "tool": tool_name, "result": last_error})
            if stop_on_error:
                break
            continue

        try:
            res = tool_entry["fn"](**args)
            step_res = str(res) if isinstance(res, (ToolResult, ToolError)) else res
            completed.append({"step": i, "tool": tool_name, "result": step_res})

            if not _is_step_success(res):
                failed_step = i
                last_error = str(res)
                if stop_on_error:
                    break
        except Exception as e:
            failed_step = i
            last_error = str(e)
            completed.append({"step": i, "tool": tool_name, "result": f"Error: {e}"})
            if stop_on_error:
                break

    if failed_step is not None:
        return {
            "ok": False,
            "completed": completed,
            "failed_step": failed_step,
            "error": last_error,
        }
    return {
        "ok": True,
        "completed": completed,
        "failed_step": None,
        "error": None,
    }


@mcp_tool("run_spec", "Execute a validated CAD Spec operation graph DAG with symbolic reference resolution")
def run_spec(
    spec: Dict[str, Any],
    stop_on_error: bool = True,
    validate_plausibility: bool = True,
    verify_postexecution: bool = True,
    pause_after: Optional[Union[List[str], str]] = None,
):
    """
    Execute a validated CAD Spec operation graph DAG with symbolic reference resolution.

    :param spec: A CAD Spec dictionary containing 'part_name', 'units', and 'nodes' list.
        Nodes support symbolic parameter references (e.g. '$n1.body_id') which resolve
        dynamically as upstream operations complete.
    :param stop_on_error: Whether to abort graph execution on the first node failure (default True).
    :param validate_plausibility: Whether to run pre-execution physical/geometric plausibility validation (default True).
    :param verify_postexecution: Whether to run post-execution geometry & graph verification (default True).
    :param pause_after: List of node IDs or 'every_node' to pause execution after specified nodes (default None).
    """
    try:
        from ..spec.executor import execute_spec
        report = execute_spec(
            spec,
            stop_on_error=stop_on_error,
            validate_plausibility=validate_plausibility,
            verify_postexecution=verify_postexecution,
            pause_after=pause_after,
        )
        if report.get("status") == "paused":
            return ToolResult(
                f"CAD Spec '{report.get('part_name')}' paused after node '{report.get('paused_node')}'. "
                f"Execution token: '{report.get('execution_token')}'. "
                f"Use resume_spec('{report.get('execution_token')}') to continue."
            )
        elif report.get("ok"):
            postcheck = report.get("postcheck_report") or {}
            post_valid = postcheck.get("valid", True)
            return ToolResult(
                f"CAD Spec '{report.get('part_name')}' executed successfully "
                f"({len(report.get('executed_nodes', []))} nodes completed). "
                f"Plausibility: PASSED. Post-check: {'VALID' if post_valid else 'VIOLATIONS DETECTED'}"
            )
        else:
            return ToolError(
                f"CAD Spec failed at node '{report.get('failed_node')}': {report.get('failure_error')}"
            )
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("resume_spec", "Resume execution of a paused CAD Spec graph using its execution token")
def resume_spec(
    execution_token: str,
    pause_after: Optional[Union[List[str], str]] = None,
    stop_on_error: bool = True,
    verify_postexecution: bool = True,
):
    """
    Resume execution of a previously paused CAD Spec graph.

    :param execution_token: The token returned when execution was paused.
    :param pause_after: Optional node ID(s) or 'every_node' to pause at a subsequent step.
    :param stop_on_error: Whether to abort on failure (default True).
    :param verify_postexecution: Whether to verify geometry on completion (default True).
    """
    try:
        from ..spec.executor import resume_spec_execution
        report = resume_spec_execution(
            execution_token,
            pause_after=pause_after,
            stop_on_error=stop_on_error,
            verify_postexecution=verify_postexecution,
        )
        if report.get("status") == "paused":
            return ToolResult(
                f"CAD Spec '{report.get('part_name')}' paused after node '{report.get('paused_node')}'. "
                f"Execution token: '{report.get('execution_token')}'. "
                f"Use resume_spec('{report.get('execution_token')}') to continue."
            )
        elif report.get("ok"):
            postcheck = report.get("postcheck_report") or {}
            post_valid = postcheck.get("valid", True)
            return ToolResult(
                f"CAD Spec '{report.get('part_name')}' resumed and completed successfully "
                f"({len(report.get('executed_nodes', []))} nodes completed). "
                f"Post-check: {'VALID' if post_valid else 'VIOLATIONS DETECTED'}"
            )
        else:
            return ToolError(
                f"CAD Spec failed at node '{report.get('failed_node')}': {report.get('failure_error')}"
            )
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("rerun_spec_node", "Selectively re-run a node and its downstream dependents with updated parameters")
def rerun_spec_node(
    execution_token: str,
    node_id: str,
    new_params: Optional[Dict[str, Any]] = None,
    pause_after: Optional[Union[List[str], str]] = None,
    stop_on_error: bool = True,
    verify_postexecution: bool = True,
):
    """
    Selectively re-run a node and its downstream dependents in an active execution session.

    :param execution_token: The token returned when execution was paused.
    :param node_id: The ID of the node to re-run with new parameters.
    :param new_params: Optional dictionary of updated parameters for the node.
    :param pause_after: Optional node ID(s) to pause at a subsequent step.
    :param stop_on_error: Whether to abort on failure (default True).
    :param verify_postexecution: Whether to verify geometry on completion (default True).
    """
    try:
        from ..spec.executor import rerun_spec_node as run_rerun
        report = run_rerun(
            execution_token,
            node_id=node_id,
            new_params=new_params,
            pause_after=pause_after,
            stop_on_error=stop_on_error,
            verify_postexecution=verify_postexecution,
        )
        if report.get("status") == "paused":
            return ToolResult(
                f"CAD Spec '{report.get('part_name')}' re-run node '{node_id}' and paused after '{report.get('paused_node')}'. "
                f"Execution token: '{report.get('execution_token')}'."
            )
        elif report.get("ok"):
            postcheck = report.get("postcheck_report") or {}
            post_valid = postcheck.get("valid", True)
            return ToolResult(
                f"CAD Spec '{report.get('part_name')}' re-run node '{node_id}' and completed successfully "
                f"({len(report.get('executed_nodes', []))} nodes completed). "
                f"Post-check: {'VALID' if post_valid else 'VIOLATIONS DETECTED'}"
            )
        else:
            return ToolError(
                f"CAD Spec re-run failed at node '{report.get('failed_node')}': {report.get('failure_error')}"
            )
    except Exception as e:
        return ToolError(str(e))



