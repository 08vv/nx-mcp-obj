import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_feat_probe.prt", NXOpen.Part.Units.Millimeters)
        
    plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    plane = plane_builder.GetPlane()
    plane.SetGeometry(NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0))
    plane.SetExpression("25.0")
    plane_feat = plane_builder.CommitFeature()
    
    print("plane_feat class:", type(plane_feat))
    print("plane_feat attributes:")
    for m in sorted(dir(plane_feat)):
        if not m.startswith("__"):
            print(f"  {m}")
            
    plane_builder.Destroy()

if __name__ == "__main__":
    main()
