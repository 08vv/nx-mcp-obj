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
res["network_MoveObjectsState_type"] = str(type(network.MoveObjectsState))
res["Positioning_dir"] = [m for m in dir(NXOpen.Positioning) if "Move" in m or "State" in m]
res["ComponentNetwork_dir"] = [m for m in dir(NXOpen.Positioning.ComponentNetwork) if not m.startswith("_")]

for key in ["MoveObjectsState", "MoveObjectsStateEnum", "DragObjects", "StepLinearDrag"]:
    if hasattr(NXOpen.Positioning, key):
        res[f"NXOpen.Positioning.{key}"] = dir(getattr(NXOpen.Positioning, key))

pos.ClearNetwork()

with open("C:/Users/HP/nx-mcp/probe_move_state.json", "w") as f:
    json.dump(res, f, indent=2)
"""

out = utility.run_nx_journal_code(code, "probe MoveObjectsState")
print("RESULT:", out)

if os.path.exists("c:/Users/HP/nx-mcp/probe_move_state.json"):
    with open("c:/Users/HP/nx-mcp/probe_move_state.json") as f:
        print("STATE_PROBE:", f.read())
