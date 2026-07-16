"""Create a clean, production-ready, parametric refill pouch model in Siemens NX 2206.

This script implements a high-quality CAD modeling history for:
- Pouch_Body (flat silhouette envelope, edge blends, bulging body loft, top-left hanging hole, crimp details, and angled spout)
- Cap (angled cylinder on spout with vertical grip ribs and edge blend)
- All primary dimensions are controlled via Expressions.

Usage:
  run_journal.exe create_pouch.py [output_path.prt]
"""

from __future__ import annotations

import math
import os
import sys
import traceback
from pathlib import Path

import NXOpen
import NXOpen.UF

UF = NXOpen.UF.UFSession.GetUFSession()

# ---------------------------------------------------------------------------
# Primary parameters (mm) — Refill Pouch
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Height": 200.0,
    "Overall_Width": 120.0,
    "Overall_Depth": 40.0,
    "Wall_Thickness": 1.0,
    "Fill_Bulge_Depth": 38.0,
    "Shoulder_Height": 40.0,
    "Shoulder_Radius": 15.0,
    "Side_Taper": 2.0,
    "Top_Seal_Width": 15.0,
    "Bottom_Gusset_Height": 25.0,
    "Bottom_Gusset_Depth": 30.0,
    "Corner_Radius": 12.0,
    "Spout_Diameter": 12.0,
    "Spout_Length": 18.0,
    "Cap_Diameter": 16.0,
    "Cap_Height": 15.0,
    "Seal_Band_Width": 8.0,
    "Blend_Radius": 2.0,
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Pouch_Model.prt"


def v(part, name: str) -> float:
    try:
        expr = part.Expressions.FindObject(name)
        return float(expr.Value)
    except Exception:
        return float(VALUES[name])


def set_name(obj, name: str) -> None:
    try:
        obj.SetName(name)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------
def make_expressions(part) -> None:
    # 1. Base input parameters
    for name, value in VALUES.items():
        try:
            try:
                expr = part.Expressions.FindObject(name)
                expr.RightHandSide = str(value)
            except Exception:
                part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
        except Exception:
            pass

    # 2. Derived geometry parameters
    formulas = {
        "seal_thickness": "Wall_Thickness * 2.0",
        "half_width": "Overall_Width / 2.0",
        "hw_top": "Overall_Width / 2.0",
        "hw_bottom": "hw_top - Overall_Height * tan(Side_Taper * 3.14159265 / 180.0)",
        "z_shoulder": "Overall_Height - Shoulder_Height",
        "hw_shoulder": "hw_top - Shoulder_Height * tan(Side_Taper * 3.14159265 / 180.0)",
        "z_top": "Overall_Height",
        
        # Silhouette points in XZ plane
        "p1_x": "-hw_bottom",
        "p1_z": "0.0",
        "p2_x": "hw_bottom",
        "p2_z": "0.0",
        "p3_x": "hw_shoulder",
        "p3_z": "z_shoulder",
        "p4_x": "hw_top - Shoulder_Height",
        "p4_z": "z_top",
        "p5_x": "-hw_top",
        "p5_z": "z_top",
        
        # Spout normal and coordinates
        "spout_start_x": "(p3_x + p4_x) / 2.0",
        "spout_start_z": "(p3_z + p4_z) / 2.0",
        "shoulder_dx": "p4_x - p3_x",
        "shoulder_dz": "p4_z - p3_z",
        "shoulder_len": "sqrt(shoulder_dx * shoulder_dx + shoulder_dz * shoulder_dz)",
        "nx": "shoulder_dz / shoulder_len",
        "nz": "-shoulder_dx / shoulder_len",
        
        "spout_end_x": "spout_start_x + Spout_Length * nx",
        "spout_end_z": "spout_start_z + Spout_Length * nz",
        
        # Cap coordinates
        "cap_start_x": "spout_end_x",
        "cap_start_z": "spout_end_z",
        "cap_end_x": "cap_start_x + Cap_Height * nx",
        "cap_end_z": "cap_start_z + Cap_Height * nz",
        
        "cap_r": "Cap_Diameter / 2.0",
        "ux": "-nz",
        "uz": "nx",
        
        # Cap revolve profile points
        "cap_pt1_x": "cap_start_x",
        "cap_pt1_z": "cap_start_z",
        "cap_pt2_x": "cap_start_x + cap_r * ux",
        "cap_pt2_z": "cap_start_z + cap_r * uz",
        "cap_pt3_x": "cap_end_x + cap_r * ux",
        "cap_pt3_z": "cap_end_z + cap_r * uz",
        "cap_pt4_x": "cap_end_x",
        "cap_pt4_z": "cap_end_z",

        # Loft Sections height expressions
        "SEC_0_Z": "0.0",
        "SEC_1_Z": "Bottom_Gusset_Height",
        "SEC_2_Z": "Bottom_Gusset_Height + 0.4 * (Overall_Height - Top_Seal_Width - Bottom_Gusset_Height)",
        "SEC_3_Z": "Bottom_Gusset_Height + 0.7 * (Overall_Height - Top_Seal_Width - Bottom_Gusset_Height)",
        "SEC_4_Z": "Overall_Height - Top_Seal_Width",

        # Loft Sections width/depth/radius/center expressions
        "SEC_0_XC": "0.0",
        "SEC_0_W": "2.0 * (hw_bottom - Seal_Band_Width)",
        "SEC_0_D": "Bottom_Gusset_Depth",
        "SEC_0_R": "Blend_Radius",

        "SEC_1_XC": "0.0",
        "SEC_1_W": "2.0 * ((hw_top - (Overall_Height - SEC_1_Z) * tan(Side_Taper * 3.14159265 / 180.0)) - Seal_Band_Width)",
        "SEC_1_D": "seal_thickness - 0.1",
        "SEC_1_R": "Wall_Thickness",

        "SEC_2_XC": "0.0",
        "SEC_2_W": "2.0 * ((hw_top - (Overall_Height - SEC_2_Z) * tan(Side_Taper * 3.14159265 / 180.0)) - Seal_Band_Width)",
        "SEC_2_D": "Fill_Bulge_Depth",
        "SEC_2_R": "max(Corner_Radius - Seal_Band_Width, Blend_Radius)",

        "SEC_3_XC": "0.0",
        "SEC_3_W": "2.0 * ((hw_top - (Overall_Height - SEC_3_Z) * tan(Side_Taper * 3.14159265 / 180.0)) - Seal_Band_Width)",
        "SEC_3_D": "Fill_Bulge_Depth",
        "SEC_3_R": "max(Corner_Radius - Seal_Band_Width, Blend_Radius)",

        # Section 4 spans the asymmetric shoulder area, so we center it to the lateral inner centroid
        "x_right_sil_4": "hw_shoulder + (SEC_4_Z - z_shoulder) / (Overall_Height - z_shoulder) * ((hw_top - Shoulder_Height) - hw_shoulder)",
        "x_left_sil_4": "- (half_width - (Overall_Height - SEC_4_Z) * tan(Side_Taper * 3.14159265 / 180.0))",
        "SEC_4_L": "x_left_sil_4 + Seal_Band_Width",
        "SEC_4_R": "x_right_sil_4 - Seal_Band_Width",
        "SEC_4_W": "SEC_4_R - SEC_4_L",
        "SEC_4_XC": "(SEC_4_L + SEC_4_R) / 2.0",
        "SEC_4_D": "seal_thickness - 0.1",
        "SEC_4_cornR": "Wall_Thickness",

        "CRIMP_PITCH": "3.0",
        "CRIMP_DEPTH": "0.15",
        "CRIMP_COUNT_Z": "floor((z_shoulder - 20.0) / CRIMP_PITCH)",
        "CRIMP_COUNT_X": "floor((Overall_Width - Shoulder_Height - 10.0) / CRIMP_PITCH)",
    }
    
    for name, rhs in formulas.items():
        try:
            try:
                expr = part.Expressions.FindObject(name)
                expr.RightHandSide = rhs
            except Exception:
                part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))


