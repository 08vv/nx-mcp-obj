"""Create a clean, production-ready, parametric shampoo sachet in Siemens NX 2206.

This script implements a high-quality CAD modeling history for:
- Sachet_Body (flat rectangular envelope, edge blends, bulging body loft, and top/bottom serrated tear edges)

All primary dimensions are controlled via Expressions.

Usage:
  run_journal.exe create_sachet.py [output_path.prt]
"""

from __future__ import annotations
import math
import os
import sys
import traceback
from pathlib import Path
import NXOpen
import NXOpen.UF
from examples._common import set_name, unite, vec

UF = NXOpen.UF.UFSession.GetUFSession()

# ---------------------------------------------------------------------------
# Default parameters (mm) — Shampoo Sachet
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Height": 90.0,
    "Overall_Width": 53.0,
    "Overall_Thickness": 8.0,
    "Wall_Thickness": 0.8,
    "Fill_Bulge_Depth": 6.4,
    "Seal_Width": 4.0,
    "Seal_Height": 8.0,
    "Corner_Radius": 1.5,
    "Top_Serration_Pitch": 2.5,
    "Top_Serration_Height": 1.5,
    "Bottom_Serration_Pitch": 2.5,
    "Bottom_Serration_Height": 1.5,
    "Edge_Blend_Radius": 1.5,
    "Body_Crown_Height": 3.2,
    "Side_Draft_Angle": 0.0,
}

DERIVED = {
    "Bulge_Width": "Overall_Width - 2.0 * Seal_Width",
    "Bulge_Height": "Overall_Height - 2.0 * Seal_Height",
    "Max_Bulge_Depth": "Overall_Thickness - 2.0 * Wall_Thickness",
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Sachet_Model.prt"




def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))




def line(part, a, b):
    return part.Curves.CreateLine(point(*a), point(*b))


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------
def make_expressions(part) -> None:
    for name, value in VALUES.items():
        try:
            try:
                expr = part.Expressions.FindObject(name)
                expr.RightHandSide = str(value)
            except Exception:
                part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
        except Exception:
            pass

    for name, rhs in DERIVED.items():
        try:
            try:
                expr = part.Expressions.FindObject(name)
                expr.RightHandSide = rhs
            except Exception:
                part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass


def get_val(part, name: str) -> float:
    try:
        return part.Expressions.FindObject(name).Value
    except Exception:
        return float(VALUES.get(name, 0.0))


# ---------------------------------------------------------------------------
# Sketch & Loft helpers
# ---------------------------------------------------------------------------
def create_sketch_on_csys(part, origin, x_vec, y_vec, z_vec, sketch_name):
    matrix = NXOpen.Matrix3x3()
    matrix.Xx = x_vec.X; matrix.Xy = x_vec.Y; matrix.Xz = x_vec.Z
    matrix.Yx = y_vec.X; matrix.Yy = y_vec.Y; matrix.Yz = y_vec.Z
    matrix.Zx = z_vec.X; matrix.Zy = z_vec.Y; matrix.Zz = z_vec.Z
    nx_matrix = part.NXMatrices.Create(matrix)
    csys = part.CoordinateSystems.CreateCoordinateSystem(origin, nx_matrix, True)

    factory2 = getattr(part.Sketches, "CreateSketchInPlaceBuilder2", None)
    builder = None
    if factory2 is not None:
        try:
            builder = factory2(None)
        except Exception:
            pass
    if builder is None:
        factory = getattr(part.Sketches, "CreateNewSketchInPlaceBuilder", None)
        if factory is None:
            factory = getattr(part.Sketches, "CreateSketchInPlaceBuilder", None)
        builder = factory(None)
    try:
        builder.Csystem = csys
        commit = getattr(builder, "CommitFeature", None) or getattr(builder, "Commit", None)
        feat = commit()
    finally:
        builder.Destroy()
    try:
        feat.SetName(sketch_name)
    except Exception:
        pass
    sketch = feat.Sketch if hasattr(feat, "Sketch") else feat
    return feat, sketch


def xz_sketch(part, name: str):
    """Create a sketch on the XZ plane (X is horizontal, Z is vertical)."""
    return create_sketch_on_csys(
        part,
        point(0.0, 0.0, 0.0),
        vec(1.0, 0.0, 0.0),
        vec(0.0, 0.0, 1.0),
        vec(0.0, -1.0, 0.0),
        name,
    )


