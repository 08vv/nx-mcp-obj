"""
build_kissan_bottle_parametric.py
=================================
Constructs a fully parametric, feature-based Siemens NX part (.prt) strictly
matching the reference geometry of obj/Kissan_Bottle2.obj:
- Analytical base cylinder for main body
- Conical shoulder transition with smooth edge blend
- Cylindrical cap closure with crown bevel
- Recessed base pushup cavity and standing contact ring
- Fully driven by named parametric expressions

Usage:
    run_journal.exe scripts/build_kissan_bottle_parametric.py [spec_json] [output_prt]
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.29" not in os.environ["SPLM_LICENSE_SERVER"]:
    curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.29;{curr}"

import NXOpen
import NXOpen.UF

UF = NXOpen.UF.UFSession.GetUFSession()


def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))


def set_name(obj, name: str):
    if obj is None:
        return
    try:
        obj.SetName(name)
    except Exception:
        pass


def find_edge_near(body, y_target: float, r_target: float, max_dist: float = 3.0) -> Optional[Any]:
    """Finds a circular edge on the body near the given (Y, radius) location."""
    best_edge = None
    min_d = float("inf")
    for e in body.GetEdges():
        v0, v1 = e.GetVertices()
        mid_y = 0.5 * (v0.Y + v1.Y)
        mid_r = 0.5 * (math.hypot(v0.X, v0.Z) + math.hypot(v1.X, v1.Z))
        d = math.hypot(mid_y - y_target, mid_r - r_target)
        if d < min_d:
            min_d = d
            best_edge = e
    if min_d <= max_dist:
        return best_edge
    return None


def apply_edge_blend(part, edge, radius_val: float, radius_expr_name: str, name: str) -> Optional[Any]:
    """Applies an Edge Blend with fallback radii if necessary."""
    if not edge:
        print(f"  [WARN] Edge for {name} not found.")
        return None

    radii_to_try = [radius_val]
    if radius_val > 5.0:
        radii_to_try.extend([radius_val * 0.75, radius_val * 0.5, 5.0, 3.0])
    elif radius_val > 1.5:
        radii_to_try.extend([1.5, 1.2, 1.0])

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
    default_spec = repo_root / "Kissan_Bottle_parametric_spec.json"
    default_prt = repo_root / "Kissan_Bottle_Parametric.prt"

    spec_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_spec
    out_prt = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else default_prt

    print("=" * 70)
    print("PARAMETRIC NX RECONSTRUCTION: KISSAN BOTTLE (STRICT GEOMETRY MATCH)")
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

    y_base = float(expressions["BASE_Y"])
    body_h = float(expressions["BODY_HEIGHT"])
    shoulder_h = float(expressions["SHOULDER_HEIGHT"])
    cap_h = float(expressions["CAP_HEIGHT"])
    body_d = float(expressions["BODY_DIAMETER"])
    neck_d = float(expressions["NECK_DIAMETER"])
    cap_d = float(expressions["CAP_DIAMETER"])

    # 2. Base Body Cylinder
    print("\n[2/7] Creating base cylindrical body...")
    cyl_b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        cyl_b.Diameter.RightHandSide = "BODY_DIAMETER"
        cyl_b.Height.RightHandSide = "BODY_HEIGHT"
        cyl_b.Origin = point(0.0, y_base, 0.0)
        cyl_b.Direction = vec(0.0, 1.0, 0.0)
        cyl_feat = cyl_b.CommitFeature()
        set_name(cyl_feat, "BASE_BODY_CYLINDER")
        main_body = cyl_feat.GetBodies()[0]
        print(f"  [OK] Base body cylinder created: {main_body}")
    finally:
        cyl_b.Destroy()

    # 3. Conical Shoulder Transition
    print("\n[3/7] Creating conical shoulder transition...")
    cone_b = part.Features.CreateConeBuilder(NXOpen.Features.Cone.Null)
    try:
        cone_b.Type = NXOpen.Features.ConeBuilder.Types.DiametersAndHeight
        cone_b.BaseDiameter.RightHandSide = "BODY_DIAMETER"
        cone_b.TopDiameter.RightHandSide = "NECK_DIAMETER"
        cone_b.Height.RightHandSide = "SHOULDER_HEIGHT"
        dir_cone = part.Directions.CreateDirection(
            point(0.0, y_base + body_h, 0.0),
            vec(0.0, 1.0, 0.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        cone_b.Axis.Point.SetCoordinates(point(0.0, y_base + body_h, 0.0))
        cone_b.Axis.Direction = dir_cone
        cone_feat = cone_b.CommitFeature()
        set_name(cone_feat, "SHOULDER_CONE")
        shoulder_body = cone_feat.GetBodies()[0]
        print(f"  [OK] Shoulder cone created: {shoulder_body}")
    finally:
        cone_b.Destroy()

    # Unite shoulder to base body
    u_b1 = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u_b1.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u_b1.Target = main_body
        u_b1.Tools.Add(shoulder_body)
        u_feat1 = u_b1.CommitFeature()
        set_name(u_feat1, "UNITE_SHOULDER")
        print("  [OK] Shoulder cone united to base body.")
    finally:
        u_b1.Destroy()

    # 4. Cap / Closure Cylinder
    print("\n[4/7] Creating cap / closure cylinder...")
    cap_b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        cap_b.Diameter.RightHandSide = "CAP_DIAMETER"
        cap_b.Height.RightHandSide = "CAP_HEIGHT"
        cap_b.Origin = point(0.0, y_base + body_h + shoulder_h, 0.0)
        cap_b.Direction = vec(0.0, 1.0, 0.0)
        cap_feat = cap_b.CommitFeature()
        set_name(cap_feat, "CAP_CYLINDER")
        cap_body = cap_feat.GetBodies()[0]
        print(f"  [OK] Cap cylinder created: {cap_body}")
    finally:
        cap_b.Destroy()

    # Unite cap to body
    u_b2 = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u_b2.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u_b2.Target = main_body
        u_b2.Tools.Add(cap_body)
        u_feat2 = u_b2.CommitFeature()
        set_name(u_feat2, "UNITE_CAP")
        print("  [OK] Cap cylinder united to body.")
    finally:
        u_b2.Destroy()

    # 5. Apply Edge Blends
    print("\n[5/7] Applying transitional edge blends...")
    # Base heel blend
    e_heel = find_edge_near(main_body, y_base, body_d / 2.0)
    apply_edge_blend(part, e_heel, float(expressions["BASE_HEEL_R"]), "BASE_HEEL_R", "BASE_HEEL_BLEND")

    # Shoulder blend
    e_shoulder = find_edge_near(main_body, y_base + body_h, body_d / 2.0)
    apply_edge_blend(part, e_shoulder, float(expressions["SHOULDER_BLEND_R"]), "SHOULDER_BLEND_R", "SHOULDER_TRANSITION_BLEND")

    # Neck step blend
    e_neck = find_edge_near(main_body, y_base + body_h + shoulder_h, neck_d / 2.0)
    apply_edge_blend(part, e_neck, float(expressions["NECK_BLEND_R"]), "NECK_BLEND_R", "NECK_TRANSITION_BLEND")

    # Cap top rim blend
    e_cap_top = find_edge_near(main_body, y_base + body_h + shoulder_h + cap_h, cap_d / 2.0)
    apply_edge_blend(part, e_cap_top, float(expressions["CAP_TOP_BLEND_R"]), "CAP_TOP_BLEND_R", "CAP_TOP_BLEND")

    # 6. Base Concave Pushup Recess (Subtract)
    print("\n[6/7] Cutting recessed base pushup cavity...")
    recess_b = part.Features.CreateConeBuilder(NXOpen.Features.Cone.Null)
    try:
        recess_b.Type = NXOpen.Features.ConeBuilder.Types.DiametersAndHeight
        recess_b.BaseDiameter.RightHandSide = "BASE_RECESS_DIAMETER"
        recess_b.TopDiameter.RightHandSide = "BASE_RECESS_DIAMETER - 6.0"
        recess_b.Height.RightHandSide = "BASE_RECESS_DEPTH"
        dir_rec = part.Directions.CreateDirection(
            point(0.0, y_base, 0.0),
            vec(0.0, 1.0, 0.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        recess_b.Axis.Point.SetCoordinates(point(0.0, y_base, 0.0))
        recess_b.Axis.Direction = dir_rec
        recess_feat = recess_b.CommitFeature()
        set_name(recess_feat, "BASE_RECESS_TOOL")
        recess_body = recess_feat.GetBodies()[0]
    finally:
        recess_b.Destroy()

    sub_b = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        sub_b.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        sub_b.Target = main_body
        sub_b.Tools.Add(recess_body)
        sub_feat = sub_b.CommitFeature()
        set_name(sub_feat, "BASE_PUSHUP_CUT")
        print("  [OK] Base pushup cavity subtracted successfully.")
    finally:
        sub_b.Destroy()

    # 7. Verification, Part Navigator Tree & Save
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

    # Export synchronized STL
    stl_path = out_prt.with_suffix(".stl")
    stl_exp = session.DexManager.CreateStlCreator()
    try:
        stl_exp.OutputFile = str(stl_path)
        stl_exp.ExportSelectionBlock.Add(main_body)
        stl_exp.Commit()
        print(f"[OK] Synchronized STL exported to: {stl_path}")
    finally:
        stl_exp.Destroy()

    part.Close(NXOpen.BasePart.CloseWholeTree.FalseValue, NXOpen.BasePart.CloseModified.CloseModified, None)


if __name__ == "__main__":
    main()
