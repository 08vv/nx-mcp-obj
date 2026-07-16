import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_geom_arg_probe.prt", NXOpen.Part.Units.Millimeters)
        
    plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        plane = plane_builder.GetPlane()
        print("SetGeometry docstring:")
        print(plane.SetGeometry.__doc__)
    finally:
        plane_builder.Destroy()

if __name__ == "__main__":
    main()
