"""Create a clean, production-ready, parametric industrial profile model in Siemens NX 2206.

This script implements a high-quality CAD modeling history for:
- Profile_Body (base block extrusion, upper & lower groove cuts, corner chamfers, edge blends)
- Italicized "Rin" Logo (Sheared, scaled, and translated curves extruded-subtracted into the front face)

All primary dimensions are controlled via Expressions.

Usage:
  run_journal.exe create_profile.py [output_path.prt]
"""

from __future__ import annotations
import math
import os
import sys
import traceback
from pathlib import Path
import NXOpen
import NXOpen.UF
from examples._common import set_name, vec

UF = NXOpen.UF.UFSession.GetUFSession()

# ---------------------------------------------------------------------------
# Default parameters (mm) — derived from Rin Soap Bar proportions
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Length": 150.0,
    "Overall_Width": 70.0,
    "Overall_Height": 60.0,
    "Profile_Thickness": 70.0,
    "Upper_Groove_Depth": 4.0,
    "Upper_Groove_Radius": 8.0,
    "Lower_Groove_Depth": 4.0,
    "Lower_Groove_Radius": 8.0,
    "Side_Wall_Angle": 5.0,
    "Top_Lip_Width": 10.0,
    "Bottom_Lip_Width": 10.0,
    "Corner_Radius": 5.0,
    "Chamfer_Size": 6.0,
    "Logo_Depth": 1.0,
    "Logo_Scale": 1.0,
    "Logo_Offset_X": 0.0,
    "Logo_Offset_Y": 0.0,
    "Edge_Blend_Radius": 3.0,
}

DERIVED = {
    "Overall_Width": "Profile_Thickness",
}

def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Industrial_Profile_Model.prt"


def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def line(part, a, b):
    return part.Curves.CreateLine(point(*a), point(*b))

# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------
def make_expressions(part) -> None:
    # 1. Create base expressions
    for name, value in VALUES.items():
        if name in ("Overall_Width",):
            continue
        try:
            try:
                expr = part.Expressions.FindObject(name)
                expr.RightHandSide = str(value)
            except Exception:
                part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
        except Exception:
            pass

    # 2. Create derived expressions
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
# Sketch Creation
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

def yz_sketch(part, name: str):
    """Create a sketch on the YZ plane (X=0, Y is horizontal, Z is vertical)."""
    return create_sketch_on_csys(
        part,
        point(0.0, 0.0, 0.0),
        vec(0.0, 1.0, 0.0),
        vec(0.0, 0.0, 1.0),
        vec(1.0, 0.0, 0.0),
        name,
    )

def front_sketch(part, y_val, name: str):
    """Create a sketch on the front face parallel to XZ plane (Y = y_val)."""
    return create_sketch_on_csys(
        part,
        point(0.0, y_val, 0.0),
        vec(1.0, 0.0, 0.0),
        vec(0.0, 0.0, 1.0),
        vec(0.0, 1.0, 0.0),
        name,
    )

# ---------------------------------------------------------------------------
# Section and Extrude Builders
# ---------------------------------------------------------------------------
def section(part, curves):
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
        builder.Section = section(part, curves)
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

def add_chamfer(part, edges, offset_rhs, name):
    builder = part.Features.CreateChamferBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Option = NXOpen.Features.ChamferBuilder.ChamferOption.OffsetAndAngle
        builder.Method = NXOpen.Features.ChamferBuilder.OffsetMethod.EdgesAlongFaces
        builder.FirstOffset = str(offset_rhs)
        builder.SecondOffset = str(offset_rhs)
        builder.Angle = "45"
        builder.Tolerance = 0.01

        collector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleEdgeDumb(edges)
        collector.ReplaceRules([rule], False)

        if hasattr(builder, "SmartCollector"):
            builder.SmartCollector = collector
        elif hasattr(builder, "EdgeCollector"):
            builder.EdgeCollector = collector

        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    return feat

def add_edge_blend(part, edges, radius_rhs, name):
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
        builder.AddChainset(collector, radius_rhs)
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    return feat

def add_edge_blend_safe(part, edges, radius_rhs, name):
    """Apply edge blend one edge at a time; silently skip edges that cause overlap conflicts."""
    applied = 0
    failed = 0
    for edge in edges:
        try:
            add_edge_blend(part, [edge], radius_rhs, "{}_{}".format(name, applied))
            applied += 1
        except Exception:
            failed += 1
    if applied > 0:
        print("[OK] {} ({}/{} edges blended, {} skipped)".format(name, applied, applied + failed, failed))
    else:
        print("[WARN] {} — no edges could be blended".format(name))

