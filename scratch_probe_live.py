import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
os.environ["NX_MCP_USE_MOCK_NXOPEN"] = "0"

from nx_mcp.tools import utility

code = """
import NXOpen
import NXOpen.Positioning
import NXOpen.Assemblies
import json

work_part = SESSION.Parts.Work
res = {}

# 1. Inspect ComponentPositioner
try:
    c_pos = work_part.ComponentAssembly.Positioner
    res["positioner_type"] = str(type(c_pos))
    res["positioner_methods"] = [m for m in dir(c_pos) if not m.startswith("_")]
except Exception as e:
    res["positioner_err"] = str(e)

# 2. Inspect AssemblyConstraintBuilder
try:
    builder = work_part.AssemblyManager.CreateAssemblyConstraintBuilder()
    res["builder_type"] = str(type(builder))
    res["builder_props"] = [m for m in dir(builder) if not m.startswith("_")]
    builder.Destroy()
except Exception as e:
    res["builder_err"] = str(e)

# 3. Inspect StudioSurfaceBuilder
try:
    ss_builder = work_part.Features.CreateStudioSurfaceBuilder(NXOpen.Features.Feature.Null)
    res["ss_builder_props"] = [m for m in dir(ss_builder) if not m.startswith("_")]
    ss_builder.Destroy()
except Exception as e:
    res["ss_builder_err"] = str(e)

with open("c:/Users/HP/nx-mcp/probe_out.json", "w") as f:
    json.dump(res, f, indent=2)
"""

out = utility.run_nx_journal_code(code, "probe nxopen api details")
print("RESULT:", out)

if os.path.exists("c:/Users/HP/nx-mcp/probe_out.json"):
    with open("c:/Users/HP/nx-mcp/probe_out.json") as f:
        print("PROBE_OUT:", f.read())
