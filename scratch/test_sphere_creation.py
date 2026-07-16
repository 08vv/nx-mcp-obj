import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_sphere_create.prt", NXOpen.Part.Units.Millimeters)
        
    part.Expressions.CreateExpression("Number", "Sphere_Diameter = 100.0")
    
    try:
        # Create Point
        p3d = NXOpen.Point3d(0.0, 0.0, 50.0)
        sphere_center_pt = part.Points.CreatePoint(p3d)
        
        # Create Sphere Builder
        sphere_builder = part.Features.CreateSphereBuilder(NXOpen.Features.Sphere.Null)
        sphere_builder.Type = NXOpen.Features.SphereBuilder.Types.CenterAndDiameter
        sphere_builder.CenterPoint = sphere_center_pt
        sphere_builder.Diameter.RightHandSide = "Sphere_Diameter"
        sphere_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        
        sphere_feat = sphere_builder.CommitFeature()
        print("[OK] Sphere feature created successfully:", sphere_feat)
        sphere_builder.Destroy()
    except Exception as e:
        print("[FAIL] Sphere creation failed:", e)

if __name__ == "__main__":
    main()
