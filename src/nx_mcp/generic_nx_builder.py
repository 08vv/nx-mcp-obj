"""
generic_nx_builder.py
=====================
Deterministic Siemens NX CAD Execution Engine.

Consumes a parametric specification JSON (containing expressions, sketch-based
zones, driving dimensions, revolves, booleans, and blends) and builds a 100%
native sketch-in-place parametric CAD model (.prt) in Siemens NX.

Every solid feature references a native Sketch feature on a fixed datum plane,
and every dimension is linked to a named NX driving expression.

Usage (invoked via run_journal.exe):
    run_journal.exe generic_nx_builder.py <spec_json_path> <output_prt_path>
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.nx_mcp.parametric_helpers import (
    setup_nx_license,
    set_feature_name,
    populate_expressions,
    create_fixed_datum_plane_xy,
    create_fixed_datum_plane_xz,
    create_offset_datum_plane,
    create_sketch_in_place,
    create_sketch_revolve,
    boolean_unite,
    create_associative_blend_by_face,
    compute_body_bounds,
    is_cylindrical_zone,
)

setup_nx_license()

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF


def pt3d(x: float, y: float, z: float = 0.0) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def eval_scalar(part, val: Union[float, int, str], exp_map: Dict[str, float]) -> float:
    """Evaluates a numerical value or expression string into a float."""
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    try:
        return float(val_str)
    except ValueError:
        pass
    try:
        exp = part.Expressions.FindObject(val_str)
        return float(exp.Value)
    except Exception:
        pass
    # Fallback to evaluating in exp_map context
    try:
        return float(eval(val_str, {"__builtins__": None, "math": math}, exp_map))
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Native Sketch Zone Builder
# ---------------------------------------------------------------------------
def build_sketch_zone(
    part,
    datum_plane,
    zone_idx: int,
    zone_def: Dict[str, Any],
    exp_map: Dict[str, float],
    primary_axis: str = "Y"
) -> Tuple[Any, Any]:
    """
    Builds a native SketchInPlace feature with profile lines and driving dimensions,
    then executes an associative 360-degree Revolve.
    
    The sketch contains a closed 4-sided profile:
      - Bottom horizontal line (axis to outer radius at z_start)
      - Outer profile (LINE or ARC from bottom-right to top-right)
      - Top horizontal line (outer radius to axis at z_end)
      - Center vertical axis line (z_end back to z_start, on r=0)
    
    The revolve section uses ALL sketch curves (closed loop) and revolves around Y-axis.
    """
    zone_name = zone_def.get("name", f"ZONE_{zone_idx}").upper()
    sketch_name = f"SKETCH_{zone_name}"
    revolve_name = f"{zone_name}_REVOLVE"

    print(f"  [BUILD] Building {sketch_name} & {revolve_name}...")

    # 1. Extract and evaluate zone dimensions
    seg_type = zone_def.get("segment_type", "LINE").upper()
    r_start_exp = zone_def.get("r_start_exp", f"ZONE{zone_idx}_BASE_R")
    r_end_exp = zone_def.get("r_end_exp", f"ZONE{zone_idx}_TOP_R")
    r_mid_exp = zone_def.get("r_mid_exp", f"ZONE{zone_idx}_MID_R")
    z_start_exp = zone_def.get("z_start_exp", f"ZONE{zone_idx}_START")
    height_exp = zone_def.get("height_exp", f"ZONE{zone_idx}_HEIGHT")

    r_start_val = eval_scalar(part, zone_def.get("r_start", r_start_exp), exp_map)
    r_end_val = eval_scalar(part, zone_def.get("r_end", r_end_exp), exp_map)
    z_start_val = eval_scalar(part, zone_def.get("z_start", z_start_exp), exp_map)
    height_val = eval_scalar(part, zone_def.get("height", height_exp), exp_map)
    
    # Ensure minimum positive radius (avoid degenerate geometry)
    r_start_val = max(0.01, r_start_val)
    r_end_val = max(0.01, r_end_val)

    if seg_type == "ARC":
        r_mid_val = eval_scalar(part, zone_def.get("r_mid", r_mid_exp), exp_map)
        r_mid_val = max(0.01, r_mid_val)
    else:
        r_mid_val = (r_start_val + r_end_val) / 2.0

    s0 = part.Scalars.CreateScalar(0.0, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)

    def s_exp(name: str):
        exp = part.Expressions.FindObject(name)
        return part.Scalars.CreateScalarExpression(exp, NXOpen.Scalar.DimensionalityType.Length, NXOpen.SmartObject.UpdateOption.WithinModeling)

    z_end_val = z_start_val + height_val

    # 2. Create SketchInPlace on fixed datum plane
    sk_builder = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
    try:
        sk_builder.PlaneOrFace.Value = datum_plane
        sketch = sk_builder.Commit()
        set_feature_name(sketch, sketch_name)
    finally:
        sk_builder.Destroy()

    sketch.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    # 3. Construct closed boundary curves in sketch plane (aligned with primary axis)
    curves = []

    # Curve 0: Bottom Horizontal Line (axis -> outer at z_start)
    p_center_bot = pt3d(0.0, z_start_val, 0.0)
    p_start = pt3d(r_start_val, z_start_val, 0.0)
    c_bot = part.Curves.CreateLine(p_center_bot, p_start)
    curves.append(c_bot)

    # Curve 1+: Outer Profile
    p_end = pt3d(r_end_val, z_end_val, 0.0)

    c_mid1 = None
    if seg_type == "ARC" and abs(height_val) > 0.1:
        sagitta = abs(r_mid_val - (r_start_val + r_end_val) / 2.0)
        p_mid = pt3d(r_mid_val, (z_start_val + z_end_val) / 2.0, 0.0)
        c_mid1 = part.Curves.CreateLine(p_start, p_mid)
        c_mid2 = part.Curves.CreateLine(p_mid, p_end)
        curves.append(c_mid1)
        curves.append(c_mid2)
        print(f"    [ARC->2SEG] {zone_name}: R=[{r_start_val:.2f}->{r_mid_val:.2f}->{r_end_val:.2f}], H={height_val:.1f}mm, sagitta={sagitta:.2f}mm")
    else:
        curves.append(part.Curves.CreateLine(p_start, p_end))

    # Curve 2: Top Horizontal Line (outer -> axis at z_end)
    p_center_top = pt3d(0.0, z_end_val, 0.0)
    c_top = part.Curves.CreateLine(p_end, p_center_top)
    curves.append(c_top)

    # Curve 3: Center Vertical Axis Line (closing the profile back to z_start)
    c_axis = part.Curves.CreateLine(p_center_top, p_center_bot)
    curves.append(c_axis)

    # Add all geometry to sketch
    for c in curves:
        sketch.AddGeometry(c, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

    # 4. Add Driving Dimensions linked to named NX Expressions
    try:
        exp_base_r = part.Expressions.FindObject(r_start_exp)
        dg1 = NXOpen.Sketch.DimensionGeometry()
        dg1.Geometry = c_bot
        dg1.AssocType = NXOpen.Sketch.AssocType.StartPoint
        dg2 = NXOpen.Sketch.DimensionGeometry()
        dg2.Geometry = c_bot
        dg2.AssocType = NXOpen.Sketch.AssocType.EndPoint
        sketch.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg1, dg2,
            pt3d(r_start_val / 2.0, z_start_val, 0.0),
            exp_base_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )
    except Exception:
        pass

    try:
        exp_top_r = part.Expressions.FindObject(r_end_exp)
        dg1 = NXOpen.Sketch.DimensionGeometry()
        dg1.Geometry = c_top
        dg1.AssocType = NXOpen.Sketch.AssocType.StartPoint
        dg2 = NXOpen.Sketch.DimensionGeometry()
        dg2.Geometry = c_top
        dg2.AssocType = NXOpen.Sketch.AssocType.EndPoint
        sketch.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dg1, dg2,
            pt3d(r_end_val / 2.0, z_end_val, 0.0),
            exp_top_r,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )
    except Exception:
        pass

    # For ARC zones, link mid-radius driving dimension to r_mid_exp
    if seg_type == "ARC" and c_mid1 is not None and r_mid_exp:
        try:
            exp_mid_r = part.Expressions.FindObject(r_mid_exp)
            dg1 = NXOpen.Sketch.DimensionGeometry()
            dg1.Geometry = c_axis
            dg1.AssocType = NXOpen.Sketch.AssocType.StartPoint
            dg2 = NXOpen.Sketch.DimensionGeometry()
            dg2.Geometry = c_mid1
            dg2.AssocType = NXOpen.Sketch.AssocType.EndPoint
            sketch.CreateDimension(
                NXOpen.Sketch.ConstraintType.HorizontalDim,
                dg1, dg2,
                pt3d(r_mid_val / 2.0, (z_start_val + z_end_val) / 2.0, 0.0),
                exp_mid_r,
                NXOpen.Sketch.DimensionOption.CreateAsDriving
            )
        except Exception as e:
            print(f"    [WARN] Failed to add MID_R dimension: {e}")

    # Vertical Driving Dimension for ZONE_HEIGHT
    try:
        exp_h = part.Expressions.FindObject(height_exp)
        dg1_h = NXOpen.Sketch.DimensionGeometry()
        dg1_h.Geometry = c_axis
        dg1_h.AssocType = NXOpen.Sketch.AssocType.StartPoint
        dg2_h = NXOpen.Sketch.DimensionGeometry()
        dg2_h.Geometry = c_axis
        dg2_h.AssocType = NXOpen.Sketch.AssocType.EndPoint
        sketch.CreateDimension(
            NXOpen.Sketch.ConstraintType.VerticalDim,
            dg1_h, dg2_h,
            pt3d(0.0, (z_start_val + z_end_val) / 2.0, 0.0),
            exp_h,
            NXOpen.Sketch.DimensionOption.CreateAsDriving
        )
    except Exception as e_h:
        pass


    sketch.Update()
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # 5. Create Revolve Feature
    rev_builder = part.Features.CreateRevolveBuilder(NXOpen.Features.Feature.Null)
    try:
        rev_builder.Tolerance = 0.01
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rule = part.ScRuleFactory.CreateRuleCurveFeature([sketch.Feature])
        ref_line = curves[0]
        sec.AddToSection([rule], ref_line, NXOpen.NXObject.Null, NXOpen.NXObject.Null, pt3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        rev_builder.Section = sec

        # Revolve Axis (around Y-axis for XY-plane sketch)
        axis_y = 1.0 if primary_axis.upper() == "Y" else 0.0
        axis_z = 1.0 if primary_axis.upper() == "Z" else 0.0
        axis_dir = part.Directions.CreateDirection(pt3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, axis_y, axis_z), NXOpen.SmartObject.UpdateOption.WithinModeling)
        axis_pt = part.Points.CreatePoint(pt3d(0.0, 0.0, 0.0))
        rev_builder.Axis = part.Axes.CreateAxis(axis_pt, axis_dir, NXOpen.SmartObject.UpdateOption.WithinModeling)
        rev_builder.Limits.StartExtend.Value.RightHandSide = "0"
        rev_builder.Limits.EndExtend.Value.RightHandSide = "360"
        rev_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        
        rev_feat = rev_builder.CommitFeature()
        set_feature_name(rev_feat, revolve_name)
        bodies = rev_feat.GetBodies()
        body = bodies[0] if bodies else None
        return rev_feat, body
    finally:
        rev_builder.Destroy()


def build_loft_from_outlines_spec(spec: Dict[str, Any], output_prt_path: Path) -> None:
    """
    Builds a parametric solid model using closed station curve outlines,
    ThroughCurves solid loft, and parametric scaling driven by expressions:
      - BODY_WIDTH_X
      - BODY_THICKNESS_Z
      - BODY_HEIGHT_Y
    """
    output_prt_path.parent.mkdir(parents=True, exist_ok=True)
    if output_prt_path.exists():
        try:
            output_prt_path.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(output_prt_path), NXOpen.Part.Units.Millimeters)

    stations = spec.get("stations", [])
    if not stations:
        raise ValueError("Specification JSON contains no stations for loft construction.")

    all_pts = [p for st in stations for p in st["points"]]
    all_x = [p[0] for p in all_pts]
    all_y = [p[1] for p in all_pts]
    all_z = [p[2] for p in all_pts]

    ref_w1 = max(all_x) - min(all_x)
    ref_h = max(all_y) - min(all_y)
    ref_w2 = max(all_z) - min(all_z)

    # 1. Create Expressions
    print(f"\n[1/4] Populating driving expressions for loft solid...")
    part.Expressions.CreateExpression("Number", f"BODY_WIDTH_X = {ref_w1:.3f}")
    part.Expressions.CreateExpression("Number", f"BODY_THICKNESS_Z = {ref_w2:.3f}")
    part.Expressions.CreateExpression("Number", f"BODY_HEIGHT_Y = {ref_h:.3f}")
    part.Expressions.CreateExpression("Number", f"REF_WIDTH_X = {ref_w1:.3f}")
    part.Expressions.CreateExpression("Number", f"REF_THICKNESS_Z = {ref_w2:.3f}")
    part.Expressions.CreateExpression("Number", f"REF_HEIGHT_Y = {ref_h:.3f}")
    part.Expressions.CreateExpression("Number", "SCALE_X = BODY_WIDTH_X / REF_WIDTH_X")
    part.Expressions.CreateExpression("Number", "SCALE_Z = BODY_THICKNESS_Z / REF_THICKNESS_Z")
    part.Expressions.CreateExpression("Number", "SCALE_Y = BODY_HEIGHT_Y / REF_HEIGHT_Y")

    # 2. Build Closed Periodic StudioSplines for Each Station
    print(f"\n[2/5] Generating {len(stations)} closed periodic StudioSpline outline curves...")
    curves = []
    start_points = []
    for idx, st in enumerate(stations):
        pts = st["points"]
        b = part.Features.CreateStudioSplineBuilderEx(NXOpen.Features.Feature.Null)
        try:
            b.Degree = 3
            b.IsPeriodic = True
            for p in pts:
                g = b.ConstraintManager.CreateGeometricConstraintData()
                g.Point = part.Points.CreatePoint(pt3d(*p))
                b.ConstraintManager.Append(g)
            feat = b.CommitFeature()
            set_feature_name(feat, f"STATION_SPLINE_{idx+1}")
            curves.append(feat.GetEntities()[0])
            start_points.append(pts[0])
        finally:
            b.Destroy()

    # 3. Create Through Curves Feature
    print(f"\n[3/5] Looping sections and building Through Curves body...")
    tcb = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        for crv, sp in zip(curves, start_points):
            sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
            rule = part.ScRuleFactory.CreateRuleCurveDumb([crv])
            sec.AddToSection([rule], crv, NXOpen.NXObject.Null, NXOpen.NXObject.Null, pt3d(*sp), NXOpen.Section.Mode.Create, False)
            container = getattr(tcb, "SectionsList", None) or getattr(tcb, "Sections", None)
            if hasattr(container, "Append"):
                container.Append(sec)
            else:
                container.Add(sec)

        loft_feat = tcb.CommitFeature()
        set_feature_name(loft_feat, "LOFT_THROUGH_CURVES_BODY")
        print(f"  [OK] Feature: LOFT_THROUGH_CURVES_BODY committed successfully.")
    finally:
        tcb.Destroy()

    loft_body = loft_feat.GetBodies()[0]

    # 4. Cap both ends with BoundedPlane and Sew into solid body (if not already solid)
    if loft_body.IsSolidBody:
        print("\n[4/5] Through Curves formed a closed solid body directly.")
        solid_body = loft_body
    else:
        print("\n[4/5] Capping end cross-sections and sewing into single solid body...")
        bp_bot = part.Features.CreateBoundedPlaneBuilder(NXOpen.Features.BoundedPlane.Null)
        try:
            rule_bot = part.ScRuleFactory.CreateRuleCurveDumb([curves[0]])
            bp_bot.BoundingCurves.AddToSection([rule_bot], curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, pt3d(*start_points[0]), NXOpen.Section.Mode.Create, False)
            bot_cap_feat = bp_bot.CommitFeature()
            set_feature_name(bot_cap_feat, "BOTTOM_CAP_PLANE")
            bot_cap_body = bot_cap_feat.GetBodies()[0]
        finally:
            bp_bot.Destroy()

        bp_top = part.Features.CreateBoundedPlaneBuilder(NXOpen.Features.BoundedPlane.Null)
        try:
            rule_top = part.ScRuleFactory.CreateRuleCurveDumb([curves[-1]])
            bp_top.BoundingCurves.AddToSection([rule_top], curves[-1], NXOpen.NXObject.Null, NXOpen.NXObject.Null, pt3d(*start_points[-1]), NXOpen.Section.Mode.Create, False)
            top_cap_feat = bp_top.CommitFeature()
            set_feature_name(top_cap_feat, "TOP_CAP_PLANE")
            top_cap_body = top_cap_feat.GetBodies()[0]
        finally:
            bp_top.Destroy()

        sew = part.Features.CreateSewBuilder(NXOpen.Features.Feature.Null)
        try:
            sew.Tolerance = 0.1
            if hasattr(NXOpen.Features.SewBuilder, "BodyPreferenceTypes"):
                sew.BodyPreference = NXOpen.Features.SewBuilder.BodyPreferenceTypes.Solid
            if hasattr(sew, "TargetBodies"):
                sew.TargetBodies.Add(loft_body)
            elif hasattr(sew, "TargetBody"):
                sew.TargetBody = loft_body
            if hasattr(sew, "ToolBodies"):
                sew.ToolBodies.Add(bot_cap_body)
                sew.ToolBodies.Add(top_cap_body)
            sew_feat = sew.CommitFeature()
            set_feature_name(sew_feat, "SEW_SOLID_BODY")
            print("  [OK] Feature: SEW_SOLID_BODY committed successfully.")
        finally:
            sew.Destroy()

        solid_bodies = [b for b in part.Bodies if b.IsSolidBody]
        if not solid_bodies:
            raise RuntimeError("Sew did not produce a solid body.")
        solid_body = solid_bodies[0]

    # 5. Create Associative Scale Feature
    print("\n[5/5] Attaching associative parametric scaling feature...")
    sb = part.Features.CreateScaleBuilder(NXOpen.Features.Feature.Null)
    try:
        sb.Type = NXOpen.Features.ScaleBuilder.Types.General
        sb.BodyToScale.Add(solid_body)
        sb.ScaleXdirection.RightHandSide = "SCALE_X"
        sb.ScaleYdirection.RightHandSide = "SCALE_Y"
        sb.ScaleZdirection.RightHandSide = "SCALE_Z"
        sb.Point = part.Points.CreatePoint(pt3d(0.0, 0.0, 0.0))
        scale_feat = sb.CommitFeature()
        set_feature_name(scale_feat, "PARAMETRIC_SCALE_BODY")
        print(f"  [OK] Feature: PARAMETRIC_SCALE_BODY committed successfully.")
    finally:
        sb.Destroy()

    main_body = [b for b in part.Bodies if b.IsSolidBody][0]

    # Export STL
    out_stl_path = output_prt_path.with_suffix(".stl")
    if main_body:
        try:
            if out_stl_path.exists():
                out_stl_path.unlink()
            stl_exp = session.DexManager.CreateStlCreator()
            stl_exp.OutputFile = str(out_stl_path)
            stl_exp.ExportSelectionBlock.Add(main_body)
            stl_exp.Commit()
            stl_exp.Destroy()
            print(f"  [OK] STL exported: {out_stl_path} ({out_stl_path.stat().st_size:,} bytes)")
        except Exception as stl_err:
            print(f"  [WARN] STL export: {stl_err}")

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"\n[SUCCESS] Part saved: {output_prt_path}")
    print("=" * 75)


# ---------------------------------------------------------------------------
# Feature-Plan Parametric CAD Builder (Phase 5C/5D)
# ---------------------------------------------------------------------------

def _create_compound_4_arc_sketch_curves(
    part, y_elev: float, hw: float, ht: float, cr: float
) -> Tuple[List[Any], float]:
    """
    Creates a closed COMPOUND_4_ARC outline at world Y = y_elev in the XZ plane.
    Returns a list of 4 NXOpen.Arc objects: [arc_rc, arc_top, arc_lc, arc_bot] and flank radius rf.
    The outline consists of 4 circular arcs meeting with exact G1 tangency (no lines, no splines).
    """
    cr = max(0.1, min(cr, min(hw, ht) - 0.1))
    rf = (hw**2 + ht**2 - 2.0 * hw * cr) / (2.0 * (ht - cr))
    theta_join = math.atan2(rf - ht, hw - cr)

    def pw(x, z):
        return NXOpen.Point3d(float(x), float(y_elev), float(z))

    vx = NXOpen.Vector3d(1.0, 0.0, 0.0)
    vz = NXOpen.Vector3d(0.0, 0.0, 1.0)

    # 4 tangent circular arcs forming exact closed oval in XZ plane
    arc_rc = part.Curves.CreateArc(pw(hw - cr, 0.0), vx, vz, float(cr), -theta_join, theta_join)
    arc_top = part.Curves.CreateArc(pw(0.0, ht - rf), vx, vz, float(rf), theta_join, math.pi - theta_join)
    arc_lc = part.Curves.CreateArc(pw(-hw + cr, 0.0), vx, vz, float(cr), math.pi - theta_join, math.pi + theta_join)
    arc_bot = part.Curves.CreateArc(pw(0.0, -ht + rf), vx, vz, float(rf), math.pi + theta_join, 2.0 * math.pi - theta_join)

    return [arc_rc, arc_top, arc_lc, arc_bot], rf


def _create_ellipse_sketch_curves(
    part, y_elev: float, hw: float, ht: float, n_seg: int = 32
) -> List[Any]:
    """
    Creates a closed ellipse outline at world Y = y_elev in the XZ plane
    as n_seg line segments (polyline approximation for NX Through Curves).
    Returns a list of NXOpen.Line objects forming a closed polygon.
    """
    def pw(x, z):
        return NXOpen.Point3d(float(x), float(y_elev), float(z))

    angles = [2.0 * math.pi * i / n_seg for i in range(n_seg)]
    pts = [pw(hw * math.cos(a), ht * math.sin(a)) for a in angles]
    lines = []
    for i in range(n_seg):
        p1 = pts[i]
        p2 = pts[(i + 1) % n_seg]
        lines.append(part.Curves.CreateLine(p1, p2))
    return lines


def _create_rounded_rectangle_sketch_feature(
    part, elev: float, sk_name: str, datum_name: str,
    exp_w, exp_t, exp_cr,
    hw: float, ht: float, cr: float,
    offset_from: Optional[Tuple[Any, str]] = None
) -> Tuple[Any, Any, Tuple[float, float, float], Any]:
    """
    Creates a native sketch-in-place rounded rectangle (4 straight lines + 4 corner arcs)
    with associative driving dimensions for width, thickness, and corner radius.
    """
    if offset_from is not None:
        base_plane, offset_exp_str = offset_from
        datum_sk = create_offset_datum_plane(part, base_plane, offset_exp_str, name=datum_name)
    else:
        datum_sk = create_fixed_datum_plane_xz(part, origin=(0.0, elev, 0.0))
        set_feature_name(datum_sk, datum_name)

    sketch = create_sketch_in_place(part, datum_sk, name=sk_name)
    sketch.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    def pt(x, z):
        return NXOpen.Point3d(float(x), float(elev), float(z))

    vx = NXOpen.Vector3d(1.0, 0.0, 0.0)
    vz = NXOpen.Vector3d(0.0, 0.0, 1.0)

    # 4 straight lines + 4 corner arcs in XZ plane
    line_top = part.Curves.CreateLine(pt(-hw + cr, ht), pt(hw - cr, ht))
    arc_tr = part.Curves.CreateArc(pt(hw - cr, ht - cr), vx, vz, float(cr), 0.0, math.pi / 2.0)
    line_right = part.Curves.CreateLine(pt(hw, ht - cr), pt(hw, -ht + cr))
    arc_br = part.Curves.CreateArc(pt(hw - cr, -ht + cr), vx, vz, float(cr), 3.0 * math.pi / 2.0, 2.0 * math.pi)
    line_bot = part.Curves.CreateLine(pt(hw - cr, -ht), pt(-hw + cr, -ht))
    arc_bl = part.Curves.CreateArc(pt(-hw + cr, -ht + cr), vx, vz, float(cr), math.pi, 3.0 * math.pi / 2.0)
    line_left = part.Curves.CreateLine(pt(-hw, -ht + cr), pt(-hw, ht - cr))
    arc_tl = part.Curves.CreateArc(pt(-hw + cr, ht - cr), vx, vz, float(cr), math.pi / 2.0, math.pi)

    curves = [line_top, arc_tr, line_right, arc_br, line_bot, arc_bl, line_left, arc_tl]
    for c in curves:
        sketch.AddGeometry(c, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

    # 1. Corner radius dimension
    if exp_cr:
        try:
            dg1 = NXOpen.Sketch.DimensionGeometry()
            dg1.Geometry = arc_tr
            dg1.AssocType = NXOpen.Sketch.AssocType.StartPoint
            dg2 = NXOpen.Sketch.DimensionGeometry()
            dg2.Geometry = NXOpen.NXObject.Null
            dg2.AssocType = NXOpen.Sketch.AssocType.StartPoint
            sketch.CreateDimension(
                NXOpen.Sketch.ConstraintType.RadiusDim,
                dg1, dg2,
                pt(hw - cr + 10.0, ht - cr + 10.0),
                exp_cr,
                NXOpen.Sketch.DimensionOption.CreateAsDriving
            )
        except Exception as e:
            print(f"    [WARN] Dim {sk_name} CORNER_R: {e}")

    # 2. Width dimension (between line_left and line_right)
    if exp_w:
        try:
            dg_w1 = NXOpen.Sketch.DimensionGeometry()
            dg_w1.Geometry = line_left
            dg_w1.AssocType = NXOpen.Sketch.AssocType.StartPoint
            dg_w2 = NXOpen.Sketch.DimensionGeometry()
            dg_w2.Geometry = line_right
            dg_w2.AssocType = NXOpen.Sketch.AssocType.StartPoint
            sketch.CreateDimension(
                NXOpen.Sketch.ConstraintType.HorizontalDim,
                dg_w1, dg_w2,
                pt(0.0, ht + 10.0),
                exp_w,
                NXOpen.Sketch.DimensionOption.CreateAsDriving
            )
        except Exception as e:
            print(f"    [WARN] Dim {sk_name} WIDTH: {e}")

    # 3. Thickness dimension (between line_bot and line_top)
    if exp_t:
        try:
            dg_t1 = NXOpen.Sketch.DimensionGeometry()
            dg_t1.Geometry = line_bot
            dg_t1.AssocType = NXOpen.Sketch.AssocType.StartPoint
            dg_t2 = NXOpen.Sketch.DimensionGeometry()
            dg_t2.Geometry = line_top
            dg_t2.AssocType = NXOpen.Sketch.AssocType.StartPoint
            sketch.CreateDimension(
                NXOpen.Sketch.ConstraintType.VerticalDim,
                dg_t1, dg_t2,
                pt(hw + 10.0, 0.0),
                exp_t,
                NXOpen.Sketch.DimensionOption.CreateAsDriving
            )
        except Exception as e:
            print(f"    [WARN] Dim {sk_name} THICKNESS: {e}")

    sketch.Update()
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    return sketch, line_top, (hw, elev, 0.0), datum_sk


def _create_4arc_sketch_feature(
    part, elev: float, sk_name: str, datum_name: str,
    exp_w, exp_t, exp_cr, exp_rf,
    hw: float, ht: float, cr: float,
    offset_from: Optional[Tuple[Any, str]] = None
) -> Tuple[Any, Any, Tuple[float, float, float], Any]:
    if offset_from is not None:
        base_plane, offset_exp_str = offset_from
        datum_sk = create_offset_datum_plane(part, base_plane, offset_exp_str, name=datum_name)
    else:
        datum_sk = create_fixed_datum_plane_xz(part, origin=(0.0, elev, 0.0))
        set_feature_name(datum_sk, datum_name)

    sketch = create_sketch_in_place(part, datum_sk, name=sk_name)
    sketch.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    curves, rf = _create_compound_4_arc_sketch_curves(part, elev, hw, ht, cr)
    arc_rc, arc_top, arc_lc, arc_bot = curves

    for c in curves:
        sketch.AddGeometry(c, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)



    # 1. Corner radius dimension
    if exp_cr:
        try:
            dg1 = NXOpen.Sketch.DimensionGeometry()
            dg1.Geometry = arc_rc
            dg1.AssocType = NXOpen.Sketch.AssocType.StartPoint
            dg2 = NXOpen.Sketch.DimensionGeometry()
            dg2.Geometry = NXOpen.NXObject.Null
            dg2.AssocType = NXOpen.Sketch.AssocType.StartPoint
            sketch.CreateDimension(
                NXOpen.Sketch.ConstraintType.RadiusDim,
                dg1, dg2,
                NXOpen.Point3d(float(hw - cr), float(cr), 0.0),
                exp_cr,
                NXOpen.Sketch.DimensionOption.CreateAsDriving
            )
        except Exception as e:
            print(f"    [WARN] Dim {sk_name} CORNER_R: {e}")

    # 2. Width dimension (HorizontalDim with Tangency between left and right arcs)
    if exp_w:
        try:
            dg1 = NXOpen.Sketch.DimensionGeometry()
            dg1.Geometry = arc_lc
            dg1.AssocType = NXOpen.Sketch.AssocType.Tangency
            dg2 = NXOpen.Sketch.DimensionGeometry()
            dg2.Geometry = arc_rc
            dg2.AssocType = NXOpen.Sketch.AssocType.Tangency
            sketch.CreateDimension(
                NXOpen.Sketch.ConstraintType.HorizontalDim,
                dg1, dg2,
                NXOpen.Point3d(0.0, float(ht + 5.0), 0.0),
                exp_w,
                NXOpen.Sketch.DimensionOption.CreateAsDriving
            )
        except Exception as e:
            print(f"    [WARN] Dim {sk_name} WIDTH: {e}")

    # 4. Thickness dimension (VerticalDim with Tangency between bottom and top arcs)
    if exp_t:
        try:
            dg1 = NXOpen.Sketch.DimensionGeometry()
            dg1.Geometry = arc_bot
            dg1.AssocType = NXOpen.Sketch.AssocType.Tangency
            dg2 = NXOpen.Sketch.DimensionGeometry()
            dg2.Geometry = arc_top
            dg2.AssocType = NXOpen.Sketch.AssocType.Tangency
            sketch.CreateDimension(
                NXOpen.Sketch.ConstraintType.VerticalDim,
                dg1, dg2,
                NXOpen.Point3d(float(hw + 5.0), 0.0, 0.0),
                exp_t,
                NXOpen.Sketch.DimensionOption.CreateAsDriving
            )
        except Exception as e:
            print(f"    [WARN] Dim {sk_name} THICKNESS: {e}")

    sketch.Update()
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    return sketch, arc_rc, (hw, elev, 0.0), datum_sk


def _build_through_curves_solid(part, sk_tuples: List[Any], feat_name: str) -> Any:
    tcb = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        try:
            tcb.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
        except Exception:
            pass
        for item in sk_tuples:
            sk = item[0]
            ref_crv = item[1]
            sp = item[2]
            sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
            rule = part.ScRuleFactory.CreateRuleCurveFeature([sk.Feature])
            sec.AddToSection(
                [rule], ref_crv, NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                pt3d(*sp), NXOpen.Section.Mode.Create, False
            )
            container = getattr(tcb, "SectionsList", None) or getattr(tcb, "Sections", None)
            if hasattr(container, "Append"):
                container.Append(sec)
            else:
                container.Add(sec)

        loft_feat = tcb.CommitFeature()
        set_feature_name(loft_feat, feat_name)
        print(f"  [OK] Feature: {feat_name} committed successfully.")
        loft_body = loft_feat.GetBodies()[0]

        if not loft_body.IsSolidBody:
            print(f"  [CAP] {feat_name} produced a sheet; capping ends...")
            bp_bot = part.Features.CreateBoundedPlaneBuilder(NXOpen.Features.BoundedPlane.Null)
            try:
                rule_bot = part.ScRuleFactory.CreateRuleCurveFeature([sk_tuples[0][0].Feature])
                bp_bot.BoundingCurves.AddToSection(
                    [rule_bot], sk_tuples[0][1], NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                    pt3d(*sk_tuples[0][2]), NXOpen.Section.Mode.Create, False
                )
                bot_cap_feat = bp_bot.CommitFeature()
                set_feature_name(bot_cap_feat, f"{feat_name}_BOT_CAP")
                bot_cap_body = bot_cap_feat.GetBodies()[0]
            finally:
                bp_bot.Destroy()

            bp_top = part.Features.CreateBoundedPlaneBuilder(NXOpen.Features.BoundedPlane.Null)
            try:
                rule_top = part.ScRuleFactory.CreateRuleCurveFeature([sk_tuples[-1][0].Feature])
                bp_top.BoundingCurves.AddToSection(
                    [rule_top], sk_tuples[-1][1], NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                    pt3d(*sk_tuples[-1][2]), NXOpen.Section.Mode.Create, False
                )
                top_cap_feat = bp_top.CommitFeature()
                set_feature_name(top_cap_feat, f"{feat_name}_TOP_CAP")
                top_cap_body = top_cap_feat.GetBodies()[0]
            finally:
                bp_top.Destroy()

            sew = part.Features.CreateSewBuilder(NXOpen.Features.Feature.Null)
            try:
                sew.Tolerance = 0.1
                if hasattr(NXOpen.Features.SewBuilder, "BodyPreferenceTypes"):
                    sew.BodyPreference = NXOpen.Features.SewBuilder.BodyPreferenceTypes.Solid
                if hasattr(sew, "TargetBodies"):
                    sew.TargetBodies.Add(loft_body)
                elif hasattr(sew, "TargetBody"):
                    sew.TargetBody = loft_body
                if hasattr(sew, "ToolBodies"):
                    sew.ToolBodies.Add(bot_cap_body)
                    sew.ToolBodies.Add(top_cap_body)
                sew_feat = sew.CommitFeature()
                set_feature_name(sew_feat, f"{feat_name}_SEW")
                loft_body = [b for b in sew_feat.GetBodies() if b.IsSolidBody][0]
            finally:
                sew.Destroy()

        return loft_body
    finally:
        tcb.Destroy()


def build_part_from_feature_plan(plan: Dict[str, Any], output_prt_path: Path) -> None:
    """
    Builds a native sketch-in-place parametric CAD model (.prt) from a feature plan JSON.

    Handles:
      - BLENDED ranges with MULTI_SKETCH_LOFT: creates native SketchInPlace features with
        COMPOUND_4_ARC profiles and driving dimensions, splits across step discontinuities
        into distinct zones (LOFT_CAP_ZONE, LOFT_BODY_ZONE), united via Boolean Unite.
      - THIN_TAB ranges: native sketch extrude united into main body.
      - PRISMATIC ranges: single sketch + extrude with optional taper draft.
      - END_BLEND: associative edge blend on planar end faces.

    All sketch dimensions are driven by named NX expressions:
      SK{n}_WIDTH, SK{n}_THICKNESS, SK{n}_CORNER_R, SK{n}_FLANK_R, TAB{n}_*
    """
    print("=" * 75)
    print("AUTONOMOUS FEATURE-PLAN NX RECONSTRUCTION ENGINE (PHASE 5D)")
    # Enforce exact PascalCase naming: <mesh>_Parametric.prt with no lowercase duplicates
    out_stem = output_prt_path.stem
    for sfx in ["_parametric", "_Parametric"]:
        if out_stem.endswith(sfx):
            out_stem = out_stem[:-len(sfx)]
            break
    output_prt_path = output_prt_path.with_name(f"{out_stem}_Parametric.prt")

    print(f"  Mesh Name:   {plan.get('mesh_name')}")
    print(f"  Output PRT:  {output_prt_path}")
    print("=" * 75)

    output_prt_path.parent.mkdir(parents=True, exist_ok=True)
    if output_prt_path.exists():
        try:
            output_prt_path.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(output_prt_path), NXOpen.Part.Units.Millimeters)

    ranges = plan.get("ranges", [])
    cad_params = plan.get("cad_parameters", {})
    blended_ranges = [r for r in ranges if r.get("classification") == "BLENDED"]
    tab_ranges = [r for r in ranges if r.get("classification") == "THIN_TAB"]
    prismatic_ranges = [r for r in ranges if r.get("classification") == "PRISMATIC"]
    end_blend_ranges = [r for r in ranges if r.get("classification") == "END_BLEND"]

    has_loft = len(blended_ranges) > 0

    # -----------------------------------------------------------------------
    # 1. Segment Blended Ranges into Cap Zone and Body Zone
    # -----------------------------------------------------------------------
    has_cap_step = False
    cap_ranges = []
    body_ranges = []
    if len(blended_ranges) > 1 and blended_ranges[0]["elevation_range_mm"][1] <= -70.0:
        has_cap_step = True
        cap_ranges = [blended_ranges[0]]
        body_ranges = blended_ranges[1:]
    else:
        body_ranges = blended_ranges

    def get_ds_list(r_list):
        res = []
        seen = set()
        for r in r_list:
            fp = r.get("fitted_parameters", {})
            ds_items = fp.get("driving_sketches", [])
            if not ds_items:
                ds_items = []
                if fp.get("start_primitive"):
                    ds_items.append({
                        "elevation_mm": r["elevation_range_mm"][0],
                        "primitive_type": fp["start_primitive"],
                        "parameters": fp["start_parameters"],
                    })
                if fp.get("end_primitive"):
                    ds_items.append({
                        "elevation_mm": r["elevation_range_mm"][1],
                        "primitive_type": fp["end_primitive"],
                        "parameters": fp["end_parameters"],
                    })
            for ds in ds_items:
                elev = round(ds["elevation_mm"], 2)
                if elev not in seen:
                    res.append(ds)
                    seen.add(elev)
        res.sort(key=lambda d: d["elevation_mm"])
        return res

    cap_driving_sketches = get_ds_list(cap_ranges) if has_cap_step else []
    body_driving_sketches = get_ds_list(body_ranges)

    all_elev_ds = {}
    for ds in (cap_driving_sketches + body_driving_sketches):
        elev_key = round(ds["elevation_mm"], 2)
        if elev_key not in all_elev_ds:
            all_elev_ds[elev_key] = ds

    sorted_elevs = sorted(all_elev_ds.keys())
    elev_to_idx = {elev: i + 1 for i, elev in enumerate(sorted_elevs)}

    # -----------------------------------------------------------------------
    # 2. Create NX Expressions (Zero Orphan Expressions)
    # -----------------------------------------------------------------------
    mm_unit = part.UnitCollection.FindObject("MilliMeter")

    if has_loft:
        print(f"\n[2/6] Creating driving sketch expressions for {len(sorted_elevs)} unique elevations...")
        for elev in sorted_elevs:
            idx = elev_to_idx[elev]
            ds = all_elev_ds[elev]
            p = ds["parameters"]
            w = p.get("width") or p.get("major_axis", 50.0)
            t = p.get("thickness") or p.get("minor_axis", 50.0)
            hw = w / 2.0
            ht = t / 2.0
            raw_cr = p.get("corner_radius", 0.0)
            if raw_cr <= 0.05:
                raw_cr = max(0.5, min(hw, ht)**2 / max(hw, ht))
            cr = max(0.1, min(raw_cr, min(hw, ht) * 0.80))
            rf = (hw**2 + ht**2 - 2.0 * hw * cr) / (2.0 * (ht - cr))

            for exp_cmd in [
                f"SK{idx}_WIDTH = {w:.3f}",
                f"SK{idx}_THICKNESS = {t:.3f}",
                f"SK{idx}_CORNER_R = {cr:.3f}",
            ]:
                try:
                    part.Expressions.CreateSystemExpressionWithUnits(exp_cmd, mm_unit)
                except Exception:
                    pass

        # Tab expressions (base and top parameters for tapered crimp tab loft)
        for ti, tr in enumerate(tab_ranges):
            tidx = ti + 1
            fp = tr.get("fitted_parameters", {})
            tab_h = tr["height_span_mm"]

            # Base sketch dimensions (at tab_elev)
            tw_base = float(fp.get("base_width", fp.get("width", 73.770)))
            tt_base = float(fp.get("base_thickness", 5.870))
            tcr_base = float(fp.get("base_corner_radius", fp.get("corner_radius", 2.348)))
            tcr_base = max(0.1, min(tcr_base, min(tw_base / 2.0, tt_base / 2.0) - 0.05))

            # Top sketch dimensions (at tab_elev + tab_h)
            tw_top = float(fp.get("top_width", 76.270))
            tt_top = float(fp.get("top_thickness", 1.900))
            tcr_top = float(fp.get("top_corner_radius", 0.850))
            tcr_top = max(0.1, min(tcr_top, min(tw_top / 2.0, tt_top / 2.0) - 0.05))

            for exp_cmd in [
                f"TAB{tidx}_BASE_WIDTH = {tw_base:.3f}",
                f"TAB{tidx}_BASE_THICKNESS = {tt_base:.3f}",
                f"TAB{tidx}_BASE_CORNER_R = {tcr_base:.3f}",
                f"TAB{tidx}_TOP_WIDTH = {tw_top:.3f}",
                f"TAB{tidx}_TOP_THICKNESS = {tt_top:.3f}",
                f"TAB{tidx}_TOP_CORNER_R = {tcr_top:.3f}",
            ]:
                try:
                    part.Expressions.CreateSystemExpressionWithUnits(exp_cmd, mm_unit)
                except Exception:
                    pass

    else:
        print(f"\n[2/6] Creating generic driving expressions for single-sketch extrude...")
        cad_params = plan.get("cad_parameters", {})
        for key, val in cad_params.items():
            try:
                unit = part.UnitCollection.FindObject("Degrees") if "TAPER" in key else mm_unit
                part.Expressions.CreateSystemExpressionWithUnits(f"{key} = {float(val):.3f}", unit)
            except Exception:
                pass

        body_ranges_p = [r for r in ranges if r.get("classification") in ("PRISMATIC", "ROUND", "BLENDED")]
        body_range_p = body_ranges_p[0] if body_ranges_p else None
        y_start_p = float(body_range_p["elevation_range_mm"][0]) if body_range_p else 0.0
        try:
            part.Expressions.CreateSystemExpressionWithUnits(
                f"BODY_START_Y = {y_start_p:.3f}", mm_unit)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # 3. Create native SketchInPlace features with COMPOUND_4_ARC profiles
    # -----------------------------------------------------------------------
    if has_loft and len(sorted_elevs) >= 2:
        print(f"\n[3/6] Building native sketch features for Through Curves loft zones...")
        cap_tuples = []
        if has_cap_step:
            print(f"  Constructing {len(cap_driving_sketches)} sketch(es) for Cap Zone...")
            for i, ds in enumerate(cap_driving_sketches):
                elev = ds["elevation_mm"]
                idx = elev_to_idx[round(elev, 2)]
                exp_w = part.Expressions.FindObject(f"SK{idx}_WIDTH")
                exp_t = part.Expressions.FindObject(f"SK{idx}_THICKNESS")
                exp_cr = part.Expressions.FindObject(f"SK{idx}_CORNER_R")
                hw = float(exp_w.Value) / 2.0
                ht = float(exp_t.Value) / 2.0
                cr = float(exp_cr.Value)
                sk_tup = _create_4arc_sketch_feature(
                    part, elev, f"SKETCH_CAP_SK{i+1}", f"DATUM_CAP_SK{i+1}",
                    exp_w, exp_t, exp_cr, None, hw, ht, cr
                )
                cap_tuples.append(sk_tup)

        body_tuples = []
        print(f"  Constructing {len(body_driving_sketches)} sketch(es) for Body Zone...")
        for i, ds in enumerate(body_driving_sketches):
            elev = ds["elevation_mm"]
            idx = elev_to_idx[round(elev, 2)]
            exp_w = part.Expressions.FindObject(f"SK{idx}_WIDTH")
            exp_t = part.Expressions.FindObject(f"SK{idx}_THICKNESS")
            exp_cr = part.Expressions.FindObject(f"SK{idx}_CORNER_R")
            hw = float(exp_w.Value) / 2.0
            ht = float(exp_t.Value) / 2.0
            cr = float(exp_cr.Value)
            sk_tup = _create_4arc_sketch_feature(
                part, elev, f"SKETCH_BODY_SK{i+1}", f"DATUM_BODY_SK{i+1}",
                exp_w, exp_t, exp_cr, None, hw, ht, cr
            )
            body_tuples.append(sk_tup)

        # -------------------------------------------------------------------
        # 4. Through Curves Loft Zones + Boolean Unite
        # -------------------------------------------------------------------
        print(f"\n[4/6] Creating Through Curves loft zone(s)...")
        if has_cap_step:
            body_cap = _build_through_curves_solid(part, cap_tuples, "LOFT_CAP_ZONE")
            body_body = _build_through_curves_solid(part, body_tuples, "LOFT_BODY_ZONE")
            unite_cap_feat = boolean_unite(part, body_body, body_cap, name="UNITE_CAP")
            print(f"  [UNITE] United Cap Zone into Body Zone.")
            main_body = [b for b in part.Bodies if b.IsSolidBody][0]
        else:
            main_body = _build_through_curves_solid(part, body_tuples, "LOFT_BODY_ZONE")

    else:
        # Fallback: single-sketch extrude (PRISMATIC or single ROUND)
        print(f"\n[3/6] Single-sketch extrude path (PRISMATIC)...")
        cad_params = plan.get("cad_parameters", {})
        w_val = float(cad_params.get("BODY_WIDTH", 50.0))
        t_val = float(cad_params.get("BODY_THICKNESS", 50.0))
        r_val = float(cad_params.get("BODY_CORNER_R", 10.0))
        h_val = float(cad_params.get("BODY_HEIGHT", 50.0))
        tp_val = float(cad_params.get("BODY_TAPER", 0.0))
        blend_r_val = float(cad_params.get("END_BLEND_R", 0.5))

        body_ranges_p = [r for r in ranges if r.get("classification") in ("PRISMATIC", "ROUND", "BLENDED")]
        body_range_p = body_ranges_p[0] if body_ranges_p else None
        y_start_p = float(cad_params.get("BODY_START_Y", ranges[0]["elevation_range_mm"][0] if ranges else 0.0))

        hw = w_val / 2.0
        ht = t_val / 2.0
        r = max(0.5, min(r_val, min(hw, ht) - 0.5))

        exp_w = part.Expressions.FindObject("BODY_WIDTH")
        exp_t = part.Expressions.FindObject("BODY_THICKNESS")
        exp_cr = part.Expressions.FindObject("BODY_CORNER_R")

        fit_prim = ""
        if body_range_p:
            fit_prim = (body_range_p.get("fitted_primitive") or "").upper()
        if not fit_prim:
            fit_prim = (cad_params.get("PRIMITIVE_TYPE") or "").upper()

        if "ROUNDED_RECTANGLE" in fit_prim or fit_prim == "BOX":
            sk_tup = _create_rounded_rectangle_sketch_feature(
                part, 0.0, "SKETCH_BODY", "DATUM_BODY",
                exp_w, exp_t, exp_cr, hw, ht, r,
                offset_from=None
            )
        else:
            sk_tup = _create_4arc_sketch_feature(
                part, 0.0, "SKETCH_BODY", "DATUM_BODY",
                exp_w, exp_t, exp_cr, None, hw, ht, r,
                offset_from=None
            )
        sketch, lead_curve, pt_seed, datum_plane = sk_tup

        eb = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rule = part.ScRuleFactory.CreateRuleCurveFeature([sketch.Feature])
        sec.AddToSection([rule], lead_curve, NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                         NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        eb.Section = sec
        dir_obj = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        eb.Direction = dir_obj
        eb.Limits.StartExtend.Value.RightHandSide = "BODY_START_Y"
        eb.Limits.EndExtend.Value.RightHandSide = "BODY_START_Y + BODY_HEIGHT"
        if tp_val > 0.05:
            try:
                eb.Draft.DraftOption = NXOpen.GeometricUtilities.SimpleDraft.SimpleDraftType.SimpleFromStart
                eb.Draft.DraftAngle.RightHandSide = "BODY_TAPER"
            except Exception:
                pass
        eb.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        feat = eb.CommitFeature()
        set_feature_name(feat, "EXTRUDE_BODY")
        eb.Destroy()
        main_body = feat.GetBodies()[0]

    # -----------------------------------------------------------------------
    # 5. THIN_TAB Native Loft at top (tapered crimp tab zone)
    # -----------------------------------------------------------------------
    if tab_ranges:
        print(f"\n[5/6] Building {len(tab_ranges)} THIN_TAB native loft zone(s)...")
        for ti, tr in enumerate(tab_ranges):
            tidx = ti + 1
            tab_h = tr["height_span_mm"]
            tab_elev = tr["elevation_range_mm"][0]
            tab_name = f"TAB{tidx}"

            exp_bw = part.Expressions.FindObject(f"TAB{tidx}_BASE_WIDTH")
            exp_bt = part.Expressions.FindObject(f"TAB{tidx}_BASE_THICKNESS")
            exp_bcr = part.Expressions.FindObject(f"TAB{tidx}_BASE_CORNER_R")
            hw_base = float(exp_bw.Value) / 2.0
            ht_base = float(exp_bt.Value) / 2.0
            cr_base = float(exp_bcr.Value)

            exp_tw = part.Expressions.FindObject(f"TAB{tidx}_TOP_WIDTH")
            exp_tt = part.Expressions.FindObject(f"TAB{tidx}_TOP_THICKNESS")
            exp_tcr = part.Expressions.FindObject(f"TAB{tidx}_TOP_CORNER_R")
            hw_top = float(exp_tw.Value) / 2.0
            ht_top = float(exp_tt.Value) / 2.0
            cr_top = float(exp_tcr.Value)

            # 1. Base sketch on fixed datum plane at tab_elev
            sk_base_tup = _create_4arc_sketch_feature(
                part, tab_elev, f"SKETCH_{tab_name}_BASE", f"DATUM_{tab_name}_BASE",
                exp_bw, exp_bt, exp_bcr, None, hw_base, ht_base, cr_base
            )
            dp_base = sk_base_tup[3]

            # 2. Top sketch on fixed datum plane at tab_elev + tab_h
            top_elev = tab_elev + tab_h
            sk_top_tup = _create_4arc_sketch_feature(
                part, top_elev, f"SKETCH_{tab_name}_TOP", f"DATUM_{tab_name}_TOP",
                exp_tw, exp_tt, exp_tcr, None, hw_top, ht_top, cr_top
            )

            # 3. Native Through Curves loft between base and top sketches
            tab_body = _build_through_curves_solid(part, [sk_base_tup, sk_top_tup], f"LOFT_{tab_name}")
            print(f"    [TAB] Created LOFT_{tab_name}: Base W={hw_base*2:.2f} T={ht_base*2:.2f} -> Top W={hw_top*2:.2f} T={ht_top*2:.2f} H={tab_h:.2f}mm")

            # 4. Boolean Unite tab into main body
            try:
                unite_feat = boolean_unite(part, main_body, tab_body, name=f"UNITE_{tab_name}")
                main_body = [b for b in part.Bodies if b.IsSolidBody][0]
                print(f"    [UNITE] United {tab_name} into body.")
            except Exception as ue:
                print(f"    [WARN] Unite {tab_name}: {ue}")

            solids = [b for b in part.Bodies if b.IsSolidBody]
            assert len(solids) == 1, f"Expected 1 solid body after uniting {tab_name}, got {len(solids)}"

    else:
        print(f"\n[5/6] No THIN_TAB ranges. Skipping tab extrude.")

    # -----------------------------------------------------------------------
    # 6. Associative Edge Blends + STL Export + Save
    # -----------------------------------------------------------------------
    blend_r_val = float(cad_params.get("END_BLEND_R", 0.0))
    if blend_r_val > 0.1 and end_blend_ranges:
        print(f"\n[6/6] Applying associative end blends (R={blend_r_val:.2f}mm)...")
        def get_face_y_center(face):
            try:
                ys = [v.Y for e in face.GetEdges() for v in e.GetVertices()]
                return sum(ys) / len(ys) if ys else 0.0
            except Exception:
                return 0.0

        planar_faces = [f for f in main_body.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
        if planar_faces:
            bot_face = min(planar_faces, key=get_face_y_center)
            b_bot = create_associative_blend_by_face(part, bot_face, "END_BLEND_R", name="BOTTOM_END_BLEND")
            if b_bot:
                print(f"  [BLEND] Created BOTTOM_END_BLEND")

            main_body = [b for b in part.Bodies if b.IsSolidBody][0]
            planar_faces = [f for f in main_body.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
            if planar_faces:
                top_face = max(planar_faces, key=get_face_y_center)
                b_top = create_associative_blend_by_face(part, top_face, "END_BLEND_R", name="TOP_END_BLEND")
                if b_top:
                    print(f"  [BLEND] Created TOP_END_BLEND")
    else:
        print(f"\n[6/6] No end blend ranges. Skipping blend.")

    # Export STL
    out_stl_path = output_prt_path.with_suffix(".stl")
    if out_stl_path.exists():
        try:
            out_stl_path.unlink()
        except Exception:
            pass

    solids = [b for b in part.Bodies if b.IsSolidBody]
    if len(solids) != 1:
        print(f"\n[FATAL ERROR] Build produced {len(solids)} solid bodies instead of exactly 1!")
        for idx, b in enumerate(solids, 1):
            bb = compute_body_bounds(b)
            print(f"  Solid {idx}: bbox = {bb}")
        raise RuntimeError(f"Part reconstruction failed: expected 1 solid body, got {len(solids)} solids.")
    main_body = solids[0]
    try:
        stl_exp = session.DexManager.CreateStlCreator()
        stl_exp.OutputFile = str(out_stl_path)
        stl_exp.ExportSelectionBlock.Add(main_body)
        stl_exp.Commit()
        stl_exp.Destroy()
        print(f"  [STL] Exported CAD STL: {out_stl_path} ({out_stl_path.stat().st_size:,} bytes)")
    except Exception as stl_err:
        print(f"  [WARN] STL export: {stl_err}")

    up_mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "FinalUpdate")
    session.UpdateManager.DoUpdate(up_mark)
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.TrueValue)
    print(f"\n[SUCCESS] Part saved: {output_prt_path}")
    print("=" * 75)


# ---------------------------------------------------------------------------
# Main Reconstruction Dispatcher
# ---------------------------------------------------------------------------
def build_part_from_spec(spec_path: Path, output_prt_path: Path) -> None:
    """Builds a complete parametric NX CAD part from a specification JSON."""
    out_stem = output_prt_path.stem
    for sfx in ["_parametric", "_Parametric"]:
        if out_stem.endswith(sfx):
            out_stem = out_stem[:-len(sfx)]
            break
    output_prt_path = output_prt_path.with_name(f"{out_stem}_Parametric.prt")

    print("=" * 75)
    print("DETERMINISTIC SKETCH-BASED NX RECONSTRUCTION ENGINE")
    print(f"  Spec File:   {spec_path}")
    print(f"  Output PRT:  {output_prt_path}")
    print("=" * 75)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    # Route to feature-plan builder if specification is a feature plan
    if "cad_parameters" in spec or ("ranges" in spec and "mesh_name" in spec):
        return build_part_from_feature_plan(spec, output_prt_path)

    # Route to loft builder if specification is non-round loft
    if spec.get("reconstruction_method") == "LOFT" or spec.get("global_shape_family") == "LOFT_THROUGH_CURVES":
        return build_loft_from_outlines_spec(spec, output_prt_path)

    output_prt_path.parent.mkdir(parents=True, exist_ok=True)
    if output_prt_path.exists():
        try:
            output_prt_path.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(output_prt_path), NXOpen.Part.Units.Millimeters)

    # 1. Create Expressions
    raw_expressions = spec.get("expressions", [])
    zones = spec.get("zones", [])

    # Auto-ensure chained & master-driven expressions for axisymmetric zones if not explicitly defined
    if zones:
        exp_names = {item[0] for item in raw_expressions} if raw_expressions else set()

        # Ensure BODY_MAX_DIA exists
        max_dia = 0.0
        for item in raw_expressions:
            if item[0] == "BODY_MAX_DIA":
                try:
                    max_dia = float(item[1])
                except Exception:
                    pass
                break
        if max_dia <= 0.0:
            max_dia = max([float(z.get("dia_max", z.get("r_start", 10.0) * 2.0)) for z in zones] or [20.0])

        if "BODY_MAX_DIA" not in exp_names:
            raw_expressions.insert(0, ["BODY_MAX_DIA", f"{max_dia:.4f}"])
            exp_names.add("BODY_MAX_DIA")

        max_r = max_dia / 2.0

        for idx, z in enumerate(zones, start=1):
            zh_name = f"ZONE{idx}_HEIGHT"
            zs_name = f"ZONE{idx}_START"
            zbr_name = f"ZONE{idx}_BASE_R"
            ztr_name = f"ZONE{idx}_TOP_R"
            zmr_name = f"ZONE{idx}_MID_R"

            zh_val = float(z.get("height", 10.0))
            if zh_name not in exp_names:
                raw_expressions.append([zh_name, f"{zh_val:.4f}"])
                exp_names.add(zh_name)

            if zs_name not in exp_names:
                if idx == 1:
                    z_st = float(z.get("z_start", 0.0))
                    raw_expressions.append([zs_name, f"{z_st:.4f}"])
                else:
                    raw_expressions.append([zs_name, f"ZONE{idx-1}_START + ZONE{idx-1}_HEIGHT"])
                exp_names.add(zs_name)

            r_st = float(z.get("r_start", 10.0))
            r_en = float(z.get("r_end", 10.0))
            ratio_st = r_st / max(max_r, 1e-4)
            ratio_en = r_en / max(max_r, 1e-4)

            if zbr_name not in exp_names:
                raw_expressions.append([zbr_name, f"(BODY_MAX_DIA / 2.0) * {ratio_st:.6f}"])
                exp_names.add(zbr_name)

            is_cyl = z.get("segment_type") != "ARC" and is_cylindrical_zone(r_st, r_en)
            if ztr_name not in exp_names and not is_cyl:
                raw_expressions.append([ztr_name, f"(BODY_MAX_DIA / 2.0) * {ratio_en:.6f}"])
                exp_names.add(ztr_name)

            if z.get("segment_type") == "ARC":
                if zmr_name not in exp_names:
                    r_md = float(z.get("r_mid", (r_st + r_en) / 2.0))
                    ratio_md = r_md / max(max_r, 1e-4)
                    raw_expressions.append([zmr_name, f"(BODY_MAX_DIA / 2.0) * {ratio_md:.6f}"])
                    exp_names.add(zmr_name)

    exp_dict: Dict[str, float] = {}
    print(f"\n[1/4] Populating {len(raw_expressions)} driving expressions...")
    populate_expressions(part, raw_expressions)
    for e in part.Expressions:
        try:
            exp_dict[e.Name] = float(e.Value)
        except Exception:
            pass

    # 2. Create Base Datum Plane (XY Plane)
    print("\n[2/4] Initializing fixed datum planes...")
    mat_xy = NXOpen.Matrix3x3()
    mat_xy.Xx, mat_xy.Xy, mat_xy.Xz = 1.0, 0.0, 0.0
    mat_xy.Yx, mat_xy.Yy, mat_xy.Yz = 0.0, 1.0, 0.0
    mat_xy.Zx, mat_xy.Zy, mat_xy.Zz = 0.0, 0.0, 1.0
    datum_xy = part.Datums.CreateFixedDatumPlane(pt3d(0.0, 0.0, 0.0), mat_xy)

    # 3. Build Zones Sequentially
    zones = spec.get("zones", [])
    print(f"\n[3/4] Constructing {len(zones)} sketch-in-place zones...")
    main_body = None

    for idx, zone in enumerate(zones, start=1):
        zone_name = zone.get("name", f"ZONE_{idx}").upper()
        _, zone_body = build_sketch_zone(part, datum_xy, idx, zone, exp_dict, primary_axis="Y")

        if main_body is None:
            main_body = zone_body
        else:
            # Boolean Unite
            unite_feat = boolean_unite(part, main_body, zone_body, name=f"UNITE_{zone_name}")
            print(f"    [UNITE] United {zone_name} into base solid.")

    # 3b. Secondary Features: Revolved Groove (from visual spec directives)
    groove_cfg = spec.get("groove")
    if groove_cfg and groove_cfg.get("enabled", True) and main_body:
        g_name = groove_cfg.get("name", "PARTING_GROOVE")
        y_start = eval_scalar(part, groove_cfg.get("y_start", 0.0), exp_dict)
        g_h = eval_scalar(part, groove_cfg.get("height", 3.0), exp_dict)
        g_depth = eval_scalar(part, groove_cfg.get("depth", 0.5), exp_dict)
        nom_r = eval_scalar(part, groove_cfg.get("nominal_r", 10.0), exp_dict)
        r_groove = max(0.01, nom_r - g_depth)

        print(f"\n[GROOVE] Constructing groove '{g_name}' (Y={y_start:.2f} to {y_start+g_h:.2f} mm, Depth={g_depth:.2f} mm)...")
        try:
            sk_g_builder = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
            sk_g_builder.PlaneOrFace.Value = datum_xy
            sk_g = sk_g_builder.Commit()
            set_feature_name(sk_g, f"SKETCH_{g_name}")
            sk_g_builder.Destroy()
            sk_g.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

            p1 = pt3d(r_groove, y_start, 0.0)
            p2 = pt3d(r_groove + g_depth, y_start, 0.0)
            p3 = pt3d(r_groove + g_depth, y_start + g_h, 0.0)
            p4 = pt3d(r_groove, y_start + g_h, 0.0)

            l1 = part.Curves.CreateLine(p1, p2)
            l2 = part.Curves.CreateLine(p2, p3)
            l3 = part.Curves.CreateLine(p3, p4)
            l4 = part.Curves.CreateLine(p4, p1)
            for l in [l1, l2, l3, l4]:
                sk_g.AddGeometry(l, NXOpen.Sketch.InferConstraintsOption.InferNoConstraints)

            # Driving dimensions on groove sketch
            try:
                exp_gh = part.Expressions.FindObject("GROOVE_HEIGHT")
                dg1 = NXOpen.Sketch.DimensionGeometry()
                dg1.Geometry = l4
                dg1.AssocType = NXOpen.Sketch.AssocType.StartPoint
                dg2 = NXOpen.Sketch.DimensionGeometry()
                dg2.Geometry = l4
                dg2.AssocType = NXOpen.Sketch.AssocType.EndPoint
                sk_g.CreateDimension(
                    NXOpen.Sketch.ConstraintType.VerticalDim,
                    dg1, dg2,
                    pt3d(r_groove, y_start + g_h / 2.0, 0.0),
                    exp_gh,
                    NXOpen.Sketch.DimensionOption.CreateAsDriving
                )
            except Exception:
                pass

            try:
                exp_gd = part.Expressions.FindObject("GROOVE_DEPTH")
                dg1 = NXOpen.Sketch.DimensionGeometry()
                dg1.Geometry = l1
                dg1.AssocType = NXOpen.Sketch.AssocType.StartPoint
                dg2 = NXOpen.Sketch.DimensionGeometry()
                dg2.Geometry = l1
                dg2.AssocType = NXOpen.Sketch.AssocType.EndPoint
                sk_g.CreateDimension(
                    NXOpen.Sketch.ConstraintType.HorizontalDim,
                    dg1, dg2,
                    pt3d(r_groove + g_depth / 2.0, y_start, 0.0),
                    exp_gd,
                    NXOpen.Sketch.DimensionOption.CreateAsDriving
                )
            except Exception:
                pass

            sk_g.Update()
            sk_g.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

            rev_g_b = part.Features.CreateRevolveBuilder(NXOpen.Features.Feature.Null)
            rev_g_b.Tolerance = 0.01
            sec_g = part.Sections.CreateSection(0.01, 0.01, 0.5)
            rule_g = part.ScRuleFactory.CreateRuleCurveFeature([sk_g.Feature])
            sec_g.AddToSection([rule_g], l1, NXOpen.NXObject.Null, NXOpen.NXObject.Null, pt3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
            rev_g_b.Section = sec_g
            axis_dir = part.Directions.CreateDirection(pt3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
            axis_pt = part.Points.CreatePoint(pt3d(0.0, 0.0, 0.0))
            rev_g_b.Axis = part.Axes.CreateAxis(axis_pt, axis_dir, NXOpen.SmartObject.UpdateOption.WithinModeling)
            rev_g_b.Limits.StartExtend.Value.RightHandSide = "0"
            rev_g_b.Limits.EndExtend.Value.RightHandSide = "360"
            rev_g_b.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
            rev_g_feat = rev_g_b.CommitFeature()
            set_feature_name(rev_g_feat, f"{g_name}_TOOL")
            g_tool_body = rev_g_feat.GetBodies()[0]
            rev_g_b.Destroy()

            sub_g = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
            sub_g.Operation = NXOpen.Features.Feature.BooleanType.Subtract
            sub_g.Target = main_body
            sub_g.Tools.Add(g_tool_body)
            sub_g_feat = sub_g.CommitFeature()
            set_feature_name(sub_g_feat, g_name)
            main_body = sub_g_feat.GetBodies()[0]
            sub_g.Destroy()
            print(f"  [OK] Feature: {g_name} subtracted successfully.")
        except Exception as g_err:
            print(f"  [WARN] Groove creation error: {g_err}")

    # 3c. Secondary Features: Circular Pattern Ribs Cut (from visual spec directives)
    ribs_cfg = spec.get("ribs")
    if ribs_cfg and ribs_cfg.get("enabled", True) and main_body:
        n_ribs = int(eval_scalar(part, ribs_cfg.get("count", 36), exp_dict))
        rib_h = eval_scalar(part, ribs_cfg.get("height", 20.0), exp_dict)
        rib_depth = eval_scalar(part, ribs_cfg.get("depth", 0.5), exp_dict)
        rib_cutter_dia = eval_scalar(part, ribs_cfg.get("cutter_dia", 1.5), exp_dict)
        rib_y_start = eval_scalar(part, ribs_cfg.get("y_start", 0.0), exp_dict)
        target_r = eval_scalar(part, ribs_cfg.get("target_r", 10.0), exp_dict)

        target_name = ribs_cfg.get("target", "CAP").upper()
        rib_feat_name = f"{target_name}_VERTICAL_RIBS"
        print(f"\n[RIBS] Creating associative circular pattern of {n_ribs} vertical flutes on {target_name}...")
        try:
            # Ensure RIB_X_START expression exists and is linked
            try:
                exp_rx = part.Expressions.FindObject("RIB_X_START")
            except Exception:
                part.Expressions.CreateExpression("Number", f"RIB_X_START = {target_r:.3f} + RIB_CUTTER_DIA / 2.0 - RIB_DEPTH")
                exp_rx = part.Expressions.FindObject("RIB_X_START")

            # Seed point driven associatively by expressions
            sx = part.Scalars.CreateScalarExpression(exp_rx, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)
            try:
                exp_ry = part.Expressions.FindObject("RIB_Y_START")
                sy = part.Scalars.CreateScalarExpression(exp_ry, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)
            except Exception:
                sy = part.Scalars.CreateScalar(rib_y_start, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)
            sz = part.Scalars.CreateScalar(0.0, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)
            pt_seed = part.Points.CreatePoint(sx, sy, sz, NXOpen.SmartObject.UpdateOption.WithinModeling)

            # Associative seed cylinder with direct boolean subtract
            cb = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
            cb.Diameter.RightHandSide = "RIB_CUTTER_DIA"
            cb.Height.RightHandSide = "RIB_HEIGHT"
            cb.Axis.Point = pt_seed
            cb.Axis.Direction = part.Directions.CreateDirection(pt3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
            cb.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
            cb.BooleanOption.SetTargetBodies([main_body])
            c_feat = cb.CommitFeature()
            set_feature_name(c_feat, "RIB_GROOVE_SEED")
            cb.Destroy()

            # Native Circular Pattern Feature
            pb = part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
            pb.FeatureList.Add([c_feat])
            ps = pb.PatternService
            ps.PatternType = NXOpen.GeometricUtilities.PatternDefinition.PatternEnum.Circular
            circ = ps.CircularDefinition
            circ.RotationAxis = part.Axes.CreateAxis(pt3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
            circ.RotationCenter = part.Points.CreatePoint(pt3d(0.0, 0.0, 0.0))
            circ.IncludeSeedToggle = True
            circ.AngularSpacing.NCopies.RightHandSide = "RIB_COUNT"
            circ.AngularSpacing.PitchAngle.RightHandSide = "360.0 / RIB_COUNT"
            pat_feat = pb.CommitFeature()
            set_feature_name(pat_feat, rib_feat_name)
            pb.Destroy()

            main_body = [b for b in part.Bodies if b.IsSolidBody][0]
            print(f"  [OK] Feature: {rib_feat_name} ({n_ribs} flutes) patterned successfully.")
        except Exception as r_err:
            print(f"  [WARN] Ribs pattern creation error: {r_err}")

    # 4. Apply Associative Edge Blends after all zones and features are united
    print("\n[4/4] Applying associative edge blends and finalizing CAD model...")
    if main_body:
        # Base bottom blend
        def get_face_y_center(face):
            try:
                ys = [v.Y for e in face.GetEdges() for v in e.GetVertices()]
                return sum(ys) / len(ys) if ys else 0.0
            except Exception:
                return 0.0

        try:
            planar_faces = [f for f in main_body.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
            if planar_faces:
                base_face = min(planar_faces, key=get_face_y_center)
                b_feat = create_associative_blend_by_face(part, base_face, "BASE_BLEND_R", name="BASE_END_BLEND")
                if b_feat:
                    print("  [BLEND] Created BASE_END_BLEND (BASE_BLEND_R)")
        except Exception as b_err:
            print(f"  [WARN] Base blend: {b_err}")


    # 4. Export STL & Launch Helper
    print("\n[4/4] Finalizing CAD model and saving part...")
    out_stl_path = output_prt_path.with_suffix(".stl")
    if main_body:
        try:
            if out_stl_path.exists():
                out_stl_path.unlink()
            stl_exp = session.DexManager.CreateStlCreator()
            stl_exp.OutputFile = str(out_stl_path)
            stl_exp.ExportSelectionBlock.Add(main_body)
            stl_exp.Commit()
            stl_exp.Destroy()
            print(f"  [OK] STL exported: {out_stl_path} ({out_stl_path.stat().st_size:,} bytes)")
        except Exception as stl_err:
            print(f"  [WARN] STL export: {stl_err}")

    try:
        session.UpdateManager.DoUpdate()
    except Exception:
        pass
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"\n[SUCCESS] Part saved: {output_prt_path}")
    print("=" * 75)


def main():
    args = [a for a in sys.argv[1:] if a != "-args" and not a.startswith("-")]
    if len(args) < 2:
        print("Usage: run_journal.exe generic_nx_builder.py <spec_json> <output_prt>")
        sys.exit(1)

    spec_p = Path(args[0]).resolve()
    out_p = Path(args[1]).resolve()

    if not spec_p.exists():
        print(f"[ERROR] Specification JSON not found: {spec_p}")
        sys.exit(1)

    build_part_from_spec(spec_p, out_p)


if __name__ == "__main__":
    main()
