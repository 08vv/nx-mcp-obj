import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_plane_reapply.prt", NXOpen.Part.Units.Millimeters)
        
    part.Expressions.CreateExpression("Number", "Base_Height = 15.0")
    
    # Create Datum Plane
    plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    split_plane_obj = plane_builder.GetPlane()
    split_plane_obj.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    split_plane_obj.Normal = NXOpen.Vector3d(0.0, 0.0, 1.0)
    split_plane_obj.SetExpression("Base_Height")
    plane_feat = plane_builder.CommitFeature()
    
    # Create Plane from feature
    plane = part.Planes.CreatePlane(plane_feat)
    print("Before re-applying:")
    print("  Origin:", plane.Origin)
    print("  Normal:", plane.Normal)
    print("  Expression value:", plane.Expression.Value)
    
    # Re-apply Origin, Normal, and Expression
    plane.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    plane.Normal = NXOpen.Vector3d(0.0, 0.0, 1.0)
    plane.SetExpression("Base_Height")
    
    print("\nAfter re-applying:")
    print("  Origin:", plane.Origin)
    print("  Normal:", plane.Normal)
    print("  Expression value:", plane.Expression.Value)
    
    plane_builder.Destroy()

if __name__ == "__main__":
    main()
