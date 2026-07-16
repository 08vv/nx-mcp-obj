import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_builder_plane.prt", NXOpen.Part.Units.Millimeters)
        
    plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        plane = plane_builder.GetPlane()
        print("Plane class:", type(plane))
        print("Plane attributes:")
        for m in sorted(dir(plane)):
            if not m.startswith("__"):
                print(f"  {m}")
                
        # Let's see if we can set its origin, normal, and expression
        # plane.SetOriginAndNormal(NXOpen.Point3d(0.0,0.0,0.0), NXOpen.Vector3d(0.0,0.0,1.0))
        # plane.SetExpression("Base_Height")
    finally:
        plane_builder.Destroy()

if __name__ == "__main__":
    main()
