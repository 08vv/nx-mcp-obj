import NXOpen
import math
import sys

def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))

def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))

def solve_cushion(W, L, Rc, Rs):
    B = W/2 - Rs
    A = L/2 - Rs
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

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\test_complete_base.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception as e:
        try:
            part = session.Parts.OpenDisplay(part_path)
        except Exception:
            part = session.Parts.Work

    # Expressions
    part.Expressions.CreateExpression("Number", "Overall_Width = 80")
    part.Expressions.CreateExpression("Number", "Overall_Length = 80")
    part.Expressions.CreateExpression("Number", "Corner_Radius = 15")
    part.Expressions.CreateExpression("Number", "Overall_Height = 28")
    part.Expressions.CreateExpression("Number", "Side_Draft_Angle = 3.0")
    part.Expressions.CreateExpression("Number", "Lid_Crown_Height = 2.0")
    part.Expressions.CreateExpression("Number", "Bottom_Fillet_Radius = 4.0")

    W = 80.0
    L = 80.0
    Rc = 15.0
    Rs = 5.0 * W
    
    xc, yc, tx_top, ty_top, tx_right, ty_right = solve_cushion(W, L, Rc, Rs)

    # Build arcs
    curves = []
    x_axis = vec(1, 0, 0)
    y_axis = vec(0, 1, 0)
    z = 0.0
    
    c_top = point(0.0, W/2 - Rs, z)
    curves.append(part.Curves.CreateArc(c_top, x_axis, y_axis, Rs, math.atan2(ty_top - (W/2 - Rs), -tx_top), math.atan2(ty_top - (W/2 - Rs), tx_top)))
    c_tr = point(xc, yc, z)
    curves.append(part.Curves.CreateArc(c_tr, x_axis, y_axis, Rc, math.atan2(ty_right - yc, tx_right - xc), math.atan2(ty_top - yc, tx_top - xc)))
    c_right = point(L/2 - Rs, 0.0, z)
    curves.append(part.Curves.CreateArc(c_right, x_axis, y_axis, Rs, math.atan2(-ty_right, tx_right - (L/2 - Rs)), math.atan2(ty_right, tx_right - (L/2 - Rs))))
    c_br = point(xc, -yc, z)
    curves.append(part.Curves.CreateArc(c_br, x_axis, y_axis, Rc, math.atan2(-ty_top - (-yc), tx_top - xc), math.atan2(-ty_right - (-yc), tx_right - xc)))
    c_bottom = point(0.0, -W/2 + Rs, z)
    curves.append(part.Curves.CreateArc(c_bottom, x_axis, y_axis, Rs, math.atan2(-ty_top - (-W/2 + Rs), tx_top), math.atan2(-ty_top - (-W/2 + Rs), -tx_top)))
    c_bl = point(-xc, -yc, z)
    curves.append(part.Curves.CreateArc(c_bl, x_axis, y_axis, Rc, math.atan2(-ty_right - (-yc), -tx_right - (-xc)), math.atan2(-ty_top - (-yc), -tx_top - (-xc))))
    c_left = point(-L/2 + Rs, 0.0, z)
    curves.append(part.Curves.CreateArc(c_left, x_axis, y_axis, Rs, math.atan2(-ty_right, -tx_right - (-L/2 + Rs)), math.atan2(ty_right, -tx_right - (-L/2 + Rs))))
    c_tl = point(-xc, yc, z)
    curves.append(part.Curves.CreateArc(c_tl, x_axis, y_axis, Rc, math.atan2(ty_top - yc, -tx_top - (-xc)), math.atan2(ty_right - yc, -tx_right - (-xc))))

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
    sketch = sketch_feat.Sketch

    # Add geometry to sketch
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for c in curves:
        sketch.AddGeometry(c, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    sketch_curves = list(sketch.GetAllGeometry())

    # 1. Extrude footprint sketch with Draft
    ext_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in sketch_curves]
        sec.AddToSection(rules, sketch_curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, point(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        ext_builder.Section = sec
        ext_builder.Direction = part.Directions.CreateDirection(point(0.0, 0.0, 0.0), vec(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_builder.Limits.EndExtend.Value.RightHandSide = "Overall_Height"
        
        # Inward draft
        draft_settings = ext_builder.DraftSettings
        draft_settings.DraftOption = NXOpen.GeometricUtilities.FeatureDraft.Types.FromStartLimit
        draft_settings.Angle.RightHandSide = "-Side_Draft_Angle"
        
        ext_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        ext_feat = ext_builder.CommitFeature()
        body = ext_feat.GetBodies()[0]
        print("Block extruded with draft successfully!")
    finally:
        ext_builder.Destroy()

    # 2. Revolved dome/sphere Boolean Intersect
    # Calculate sphere radius: R = (L_e^2 + C^2) / (2 * C)
    # L_e can be Overall_Length/2 + 20 to ensure it overlaps fully
    # R = ((W/2 + 20)^2 + Lid_Crown_Height^2) / (2 * Lid_Crown_Height)
    # Since we want it parametric, we can use NX Expressions to define the sphere diameter!
    # Let's create expressions for:
    # Sphere_Radius = ((Overall_Length/2.0 + 20.0)**2 + Lid_Crown_Height**2) / (2.0 * Lid_Crown_Height)
    # Sphere_Diameter = 2.0 * Sphere_Radius
    # Sphere_Center_Z = Overall_Height - Sphere_Radius
    part.Expressions.CreateExpression("Number", "Sphere_Radius = ((Overall_Length / 2.0 + 20.0)^2 + Lid_Crown_Height^2) / (2.0 * Lid_Crown_Height)")
    part.Expressions.CreateExpression("Number", "Sphere_Diameter = 2.0 * Sphere_Radius")
    part.Expressions.CreateExpression("Number", "Sphere_Center_Z = Overall_Height - Sphere_Radius")

    sphere_builder = part.Features.CreateSphereBuilder(NXOpen.Features.Feature.Null)
    try:
        sphere_builder.Type = NXOpen.Features.SphereBuilder.Types.CenterAndDiameter
        sphere_center = part.Points.CreatePoint(point(0.0, 0.0, 0.0))
        # Let's link center point to Z expression
        # Actually we can set coordinates using expressions: X = 0, Y = 0, Z = Sphere_Center_Z
        # Let's check how to set point coordinates using expressions
        # Points.CreatePoint takes Point3d. To set it via expressions, we can set the point coordinates
        # Or we can just use the expression value in Python and update it later?
        # To make it parametric, we can create the point, and then create a Point expression constraint
        # Or in NXOpen, part.Points.CreatePoint can take Expressions!
        # Let's see: does part.Points.CreatePoint(Point3d) support expressions? No, Point3d contains floats.
        # But we can define the point using a Point builder!
        # Wait, if we use a point builder:
        # point_builder = part.Points.CreatePointBuilder(...)
        # Or we can just create the point at the current value of Sphere_Center_Z,
        # but to make it 100% parametric, we can create a Point feature!
        # Let's see. If we use the Point builder, we can set X, Y, Z coordinates to expression strings.
        # Let's check if point builder is easy to use.
        # Wait, let's look at how they create points in clevis mount:
        # "work_part.Points.CreatePoint(point)"
        # If we use a point builder:
        pt_builder = part.Points.CreatePointBuilder(NXOpen.Point.Null)
        try:
            pt_builder.Type = NXOpen.PointBuilder.PointTypes.Coordinates
            pt_builder.Csystem = part.CoordinateSystems.Wcs
            pt_builder.X.RightHandSide = "0.0"
            pt_builder.Y.RightHandSide = "0.0"
            pt_builder.Z.RightHandSide = "Sphere_Center_Z"
            sphere_center_pt = pt_builder.Commit()
        finally:
            pt_builder.Destroy()
            
        sphere_builder.CenterPoint = sphere_center_pt
        sphere_builder.Diameter.RightHandSide = "Sphere_Diameter"
        sphere_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        sphere_feat = sphere_builder.CommitFeature()
        tool_body = sphere_feat.GetBodies()[0]
        print("Sphere tool created.")
    finally:
        sphere_builder.Destroy()

    # Intersect
    bool_builder = part.Features.CreateBooleanBuilder(NXOpen.Features.Feature.BooleanType.Null)
    try:
        bool_builder.Operation = NXOpen.Features.Feature.BooleanType.Intersect
        bool_builder.Targets.Add(body)
        collector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([tool_body], True)
        collector.ReplaceRules([rule], False)
        if hasattr(bool_builder, "ToolBodyCollector"):
            bool_builder.ToolBodyCollector = collector
        elif hasattr(bool_builder, "BooleanTool"):
            for attr in ("BodyCollector", "ToolBodyCollector"):
                if hasattr(bool_builder.BooleanTool, attr):
                    setattr(bool_builder.BooleanTool, attr, collector)
                    break
        bool_feat = bool_builder.CommitFeature()
        body = bool_feat.GetBodies()[0]
        print("Dome intersection successful!")
    finally:
        bool_builder.Destroy()

    # 3. Apply Edge Blends to top and bottom perimeters
    # We want to blend the bottom edges with Bottom_Fillet_Radius
    # and the top edges with Bottom_Fillet_Radius (or similar)
    # Let's find top and bottom edges
    top_edges = []
    bottom_edges = []
    for edge in list(body.GetEdges() or []):
        verts = edge.GetVertices()
        if verts:
            z1 = verts[0].GetCoordinates().Z
            z2 = verts[1].GetCoordinates().Z
            # Bottom edges are at Z = 0
            if abs(z1) < 0.05 and abs(z2) < 0.05:
                bottom_edges.append(edge)
            # Top edges are near Z = Overall_Height (actually on the domed top face)
            # Since the top face is domed, its edges have Z values between
            # Overall_Height and Overall_Height - Lid_Crown_Height.
            # So Z is greater than Overall_Height - Lid_Crown_Height - 1
            # and less than Overall_Height + 1.
            # And they are not vertical (since they form the perimeter loop)
            # Let's check:
            is_vertical = abs(verts[0].GetCoordinates().X - verts[1].GetCoordinates().X) < 0.1 and abs(verts[0].GetCoordinates().Y - verts[1].GetCoordinates().Y) < 0.1
            if not is_vertical and (z1 > 20.0 and z2 > 20.0):
                top_edges.append(edge)

    print(f"Found {len(bottom_edges)} bottom edges and {len(top_edges)} top edges.")

    # Apply bottom blend
    if bottom_edges:
        blend_builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = part.ScCollectors.CreateCollector()
            collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(bottom_edges)], False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "Bottom_Fillet_Radius")
            blend_builder.CommitFeature()
            print("Bottom edge blend applied successfully!")
        except Exception as e:
            print(f"Failed to apply bottom blend: {e}")
        finally:
            blend_builder.Destroy()

    # Apply top blend
    if top_edges:
        blend_builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = part.ScCollectors.CreateCollector()
            collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(top_edges)], False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "Bottom_Fillet_Radius")
            blend_builder.CommitFeature()
            print("Top edge blend applied successfully!")
        except Exception as e:
            print(f"Failed to apply top blend: {e}")
        finally:
            blend_builder.Destroy()

if __name__ == "__main__":
    main()
