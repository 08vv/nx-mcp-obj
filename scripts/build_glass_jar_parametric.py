"""
build_glass_jar_parametric.py
==============================
Feature-based, zone-wise parametric Siemens NX CAD model for Glass Jar Container
(obj/Glass jar_reduced.obj).

Feature Tree Architecture:
  1. JAR_BODY_BLOCK: Base Block (87.40 mm Width, 88.00 mm Height, 72.00 mm Depth)
  2. BODY_VERTICAL_CORNER_BLENDS: 4 Vertical corner blends (R = 7.00 mm)
  3. BASE_PERIMETER_BLEND: Associative blend on bottom planar face boundary (R = 5.00 mm)
  4. SHOULDER_BLEND: Associative blend on top planar shoulder boundary (R = 6.00 mm)
  5. NECK_CYLINDER: Cylinder (Dia = 54.70 mm, Height = 4.00 mm, chained to body top)
  6. UNITE_NECK: Boolean unite into main body
  7. CAP_CYLINDER: Cone/Cylinder (Dia = 58.30 -> 55.60 mm, Height = 107.44 mm, chained to neck end)
  8. UNITE_CAP: Boolean unite into main body
  9. CAP_CROWN_BLEND: Associative blend on cap apex planar face boundary (R = 4.00 mm)

Usage:
  run_journal.exe scripts/build_glass_jar_parametric.py [output_prt]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Configure license servers
if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.5" not in os.environ.get("SPLM_LICENSE_SERVER", ""):
    curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.5;28000@SunFibo19;28000@192.168.1.29;28000@192.168.1.3;{curr}"

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF

UF = NXOpen.UF.UFSession.GetUFSession()


def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    default_prt = repo_root / "Glass_jar_Parametric_v2.prt"
    out_prt = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: GLASS JAR CONTAINER")
    print("  ZONE-WISE FULLY PARAMETRIC FEATURE TREE")
    print(f"  Target PRT: {out_prt}")
    print("=" * 75)

    if out_prt.exists():
        try:
            out_prt.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(out_prt), NXOpen.Part.Units.Millimeters)

    # 1. Driving Parametric Expressions (Chained)
    print("\n[1/5] Creating driving expressions...")
    exp_defs = [
        ("BODY_BASE_Y", "-100.000"),
        ("BODY_WIDTH", "87.400"),
        ("BODY_DEPTH", "72.000"),
        ("BODY_HEIGHT", "88.000"),
        ("BODY_CORNER_R", "7.000"),
        ("BASE_BLEND_R", "5.000"),
        ("SHOULDER_BLEND_R", "6.000"),
        
        # Neck chained from body top
        ("NECK_START_Y", "BODY_BASE_Y + BODY_HEIGHT"),
        ("NECK_DIA", "54.700"),
        ("NECK_HEIGHT", "4.000"),
        ("NECK_END_Y", "NECK_START_Y + NECK_HEIGHT"),
        
        # Cap chained from neck end
        ("CAP_START_Y", "NECK_END_Y"),
        ("CAP_BASE_DIA", "58.300"),
        ("CAP_TOP_DIA", "55.600"),
        ("CAP_HEIGHT", "107.440"),
        ("CAP_CROWN_R", "4.000"),
        ("CAP_END_Y", "CAP_START_Y + CAP_HEIGHT"),
    ]

    for name, val in exp_defs:
        part.Expressions.CreateExpression("Number", f"{name} = {val}")
        print(f"  {name} = {val}")

    s0 = part.Scalars.CreateScalar(0.0, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)

    def s_exp(name: str):
        exp = part.Expressions.FindObject(name)
        return part.Scalars.CreateScalarExpression(exp, NXOpen.Scalar.DimensionalityType.Length, NXOpen.SmartObject.UpdateOption.WithinModeling)

    def pt_assoc(sx_name: str, sy_name: str, sz_name: str = "0"):
        sx = s0 if sx_name == "0" else s_exp(sx_name)
        sy = s0 if sy_name == "0" else s_exp(sy_name)
        sz = s0 if sz_name == "0" else s_exp(sz_name)
        return part.Points.CreatePoint(sx, sy, sz, NXOpen.SmartObject.UpdateOption.WithinModeling)

    dir_y = part.Directions.CreateDirection(NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0), NXOpen.SmartObject.UpdateOption.WithinModeling)

    # 2. JAR_BODY Block
    print("\n[2/5] Building Zone 1: JAR_BODY & Corner/Shoulder Blends...")
    bb = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    bb.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
    bb.SetOriginAndLengths(NXOpen.Point3d(-43.7, -100.0, -36.0), "BODY_WIDTH", "BODY_HEIGHT", "BODY_DEPTH")
    block_feat = bb.CommitFeature()
    block_feat.SetName("JAR_BODY_BLOCK")
    main_body = block_feat.GetBodies()[0]
    bb.Destroy()
    print("  [OK] Feature: JAR_BODY_BLOCK")

    # Vertical corner blends
    v_edges = []
    for e in main_body.GetEdges():
        v0, v1 = e.GetVertices()
        if abs(v0.Y - v1.Y) > 80.0:
            v_edges.append(e)

    ebb_v = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    coll_v = part.ScCollectors.CreateCollector()
    coll_v.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(v_edges)], False)
    ebb_v.AddChainset(coll_v, "BODY_CORNER_R")
    blend_v_feat = ebb_v.CommitFeature()
    blend_v_feat.SetName("BODY_VERTICAL_CORNER_BLENDS")
    ebb_v.Destroy()
    print("  [OK] Feature: BODY_VERTICAL_CORNER_BLENDS")

    # Base Perimeter Blend (associative to bottom planar face)
    def face_y(f):
        ys = [v.Y for e in f.GetEdges() for v in e.GetVertices()]
        return sum(ys) / len(ys) if ys else 0.0

    planars = [f for f in main_body.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    bot_face = min(planars, key=face_y)

    ebb_base = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    coll_base = part.ScCollectors.CreateCollector()
    coll_base.ReplaceRules([part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([bot_face])], False)
    ebb_base.AddChainset(coll_base, "BASE_BLEND_R")
    blend_base_feat = ebb_base.CommitFeature()
    blend_base_feat.SetName("BASE_PERIMETER_BLEND")
    ebb_base.Destroy()
    print("  [OK] Feature: BASE_PERIMETER_BLEND (associative face-boundary rule)")

    # Shoulder Blend (associative to top planar face)
    planars2 = [f for f in main_body.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    top_face2 = max(planars2, key=face_y)
    ebb_sh = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    coll_sh = part.ScCollectors.CreateCollector()
    coll_sh.ReplaceRules([part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([top_face2])], False)
    ebb_sh.AddChainset(coll_sh, "SHOULDER_BLEND_R")
    blend_sh_feat = ebb_sh.CommitFeature()
    blend_sh_feat.SetName("SHOULDER_BLEND")
    ebb_sh.Destroy()
    print("  [OK] Feature: SHOULDER_BLEND (associative face-boundary rule)")

    # 3. NECK CYLINDER
    print("\n[3/5] Building Zone 2: NECK_CYLINDER & UNITE...")
    neck_b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    neck_b.Diameter.RightHandSide = "NECK_DIA"
    neck_b.Height.RightHandSide   = "NECK_HEIGHT"
    neck_b.Axis.Point = pt_assoc("0", "NECK_START_Y")
    neck_b.Axis.Direction = dir_y
    neck_b.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    neck_feat = neck_b.CommitFeature()
    neck_feat.SetName("NECK_CYLINDER")
    neck_body = neck_feat.GetBodies()[0]
    neck_b.Destroy()
    print("  [OK] Feature: NECK_CYLINDER")

    u_neck = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_neck.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_neck.RetainTarget = False
    u_neck.RetainTool = False
    u_neck.Target = main_body
    u_neck.Tools.Add(neck_body)
    u_neck_feat = u_neck.CommitFeature()
    u_neck_feat.SetName("UNITE_NECK")
    u_neck.Destroy()
    print("  [OK] Feature: UNITE_NECK")

    # 4. CAP CONE (tapered cylinder)
    print("\n[4/5] Building Zone 3: CAP_CYLINDER & UNITE...")
    cap_b = part.Features.CreateConeBuilder(NXOpen.Features.Cone.Null)
    cap_b.Type = NXOpen.Features.ConeBuilder.Types.DiametersAndHeight
    cap_b.BaseDiameter.RightHandSide = "CAP_BASE_DIA"
    cap_b.TopDiameter.RightHandSide  = "CAP_TOP_DIA"
    cap_b.Height.RightHandSide       = "CAP_HEIGHT"
    cap_b.Axis.Point = pt_assoc("0", "CAP_START_Y")
    cap_b.Axis.Direction = dir_y
    cap_b.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    cap_feat = cap_b.CommitFeature()
    cap_feat.SetName("CAP_CYLINDER")
    cap_body = cap_feat.GetBodies()[0]
    cap_b.Destroy()
    print("  [OK] Feature: CAP_CYLINDER")

    u_cap = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_cap.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_cap.RetainTarget = False
    u_cap.RetainTool = False
    u_cap.Target = main_body
    u_cap.Tools.Add(cap_body)
    u_cap_feat = u_cap.CommitFeature()
    u_cap_feat.SetName("UNITE_CAP")
    u_cap.Destroy()
    print("  [OK] Feature: UNITE_CAP")

    # 5. CAP CROWN BLEND (associative to apex planar face)
    print("\n[5/5] Building Zone 4: CAP_CROWN_BLEND...")
    planars3 = [f for f in main_body.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    cap_top_face = max(planars3, key=face_y)
    ebb_cap = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    coll_cap = part.ScCollectors.CreateCollector()
    coll_cap.ReplaceRules([part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([cap_top_face])], False)
    ebb_cap.AddChainset(coll_cap, "CAP_CROWN_R")
    blend_cap_feat = ebb_cap.CommitFeature()
    blend_cap_feat.SetName("CAP_CROWN_BLEND")
    ebb_cap.Destroy()
    print("  [OK] Feature: CAP_CROWN_BLEND (associative face-boundary rule)")

    # Save & Export
    solids = [b for b in part.Bodies if b.IsSolidBody]
    print("\n" + "=" * 75)
    print(f"RECONSTRUCTION COMPLETE: {out_prt.name}")
    print(f"  Solid Bodies:  {len(solids)}")
    print(f"  Total Features: {len(list(part.Features))}")
    print("  Feature Tree:")
    for idx, f in enumerate(part.Features):
        print(f"    [{idx:2d}] {f.FeatureType:12s} | '{f.Name}'")
    print("=" * 75)

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"[OK] Part saved to: {out_prt}")

    # Export STL
    stlc = session.DexManager.CreateStlCreator()
    try:
        stlc.OutputFile = str(out_stl)
        stlc.ExportSelectionBlock.Add(main_body)
        stlc.Commit()
        print(f"[OK] Exported STL: {out_stl}")
    finally:
        stlc.Destroy()

    part.Close(NXOpen.BasePart.CloseWholeTree.FalseValue, NXOpen.BasePart.CloseModified.CloseModified, None)


if __name__ == "__main__":
    main()
