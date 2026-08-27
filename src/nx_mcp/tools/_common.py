import os
from nx_mcp.response import ToolResult

def _use_mock_nxopen() -> bool:
    return os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1"

def _bridge_result(res: dict, cmd_path: str = None, auto_open: bool = False) -> ToolResult:
    if res.get("status") == "success" or res.get("ok"):
        msg = res.get("result") or res.get("message") or "Success"
        
        ids = []
        for key in ("body_id", "feature_id", "sketch_id", "curve_id"):
            if res.get(key):
                ids.append(f"{key}={res[key]}")
        if ids:
            msg += f" [{', '.join(ids)}]"
            
        if auto_open and _use_mock_nxopen():
            if not cmd_path:
                from nx_mcp.bridge import runner
                cmd_path = str(runner.ROOT_DIR / "open_current_nx_result.cmd")
            import subprocess
            try:
                subprocess.Popen([cmd_path], shell=True)
                msg += f"\n\nAuto-opened in NX (runner script: {cmd_path})."
            except Exception as e:
                msg += f"\n\n(Auto-open failed: {e}. You can manually run: {cmd_path})"
        elif cmd_path:
            msg += f"\n\nTo manually open in NX, run:\n{cmd_path}"
            
        return ToolResult(msg)
    raise RuntimeError(res.get("error", "NX bridge command failed"))


