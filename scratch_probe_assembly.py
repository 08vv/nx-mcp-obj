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
res = {}

pos = work_part.ComponentAssembly.Positioner

# 1. Inspect Positioner.BeginMoveComponent and Network
try:
    network = pos.EstablishNetwork()
    res["network_type"] = str(type(network))
    res["network_methods"] = [m for m in dir(network) if not m.startswith("_")]
    pos.ClearNetwork()
except Exception as e:
    res["network_err"] = str(e)

# 2. Inspect Positioner.CreateConstraint
try:
    pos.BeginAssemblyConstraints()
    constraint = pos.CreateConstraint()
    res["constraint_type"] = str(type(constraint))
    res["constraint_methods"] = [m for m in dir(constraint) if not m.startswith("_")]
    pos.EndAssemblyConstraints()
except Exception as e:
    res["constraint_err"] = str(e)

# 3. Check NXOpen.Positioning.Constraint types and methods
try:
    res["constraint_enum"] = [m for m in dir(NXOpen.Positioning.Constraint.Type) if not m.startswith("_")]
except Exception as e:
    res["constraint_enum_err"] = str(e)

# 4. Check Component class methods
try:
    res["component_class_methods"] = [m for m in dir(NXOpen.Assemblies.Component) if not m.startswith("_")]
except Exception as e:
    res["comp_err"] = str(e)

with open("c:/Users/HP/nx-mcp/probe_assembly_details.json", "w") as f:
    json.dump(res, f, indent=2)
"""

out = utility.run_nx_journal_code(code, "probe assembly details")
print("RESULT:", out)

if os.path.exists("c:/Users/HP/nx-mcp/probe_assembly_details.json"):
    with open("c:/Users/HP/nx-mcp/probe_assembly_details.json") as f:
        print("PROBE_DETAILS:", f.read())
