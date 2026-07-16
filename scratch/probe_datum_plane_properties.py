import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_datum_prop.prt", NXOpen.Part.Units.Millimeters)
        
    plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    plane = plane_builder.GetPlane()
    plane.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    plane.Normal = NXOpen.Vector3d(0.0, 0.0, 1.0)
    plane.SetExpression("25.0")
    plane_feat = plane_builder.CommitFeature()
    
    datum = plane_builder.GetDatum()
    print("Datum class:", type(datum))
    print("Datum attributes:")
    for m in sorted(dir(datum)):
        if not m.startswith("__"):
            print(f"  {m}: {type(getattr(datum, m, None))}")
            
    plane_builder.Destroy()

if __name__ == "__main__":
    main()
