import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\test_sphere_bool.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception as e:
        try:
            part = session.Parts.OpenDisplay(part_path)
        except Exception:
            part = session.Parts.Work

    # 1. Create solid block (Target)
    block_builder = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    block_builder.SetOriginAndLengths(NXOpen.Point3d(-40, -40, 0), "80", "80", "28")
    block_feat = block_builder.CommitFeature()
    target_body = block_feat.GetBodies()[0]
    block_builder.Destroy()
    print("Target block created.")

    # 2. Create Sphere (Tool)
    # We want a sphere of diameter = 1200 (radius = 600)
    # centered at (0, 0, 28 - 600) = (0, 0, -572)
    sphere_builder = part.Features.CreateSphereBuilder(NXOpen.Features.Feature.Null)
    try:
        sphere_builder.Type = NXOpen.Features.SphereBuilder.Types.CenterAndDiameter
        # Create Center Point
        center_pt = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, -572.0))
        sphere_builder.CenterPoint = center_pt
        sphere_builder.Diameter.RightHandSide = "1200"
        sphere_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        sphere_feat = sphere_builder.CommitFeature()
        tool_body = sphere_feat.GetBodies()[0]
        print("Tool sphere created.")
    finally:
        sphere_builder.Destroy()

    # 3. Intersect Target and Tool
    bool_builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        # Check if Intersect is valid BooleanType
        bool_builder.Operation = NXOpen.Features.Feature.BooleanType.Intersect
        
        # Helper logic to assign target and tool
        bool_builder.Targets.Add(target_body)
        
        collector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([tool_body], True)
        collector.ReplaceRules([rule], False)
        
        # Let's inspect which collector to use
        if hasattr(bool_builder, "ToolBodyCollector"):
            bool_builder.ToolBodyCollector = collector
        elif hasattr(bool_builder, "BooleanTool"):
            for attr in ("BodyCollector", "ToolBodyCollector"):
                if hasattr(bool_builder.BooleanTool, attr):
                    setattr(bool_builder.BooleanTool, attr, collector)
                    break
        
        bool_feat = bool_builder.CommitFeature()
        print("Boolean Intersect successful!")
        bodies = part.Bodies
        for i, b in enumerate(bodies):
            print(f"Result Body {i}: IsSolid={b.IsSolidBody}, Name={b.Name}")
    except Exception as e:
        print(f"Failed boolean intersect: {e}")
        import traceback
        traceback.print_exc()
    finally:
        bool_builder.Destroy()

if __name__ == "__main__":
    main()
