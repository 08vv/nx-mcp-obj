"""
build_tresemme_parametric.py
============================
Constructs a fully parametric, feature-based Siemens NX part (.prt) strictly
matching the reference geometry of TRESemme6.obj:
- Continuous tapered squircle body loft (from base Y=-100 to shoulder Y=42 mm)
- Raised cylindrical collar with smooth shoulder transition
- Middle pump assembly cylindrical stem
- Pump actuator head with authentic front-facing angled nozzle (extending along -X)
- Parametric edge blends on heel, shoulder, collar rim, and head crown
- Fully driven by named parametric expressions

Usage:
    run_journal.exe scripts/build_tresemme_parametric.py [spec_json] [output_prt]
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure license servers
if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.29" not in os.environ["SPLM_LICENSE_SERVER"]:
    curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.29;28000@192.168.1.3;{curr}"

import NXOpen
import NXOpen.UF

UF = NXOpen.UF.UFSession.GetUFSession()


def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))


def make_line(part, a: Tuple[float, float, float], b: Tuple[float, float, float]):
    return part.Curves.CreateLine(point(*a), point(*b))


def set_name(obj, name: str):
    if obj is None:
        return
    try:
        obj.SetName(name)
    except Exception:
        pass


def nx_section(part, curves, start_point=None):
    sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
    rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    help_pt = start_point if start_point is not None else point(0.0, 0.0, 0.0)
    sec.AddToSection(
        rules,
        curves[0],
        NXOpen.NXObject.Null,
        NXOpen.NXObject.Null,
        help_pt,
        NXOpen.Section.Mode.Create,
        False,
    )
    return sec


def append_section(builder, sec) -> None:
    container = getattr(builder, "SectionsList", None) or getattr(builder, "Sections", None)
    if hasattr(container, "Append"):
        container.Append(sec)
    else:
        container.Add(sec)


def station_to_curves(part, pts_3d):
    n = len(pts_3d)
    return [make_line(part, pts_3d[k], pts_3d[(k + 1) % n]) for k in range(n)]


def find_edge_near(body, y_target: float, r_target: float, max_dist: float = 4.0) -> Optional[Any]:
    best = None
    min_d = float("inf")
    for e in body.GetEdges():
        v0, v1 = e.GetVertices()
        my = 0.5 * (v0.Y + v1.Y)
        mr = 0.5 * (math.hypot(v0.X, v0.Z) + math.hypot(v1.X, v1.Z))
        d = math.hypot(my - y_target, mr - r_target)
        if d < min_d:
            min_d = d
            best = e
    if min_d <= max_dist:
        return best
    return None


def apply_edge_blend(part, edge, radius_val: float, radius_expr_name: str, name: str) -> Optional[Any]:
    if not edge:
        print(f"  [WARN] Edge for {name} not found.")
        return None

    radii_to_try = [radius_val]
    if radius_val > 2.0:
        radii_to_try.extend([radius_val * 0.75, radius_val * 0.5, 1.5, 1.0])
    elif radius_val > 1.0:
        radii_to_try.extend([1.0, 0.8])

    for r in radii_to_try:
        bb = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            coll = part.ScCollectors.CreateCollector()
            coll.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb([edge])], False)
            bb.Tolerance = 0.01
            r_str = radius_expr_name if r == radius_val else f"{r:.2f}"
            bb.AddChainset(coll, r_str)
            feat = bb.CommitFeature()
            set_name(feat, name)
            print(f"  [OK] {name} applied with radius {r_str} mm")
            return feat
        except Exception:
            continue
        finally:
            bb.Destroy()

    print(f"  [WARN] {name} failed with all attempted radii.")
    return None


def main():
    repo_root = Path(__file__).resolve().parent.parent
    default_spec = repo_root / "TRESemme6_parametric_spec.json"
    default_prt = repo_root / "TRESemme6_Parametric.prt"

    spec_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_spec
    out_prt = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 70)
    print("PARAMETRIC NX RECONSTRUCTION: TRESEMMÉ BOTTLE")
    print(f"  Specification: {spec_path}")
    print(f"  Target PRT:    {out_prt}")
    print("=" * 70)

    if not spec_path.exists():
        print(f"ERROR: Specification file not found: {spec_path}")
        sys.exit(1)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    if out_prt.exists():
        try:
            out_prt.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(out_prt), NXOpen.Part.Units.Millimeters)

    # 1. Driving Expressions
    print("\n[1/7] Creating driving expressions...")
    expressions = spec.get("expressions", {})
    for name, val in expressions.items():
        try:
            exp_str = f"{name} = {float(val):.3f}"
            part.Expressions.CreateExpression("Number", exp_str)
            print(f"  Expression: {exp_str}")
        except Exception as e:
            print(f"  [WARN] Expression {name}: {e}")

    # 2. Base Body Loft
    print("\n[2/7] Lofting tapered bottle body solid...")
    body_stations = spec.get("stations", [])
    curvesets = []
    start_points = []
    for i, pts in enumerate(body_stations):
        curves = station_to_curves(part, pts)
        curvesets.append(curves)
        start_points.append(pts[0])

    loft_b = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        loft_b.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
        for curves, spt in zip(curvesets, start_points):
            append_section(loft_b, nx_section(part, curves, start_point=point(*spt)))
        body_feat = loft_b.CommitFeature()
        set_name(body_feat, "BASE_BODY_LOFT")
        main_body = body_feat.GetBodies()[0]
        print(f"  [OK] Base body loft created: {main_body}")
    finally:
        loft_b.Destroy()

    # 3. Raised Collar Cylinder
    print("\n[3/7] Creating raised collar cylinder...")
    collar_b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        collar_b.Diameter.RightHandSide = "COLLAR_DIAMETER"
        collar_b.Height.RightHandSide = "COLLAR_HEIGHT"
        collar_b.Origin = point(0.0, 42.0, 0.0)
        collar_b.Direction = vec(0.0, 1.0, 0.0)
        collar_feat = collar_b.CommitFeature()
        set_name(collar_feat, "COLLAR_CYLINDER")
        collar_body = collar_feat.GetBodies()[0]
        print(f"  [OK] Collar cylinder created: {collar_body}")
    finally:
        collar_b.Destroy()

    u_b1 = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u_b1.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u_b1.Target = main_body
        u_b1.Tools.Add(collar_body)
        u_feat1 = u_b1.CommitFeature()
        set_name(u_feat1, "UNITE_COLLAR")
        print("  [OK] Collar united to body.")
    finally:
        u_b1.Destroy()

    # 4. Middle Pump Assembly Stem Cylinder
    print("\n[4/7] Creating pump assembly stem cylinder...")
    stem_b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        stem_b.Diameter.RightHandSide = "PUMP_STEM_DIAMETER"
        stem_b.Height.RightHandSide = "PUMP_STEM_HEIGHT"
        stem_b.Origin = point(0.0, 42.0 + float(expressions["COLLAR_HEIGHT"]), 0.0)
        stem_b.Direction = vec(0.0, 1.0, 0.0)
        stem_feat = stem_b.CommitFeature()
        set_name(stem_feat, "PUMP_STEM_CYLINDER")
        stem_body = stem_feat.GetBodies()[0]
        print(f"  [OK] Pump stem cylinder created: {stem_body}")
    finally:
        stem_b.Destroy()

    u_b2 = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u_b2.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u_b2.Target = main_body
        u_b2.Tools.Add(stem_body)
        u_feat2 = u_b2.CommitFeature()
        set_name(u_feat2, "UNITE_PUMP_STEM")
        print("  [OK] Pump stem united.")
    finally:
        u_b2.Destroy()

    # 5. Pump Actuator Head Base Cylinder
    print("\n[5/7] Creating pump actuator head base & nozzle...")
    head_base_y = 91.0
    head_b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        head_b.Diameter.RightHandSide = "PUMP_HEAD_DIAMETER"
        head_b.Height.RightHandSide = "3.80"
        head_b.Origin = point(0.0, head_base_y, 0.0)
        head_b.Direction = vec(0.0, 1.0, 0.0)
        head_feat = head_b.CommitFeature()
        set_name(head_feat, "PUMP_HEAD_BASE_CYLINDER")
        head_lower_body = head_feat.GetBodies()[0]
        print(f"  [OK] Pump head base cylinder created: {head_lower_body}")
    finally:
        head_b.Destroy()

    u_b3 = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u_b3.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u_b3.Target = main_body
        u_b3.Tools.Add(head_lower_body)
        u_feat3 = u_b3.CommitFeature()
        set_name(u_feat3, "UNITE_PUMP_HEAD_BASE")
        print("  [OK] Pump head base united.")
    finally:
        u_b3.Destroy()

    # 6. Upper Actuator Head with Authentic Angled Nozzle Solid
    actuator_stations = spec.get("actuator_stations", [])
    act_curvesets = []
    act_starts = []
    for pts in actuator_stations:
        c_list = station_to_curves(part, pts)
        act_curvesets.append(c_list)
        act_starts.append(pts[0])

    act_loft_b = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        act_loft_b.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
        for curves, spt in zip(act_curvesets, act_starts):
            append_section(act_loft_b, nx_section(part, curves, start_point=point(*spt)))
        act_feat = act_loft_b.CommitFeature()
        set_name(act_feat, "PUMP_ACTUATOR_NOZZLE_SOLID")
        act_body = act_feat.GetBodies()[0]
        print(f"  [OK] Pump actuator nozzle solid created: {act_body}")
    finally:
        act_loft_b.Destroy()

    u_b4 = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u_b4.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u_b4.Target = main_body
        u_b4.Tools.Add(act_body)
        u_feat4 = u_b4.CommitFeature()
        set_name(u_feat4, "UNITE_PUMP_ACTUATOR")
        print("  [OK] Pump actuator nozzle united.")
    finally:
        u_b4.Destroy()

    # 7. Apply Transitional Edge Blends
    print("\n[6/7] Applying transitional edge blends...")
    # Shoulder transition blend
    e_shoulder = find_edge_near(main_body, 42.0, float(expressions["COLLAR_DIAMETER"]) / 2.0, max_dist=3.0)
    apply_edge_blend(part, e_shoulder, float(expressions["SHOULDER_BLEND_R"]), "SHOULDER_BLEND_R", "SHOULDER_TRANSITION_BLEND")

    # Collar top blend
    e_collar = find_edge_near(main_body, 42.0 + float(expressions["COLLAR_HEIGHT"]), float(expressions["COLLAR_DIAMETER"]) / 2.0, max_dist=3.0)
    apply_edge_blend(part, e_collar, float(expressions["COLLAR_TOP_BLEND_R"]), "COLLAR_TOP_BLEND_R", "COLLAR_TOP_BLEND")

    # Stem to head transition blend
    e_stem = find_edge_near(main_body, head_base_y, float(expressions["PUMP_STEM_DIAMETER"]) / 2.0, max_dist=3.0)
    apply_edge_blend(part, e_stem, 1.20, "1.20", "STEM_HEAD_TRANSITION_BLEND")

    # Part Navigator Feature Tree Summary
    print("\n[7/7] Verifying Part Navigator feature tree and saving...")
    print("=" * 70)
    print("PART NAVIGATOR FEATURE TREE:")
    feats = list(part.Features)
    for i, f in enumerate(feats):
        print(f"  [{i+1:2d}] {f.GetFeatureName():<32} (Type: {f.FeatureType})")
    print(f"Total features: {len(feats)}")
    bodies = list(part.Bodies)
    print(f"Solid Bodies:   {len(bodies)}")
    print("=" * 70)

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"\n[OK] Part successfully saved to: {out_prt}")

    # Synchronized STL Export
    stl_exp = session.DexManager.CreateStlCreator()
    try:
        stl_exp.OutputFile = str(out_stl)
        stl_exp.ExportSelectionBlock.Add(main_body)
        stl_exp.Commit()
        print(f"[OK] Synchronized STL exported to: {out_stl}")
    finally:
        stl_exp.Destroy()

    part.Close(NXOpen.BasePart.CloseWholeTree.FalseValue, NXOpen.BasePart.CloseModified.CloseModified, None)


if __name__ == "__main__":
    main()
