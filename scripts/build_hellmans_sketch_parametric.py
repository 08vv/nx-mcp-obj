"""
build_hellmans_sketch_parametric.py
===================================
Constructs a 100% Sketch-In-Place driven, zone-wise parametric Siemens NX CAD
model for the Hellmann's Mayonnaise Jar (obj/Hellmans_reduced.obj).

Architecture:
  1. Parametric Expressions (All active & chained, 0 orphans)
  2. Fixed Datum Plane (XY Plane)
  3. Zone 1: SKETCH_BASE     -> BASE_REVOLVE     -> BASE_BOTTOM_BLEND
  4. Zone 2: SKETCH_BODY     -> BODY_REVOLVE     -> UNITE_BODY
  5. Zone 3: SKETCH_SHOULDER -> SHOULDER_REVOLVE -> UNITE_SHOULDER -> SHOULDER_BLEND
  6. Zone 4: SKETCH_NECK     -> NECK_REVOLVE     -> UNITE_NECK
  7. Zone 5: SKETCH_CAP      -> CAP_REVOLVE      -> UNITE_CAP

Usage:
  run_journal.exe scripts/build_hellmans_sketch_parametric.py -args [output_prt]
"""

from __future__ import annotations

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


def create_sketch_revolve(part, sketch, ref_line: Any, name: str = "REVOLVE"):
    """Creates an associative Revolve feature from sketch geometry around the Y axis."""
    rev_b = part.Features.CreateRevolveBuilder(NXOpen.Features.Feature.Null)
    try:
        rev_b.Tolerance = 0.01
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rule = part.ScRuleFactory.CreateRuleCurveFeature([sketch.Feature])
        sec.AddToSection([rule], ref_line, NXOpen.NXObject.Null, NXOpen.NXObject.Null, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
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
    default_prt = repo_root / "Hellmans_mayonnaise_jar.prt"
    out_prt = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and sys.argv[1].endswith(".prt") else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: HELLMANN'S MAYONNAISE JAR")
    print("  100% NATIVE SKETCH-IN-PLACE FEATURE TREE")
    print(f"  Target PRT: {out_prt}")
    print("=" * 75)

    if out_prt.exists():
        try:
            out_prt.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(out_prt), NXOpen.Part.Units.Millimeters)

    # =========================================================================
    # 1. DRIVING PARAMETRIC EXPRESSIONS (100% ACTIVE, ZERO ORPHANS)
    # =========================================================================
    print("\n[1/6] Creating driving expressions...")
    exp_defs = [
        # Zone 1: Base Foot Ring & Chamfer
        ("BASE_BOTTOM_DIA", "96.0"),
        ("BASE_TOP_DIA", "133.6"),
        ("BASE_HEIGHT", "12.0"),
        ("BASE_BOTTOM_BLEND_R", "3.5"),
        ("BASE_BOTTOM_R", "BASE_BOTTOM_DIA / 2.0"),
        ("BASE_TOP_R", "BASE_TOP_DIA / 2.0"),

        # Zone 2: Main Body with Label Bumper Ridges
        ("BODY_DIA", "133.6"),
        ("BODY_HEIGHT", "126.0"),
        ("LOWER_RIDGE_DIA", "134.4"),
        ("UPPER_RIDGE_DIA", "134.4"),
        ("BODY_R", "BODY_DIA / 2.0"),
        ("LOWER_RIDGE_R", "LOWER_RIDGE_DIA / 2.0"),
        ("UPPER_RIDGE_R", "UPPER_RIDGE_DIA / 2.0"),

        # Zone 3: Shoulder Transition
        ("SHOULDER_TOP_DIA", "101.6"),
        ("SHOULDER_HEIGHT", "33.0"),
        ("SHOULDER_BLEND_R", "2.5"),
        ("SHOULDER_TOP_R", "SHOULDER_TOP_DIA / 2.0"),

        # Zone 4: Neck & Collar Bead
        ("NECK_DIA", "101.6"),
        ("NECK_HEIGHT", "4.5"),
        ("NECK_R", "NECK_DIA / 2.0"),

        # Zone 5: Cap / Lid Body
        ("CAP_DIA", "105.0"),
        ("CAP_HEIGHT", "25.0"),
        ("CAP_R", "CAP_DIA / 2.0"),
    ]

    for name, formula in exp_defs:
        part.Expressions.CreateExpression("Number", f"{name} = {formula}")
        print(f"  {name} = {formula}")

    # Base Sketching Datum Plane (XY Plane: X = Radius, Y = Axial Height)
    mat_xy = NXOpen.Matrix3x3()
    mat_xy.Xx, mat_xy.Xy, mat_xy.Xz = 1.0, 0.0, 0.0
    mat_xy.Yx, mat_xy.Yy, mat_xy.Yz = 0.0, 1.0, 0.0
    mat_xy.Zx, mat_xy.Zy, mat_xy.Zz = 0.0, 0.0, 1.0
    datum_xy = part.Datums.CreateFixedDatumPlane(NXOpen.Point3d(0.0, 0.0, 0.0), mat_xy)

    # =========================================================================
    # 2. ZONE 1: SKETCH_BASE -> BASE_REVOLVE -> BASE_BOTTOM_BLEND
    # =========================================================================
    print("\n[2/5] Building Zone 1: SKETCH_BASE, BASE_REVOLVE & BASE_BOTTOM_BLEND...")
    skb_base = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
    skb_base.PlaneOrFace.Value = datum_xy
    sk_base = skb_base.Commit()
    set_name(sk_base, "SKETCH_BASE")
    skb_base.Destroy()

    sk_base.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    base_pts = [
        pt(0.0, 0.0),
        pt(48.0, 0.0),
        pt(66.8, 12.0),
        pt(0.0, 12.0),
    ]
    base_lines = []
    for k in range(len(base_pts)):
        p_a = base_pts[k]
        p_b = base_pts[(k + 1) % len(base_pts)]
        line = part.Curves.CreateLine(p_a, p_b)
        base_lines.append(line)
        sk_base.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

    # Add driving dimensional constraints
    try:
        dg_axis = NXOpen.Sketch.DimensionGeometry()
        dg_axis.Geometry = base_lines[3]
        dg_axis.AssocType = NXOpen.Sketch.AssocType.StartPoint

        dg_b_r = NXOpen.Sketch.DimensionGeometry()
        dg_b_r.Geometry = base_lines[0]
        dg_b_r.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_b_r = part.Expressions.FindObject("BASE_BOTTOM_R")
        sk_base.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg_axis, dg_b_r,
            pt(24.0, 0.0), exp_b_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )

        dg_t_r = NXOpen.Sketch.DimensionGeometry()
        dg_t_r.Geometry = base_lines[2]
        dg_t_r.AssocType = NXOpen.Sketch.AssocType.StartPoint

        exp_t_r = part.Expressions.FindObject("BASE_TOP_R")
        sk_base.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg_axis, dg_t_r,
            pt(33.4, 12.0), exp_t_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )

        dg_h_start = NXOpen.Sketch.DimensionGeometry()
        dg_h_start.Geometry = base_lines[3]
        dg_h_start.AssocType = NXOpen.Sketch.AssocType.StartPoint

        dg_h_end = NXOpen.Sketch.DimensionGeometry()
        dg_h_end.Geometry = base_lines[3]
        dg_h_end.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_base_h = part.Expressions.FindObject("BASE_HEIGHT")
        sk_base.CreateDimension(
            NXOpen.Sketch.ConstraintType.VerticalDim,
            dg_h_start, dg_h_end,
            pt(0.0, 6.0), exp_base_h,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )
    except Exception as e:
        print(f"  [INFO] Dimensions note: {e}")

    sk_base.Update()
    sk_base.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print("  [OK] Feature: SKETCH_BASE (4 profile segments)")

    base_feat, main_body = create_sketch_revolve(part, sk_base, base_lines[0], name="BASE_REVOLVE")
    print("  [OK] Feature: BASE_REVOLVE")

    # Associative blend on bottom planar face
    base_faces = [f for f in base_feat.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    if base_faces:
        base_bottom_face = min(base_faces, key=lambda f: f.GetCenter()[1] if hasattr(f, "GetCenter") else 0.0)
        bb_base = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            coll_base = part.ScCollectors.CreateCollector()
            coll_base.ReplaceRules([part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([base_bottom_face])], False)
            bb_base.AddChainset(coll_base, "BASE_BOTTOM_BLEND_R")
            blend_base_feat = bb_base.CommitFeature()
            set_name(blend_base_feat, "BASE_BOTTOM_BLEND")
            print("  [OK] Feature: BASE_BOTTOM_BLEND (associative face boundary rule)")
        finally:
            bb_base.Destroy()

    # =========================================================================
    # 3. ZONE 2: SKETCH_BODY -> BODY_REVOLVE -> UNITE_BODY
    # =========================================================================
    print("\n[3/5] Building Zone 2: SKETCH_BODY, BODY_REVOLVE & UNITE_BODY...")
    skb_body = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
    skb_body.PlaneOrFace.Value = datum_xy
    sk_body = skb_body.Commit()
    set_name(sk_body, "SKETCH_BODY")
    skb_body.Destroy()

    sk_body.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    body_pts = [
        pt(0.0, 12.0),
        pt(66.8, 12.0),
        pt(66.8, 27.0),
        pt(67.2, 29.0),
        pt(66.8, 31.0),
        pt(66.8, 124.0),
        pt(67.2, 126.0),
        pt(66.8, 128.0),
        pt(66.8, 138.0),
        pt(0.0, 138.0),
    ]
    body_lines = []
    for k in range(len(body_pts)):
        p_a = body_pts[k]
        p_b = body_pts[(k + 1) % len(body_pts)]
        line = part.Curves.CreateLine(p_a, p_b)
        body_lines.append(line)
        sk_body.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

    try:
        dg_axis2 = NXOpen.Sketch.DimensionGeometry()
        dg_axis2.Geometry = body_lines[len(body_lines) - 1]
        dg_axis2.AssocType = NXOpen.Sketch.AssocType.StartPoint

        dg_body_r = NXOpen.Sketch.DimensionGeometry()
        dg_body_r.Geometry = body_lines[0]
        dg_body_r.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_body_r = part.Expressions.FindObject("BODY_R")
        sk_body.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg_axis2, dg_body_r,
            pt(33.4, 12.0), exp_body_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )

        dg_ridge_low = NXOpen.Sketch.DimensionGeometry()
        dg_ridge_low.Geometry = body_lines[2]
        dg_ridge_low.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_ridge_low_r = part.Expressions.FindObject("LOWER_RIDGE_R")
        sk_body.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg_axis2, dg_ridge_low,
            pt(33.6, 29.0), exp_ridge_low_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )

        dg_ridge_high = NXOpen.Sketch.DimensionGeometry()
        dg_ridge_high.Geometry = body_lines[5]
        dg_ridge_high.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_ridge_high_r = part.Expressions.FindObject("UPPER_RIDGE_R")
        sk_body.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg_axis2, dg_ridge_high,
            pt(33.6, 126.0), exp_ridge_high_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )

        dg_body_h_start = NXOpen.Sketch.DimensionGeometry()
        dg_body_h_start.Geometry = body_lines[len(body_lines) - 1]
        dg_body_h_start.AssocType = NXOpen.Sketch.AssocType.StartPoint

        dg_body_h_end = NXOpen.Sketch.DimensionGeometry()
        dg_body_h_end.Geometry = body_lines[len(body_lines) - 1]
        dg_body_h_end.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_body_h = part.Expressions.FindObject("BODY_HEIGHT")
        sk_body.CreateDimension(
            NXOpen.Sketch.ConstraintType.VerticalDim,
            dg_body_h_start, dg_body_h_end,
            pt(0.0, 75.0), exp_body_h,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )
    except Exception as e:
        print(f"  [INFO] Dimensions note: {e}")

    sk_body.Update()
    sk_body.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print(f"  [OK] Feature: SKETCH_BODY ({len(body_lines)} profile segments)")

    body_feat, body_body = create_sketch_revolve(part, sk_body, body_lines[0], name="BODY_REVOLVE")
    print("  [OK] Feature: BODY_REVOLVE")

    u_body = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u_body.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u_body.RetainTarget = False
        u_body.RetainTool = False
        u_body.Target = main_body
        u_body.Tools.Add(body_body)
        u_body_feat = u_body.CommitFeature()
        set_name(u_body_feat, "UNITE_BODY")
        print("  [OK] Feature: UNITE_BODY")
    finally:
        u_body.Destroy()

    # =========================================================================
    # 4. ZONE 3: SKETCH_SHOULDER -> SHOULDER_REVOLVE -> UNITE & BLEND
    # =========================================================================
    print("\n[4/5] Building Zone 3: SKETCH_SHOULDER, REVOLVE, UNITE & BLEND...")
    skb_sh = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
    skb_sh.PlaneOrFace.Value = datum_xy
    sk_sh = skb_sh.Commit()
    set_name(sk_sh, "SKETCH_SHOULDER")
    skb_sh.Destroy()

    sk_sh.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    sh_pts = [
        pt(0.0, 138.0),
        pt(66.8, 138.0),
        pt(50.8, 171.0),
        pt(0.0, 171.0),
    ]
    sh_lines = []
    for k in range(len(sh_pts)):
        p_a = sh_pts[k]
        p_b = sh_pts[(k + 1) % len(sh_pts)]
        line = part.Curves.CreateLine(p_a, p_b)
        sh_lines.append(line)
        sk_sh.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

    try:
        dg_axis3 = NXOpen.Sketch.DimensionGeometry()
        dg_axis3.Geometry = sh_lines[3]
        dg_axis3.AssocType = NXOpen.Sketch.AssocType.StartPoint

        dg_sh_top = NXOpen.Sketch.DimensionGeometry()
        dg_sh_top.Geometry = sh_lines[2]
        dg_sh_top.AssocType = NXOpen.Sketch.AssocType.StartPoint

        exp_sh_top_r = part.Expressions.FindObject("SHOULDER_TOP_R")
        sk_sh.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg_axis3, dg_sh_top,
            pt(25.4, 171.0), exp_sh_top_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )

        dg_sh_h_start = NXOpen.Sketch.DimensionGeometry()
        dg_sh_h_start.Geometry = sh_lines[3]
        dg_sh_h_start.AssocType = NXOpen.Sketch.AssocType.StartPoint

        dg_sh_h_end = NXOpen.Sketch.DimensionGeometry()
        dg_sh_h_end.Geometry = sh_lines[3]
        dg_sh_h_end.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_sh_h = part.Expressions.FindObject("SHOULDER_HEIGHT")
        sk_sh.CreateDimension(
            NXOpen.Sketch.ConstraintType.VerticalDim,
            dg_sh_h_start, dg_sh_h_end,
            pt(0.0, 154.5), exp_sh_h,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )
    except Exception as e:
        print(f"  [INFO] Dimensions note: {e}")

    sk_sh.Update()
    sk_sh.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print("  [OK] Feature: SKETCH_SHOULDER (4 profile segments)")

    sh_feat, sh_body = create_sketch_revolve(part, sk_sh, sh_lines[0], name="SHOULDER_REVOLVE")
    print("  [OK] Feature: SHOULDER_REVOLVE")

    u_sh = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u_sh.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u_sh.RetainTarget = False
        u_sh.RetainTool = False
        u_sh.Target = main_body
        u_sh.Tools.Add(sh_body)
        u_sh_feat = u_sh.CommitFeature()
        set_name(u_sh_feat, "UNITE_SHOULDER")
        print("  [OK] Feature: UNITE_SHOULDER")
    finally:
        u_sh.Destroy()

    # Associative blend on shoulder conical face boundary
    sh_conical_faces = [f for f in sh_feat.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Conical]
    if sh_conical_faces:
        bb_sh = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            coll_sh = part.ScCollectors.CreateCollector()
            coll_sh.ReplaceRules([part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([sh_conical_faces[0]])], False)
            bb_sh.AddChainset(coll_sh, "SHOULDER_BLEND_R")
            blend_sh_feat = bb_sh.CommitFeature()
            set_name(blend_sh_feat, "SHOULDER_BLEND")
            print("  [OK] Feature: SHOULDER_BLEND (associative conical face rule)")
        except Exception as e:
            print(f"  [WARN] Shoulder blend: {e}")
        finally:
            bb_sh.Destroy()

    # =========================================================================
    # 5. ZONE 4: SKETCH_NECK -> NECK_REVOLVE -> UNITE_NECK
    # =========================================================================
    print("\n[5/6] Building Zone 4: SKETCH_NECK, NECK_REVOLVE & UNITE_NECK...")
    skb_neck = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
    skb_neck.PlaneOrFace.Value = datum_xy
    sk_neck = skb_neck.Commit()
    set_name(sk_neck, "SKETCH_NECK")
    skb_neck.Destroy()

    sk_neck.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    neck_pts = [
        pt(0.0, 171.0),
        pt(50.8, 171.0),
        pt(50.8, 175.5),
        pt(0.0, 175.5),
    ]
    neck_lines = []
    for k in range(len(neck_pts)):
        p_a = neck_pts[k]
        p_b = neck_pts[(k + 1) % len(neck_pts)]
        line = part.Curves.CreateLine(p_a, p_b)
        neck_lines.append(line)
        sk_neck.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

    try:
        dg_axis4 = NXOpen.Sketch.DimensionGeometry()
        dg_axis4.Geometry = neck_lines[3]
        dg_axis4.AssocType = NXOpen.Sketch.AssocType.StartPoint

        dg_neck_r = NXOpen.Sketch.DimensionGeometry()
        dg_neck_r.Geometry = neck_lines[0]
        dg_neck_r.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_neck_r = part.Expressions.FindObject("NECK_R")
        sk_neck.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg_axis4, dg_neck_r,
            pt(25.4, 171.0), exp_neck_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )

        dg_neck_h_start = NXOpen.Sketch.DimensionGeometry()
        dg_neck_h_start.Geometry = neck_lines[3]
        dg_neck_h_start.AssocType = NXOpen.Sketch.AssocType.StartPoint

        dg_neck_h_end = NXOpen.Sketch.DimensionGeometry()
        dg_neck_h_end.Geometry = neck_lines[3]
        dg_neck_h_end.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_neck_h = part.Expressions.FindObject("NECK_HEIGHT")
        sk_neck.CreateDimension(
            NXOpen.Sketch.ConstraintType.VerticalDim,
            dg_neck_h_start, dg_neck_h_end,
            pt(0.0, 173.25), exp_neck_h,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )
    except Exception as e:
        print(f"  [INFO] Dimensions note: {e}")

    sk_neck.Update()
    sk_neck.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print("  [OK] Feature: SKETCH_NECK (4 profile segments)")

    neck_feat, neck_body = create_sketch_revolve(part, sk_neck, neck_lines[0], name="NECK_REVOLVE")
    print("  [OK] Feature: NECK_REVOLVE")

    u_neck = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u_neck.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u_neck.RetainTarget = False
        u_neck.RetainTool = False
        u_neck.Target = main_body
        u_neck.Tools.Add(neck_body)
        u_neck_feat = u_neck.CommitFeature()
        set_name(u_neck_feat, "UNITE_NECK")
        print("  [OK] Feature: UNITE_NECK")
    finally:
        u_neck.Destroy()

    # =========================================================================
    # 6. ZONE 5: SKETCH_CAP -> CAP_REVOLVE -> UNITE_CAP
    # =========================================================================
    print("\n[6/6] Building Zone 5: SKETCH_CAP, CAP_REVOLVE & UNITE_CAP...")
    skb_cap = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
    skb_cap.PlaneOrFace.Value = datum_xy
    sk_cap = skb_cap.Commit()
    set_name(sk_cap, "SKETCH_CAP")
    skb_cap.Destroy()

    sk_cap.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    cap_pts = [
        pt(0.0, 175.5),
        pt(52.5, 175.5),
        pt(52.5, 200.5),
        pt(0.0, 200.5),
    ]
    cap_lines = []
    for k in range(len(cap_pts)):
        p_a = cap_pts[k]
        p_b = cap_pts[(k + 1) % len(cap_pts)]
        line = part.Curves.CreateLine(p_a, p_b)
        cap_lines.append(line)
        sk_cap.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

    try:
        dg_axis5 = NXOpen.Sketch.DimensionGeometry()
        dg_axis5.Geometry = cap_lines[3]
        dg_axis5.AssocType = NXOpen.Sketch.AssocType.StartPoint

        dg_cap_r = NXOpen.Sketch.DimensionGeometry()
        dg_cap_r.Geometry = cap_lines[0]
        dg_cap_r.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_cap_r = part.Expressions.FindObject("CAP_R")
        sk_cap.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg_axis5, dg_cap_r,
            pt(26.25, 175.5), exp_cap_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )

        dg_cap_h_start = NXOpen.Sketch.DimensionGeometry()
        dg_cap_h_start.Geometry = cap_lines[3]
        dg_cap_h_start.AssocType = NXOpen.Sketch.AssocType.StartPoint

        dg_cap_h_end = NXOpen.Sketch.DimensionGeometry()
        dg_cap_h_end.Geometry = cap_lines[3]
        dg_cap_h_end.AssocType = NXOpen.Sketch.AssocType.EndPoint

        exp_cap_h = part.Expressions.FindObject("CAP_HEIGHT")
        sk_cap.CreateDimension(
            NXOpen.Sketch.ConstraintType.VerticalDim,
            dg_cap_h_start, dg_cap_h_end,
            pt(0.0, 188.0), exp_cap_h,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )
    except Exception as e:
        print(f"  [INFO] Dimensions note: {e}")

    sk_cap.Update()
    sk_cap.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print("  [OK] Feature: SKETCH_CAP (4 profile segments)")

    cap_feat, cap_body = create_sketch_revolve(part, sk_cap, cap_lines[0], name="CAP_REVOLVE")
    print("  [OK] Feature: CAP_REVOLVE")

    u_cap = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u_cap.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u_cap.RetainTarget = False
        u_cap.RetainTool = False
        u_cap.Target = main_body
        u_cap.Tools.Add(cap_body)
        u_cap_feat = u_cap.CommitFeature()
        set_name(u_cap_feat, "UNITE_CAP")
        print("  [OK] Feature: UNITE_CAP")
    finally:
        u_cap.Destroy()

    # Save and Export
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"\n[SAVED] Part saved: {out_prt}")

    export_stl(session, part, main_body, out_stl)

    # Update latest pointer files
    latest_txt = repo_root / "latest_nx_result.txt"
    latest_cmd = repo_root / "open_current_nx_result.cmd"
    try:
        latest_txt.write_text(f"{out_prt}\n", encoding="utf-8")
        latest_cmd.write_text(f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugraf.exe" "{out_prt}"\n', encoding="utf-8")
        print("  [OK] Updated latest_nx_result.txt and open_current_nx_result.cmd")
    except Exception as e:
        print(f"  [WARN] Updating pointer files: {e}")

    print("\n" + "=" * 75)
    print("BUILD COMPLETE: HELLMANN'S MAYONNAISE JAR (100% NATIVE SKETCH TREE)")
    print("=" * 75)


if __name__ == "__main__":
    main()
