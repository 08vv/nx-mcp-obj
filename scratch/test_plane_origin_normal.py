import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_org_norm.prt", NXOpen.Part.Units.Millimeters)
        
    plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        plane = plane_builder.GetPlane()
        
        # Test 1: Direct assignment of Point3d/Vector3d
        try:
            plane.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
            plane.Normal = NXOpen.Vector3d(0.0, 0.0, 1.0)
            print("[OK] Direct assignment of Origin/Normal succeeded!")
        except Exception as e:
            print("[FAIL] Direct assignment:", e)
            
        # Test 2: SetGeometry with list of [Point, Direction]
        try:
            pt = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
            dir_vec = part.Directions.CreateDirection(NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
            plane.SetGeometry([pt, dir_vec])
            print("[OK] SetGeometry([Point, Direction]) succeeded!")
        except Exception as e:
            print("[FAIL] SetGeometry([Point, Direction]):", e)
            
    finally:
        plane_builder.Destroy()

if __name__ == "__main__":
    main()
