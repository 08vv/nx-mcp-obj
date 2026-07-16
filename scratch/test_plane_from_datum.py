import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_plane_from_datum.prt", NXOpen.Part.Units.Millimeters)
        
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
    
    # Get datum object
    datum = plane_builder.GetDatum()
    
    # Convert datum to Plane object
    plane_from_datum = part.Planes.CreatePlaneFromDatum(datum)
    print("Created Plane from Datum successfully:", plane_from_datum)

    # Split body
    split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
    try:
        split_builder.TargetBodyCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([body], True)
        split_builder.TargetBodyCollector.ReplaceRules([rule], False)
        
        split_builder.BooleanTool.ToolOption = NXOpen.GeometricUtilities.BooleanToolBuilder.BooleanToolType.FaceOrPlane
        
        # Assign plane from datum to ToolPlane
        split_builder.BooleanTool.FacePlaneTool.ToolPlane = plane_from_datum
            
        split_feat = split_builder.CommitFeature()
        print("[OK] Split succeeded! Feature:", split_feat)
        bodies = split_feat.GetBodies()
        print(f"Created {len(bodies)} split bodies.")
    except Exception as e:
        print("[FAIL] Split failed:", e)
    finally:
        split_builder.Destroy()
        plane_builder.Destroy()

if __name__ == "__main__":
    main()
