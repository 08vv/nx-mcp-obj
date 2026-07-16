import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_plane_geom.prt", NXOpen.Part.Units.Millimeters)
        
    part.Expressions.CreateExpression("Number", "Base_Height = 15.0")
    
    plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    split_plane_obj = plane_builder.GetPlane()
    split_plane_obj.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    split_plane_obj.Normal = NXOpen.Vector3d(0.0, 0.0, 1.0)
    split_plane_obj.SetExpression("Base_Height")
    
    print("--- BEFORE COMMIT ---")
    print("Origin:", split_plane_obj.Origin)
    print("Normal:", split_plane_obj.Normal)
    print("Expression value:", split_plane_obj.Expression.Value)
    
    plane_feat = plane_builder.CommitFeature()
    datum = plane_builder.GetDatum()
    
    print("\n--- AFTER COMMIT (GetDatum) ---")
    print("Origin:", datum.Origin)
    print("Normal:", datum.Normal)
    print("Expression value:", datum.Expression.Value)
    
    plane_from_datum = part.Planes.CreatePlane(plane_feat)
    print("\n--- AFTER COMMIT (Plane from Feature) ---")
    print("Origin:", plane_from_datum.Origin)
    print("Normal:", plane_from_datum.Normal)
    print("Expression value:", plane_from_datum.Expression.Value)
    
    plane_builder.Destroy()

if __name__ == "__main__":
    main()
