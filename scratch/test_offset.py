import NXOpen
import NXOpen.Features

def main():
    session = NXOpen.Session.GetSession()
    work_part = session.Parts.Work
    if work_part is None:
        work_part = session.Parts.NewDisplay("C:/Users/HP/nx-mcp/test_offset.prt", NXOpen.Part.Units.Millimeters)
    
    # Try creating a plane object
    origin = NXOpen.Point3d(0.0, 0.0, 53.0)
    normal = NXOpen.Vector3d(0.0, 0.0, 1.0)
    plane_obj = work_part.Planes.CreatePlane(origin, normal, NXOpen.SmartObject.UpdateOption.WithinModeling)
    
    # Try creating datum plane builder
    datum_builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        datum_builder.SetFixedDatumPlane(plane_obj)
        feat = datum_builder.CommitFeature()
        print("Success committing datum plane: " + str(feat))
    except Exception as e:
        print("Failed to commit datum plane: " + str(e))
    finally:
        datum_builder.Destroy()

if __name__ == "__main__":
    main()
