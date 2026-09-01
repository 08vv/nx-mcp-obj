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

res = {{}}

# Create Part 1
p1_path = "C:/Users/HP/nx-mcp/test_comp1_{ts}.prt"
part1 = SESSION.Parts.NewDisplay(p1_path, NXOpen.Part.Units.Millimeters)
cb1 = part1.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
cb1.SetOriginAndLengths(NXOpen.Point3d(0.0, 0.0, 0.0), "50", "50", "50")
cb1.CommitFeature()
cb1.Destroy()
part1.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.TrueValue)

# Create Part 2
p2_path = "C:/Users/HP/nx-mcp/test_comp2_{ts}.prt"
part2 = SESSION.Parts.NewDisplay(p2_path, NXOpen.Part.Units.Millimeters)
cb2 = part2.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
cb2.SetOriginAndLengths(NXOpen.Point3d(0.0, 0.0, 0.0), "30", "30", "30")
cb2.CommitFeature()
cb2.Destroy()
part2.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.TrueValue)

# Create Assembly
assy_path = "C:/Users/HP/nx-mcp/test_assy_{ts}.prt"
assy = SESSION.Parts.NewDisplay(assy_path, NXOpen.Part.Units.Millimeters)

# Add Component 1
pt_origin = NXOpen.Point3d(0.0, 0.0, 0.0)
rot_ident = NXOpen.Matrix3x3()
rot_ident.Xx = 1.0; rot_ident.Xy = 0.0; rot_ident.Xz = 0.0
rot_ident.Yx = 0.0; rot_ident.Yy = 1.0; rot_ident.Yz = 0.0
rot_ident.Zx = 0.0; rot_ident.Zy = 0.0; rot_ident.Zz = 1.0

comp1, _ = assy.ComponentAssembly.AddComponent(p1_path, "Entire Part", "COMP1", pt_origin, rot_ident, -1)
comp2, _ = assy.ComponentAssembly.AddComponent(p2_path, "Entire Part", "COMP2", NXOpen.Point3d(100.0, 0.0, 0.0), rot_ident, -1)

# Check Initial Positions
pos1_pt, pos1_rot = comp1.GetPosition()
pos2_pt, pos2_rot = comp2.GetPosition()
res["initial_pos2"] = [pos2_pt.X, pos2_pt.Y, pos2_pt.Z]

# Test Repositioning Component 2 using ComponentNetwork DragByTranslation
pos = assy.ComponentAssembly.Positioner
pos.ClearNetwork()
network = pos.EstablishNetwork()
network.SetMovingGroup([comp2])
new_origin = NXOpen.Point3d(10.0, 20.0, 30.0)
delta_vec = NXOpen.Vector3d(new_origin.X - pos2_pt.X, new_origin.Y - pos2_pt.Y, new_origin.Z - pos2_pt.Z)
network.DragByTranslation(delta_vec)
network.Solve()
network.ApplyToModel()
pos.ClearNetwork()

pos2_new_pt, _ = comp2.GetPosition()
res["repositioned_pos2"] = [pos2_new_pt.X, pos2_new_pt.Y, pos2_new_pt.Z]

# Test Mating Components: Touch / Align
comp1_proto = comp1.Prototype
comp2_proto = comp2.Prototype

comp1_body = list(comp1_proto.Bodies)[0]
comp2_body = list(comp2_proto.Bodies)[0]

comp1_faces = list(comp1_body.GetFaces())
comp2_faces = list(comp2_body.GetFaces())

# Find occurrence faces
comp1_occ_face = comp1.FindOccurrence(comp1_faces[0]) or comp1_faces[0]
comp2_occ_face = comp2.FindOccurrence(comp2_faces[0]) or comp2_faces[0]

pos.BeginAssemblyConstraints()
constraint = pos.CreateConstraint()
constraint.ConstraintType = NXOpen.Positioning.Constraint.Type.Touch
# Reference 1
ref1 = constraint.CreateConstraintReference(comp1, comp1_occ_face, False, False, False)
# Reference 2
ref2 = constraint.CreateConstraintReference(comp2, comp2_occ_face, False, False, False)
pos.SolvePostponedConstraints()
pos.EndAssemblyConstraints()

res["constraint_status"] = str(constraint.GetConstraintStatus())
res["constraint_count"] = len(list(pos.Constraints))

with open("C:/Users/HP/nx-mcp/probe_assy_test_out.json", "w") as f:
    json.dump(res, f, indent=2)
"""

out = utility.run_nx_journal_code(code, "test assembly reposition and mate")
print("RESULT:", out)

if os.path.exists("c:/Users/HP/nx-mcp/probe_assy_test_out.json"):
    with open("c:/Users/HP/nx-mcp/probe_assy_test_out.json") as f:
        print("ASSY_TEST_OUT:", f.read())
