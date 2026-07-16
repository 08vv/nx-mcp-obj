import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\test_shell_split.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception as e:
        try:
            part = session.Parts.OpenDisplay(part_path)
        except Exception:
            part = session.Parts.Work

    # 1. Create solid block
    block_builder = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    block_builder.SetOriginAndLengths(NXOpen.Point3d(-40, -40, 0), "80", "80", "28")
    block_feat = block_builder.CommitFeature()
    body = block_feat.GetBodies()[0]
    block_builder.Destroy()
    print("Block created.")

    # 2. Shell block with no removed faces
    shell_builder = part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
    try:
        shell_builder.Body = body
        shell_builder.DefaultThickness.RightHandSide = "2.0"
        shell_builder.Tolerance = 0.01
        # Leave RemovedFacesCollector empty
        shell_feat = shell_builder.CommitFeature()
        print("Closed shell successful!")
    except Exception as e:
        print(f"Failed to shell closed body: {e}")
        import traceback
        traceback.print_exc()
        shell_builder.Destroy()
        return
    finally:
        shell_builder.Destroy()

    # 3. Split body using a plane at Z = 15
    origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    z_vector = NXOpen.Vector3d(0.0, 0.0, 1.0)
    plane = part.Planes.CreatePlane(origin, z_vector, NXOpen.SmartObject.UpdateOption.WithinModeling)
    part.Expressions.CreateExpression("Number", "Base_Height = 15")
    plane.SetExpression("Base_Height")

    split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.Feature.Null)
    try:
        # Get the latest body
        bodies = [b for b in part.Bodies if b.IsSolidBody]
        shell_body = bodies[0]
        
        split_builder.SplitBlankCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([shell_body], True)
        split_builder.SplitBlankCollector.ReplaceRules([rule], False)
        
        split_builder.Plane = plane
        split_feat = split_builder.CommitFeature()
        print("Split of hollow body successful!")
        
        bodies = [b for b in part.Bodies if b.IsSolidBody]
        for i, b in enumerate(bodies):
            print(f"Result Body {i}: IsSolid={b.IsSolidBody}, Name='{b.Name}', Faces={len(list(b.GetFaces() or []))}")
    except Exception as e:
        print(f"Failed to split hollow body: {e}")
        import traceback
        traceback.print_exc()
    finally:
        split_builder.Destroy()

if __name__ == "__main__":
    main()
