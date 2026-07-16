import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_geom_probe.prt", NXOpen.Part.Units.Millimeters)
        
    plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        plane = plane_builder.GetPlane()
        print("GetGeometry:", plane.GetGeometry())
        
        # Test SetGeometry
        try:
            plane.SetGeometry(NXOpen.Point3d(0.0,0.0,0.0), NXOpen.Vector3d(0.0,0.0,1.0))
            print("[OK] SetGeometry(Point3d, Vector3d) succeeded!")
        except Exception as e:
            print("[FAIL] SetGeometry(Point3d, Vector3d):", e)
            
        # Test SetExpression
        try:
            plane.SetExpression("25.0")
            print("[OK] SetExpression succeeded!")
        except Exception as e:
            print("[FAIL] SetExpression:", e)
            
    finally:
        plane_builder.Destroy()

if __name__ == "__main__":
    main()
