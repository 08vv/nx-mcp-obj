import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
os.environ["NX_MCP_USE_MOCK_NXOPEN"] = "0"

import atexit
from nx_mcp.bridge import runner
from nx_mcp.tools import utility
atexit.unregister(runner.NXBridgeProcess.reset)

code = """
import NXOpen
import NXOpen.Positioning
import NXOpen.Assemblies
import json

work_part = SESSION.Parts.Work
pos = work_part.ComponentAssembly.Positioner
network = pos.EstablishNetwork()

res = {}
res["network_methods"] = [m for m in dir(network) if not m.startswith("_")]
for m_name in ["ApplyTransformation", "BeginDrag", "Drag", "MoveObjects", "SetMovingGroup", "StepLinearDrag", "StepRotateDrag", "Solve"]:
    if hasattr(network, m_name):
        try:
            attr = getattr(network, m_name)
            res[m_name] = str(attr)
        except Exception as e:
            res[m_name] = f"err: {e}"

pos.ClearNetwork()

with open("C:/Users/HP/nx-mcp/probe_network.json", "w") as f:
    json.dump(res, f, indent=2)
"""

out = utility.run_nx_journal_code(code, "probe network methods")
print("RESULT:", out)

if os.path.exists("c:/Users/HP/nx-mcp/probe_network.json"):
    with open("c:/Users/HP/nx-mcp/probe_network.json") as f:
        print("NETWORK_PROBE:", f.read())
