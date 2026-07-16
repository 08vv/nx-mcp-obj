import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\test_split_shell.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception as e:
        try:
            part = session.Parts.OpenDisplay(part_path)
        except Exception:
            part = session.Parts.Work

    # Expressions
    part.Expressions.CreateExpression("Number", "Base_Height = 15")

    # 1. Create solid block
    block_builder = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    block_builder.SetOriginAndLengths(NXOpen.Point3d(-40, -40, 0), "80", "80", "28")
    block_feat = block_builder.CommitFeature()
    body = block_feat.GetBodies()[0]
    block_builder.Destroy()
    print("Block created.")

    # 2. Split body using a plane at Z = 15
    origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    z_vector = NXOpen.Vector3d(0.0, 0.0, 1.0)
    plane = part.Planes.CreatePlane(origin, z_vector, NXOpen.SmartObject.UpdateOption.WithinModeling)
    plane.SetExpression("Base_Height")

    split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.Feature.Null)
    try:
        split_builder.SplitBlankCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([body], True)
        split_builder.SplitBlankCollector.ReplaceRules([rule], False)
        
        split_builder.Plane = plane
        split_feat = split_builder.CommitFeature()
        print("Split body successful!")
    except Exception as e:
        print(f"Failed to split body: {e}")
        split_builder.Destroy()
        return
    finally:
        split_builder.Destroy()

    # Find the split bodies
    bodies = [b for b in part.Bodies if b.IsSolidBody]
    print(f"Number of bodies after split: {len(bodies)}")
    base_body = None
    lid_body = None
    for b in bodies:
        # Check center of gravity or bounding box
        # We can find base body which is lower, lid body which is higher
        box = b.GetEdges()[0].GetVertices()[0].GetCoordinates() # get some point
        # Let's check bounding box Z values of all vertices
        pts = []
        for edge in list(b.GetEdges() or []):
            verts = edge.GetVertices()
            if verts:
                pts.append(verts[0].GetCoordinates().Z)
        max_z = max(pts)
        if max_z <= 15.01:
            base_body = b
        else:
            lid_body = b

    # 3. Shell base body removing top face (Z = 15)
    if base_body:
        faces_to_remove = []
        for face in list(base_body.GetFaces() or []):
            # Find face that has all vertices at Z = 15
            # Or check the normal vector (Z = 1) and position (Z = 15)
            # Let's check the highest face
            # We can compute average Z of vertices of the face
            z_sum = 0
            count = 0
            for edge in list(face.GetEdges() or []):
                verts = edge.GetVertices()
                if verts:
                    z_sum += verts[0].GetCoordinates().Z
                    count += 1
            if count > 0 and abs((z_sum / count) - 15.0) < 0.1:
                faces_to_remove.append(face)
                break
        
        if faces_to_remove:
            shell_builder = part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
            try:
                shell_builder.Body = base_body
                shell_builder.DefaultThickness.RightHandSide = "2.0"
                shell_builder.Tolerance = 0.01
                collector = part.ScCollectors.CreateCollector()
                collector.ReplaceRules([part.ScRuleFactory.CreateRuleFaceDumb(faces_to_remove)], False)
                shell_builder.RemovedFacesCollector = collector
                shell_feat = shell_builder.CommitFeature()
                print("Base body shelled successfully!")
            except Exception as e:
                print(f"Failed to shell base body: {e}")
            finally:
                shell_builder.Destroy()
        else:
            print("Failed to find top face of base body for shell.")

    # 4. Shell lid body removing bottom face (Z = 15)
    if lid_body:
        faces_to_remove = []
        for face in list(lid_body.GetFaces() or []):
            z_sum = 0
            count = 0
            for edge in list(face.GetEdges() or []):
                verts = edge.GetVertices()
                if verts:
                    z_sum += verts[0].GetCoordinates().Z
                    count += 1
            if count > 0 and abs((z_sum / count) - 15.0) < 0.1:
                faces_to_remove.append(face)
                break
        
        if faces_to_remove:
            shell_builder = part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
            try:
                shell_builder.Body = lid_body
                shell_builder.DefaultThickness.RightHandSide = "2.0"
                shell_builder.Tolerance = 0.01
                collector = part.ScCollectors.CreateCollector()
                collector.ReplaceRules([part.ScRuleFactory.CreateRuleFaceDumb(faces_to_remove)], False)
                shell_builder.RemovedFacesCollector = collector
                shell_feat = shell_builder.CommitFeature()
                print("Lid body shelled successfully!")
            except Exception as e:
                print(f"Failed to shell lid body: {e}")
            finally:
                shell_builder.Destroy()
        else:
            print("Failed to find bottom face of lid body for shell.")

if __name__ == "__main__":
    main()