def line(part, a, b):
    return part.Curves.CreateLine(point(*a), point(*b))


def assoc_line(part, pt1, pt2):
    builder = part.BaseFeatures.CreateAssociativeLineBuilder(NXOpen.Features.AssociativeLine.Null)
    try:
        builder.StartPointOptions = NXOpen.Features.AssociativeLineBuilderStartOption.Point
        builder.EndPointOptions = NXOpen.Features.AssociativeLineBuilderEndOption.Point
        builder.StartPoint.Value = pt1
        builder.EndPoint.Value = pt2
        feat = builder.CommitFeature()
        entities = feat.GetEntities()
        return entities[0] if entities else None
    finally:
        builder.Destroy()


_pt_counter = 0

def make_assoc_point(part, x_expr, y_expr, z_expr):
    global _pt_counter
    _pt_counter += 1
    expr_x = part.Expressions.CreateExpression("Number", "PT_{}_X = {}".format(_pt_counter, x_expr))
    expr_y = part.Expressions.CreateExpression("Number", "PT_{}_Y = {}".format(_pt_counter, y_expr))
    expr_z = part.Expressions.CreateExpression("Number", "PT_{}_Z = {}".format(_pt_counter, z_expr))
    
    csys = part.WCS.CoordinateSystem
    x_scalar = part.Scalars.CreateScalarExpression(expr_x, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)
    y_scalar = part.Scalars.CreateScalarExpression(expr_y, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)
    z_scalar = part.Scalars.CreateScalarExpression(expr_z, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)
    return part.Points.CreatePoint(csys, x_scalar, y_scalar, z_scalar, NXOpen.SmartObject.UpdateOption.WithinModeling)


