import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_datum_get.prt", NXOpen.Part.Units.Millimeters)
        
    # Create block
    block_builder = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    block_builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
    block_builder.SetOriginAndLengths(NXOpen.Point3d(0.0,0.0,0.0), "50.0", "50.0", "50.0")
    block_feat = block_builder.CommitFeature()
    body = block_feat.GetBodies()[0]
    block_builder.Destroy()
    
    # Create Datum Plane
    plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    plane = plane_builder.GetPlane()
    plane.SetGeometry(NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0))
    plane.SetExpression("25.0")
    plane_feat = plane_builder.CommitFeature()
    
    # Get datum object
    datum = plane_builder.GetDatum()
    print("Type of plane_builder.GetDatum():", type(datum))
    
    # Get datum from feature if possible
    # print("Type of plane_feat.DatumPlane:", type(plane_feat.DatumPlane))
    
    # Split body
    split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
    try:
        split_builder.TargetBodyCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([body], True)
        split_builder.TargetBodyCollector.ReplaceRules([rule], False)
        
        split_builder.BooleanTool.ToolOption = NXOpen.GeometricUtilities.BooleanToolBuilder.BooleanToolType.FaceOrPlane
        
        # Test assigning datum to ToolPlane
        try:
            split_builder.BooleanTool.FacePlaneTool.ToolPlane = datum
            print("[OK] Assigned plane_builder.GetDatum() to ToolPlane successfully!")
        except Exception as e:
            print("[FAIL] Assigning plane_builder.GetDatum() to ToolPlane:", e)
            
        split_feat = split_builder.CommitFeature()
        print("[OK] Split succeeded!")
    except Exception as e:
        print("[FAIL] Split failed:", e)
    finally:
        split_builder.Destroy()
        plane_builder.Destroy()

if __name__ == "__main__":
    main()
