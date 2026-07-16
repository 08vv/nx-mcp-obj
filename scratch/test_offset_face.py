import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\test_offset.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception as e:
        try:
            part = session.Parts.OpenDisplay(part_path)
        except Exception:
            part = session.Parts.Work

    # Expressions
    part.Expressions.CreateExpression("Number", "Base_Height = 15")
    part.Expressions.CreateExpression("Number", "Split_Gap = 0.5")

    # 1. Create block
    block_builder = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    block_builder.SetOriginAndLengths(NXOpen.Point3d(-40, -40, 0), "80", "80", "28")
    block_feat = block_builder.CommitFeature()
    body = block_feat.GetBodies()[0]
    block_builder.Destroy()

    # 2. Split body
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
    finally:
        split_builder.Destroy()

    # Find lid body (higher one)
    bodies = [b for b in part.Bodies if b.IsSolidBody]
    lid_body = None
    for b in bodies:
        pts = []
        for edge in list(b.GetEdges() or []):
            verts = edge.GetVertices()
            if verts:
                pts.append(verts[0].GetCoordinates().Z)
        max_z = max(pts)
        if max_z > 15.01:
            lid_body = b
            break

    # 3. Find the bottom face of the lid body (at Z = 15)
    face_to_offset = None
    for face in list(lid_body.GetFaces() or []):
        z_sum = 0
        count = 0
        for edge in list(face.GetEdges() or []):
            verts = edge.GetVertices()
            if verts:
                z_sum += verts[0].GetCoordinates().Z
                count += 1
        if count > 0 and abs((z_sum / count) - 15.0) < 0.1:
            face_to_offset = face
            break

    # 4. Offset this face by Split_Gap
    if face_to_offset:
        offset_builder = part.Features.CreateOffsetFaceBuilder(NXOpen.Features.Feature.Null)
        try:
            # Let's see how OffsetFaceBuilder is configured
            print("OffsetFaceBuilder methods/properties:")
            for m in sorted(dir(offset_builder)):
                if not m.startswith("__"):
                    print(f"  {m}")
            
            # OffsetFaceBuilder configuration:
            # OffsetFaceBuilder has: FaceCollector or FaceSet, and Distance.
            # Let's inspect FaceCollector or FaceSet in printouts first.
        finally:
            offset_builder.Destroy()

if __name__ == "__main__":
    main()