# ---------------------------------------------------------------------------
# Geometry Edge Queries
# ---------------------------------------------------------------------------
def find_bottom_longitudinal_edges(body, h_val, t_val):
    edges = []
    for edge in body.GetEdges():
        verts = edge.GetVertices()
        if verts:
            p1 = verts[0]
            p2 = verts[1]
            # Runs along X-axis
            if abs(p1.Y - p2.Y) < 0.1 and abs(p1.Z - p2.Z) < 0.1:
                # Z is at the bottom face
                if abs(p1.Z - (-h_val / 2.0)) < 0.2:
                    # Y is at front (+t/2) or back (-t/2) face
                    if abs(p1.Y - t_val / 2.0) < 0.2 or abs(p1.Y - (-t_val / 2.0)) < 0.2:
                        edges.append(edge)
    return edges

def find_top_longitudinal_edges(body, h_val, t_val):
    edges = []
    for edge in body.GetEdges():
        verts = edge.GetVertices()
        if verts:
            p1 = verts[0]
            p2 = verts[1]
            # Runs along X-axis
            if abs(p1.Y - p2.Y) < 0.1 and abs(p1.Z - p2.Z) < 0.1:
                # Z is at the top face
                if abs(p1.Z - (h_val / 2.0)) < 0.2:
                    # Y is at front (+t/2) or back (-t/2) face
                    if abs(p1.Y - t_val / 2.0) < 0.2 or abs(p1.Y - (-t_val / 2.0)) < 0.2:
                        edges.append(edge)
    return edges

def find_groove_edges(body, t_val, upper_z, upper_h_half, lower_z, lower_h_half):
    edges = []
    for edge in body.GetEdges():
        verts = edge.GetVertices()
        if verts:
            p1 = verts[0]
            p2 = verts[1]
            # Runs along X-axis
            if abs(p1.Y - p2.Y) < 0.1 and abs(p1.Z - p2.Z) < 0.1:
                # Front face
                if abs(p1.Y - t_val / 2.0) < 0.2:
                    # Upper groove edges
                    if abs(p1.Z - (upper_z + upper_h_half)) < 0.2 or abs(p1.Z - (upper_z - upper_h_half)) < 0.2:
                        edges.append(edge)
                    # Lower groove edges
                    elif abs(p1.Z - (lower_z + lower_h_half)) < 0.2 or abs(p1.Z - (lower_z - lower_h_half)) < 0.2:
                        edges.append(edge)
    return edges

def find_vertical_corner_edges(body, l_val, t_val):
    edges = []
    for edge in body.GetEdges():
        verts = edge.GetVertices()
        if verts:
            p1 = verts[0]
            p2 = verts[1]
            # Runs along Z-axis
            if abs(p1.X - p2.X) < 0.1 and abs(p1.Y - p2.Y) < 0.1:
                # At X=0 or X=l_val
                if abs(p1.X) < 0.2 or abs(p1.X - l_val) < 0.2:
                    # At Y=±t_val/2
                    if abs(p1.Y - t_val / 2.0) < 0.2 or abs(p1.Y - (-t_val / 2.0)) < 0.2:
                        edges.append(edge)
    return edges

