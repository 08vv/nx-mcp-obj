import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\test_datum_split.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception as e:
        try:
            part = session.Parts.OpenDisplay(part_path)
        except Exception:
            part = session.Parts.Work

    # Expressions
    part.Expressions.CreateExpression("Number", "Base_Height = 15")

    # Create solid block
    block_builder = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    block_builder.SetOriginAndLengths(NXOpen.Point3d(-40, -40, 0), "80", "80", "28")
    block_feat = block_builder.CommitFeature()
    body = block_feat.GetBodies()[0]
    block_builder.Destroy()

    # Create plane geometry directly
    origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    z_vector = NXOpen.Vector3d(0.0, 0.0, 1.0)
    plane = part.Planes.CreatePlane(origin, z_vector, NXOpen.SmartObject.UpdateOption.WithinModeling)
    plane.SetExpression("Base_Height")

    # Let's see if SplitBodyBuilder accepts the plane directly
    split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.Feature.Null)
    try:
        if hasattr(split_builder, "TargetBody"):
            split_builder.TargetBody = body
        elif hasattr(split_builder, "SplitBlankCollector"):
            # If SplitBlankCollector is used, we add target body to collector
            collector = part.ScCollectors.CreateCollector()
            rule = part.ScRuleFactory.CreateRuleBodyDumb([body], True)
            collector.ReplaceRules([rule], False)
            split_builder.SplitBlankCollector = collector
            
        # Try passing plane
        split_builder.Plane = plane
        
        split_feat = split_builder.CommitFeature()
        print("Split Body created successfully using plane smart object!")
        bodies = part.Bodies
        for i, b in enumerate(bodies):
            print(f"Body {i}: IsSolid={b.IsSolidBody}, Name={b.Name}")
    except Exception as e:
        print(f"Failed to split body with plane smart object: {e}")
        import traceback
        traceback.print_exc()
    finally:
        split_builder.Destroy()

if __name__ == "__main__":
    main()
