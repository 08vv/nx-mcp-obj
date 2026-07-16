import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_tool_obj_test.prt", NXOpen.Part.Units.Millimeters)
        
    # Create block
    block_builder = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    block_builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
    block_builder.SetOriginAndLengths(NXOpen.Point3d(0.0,0.0,0.0), "50.0", "50.0", "50.0")
    block_feat = block_builder.CommitFeature()
    body = block_feat.GetBodies()[0]
    block_builder.Destroy()
    
    # Create Plane object at Z=25
    plane = part.Planes.CreatePlane(NXOpen.Point3d(0.0,0.0,0.0), NXOpen.Vector3d(0.0,0.0,1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
    plane.SetExpression("25.0")

    # Split body
    split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
    try:
        split_builder.TargetBodyCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([body], True)
        split_builder.TargetBodyCollector.ReplaceRules([rule], False)
        
        split_builder.BooleanTool.ToolOption = NXOpen.GeometricUtilities.BooleanToolBuilder.BooleanToolType.FaceOrPlane
        
        # Test SetToolObjects with [plane] (Plane object)
        try:
            split_builder.BooleanTool.FacePlaneTool.SetToolObjects([plane])
            print("[OK] SetToolObjects with [plane] succeeded!")
        except Exception as e:
            print("[FAIL] SetToolObjects with [plane]:", e)

        split_feat = split_builder.CommitFeature()
        print("[OK] Split succeeded! Feature:", split_feat)
        bodies = split_feat.GetBodies()
        print(f"Created {len(bodies)} split bodies.")
    except Exception as e:
        print("[FAIL] Split failed:", e)
        import traceback
        traceback.print_exc()
    finally:
        split_builder.Destroy()

if __name__ == "__main__":
    main()
