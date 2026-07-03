import NXOpen
import NXOpen.Features

def main():
    session = NXOpen.Session.GetSession()
    work_part = session.Parts.Work
    if work_part is None:
        work_part = session.Parts.NewDisplay("C:/Users/HP/nx-mcp/test_sketch_plane.prt", NXOpen.Part.Units.Millimeters)
    
    # Try creating a plane object
    origin = NXOpen.Point3d(0.0, 0.0, 53.0)
    normal = NXOpen.Vector3d(0.0, 0.0, 1.0)
    plane_obj = work_part.Planes.CreatePlane(origin, normal, NXOpen.SmartObject.UpdateOption.WithinModeling)
    
    # Try creating sketch on that plane object
    builder_factory = getattr(work_part.Sketches, "CreateNewSketch", None)
    if not builder_factory:
        builder_factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder", None)
        
    if builder_factory:
        sketch_builder = builder_factory(NXOpen.Features.Feature.Null)
        try:
            sketch_builder.PlaneReference = plane_obj
            feat = sketch_builder.CommitFeature()
            print("Success committing sketch on PlaneReference: " + str(feat))
        except Exception as e:
            print("Failed to commit sketch on PlaneReference: " + str(e))
            # Try setting other properties
            try:
                sketch_builder.PlacementFace = plane_obj
                feat = sketch_builder.CommitFeature()
                print("Success committing sketch on PlacementFace: " + str(feat))
            except Exception as e2:
                print("Failed to commit sketch on PlacementFace: " + str(e2))
        finally:
            sketch_builder.Destroy()
    else:
        print("No builder factory found")

if __name__ == "__main__":
    main()
