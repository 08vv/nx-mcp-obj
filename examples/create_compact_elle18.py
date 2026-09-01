"""Create a clean, production-ready, parametric cosmetic compact model in Siemens NX 2206.

All primary dimensions are controlled via Expressions.

Usage:
  run_journal.exe create_compact_elle18.py [output_path.prt]
"""

from __future__ import annotations
import math
import os
import sys
import traceback
from pathlib import Path
import NXOpen
from examples._common import set_name, vec

# ---------------------------------------------------------------------------
# Default parameters (mm) — Cosmetic Compact
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Length": 82.0,
    "Overall_Width": 74.0,
    "Overall_Height": 22.0,
    "Corner_Radius": 12.0,
    "Lid_Height": 12.0,
    "Base_Height": 10.0,
    "Lid_Crown_Height": 2.0,
    "Side_Draft_Angle": 2.0,
    "Split_Gap": 0.4,
    "Wall_Thickness": 2.0,
    "Front_Recess_Width": 16.0,
    "Front_Recess_Height": 6.0,
    "Front_Recess_Depth": 4.0,
    "Latch_Button_Diameter": 8.0,
    "Edge_Blend_Radius": 4.0,
    "Bottom_Fillet_Radius": 3.0,
}

def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Compact_Model_Elle18.prt"


def commit_builder(builder):
    commit = getattr(builder, "CommitFeature", None) or getattr(builder, "Commit", None)
    return commit()

def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))

def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))

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

    # Sphere parameters for dome
    derived = {
        "Sphere_Radius": "((Overall_Length / 2.0 + 20.0)^2 + Lid_Crown_Height^2) / (2.0 * Lid_Crown_Height)",
        "Sphere_Diameter": "2.0 * Sphere_Radius",
        "Sphere_Center_Z": "Overall_Height - Sphere_Radius",
    }
    for name, rhs in derived.items():
        try:
            try:
                expr = part.Expressions.FindObject(name)
                expr.RightHandSide = rhs
            except Exception:
                part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Cushion math solver
# ---------------------------------------------------------------------------
def solve_cushion(W, L, Rc, Rs):
    B = W/2.0 - Rs
    A = L/2.0 - Rs
    d = Rs - Rc
    
    k = (A**2 - B**2) / 2.0
    aq = 1.0 + (B / A)**2
    bq = 2.0 * B * (k / (A**2) - 1.0)
    cq = (k / A)**2 + B**2 - d**2
    
    disc = bq**2 - 4.0 * aq * cq
    if disc < 0:
        raise ValueError("No solution for cushion shape parameters")
    yc = (-bq + math.sqrt(disc)) / (2.0 * aq)
    xc = (B * yc + k) / A
    
    v_top_x = xc
    v_top_y = yc - B
    v_top_len = math.hypot(v_top_x, v_top_y)
    t_top_x = xc * (Rs / v_top_len)
    t_top_y = B + (yc - B) * (Rs / v_top_len)
    
    v_right_x = xc - A
    v_right_y = yc
    v_right_len = math.hypot(v_right_x, v_right_y)
    t_right_x = A + (xc - A) * (Rs / v_right_len)
    t_right_y = yc * (Rs / v_right_len)
    
    return xc, yc, t_top_x, t_top_y, t_right_x, t_right_y