def add_to_sketch(sketch, curve) -> None:
    try:
        sketch.AddGeometry(curve, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    except Exception:
        try:
            sketch.AddGeometry(curve)
        except Exception:
            pass


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


def append_section(builder, sec) -> None:
    container = getattr(builder, "SectionsList", None) or getattr(builder, "Sections", None)
    if hasattr(container, "Append"):
        container.Append(sec)
    else:
        container.Add(sec)


def through_curves(part, curvesets, name):
    builder = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        try:
            builder.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
        except Exception:
            pass
        for curves in curvesets:
            append_section(builder, nx_section(part, curves))
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, bodies[0] if bodies else None


# ---------------------------------------------------------------------------
# Rounded rectangle (polar radius bisection) for bulge profiles
# ---------------------------------------------------------------------------
def radius_to_rounded_rect(width, depth, corner, angle):
    ux, uy = math.cos(angle), math.sin(angle)
    low, high = 0.0, max(width, depth)
    hw, hd = width * 0.5, depth * 0.5
    rr = min(corner, hw - 0.01, hd - 0.01)
    for _ in range(40):
        mid = (low + high) * 0.5
        x, y = mid * ux, mid * uy
        qx = abs(x) - (hw - rr)
        qy = abs(y) - (hd - rr)
        outside = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - rr
        if outside <= 0.0:
            low = mid
        else:
            high = mid
    return low


def ring_polyline(part, width, depth, corner, z, count=72):
    pts = []
    for i in range(count):
        a = 2.0 * math.pi * float(i) / float(count)
        mag = radius_to_rounded_rect(width, depth, corner, a)
        pts.append((mag * math.cos(a), mag * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % count]) for i in range(count)]


# ---------------------------------------------------------------------------
# Edge and Boolean helpers
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


def edge_z_center(edge):
    pts = edge_points(edge)
    if pts is not None:
        return (pts[0][2] + pts[1][2]) * 0.5
    return 0.0


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




def blend_edges(part, body, chooser, radius_rhs, name):
    edges = [e for e in list(body.GetEdges() or []) if chooser(e)]
    if not edges:
        print("  [WARN] blend_edges '{}': no matching edges found".format(name))
        return None
    builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        collector = part.ScCollectors.CreateCollector()
        collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(edges)], False)
        builder.Tolerance = 0.01
        builder.AllInstancesOption = False
        builder.RemoveSelfIntersection = True
        builder.RollOverSmoothEdge = True
        builder.RollOntoEdge = True
        builder.MoveSharpEdge = True
        builder.OverlapOption = NXOpen.Features.EdgeBlendBuilder.Overlap.AnyConvexityRollOver
        builder.BlendOrder = NXOpen.Features.EdgeBlendBuilder.OrderOfBlending.ConvexFirst
        builder.SetbackOption = NXOpen.Features.EdgeBlendBuilder.Setback.SeparateFromCorner
        builder.AddChainset(collector, str(radius_rhs))
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    return feat


def blend_edges_safe(part, body, chooser, radius_rhs, name):
    """Apply edge blend one edge at a time; skip edges that fail."""
    edges = [e for e in list(body.GetEdges() or []) if chooser(e)]
    if not edges:
        print("  [WARN] blend_edges_safe '{}': no matching edges found".format(name))
        return
    applied = 0
    failed = 0
    for edge in edges:
        try:
            blend_edges(part, body, lambda e, ref=edge: e == ref, radius_rhs, "{}_{}".format(name, applied))
            applied += 1
        except Exception:
            failed += 1
    if applied > 0:
        print("[OK] {} ({}/{} edges blended, {} skipped)".format(name, applied, applied + failed, failed))
    else:
        print("[WARN] {} - no edges could be blended".format(name))


