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
import NXOpen.Features
import json

work_part = SESSION.Parts.Work

res = {}

try:
    ss_builder = work_part.Features.CreateStudioSurfaceBuilder(NXOpen.Features.Feature.Null)
    res["studio_surface_props"] = [m for m in dir(ss_builder) if not m.startswith("_")]
    ss_builder.Destroy()
except Exception as e:
    res["studio_surface_err"] = str(e)

try:
    sec_builder = work_part.Features.CreateSectionSurfaceBuilder(NXOpen.Features.Feature.Null)
    res["section_surface_props"] = [m for m in dir(sec_builder) if not m.startswith("_")]
    sec_builder.Destroy()
except Exception as e:
    res["section_surface_err"] = str(e)

with open("C:/Users/HP/nx-mcp/probe_surface_builders.json", "w") as f:
    json.dump(res, f, indent=2)
"""

out = utility.run_nx_journal_code(code, "probe surface builders")
print("RESULT:", out)

if os.path.exists("c:/Users/HP/nx-mcp/probe_surface_builders.json"):
    with open("c:/Users/HP/nx-mcp/probe_surface_builders.json") as f:
        print("SURFACE_BUILDERS:", f.read())