# ---------------------------------------------------------------------------
# Helper: Create cushion curves
# ---------------------------------------------------------------------------
def create_cushion_curves(part, W, L, Rc, Rs, z_val, angle_deg=0.0):
    xc, yc, tx_top, ty_top, tx_right, ty_right = solve_cushion(W, L, Rc, Rs)
    
    c_top = (0.0, W/2.0 - Rs)
    c_tl = (-xc, yc)
    c_left = (-L/2.0 + Rs, 0.0)
    c_bl = (-xc, -yc)
    c_bottom = (0.0, -W/2.0 + Rs)
    c_br = (xc, -yc)
    c_right = (L/2.0 - Rs, 0.0)
    c_tr = (xc, yc)
    
    def rot_pt(x, y):
        if angle_deg == 0.0:
            return x, y
        rad = math.radians(angle_deg)
        c = math.cos(rad)
        s = math.sin(rad)
        return x * c - y * s, x * s + y * c
        
    c_top_rot = rot_pt(*c_top)
    c_tl_rot = rot_pt(*c_tl)
    c_left_rot = rot_pt(*c_left)
    c_bl_rot = rot_pt(*c_bl)
    c_bottom_rot = rot_pt(*c_bottom)
    c_br_rot = rot_pt(*c_br)
    c_right_rot = rot_pt(*c_right)
    c_tr_rot = rot_pt(*c_tr)
    
    offset_rad = math.radians(angle_deg)
    x_axis = vec(math.cos(offset_rad), math.sin(offset_rad), 0.0)
    y_axis = vec(-math.sin(offset_rad), math.cos(offset_rad), 0.0)
    
    curves = []
    a1_s = math.atan2(ty_top - (W/2.0 - Rs), tx_top)
    a1_e = math.atan2(ty_top - (W/2.0 - Rs), -tx_top)
    curves.append(part.Curves.CreateArc(point(c_top_rot[0], c_top_rot[1], z_val), x_axis, y_axis, Rs, a1_s, a1_e))
    
    a2_s = math.atan2(ty_top - yc, -tx_top + xc)
    a2_e = math.atan2(ty_right - yc, -tx_right + xc)
    curves.append(part.Curves.CreateArc(point(c_tl_rot[0], c_tl_rot[1], z_val), x_axis, y_axis, Rc, a2_s, a2_e))
    
    a3_s = math.atan2(ty_right, -tx_right - (-L/2.0 + Rs))
    a3_e = math.atan2(-ty_right, -tx_right - (-L/2.0 + Rs))
    curves.append(part.Curves.CreateArc(point(c_left_rot[0], c_left_rot[1], z_val), x_axis, y_axis, Rs, a3_s, a3_e))
    
    a4_s = math.atan2(-ty_right + yc, -tx_right + xc)
    a4_e = math.atan2(-ty_top + yc, -tx_top + xc)
    curves.append(part.Curves.CreateArc(point(c_bl_rot[0], c_bl_rot[1], z_val), x_axis, y_axis, Rc, a4_s, a4_e))
    
    a5_s = math.atan2(-ty_top - (-W/2.0 + Rs), -tx_top)
    a5_e = math.atan2(-ty_top - (-W/2.0 + Rs), tx_top)
    curves.append(part.Curves.CreateArc(point(c_bottom_rot[0], c_bottom_rot[1], z_val), x_axis, y_axis, Rs, a5_s, a5_e))
    
    a6_s = math.atan2(-ty_top + yc, tx_top - xc)
    a6_e = math.atan2(-ty_right + yc, tx_right - xc)
    curves.append(part.Curves.CreateArc(point(c_br_rot[0], c_br_rot[1], z_val), x_axis, y_axis, Rc, a6_s, a6_e))
    
    a7_s = math.atan2(-ty_right, tx_right - (L/2.0 - Rs))
    a7_e = math.atan2(ty_right, tx_right - (L/2.0 - Rs))
    curves.append(part.Curves.CreateArc(point(c_right_rot[0], c_right_rot[1], z_val), x_axis, y_axis, Rs, a7_s, a7_e))
    
    a8_s = math.atan2(ty_right - yc, tx_right - xc)
    a8_e = math.atan2(ty_top - yc, tx_top - xc)
    curves.append(part.Curves.CreateArc(point(c_tr_rot[0], c_tr_rot[1], z_val), x_axis, y_axis, Rc, a8_s, a8_e))
    
    return curves

