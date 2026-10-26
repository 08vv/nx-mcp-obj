import json
import logging
import os
import sys

from nx_mcp.tools import (
    assembly,
    combine_operations,  # noqa
    edit_operations,
    file_ops,
    measure,
    modeling,
    sketch,
    surface_modeling,
    utility,
    discovery,
    recipe,
    state_tools,
    mesh_tools,
)
from nx_mcp.tools.registry import ToolRegistry

logging.basicConfig(
    level=logging.DEBUG, stream=sys.stderr, format="[nx-mcp] %(levelname)s %(message)s"
)
log = logging.getLogger("nx-mcp")


_session_state = {
    "active_routed_tool_names": None,
    "escape_hatch_active": False,
    "task_prompt": None,
}


def ok(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def err(id_, c, msg):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": c, "message": msg}}


def handle(req):
    id_ = req.get("id")
    method = req.get("method", "")
    params = req.get("params", {})
    log.debug(f"→ {method}")

    if method == "initialize":
        _session_state["active_routed_tool_names"] = None
        _session_state["escape_hatch_active"] = False
        _session_state["task_prompt"] = None
        return ok(
            id_,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "nx-mcp", "version": "0.1.0"},
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        enable_routing = os.environ.get("NX_MCP_ENABLE_ROUTING") == "1"
        prompt = (
            params.get("prompt")
            or params.get("query")
            or os.environ.get("NX_MCP_TASK_PROMPT")
            or _session_state["task_prompt"]
        )

        if prompt:
            _session_state["task_prompt"] = prompt

        all_tools = ToolRegistry.list_tools()

        if _session_state["escape_hatch_active"]:
            log.info(
                f"ROUTED: escape hatch active, returning all {len(all_tools)} tools"
            )
            _session_state["active_routed_tool_names"] = {
                t["name"] for t in all_tools
            }
            return ok(id_, {"tools": all_tools})

        if enable_routing and prompt:
            from nx_mcp.router import route

            routed = route(prompt)
            matched_names = set()
            for cat in routed["categories"]:
                matched_names.update(cat["tools"])

            is_fallback = routed.get("is_fallback", False)
            if is_fallback:
                filtered_tools = all_tools
            else:
                filtered_tools = [
                    t
                    for t in all_tools
                    if t["name"] in matched_names
                    or t["name"] == "get_relevant_nx_tools"
                ]

            _session_state["active_routed_tool_names"] = {
                t["name"] for t in filtered_tools
            }
            categories_str = ", ".join(c["name"] for c in routed["categories"])
            log.info(
                f"ROUTED: prompt=\"{prompt[:50]}\", "
                f"categories=[{categories_str}], "
                f"tools={len(filtered_tools)}/{len(all_tools)}, "
                f"is_fallback={is_fallback}"
            )
            return ok(id_, {"tools": filtered_tools})
        else:
            _session_state["active_routed_tool_names"] = {
                t["name"] for t in all_tools
            }
            return ok(id_, {"tools": all_tools})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        tool = ToolRegistry.get(name)
        if not tool:
            return err(id_, -32601, f"Unknown tool: {name}")

        active_names = _session_state["active_routed_tool_names"]
        if active_names is not None and name not in active_names:
            _session_state["escape_hatch_active"] = True
            log.info(
                f"ESCAPE HATCH TRIGGERED: Tool '{name}' called outside active routed subset. Re-exposing all {len(ToolRegistry.all())} tools."
            )

        try:
            result = tool["fn"](**args)
            return ok(id_, {"content": [{"type": "text", "text": str(result)}]})
        except TypeError as e:
            return err(id_, -32602, f"Bad args for '{name}': {e}")
        except Exception as e:
            return err(id_, -32603, f"Error in '{name}': {e}")

    return err(id_, -32601, f"Unknown method: {method}")


def _check_or_prewarm_nx():
    try:
        from nx_mcp.bridge import runner
        s = runner.try_connect_socket(runner.LIVE_PORT)
        if s is not None:
            s.close()
            sys.stderr.write(
                f"[NX-MCP] Siemens NX bridge is connected and ready on port {runner.LIVE_PORT}.\n"
            )
            sys.stderr.flush()
            return

        sys.stderr.write(
            f"[NX-MCP] Siemens NX interactive bridge is not running on port {runner.LIVE_PORT}.\n"
        )
        if os.environ.get("NX_MCP_AUTO_LAUNCH", "1") == "1":
            sys.stderr.write(
                "[NX-MCP] Auto-launching Siemens NX session in the background...\n"
            )
            sys.stderr.flush()
            success = runner.launch_interactive_nx(port=runner.LIVE_PORT)
            if success:
                sys.stderr.write(
                    f"[NX-MCP] Siemens NX auto-launched successfully on port {runner.LIVE_PORT}.\n"
                )
            else:
                sys.stderr.write(
                    "[NX-MCP] Notice: Auto-launch did not bring up the bridge. "
                    "If the floating license is held or NX is still starting, please ensure the license seat is free or run 'python prewarm_nx.py'.\n"
                )
            sys.stderr.flush()
        else:
            sys.stderr.write(
                "[NX-MCP] Auto-launch is disabled (NX_MCP_AUTO_LAUNCH=0). "
                "Please run 'python prewarm_nx.py' to start the NX bridge.\n"
            )
            sys.stderr.flush()
    except Exception as exc:
        log.warning(f"Background NX prewarm encountered: {exc}")


def main():
    log.info(f"NX MCP started — {len(ToolRegistry.all())} tools")

    if os.environ.get("NX_MCP_USE_MOCK_NXOPEN") != "1":
        from nx_mcp.bridge.runner import verify_nx_environment

        try:
            verify_nx_environment()
        except RuntimeError as e:
            log.error(f"NX environment check failed: {e}")
            sys.stderr.write(f"ERROR: NX environment check failed: {e}\n")
            sys.stderr.flush()
            sys.exit(1)

        import threading
        threading.Thread(target=_check_or_prewarm_nx, daemon=True, name="nx-prewarm").start()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            resp = handle(json.loads(line))
            if resp:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as e:
            sys.stdout.write(json.dumps(err(None, -32700, str(e))) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
