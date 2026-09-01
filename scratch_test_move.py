import sys
import os
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
os.environ["NX_MCP_USE_MOCK_NXOPEN"] = "0"

import atexit
from nx_mcp.bridge import runner
from nx_mcp.tools import utility
atexit.unregister(runner.NXBridgeProcess.reset)

ts = int(time.time())
code = f"""
import NXOpen
import NXOpen.Positioning
import NXOpen.Assemblies
import json
import os

p1_path = "C:/Users/HP/nx-mcp/test_move_{ts}.prt"
part1 = SESSION.Parts.NewDisplay(p1_path, NXOpen.Part.Units.Millimeters)
cb1 = part1.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
cb1.SetOriginAndLengths(NXOpen.Point3d(0.0, 0.0, 0.0), "50", "50", "50")
cb1.CommitFeature()
cb1.Destroy()
part1.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.TrueValue)

assy_path = "C:/Users/HP/nx-mcp/test_assy_move_{ts}.prt"
assy = SESSION.Parts.NewDisplay(assy_path, NXOpen.Part.Units.Millimeters)
pt_origin = NXOpen.Point3d(0.0, 0.0, 0.0)
rot_ident = NXOpen.Matrix3x3()
rot_ident.Xx = 1.0; rot_ident.Xy = 0.0; rot_ident.Xz = 0.0
rot_ident.Yx = 0.0; rot_ident.Yy = 1.0; rot_ident.Yz = 0.0
rot_ident.Zx = 0.0; rot_ident.Zy = 0.0; rot_ident.Zz = 1.0

comp, _ = assy.ComponentAssembly.AddComponent(p1_path, "Entire Part", "COMP", pt_origin, rot_ident, -1)

res = {{}}
p_init, _ = comp.GetPosition()
res["p_init"] = [p_init.X, p_init.Y, p_init.Z]

# Approach 1: BeginDrag -> DragByTranslation -> EndDrag -> Solve -> ApplyToModel
pos = assy.ComponentAssembly.Positioner
pos.ClearNetwork()
network = pos.EstablishNetwork()
network.SetMovingGroup([comp])
network.BeginDrag()
delta = NXOpen.Vector3d(50.0, 60.0, 70.0)
network.DragByTranslation(delta)
network.EndDrag()
network.Solve()
network.ApplyToModel()
pos.ClearNetwork()

p_after1, _ = comp.GetPosition()
res["p_after1"] = [p_after1.X, p_after1.Y, p_after1.Z]

with open("C:/Users/HP/nx-mcp/probe_move_out.json", "w") as f:
    json.dump(res, f, indent=2)
"""

out = utility.run_nx_journal_code(code, "test move network")
print("RESULT:", out)

if os.path.exists("c:/Users/HP/nx-mcp/probe_move_out.json"):
    with open("c:/Users/HP/nx-mcp/probe_move_out.json") as f:
        print("MOVE_OUT:", f.read())