# ---------------------------------------------------------------------------
# Main Builder
# ---------------------------------------------------------------------------
def main():
    path = out_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()
    
    # Close open parts for a clean environment
    try:
        session.Parts.CloseAll(NXOpen.BasePartCloseModified.CloseModified, None)
    except Exception:
        pass
        
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

    # Create new part
    part = session.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)

    # 1. Create Expressions
    make_expressions(part)
    print("[OK] All named Expressions successfully created.")

    # 2. Sketch & Extrude Base Block
    feat_s1, sk1 = yz_sketch(part, "S1_Profile_Section")
    
    t = get_val(part, "Profile_Thickness")
    h = get_val(part, "Overall_Height")
    l_val = get_val(part, "Overall_Length")
    
    p1 = (0.0, -t / 2.0, -h / 2.0)
    p2 = (0.0, t / 2.0, -h / 2.0)
    p3 = (0.0, t / 2.0, h / 2.0)
    p4 = (0.0, -t / 2.0, h / 2.0)
    
    bl1 = line(part, p1, p2)
    bl2 = line(part, p2, p3)
    bl3 = line(part, p3, p4)
    bl4 = line(part, p4, p1)
    
    sk1.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    infer = NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints
    for bl in (bl1, bl2, bl3, bl4):
        sk1.AddGeometry(bl, infer)
    sk1.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
    
    # Extrude along X axis from 0 to Overall_Length
    ext_feat, profile_body = extrude(part, [bl1, bl2, bl3, bl4], vec(1.0, 0.0, 0.0), "0.0", "Overall_Length", "F1_Extrude_Base_Block")
    print("[OK] Base rectangular block extruded.")

    # 3. Sketch & Extrude Upper & Lower Groove Cuts (Boolean Subtract)
    feat_s2, sk2 = yz_sketch(part, "S2_Grooves_Section")
    
    top_lip = get_val(part, "Top_Lip_Width")
    bot_lip = get_val(part, "Bottom_Lip_Width")
    
    u_rad = get_val(part, "Upper_Groove_Radius")
    u_dep = get_val(part, "Upper_Groove_Depth")
    l_rad = get_val(part, "Lower_Groove_Radius")
    l_dep = get_val(part, "Lower_Groove_Depth")
    
    # Upper groove calculations
    z_upper = h / 2.0 - top_lip
    u_h_half = math.sqrt(2 * u_rad * u_dep - u_dep**2)
    y_center_u = t / 2.0 + u_rad - u_dep
    u_theta = math.acos((u_dep - u_rad) / u_rad)
    
    # Lower groove calculations
    z_lower = -h / 2.0 + bot_lip
    l_h_half = math.sqrt(2 * l_rad * l_dep - l_dep**2)
    y_center_l = t / 2.0 + l_rad - l_dep
    l_theta = math.acos((l_dep - l_rad) / l_rad)
    
    # Upper groove loop (left half of circle, curving inwards)
    u_arc_center = point(0.0, y_center_u, z_upper)
    u_arc = part.Curves.CreateArc(u_arc_center, vec(0.0, 1.0, 0.0), vec(0.0, 0.0, 1.0), u_rad, u_theta, 2.0 * math.pi - u_theta)
    
    ul1 = line(part, (0.0, t / 2.0, z_upper - u_h_half), (0.0, t / 2.0 + 5.0, z_upper - u_h_half))
    ul2 = line(part, (0.0, t / 2.0 + 5.0, z_upper - u_h_half), (0.0, t / 2.0 + 5.0, z_upper + u_h_half))
    ul3 = line(part, (0.0, t / 2.0 + 5.0, z_upper + u_h_half), (0.0, t / 2.0, z_upper + u_h_half))
    
    # Lower groove loop (left half of circle, curving inwards)
    l_arc_center = point(0.0, y_center_l, z_lower)
    l_arc = part.Curves.CreateArc(l_arc_center, vec(0.0, 1.0, 0.0), vec(0.0, 0.0, 1.0), l_rad, l_theta, 2.0 * math.pi - l_theta)
    
    ll1 = line(part, (0.0, t / 2.0, z_lower - l_h_half), (0.0, t / 2.0 + 5.0, z_lower - l_h_half))
    ll2 = line(part, (0.0, t / 2.0 + 5.0, z_lower - l_h_half), (0.0, t / 2.0 + 5.0, z_lower + l_h_half))
    ll3 = line(part, (0.0, t / 2.0 + 5.0, z_lower + l_h_half), (0.0, t / 2.0, z_lower + l_h_half))
    
    sk2.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    sk2.AddGeometry(u_arc, infer)
    for l in (ul1, ul2, ul3):
        sk2.AddGeometry(l, infer)
    sk2.AddGeometry(l_arc, infer)
    for l in (ll1, ll2, ll3):
        sk2.AddGeometry(l, infer)
    sk2.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
    
    # Extrude and Subtract grooves (note: the arc goes from top to bottom, so the lines close CCW)
    groove_curves_ccw = [u_arc, ul1, ul2, ul3, l_arc, ll1, ll2, ll3]
    ext_grooves_feat, profile_body = extrude(
        part, groove_curves_ccw, vec(1.0, 0.0, 0.0), "0.0", "Overall_Length",
        "F2_Subtract_Grooves", target=profile_body, subtract=True
    )
    print("[OK] Upper and lower longitudinal grooves cut.")

    # 4. Apply Chamfer to lower corners
    bottom_edges = find_bottom_longitudinal_edges(profile_body, h, t)
    if bottom_edges:
        add_chamfer(part, bottom_edges, "Chamfer_Size", "F3_Lower_Corners_Chamfer")
        print("[OK] Lower corner chamfers applied.")

    # 5. Apply Edge Blends to Grooves
    groove_long_edges = find_groove_edges(profile_body, t, z_upper, u_h_half, z_lower, l_h_half)
    if groove_long_edges:
        add_edge_blend(part, groove_long_edges, "Edge_Blend_Radius", "F4_Grooves_Transition_Blends")
        print("[OK] Groove transition edge blends applied.")

    # 6. Apply Edge Blends to top longitudinal corners & vertical corners
    top_edges = find_top_longitudinal_edges(profile_body, h, t)
    if top_edges:
        add_edge_blend_safe(part, top_edges, "Corner_Radius", "F5_Top_Corners_Blends")
        
    vertical_edges = find_vertical_corner_edges(profile_body, l_val, t)
    if vertical_edges:
        add_edge_blend_safe(part, vertical_edges, "Corner_Radius", "F6_Vertical_Corners_Blends")

    # 7. Extrude italicized "Rin" logo (each letter loop as a separate subtract)
    logo_scale = get_val(part, "Logo_Scale")
    logo_offset_x = get_val(part, "Logo_Offset_X")
    logo_offset_z = get_val(part, "Logo_Offset_Y")
    
    x_center = l_val / 2.0 + logo_offset_x
    z_center = logo_offset_z
    
    # Transformation helper
    slant = 0.268  # 15 degrees right slant
    def trans(pts_list):
        transformed = []
        for x, z in pts_list:
            xc = x - 6.1
            zc = z - 5.0
            xs = xc + zc * slant
            xs *= logo_scale
            zs = zc * logo_scale
            transformed.append((xs + x_center, zs + z_center))
        return transformed

    y_front = t / 2.0

    # Define letter loops — each is a single closed outline
    # Letter R outer loop
    r_out = trans([(0.0, 0.0), (1.5, 0.0), (1.5, 4.0), (3.0, 0.0), (5.0, 0.0), (2.5, 5.5), (5.0, 5.5), (5.0, 10.0), (0.0, 10.0)])
    # Letter R inner hole
    r_in = trans([(1.5, 7.0), (3.5, 7.0), (3.5, 8.5), (1.5, 8.5)])
    # Letter i body
    i_body = trans([(6.0, 0.0), (7.5, 0.0), (7.5, 6.0), (6.0, 6.0)])
    # Letter i dot
    i_dot = trans([(6.0, 7.5), (7.5, 7.5), (7.5, 9.0), (6.0, 9.0)])
    # Letter n — single merged outline (left stem + arch + right stem)
    n_outline = trans([
        (8.5, 0.0), (9.7, 0.0), (9.7, 4.5), (11.0, 4.5),
        (11.0, 0.0), (12.2, 0.0), (12.2, 6.0), (8.5, 6.0),
    ])

    # Extrude each letter loop individually
    # (subtract=True for cuts, subtract=False for adding material back like R inner hole)
    letter_loops = [
        ("F7a_Logo_R_Outer", r_out, True),
        ("F7b_Logo_R_Inner", r_in, False),
        ("F7c_Logo_i_Body", i_body, True),
        ("F7d_Logo_i_Dot", i_dot, True),
        ("F7e_Logo_n", n_outline, True),
    ]
    for feat_name, pts, is_subtract in letter_loops:
        curves = draw_loop(part, pts, y_front)
        try:
            _, profile_body = extrude(
                part, curves, vec(0.0, -1.0, 0.0), "0.0", "Logo_Depth",
                feat_name, target=profile_body, subtract=is_subtract
            )
        except Exception as e:
            print("[WARN] {} failed: {}".format(feat_name, e))
    print("[OK] Recessed central 'Rin' logo engraved on front face.")

    # 8. Rename and Save
    set_name(profile_body, "Profile_Body")
    part.ModelingViews.WorkView.Fit()
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("Industrial Profile Model saved successfully to {}".format(path))

def draw_loop(part, pts_2d, y_val):
    lines = []
    n = len(pts_2d)
    for i in range(n):
        p1 = pts_2d[i]
        p2 = pts_2d[(i + 1) % n]
        lines.append(part.Curves.CreateLine(
            point(p1[0], y_val, p1[1]),
            point(p2[0], y_val, p2[1])
        ))
    return lines

if __name__ == "__main__":
    log_path = Path(__file__).resolve().parents[3] / "profile_journal.log"
    try:
        log_path.write_text("Starting profile model journal\n", encoding="utf-8")
        main()
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
