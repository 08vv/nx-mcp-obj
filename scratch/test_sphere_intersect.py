import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\test_sphere.prt"
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

    # 2. Check if CreateSphereBuilder exists
    features = part.Features
    methods = dir(features)
    has_sphere = "CreateSphereBuilder" in methods
    print(f"Has CreateSphereBuilder: {has_sphere}")

    if has_sphere:
        sphere_builder = features.CreateSphereBuilder(NXOpen.Features.Feature.Null)
        try:
            # Let's inspect sphere builder properties
            print("SphereBuilder properties:")
            for m in sorted(dir(sphere_builder)):
                if not m.startswith("__"):
                    print(f"  {m}")
        finally:
            sphere_builder.Destroy()

if __name__ == "__main__":
    main()
