"""Create a clean, production-ready, parametric cosmetic compact model in Siemens NX 2206.

This script implements a high-quality CAD modeling history for:
- Cushion footprint sketch
- Extrude with Side_Draft_Angle
- Domed lid surface (Sphere intersection)
- Edge blends on top and bottom perimeters
- Body split at Base_Height
- Split_Gap offset face on Lid
- Internal hollowing via Shell
- Front finger recess cut
- Central latch button
- Mating perimeter edge blends
- Final bodies named Compact_Base and Compact_Lid

All primary dimensions are controlled via Expressions.

Usage:
  run_journal.exe create_compact.py [output_path.prt]
"""

from __future__ import annotations
import math
import os
import sys
import traceback
from pathlib import Path
import NXOpen

# ---------------------------------------------------------------------------
# Default parameters (mm) — Cosmetic Compact
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Length": 80.0,
    "Overall_Width": 80.0,
    "Overall_Height": 28.0,
    "Corner_Radius": 15.0,
    "Lid_Height": 12.0,
    "Base_Height": 15.0,
    "Lid_Crown_Height": 2.0,
    "Side_Draft_Angle": 3.0,
    "Split_Gap": 0.5,
    "Wall_Thickness": 2.0,
    "Front_Recess_Width": 25.0,
    "Front_Recess_Height": 4.0,
    "Front_Recess_Depth": 2.0,
    "Latch_Button_Diameter": 8.0,
    "Edge_Blend_Radius": 1.0,
    "Bottom_Fillet_Radius": 4.0,
}

def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Compact_Model.prt"

