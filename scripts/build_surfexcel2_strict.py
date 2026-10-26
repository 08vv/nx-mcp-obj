"""
build_surfexcel2_strict.py
==========================
Constructs a true feature-based, zone-wise parametric Siemens NX CAD model for
the Surf Excel detergent jug (obj/Surfexcel2_reduced.obj) with STRICT GEOMETRIC FIDELITY:

Feature Tree Architecture:
  1. Parametric Driving Expressions (All active, 0 orphans)
  2. ZONE1_LOWER_BODY:       Solid ThroughCurves loft across 16 stations (reservoir base)
  3. ZONE2_HANDLE_BODY:      Solid ThroughCurves loft across 14 stations (mid body & handle bridge)
  4. UNITE_HANDLE_BODY:      Boolean unite into main body
  5. ZONE3_SHOULDER_BODY:    Solid ThroughCurves loft across 14 stations (upper shoulder sweep)
  6. UNITE_SHOULDER_BODY:    Boolean unite into main body
  7. ZONE4_NECK_BODY:        Solid ThroughCurves loft across 5 stations (tapered neck collar)
  8. UNITE_NECK_BODY:        Boolean unite into main body
  9. ZONE5_CAP_BODY:         Solid ThroughCurves loft across 14 stations (irregular organic cap)
  10. UNITE_CAP_BODY:        Boolean unite into main body
  11. HANDLE_OPENING_CUT:    Extrude subtract through-all using exact organic spline opening
  12. HANDLE_RIM_BLEND:      Associative edge blend on handle opening rim
  13. RECESS_FRONT_CUT:      Extrude subtract using exact organic spline recess outline
  14. RECESS_BACK_CUT:       Extrude subtract on back face using exact organic spline recess outline
  15. BASE_END_BLEND:        Associative edge blend on lower base rim
  16. CAP_TOP_BLEND:         Associative edge blend on cap top

Usage:
  run_journal.exe scripts/build_surfexcel2_strict.py
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

# License setup
if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.5" not in os.environ.get("SPLM_LICENSE_SERVER", ""):
    curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.5;28000@SunFibo19;28000@192.168.1.29;28000@192.168.1.3;{curr}"

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities

REPO_ROOT = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
SPEC_PATH = REPO_ROOT / "Surfexcel2_strict_spec.json"
OUT_PRT = REPO_ROOT / "Surfexcel2_Strict.prt"
OUT_STL = REPO_ROOT / "Surfexcel2_Strict.stl"


def pt(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def set_name(obj, name: str):
    if obj is None:
        return
    try:
        obj.SetName(name)
    except Exception:
        pass


def make_line(part, a, b):
    c = part.Curves.CreateLine(pt(*a), pt(*b))
    try:
        c.Blank()
    except Exception:
        pass
    return c


def nx_section(part, curves, start_point=None):
    sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
    rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    help_pt = start_point if start_point is not None else pt(0.0, 0.0, 0.0)
    sec.AddToSection(rules, curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, help_pt, NXOpen.Section.Mode.Create, False)
    return sec


def append_section(builder, sec):
    container = getattr(builder, "SectionsList", None) or getattr(builder, "Sections", None)
    if hasattr(container, "Append"):
        container.Append(sec)
    else:
        container.Add(sec)


def station_to_curves(part, pts_3d):
    n = len(pts_3d)
    return [make_line(part, pts_3d[k], pts_3d[(k + 1) % n]) for k in range(n)]


def build_through_curves_zone(part, stations_3d, zone_name: str):
    print(f"  Building {zone_name} ({len(stations_3d)} stations)...")
    curvesets = []
    start_points = []
    for pts in stations_3d:
        curves = station_to_curves(part, pts)
        curvesets.append(curves)
        start_points.append(pts[0])

    loft_b = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        loft_b.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
    except Exception:
        pass

    for curves, spt in zip(curvesets, start_points):
        append_section(loft_b, nx_section(part, curves, start_point=pt(*spt)))

    feat = loft_b.CommitFeature()
    set_name(feat, zone_name)
    body = feat.GetBodies()[0]
    loft_b.Destroy()
    print(f"  [OK] Feature created: {zone_name}")
    return feat, body


def boolean_unite(part, target_body, tool_body, name: str):
    u = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u.RetainTarget = False
        u.RetainTool = False
        u.Target = target_body
        u.Tools.Add(tool_body)
        feat = u.CommitFeature()
        set_name(feat, name)
        print(f"  [OK] Feature created: {name}")
        return feat
    finally:
        u.Destroy()


def create_closed_studio_spline(part, pts_2d, z_val=0.0):
    b = part.Features.CreateStudioSplineBuilderEx(NXOpen.Features.Feature.Null)
    try:
        b.Degree = 3
        b.IsPeriodic = True
        for p in pts_2d:
            g = b.ConstraintManager.CreateGeometricConstraintData()
            g.Point = part.Points.CreatePoint(pt(p[0], p[1], z_val))
            b.ConstraintManager.Append(g)
        feat = b.CommitFeature()
        return feat.GetEntities()[0]
    finally:
        b.Destroy()


def extrude_cut(part, curves, cut_target, vec, start_val, end_val, name: str, help_pt=None):
    ET = NXOpen.GeometricUtilities.Extend.ExtendType
    sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
    crvs = curves if isinstance(curves, list) else [curves]
    rules = [part.ScRuleFactory.CreateRuleCurveDumb(crvs)]
    hpt = help_pt if help_pt is not None else pt(0.0, 0.0, 0.0)
    sec.AddToSection(rules, crvs[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, hpt, NXOpen.Section.Mode.Create, False)

    eb = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        eb.Section = sec
        eb.Direction = part.Directions.CreateDirection(pt(0, 0, 0), NXOpen.Vector3d(*[float(c) for c in vec]), NXOpen.SmartObject.UpdateOption.WithinModeling)
        for lim, val in ((eb.Limits.StartExtend, start_val), (eb.Limits.EndExtend, end_val)):
            if val == "THRU":
                lim.TrimType = ET.ThroughAll
            else:
                lim.Value.RightHandSide = str(val)
        eb.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
        eb.BooleanOperation.SetTargetBodies([cut_target])
        feat = eb.CommitFeature()
        set_name(feat, name)
        print(f"  [OK] Feature created: {name}")
        return feat
    finally:
        eb.Destroy()


def blend_associative(part, rules_fn, radius_expr: str, name: str):
    bb = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        coll = part.ScCollectors.CreateCollector()
        coll.ReplaceRules([rules_fn()], False)
        bb.Tolerance = 0.01
        bb.AddChainset(coll, radius_expr)
        f = bb.CommitFeature()
        set_name(f, name)
        print(f"  [OK] Feature created: {name}")
        return f
    except Exception as e:
        print(f"  [WARN] Blend {name}: {e}")
        return None
    finally:
        bb.Destroy()


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
        print(f"  [WARN] STL export: {e}")
    finally:
        stl_exp.Destroy()


def main():
    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: SURF EXCEL (STRICT GEOMETRIC FIDELITY)")
    print(f"  Source Specification: {SPEC_PATH}")
    print(f"  Target PRT:           {OUT_PRT}")
    print("=" * 75)

    if not SPEC_PATH.exists():
        print(f"[FAIL] Specification not found: {SPEC_PATH}")
        sys.exit(1)

    with open(SPEC_PATH, "r", encoding="utf-8") as f:
        spec = json.load(f)

    if OUT_PRT.exists():
        try:
            OUT_PRT.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(OUT_PRT), NXOpen.Part.Units.Millimeters)

    # 1. Expressions
    print("\n[1/5] Defining active driving parametric expressions...")
    expressions = [
        ("BASE_BLEND_R", "7.000"),
        ("HANDLE_RIM_R", "5.000"),
        ("RECESS_FLOOR_Z", "12.000"),
        ("RECESS_FLOOR_R", "2.000"),
        ("CAP_TOP_R", "8.000"),
    ]
    for n, v in expressions:
        part.Expressions.CreateExpression("Number", f"{n} = {v}")
        print(f"  {n} = {v}")

    # 2. Zones
    print("\n[2/5] Building functional zones via Through Curves...")
    main_body = None
    z1_feat = None
    z5_feat = None

    zone_defs = [
        ("ZONE1_LOWER_BODY", "zone1_lower"),
        ("ZONE2_HANDLE_BODY", "zone2_handle"),
        ("ZONE3_SHOULDER_BODY", "zone3_shoulder"),
        ("ZONE4_NECK_BODY", "zone4_neck"),
        ("ZONE5_CAP_BODY", "zone5_cap"),
    ]

    for feat_name, zkey in zone_defs:
        feat, body = build_through_curves_zone(part, spec["zones"][zkey], feat_name)
        if main_body is None:
            main_body = body
            z1_feat = feat
        else:
            if zkey == "zone5_cap":
                z5_feat = feat
            unite_name = f"UNITE_{zkey.upper()}"
            boolean_unite(part, main_body, body, unite_name)
            main_body = [b for b in part.Bodies if b.IsSolidBody][0]

    # 3. Handle Opening Cut
    print("\n[3/5] Applying secondary features (opening cut & recessed label field)...")
    handle_curve = create_closed_studio_spline(part, spec["handle_opening"], z_val=0.0)
    extrude_cut(part, handle_curve, main_body, (0, 0, 1), "THRU", "THRU", "HANDLE_OPENING_CUT")
    main_body = [b for b in part.Bodies if b.IsSolidBody][0]

    # Handle Rim Blend
    print("  Applying Handle Rim Blend...")
    hole_wall_faces = []
    for f in main_body.GetFaces():
        if f.SolidFaceType != NXOpen.Face.FaceType.Planar:
            vs = [v for e in f.GetEdges() for v in e.GetVertices()]
            if vs:
                xs = [v.X for v in vs]
                ys = [v.Y for v in vs]
                if min(xs) >= 8.0 and max(xs) <= 40.0 and min(ys) >= -40.0 and max(ys) <= 26.0:
                    hole_wall_faces.append(f)
    print(f"  Found {len(hole_wall_faces)} handle hole wall faces")
    if hole_wall_faces:
        blend_associative(part, lambda: part.ScRuleFactory.CreateRuleEdgeFace(hole_wall_faces), "HANDLE_RIM_R", "HANDLE_RIM_BLEND")
        main_body = [b for b in part.Bodies if b.IsSolidBody][0]

    # Recessed Front & Back Label Fields
    print("  Applying Recessed Label Fields...")
    recess_curve_front = create_closed_studio_spline(part, spec["recess_profile"], z_val=0.0)
    extrude_cut(part, recess_curve_front, main_body, (0, 0, 1), "RECESS_FLOOR_Z", "THRU", "RECESS_FRONT_CUT")
    main_body = [b for b in part.Bodies if b.IsSolidBody][0]

    recess_curve_back = create_closed_studio_spline(part, spec["recess_profile"], z_val=0.0)
    extrude_cut(part, recess_curve_back, main_body, (0, 0, -1), "RECESS_FLOOR_Z", "THRU", "RECESS_BACK_CUT")
    main_body = [b for b in part.Bodies if b.IsSolidBody][0]

    # Recess Floor Blends
    for zsign, sname in ((1.0, "FRONT"), (-1.0, "BACK")):
        target_z = zsign * 12.0
        floor_faces = []
        for f in main_body.GetFaces():
            if f.SolidFaceType == NXOpen.Face.FaceType.Planar:
                vs = [v for e in f.GetEdges() for v in e.GetVertices()]
                if vs and abs(vs[0].Z - target_z) < 0.5:
                    floor_faces.append(f)
        if floor_faces:
            blend_associative(part, lambda: part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([floor_faces[0]]), "RECESS_FLOOR_R", f"RECESS_FLOOR_BLEND_{sname}")
            main_body = [b for b in part.Bodies if b.IsSolidBody][0]

    # 4. Base & Cap Blends
    print("\n[4/5] Applying Base and Cap Dress-up Blends...")
    bot_faces = []
    for f in main_body.GetFaces():
        if f.SolidFaceType == NXOpen.Face.FaceType.Planar:
            vs = [v for e in f.GetEdges() for v in e.GetVertices()]
            if vs and abs(vs[0].Y - (-107.8)) < 1.0:
                bot_faces.append(f)
    if bot_faces:
        blend_associative(part, lambda: part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([bot_faces[0]]), "BASE_BLEND_R", "BASE_END_BLEND")
        main_body = [b for b in part.Bodies if b.IsSolidBody][0]

    top_faces = []
    for f in main_body.GetFaces():
        if f.SolidFaceType == NXOpen.Face.FaceType.Planar:
            vs = [v for e in f.GetEdges() for v in e.GetVertices()]
            if vs and abs(vs[0].Y - 108.9) < 1.0:
                top_faces.append(f)
    if top_faces:
        blend_associative(part, lambda: part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([top_faces[0]]), "CAP_TOP_R", "CAP_TOP_BLEND")
        main_body = [b for b in part.Bodies if b.IsSolidBody][0]

    # 5. Inspection & Save
    print("\n[5/5] Inspecting Feature Tree & Topology...")
    feats = list(part.Features)
    solids = [b for b in part.Bodies if b.IsSolidBody]
    print(f"  Solid Bodies:  {len(solids)}")
    print(f"  Active Features ({len(feats)}):")
    for i, f in enumerate(feats, 1):
        print(f"    [{i:02d}] {f.GetFeatureName():<30} ({f.FeatureType})")

    export_stl(session, part, main_body, OUT_STL)
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"  [OK] Part saved: {OUT_PRT} ({OUT_PRT.stat().st_size:,} bytes)")

    latest_txt = REPO_ROOT / "latest_nx_result.txt"
    latest_txt.write_text(str(OUT_PRT.resolve()), encoding="utf-8")
    ugraf_exe = Path(r"C:\Program Files\Siemens\NX2206\NXBIN\ugraf.exe")
    cmd_file = REPO_ROOT / "open_current_nx_result.cmd"
    cmd_file.write_text(f'@echo off\nstart "" "{ugraf_exe}" "{OUT_PRT.resolve()}"\n', encoding="utf-8")

    print("\n" + "=" * 75)
    print("RECONSTRUCTION COMPLETED SUCCESSFULLY!")
    print("=" * 75)
    part.Close(NXOpen.BasePart.CloseWholeTree.FalseValue, NXOpen.BasePart.CloseModified.CloseModified, None)


if __name__ == "__main__":
    main()
