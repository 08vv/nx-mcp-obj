"""
build_ellie_18_parametric.py
============================
Constructs a true feature-based, zone-wise parametric Siemens NX CAD model for
the Ellie 18 Cosmetic Eyeliner (obj/Ellie_18_eye_liner.obj).

Feature Tree Architecture:
  1. Parametric Expressions (All driving, 0 orphans)
  2. BARREL_CONE: Cone primitive (Base Dia 13.80 mm, Top Dia 14.22 mm, Length 115.117 mm)
  3. BASE_END_BLEND: Associative edge blend on bottom perimeter face boundary (R = 1.80 mm)
  4. COLLAR_REVOLVE: Revolved profile capturing stepped lands, annular groove & accent ridge
  5. UNITE_COLLAR: Boolean unite into main body
  6. WAND_TRANSITION_CONE: Transition cone (Dia 10.58 -> 8.78 mm, Length 23.42 mm)
  7. UNITE_WAND_TRANSITION: Boolean unite into main body
  8. WAND_STEM_CYLINDER: Straight slender cylinder (Dia 8.78 mm, Length 26.50 mm)
  9. UNITE_WAND_STEM: Boolean unite into main body
  10. TIP_CONE: Tapered cone (Base Dia 8.78 mm, Apex Dia 0.50 mm, Length 14.43 mm)
  11. UNITE_TIP: Boolean unite into main body
  12. TIP_APEX_BLEND: Associative edge blend on crown apex dome (R = 0.50 mm)

Usage:
  run_journal.exe scripts/build_ellie_18_parametric.py [spec_json] [output_prt]
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Configure license servers
if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.5" not in os.environ.get("SPLM_LICENSE_SERVER", ""):
    curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.5;28000@SunFibo19;28000@192.168.1.29;28000@192.168.1.3;{curr}"

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF

UF = NXOpen.UF.UFSession.GetUFSession()


def pt(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def vc(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))


def set_name(obj, name: str):
    if obj is None:
        return
    try:
        obj.SetName(name)
    except Exception:
        pass


def export_stl(session, part, main_body, out_stl_path: Path):
    print(f"\nExporting STL: {out_stl_path}")
    if out_stl_path.exists():
        try:
            out_stl_path.unlink()
        except Exception:
            pass

    stl_exp = session.DexManager.CreateStlCreator()
    try:
        stl_exp.OutputFile = str(out_stl_path)
        stl_exp.ExportSelectionBlock.Add(main_body)
        stl_exp.Commit()
        print(f"  [OK] STL exported successfully: {out_stl_path} ({out_stl_path.stat().st_size:,} bytes)")
    except Exception as e:
        print(f"  [ERROR] STL export failed: {e}")
    finally:
        stl_exp.Destroy()


def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    default_spec = repo_root / "Ellie_18_eye_liner_parametric_spec.json"
    default_prt = repo_root / "Ellie_18_eye_liner_Parametric_v2.prt"

    spec_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_spec
    out_prt = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: ELLIE 18 COSMETIC EYELINER")
    print("  ZONE-WISE FULLY PARAMETRIC FEATURE TREE")
    print(f"  Specification: {spec_path}")
    print(f"  Target PRT:    {out_prt}")
    print("=" * 75)

    if out_prt.exists():
        try:
            out_prt.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(out_prt), NXOpen.Part.Units.Millimeters)

    # =========================================================================
    # 1. DRIVING PARAMETRIC EXPRESSIONS (ALL ACTIVE, 0 ORPHANS, FULLY CHAINED)
    # =========================================================================
    print("\n[1/5] Creating driving expressions...")
    exp_defs = [
        ("BARREL_BASE_Y", "-100.037"),
        ("BARREL_BASE_DIA", "13.800"),
        ("BARREL_TOP_DIA", "14.220"),
        ("BARREL_LENGTH", "115.117"),
        ("BASE_BLEND_R", "1.800"),
        
        # Zone 2: COLLAR chained from Zone 1
        ("COLLAR_START_Y", "BARREL_BASE_Y + BARREL_LENGTH"),
        ("COLLAR_LENGTH", "19.920"),
        ("COLLAR_MAX_DIA", "14.230"),
        ("COLLAR_STEP_OFFSET", "7.220"),
        ("COLLAR_STEP_DIA", "12.410"),
        ("ANNULAR_GROOVE_OFFSET", "11.740"),
        ("ANNULAR_GROOVE_DIA", "11.480"),
        ("ACCENT_RIDGE_OFFSET", "13.420"),
        ("ACCENT_RIDGE_DIA", "11.920"),
        ("COLLAR_END_DIA", "10.580"),
        ("COLLAR_END_Y", "COLLAR_START_Y + COLLAR_LENGTH"),
        
        # Collar Profile Vertices
        ("COLLAR_P0_Y", "COLLAR_START_Y"),
        ("COLLAR_P1_Y", "COLLAR_START_Y + 3.0"),
        ("COLLAR_P2_Y", "COLLAR_START_Y + COLLAR_STEP_OFFSET"),
        ("COLLAR_P3_Y", "COLLAR_P2_Y + 2.0"),
        ("COLLAR_P4_Y", "COLLAR_START_Y + ANNULAR_GROOVE_OFFSET"),
        ("COLLAR_P5_Y", "COLLAR_START_Y + ACCENT_RIDGE_OFFSET"),
        ("COLLAR_P6_Y", "COLLAR_P5_Y + 3.0"),
        ("COLLAR_P7_Y", "COLLAR_END_Y"),
        
        ("COLLAR_R_MAX", "COLLAR_MAX_DIA / 2.0"),
        ("COLLAR_R_STEP", "COLLAR_STEP_DIA / 2.0"),
        ("COLLAR_R_GRV", "ANNULAR_GROOVE_DIA / 2.0"),
        ("COLLAR_R_RDG", "ACCENT_RIDGE_DIA / 2.0"),
        ("COLLAR_R_END", "COLLAR_END_DIA / 2.0"),
        ("COLLAR_R_NECK", "COLLAR_R_END * 1.05"),
        
        # Zone 3: WAND STEM chained from Zone 2
        ("WAND_TRANS_START_Y", "COLLAR_END_Y"),
        ("WAND_TRANS_LENGTH", "23.420"),
        ("WAND_STEM_DIA", "8.780"),
        ("WAND_STEM_START_Y", "WAND_TRANS_START_Y + WAND_TRANS_LENGTH"),
        ("WAND_STEM_LENGTH", "26.500"),
        ("WAND_STEM_END_Y", "WAND_STEM_START_Y + WAND_STEM_LENGTH"),
        
        # Zone 4: TIP chained from Zone 3 (Profiled Revolve with gentle taper, shoulder & dome)
        ("TIP_START_Y", "WAND_STEM_END_Y"),
        ("TIP_BASE_DIA", "WAND_STEM_DIA"),
        ("TIP_TAPER_OFFSET", "6.080"),
        ("TIP_TAPER_DIA", "7.480"),
        ("TIP_SHOULDER_OFFSET", "12.080"),
        ("TIP_SHOULDER_DIA", "4.820"),
        ("TIP_LENGTH", "14.510"),
        ("TIP_TOP_DIA", "1.400"),
        ("TIP_APEX_R", "0.500"),
        ("TIP_END_Y", "TIP_START_Y + TIP_LENGTH"),
        
        ("TIP_P0_Y", "TIP_START_Y"),
        ("TIP_P1_Y", "TIP_START_Y + TIP_TAPER_OFFSET"),
        ("TIP_P2_Y", "TIP_START_Y + TIP_SHOULDER_OFFSET"),
        ("TIP_P3_Y", "TIP_END_Y"),
        
        ("TIP_R_BASE", "TIP_BASE_DIA / 2.0"),
        ("TIP_R_TAPER", "TIP_TAPER_DIA / 2.0"),
        ("TIP_R_SHOULDER", "TIP_SHOULDER_DIA / 2.0"),
        ("TIP_R_TOP", "TIP_TOP_DIA / 2.0"),
    ]

    for name, formula in exp_defs:
        part.Expressions.CreateExpression("Number", f"{name} = {formula}")
        print(f"  {name} = {formula}")

    s0 = part.Scalars.CreateScalar(0.0, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)

    def s_exp(name: str):
        exp = part.Expressions.FindObject(name)
        return part.Scalars.CreateScalarExpression(exp, NXOpen.Scalar.DimensionalityType.Length, NXOpen.SmartObject.UpdateOption.WithinModeling)

    def pt_assoc(sx_name: str, sy_name: str):
        sx = s0 if sx_name == "0" else s_exp(sx_name)
        sy = s0 if sy_name == "0" else s_exp(sy_name)
        return part.Points.CreatePoint(sx, sy, s0, NXOpen.SmartObject.UpdateOption.WithinModeling)

    dir_y = part.Directions.CreateDirection(NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0), NXOpen.SmartObject.UpdateOption.WithinModeling)

    # =========================================================================
    # 2. ZONE 1: BARREL CONE & ASSOCIATIVE BASE BLEND
    # =========================================================================
    print("\n[2/5] Building Zone 1: BARREL_CONE & BASE_END_BLEND...")
    cb_barrel = part.Features.CreateConeBuilder(NXOpen.Features.Cone.Null)
    cb_barrel.Type = NXOpen.Features.ConeBuilder.Types.DiametersAndHeight
    cb_barrel.BaseDiameter.RightHandSide = "BARREL_BASE_DIA"
    cb_barrel.TopDiameter.RightHandSide  = "BARREL_TOP_DIA"
    cb_barrel.Height.RightHandSide       = "BARREL_LENGTH"
    cb_barrel.Axis.Point = pt_assoc("0", "BARREL_BASE_Y")
    cb_barrel.Axis.Direction = dir_y
    cb_barrel.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create

    barrel_feat = cb_barrel.CommitFeature()
    set_name(barrel_feat, "BARREL_CONE")
    main_body = barrel_feat.GetBodies()[0]
    cb_barrel.Destroy()
    print("  [OK] Feature: BARREL_CONE")

    # Associative Base Blend on bottom planar face boundary
    planar_faces = [f for f in barrel_feat.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    base_face = min(planar_faces, key=lambda f: f.GetCenter()[1] if hasattr(f, "GetCenter") else 0.0)

    bb_base = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    coll_base = part.ScCollectors.CreateCollector()
    coll_base.ReplaceRules([part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([base_face])], False)
    bb_base.AddChainset(coll_base, "BASE_BLEND_R")
    blend_base_feat = bb_base.CommitFeature()
    set_name(blend_base_feat, "BASE_END_BLEND")
    bb_base.Destroy()
    print("  [OK] Feature: BASE_END_BLEND (associative face-boundary rule)")

    # =========================================================================
    # 3. ZONE 2: COLLAR REVOLVE (FULLY ASSOCIATIVE PROFILE)
    # =========================================================================
    print("\n[3/5] Building Zone 2: COLLAR_REVOLVE & UNITE...")
    c_pts = [
        pt_assoc("0", "COLLAR_P0_Y"),
        pt_assoc("COLLAR_R_MAX", "COLLAR_P0_Y"),
        pt_assoc("COLLAR_R_MAX", "COLLAR_P1_Y"),
        pt_assoc("COLLAR_R_STEP", "COLLAR_P2_Y"),
        pt_assoc("COLLAR_R_STEP", "COLLAR_P3_Y"),
        pt_assoc("COLLAR_R_GRV", "COLLAR_P4_Y"),
        pt_assoc("COLLAR_R_RDG", "COLLAR_P5_Y"),
        pt_assoc("COLLAR_R_NECK", "COLLAR_P6_Y"),
        pt_assoc("COLLAR_R_END", "COLLAR_P7_Y"),
        pt_assoc("0", "COLLAR_P7_Y"),
    ]

    c_lines = []
    for k in range(len(c_pts)):
        p_a = c_pts[k]
        p_b = c_pts[(k + 1) % len(c_pts)]
        c_lines.append(part.Curves.CreateLine(p_a, p_b))

    tags = [l.Tag for l in c_lines]
    feats, num_feat = UF.Modl.CreateRevolution(
        tags, len(tags), None,
        ["0", "360"], ["0", "0"],
        [0.0, 0.0, 0.0], False, True,
        [0.0, 0.0, 0.0], [0.0, 1.0, 0.0],
        NXOpen.UF.Modl.FeatureSigns.NULLSIGN,
    )
    collar_feat = NXOpen.TaggedObjectManager().GetTaggedObject(feats[0])
    set_name(collar_feat, "COLLAR_REVOLVE")
    collar_body = collar_feat.GetBodies()[0]
    print("  [OK] Feature: COLLAR_REVOLVE")

    u_collar = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_collar.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_collar.RetainTarget = False
    u_collar.RetainTool = False
    u_collar.Target = main_body
    u_collar.Tools.Add(collar_body)
    u_collar_feat = u_collar.CommitFeature()
    set_name(u_collar_feat, "UNITE_COLLAR")
    u_collar.Destroy()
    print("  [OK] Feature: UNITE_COLLAR")

    # =========================================================================
    # 4. ZONE 3: WAND STEM (TRANSITION CONE + STRAIGHT CYLINDER)
    # =========================================================================
    print("\n[4/5] Building Zone 3: WAND STEM (TRANSITION CONE + CYLINDER)...")
    cb_trans = part.Features.CreateConeBuilder(NXOpen.Features.Cone.Null)
    cb_trans.Type = NXOpen.Features.ConeBuilder.Types.DiametersAndHeight
    cb_trans.BaseDiameter.RightHandSide = "COLLAR_END_DIA"
    cb_trans.TopDiameter.RightHandSide  = "WAND_STEM_DIA"
    cb_trans.Height.RightHandSide       = "WAND_TRANS_LENGTH"
    cb_trans.Axis.Point = pt_assoc("0", "WAND_TRANS_START_Y")
    cb_trans.Axis.Direction = dir_y
    cb_trans.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create

    trans_feat = cb_trans.CommitFeature()
    set_name(trans_feat, "WAND_TRANSITION_CONE")
    trans_body = trans_feat.GetBodies()[0]
    cb_trans.Destroy()
    print("  [OK] Feature: WAND_TRANSITION_CONE")

    u_trans = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_trans.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_trans.RetainTarget = False
    u_trans.RetainTool = False
    u_trans.Target = main_body
    u_trans.Tools.Add(trans_body)
    u_trans_feat = u_trans.CommitFeature()
    set_name(u_trans_feat, "UNITE_WAND_TRANSITION")
    u_trans.Destroy()
    print("  [OK] Feature: UNITE_WAND_TRANSITION")

    # 4B. Wand Straight Stem Cylinder
    stem_b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    stem_b.Diameter.RightHandSide = "WAND_STEM_DIA"
    stem_b.Height.RightHandSide   = "WAND_STEM_LENGTH"
    stem_b.Axis.Point = pt_assoc("0", "WAND_STEM_START_Y")
    stem_b.Axis.Direction = dir_y
    stem_b.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create

    stem_feat = stem_b.CommitFeature()
    set_name(stem_feat, "WAND_STEM_CYLINDER")
    stem_body = stem_feat.GetBodies()[0]
    stem_b.Destroy()
    print("  [OK] Feature: WAND_STEM_CYLINDER")

    u_stem = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_stem.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_stem.RetainTarget = False
    u_stem.RetainTool = False
    u_stem.Target = main_body
    u_stem.Tools.Add(stem_body)
    u_stem_feat = u_stem.CommitFeature()
    set_name(u_stem_feat, "UNITE_WAND_STEM")
    u_stem.Destroy()
    print("  [OK] Feature: UNITE_WAND_STEM")

    # =========================================================================
    # 5. ZONE 4: TIP REVOLVE & ASSOCIATIVE APEX DOME BLEND
    # =========================================================================
    print("\n[5/5] Building Zone 4: TIP_REVOLVE & APEX DOME BLEND...")
    tip_pts = [
        pt_assoc("0", "TIP_P0_Y"),
        pt_assoc("TIP_R_BASE", "TIP_P0_Y"),
        pt_assoc("TIP_R_TAPER", "TIP_P1_Y"),
        pt_assoc("TIP_R_SHOULDER", "TIP_P2_Y"),
        pt_assoc("TIP_R_TOP", "TIP_P3_Y"),
        pt_assoc("0", "TIP_P3_Y"),
    ]

    tip_lines = []
    for k in range(len(tip_pts)):
        p_a = tip_pts[k]
        p_b = tip_pts[(k + 1) % len(tip_pts)]
        tip_lines.append(part.Curves.CreateLine(p_a, p_b))

    tags_tip = [l.Tag for l in tip_lines]
    feats_tip, num_feat_tip = UF.Modl.CreateRevolution(
        tags_tip, len(tags_tip), None,
        ["0", "360"], ["0", "0"],
        [0.0, 0.0, 0.0], False, True,
        [0.0, 0.0, 0.0], [0.0, 1.0, 0.0],
        NXOpen.UF.Modl.FeatureSigns.NULLSIGN,
    )
    tip_feat = NXOpen.TaggedObjectManager().GetTaggedObject(feats_tip[0])
    set_name(tip_feat, "TIP_REVOLVE")
    tip_body = tip_feat.GetBodies()[0]
    print("  [OK] Feature: TIP_REVOLVE")

    # Unite tip revolve into main body
    u_tip = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_tip.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_tip.RetainTarget = False
    u_tip.RetainTool = False
    u_tip.Target = main_body
    u_tip.Tools.Add(tip_body)
    u_tip_feat = u_tip.CommitFeature()
    set_name(u_tip_feat, "UNITE_TIP")
    u_tip.Destroy()
    print("  [OK] Feature: UNITE_TIP")

    # Associative Edge Blend on Tip Crown Apex (top planar face boundary of united main body)
    def face_y(f):
        ys = [v.Y for e in f.GetEdges() for v in e.GetVertices()]
        return sum(ys) / len(ys) if ys else 0.0

    main_planars = [f for f in main_body.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    apex_face = max(main_planars, key=face_y)
    bb_tip = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    coll_tip = part.ScCollectors.CreateCollector()
    coll_tip.ReplaceRules([part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([apex_face])], False)
    bb_tip.AddChainset(coll_tip, "TIP_APEX_R")
    blend_tip_feat = bb_tip.CommitFeature()
    set_name(blend_tip_feat, "TIP_APEX_BLEND")
    bb_tip.Destroy()
    print("  [OK] Feature: TIP_APEX_BLEND (associative face-boundary rule)")

    # =========================================================================
    # INSPECT, SAVE & EXPORT
    # =========================================================================
    feats = list(part.Features)
    solids = [b for b in part.Bodies if b.IsSolidBody]
    faces = list(main_body.GetFaces()) if main_body else []
    edges = list(main_body.GetEdges()) if main_body else []

    print("\n" + "=" * 75)
    print(f"RECONSTRUCTION COMPLETE: {out_prt.name}")
    print(f"  Solid Bodies:  {len(solids)}")
    print(f"  Faces / Edges: {len(faces)} faces, {len(edges)} edges")
    print("  Feature Tree:")
    for idx, f in enumerate(feats):
        print(f"    [{idx}] {f.FeatureType:12s} | '{f.Name}'")
    print("=" * 75)

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"[OK] Part successfully saved to: {out_prt}")

    export_stl(session, part, main_body, out_stl)

    # Update quick-launch files
    cmd_file = repo_root / "open_current_nx_result.cmd"
    cmd_file.write_text(f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugraf.exe" "{out_prt}"\n', encoding="utf-8")
    latest_file = repo_root / "latest_nx_result.txt"
    latest_file.write_text(str(out_prt), encoding="utf-8")

    print(f"[OK] Updated {cmd_file.name} and {latest_file.name}")


if __name__ == "__main__":
    main()
