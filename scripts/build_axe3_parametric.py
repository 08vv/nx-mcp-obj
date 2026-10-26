"""
build_axe3_parametric.py
========================
Constructs a fully parametric, feature-based Siemens NX part (.prt) strictly
matching the reference geometry of Axe3.obj:
- Straight cylindrical lower canister (Dia ~77.14 mm)
- Narrower neck waist section (Dia ~71.72 mm)
- Smooth shoulder transition (Dia ~77.0 mm)
- Large cylindrical cap (Dia ~76.8 mm, Height ~67.46 mm)
- 40 dense vertical flutes/grooves around lower portion of cap (depth ~0.60 mm, height ~40.5 mm)
- Smooth upper portion of cap (Height ~23.5 mm)
- Concave bottom dome cavity cut (Depth ~6.70 mm)
- Rounded heel and cap crown edge blends
- Fully driven by named parametric expressions

Usage:
    run_journal.exe scripts/build_axe3_parametric.py [spec_json] [output_prt]
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
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


def set_name(obj, name: str):
    if obj is None:
        return
    try:
        obj.SetName(name)
    except Exception:
        pass


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


def find_circular_edge_near(body, y_target: float, r_target: float, max_dist: float = 3.0) -> Optional[Any]:
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


def main():
    repo_root = Path(__file__).resolve().parent.parent
    default_spec = repo_root / "Axe3_parametric_spec.json"
    default_prt = repo_root / "Axe3_Parametric.prt"

    spec_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_spec
    out_prt = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 70)
    print("PARAMETRIC NX RECONSTRUCTION: AXE BODY SPRAY CAN")
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
    print("\n[1/8] Creating driving expressions...")
    expressions = spec.get("expressions", {})
    for name, val in expressions.items():
        try:
            rhs = int(val) if name == "RIB_COUNT" else float(val)
            part.Expressions.CreateExpression("Number", f"{name} = {rhs}")
            print(f"  Expression: {name} = {rhs}")
        except Exception as e:
            print(f"  [WARN] Expression {name}: {e}")

    base_y = float(expressions["BASE_Y"])
    body_h = float(expressions["BODY_HEIGHT"])
    waist_h = float(expressions["WAIST_HEIGHT"])
    cap_h = float(expressions["CAP_HEIGHT"])
    rib_h = float(expressions["RIB_HEIGHT"])
    rib_depth = float(expressions["RIB_DEPTH"])
    rib_cutter_dia = float(expressions["RIB_CUTTER_DIA"])
    n_ribs = int(expressions["RIB_COUNT"])

    # 2. Base Cylindrical Canister Body
    print("\n[2/8] Creating base cylindrical body...")
    body_b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    body_b.Diameter.RightHandSide = "BODY_DIAMETER"
    body_b.Height.RightHandSide = "BODY_HEIGHT"
    body_b.Origin = point(0.0, base_y, 0.0)
    body_b.Direction = vec(0.0, 1.0, 0.0)
    body_feat = body_b.CommitFeature()
    set_name(body_feat, "BASE_BODY_CYLINDER")
    main_body = body_feat.GetBodies()[0]
    body_b.Destroy()
    print("  [OK] Base body cylinder created.")

    # 3. Narrower Neck Waist Section (overlapping 1mm into body)
    print("\n[3/8] Creating narrower neck section...")
    neck_b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    neck_b.Diameter.RightHandSide = "WAIST_DIAMETER"
    neck_b.Height.RightHandSide = "WAIST_HEIGHT + 1.0"
    neck_b.Origin = point(0.0, 9.0, 0.0)
    neck_b.Direction = vec(0.0, 1.0, 0.0)
    neck_feat = neck_b.CommitFeature()
    set_name(neck_feat, "NECK_WAIST_CYLINDER")
    neck_body = neck_feat.GetBodies()[0]
    neck_b.Destroy()

    u_b1 = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_b1.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_b1.Target = main_body
    u_b1.Tools.Add(neck_body)
    u_feat1 = u_b1.CommitFeature()
    set_name(u_feat1, "UNITE_NECK")
    main_body = u_feat1.GetBodies()[0]
    u_b1.Destroy()
    print("  [OK] Neck united to main body.")

    # 4. Shoulder Transition (overlapping 1mm into neck)
    print("\n[4/8] Creating shoulder transition...")
    sh_b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    sh_b.Diameter.RightHandSide = "SHOULDER_DIAMETER"
    sh_b.Height.RightHandSide = "3.0"
    sh_b.Origin = point(0.0, 29.0, 0.0)
    sh_b.Direction = vec(0.0, 1.0, 0.0)
    sh_feat = sh_b.CommitFeature()
    set_name(sh_feat, "SHOULDER_CYLINDER")
    sh_body = sh_feat.GetBodies()[0]
    sh_b.Destroy()

    u_b2 = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_b2.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_b2.Target = main_body
    u_b2.Tools.Add(sh_body)
    u_feat2 = u_b2.CommitFeature()
    set_name(u_feat2, "UNITE_SHOULDER")
    main_body = u_feat2.GetBodies()[0]
    u_b2.Destroy()
    print("  [OK] Shoulder united.")

    # 5. Large Cylindrical Cap (overlapping 1mm into shoulder)
    print("\n[5/8] Creating large cylindrical cap...")
    cap_b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    cap_b.Diameter.RightHandSide = "CAP_DIAMETER"
    cap_b.Height.RightHandSide = "CAP_HEIGHT + 1.0"
    cap_b.Origin = point(0.0, 31.0, 0.0)
    cap_b.Direction = vec(0.0, 1.0, 0.0)
    cap_feat = cap_b.CommitFeature()
    set_name(cap_feat, "CAP_CYLINDER")
    cap_body = cap_feat.GetBodies()[0]
    cap_b.Destroy()

    # 6. Dense Vertical Ribs on Lower Cap Body
    print(f"\n[6/8] Subtracting {n_ribs} vertical flutes on lower cap portion...")
    t0 = time.time()
    r_cap = float(expressions["CAP_DIAMETER"]) / 2.0
    cutter_r = rib_cutter_dia / 2.0
    rc = r_cap + cutter_r - rib_depth
    rib_y_start = 32.0

    sub_b = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    sub_b.Operation = NXOpen.Features.Feature.BooleanType.Subtract
    sub_b.Target = cap_body

    for i in range(n_ribs):
        theta = 2.0 * math.pi * i / n_ribs
        xc = rc * math.cos(theta)
        zc = rc * math.sin(theta)
        cb = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        cb.Diameter.RightHandSide = "RIB_CUTTER_DIA"
        cb.Height.RightHandSide = "RIB_HEIGHT"
        cb.Origin = point(xc, rib_y_start, zc)
        cb.Direction = vec(0.0, 1.0, 0.0)
        c_feat = cb.CommitFeature()
        c_body = c_feat.GetBodies()[0]
        cb.Destroy()
        sub_b.Tools.Add(c_body)

    sub_feat = sub_b.CommitFeature()
    set_name(sub_feat, "CAP_LOWER_VERTICAL_RIBS")
    cap_body = sub_feat.GetBodies()[0]
    sub_b.Destroy()
    print(f"  [OK] {n_ribs} vertical ribs subtracted in {time.time() - t0:.2f}s!")

    # Unite ribbed cap to main body
    u_b3 = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    u_b3.Operation = NXOpen.Features.Feature.BooleanType.Unite
    u_b3.Target = main_body
    u_b3.Tools.Add(cap_body)
    u_feat3 = u_b3.CommitFeature()
    set_name(u_feat3, "UNITE_CAP")
    main_body = u_feat3.GetBodies()[0]
    u_b3.Destroy()
    print("  [OK] Ribbed cap united to main body.")

    # 7. Concave Bottom Dome Recess
    print("\n[7/8] Cutting bottom concave dome cavity...")
    recess_b = part.Features.CreateConeBuilder(NXOpen.Features.Cone.Null)
    recess_b.Type = NXOpen.Features.ConeBuilder.Types.DiametersAndHeight
    recess_b.BaseDiameter.RightHandSide = "BOTTOM_DOME_DIA"
    recess_b.TopDiameter.RightHandSide = "BOTTOM_DOME_DIA - 8.0"
    recess_b.Height.RightHandSide = "BOTTOM_DOME_DEPTH"
    dir_rec = part.Directions.CreateDirection(
        point(0.0, base_y, 0.0),
        vec(0.0, 1.0, 0.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    recess_b.Axis.Point.SetCoordinates(point(0.0, base_y, 0.0))
    recess_b.Axis.Direction = dir_rec
    recess_feat = recess_b.CommitFeature()
    set_name(recess_feat, "BOTTOM_DOME_TOOL")
    recess_body = recess_feat.GetBodies()[0]
    recess_b.Destroy()

    sub_dome = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    sub_dome.Operation = NXOpen.Features.Feature.BooleanType.Subtract
    sub_dome.Target = main_body
    sub_dome.Tools.Add(recess_body)
    sub_dome_feat = sub_dome.CommitFeature()
    set_name(sub_dome_feat, "BOTTOM_DOME_CUT")
    main_body = sub_dome_feat.GetBodies()[0]
    sub_dome.Destroy()
    print("  [OK] Bottom concave dome cut subtracted.")

    # 8. Transitional Edge Blends
    print("\n[8/8] Applying edge blends...")
    e_heel = find_circular_edge_near(main_body, base_y, float(expressions["BODY_DIAMETER"]) / 2.0, max_dist=3.0)
    apply_edge_blend(part, e_heel, float(expressions["BOTTOM_HEEL_R"]), "BOTTOM_HEEL_R", "BOTTOM_HEEL_BLEND")

    e_cap_top = find_circular_edge_near(main_body, 32.0 + cap_h, float(expressions["CAP_DIAMETER"]) / 2.0, max_dist=3.0)
    apply_edge_blend(part, e_cap_top, float(expressions["CAP_TOP_BLEND_R"]), "CAP_TOP_BLEND_R", "CAP_TOP_BLEND")

    e_waist1 = find_circular_edge_near(main_body, 10.0, float(expressions["WAIST_DIAMETER"]) / 2.0, max_dist=3.0)
    apply_edge_blend(part, e_waist1, float(expressions["WAIST_BLEND_R"]), "WAIST_BLEND_R", "WAIST_LOWER_BLEND")

    e_waist2 = find_circular_edge_near(main_body, 30.0, float(expressions["WAIST_DIAMETER"]) / 2.0, max_dist=3.0)
    apply_edge_blend(part, e_waist2, float(expressions["SHOULDER_BLEND_R"]), "SHOULDER_BLEND_R", "WAIST_UPPER_BLEND")

    # Feature Tree Inspection
    print("\n" + "=" * 70)
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
    stl_exp.OutputFile = str(out_stl)
    stl_exp.ExportSelectionBlock.Add(main_body)
    stl_exp.Commit()
    stl_exp.Destroy()
    print(f"[OK] Synchronized STL exported to: {out_stl}")

    part.Close(NXOpen.BasePart.CloseWholeTree.FalseValue, NXOpen.BasePart.CloseModified.CloseModified, None)


if __name__ == "__main__":
    main()