# ---------------------------------------------------------------------------
# Section, Extrude, Revolve
# ---------------------------------------------------------------------------
def nx_section(part, curves):
    sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
    rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    sec.AddToSection(
        rules,
        curves[0],
        NXOpen.NXObject.Null,
        NXOpen.NXObject.Null,
        point(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create,
        False,
    )
    return sec


def extrude(part, curves, dir_vec, start_rhs, end_rhs, name, target=None, subtract=False):
    builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = nx_section(part, curves)
        builder.Direction = part.Directions.CreateDirection(
            point(0.0, 0.0, 0.0),
            dir_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Limits.StartExtend.Value.RightHandSide = str(start_rhs)
        builder.Limits.EndExtend.Value.RightHandSide = str(end_rhs)
        if target is not None:
            bool_type = (
                NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
                if subtract
                else NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite
            )
            builder.BooleanOperation.SetBooleanOperationAndBody(bool_type, target)
        else:
            builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, target if target is not None else (bodies[0] if bodies else None)


def revolve_curves(part, curves, axis_start_pt, axis_dir_vec, name):
    tags = [c.Tag for c in curves]
    ax_x = float(axis_start_pt.Coordinates.X)
    ax_y = float(axis_start_pt.Coordinates.Y)
    ax_z = float(axis_start_pt.Coordinates.Z)
    axis_pt = [ax_x, ax_y, ax_z]
    axis_dir = [float(axis_dir_vec.X), float(axis_dir_vec.Y), float(axis_dir_vec.Z)]
    
    features, number_of_features = UF.Modl.CreateRevolution(
        tags,
        len(tags),
        None,
        ["0", "360.0"],
        ["0", "0"],
        axis_pt,
        False,
        True,
        axis_pt,
        axis_dir,
        NXOpen.UF.Modl.FeatureSigns.NULLSIGN,
    )
    
    if number_of_features > 0 and features:
        feature = NXOpen.TaggedObjectManager().GetTaggedObject(features[0])
        set_name(feature, name)
        bodies = feature.GetBodies()
        return feature, bodies[0] if bodies else None
    return None, None


# ---------------------------------------------------------------------------
# Cylinder and Pattern helpers
# ---------------------------------------------------------------------------
def create_cylinder_feature(part, center_pt, direction_vec, diameter_rhs, height_rhs, name, target=None):
    builder = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Diameter.RightHandSide = diameter_rhs
        builder.Height.RightHandSide = height_rhs
        builder.Axis.Point = center_pt
        builder.Axis.Direction = part.Directions.CreateDirection(point(0.0, 0.0, 0.0), direction_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
        
        if hasattr(builder, "Boolean"):
            builder.Boolean.Type = NXOpen.Features.Feature.BooleanType.Create
            
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    cylinder_body = bodies[0] if bodies else None
    
    if target is not None and cylinder_body is not None:
        return feat, unite(part, target, cylinder_body, "UNITE_{}".format(name))
    return feat, target if target is not None else cylinder_body


def pattern_circular(part, feature, center_pt, axis_dir_vec, count_expr, angle_expr, name):
    builder = part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        if hasattr(builder, "FeatureList"):
            builder.FeatureList.Add([feature])
        elif hasattr(builder, "Features"):
            builder.Features.Add([feature])
        elif hasattr(builder, "Feature"):
            builder.Feature = feature
        service = builder.PatternService
        
        if hasattr(service, "PatternType"):
            try:
                service.PatternType = getattr(
                    type(service).PatternType,
                    "Circular",
                    service.PatternType
                )
            except Exception:
                pass
                
        axis_direction = part.Directions.CreateDirection(point(0.0, 0.0, 0.0), axis_dir_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
        
        circ = getattr(service, "CircularDefinition", None)
        if circ is not None:
            circ.RotationAxis = part.Axes.CreateAxis(center_pt.Coordinates, axis_dir_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
            circ.RotationCenter = center_pt
            circ.AngularSpacing.NCopies.RightHandSide = count_expr
            circ.AngularSpacing.PitchAngle.RightHandSide = angle_expr
        else:
            # Fallback
            rect = getattr(service, "RectangularDefinition", None)
            if rect is not None:
                rect.XDirection = axis_direction
                rect.UseYDirectionToggle = False
                rect.XSpacing.NCopies.RightHandSide = count_expr
                rect.XSpacing.PitchDistance.RightHandSide = angle_expr
                
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    return feat


# ---------------------------------------------------------------------------
# Boolean helpers
# ---------------------------------------------------------------------------
def set_boolean_inputs(builder, part, target_body, tool_body):
    tool_bodies = list(tool_body) if isinstance(tool_body, (list, tuple)) else [tool_body]
    single_tool = tool_bodies[0] if tool_bodies else None
    
    if hasattr(builder, "Targets") and (hasattr(builder, "ToolBodyCollector") or hasattr(builder, "BooleanTool")):
        try:
            builder.Targets.Add(target_body)
            collector = part.ScCollectors.CreateCollector()
            rule = part.ScRuleFactory.CreateRuleBodyDumb(tool_bodies, True)
            collector.ReplaceRules([rule], False)
            if hasattr(builder, "ToolBodyCollector"):
                builder.ToolBodyCollector = collector
                return
            elif hasattr(builder, "BooleanTool"):
                boolean_tool = builder.BooleanTool
                for attr in ("BodyCollector", "ToolBodyCollector"):
                    if hasattr(boolean_tool, attr):
                        setattr(boolean_tool, attr, collector)
                        return
        except Exception:
            pass

    for attr in ("Target", "TargetBody"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, target_body)
                break
            except Exception:
                pass

    for attr in ("Tool", "ToolBody"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, single_tool)
                return
            except Exception:
                pass

    if hasattr(builder, "Targets"):
        try:
            builder.Targets.Add([target_body])
        except Exception:
            pass
    if hasattr(builder, "Tools"):
        try:
            builder.Tools.Add([tool_body])
            return
        except Exception:
            pass

    collector = part.ScCollectors.CreateCollector()
    rule = part.ScRuleFactory.CreateRuleBodyDumb([tool_body], True)
    collector.ReplaceRules([rule], False)
    for attr in ("ToolBodyCollector", "ToolCollector"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, collector)
                return
            except Exception:
                try:
                    getattr(builder, attr).ReplaceRules(collector.GetRules(), False)
                    return
                except Exception:
                    pass

    boolean_tool = getattr(builder, "BooleanTool", None)
    if boolean_tool is not None:
        for attr in ("BodyCollector", "ToolBodyCollector"):
            if hasattr(boolean_tool, attr):
                try:
                    setattr(boolean_tool, attr, collector)
                    return
                except Exception:
                    pass
    raise RuntimeError("Could not assign boolean target/tool bodies")


def unite(part, target, tool, name):
    builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        set_boolean_inputs(builder, part, target, tool)
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return bodies[0] if bodies else target


# ---------------------------------------------------------------------------
# Edge helpers
# ---------------------------------------------------------------------------
def edge_points(edge):
    try:
        verts = edge.GetVertices()
        if verts and len(verts) >= 2:
            return (float(verts[0].X), float(verts[0].Y), float(verts[0].Z)), (float(verts[1].X), float(verts[1].Y), float(verts[1].Z))
        elif verts and len(verts) == 1:
            pt = (float(verts[0].X), float(verts[0].Y), float(verts[0].Z))
            return pt, pt
    except Exception:
        pass
    return None


def find_edge_near_xz(body, target_x, target_z, tolerance=2.0):
    for edge in list(body.GetEdges() or []):
        verts = edge.GetVertices()
        if verts and len(verts) >= 2:
            x_mid = (verts[0].X + verts[1].X) * 0.5
            z_mid = (verts[0].Z + verts[1].Z) * 0.5
            y_diff = abs(verts[0].Y - verts[1].Y)
            x_diff = abs(verts[0].X - verts[1].X)
            z_diff = abs(verts[0].Z - verts[1].Z)
            # Find vertical-ish edges parallel to the Y-axis
            if x_diff < 0.1 and z_diff < 0.1 and y_diff > 0.1:
                dist = math.hypot(x_mid - target_x, z_mid - target_z)
                if dist < tolerance:
                    return edge
    return None


def blend_corners(part, body, edge_radius_map):
    groups = {}
    for edge, rad in edge_radius_map:
        if edge is None:
            continue
        groups.setdefault(rad, []).append(edge)
    
    for rad, edges in groups.items():
        builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = part.ScCollectors.CreateCollector()
            collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(edges)], False)
            builder.Tolerance = 0.01
            builder.AddChainset(collector, str(rad))
            feat = builder.CommitFeature()
        finally:
            builder.Destroy()
        set_name(feat, f"EDGE_BLEND_{rad}")


def find_cap_top_edge(cap_body, cap_top_center):
    best_edge = None
    min_dist = 999999.0
    for edge in list(cap_body.GetEdges() or []):
        pts = edge_points(edge)
        if pts:
            mid = ((pts[0][0] + pts[1][0]) * 0.5, (pts[0][1] + pts[1][1]) * 0.5, (pts[0][2] + pts[1][2]) * 0.5)
            dist = math.hypot(math.hypot(mid[0] - cap_top_center[0], mid[1] - cap_top_center[1]), mid[2] - cap_top_center[2])
            if dist < min_dist:
                min_dist = dist
                best_edge = edge
    return best_edge


def assoc_arc(part, pt1, pt2, pt3):
    builder = part.BaseFeatures.CreateAssociativeArcBuilder(NXOpen.Features.AssociativeArc.Null)
    try:
        builder.Type = NXOpen.Features.AssociativeArcBuilder.Types.ThreePointArc
        builder.StartPointOptions = NXOpen.Features.AssociativeArcBuilderStartOption.Point
        builder.MidPointOptions = NXOpen.Features.AssociativeArcBuilderMidOption.Point
        builder.EndPointOptions = NXOpen.Features.AssociativeArcBuilderEndOption.Point
        
        builder.StartPoint.Value = pt1
        builder.MidPoint.Value = pt2
        builder.EndPoint.Value = pt3
        
        feat = builder.CommitFeature()
        entities = feat.GetEntities()
        return entities[0] if entities else None
    finally:
        builder.Destroy()
# ---------------------------------------------------------------------------
# Stadium Section generator (Associative/Parametric)
# ---------------------------------------------------------------------------
def make_stadium_section(part, prefix):
    # SEC_4 uses a separately-named corner radius to avoid collision with
    # the right-boundary expression SEC_4_R.
    r_expr = f"{prefix}_cornR" if prefix == "SEC_4" else f"{prefix}_R"

    # Derived helper expressions
    formulas = {
        f"{prefix}_HW":       f"{prefix}_W / 2.0",
        f"{prefix}_HD":       f"{prefix}_D / 2.0",
        # RC = radius clamped so it never exceeds half-width or half-depth
        f"{prefix}_RC":       f"min({r_expr}, {prefix}_HW - 0.5, {prefix}_HD - 0.5)",
        f"{prefix}_R_offset": f"{prefix}_RC * 0.2928932188",  # RC*(1-cos45)
    }
    for name, formula in formulas.items():
        try:
            expr = part.Expressions.FindObject(name)
            expr.RightHandSide = formula
        except Exception:
            part.Expressions.CreateExpression("Number", f"{name} = {formula}")

    rc = f"{prefix}_RC"          # clamped radius expression name
    ro = f"{prefix}_R_offset"    # 45-degree offset expression name
    hw = f"{prefix}_HW"
    hd = f"{prefix}_HD"
    xc = f"{prefix}_XC"
    z  = f"{prefix}_Z"

    # 12 corner/edge points that define the rounded-rectangle contour
    pt_coords = {
        "pt1":  (f"{xc} + {hw}",          f"{hd} - {rc}",      z),
        "pt2":  (f"{xc} + {hw} - {ro}",   f"{hd} - {ro}",      z),
        "pt3":  (f"{xc} + {hw} - {rc}",   f"{hd}",             z),

        "pt4":  (f"{xc} - ({hw} - {rc})", f"{hd}",             z),
        "pt5":  (f"{xc} - ({hw} - {ro})", f"{hd} - {ro}",      z),
        "pt6":  (f"{xc} - {hw}",          f"{hd} - {rc}",      z),

        "pt7":  (f"{xc} - {hw}",          f"-({hd} - {rc})",   z),
        "pt8":  (f"{xc} - ({hw} - {ro})", f"-({hd} - {ro})",   z),
        "pt9":  (f"{xc} - ({hw} - {rc})", f"-{hd}",            z),

        "pt10": (f"{xc} + {hw} - {rc}",   f"-{hd}",            z),
        "pt11": (f"{xc} + {hw} - {ro}",   f"-({hd} - {ro})",   z),
        "pt12": (f"{xc} + {hw}",          f"-({hd} - {rc})",   z),
    }

    pts = {}
    for name, coords in pt_coords.items():
        pts[name] = make_assoc_point(part, coords[0], coords[1], coords[2])

    curves = [
        assoc_arc(part,  pts["pt1"],  pts["pt2"],  pts["pt3"]),
        assoc_line(part, pts["pt3"],  pts["pt4"]),
        assoc_arc(part,  pts["pt4"],  pts["pt5"],  pts["pt6"]),
        assoc_line(part, pts["pt6"],  pts["pt7"]),
        assoc_arc(part,  pts["pt7"],  pts["pt8"],  pts["pt9"]),
        assoc_line(part, pts["pt9"],  pts["pt10"]),
        assoc_arc(part,  pts["pt10"], pts["pt11"], pts["pt12"]),
        assoc_line(part, pts["pt12"], pts["pt1"]),
    ]
    return curves


# ---------------------------------------------------------------------------
# Through Curves (Loft)
# ---------------------------------------------------------------------------
def append_section(builder, sec) -> None:
    container = getattr(builder, "SectionsList", None) or getattr(builder, "Sections", None)
    if hasattr(container, "Append"):
        container.Append(sec)
    else:
        container.Add(sec)


def through_curves(part, sections, name):
    builder = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        try:
            builder.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
        except Exception:
            pass
        for sec in sections:
            append_section(builder, sec)
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, bodies[0] if bodies else None


def pattern_linear(part, feature, direction_vec, count_expr, pitch_expr, name):
    builder = part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        if hasattr(builder, "FeatureList"):
            builder.FeatureList.Add([feature])
        elif hasattr(builder, "Features"):
            builder.Features.Add([feature])
        elif hasattr(builder, "Feature"):
            builder.Feature = feature
        service = builder.PatternService
        
        if hasattr(service, "PatternType"):
            try:
                service.PatternType = getattr(
                    type(service).PatternType,
                    "Rectangular",
                    service.PatternType
                )
            except Exception:
                try:
                    service.PatternType = getattr(
                        type(service).PatternType,
                        "Linear",
                        service.PatternType
                    )
                except Exception:
                    pass
                    
        origin = point(0.0, 0.0, 0.0)
        direction = part.Directions.CreateDirection(origin, direction_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
        
        rect = getattr(service, "RectangularDefinition", None)
        if rect is not None:
            rect.XDirection = direction
            rect.UseYDirectionToggle = False
            rect.XSpacing.NCopies.RightHandSide = count_expr
            rect.XSpacing.PitchDistance.RightHandSide = pitch_expr
        else:
            service.PatternCount.RightHandSide = count_expr
            service.Pitch.RightHandSide = pitch_expr
            if hasattr(service, "Direction"):
                service.Direction = direction
                
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    return feat


# ---------------------------------------------------------------------------
# Crimp details generator
# ---------------------------------------------------------------------------
def apply_crimp_details(part, pouch):
    width = v(part, "Overall_Width")
    height = v(part, "Overall_Height")
    w_thickness = v(part, "Wall_Thickness")
    
    # 1. Front horizontal crimp at Z = 10.0
    p1 = (-width * 0.6, w_thickness, 10.0 - 0.2)
    p2 = (width * 0.6, w_thickness, 10.0 - 0.2)
    p3 = (width * 0.6, w_thickness, 10.0 + 0.2)
    p4 = (-width * 0.6, w_thickness, 10.0 + 0.2)
    c1 = line(part, p1, p2)
    c2 = line(part, p2, p3)
    c3 = line(part, p3, p4)
    c4 = line(part, p4, p1)
    
    feat_front, pouch = extrude(part, [c1, c2, c3, c4], vec(0.0, -1.0, 0.0), "0.0", "CRIMP_DEPTH", "CRIMP_CUT_FRONT_BASE", target=pouch, subtract=True)
    pattern_linear(part, feat_front, vec(0.0, 0.0, 1.0), "CRIMP_COUNT_Z", "CRIMP_PITCH", "PATTERN_CRIMP_FRONT")
    
    # 2. Back horizontal crimp at Z = 10.0
    pb1 = (-width * 0.6, -w_thickness, 10.0 - 0.2)
    pb2 = (width * 0.6, -w_thickness, 10.0 - 0.2)
    pb3 = (width * 0.6, -w_thickness, 10.0 + 0.2)
    pb4 = (-width * 0.6, -w_thickness, 10.0 + 0.2)
    cb1 = line(part, pb1, pb2)
    cb2 = line(part, pb2, pb3)
    cb3 = line(part, pb3, pb4)
    cb4 = line(part, pb4, pb1)
    
    feat_back, pouch = extrude(part, [cb1, cb2, cb3, cb4], vec(0.0, 1.0, 0.0), "0.0", "CRIMP_DEPTH", "CRIMP_CUT_BACK_BASE", target=pouch, subtract=True)
    pattern_linear(part, feat_back, vec(0.0, 0.0, 1.0), "CRIMP_COUNT_Z", "CRIMP_PITCH", "PATTERN_CRIMP_BACK")
    
    # 3. Top seal vertical crimp
    top_seal = v(part, "Top_Seal_Width")
    x0 = -width * 0.5 + 5.0
    z0 = height - top_seal - 1.0
    z1 = height + 5.0
    
    # Front vertical crimp
    pf1 = (x0 - 0.2, w_thickness, z0)
    pf2 = (x0 + 0.2, w_thickness, z0)
    pf3 = (x0 + 0.2, w_thickness, z1)
    pf4 = (x0 - 0.2, w_thickness, z1)
    cf1 = line(part, pf1, pf2)
    cf2 = line(part, pf2, pf3)
    cf3 = line(part, pf3, pf4)
    cf4 = line(part, pf4, pf1)
    
    feat_top_front, pouch = extrude(part, [cf1, cf2, cf3, cf4], vec(0.0, -1.0, 0.0), "0.0", "CRIMP_DEPTH", "CRIMP_CUT_TOP_FRONT_BASE", target=pouch, subtract=True)
    pattern_linear(part, feat_top_front, vec(1.0, 0.0, 0.0), "CRIMP_COUNT_X", "CRIMP_PITCH", "PATTERN_CRIMP_TOP_FRONT")
    
    # Back vertical crimp
    pbf1 = (x0 - 0.2, -w_thickness, z0)
    pbf2 = (x0 + 0.2, -w_thickness, z0)
    pbf3 = (x0 + 0.2, -w_thickness, z1)
    pbf4 = (x0 - 0.2, -w_thickness, z1)
    cbf1 = line(part, pbf1, pbf2)
    cbf2 = line(part, pbf2, pbf3)
    cbf3 = line(part, pbf3, pbf4)
    cbf4 = line(part, pbf4, pbf1)
    
    feat_top_back, pouch = extrude(part, [cbf1, cbf2, cbf3, cbf4], vec(0.0, 1.0, 0.0), "0.0", "CRIMP_DEPTH", "CRIMP_CUT_TOP_BACK_BASE", target=pouch, subtract=True)
    pattern_linear(part, feat_top_back, vec(1.0, 0.0, 0.0), "CRIMP_COUNT_X", "CRIMP_PITCH", "PATTERN_CRIMP_TOP_BACK")
    
    return pouch


# ---------------------------------------------------------------------------
# Launch file helpers
# ---------------------------------------------------------------------------
def write_launch_files(path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    (root / "latest_nx_result.txt").write_text(str(path), encoding="utf-8")
    base = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
    router = Path(base) / "NXBIN" / "ugs_router.exe"
    (root / "open_current_nx_result.cmd").write_text(
        '@echo off\nstart "" "{}" -ug -use_file_dir "{}"\n'.format(router, path),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    path = out_path()
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = None
    try:
        part = session.Parts.FindObject(path.name)
    except Exception:
        pass

    if part is not None:
        part.Close(NXOpen.BasePart.CloseWholeTree.TrueValue, NXOpen.BasePart.CloseModified.CloseWithSaving, None)

    session.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)
    part = session.Parts.Work
    print("Building Parametric Refill Pouch")
    print("--------------------------------")

    # Step 1: Expressions
    make_expressions(part)

    # Read current parameters for edge finding
    taper_rad = math.radians(v(part, "Side_Taper"))
    hw_top = v(part, "Overall_Width") / 2.0
    hw_bottom = hw_top - v(part, "Overall_Height") * math.tan(taper_rad)
    z_shoulder = v(part, "Overall_Height") - v(part, "Shoulder_Height")
    hw_shoulder = hw_top - v(part, "Shoulder_Height") * math.tan(taper_rad)
    z_top = v(part, "Overall_Height")

    # -----------------------------------------------------------------------
    # Step 2: Silhouette Envelope (Flat Plate)
    # -----------------------------------------------------------------------
    # Create associative points for envelope corners
    pt_p1 = make_assoc_point(part, "p1_x", "0.0", "p1_z")
    pt_p2 = make_assoc_point(part, "p2_x", "0.0", "p2_z")
    pt_p3 = make_assoc_point(part, "p3_x", "0.0", "p3_z")
    pt_p4 = make_assoc_point(part, "p4_x", "0.0", "p4_z")
    pt_p5 = make_assoc_point(part, "p5_x", "0.0", "p5_z")

    envelope_curves = [
        assoc_line(part, pt_p1, pt_p2),
        assoc_line(part, pt_p2, pt_p3),
        assoc_line(part, pt_p3, pt_p4),
        assoc_line(part, pt_p4, pt_p5),
        assoc_line(part, pt_p5, pt_p1),
    ]

    _, pouch = extrude(part, envelope_curves, vec(0.0, 1.0, 0.0), "-Wall_Thickness", "Wall_Thickness", "EXTRUDE_ENVELOPE")
    print("[OK] Envelope extruded")

    # Step 2b: Apply Edge Blends to silhouette corners
    p1 = (-hw_bottom, 0.0, 0.0)
    p2 = (hw_bottom, 0.0, 0.0)
    p3 = (hw_shoulder, 0.0, z_shoulder)
    p4 = (hw_top - v(part, "Shoulder_Height"), 0.0, z_top)
    p5 = (-hw_top, 0.0, z_top)

    edge_p1 = find_edge_near_xz(pouch, p1[0], p1[2])
    edge_p2 = find_edge_near_xz(pouch, p2[0], p2[2])
    edge_p3 = find_edge_near_xz(pouch, p3[0], p3[2])
    edge_p4 = find_edge_near_xz(pouch, p4[0], p4[2])
    edge_p5 = find_edge_near_xz(pouch, p5[0], p5[2])

    edge_radius_map = [
        (edge_p1, "Corner_Radius"),
        (edge_p2, "Corner_Radius"),
        (edge_p3, "Shoulder_Radius"),
        (edge_p4, "Shoulder_Radius"),
        (edge_p5, "Corner_Radius"),
    ]
    blend_corners(part, pouch, edge_radius_map)
    print("[OK] Envelope corners blended")

    # -----------------------------------------------------------------------
    # Step 3: Central Puffy Body (Loft)
    # -----------------------------------------------------------------------
    # Generate 5 stadium sections
    sec0_curves = make_stadium_section(part, "SEC_0")
    sec1_curves = make_stadium_section(part, "SEC_1")
    sec2_curves = make_stadium_section(part, "SEC_2")
    sec3_curves = make_stadium_section(part, "SEC_3")
    sec4_curves = make_stadium_section(part, "SEC_4")

    # Force update to compute curve geometry of all 5 sections before constructing NX sections
    try:
        session.UpdateManager.DoUpdate(session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "Section Curves Update"))
    except Exception as e:
        print("[WARN] Section curves update warning: {}".format(e))

    sections = [
        nx_section(part, sec0_curves),
        nx_section(part, sec1_curves),
        nx_section(part, sec2_curves),
        nx_section(part, sec3_curves),
        nx_section(part, sec4_curves),
    ]

    _, puffy = through_curves(part, sections, "THROUGH_CURVES_PUFFY")
    pouch = unite(part, pouch, puffy, "UNITE_PUFFY_BODY")
    print("[OK] Puffy body lofted and united")

    # -----------------------------------------------------------------------
    # Step 4: Raised Sealing Band Crimp Details
    # -----------------------------------------------------------------------
    pouch = apply_crimp_details(part, pouch)
    print("[OK] Perimeter crimp details applied")

    # -----------------------------------------------------------------------
    # Step 5: Hanging Hole
    # -----------------------------------------------------------------------
    z_hole = z_top - v(part, "Top_Seal_Width") * 0.5
    x_hole = -hw_top + v(part, "Seal_Band_Width") * 1.5
    hole_curves = circle_profile_xz = []
    # Make hole circular profile
    r_h = 3.0
    for i in range(36):
        a1 = 2.0 * math.pi * float(i) / 36.0
        a2 = 2.0 * math.pi * float(i + 1) / 36.0
        p_a = (x_hole + r_h * math.cos(a1), 0.0, z_hole + r_h * math.sin(a1))
        p_b = (x_hole + r_h * math.cos(a2), 0.0, z_hole + r_h * math.sin(a2))
        circle_profile_xz.append(line(part, p_a, p_b))

    _, pouch = extrude(part, circle_profile_xz, vec(0.0, 1.0, 0.0), "-Wall_Thickness * 3.0", "Wall_Thickness * 3.0", "EXTRUDE_HOLE", target=pouch, subtract=True)
    print("[OK] Hanging hole created")

    # -----------------------------------------------------------------------
    # Step 6: Spout
    # -----------------------------------------------------------------------
    # Calculate directions
    nx = v(part, "nx")
    nz = v(part, "nz")
    
    spout_start_pt = make_assoc_point(part, "spout_start_x", "0.0", "spout_start_z")
    
    # Create spout cylinder (parametric)
    _, pouch = create_cylinder_feature(
        part,
        spout_start_pt,
        vec(nx, 0.0, nz),
        "Spout_Diameter",
        "Spout_Length",
        "EXTRUDE_SPOUT",
        target=pouch
    )
    print("[OK] Spout cylinder created and united")

    set_name(pouch, "Pouch_Body")

    # -----------------------------------------------------------------------
    # Step 7: Cap (Revolve & Pattern Grip Ribs)
    # -----------------------------------------------------------------------
    # 4 points of the Cap revolve profile rectangle
    cap_pt1 = make_assoc_point(part, "cap_pt1_x", "0.0", "cap_pt1_z")
    cap_pt2 = make_assoc_point(part, "cap_pt2_x", "0.0", "cap_pt2_z")
    cap_pt3 = make_assoc_point(part, "cap_pt3_x", "0.0", "cap_pt3_z")
    cap_pt4 = make_assoc_point(part, "cap_pt4_x", "0.0", "cap_pt4_z")

    cap_rect_curves = [
        assoc_line(part, cap_pt1, cap_pt2),
        assoc_line(part, cap_pt2, cap_pt3),
        assoc_line(part, cap_pt3, cap_pt4),
        assoc_line(part, cap_pt4, cap_pt1)
    ]

    feat_cap, cap = revolve_curves(part, cap_rect_curves, cap_pt1, vec(nx, 0.0, nz), "REVOLVE_CAP")
    print("[OK] Cap revolved")

    # Create a single rib cylinder on cap surface (as separate body)
    feat_rib, rib_body = create_cylinder_feature(
        part,
        cap_pt2,
        vec(nx, 0.0, nz),
        "0.8", # rib diameter
        "Cap_Height - Blend_Radius",
        "EXTRUDE_RIB",
        target=None
    )
    print("[OK] Single rib cylinder created")

    # Pattern the rib feature circularly (as separate bodies)
    feat_pattern = pattern_circular(part, feat_rib, cap_pt1, vec(nx, 0.0, nz), "24", "360.0 / 24", "PATTERN_RIBS")
    print("[OK] Cap grip ribs patterned")
    
    # Find all extra bodies to unite with Cap
    all_bodies = list(part.Bodies)
    rib_bodies = []
    for b in all_bodies:
        if b.JournalIdentifier != pouch.JournalIdentifier and b.JournalIdentifier != cap.JournalIdentifier:
            rib_bodies.append(b)
            
    print("Found {} rib bodies to unite with Cap".format(len(rib_bodies)))
    if rib_bodies:
        cap = unite(part, cap, rib_bodies, "UNITE_RIBS")
        print("[OK] Cap grip ribs united to Cap body")

    # Blend Cap Top Corner
    cap_top_center = (v(part, "cap_pt4_x"), 0.0, v(part, "cap_pt4_z"))
    cap_top_edge = find_cap_top_edge(cap, cap_top_center)
    if cap_top_edge is not None:
        blend_corners(part, cap, [(cap_top_edge, "Blend_Radius")])
        print("[OK] Cap top corner blended")
    else:
        print("[WARN] Could not find cap top edge for blend")

    set_name(cap, "Cap")

    # ---- FINALIZE ----
    try:
        num_bodies = len(list(part.Bodies or []))
        for idx, b in enumerate(list(part.Bodies or [])):
            print("Body #{}: Name='{}', Id='{}', Solid={}, Faces={}".format(
                idx, b.Name, b.JournalIdentifier, b.IsSolidBody, len(list(b.GetFaces() or []))
            ))
        part.ModelingViews.WorkView.Fit()
    except Exception as e:
        print("Finalize error: {}".format(e))

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    write_launch_files(path)
    print("Saved: {}".format(path))


if __name__ == "__main__":
    log = Path(__file__).resolve().parents[3] / "pouch_journal.log"
    try:
        log.write_text("Starting pouch journal\n", encoding="utf-8")
        main()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
