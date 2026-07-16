import NXOpen
import math
import os
import sys

def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))

def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))

def solve_cushion(W, L, Rc, Rs):
    B = W/2.0 - Rs
    A = L/2.0 - Rs
    d = Rs - Rc
    k = (A**2 - B**2) / 2.0
    aq = 1.0 + (B / A)**2
    bq = 2.0 * B * (k / (A**2) - 1.0)
    cq = (k / A)**2 + B**2 - d**2
    disc = bq**2 - 4.0 * aq * cq
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

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\temp_face_draft.prt"
    
    session.Parts.CloseAll(NXOpen.BasePartCloseModified.CloseModified, None)
    if os.path.exists(part_path):
        try:
            os.remove(part_path)
        except Exception:
            pass

    part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)

    # Expressions
    part.Expressions.CreateExpression("Number", "Overall_Width = 80")
    part.Expressions.CreateExpression("Number", "Overall_Length = 80")
    part.Expressions.CreateExpression("Number", "Corner_Radius = 15")
    part.Expressions.CreateExpression("Number", "Overall_Height = 28")
    part.Expressions.CreateExpression("Number", "Side_Draft_Angle = 3.0")

    W, L, Rc = 80.0, 80.0, 15.0
    Rs = 5.0 * W
    xc, yc, tx_top, ty_top, tx_right, ty_right = solve_cushion(W, L, Rc, Rs)

    curves = []
    x_axis = vec(1.0, 0.0, 0.0)
    y_axis = vec(0.0, 1.0, 0.0)
    z = 0.0
    
    c_top = point(0.0, W/2.0 - Rs, z)
    curves.append(part.Curves.CreateArc(c_top, x_axis, y_axis, Rs, math.atan2(ty_top - (W/2.0 - Rs), -tx_top), math.atan2(ty_top - (W/2.0 - Rs), tx_top)))
    c_tr = point(xc, yc, z)
    curves.append(part.Curves.CreateArc(c_tr, x_axis, y_axis, Rc, math.atan2(ty_right - yc, tx_right - xc), math.atan2(ty_top - yc, tx_top - xc)))
    c_right = point(L/2.0 - Rs, 0.0, z)
    curves.append(part.Curves.CreateArc(c_right, x_axis, y_axis, Rs, math.atan2(-ty_right, tx_right - (L/2.0 - Rs)), math.atan2(ty_right, tx_right - (L/2.0 - Rs))))
    c_br = point(xc, -yc, z)
    curves.append(part.Curves.CreateArc(c_br, x_axis, y_axis, Rc, math.atan2(-ty_top - (-yc), tx_top - xc), math.atan2(-ty_right - (-yc), tx_right - xc)))
    c_bottom = point(0.0, -W/2.0 + Rs, z)
    curves.append(part.Curves.CreateArc(c_bottom, x_axis, y_axis, Rs, math.atan2(-ty_top - (-W/2.0 + Rs), tx_top), math.atan2(-ty_top - (-W/2.0 + Rs), -tx_top)))
    c_bl = point(-xc, -yc, z)
    curves.append(part.Curves.CreateArc(c_bl, x_axis, y_axis, Rc, math.atan2(-ty_right - (-yc), -tx_right - (-xc)), math.atan2(-ty_top - (-yc), -tx_top - (-xc))))
    c_left = point(-L/2.0 + Rs, 0.0, z)
    curves.append(part.Curves.CreateArc(c_left, x_axis, y_axis, Rs, math.atan2(-ty_right, -tx_right - (-L/2.0 + Rs)), math.atan2(ty_right, -tx_right - (-L/2.0 + Rs))))
    c_tl = point(-xc, yc, z)
    curves.append(part.Curves.CreateArc(c_tl, x_axis, y_axis, Rc, math.atan2(ty_top - yc, -tx_top - (-xc)), math.atan2(ty_right - yc, -tx_right - (-xc))))

    factory2 = getattr(part.Sketches, "CreateSketchInPlaceBuilder2", None)
    builder = factory2(None)
    matrix = NXOpen.Matrix3x3()
    matrix.Xx = 1.0; matrix.Xy = 0.0; matrix.Xz = 0.0
    matrix.Yx = 0.0; matrix.Yy = 1.0; matrix.Yz = 0.0
    matrix.Zx = 0.0; matrix.Zy = 0.0; matrix.Zz = 1.0
    builder.Csystem = part.CoordinateSystems.CreateCoordinateSystem(point(0.0, 0.0, 0.0), part.NXMatrices.Create(matrix), True)
    
    commit = getattr(builder, "CommitFeature", None) or getattr(builder, "Commit", None)
    sketch_feat = commit()
    builder.Destroy()
    sketch = sketch_feat.Sketch if hasattr(sketch_feat, "Sketch") else sketch_feat

    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for c in curves:
        sketch.AddGeometry(c, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    sketch_curves = list(sketch.GetAllGeometry())

    # 1. Extrude footprint without draft
    ext_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in sketch_curves]
        sec.AddToSection(rules, sketch_curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, point(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        ext_builder.Section = sec
        ext_builder.Direction = part.Directions.CreateDirection(point(0.0, 0.0, 0.0), vec(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_builder.Limits.EndExtend.Value.RightHandSide = "Overall_Height"
        ext_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        ext_feat = ext_builder.CommitFeature()
        main_body = ext_feat.GetBodies()[0]
        print("[OK] Extruded main body without draft successfully!")
    finally:
        ext_builder.Destroy()

    # 2. Add Face Draft to the 8 side faces
    # Draft angle = Side_Draft_Angle (positive 3.0 degrees)
    # Draft direction = Z-axis
    # Stationary face = bottom face (Z=0)
    # We will find the bottom face of the main body, and all the side faces
    faces = list(main_body.GetFaces())
    bottom_face = None
    side_faces = []
    
    for f in faces:
        # Find bottom face (normal is (0,0,-1) or center has Z=0)
        box = f.GetEnvelope()
        z_min, z_max = box[2], box[5]
        if abs(z_min) < 1e-4 and abs(z_max) < 1e-4:
            bottom_face = f
        else:
            # Side faces (vertical) or top face (Z=28)
            if abs(z_max - 28.0) > 1e-4:
                side_faces.append(f)
                
    print(f"Found bottom face: {bottom_face is not None}")
    print(f"Found side faces: {len(side_faces)}")
    
    draft_builder = part.Features.CreateDraftBuilder(NXOpen.Features.Feature.Null)
    try:
        # Draft type: Face draft
        # Let's see how draft is built in NXOpen.
        # Typically:
        # draft_builder.Type = NXOpen.Features.DraftBuilder.Types.Face
        # but let's see draft_builder properties
        print("DraftBuilder members:")
        for m in sorted(dir(draft_builder)):
            if not m.startswith("__"):
                print(f"  {m}")
    finally:
        draft_builder.Destroy()

if __name__ == "__main__":
    main()
