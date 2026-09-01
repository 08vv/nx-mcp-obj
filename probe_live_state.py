"""
Probe current global state in live ugraf.exe process.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import os
os.environ["NX_MCP_USE_MOCK_NXOPEN"] = "0"

from nx_mcp.bridge import runner

def probe_live_state():
    print("=== Probing Live Global State in ugraf.exe ===")
    code = (
        "import sys\n"
        "from nx_mcp.bridge import nx_bridge\n"
        "print('ACTIVE_SKETCH_PLANE:', getattr(nx_bridge, 'ACTIVE_SKETCH_PLANE', 'N/A'))\n"
        "print('_state:', getattr(nx_bridge, '_state', {}))\n"
    )
    res = runner.call_nx("exec_python_code", {"code": code})
    print("Execution Result:", res)

if __name__ == "__main__":
    probe_live_state()
