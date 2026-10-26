"""
build_ellie_18_reduced_parametric.py
====================================
Feature-based, fully parametric Siemens NX CAD model generator for the
Ellie 18 Compact Powder / Foundation Case (obj/Ellie_18_reduced.obj).

Strict Geometric Match:
  • Compact rounded-rectangular overall body (199.3 x 71.1 x 191.8 mm)
  • Wide, shallow proportions with large smooth rounded corners (R = 40 mm)
  • Broad flat top surface with continuous curved crown edge blend (R = 5 mm)
  • Distinct two-level lid structure: lower rim collar + upper stepped body
  • Narrow continuous parting seam groove between lower body and lid
  • Rounded stepped transition perimeter around the upper lid
  • Small recessed rectangular clasp feature on the front side (+Z)
  • Raised push-button detail inside the recessed pocket

Parametric Feature Tree Architecture:
  1. USER EXPRESSIONS (Fully chained elevations, 0 orphans)
  2. LOWER_BODY_BLOCK (Block primitive)
  3. LOWER_BODY_CORNER_BLENDS (Associative intersection edge blend, R = 40 mm)
  4. LOWER_BODY_BASE_BLEND (Associative face boundary blend, R = 4.5 mm)
  5. SEAM_NECK_BLOCK (Block primitive)
  6. SEAM_NECK_CORNER_BLENDS (Associative intersection edge blend)
  7. UNITE_SEAM_NECK (Boolean Unite)
  8. LID_RIM_BLOCK (Block primitive)
  9. LID_RIM_CORNER_BLENDS (Associative intersection edge blend, R = 40 mm)
  10. UNITE_LID_RIM (Boolean Unite)
  11. LID_UPPER_BLOCK (Block primitive)
  12. LID_UPPER_CORNER_BLENDS (Associative intersection edge blend, R = 38 mm)
  13. LID_TOP_BLEND (Associative face boundary blend, R = 5 mm)
  14. UNITE_LID_UPPER (Boolean Unite)
  15. FRONT_RECESS_BLOCK (Block primitive)
  16. SUBTRACT_FRONT_RECESS (Boolean Subtract)
  17. FRONT_BUTTON_BLOCK (Block primitive)
  18. FRONT_BUTTON_CORNER_BLENDS (Associative intersection edge blend, R = 1.5 mm)
  19. UNITE_FRONT_BUTTON (Boolean Unite)

Usage:
  run_journal.exe scripts/build_ellie_18_reduced_parametric.py [output_prt]
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

# Configure Siemens NX License Servers
if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.5" not in os.environ.get("SPLM_LICENSE_SERVER", ""):
    curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.5;28000@SunFibo19;28000@192.168.1.29;28000@192.168.1.3;{curr}"

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities


def set_name(feat, name: str):
    if feat is not None:
        try:
            feat.SetName(name)
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
    default_prt = repo_root / "Ellie_18_reduced_Parametric.prt"
    out_prt = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: ELLIE 18 COMPACT CASE")
    print("  STRICT GEOMETRY MATCH TO OBJ (obj/Ellie_18_reduced.obj)")
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
    # 1. DRIVING PARAMETRIC EXPRESSIONS (ALL ACTIVE, 0 ORPHANS, CHAINED ELEVATIONS)
    # =========================================================================
    print("\n[1/7] Creating driving expressions...")
    exp_defs = [
        # Zone 1: Lower Body Base Container
        ("LOWER_BODY_START_Y", "-35.905"),
        ("LOWER_BODY_HEIGHT",  "41.405"),
        ("LOWER_BODY_LENGTH",  "199.140"),
        ("LOWER_BODY_WIDTH",   "190.870"),
        ("LOWER_BODY_ORIGIN_X", "-99.570"),
        ("LOWER_BODY_ORIGIN_Z", "-96.140"),
        ("LOWER_CORNER_R",     "40.000"),
        ("BASE_END_BLEND_R",   "4.500"),

        # Zone 2: Continuous Parting Seam Neck (Chained to Zone 1)
        ("SEAM_START_Y",       "LOWER_BODY_START_Y + LOWER_BODY_HEIGHT"),
        ("SEAM_HEIGHT",        "1.200"),
        ("SEAM_INDENT",        "0.900"),
        ("SEAM_LENGTH",        "LOWER_BODY_LENGTH - 2.0 * SEAM_INDENT"),
        ("SEAM_WIDTH",         "LOWER_BODY_WIDTH - 2.0 * SEAM_INDENT"),
        ("SEAM_ORIGIN_X",      "LOWER_BODY_ORIGIN_X + SEAM_INDENT"),
        ("SEAM_ORIGIN_Z",      "LOWER_BODY_ORIGIN_Z + SEAM_INDENT"),
        ("SEAM_CORNER_R",      "39.000"),

        # Zone 3: Lid Lower Rim (Chained to Zone 2)
        ("LID_RIM_START_Y",    "SEAM_START_Y + SEAM_HEIGHT"),
        ("LID_RIM_HEIGHT",     "4.800"),
        ("LID_RIM_LENGTH",     "199.286"),
        ("LID_RIM_WIDTH",      "191.837"),
        ("LID_RIM_ORIGIN_X",   "-99.959"),
        ("LID_RIM_ORIGIN_Z",   "-96.308"),
        ("LID_RIM_CORNER_R",   "40.000"),

        # Zone 4: Upper Lid (Chained to Zone 3)
        ("LID_UPPER_START_Y",  "LID_RIM_START_Y + LID_RIM_HEIGHT"),
        ("LID_UPPER_HEIGHT",   "23.688"),
        ("LID_UPPER_LENGTH",   "195.827"),
        ("LID_UPPER_WIDTH",    "188.465"),
        ("LID_UPPER_ORIGIN_X", "-98.192"),
        ("LID_UPPER_ORIGIN_Z", "-94.470"),
        ("LID_UPPER_CORNER_R", "38.000"),
        ("LID_TOP_BLEND_R",    "5.000"),

        # Zone 5: Front Recessed Pocket (Cutout)
        ("RECESS_START_X",     "-28.544"),
        ("RECESS_START_Y",     "-19.199"),
        ("RECESS_FLOOR_Z",     "88.000"),
        ("RECESS_WIDTH",       "56.625"),
        ("RECESS_HEIGHT",      "21.899"),
        ("RECESS_CUT_EXTENT",  "10.000"),

        # Zone 6: Front Latch Button (Unite)
        ("BUTTON_START_X",     "-16.000"),
        ("BUTTON_START_Y",     "-20.077"),
        ("BUTTON_BASE_Z",      "88.000"),
        ("BUTTON_WIDTH",       "32.000"),
        ("BUTTON_HEIGHT",      "13.980"),
        ("BUTTON_THICKNESS",   "6.058"),
        ("BUTTON_TOP_BLEND_R", "1.500"),
    ]

    for name, formula in exp_defs:
        part.Expressions.CreateExpression("Number", f"{name} = {formula}")
        print(f"  {name} = {formula}")

    s0 = part.Scalars.CreateScalar(0.0, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)

    def s_exp(name: str):
        exp = part.Expressions.FindObject(name)
        return part.Scalars.CreateScalarExpression(exp, NXOpen.Scalar.DimensionalityType.Length, NXOpen.SmartObject.UpdateOption.WithinModeling)

    def pt_assoc(sx_name: str, sy_name: str, sz_name: str):
        sx = s0 if sx_name == "0" else s_exp(sx_name)
        sy = s0 if sy_name == "0" else s_exp(sy_name)
        sz = s0 if sz_name == "0" else s_exp(sz_name)
        return part.Points.CreatePoint(sx, sy, sz, NXOpen.SmartObject.UpdateOption.WithinModeling)

    # =========================================================================
    # 2. ZONE 1: LOWER BODY (BLOCK + VERTICAL CORNER BLENDS + BASE BLEND)
    # =========================================================================
    print("\n[2/7] Building Zone 1: LOWER_BODY_BLOCK, CORNER_BLENDS & BASE_BLEND...")
    b1 = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    b1.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
    pt_orig1 = pt_assoc("LOWER_BODY_ORIGIN_X", "LOWER_BODY_START_Y", "LOWER_BODY_ORIGIN_Z")
    b1.SetOriginAndLengths(pt_orig1.Coordinates, "LOWER_BODY_LENGTH", "LOWER_BODY_HEIGHT", "LOWER_BODY_WIDTH")
    b1.OriginPoint = pt_orig1
    f_b1 = b1.CommitFeature()
    set_name(f_b1, "LOWER_BODY_BLOCK")
    b1.Destroy()
    main_body = f_b1.GetBodies()[0]
    print("  [OK] Feature: LOWER_BODY_BLOCK")

    # Associative vertical corner blend (Rule Type 8: Intersecting vertical faces)
    faces = list(main_body.GetFaces())
    v_faces = []
    for f in faces:
        ys = [v.Y for e in f.GetEdges() for v in e.GetVertices()]
        if ys and (max(ys) - min(ys)) > 20.0:
            v_faces.append(f)

    rules_c1 = []
    for i in range(len(v_faces)):
        for j in range(i + 1, len(v_faces)):
            try:
                r = part.ScRuleFactory.CreateRuleEdgeIntersect([v_faces[i]], [v_faces[j]])
                c_test = part.ScCollectors.CreateCollector()
                c_test.ReplaceRules([r], False)
                if len(c_test.GetObjects()) == 1:
                    rules_c1.append(r)
            except Exception:
                pass

    coll_c1 = part.ScCollectors.CreateCollector()
    coll_c1.ReplaceRules(rules_c1, False)
    eb1 = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    eb1.AddChainset(coll_c1, "LOWER_CORNER_R")
    f_eb1 = eb1.CommitFeature()
    set_name(f_eb1, "LOWER_BODY_CORNER_BLENDS")
    eb1.Destroy()
    print("  [OK] Feature: LOWER_BODY_CORNER_BLENDS (associative intersecting face rule)")

    # Associative Base End Blend (Rule Type 38: OuterEdgesOfFaces on bottom planar face)
    b_faces = [f for f in main_body.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    bot_face = min(b_faces, key=lambda f: min(v.Y for e in f.GetEdges() for v in e.GetVertices()))
    coll_base = part.ScCollectors.CreateCollector()
    coll_base.ReplaceRules([part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([bot_face])], False)
    eb_base = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    eb_base.AddChainset(coll_base, "BASE_END_BLEND_R")
    f_base_blend = eb_base.CommitFeature()
    set_name(f_base_blend, "LOWER_BODY_BASE_BLEND")
    eb_base.Destroy()
    print("  [OK] Feature: LOWER_BODY_BASE_BLEND (associative face-boundary rule)")

    # =========================================================================
    # 3. ZONE 2: CONTINUOUS PARTING SEAM NECK & UNITE
    # =========================================================================
    print("\n[3/7] Building Zone 2: SEAM_NECK_BLOCK & UNITE...")
    b_seam = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    b_seam.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
    pt_orig_seam = pt_assoc("SEAM_ORIGIN_X", "SEAM_START_Y", "SEAM_ORIGIN_Z")
    b_seam.SetOriginAndLengths(pt_orig_seam.Coordinates, "SEAM_LENGTH", "SEAM_HEIGHT", "SEAM_WIDTH")
    b_seam.OriginPoint = pt_orig_seam
    f_b_seam = b_seam.CommitFeature()
    set_name(f_b_seam, "SEAM_NECK_BLOCK")
    b_seam.Destroy()
    body_seam = f_b_seam.GetBodies()[0]

    seam_v_faces = []
    for f in body_seam.GetFaces():
        ys = [v.Y for e in f.GetEdges() for v in e.GetVertices()]
        if ys and (max(ys) - min(ys)) > 0.5:
            seam_v_faces.append(f)

    rules_seam = []
    for i in range(len(seam_v_faces)):
        for j in range(i + 1, len(seam_v_faces)):
            try:
                r = part.ScRuleFactory.CreateRuleEdgeIntersect([seam_v_faces[i]], [seam_v_faces[j]])
                c_test = part.ScCollectors.CreateCollector()
                c_test.ReplaceRules([r], False)
                if len(c_test.GetObjects()) == 1:
                    rules_seam.append(r)
            except Exception:
                pass

    if rules_seam:
        coll_seam = part.ScCollectors.CreateCollector()
        coll_seam.ReplaceRules(rules_seam, False)
        eb_seam = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        eb_seam.AddChainset(coll_seam, "SEAM_CORNER_R")
        f_eb_seam = eb_seam.CommitFeature()
        set_name(f_eb_seam, "SEAM_NECK_CORNER_BLENDS")
        eb_seam.Destroy()
        print("  [OK] Feature: SEAM_NECK_CORNER_BLENDS")

    u_seam = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_seam.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_seam.Target = main_body
    u_seam.Tools.Add(body_seam)
    f_u_seam = u_seam.CommitFeature()
    set_name(f_u_seam, "UNITE_SEAM_NECK")
    u_seam.Destroy()
    print("  [OK] Feature: UNITE_SEAM_NECK")

    # =========================================================================
    # 4. ZONE 3: LID LOWER RIM & UNITE
    # =========================================================================
    print("\n[4/7] Building Zone 3: LID_RIM_BLOCK, CORNER_BLENDS & UNITE...")
    b2 = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    b2.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
    pt_orig2 = pt_assoc("LID_RIM_ORIGIN_X", "LID_RIM_START_Y", "LID_RIM_ORIGIN_Z")
    b2.SetOriginAndLengths(pt_orig2.Coordinates, "LID_RIM_LENGTH", "LID_RIM_HEIGHT", "LID_RIM_WIDTH")
    b2.OriginPoint = pt_orig2
    f_b2 = b2.CommitFeature()
    set_name(f_b2, "LID_RIM_BLOCK")
    b2.Destroy()
    body_rim = f_b2.GetBodies()[0]
    print("  [OK] Feature: LID_RIM_BLOCK")

    rim_v_faces = []
    for f in body_rim.GetFaces():
        ys = [v.Y for e in f.GetEdges() for v in e.GetVertices()]
        if ys and (max(ys) - min(ys)) > 2.0:
            rim_v_faces.append(f)

    rules_rim = []
    for i in range(len(rim_v_faces)):
        for j in range(i + 1, len(rim_v_faces)):
            try:
                r = part.ScRuleFactory.CreateRuleEdgeIntersect([rim_v_faces[i]], [rim_v_faces[j]])
                c_test = part.ScCollectors.CreateCollector()
                c_test.ReplaceRules([r], False)
                if len(c_test.GetObjects()) == 1:
                    rules_rim.append(r)
            except Exception:
                pass

    coll_rim = part.ScCollectors.CreateCollector()
    coll_rim.ReplaceRules(rules_rim, False)
    eb_rim = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    eb_rim.AddChainset(coll_rim, "LID_RIM_CORNER_R")
    f_eb_rim = eb_rim.CommitFeature()
    set_name(f_eb_rim, "LID_RIM_CORNER_BLENDS")
    eb_rim.Destroy()
    print("  [OK] Feature: LID_RIM_CORNER_BLENDS")

    u1 = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u1.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u1.Target = main_body
    u1.Tools.Add(body_rim)
    f_u1 = u1.CommitFeature()
    set_name(f_u1, "UNITE_LID_RIM")
    u1.Destroy()
    print("  [OK] Feature: UNITE_LID_RIM")

    # =========================================================================
    # 5. ZONE 4: UPPER LID (BLOCK + CORNER BLENDS + TOP FACE BLEND + UNITE)
    # =========================================================================
    print("\n[5/7] Building Zone 4: LID_UPPER_BLOCK, BLENDS & UNITE...")
    b3 = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    b3.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
    pt_orig3 = pt_assoc("LID_UPPER_ORIGIN_X", "LID_UPPER_START_Y", "LID_UPPER_ORIGIN_Z")
    b3.SetOriginAndLengths(pt_orig3.Coordinates, "LID_UPPER_LENGTH", "LID_UPPER_HEIGHT", "LID_UPPER_WIDTH")
    b3.OriginPoint = pt_orig3
    f_b3 = b3.CommitFeature()
    set_name(f_b3, "LID_UPPER_BLOCK")
    b3.Destroy()
    body_upper = f_b3.GetBodies()[0]
    print("  [OK] Feature: LID_UPPER_BLOCK")

    upper_v_faces = []
    for f in body_upper.GetFaces():
        ys = [v.Y for e in f.GetEdges() for v in e.GetVertices()]
        if ys and (max(ys) - min(ys)) > 10.0:
            upper_v_faces.append(f)

    rules_upper = []
    for i in range(len(upper_v_faces)):
        for j in range(i + 1, len(upper_v_faces)):
            try:
                r = part.ScRuleFactory.CreateRuleEdgeIntersect([upper_v_faces[i]], [upper_v_faces[j]])
                c_test = part.ScCollectors.CreateCollector()
                c_test.ReplaceRules([r], False)
                if len(c_test.GetObjects()) == 1:
                    rules_upper.append(r)
            except Exception:
                pass

    coll_upper = part.ScCollectors.CreateCollector()
    coll_upper.ReplaceRules(rules_upper, False)
    eb_upper = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    eb_upper.AddChainset(coll_upper, "LID_UPPER_CORNER_R")
    f_eb_upper = eb_upper.CommitFeature()
    set_name(f_eb_upper, "LID_UPPER_CORNER_BLENDS")
    eb_upper.Destroy()
    print("  [OK] Feature: LID_UPPER_CORNER_BLENDS")

    # Associative blend on top planar face before boolean unite (Rule Type 38)
    top_faces_after_corner = [f for f in body_upper.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    top_face_final = max(top_faces_after_corner, key=lambda f: max(v.Y for e in f.GetEdges() for v in e.GetVertices()))
    coll_top = part.ScCollectors.CreateCollector()
    coll_top.ReplaceRules([part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([top_face_final])], False)
    eb_top = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    eb_top.AddChainset(coll_top, "LID_TOP_BLEND_R")
    f_top_blend = eb_top.CommitFeature()
    set_name(f_top_blend, "LID_TOP_BLEND")
    eb_top.Destroy()
    print("  [OK] Feature: LID_TOP_BLEND (associative face-boundary rule)")

    u2 = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u2.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u2.Target = main_body
    u2.Tools.Add(body_upper)
    f_u2 = u2.CommitFeature()
    set_name(f_u2, "UNITE_LID_UPPER")
    u2.Destroy()
    print("  [OK] Feature: UNITE_LID_UPPER")

    # =========================================================================
    # 6. ZONE 5: FRONT RECESSED POCKET (CUTOUT)
    # =========================================================================
    print("\n[6/7] Building Zone 5: FRONT_RECESS_BLOCK & SUBTRACT...")
    b_rec = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    b_rec.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
    pt_orig_rec = pt_assoc("RECESS_START_X", "RECESS_START_Y", "RECESS_FLOOR_Z")
    b_rec.SetOriginAndLengths(pt_orig_rec.Coordinates, "RECESS_WIDTH", "RECESS_HEIGHT", "RECESS_CUT_EXTENT")
    b_rec.OriginPoint = pt_orig_rec
    f_b_rec = b_rec.CommitFeature()
    set_name(f_b_rec, "FRONT_RECESS_BLOCK")
    b_rec.Destroy()
    tool_rec = f_b_rec.GetBodies()[0]

    s_rec = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    s_rec.Operation = NXOpen.Features.Feature.BooleanType.Subtract
    s_rec.Target = main_body
    s_rec.Tools.Add(tool_rec)
    f_s_rec = s_rec.CommitFeature()
    set_name(f_s_rec, "SUBTRACT_FRONT_RECESS")
    s_rec.Destroy()
    print("  [OK] Feature: SUBTRACT_FRONT_RECESS")

    # =========================================================================
    # 7. ZONE 6: FRONT LATCH BUTTON (BLOCK + BLENDS + UNITE)
    # =========================================================================
    print("\n[7/7] Building Zone 6: FRONT_BUTTON_BLOCK, BLENDS & UNITE...")
    b_btn = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    b_btn.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
    pt_orig_btn = pt_assoc("BUTTON_START_X", "BUTTON_START_Y", "BUTTON_BASE_Z")
    b_btn.SetOriginAndLengths(pt_orig_btn.Coordinates, "BUTTON_WIDTH", "BUTTON_HEIGHT", "BUTTON_THICKNESS")
    b_btn.OriginPoint = pt_orig_btn
    f_b_btn = b_btn.CommitFeature()
    set_name(f_b_btn, "FRONT_BUTTON_BLOCK")
    b_btn.Destroy()
    tool_btn = f_b_btn.GetBodies()[0]

    btn_v_faces = []
    for f in tool_btn.GetFaces():
        ys = [v.Y for e in f.GetEdges() for v in e.GetVertices()]
        if ys and (max(ys) - min(ys)) > 5.0:
            btn_v_faces.append(f)

    rules_btn = []
    for i in range(len(btn_v_faces)):
        for j in range(i + 1, len(btn_v_faces)):
            try:
                r = part.ScRuleFactory.CreateRuleEdgeIntersect([btn_v_faces[i]], [btn_v_faces[j]])
                c_test = part.ScCollectors.CreateCollector()
                c_test.ReplaceRules([r], False)
                if len(c_test.GetObjects()) == 1:
                    rules_btn.append(r)
            except Exception:
                pass

    if rules_btn:
        coll_btn = part.ScCollectors.CreateCollector()
        coll_btn.ReplaceRules(rules_btn, False)
        eb_btn = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        eb_btn.AddChainset(coll_btn, "BUTTON_TOP_BLEND_R")
        f_eb_btn = eb_btn.CommitFeature()
        set_name(f_eb_btn, "FRONT_BUTTON_CORNER_BLENDS")
        eb_btn.Destroy()
        print("  [OK] Feature: FRONT_BUTTON_CORNER_BLENDS")

    u_btn = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_btn.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_btn.Target = main_body
    u_btn.Tools.Add(tool_btn)
    f_u_btn = u_btn.CommitFeature()
    set_name(f_u_btn, "UNITE_FRONT_BUTTON")
    u_btn.Destroy()
    print("  [OK] Feature: UNITE_FRONT_BUTTON")

    # Export synchronized STL
    export_stl(session, part, main_body, out_stl)

    # Save Part
    part.Save(NXOpen.BasePart.SaveComponents.FalseValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("\n[COMPLETE] Model saved successfully to:", out_prt)
    part.Close(NXOpen.BasePart.CloseWholeTree.FalseValue, NXOpen.BasePart.CloseModified.CloseModified, None)


if __name__ == "__main__":
    main()