# ---------------------------------------------------------------------------
# Helper: Create sketch feature on specific Z plane
# ---------------------------------------------------------------------------
def create_sketch_with_curves(part, name, curves, z_val):
    factory2 = getattr(part.Sketches, "CreateSketchInPlaceBuilder2", None)
    builder = factory2(None)
    matrix = NXOpen.Matrix3x3()
    matrix.Xx = 1.0; matrix.Xy = 0.0; matrix.Xz = 0.0
    matrix.Yx = 0.0; matrix.Yy = 1.0; matrix.Yz = 0.0
    matrix.Zx = 0.0; matrix.Zy = 0.0; matrix.Zz = 1.0
    builder.Csystem = part.CoordinateSystems.CreateCoordinateSystem(point(0.0, 0.0, z_val), part.NXMatrices.Create(matrix), True)
    sketch_feat = commit_builder(builder)
    builder.Destroy()
    sketch = sketch_feat.Sketch if hasattr(sketch_feat, "Sketch") else sketch_feat
    set_name(sketch_feat, name)
    
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for c in curves:
        sketch.AddGeometry(c, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
    return list(sketch.GetAllGeometry())

# ---------------------------------------------------------------------------
# Helper: Run solid boolean operation
# ---------------------------------------------------------------------------
def run_boolean(part, op_type, target_body, tool_body):
    builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = op_type
        builder.Targets.Add(target_body)
        collector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([tool_body], True)
        collector.ReplaceRules([rule], False)
        if hasattr(builder, "ToolBodyCollector"):
            builder.ToolBodyCollector = collector
        elif hasattr(builder, "BooleanTool"):
            for attr in ("BodyCollector", "ToolBodyCollector"):
                if hasattr(builder.BooleanTool, attr):
                    setattr(builder.BooleanTool, attr, collector)
                    break
        feat = builder.CommitFeature()
        return feat.GetBodies()[0]
    finally:
        builder.Destroy()

# ---------------------------------------------------------------------------
# Helper: Create sphere tool body
# ---------------------------------------------------------------------------
def create_sphere_body(part, diameter_rhs, sz, name):
    sphere_center_pt = part.Points.CreatePoint(point(0.0, 0.0, sz))
    sphere_builder = part.Features.CreateSphereBuilder(NXOpen.Features.Sphere.Null)
    try:
        sphere_builder.Type = NXOpen.Features.SphereBuilder.Types.CenterPointAndDiameter
        sphere_builder.CenterPoint = sphere_center_pt
        sphere_builder.Diameter.RightHandSide = diameter_rhs
        sphere_builder.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        sphere_feat = sphere_builder.CommitFeature()
        body = sphere_feat.GetBodies()[0]
        set_name(sphere_feat, name)
        return body
    finally:
        sphere_builder.Destroy()

# ---------------------------------------------------------------------------
# Main Builder
# ---------------------------------------------------------------------------
def main():
    path = out_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()
    
    # Close any open parts to ensure clean slate
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
    
    W = part.Expressions.FindObject("Overall_Width").Value
    L = part.Expressions.FindObject("Overall_Length").Value
    Rc_lid = part.Expressions.FindObject("Corner_Radius").Value
    Rc_base = Rc_lid - 1.0 # Base Corner Radius = 11 mm
    Rs = 5.0 * W  # Side radius of curvature

    # ---------------------------------------------------------------------------
    # 2. Build Lower Base (Segment 2)
    # ---------------------------------------------------------------------------
    base_curves = create_cushion_curves(part, W, L, Rc_base, Rs, 10.0)
    base_sketch_curves = create_sketch_with_curves(part, "S1_Base_Footprint", base_curves, 10.0)

    ext_base_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in base_sketch_curves]
        sec.AddToSection(rules, base_sketch_curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, point(0.0, 0.0, 10.0), NXOpen.Section.Mode.Create, False)
        ext_base_builder.Section = sec
        ext_base_builder.Direction = part.Directions.CreateDirection(point(0.0, 0.0, 10.0), vec(0.0, 0.0, -1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        ext_base_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_base_builder.Limits.EndExtend.Value.RightHandSide = "Base_Height"
        
        # Base side draft is 1.5° (drafted from start, so Z=10 is maximum size, tapers inward to Z=0)
        draft = ext_base_builder.Draft
        draft.DraftOption = NXOpen.GeometricUtilities.SimpleDraftSimpleDraftType.SimpleFromStart
        draft.FrontDraftAngle.RightHandSide = "Side_Draft_Angle - 0.5"
        
        ext_base_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        ext_feat = ext_base_builder.CommitFeature()
        base_body = ext_feat.GetBodies()[0]
        set_name(ext_feat, "F1_Extrude_Base")
        print("[OK] Base block extruded.")
    finally:
        ext_base_builder.Destroy()

    # Apply bottom outer perimeter edge blend
    bottom_edges = []
    for edge in list(base_body.GetEdges() or []):
        verts = edge.GetVertices()
        if verts:
            z1 = verts[0].Z
            z2 = verts[1].Z
            if abs(z1) < 0.05 and abs(z2) < 0.05:
                bottom_edges.append(edge)

    if bottom_edges:
        blend_builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = part.ScCollectors.CreateCollector()
            collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(bottom_edges)], False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "Bottom_Fillet_Radius")
            feat = blend_builder.CommitFeature()
            set_name(feat, "F2_Bottom_Fillet")
            base_body = feat.GetBodies()[0]
            print("[OK] Bottom fillet applied.")
        finally:
            blend_builder.Destroy()

    # ---------------------------------------------------------------------------
    # 3. Build Upper Lid (Segment 1)
    # ---------------------------------------------------------------------------
    # Lid footprint at parting line plane Z = Base_Height + Split_Gap = 10.4
    lid_curves = create_cushion_curves(part, W, L, Rc_lid, Rs, 10.4)
    lid_sketch_curves = create_sketch_with_curves(part, "S2_Lid_Footprint", lid_curves, 10.4)

    ext_lid_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in lid_sketch_curves]
        sec.AddToSection(rules, lid_sketch_curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, point(0.0, 0.0, 10.4), NXOpen.Section.Mode.Create, False)
        ext_lid_builder.Section = sec
        ext_lid_builder.Direction = part.Directions.CreateDirection(point(0.0, 0.0, 10.4), vec(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        ext_lid_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_lid_builder.Limits.EndExtend.Value.RightHandSide = "Overall_Height - Base_Height - Split_Gap"
        
        # Lid side draft is 2.0° (drafted from start, so Z=10.4 is maximum size, tapers inward to top)
        draft = ext_lid_builder.Draft
        draft.DraftOption = NXOpen.GeometricUtilities.SimpleDraftSimpleDraftType.SimpleFromStart
        draft.FrontDraftAngle.RightHandSide = "Side_Draft_Angle"
        
        ext_lid_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        ext_feat = ext_lid_builder.CommitFeature()
        lid_body = ext_feat.GetBodies()[0]
        set_name(ext_feat, "F3_Extrude_Lid")
        print("[OK] Lid block extruded.")
    finally:
        ext_lid_builder.Destroy()

    # Create sphere for top dome intersection
    sz = part.Expressions.FindObject("Sphere_Center_Z").Value
    dome_sphere = create_sphere_body(part, "Sphere_Diameter", sz, "F4_Dome_Sphere")
    
    # Intersect Lid with dome sphere
    lid_body = run_boolean(part, NXOpen.Features.Feature.BooleanType.Intersect, lid_body, dome_sphere)
    print("[OK] Lid dome intersection complete.")

    # Apply top outer perimeter edge blend
    top_edges = []
    z_min_top = part.Expressions.FindObject("Overall_Height").Value - part.Expressions.FindObject("Lid_Crown_Height").Value - 2.0
    for edge in list(lid_body.GetEdges() or []):
        verts = edge.GetVertices()
        if verts:
            z1 = verts[0].Z
            z2 = verts[1].Z
            is_vertical = abs(verts[0].X - verts[1].X) < 0.1 and abs(verts[0].Y - verts[1].Y) < 0.1
            if not is_vertical and (z1 > z_min_top and z2 > z_min_top):
                top_edges.append(edge)

    if top_edges:
        blend_builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = part.ScCollectors.CreateCollector()
            collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(top_edges)], False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "Edge_Blend_Radius")
            feat = blend_builder.CommitFeature()
            set_name(feat, "F5_Top_Fillet")
            lid_body = feat.GetBodies()[0]
            print("[OK] Top fillet applied.")
        finally:
            blend_builder.Destroy()

    # ---------------------------------------------------------------------------
    # 4. Build Decorative Recess (Segment 3) and Logo Pad (Segment 4)
    # ---------------------------------------------------------------------------
    # S3 Recess footprint: Cushion shape (Length 48.0, Width 40.0, Rc 10.0, Rs 200.0) at Z = 25.0, rotated 18°
    s3_curves = create_cushion_curves(part, 40.0, 48.0, 10.0, 200.0, 25.0, angle_deg=18.0)
    # S4 Logo footprint: Rectangle (Length 22.0, Width 18.0) at Z = 25.0, rotated 0°
    s4_curves = [
        part.Curves.CreateLine(point(-11.0, 9.0, 25.0), point(11.0, 9.0, 25.0)),
        part.Curves.CreateLine(point(11.0, 9.0, 25.0), point(11.0, -9.0, 25.0)),
        part.Curves.CreateLine(point(11.0, -9.0, 25.0), point(-11.0, -9.0, 25.0)),
        part.Curves.CreateLine(point(-11.0, -9.0, 25.0), point(-11.0, 9.0, 25.0)),
    ]

    # Helper function to extrude tool body directly from curves
    def extrude_tool_direct(curves, extrude_name):
        builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
        try:
            sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
            rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
            sec.AddToSection(rules, curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, point(0.0, 0.0, 25.0), NXOpen.Section.Mode.Create, False)
            builder.Section = sec
            builder.Direction = part.Directions.CreateDirection(point(0.0, 0.0, 25.0), vec(0.0, 0.0, -1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
            builder.Limits.StartExtend.Value.RightHandSide = "0.0"
            builder.Limits.EndExtend.Value.RightHandSide = "10.0"
            builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
            feat = builder.CommitFeature()
            set_name(feat, extrude_name)
            return feat.GetBodies()[0]
        finally:
            builder.Destroy()

    # Recess 3 Annulus outer & inner tool bodies
    E3_outer = extrude_tool_direct(s3_curves, "E3_outer")
    E4_outer = extrude_tool_direct(s4_curves, "E4_outer")
    E3_annulus_outer = run_boolean(part, NXOpen.Features.Feature.BooleanType.Subtract, E3_outer, E4_outer)

    E3_inner = extrude_tool_direct(s3_curves, "E3_inner")
    E4_inner = extrude_tool_direct(s4_curves, "E4_inner")
    E3_annulus_inner = run_boolean(part, NXOpen.Features.Feature.BooleanType.Subtract, E3_inner, E4_inner)

    # Concentric spheres
    sphere1_a = create_sphere_body(part, "Sphere_Diameter", sz, "Sphere1_a") # outer for recess
    sphere1_b = create_sphere_body(part, "Sphere_Diameter", sz, "Sphere1_b") # outer for pad
    sphere2 = create_sphere_body(part, "Sphere_Diameter - 1.6", sz, "Sphere2") # depth 0.8 mm (1.6 diameter)
    sphere3 = create_sphere_body(part, "Sphere_Diameter - 0.8", sz, "Sphere3") # depth 0.4 mm (0.8 diameter)

    # Recess 3 Volume
    T3_outer = run_boolean(part, NXOpen.Features.Feature.BooleanType.Intersect, E3_annulus_outer, sphere1_a)
    T3_inner = run_boolean(part, NXOpen.Features.Feature.BooleanType.Intersect, E3_annulus_inner, sphere2)
    Recess_3_Volume = run_boolean(part, NXOpen.Features.Feature.BooleanType.Subtract, T3_outer, T3_inner)

    # Recess 4 Volume (Logo Pad)
    E4_logo_outer = extrude_tool_direct(s4_curves, "E4_logo_outer")
    E4_logo_inner = extrude_tool_direct(s4_curves, "E4_logo_inner")
    T4_outer = run_boolean(part, NXOpen.Features.Feature.BooleanType.Intersect, E4_logo_outer, sphere1_b)
    T4_inner = run_boolean(part, NXOpen.Features.Feature.BooleanType.Intersect, E4_logo_inner, sphere3)
    Recess_4_Volume = run_boolean(part, NXOpen.Features.Feature.BooleanType.Subtract, T4_outer, T4_inner)

    # Subtract the recess and logo pad volumes from Lid body
    lid_body = run_boolean(part, NXOpen.Features.Feature.BooleanType.Subtract, lid_body, Recess_3_Volume)
    lid_body = run_boolean(part, NXOpen.Features.Feature.BooleanType.Subtract, lid_body, Recess_4_Volume)
    print("[OK] Decorative recess and logo pad successfully carved into Lid.")

    # ---------------------------------------------------------------------------
    # 5. Shell Operations
    # ---------------------------------------------------------------------------
    # Shell base body (removing flat top face at Z = 10.0)
    base_top_face = None
    for face in list(base_body.GetFaces() or []):
        z_sum = 0
        count = 0
        for edge in list(face.GetEdges() or []):
            verts = edge.GetVertices()
            if verts:
                z_sum += verts[0].Z
                count += 1
        if count > 0 and abs((z_sum / count) - 10.0) < 0.1:
            base_top_face = face
            break

    if base_top_face:
        shell_builder = part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
        try:
            shell_builder.Body = base_body
            shell_builder.DefaultThickness.RightHandSide = "Wall_Thickness"
            shell_builder.Tolerance = 0.01
            collector = part.ScCollectors.CreateCollector()
            collector.ReplaceRules([part.ScRuleFactory.CreateRuleFaceDumb([base_top_face])], False)
            shell_builder.RemovedFacesCollector = collector
            feat = shell_builder.CommitFeature()
            set_name(feat, "F6_Shell_Base")
            base_body = feat.GetBodies()[0]
            print("[OK] Base shelled.")
        finally:
            shell_builder.Destroy()

    # Offset bottom inner face of base upward by 0.5 mm to achieve bottom thickness 2.5 mm
    base_inner_bottom_face = None
    for face in list(base_body.GetFaces() or []):
        z_sum = 0
        count = 0
        for edge in list(face.GetEdges() or []):
            verts = edge.GetVertices()
            if verts:
                z_sum += verts[0].Z
                count += 1
        if count > 0 and abs((z_sum / count) - 2.0) < 0.1:
            base_inner_bottom_face = face
            break

    if base_inner_bottom_face:
        offset_builder = part.Features.CreateOffsetFaceBuilder(NXOpen.Features.Feature.Null)
        try:
            offset_builder.Distance.RightHandSide = "0.5"
            rule = part.ScRuleFactory.CreateRuleFaceDumb([base_inner_bottom_face])
            offset_builder.FaceCollector.ReplaceRules([rule], False)
            feat = offset_builder.CommitFeature()
            set_name(feat, "F7_Base_Bottom_Offset")
            base_body = feat.GetBodies()[0]
            print("[OK] Base bottom thickness increased to 2.5 mm.")
        finally:
            offset_builder.Destroy()

    # Shell lid body (removing bottom face at Z = 10.4)
    lid_bottom_face = None
    for face in list(lid_body.GetFaces() or []):
        z_sum = 0
        count = 0
        for edge in list(face.GetEdges() or []):
            verts = edge.GetVertices()
            if verts:
                z_sum += verts[0].Z
                count += 1
        if count > 0 and abs((z_sum / count) - 10.4) < 0.1:
            lid_bottom_face = face
            break

    if lid_bottom_face:
        shell_builder = part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
        try:
            shell_builder.Body = lid_body
            shell_builder.DefaultThickness.RightHandSide = "Wall_Thickness"
            shell_builder.Tolerance = 0.01
            collector = part.ScCollectors.CreateCollector()
            collector.ReplaceRules([part.ScRuleFactory.CreateRuleFaceDumb([lid_bottom_face])], False)
            shell_builder.RemovedFacesCollector = collector
            feat = shell_builder.CommitFeature()
            set_name(feat, "F8_Shell_Lid")
            lid_body = feat.GetBodies()[0]
            print("[OK] Lid shelled.")
        finally:
            shell_builder.Destroy()

    # ---------------------------------------------------------------------------
    # 6. Front Latch and Latch Button
    # ---------------------------------------------------------------------------
    rw = VALUES["Front_Recess_Width"]
    rh = VALUES["Front_Recess_Height"]
    rd = VALUES["Front_Recess_Depth"]
    y_front = -W / 2.0

    recess_curves = [
        part.Curves.CreateLine(point(-rw/2.0, y_front, 10.0), point(rw/2.0, y_front, 10.0)),
        part.Curves.CreateLine(point(rw/2.0, y_front, 10.0), point(rw/2.0, y_front, 10.0 - rh)),
        part.Curves.CreateLine(point(rw/2.0, y_front, 10.0 - rh), point(-rw/2.0, y_front, 10.0 - rh)),
        part.Curves.CreateLine(point(-rw/2.0, y_front, 10.0 - rh), point(-rw/2.0, y_front, 10.0)),
    ]

    ext_rec_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in recess_curves]
        sec.AddToSection(rules, recess_curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, point(0.0, y_front, 10.0), NXOpen.Section.Mode.Create, False)
        ext_rec_builder.Section = sec
        ext_rec_builder.Direction = part.Directions.CreateDirection(point(0.0, y_front, 10.0), vec(0.0, 1.0, 0.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        ext_rec_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_rec_builder.Limits.EndExtend.Value.RightHandSide = "Front_Recess_Depth"
        ext_rec_builder.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
            base_body
        )
        ext_rec_feat = ext_rec_builder.CommitFeature()
        base_body = ext_rec_feat.GetBodies()[0]
        set_name(ext_rec_feat, "F9_Front_Recess_Cut")
        print("[OK] Latch recess cut.")
    finally:
        ext_rec_builder.Destroy()

    # Latch Button
    bd = VALUES["Latch_Button_Diameter"]
    bz = 10.0 - rh / 2.0
    y_btn = y_front + rd
    x_axis = vec(1.0, 0.0, 0.0)
    z_axis = vec(0.0, 0.0, 1.0)
    btn_c = part.Curves.CreateArc(point(0.0, y_btn, bz), x_axis, z_axis, bd / 2.0, 0.0, 2.0 * math.pi)

    ext_btn_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rules = [part.ScRuleFactory.CreateRuleCurveDumb([btn_c])]
        sec.AddToSection(rules, btn_c, NXOpen.NXObject.Null, NXOpen.NXObject.Null, point(0.0, y_btn, bz), NXOpen.Section.Mode.Create, False)
        ext_btn_builder.Section = sec
        ext_btn_builder.Direction = part.Directions.CreateDirection(point(0.0, y_btn, bz), vec(0.0, -1.0, 0.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        ext_btn_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_btn_builder.Limits.EndExtend.Value.RightHandSide = "0.6" # Projection: 0.6 mm
        
        ext_btn_builder.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
            base_body
        )
        ext_btn_feat = ext_btn_builder.CommitFeature()
        base_body = ext_btn_feat.GetBodies()[0]
        set_name(ext_btn_feat, "F10_Latch_Button")
        print("[OK] Latch button united.")
    finally:
        ext_btn_builder.Destroy()

    # ---------------------------------------------------------------------------
    # 7. Split Line Mating Perimeter Edge Blends (Cosmetic 0.5 mm)
    # ---------------------------------------------------------------------------
    base_split_edges = []
    for edge in list(base_body.GetEdges() or []):
        verts = edge.GetVertices()
        if verts:
            z1 = verts[0].Z
            z2 = verts[1].Z
            if abs(z1 - 10.0) < 0.1 and abs(z2 - 10.0) < 0.1:
                mid_x, mid_y, _ = edge_mid(edge)
                is_pocket_front = (mid_y < y_front + 3.0) and (abs(mid_x) < rw/2.0 + 1.0)
                if not is_pocket_front:
                    base_split_edges.append(edge)

    lid_split_edges = []
    for edge in list(lid_body.GetEdges() or []):
        verts = edge.GetVertices()
        if verts:
            z1 = verts[0].Z
            z2 = verts[1].Z
            if abs(z1 - 10.4) < 0.1 and abs(z2 - 10.4) < 0.1:
                lid_split_edges.append(edge)

    for label, es, target_body in [("base_split", base_split_edges, base_body), ("lid_split", lid_split_edges, lid_body)]:
        if es:
            blend_builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
            try:
                collector = part.ScCollectors.CreateCollector()
                collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(es)], False)
                blend_builder.Tolerance = 0.01
                blend_builder.AddChainset(collector, "0.5") # 0.5 mm cosmetic split line blend
                feat = blend_builder.CommitFeature()
                set_name(feat, "F11_Split_Fillet_{}".format(label))
                if label == "base_split":
                    base_body = feat.GetBodies()[0]
                else:
                    lid_body = feat.GetBodies()[0]
                print("[OK] Split line edge blend applied for {}.".format(label))
            except Exception as e:
                print("[WARN] Split blend failed for {}: {}".format(label, e))
            finally:
                blend_builder.Destroy()

    # ---------------------------------------------------------------------------
    # Finalize
    # ---------------------------------------------------------------------------
    set_name(base_body, "Compact_Base")
    set_name(lid_body, "Compact_Lid")

    part.ModelingViews.WorkView.Fit()
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("Part saved successfully to {}".format(path))

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

def edge_mid(e):
    pts = edge_points(e)
    if pts is None:
        return 0.0, 0.0, 0.0
    return ((pts[0][0] + pts[1][0]) * 0.5, (pts[0][1] + pts[1][1]) * 0.5, (pts[0][2] + pts[1][2]) * 0.5)

if __name__ == "__main__":
    log_path = Path(__file__).resolve().parents[3] / "compact_journal.log"
    try:
        log_path.write_text("Starting compact model journal\n", encoding="utf-8")
        main()
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