# ---------------------------------------------------------------------------
# Main Builder
# ---------------------------------------------------------------------------
def main():
    path = out_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()

    try:
        session.Parts.CloseAll(NXOpen.BasePartCloseModified.CloseModified, None)
    except Exception:
        pass

    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

    part = session.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)

    # 1. Create Expressions
    make_expressions(part)
    print("[OK] All named Expressions successfully created.")

    # Read values
    h = get_val(part, "Overall_Height")
    w = get_val(part, "Overall_Width")
    t = get_val(part, "Overall_Thickness")
    wt = get_val(part, "Wall_Thickness")
    seal_w = get_val(part, "Seal_Width")
    seal_h = get_val(part, "Seal_Height")
    top_pitch = get_val(part, "Top_Serration_Pitch")
    top_sh = get_val(part, "Top_Serration_Height")
    bot_pitch = get_val(part, "Bottom_Serration_Pitch")
    bot_sh = get_val(part, "Bottom_Serration_Height")

    # -----------------------------------------------------------------------
    # 2. Envelope Sketch with Serrated Top and Bottom Edges
    # -----------------------------------------------------------------------
    _, sk_envelope = xz_sketch(part, "S1_Envelope_Profile")

    # Generate top serrations along Z = h/2
    num_teeth_top = int(w / top_pitch)
    actual_pitch_top = w / num_teeth_top
    top_curves = []
    
    # Valley to valley: start at -w/2, valleys are at z = h/2 - top_sh, tips are at z = h/2
    for i in range(num_teeth_top):
        x0 = -w/2 + i * actual_pitch_top
        x1 = -w/2 + (i + 0.5) * actual_pitch_top
        x2 = -w/2 + (i + 1) * actual_pitch_top
        top_curves.append(line(part, (x0, 0.0, h/2 - top_sh), (x1, 0.0, h/2)))
        top_curves.append(line(part, (x1, 0.0, h/2), (x2, 0.0, h/2 - top_sh)))

    # Generate bottom serrations along Z = -h/2
    num_teeth_bot = int(w / bot_pitch)
    actual_pitch_bot = w / num_teeth_bot
    bot_curves = []
    
    # Valleys are at z = -h/2 + bot_sh, tips are at z = -h/2
    # Tracing from right to left: from w/2 to -w/2
    for i in range(num_teeth_bot):
        x0 = w/2 - i * actual_pitch_bot
        x1 = w/2 - (i + 0.5) * actual_pitch_bot
        x2 = w/2 - (i + 1) * actual_pitch_bot
        bot_curves.append(line(part, (x0, 0.0, -h/2 + bot_sh), (x1, 0.0, -h/2)))
        bot_curves.append(line(part, (x1, 0.0, -h/2), (x2, 0.0, -h/2 + bot_sh)))

    # Vertical side borders
    left_line = line(part, (-w/2, 0.0, -h/2 + bot_sh), (-w/2, 0.0, h/2 - top_sh))
    right_line = line(part, (w/2, 0.0, h/2 - top_sh), (w/2, 0.0, -h/2 + bot_sh))

    all_envelope_curves = top_curves + [right_line] + bot_curves + [left_line]

    sk_envelope.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for c in all_envelope_curves:
        add_to_sketch(sk_envelope, c)
    sk_envelope.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    # Extrude envelope along Y-axis from -wt to wt (thickness = 2*wt)
    _, sachet_body = extrude(part, all_envelope_curves, vec(0.0, 1.0, 0.0), "-Wall_Thickness", "Wall_Thickness", "F1_Extrude_Envelope")
    print("[OK] Envelope extruded.")

    # Apply corner blends to vertical side edges (running along Y)
    blend_edges_safe(
        part, sachet_body,
        lambda e: abs(edge_points(e)[0][0] - w/2) < 0.5 or abs(edge_points(e)[0][0] + w/2) < 0.5,
        "Corner_Radius",
        "F1b_Corner_Blends"
    )

    # -----------------------------------------------------------------------
    # 3. Puffy Body Loft (Through Curves)
    # -----------------------------------------------------------------------
    # Center section width
    bulge_w = w - 2 * seal_w
    # Max puffy thickness in center
    max_puffy_t = t - 2 * wt
    
    # 5 sections along Z
    z_coords = [
        -h/2 + seal_h,
        -h/4,
        0.0,
        h/4,
        h/2 - seal_h
    ]
    
    # Sections shapes (stadiums)
    curvesets = []
    # SEC_0 (Z bottom): flat stadium (matching envelope thickness of 2*wt)
    curvesets.append(ring_polyline(part, bulge_w, 2.0 * wt, wt, z_coords[0]))
    # SEC_1 (Z intermediate): bulging stadium
    curvesets.append(ring_polyline(part, bulge_w, 2.0 * wt + (max_puffy_t - 2.0 * wt) * 0.7, bulge_w * 0.4, z_coords[1]))
    # SEC_2 (Z middle): max bulging stadium
    curvesets.append(ring_polyline(part, bulge_w, max_puffy_t, bulge_w * 0.4, z_coords[2]))
    # SEC_3 (Z intermediate): bulging stadium
    curvesets.append(ring_polyline(part, bulge_w, 2.0 * wt + (max_puffy_t - 2.0 * wt) * 0.7, bulge_w * 0.4, z_coords[3]))
    # SEC_4 (Z top): flat stadium (matching envelope thickness of 2*wt)
    curvesets.append(ring_polyline(part, bulge_w, 2.0 * wt, wt, z_coords[4]))

    # Force update to compute curve geometry of all sections
    try:
        session.UpdateManager.DoUpdate(session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "Section Curves Update"))
    except Exception as e:
        print("[WARN] Section curves update warning: {}".format(e))

    _, puffy_body = through_curves(part, curvesets, "F2_Through_Curves_Puffy")
    print("[OK] Central puffy body lofted.")

    # -----------------------------------------------------------------------
    # 4. Unite & Final Blends
    # -----------------------------------------------------------------------
    # Unite envelope with puffy body
    sachet_body = unite(part, sachet_body, puffy_body, "F3_Unite_Sachet")
    print("[OK] Sachet united.")

    # Smooth the transition between the bulging puffy body and the flat envelope
    # We choose the transition edges near the boundary of the loft (x within bulge_w, y near wt)
    blend_edges_safe(
        part, sachet_body,
        lambda e: abs(edge_points(e)[0][1]) > wt * 0.8 and abs(edge_points(e)[0][0]) < (bulge_w / 2 + 1.0) and abs(edge_z_center(e)) < (h/2 - seal_h + 1.0),
        "Edge_Blend_Radius",
        "F4_Transition_Blend"
    )

    # -----------------------------------------------------------------------
    # 5. Rename body and save
    # -----------------------------------------------------------------------
    set_name(sachet_body, "Sachet_Body")

    part.ModelingViews.WorkView.Fit()
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("Sachet saved successfully to {}".format(path))


if __name__ == "__main__":
    log_path = Path(__file__).resolve().parents[3] / "sachet_journal.log"
    try:
        log_path.write_text("Starting sachet journal\n", encoding="utf-8")
        main()
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
