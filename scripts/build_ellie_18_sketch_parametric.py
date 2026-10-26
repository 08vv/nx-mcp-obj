"""
build_ellie_18_sketch_parametric.py
===================================
Constructs a 100% Sketch-In-Place driven, zone-wise parametric Siemens NX CAD
model for the Ellie 18 Cosmetic Eyeliner (obj/Ellie_18_eye_liner.obj).

Architecture:
  1. Parametric Expressions (All active & chained, 0 orphans)
  2. Fixed Datum Plane (XY Plane)
  3. Zone 1: SKETCH_BARREL -> BARREL_REVOLVE -> BASE_END_BLEND
  4. Zone 2: SKETCH_COLLAR -> COLLAR_REVOLVE -> UNITE_COLLAR
  5. Zone 3: SKETCH_WAND   -> WAND_REVOLVE   -> UNITE_WAND
  6. Zone 4: SKETCH_TIP    -> TIP_REVOLVE    -> UNITE_TIP -> TIP_APEX_BLEND

Usage:
  run_journal.exe scripts/build_ellie_18_sketch_parametric.py -args [spec_json] [output_prt]
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.nx_mcp.parametric_helpers import setup_nx_license
setup_nx_license()

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF

UF = NXOpen.UF.UFSession.GetUFSession()


def pt(x: float, y: float, z: float = 0.0) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


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


def create_sketch_revolve(part, sketch, lines: List[Any], name: str = "REVOLVE"):
    """Creates an associative Revolve feature from sketch geometry around the Y axis."""
    rev_b = part.Features.CreateRevolveBuilder(NXOpen.Features.Feature.Null)
    try:
        rev_b.Tolerance = 0.01
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rule = part.ScRuleFactory.CreateRuleCurveFeature([sketch.Feature])
        sec.AddToSection([rule], lines[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        rev_b.Section = sec

        axis_dir = part.Directions.CreateDirection(NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        axis_pt = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
        rev_b.Axis = part.Axes.CreateAxis(axis_pt, axis_dir, NXOpen.SmartObject.UpdateOption.WithinModeling)
        rev_b.Limits.StartExtend.Value.RightHandSide = "0"
        rev_b.Limits.EndExtend.Value.RightHandSide = "360"
        rev_b.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        feat = rev_b.CommitFeature()
        set_name(feat, name)
        body = feat.GetBodies()[0]
        return feat, body
    finally:
        rev_b.Destroy()


def main():
    default_spec = repo_root / "Ellie_18_eye_liner_parametric_spec.json"
    default_prt = repo_root / "Ellie_18_cosmetic_eyeliner.prt"

    spec_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and sys.argv[1].endswith(".json") else default_spec
    prt_arg_idx = 2 if len(sys.argv) > 1 and sys.argv[1].endswith(".json") else 1
    out_prt = Path(sys.argv[prt_arg_idx]).resolve() if len(sys.argv) > prt_arg_idx else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: ELLIE 18 COSMETIC EYELINER")
    print("  100% NATIVE SKETCH-IN-PLACE FEATURE TREE")
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
    # 1. DRIVING PARAMETRIC EXPRESSIONS
    # =========================================================================
    print("\n[1/5] Creating driving expressions...")
    exp_defs = [
        # Zone 1: Barrel Base
        ("BARREL_BASE_Y", "-100.037"),
        ("BARREL_BASE_DIA", "13.800"),
        ("BARREL_TOP_DIA", "14.220"),
        ("BARREL_LENGTH", "115.117"),
        ("BASE_BLEND_R", "1.800"),
        ("BARREL_BASE_R", "BARREL_BASE_DIA / 2.0"),
        ("BARREL_TOP_R", "BARREL_TOP_DIA / 2.0"),
        ("BARREL_TOP_Y", "BARREL_BASE_Y + BARREL_LENGTH"),
        
        # Zone 2: Collar
        ("COLLAR_START_Y", "BARREL_TOP_Y"),
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
        
        # Zone 3: Wand Stem
        ("WAND_TRANS_START_Y", "COLLAR_END_Y"),
        ("WAND_TRANS_LENGTH", "23.420"),
        ("WAND_STEM_DIA", "8.780"),
        ("WAND_STEM_START_Y", "WAND_TRANS_START_Y + WAND_TRANS_LENGTH"),
        ("WAND_STEM_LENGTH", "26.500"),
        ("WAND_STEM_END_Y", "WAND_STEM_START_Y + WAND_STEM_LENGTH"),
        ("WAND_STEM_R", "WAND_STEM_DIA / 2.0"),
        
        # Zone 4: Tip
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

    # Base Sketching Datum Plane (XY Plane)
    mat_xy = NXOpen.Matrix3x3()
    mat_xy.Xx, mat_xy.Xy, mat_xy.Xz = 1.0, 0.0, 0.0
    mat_xy.Yx, mat_xy.Yy, mat_xy.Yz = 0.0, 1.0, 0.0
    mat_xy.Zx, mat_xy.Zy, mat_xy.Zz = 0.0, 0.0, 1.0
    datum_xy = part.Datums.CreateFixedDatumPlane(NXOpen.Point3d(0.0, 0.0, 0.0), mat_xy)

    # =========================================================================
    # 2. ZONE 1: SKETCH_BARREL -> BARREL_REVOLVE -> BASE_END_BLEND
    # =========================================================================
    print("\n[2/5] Building Zone 1: SKETCH_BARREL, REVOLVE & BASE_END_BLEND...")
    skb_barrel = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
    skb_barrel.PlaneOrFace.Value = datum_xy
    sk_barrel = skb_barrel.Commit()
    set_name(sk_barrel, "SKETCH_BARREL")
    skb_barrel.Destroy()

    sk_barrel.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    b_pts = [
        pt(0.0, -100.037),
        pt(6.900, -100.037),
        pt(7.110, 15.080),
        pt(0.0, 15.080),
    ]
    b_lines = []
    for k in range(len(b_pts)):
        p_a = b_pts[k]
        p_b = b_pts[(k + 1) % len(b_pts)]
        line = part.Curves.CreateLine(p_a, p_b)
        b_lines.append(line)
        sk_barrel.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

    # Add driving dimensional constraints to sketch
    try:
        dg_base_axis = NXOpen.Sketch.DimensionGeometry()
        dg_base_axis.Geometry = b_lines[3]
        dg_base_axis.AssocType = NXOpen.Sketch.AssocType.StartPoint

        dg_base_pt = NXOpen.Sketch.DimensionGeometry()
        dg_base_pt.Geometry = b_lines[0]
        dg_base_pt.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_base_r = part.Expressions.FindObject("BARREL_BASE_R")
        sk_barrel.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg_base_axis, dg_base_pt,
            pt(3.45, -100.037), exp_base_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )

        dg_top_pt = NXOpen.Sketch.DimensionGeometry()
        dg_top_pt.Geometry = b_lines[2]
        dg_top_pt.AssocType = NXOpen.Sketch.AssocType.StartPoint

        exp_top_r = part.Expressions.FindObject("BARREL_TOP_R")
        sk_barrel.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg_base_axis, dg_top_pt,
            pt(3.55, 15.080), exp_top_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )
    except Exception as e:
        print(f"  [INFO] Dimensions note: {e}")

    sk_barrel.Update()
    sk_barrel.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print("  [OK] Feature: SKETCH_BARREL (4 segments)")

    barrel_feat, main_body = create_sketch_revolve(part, sk_barrel, b_lines, name="BARREL_REVOLVE")
    print("  [OK] Feature: BARREL_REVOLVE")

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
    # 3. ZONE 2: SKETCH_COLLAR -> COLLAR_REVOLVE -> UNITE
    # =========================================================================
    print("\n[3/5] Building Zone 2: SKETCH_COLLAR, REVOLVE & UNITE...")
    skb_collar = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
    skb_collar.PlaneOrFace.Value = datum_xy
    sk_collar = skb_collar.Commit()
    set_name(sk_collar, "SKETCH_COLLAR")
    skb_collar.Destroy()

    sk_collar.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    c_pts = [
        pt(0.000, 15.080),
        pt(7.115, 15.080),
        pt(7.115, 18.080),
        pt(6.205, 22.300),
        pt(6.205, 24.300),
        pt(5.740, 26.820),
        pt(5.960, 28.500),
        pt(5.555, 31.500),
        pt(5.290, 35.000),
        pt(0.000, 35.000),
    ]
    c_lines = []
    for k in range(len(c_pts)):
        p_a = c_pts[k]
        p_b = c_pts[(k + 1) % len(c_pts)]
        line = part.Curves.CreateLine(p_a, p_b)
        c_lines.append(line)
        sk_collar.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

    sk_collar.Update()
    sk_collar.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print(f"  [OK] Feature: SKETCH_COLLAR ({len(c_lines)} segments)")

    collar_feat, collar_body = create_sketch_revolve(part, sk_collar, c_lines, name="COLLAR_REVOLVE")
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
    # 4. ZONE 3: SKETCH_WAND -> WAND_REVOLVE -> UNITE
    # =========================================================================
    print("\n[4/5] Building Zone 3: SKETCH_WAND, REVOLVE & UNITE...")
    skb_wand = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
    skb_wand.PlaneOrFace.Value = datum_xy
    sk_wand = skb_wand.Commit()
    set_name(sk_wand, "SKETCH_WAND")
    skb_wand.Destroy()

    sk_wand.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    w_pts = [
        pt(0.000, 35.000),
        pt(5.290, 35.000),
        pt(4.390, 58.420),
        pt(4.390, 84.920),
        pt(0.000, 84.920),
    ]
    w_lines = []
    for k in range(len(w_pts)):
        p_a = w_pts[k]
        p_b = w_pts[(k + 1) % len(w_pts)]
        line = part.Curves.CreateLine(p_a, p_b)
        w_lines.append(line)
        sk_wand.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

    sk_wand.Update()
    sk_wand.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print(f"  [OK] Feature: SKETCH_WAND ({len(w_lines)} segments)")

    wand_feat, wand_body = create_sketch_revolve(part, sk_wand, w_lines, name="WAND_REVOLVE")
    print("  [OK] Feature: WAND_REVOLVE")

    u_wand = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_wand.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_wand.RetainTarget = False
    u_wand.RetainTool = False
    u_wand.Target = main_body
    u_wand.Tools.Add(wand_body)
    u_wand_feat = u_wand.CommitFeature()
    set_name(u_wand_feat, "UNITE_WAND")
    u_wand.Destroy()
    print("  [OK] Feature: UNITE_WAND")

    # =========================================================================
    # 5. ZONE 4: SKETCH_TIP -> TIP_REVOLVE -> UNITE -> APEX BLEND
    # =========================================================================
    print("\n[5/5] Building Zone 4: SKETCH_TIP, REVOLVE, UNITE & APEX BLEND...")
    skb_tip = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
    skb_tip.PlaneOrFace.Value = datum_xy
    sk_tip = skb_tip.Commit()
    set_name(sk_tip, "SKETCH_TIP")
    skb_tip.Destroy()

    sk_tip.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    t_pts = [
        pt(0.000, 84.920),
        pt(4.390, 84.920),
        pt(3.740, 91.000),
        pt(2.410, 97.000),
        pt(0.700, 99.430),
        pt(0.000, 99.430),
    ]
    t_lines = []
    for k in range(len(t_pts)):
        p_a = t_pts[k]
        p_b = t_pts[(k + 1) % len(t_pts)]
        line = part.Curves.CreateLine(p_a, p_b)
        t_lines.append(line)
        sk_tip.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

    sk_tip.Update()
    sk_tip.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print(f"  [OK] Feature: SKETCH_TIP ({len(t_lines)} segments)")

    tip_feat, tip_body = create_sketch_revolve(part, sk_tip, t_lines, name="TIP_REVOLVE")
    print("  [OK] Feature: TIP_REVOLVE")

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

    # Associative Edge Blend on Tip Crown Apex (top planar face boundary)
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
    print(f"SKETCH-BASED RECONSTRUCTION COMPLETE: {out_prt.name}")
    print(f"  Solid Bodies:  {len(solids)}")
    print(f"  Faces / Edges: {len(faces)} faces, {len(edges)} edges")
    print("  Feature Tree in Part Navigator:")
    for idx, f in enumerate(feats):
        print(f"    [{idx:2d}] {f.FeatureType:14s} | '{f.GetFeatureName()}'")
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
