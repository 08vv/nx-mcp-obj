import NXOpen
import sys

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

def point(x, y, z):
    return NXOpen.Point3d(float(x), float(y), float(z))

def vec(x, y, z):
    return NXOpen.Vector3d(float(x), float(y), float(z))

def main():
    session = NXOpen.Session.GetSession()
    # Close any open parts
    for p in list(session.Parts or []):
        p.Close(NXOpen.BasePart.CloseModified.CloseWithDiscard, None)
        
    part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_datum_gen_test.prt", NXOpen.Part.Units.Millimeters)
    
    # 1. Expressions
    for name, value in VALUES.items():
        part.Expressions.CreateExpression("Number", f"{name} = {value}")
        
    r_val = "((Overall_Length / 2.0 + 20.0)^2 + Lid_Crown_Height^2) / (2.0 * Lid_Crown_Height)"
    part.Expressions.CreateExpression("Number", f"Sphere_Radius = {r_val}")
    part.Expressions.CreateExpression("Number", "Sphere_Diameter = 2.0 * Sphere_Radius")
    part.Expressions.CreateExpression("Number", "Sphere_Center_Z = Overall_Height - Sphere_Radius")
    
    # 2. Rectangle footprint curves
    rect_lines = []
    rect_lines.append(part.Curves.CreateLine(point(-40, -40, 0), point(40, -40, 0)))
    rect_lines.append(part.Curves.CreateLine(point(40, -40, 0), point(40, 40, 0)))
    rect_lines.append(part.Curves.CreateLine(point(40, 40, 0), point(-40, 40, 0)))
    rect_lines.append(part.Curves.CreateLine(point(-40, 40, 0), point(-40, -40, 0)))
    
    # Extrude
    ext_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
    rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in rect_lines]
    sec.AddToSection(rules, rect_lines[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, point(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
    ext_builder.Section = sec
    ext_builder.Direction = part.Directions.CreateDirection(point(0.0, 0.0, 0.0), vec(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
    ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
    ext_builder.Limits.EndExtend.Value.RightHandSide = "Overall_Height"
    draft = ext_builder.Draft
    draft.DraftOption = NXOpen.GeometricUtilities.SimpleDraftSimpleDraftType.SimpleFromStart
    draft.FrontDraftAngle.RightHandSide = "Side_Draft_Angle"
    ext_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    ext_feat = ext_builder.CommitFeature()
    main_body = ext_feat.GetBodies()[0]
    ext_builder.Destroy()
    
    # Dome Sphere Boolean Intersect
    sz = part.Expressions.FindObject("Sphere_Center_Z").Value
    sphere_center_pt = part.Points.CreatePoint(point(0.0, 0.0, sz))
    sphere_builder = part.Features.CreateSphereBuilder(NXOpen.Features.Sphere.Null)
    sphere_builder.Type = NXOpen.Features.SphereBuilder.Types.CenterPointAndDiameter
    sphere_builder.CenterPoint = sphere_center_pt
    sphere_builder.Diameter.RightHandSide = "Sphere_Diameter"
    sphere_builder.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    sphere_feat = sphere_builder.CommitFeature()
    dome_sphere = sphere_feat.GetBodies()[0]
    sphere_builder.Destroy()
    
    bool_builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    bool_builder.Operation = NXOpen.Features.Feature.BooleanType.Intersect
    bool_builder.Targets.Add(main_body)
    collector = part.ScCollectors.CreateCollector()
    rule = part.ScRuleFactory.CreateRuleBodyDumb([dome_sphere], True)
    collector.ReplaceRules([rule], False)
    bool_builder.ToolBodyCollector = collector
    bool_feat = bool_builder.CommitFeature()
    main_body = bool_feat.GetBodies()[0]
    bool_builder.Destroy()
    
    # Apply blends
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
                
    # Apply bottom blend
    if bottom_edges:
        blend_builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        collector = part.ScCollectors.CreateCollector()
        collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(bottom_edges)], False)
        blend_builder.Tolerance = 0.01
        blend_builder.AddChainset(collector, "Bottom_Fillet_Radius")
        feat = blend_builder.CommitFeature()
        blend_builder.Destroy()
        
    # Apply top blend
    if top_edges:
        blend_builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        collector = part.ScCollectors.CreateCollector()
        collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(top_edges)], False)
        blend_builder.Tolerance = 0.01
        blend_builder.AddChainset(collector, "Bottom_Fillet_Radius")
        feat = blend_builder.CommitFeature()
        blend_builder.Destroy()
        
    # Retrieve active body
    bodies = [b for b in part.Bodies if b.IsSolidBody]
    if bodies:
        main_body = bodies[0]
        
    # Create Split Plane
    origin_pt = point(0.0, 0.0, 0.0)
    z_dir = vec(0.0, 0.0, 1.0)
    plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    split_plane_obj = plane_builder.GetPlane()
    split_plane_obj.Origin = origin_pt
    split_plane_obj.Normal = z_dir
    split_plane_obj.SetExpression("Base_Height")
    plane_feat = plane_builder.CommitFeature()
    split_plane = part.Planes.CreatePlane(plane_feat)
    
    # Split body
    split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
    try:
        split_builder.TargetBodyCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([main_body], True)
        split_builder.TargetBodyCollector.ReplaceRules([rule], False)
        split_builder.BooleanTool.ToolOption = NXOpen.GeometricUtilities.BooleanToolBuilder.BooleanToolType.NewPlane
        split_builder.BooleanTool.FacePlaneTool.ToolPlane = split_plane
        split_feat = split_builder.CommitFeature()
        print("[OK] Split succeeded! Created bodies:", len(split_feat.GetBodies()))
    except Exception as e:
        print("[FAIL] Split failed:", e)
    finally:
        split_builder.Destroy()
        plane_builder.Destroy()

if __name__ == "__main__":
    main()
