import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_split_opt.prt", NXOpen.Part.Units.Millimeters)
        
    # Create block
    block_builder = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    block_builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
    block_builder.SetOriginAndLengths(NXOpen.Point3d(0.0,0.0,0.0), "50.0", "50.0", "50.0")
    block_feat = block_builder.CommitFeature()
    body = block_feat.GetBodies()[0]
    block_builder.Destroy()
    
    # Create Datum Plane
    plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    plane_obj = plane_builder.GetPlane()
    plane_obj.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    plane_obj.Normal = NXOpen.Vector3d(0.0, 0.0, 1.0)
    plane_obj.SetExpression("25.0")
    plane_feat = plane_builder.CommitFeature()
    datum = plane_builder.GetDatum()
    
    # Test 1: ToolOption = NewPlane, ToolPlane = plane
    print("\n--- Test 1: NewPlane with plane ---")
    split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
    try:
        split_builder.TargetBodyCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([body], True)
        split_builder.TargetBodyCollector.ReplaceRules([rule], False)
        
        split_builder.BooleanTool.ToolOption = NXOpen.GeometricUtilities.BooleanToolBuilder.BooleanToolType.NewPlane
        # Let's try assigning split_plane (transient) to ToolPlane
        plane_trans = part.Planes.CreatePlane(NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        plane_trans.SetExpression("25.0")
        split_builder.BooleanTool.FacePlaneTool.ToolPlane = plane_trans
        
        split_feat = split_builder.CommitFeature()
        print("[OK] Test 1 Succeeded!")
        split_builder.Destroy()
    except Exception as e:
        print("[FAIL] Test 1:", e)
        split_builder.Destroy()
        
    # Test 2: ToolOption = NewPlane, ToolPlane = plane_from_datum
    print("\n--- Test 2: NewPlane with plane_from_datum ---")
    split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
    try:
        split_builder.TargetBodyCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([body], True)
        split_builder.TargetBodyCollector.ReplaceRules([rule], False)
        
        split_builder.BooleanTool.ToolOption = NXOpen.GeometricUtilities.BooleanToolBuilder.BooleanToolType.NewPlane
        plane_from_datum = part.Planes.CreatePlane(plane_feat)
        split_builder.BooleanTool.FacePlaneTool.ToolPlane = plane_from_datum
        
        split_feat = split_builder.CommitFeature()
        print("[OK] Test 2 Succeeded!")
        split_builder.Destroy()
    except Exception as e:
        print("[FAIL] Test 2:", e)
        split_builder.Destroy()
        
    # Let's inspect the DatumPlane features / properties
    print("\nChecking if datum has GetFaces:")
    try:
        faces = datum.GetFaces()
        print("[OK] datum.GetFaces succeeded:", faces)
    except Exception as e:
        print("[FAIL] datum.GetFaces:", e)

    plane_builder.Destroy()

if __name__ == "__main__":
    main()