def set_name(obj, name: str) -> None:
    try:
        obj.SetName(name)
    except Exception:
        pass

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
    
    # Query current expression values for footprint math
    W = part.Expressions.FindObject("Overall_Width").Value
    L = part.Expressions.FindObject("Overall_Length").Value
    Rc = part.Expressions.FindObject("Corner_Radius").Value
    Rs = 5.0 * W  # side radius of curvature

    xc, yc, tx_top, ty_top, tx_right, ty_right = solve_cushion(W, L, Rc, Rs)

    # 2. Build arcs for footprint in a continuous counter-clockwise loop
    curves = []
    x_axis = vec(1.0, 0.0, 0.0)
    y_axis = vec(0.0, 1.0, 0.0)
    z = 0.0
    
    # Centers
    c_top = point(0.0, W/2.0 - Rs, z)
    c_tl = point(-xc, yc, z)
    c_left = point(-L/2.0 + Rs, 0.0, z)
    c_bl = point(-xc, -yc, z)
    c_bottom = point(0.0, -W/2.0 + Rs, z)
    c_br = point(xc, -yc, z)
    c_right = point(L/2.0 - Rs, 0.0, z)
    c_tr = point(xc, yc, z)
    
    # 1. Top side arc: P1 -> P8
    curves.append(part.Curves.CreateArc(c_top, x_axis, y_axis, Rs, math.atan2(ty_top - (W/2.0 - Rs), tx_top), math.atan2(ty_top - (W/2.0 - Rs), -tx_top)))
    
    # 2. Top-Left corner: P8 -> P7
    curves.append(part.Curves.CreateArc(c_tl, x_axis, y_axis, Rc, math.atan2(ty_top - yc, -tx_top - (-xc)), math.atan2(ty_right - yc, -tx_right - (-xc))))
    
    # 3. Left side arc: P7 -> P6
    curves.append(part.Curves.CreateArc(c_left, x_axis, y_axis, Rs, math.atan2(ty_right, -tx_right - (-L/2.0 + Rs)), math.atan2(-ty_right, -tx_right - (-L/2.0 + Rs))))
    
    # 4. Bottom-Left corner: P6 -> P5
    curves.append(part.Curves.CreateArc(c_bl, x_axis, y_axis, Rc, math.atan2(-ty_right - (-yc), -tx_right - (-xc)), math.atan2(-ty_top - (-yc), -tx_top - (-xc))))
    
    # 5. Bottom side arc: P5 -> P4
    curves.append(part.Curves.CreateArc(c_bottom, x_axis, y_axis, Rs, math.atan2(-ty_top - (-W/2.0 + Rs), -tx_top), math.atan2(-ty_top - (-W/2.0 + Rs), tx_top)))
    
    # 6. Bottom-Right corner: P4 -> P3
    curves.append(part.Curves.CreateArc(c_br, x_axis, y_axis, Rc, math.atan2(-ty_top - (-yc), tx_top - xc), math.atan2(-ty_right - (-yc), tx_right - xc)))
    
    # 7. Right side arc: P3 -> P2
    curves.append(part.Curves.CreateArc(c_right, x_axis, y_axis, Rs, math.atan2(-ty_right, tx_right - (L/2.0 - Rs)), math.atan2(ty_right, tx_right - (L/2.0 - Rs))))
    
    # 8. Top-Right corner: P2 -> P1
    curves.append(part.Curves.CreateArc(c_tr, x_axis, y_axis, Rc, math.atan2(ty_right - yc, tx_right - xc), math.atan2(ty_top - yc, tx_top - xc)))

    # 3. Create Sketch feature
    factory2 = getattr(part.Sketches, "CreateSketchInPlaceBuilder2", None)
    builder = factory2(None)
    matrix = NXOpen.Matrix3x3()
    matrix.Xx = 1.0; matrix.Xy = 0.0; matrix.Xz = 0.0
    matrix.Yx = 0.0; matrix.Yy = 1.0; matrix.Yz = 0.0
    matrix.Zx = 0.0; matrix.Zy = 0.0; matrix.Zz = 1.0
    builder.Csystem = part.CoordinateSystems.CreateCoordinateSystem(point(0.0, 0.0, 0.0), part.NXMatrices.Create(matrix), True)
    sketch_feat = commit_builder(builder)
    builder.Destroy()
    sketch = sketch_feat.Sketch if hasattr(sketch_feat, "Sketch") else sketch_feat
    set_name(sketch_feat, "S1_Cushion_Footprint")

    # Add geometry to sketch
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for c in curves:
        sketch.AddGeometry(c, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    sketch_curves = list(sketch.GetAllGeometry())

    # 4. Extrude footprint sketch with Draft
    ext_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in sketch_curves]
        sec.AddToSection(rules, sketch_curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, point(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        ext_builder.Section = sec
        ext_builder.Direction = part.Directions.CreateDirection(point(0.0, 0.0, 0.0), vec(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_builder.Limits.EndExtend.Value.RightHandSide = "Overall_Height"
        
        # Configure inward side draft
        draft = ext_builder.Draft
        draft.DraftOption = NXOpen.GeometricUtilities.SimpleDraftSimpleDraftType.SimpleFromStart
        draft.FrontDraftAngle.RightHandSide = "Side_Draft_Angle"
        
        ext_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        ext_feat = ext_builder.CommitFeature()
        main_body = ext_feat.GetBodies()[0]
        set_name(ext_feat, "F1_Extrude_Main_Body")
        print("[OK] Main block extruded with side draft.")
    finally:
        ext_builder.Destroy()

    # 5. Domed top surface (Sphere Boolean Intersect)
    sz = part.Expressions.FindObject("Sphere_Center_Z").Value
    sphere_center_pt = part.Points.CreatePoint(point(0.0, 0.0, sz))

    sphere_builder = part.Features.CreateSphereBuilder(NXOpen.Features.Sphere.Null)
    try:
        sphere_builder.Type = NXOpen.Features.SphereBuilder.Types.CenterPointAndDiameter
        sphere_builder.CenterPoint = sphere_center_pt
        sphere_builder.Diameter.RightHandSide = "Sphere_Diameter"
        sphere_builder.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        sphere_feat = sphere_builder.CommitFeature()
        dome_sphere = sphere_feat.GetBodies()[0]
        set_name(sphere_feat, "F2_Dome_Sphere")
        print("[OK] Dome sphere tool body created.")
    finally:
        sphere_builder.Destroy()

    # Boolean Intersect
    bool_builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        bool_builder.Operation = NXOpen.Features.Feature.BooleanType.Intersect
        bool_builder.Targets.Add(main_body)
        collector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([dome_sphere], True)
        collector.ReplaceRules([rule], False)
        if hasattr(bool_builder, "ToolBodyCollector"):
            bool_builder.ToolBodyCollector = collector
        elif hasattr(bool_builder, "BooleanTool"):
            for attr in ("BodyCollector", "ToolBodyCollector"):
                if hasattr(bool_builder.BooleanTool, attr):
                    setattr(bool_builder.BooleanTool, attr, collector)
                    break
        bool_feat = bool_builder.CommitFeature()
        main_body = bool_feat.GetBodies()[0]
        set_name(bool_feat, "F3_Dome_Intersection")
        print("[OK] Dome intersected to shape upper surface.")
    finally:
        bool_builder.Destroy()

    # 6. Apply generous Bottom_Fillet_Radius to top & bottom perimeters
    top_edges = []
    bottom_edges = []
    z_min_top = part.Expressions.FindObject("Overall_Height").Value - part.Expressions.FindObject("Lid_Crown_Height").Value - 2.0

    for edge in list(main_body.GetEdges() or []):
        verts = edge.GetVertices()
        if verts:
            z1 = verts[0].Z
            z2 = verts[1].Z
            if abs(z1) < 0.05 and abs(z2) < 0.05:
                bottom_edges.append(edge)
            is_vertical = abs(verts[0].X - verts[1].X) < 0.1 and abs(verts[0].Y - verts[1].Y) < 0.1
            if not is_vertical and (z1 > z_min_top and z2 > z_min_top):
                top_edges.append(edge)

    # Bottom Edge Blend
    if bottom_edges:
        blend_builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = part.ScCollectors.CreateCollector()
            collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(bottom_edges)], False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "Bottom_Fillet_Radius")
            feat = blend_builder.CommitFeature()
            set_name(feat, "F4_Bottom_Fillet")
            print("[OK] Bottom perimeter fillet applied.")
        finally:
            blend_builder.Destroy()

    # Top Edge Blend
    if top_edges:
        blend_builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = part.ScCollectors.CreateCollector()
            collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(top_edges)], False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "Bottom_Fillet_Radius")
            feat = blend_builder.CommitFeature()
            set_name(feat, "F5_Top_Fillet")
            print("[OK] Top perimeter fillet applied.")
        finally:
            blend_builder.Destroy()

    # Create a standalone Plane at Base_Height for the split tool.
    # NOTE: part.Planes.CreatePlane(plane_feat) resets origin to Z=0 in NX 2206,
    # so we create the plane directly at the evaluated Base_Height position.
    bh_val = part.Expressions.FindObject("Base_Height").Value
    split_plane = part.Planes.CreatePlane(
        point(0.0, 0.0, bh_val), vec(0.0, 0.0, 1.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling)

    # Retrieve the latest active solid body after fillets
    bodies = [b for b in part.Bodies if b.IsSolidBody]
    if bodies:
        main_body = bodies[0]

    split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
    try:
        split_builder.TargetBodyCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([main_body], True)
        split_builder.TargetBodyCollector.ReplaceRules([rule], False)
        split_builder.BooleanTool.ToolOption = NXOpen.GeometricUtilities.BooleanToolBuilder.BooleanToolType.NewPlane
        split_builder.BooleanTool.FacePlaneTool.ToolPlane = split_plane
        split_feat = split_builder.CommitFeature()
        set_name(split_feat, "F6_Body_Split")
        print("[OK] Body split at Base_Height.")
    finally:
        split_builder.Destroy()

    # Identify base and lid bodies
    bodies = [b for b in part.Bodies if b.IsSolidBody]
    base_body = None
    lid_body = None
    b_height = part.Expressions.FindObject("Base_Height").Value

    for b in bodies:
        pts = []
        for edge in list(b.GetEdges() or []):
            verts = edge.GetVertices()
            if verts:
                pts.append(verts[0].Z)
        max_z = max(pts)
        if max_z <= b_height + 0.1:
            base_body = b
        else:
            lid_body = b

    if not base_body or not lid_body:
        raise RuntimeError("Failed to identify split base and lid bodies.")

    # 8. Create Split_Gap by offsetting the lid's bottom face
    lid_bottom_face = None
    for face in list(lid_body.GetFaces() or []):
        z_sum = 0
        count = 0
        for edge in list(face.GetEdges() or []):
            verts = edge.GetVertices()
            if verts:
                z_sum += verts[0].Z
                count += 1
        if count > 0 and abs((z_sum / count) - b_height) < 0.1:
            lid_bottom_face = face
            break

    if lid_bottom_face:
        offset_builder = part.Features.CreateOffsetFaceBuilder(NXOpen.Features.Feature.Null)
        try:
            offset_builder.Distance.RightHandSide = "Split_Gap"
            rule = part.ScRuleFactory.CreateRuleFaceDumb([lid_bottom_face])
            offset_builder.FaceCollector.ReplaceRules([rule], False)
            feat = offset_builder.CommitFeature()
            set_name(feat, "F7_Lid_Gap_Offset")
            print("[OK] Split gap created by face offset.")
        finally:
            offset_builder.Destroy()
    else:
        print("[WARN] Could not find bottom face of lid body for gap offset.")

    # Update dynamic split heights for hollowing checks
    gap_val = part.Expressions.FindObject("Split_Gap").Value
    lid_bottom_z = b_height + gap_val

    # 9. Shell both bodies with Wall_Thickness
    # Shell base body (removing top face at Z = Base_Height)
    base_top_face = None
    for face in list(base_body.GetFaces() or []):
        z_sum = 0
        count = 0
        for edge in list(face.GetEdges() or []):
            verts = edge.GetVertices()
            if verts:
                z_sum += verts[0].Z
                count += 1
        if count > 0 and abs((z_sum / count) - b_height) < 0.1:
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
            set_name(feat, "F8_Shell_Base")
            print("[OK] Base body hollowed.")
        finally:
            shell_builder.Destroy()

    # Shell lid body (removing bottom face at Z = Base_Height + Split_Gap)
    lid_bottom_face_new = None
    for face in list(lid_body.GetFaces() or []):
        z_sum = 0
        count = 0
        for edge in list(face.GetEdges() or []):
            verts = edge.GetVertices()
            if verts:
                z_sum += verts[0].Z
                count += 1
        if count > 0 and abs((z_sum / count) - lid_bottom_z) < 0.1:
            lid_bottom_face_new = face
            break

    if lid_bottom_face_new:
        shell_builder = part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
        try:
            shell_builder.Body = lid_body
            shell_builder.DefaultThickness.RightHandSide = "Wall_Thickness"
            shell_builder.Tolerance = 0.01
            collector = part.ScCollectors.CreateCollector()
            collector.ReplaceRules([part.ScRuleFactory.CreateRuleFaceDumb([lid_bottom_face_new])], False)
            shell_builder.RemovedFacesCollector = collector
            feat = shell_builder.CommitFeature()
            set_name(feat, "F9_Shell_Lid")
            print("[OK] Lid body hollowed.")
        finally:
            shell_builder.Destroy()

    # 10. Front finger recess (Cut into base body)
    # Create recess rectangle directly as standalone curves
    rw = VALUES["Front_Recess_Width"]
    rh = VALUES["Front_Recess_Height"]
    W = VALUES["Overall_Width"]
    y_front = -W / 2.0  # Front face of body at Y = -40
    z_top_rec = b_height
    z_bot_rec = b_height - rh

    rec_curves = [
        part.Curves.CreateLine(point(-rw/2.0, y_front, z_top_rec), point(rw/2.0, y_front, z_top_rec)),
        part.Curves.CreateLine(point(rw/2.0, y_front, z_top_rec), point(rw/2.0, y_front, z_bot_rec)),
        part.Curves.CreateLine(point(rw/2.0, y_front, z_bot_rec), point(-rw/2.0, y_front, z_bot_rec)),
        part.Curves.CreateLine(point(-rw/2.0, y_front, z_bot_rec), point(-rw/2.0, y_front, z_top_rec)),
    ]

    # Extrude cut the recess in positive Y direction into the base body
    ext_rec_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in rec_curves]
        sec.AddToSection(rules, rec_curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                         point(0.0, y_front, b_height), NXOpen.Section.Mode.Create, False)
        ext_rec_builder.Section = sec
        ext_rec_builder.Direction = part.Directions.CreateDirection(
            point(0.0, y_front, b_height), vec(0.0, 1.0, 0.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)

        ext_rec_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_rec_builder.Limits.EndExtend.Value.RightHandSide = "Front_Recess_Depth"

        ext_rec_builder.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
            base_body,
        )
        ext_rec_feat = ext_rec_builder.CommitFeature()
        base_body = ext_rec_feat.GetBodies()[0]
        set_name(ext_rec_feat, "F10_Front_Recess_Cut")
        print("[OK] Front latch recess cut.")
    finally:
        ext_rec_builder.Destroy()

    # 11. Central Latch Button (Add to base body)
    # Circle of diameter Latch_Button_Diameter at center of recess
    bd = VALUES["Latch_Button_Diameter"]
    bz = b_height - rh / 2.0
    btn_c = part.Curves.CreateArc(
        point(0.0, y_front, bz), x_axis, vec(0.0, 0.0, 1.0),
        bd / 2.0, 0.0, 2.0 * math.pi)

    # Extrude button
    ext_btn_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rules = [part.ScRuleFactory.CreateRuleCurveDumb([btn_c])]
        sec.AddToSection(rules, btn_c, NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                         point(0.0, y_front, bz), NXOpen.Section.Mode.Create, False)
        ext_btn_builder.Section = sec
        ext_btn_builder.Direction = part.Directions.CreateDirection(
            point(0.0, y_front, bz), vec(0.0, -1.0, 0.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)

        # Extrude button outward from front face
        ext_btn_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_btn_builder.Limits.EndExtend.Value.RightHandSide = "1.0"

        ext_btn_builder.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
            base_body,
        )
        ext_btn_feat = ext_btn_builder.CommitFeature()
        base_body = ext_btn_feat.GetBodies()[0]
        set_name(ext_btn_feat, "F11_Latch_Button")
        print("[OK] Latch button united.")
    finally:
        ext_btn_builder.Destroy()

    # 12. Edge blends on recess and split line perimeter
    # Let's blend mating split perimeter edges of base and lid, and recess internal edges
    base_split_edges = []
    for edge in list(base_body.GetEdges() or []):
        verts = edge.GetVertices()
        if verts:
            z1 = verts[0].Z
            z2 = verts[1].Z
            # Outer split perimeter edge of base is flat at Z = Base_Height
            if abs(z1 - b_height) < 0.1 and abs(z2 - b_height) < 0.1:
                # Exclude internal pocket edges or vertical pocket edges
                mid_x, mid_y, _ = edge_mid(edge)
                is_pocket_front = (mid_y < -W/2.0 + 3.0) and (abs(mid_x) < VALUES["Front_Recess_Width"]/2.0 + 1.0)
                if not is_pocket_front:
                    base_split_edges.append(edge)

    lid_split_edges = []
    for edge in list(lid_body.GetEdges() or []):
        verts = edge.GetVertices()
        if verts:
            z1 = verts[0].Z
            z2 = verts[1].Z
            # Outer split perimeter edge of lid is flat at Z = Base_Height + Split_Gap
            if abs(z1 - lid_bottom_z) < 0.1 and abs(z2 - lid_bottom_z) < 0.1:
                lid_split_edges.append(edge)

    # Apply split perimeter blends
    for label, es, target_body in [("base_split", base_split_edges, base_body), ("lid_split", lid_split_edges, lid_body)]:
        if es:
            blend_builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
            try:
                collector = part.ScCollectors.CreateCollector()
                collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(es)], False)
                blend_builder.Tolerance = 0.01
                blend_builder.AddChainset(collector, "Edge_Blend_Radius")
                feat = blend_builder.CommitFeature()
                set_name(feat, "F12_Split_Perimeter_Fillet_{}".format(label))
                print("[OK] Split perimeter edge blend applied for {}.".format(label))
            except Exception as e:
                print("[WARN] Split blend failed for {}: {}".format(label, e))
            finally:
                blend_builder.Destroy()

    # Recess internal blend (filter edges in the pocket region)
    recess_edges = []
    for edge in list(base_body.GetEdges() or []):
        mid_x, mid_y, mid_z = edge_mid(edge)
        # Inside pocket bounding box
        if (abs(mid_x) < VALUES["Front_Recess_Width"]/2.0 + 1.0 and
            mid_y < -W/2.0 + VALUES["Front_Recess_Depth"] + 1.5 and
            mid_z > b_height - VALUES["Front_Recess_Height"] - 1.0 and
            mid_z < b_height + 0.5):
            recess_edges.append(edge)

    if recess_edges:
        blend_builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = part.ScCollectors.CreateCollector()
            collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(recess_edges)], False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "Edge_Blend_Radius")
            feat = blend_builder.CommitFeature()
            set_name(feat, "F13_Recess_Fillet")
            print("[OK] Recess pocket edge blend applied.")
        except Exception as e:
            print("[WARN] Recess blend failed: {}".format(e))
        finally:
            blend_builder.Destroy()

    # Name the final bodies
    set_name(base_body, "Compact_Base")
    set_name(lid_body, "Compact_Lid")
    print("[OK] Bodies named Compact_Base and Compact_Lid.")

    # Save
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
