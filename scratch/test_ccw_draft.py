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
    part_path = r"C:\Users\HP\nx-mcp\scratch\temp_ccw_draft.prt"
    
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

    # Setup vectors and coordinates
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
    
    # 8 transition points in CCW sequence:
    # P1: top-right on top arc
    # P8: top-left on top arc
    # P7: top-left on left arc
    # P6: bottom-left on left arc
    # P5: bottom-left on bottom arc
    # P4: bottom-right on bottom arc
    # P3: bottom-right on right arc
    # P2: top-right on right arc
    
    curves = []
    # 1. Top side arc: P1 (tx_top, ty_top) -> P8 (-tx_top, ty_top)
    curves.append(part.Curves.CreateArc(c_top, x_axis, y_axis, Rs, math.atan2(ty_top - (W/2.0 - Rs), tx_top), math.atan2(ty_top - (W/2.0 - Rs), -tx_top)))
    
    # 2. Top-Left corner: P8 (-tx_top, ty_top) -> P7 (-tx_right, ty_right)
    curves.append(part.Curves.CreateArc(c_tl, x_axis, y_axis, Rc, math.atan2(ty_top - yc, -tx_top - (-xc)), math.atan2(ty_right - yc, -tx_right - (-xc))))
    
    # 3. Left side arc: P7 (-tx_right, ty_right) -> P6 (-tx_right, -ty_right)
    curves.append(part.Curves.CreateArc(c_left, x_axis, y_axis, Rs, math.atan2(ty_right, -tx_right - (-L/2.0 + Rs)), math.atan2(-ty_right, -tx_right - (-L/2.0 + Rs))))
    
    # 4. Bottom-Left corner: P6 (-tx_right, -ty_right) -> P5 (-tx_top, -ty_top)
    curves.append(part.Curves.CreateArc(c_bl, x_axis, y_axis, Rc, math.atan2(-ty_right - (-yc), -tx_right - (-xc)), math.atan2(-ty_top - (-yc), -tx_top - (-xc))))
    
    # 5. Bottom side arc: P5 (-tx_top, -ty_top) -> P4 (tx_top, -ty_top)
    curves.append(part.Curves.CreateArc(c_bottom, x_axis, y_axis, Rs, math.atan2(-ty_top - (-W/2.0 + Rs), -tx_top), math.atan2(-ty_top - (-W/2.0 + Rs), tx_top)))
    
    # 6. Bottom-Right corner: P4 (tx_top, -ty_top) -> P3 (tx_right, -ty_right)
    curves.append(part.Curves.CreateArc(c_br, x_axis, y_axis, Rc, math.atan2(-ty_top - (-yc), tx_top - xc), math.atan2(-ty_right - (-yc), tx_right - xc)))
    
    # 7. Right side arc: P3 (tx_right, -ty_right) -> P2 (tx_right, ty_right)
    curves.append(part.Curves.CreateArc(c_right, x_axis, y_axis, Rs, math.atan2(-ty_right, tx_right - (L/2.0 - Rs)), math.atan2(ty_right, tx_right - (L/2.0 - Rs))))
    
    # 8. Top-Right corner: P2 (tx_right, ty_right) -> P1 (tx_top, ty_top)
    curves.append(part.Curves.CreateArc(c_tr, x_axis, y_axis, Rc, math.atan2(ty_right - yc, tx_right - xc), math.atan2(ty_top - yc, tx_top - xc)))

    # Create Sketch feature
    factory2 = getattr(part.Sketches, "CreateSketchInPlaceBuilder2", None)
    builder = factory2(None)
    matrix = NXOpen.Matrix3x3()
    matrix.Xx = 1.0; matrix.Xy = 0.0; matrix.Xz = 0.0
    matrix.Yx = 0.0; matrix.Yy = 1.0; matrix.Yz = 0.0
    matrix.Zx = 0.0; matrix.Zy = 0.0; matrix.Zz = 1.0
    builder.Csystem = part.CoordinateSystems.CreateCoordinateSystem(point(0.0, 0.0, 0.0), part.NXMatrices.Create(matrix), True)
    sketch_feat = builder.CommitFeature()
    builder.Destroy()
    sketch = sketch_feat.Sketch if hasattr(sketch_feat, "Sketch") else sketch_feat

    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for c in curves:
        sketch.AddGeometry(c, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    sketch_curves = list(sketch.GetAllGeometry())

    ext_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in sketch_curves]
        sec.AddToSection(rules, sketch_curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, point(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        ext_builder.Section = sec
        ext_builder.Direction = part.Directions.CreateDirection(point(0.0, 0.0, 0.0), vec(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_builder.Limits.EndExtend.Value.RightHandSide = "Overall_Height"
        
        # Configure MultiDraft with positive inward draft angle
        draft = ext_builder.Draft
        draft.DraftOption = NXOpen.GeometricUtilities.SimpleDraftSimpleDraftType.SimpleFromStart
        draft.FrontDraftAngle.RightHandSide = "Side_Draft_Angle"
        
        ext_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        ext_feat = ext_builder.CommitFeature()
        print("[OK] Extruded with positive CCW draft successfully!")
    except Exception as e:
        print(f"[FAIL] Extrusion failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ext_builder.Destroy()

if __name__ == "__main__":
    main()
