import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
os.environ["NX_MCP_USE_MOCK_NXOPEN"] = "0"

from nx_mcp.bridge import runner

code = """
import sys
from nx_mcp.bridge import nx_bridge
active_plane = getattr(nx_bridge, 'ACTIVE_SKETCH_PLANE', 'N/A')
state = str(getattr(nx_bridge, '_state', {}))
with open('c:/Users/HP/nx-mcp/live_state_dump.txt', 'w') as f:
    f.write(f"ACTIVE_SKETCH_PLANE={active_plane}\\n")
    f.write(f"_state={state}\\n")
"""

res = runner.call_nx("exec_python_code", {"code": code})
print("Result:", res)
