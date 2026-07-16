import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay("temp_assoc_test.prt", NXOpen.Part.Units.Millimeters)
    try:
        p1 = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
        p2 = part.Points.CreatePoint(NXOpen.Point3d(5.0, 5.0, 0.0))
        p3 = part.Points.CreatePoint(NXOpen.Point3d(10.0, 0.0, 0.0))
        
        builder = part.BaseFeatures.CreateAssociativeArcBuilder(NXOpen.Features.AssociativeArc.Null)
        
        builder.Type = NXOpen.Features.AssociativeArcBuilder.Types.ThreePointArc
        builder.StartPointOptions = NXOpen.Features.AssociativeArcBuilderStartOption.Point
        builder.MidPointOptions = NXOpen.Features.AssociativeArcBuilderMidOption.Point
        builder.EndPointOptions = NXOpen.Features.AssociativeArcBuilderEndOption.Point
        
        builder.StartPoint.Value = p1
        builder.MidPoint.Value = p2
        builder.EndPoint.Value = p3
        
        feat = builder.CommitFeature()
        print("[OK] Associative arc feature created successfully!")
        
        # Print entity details
        entities = feat.GetEntities()
        print("Feature entities: {}".format(entities))
        if entities:
            print("Arc entity type: {}".format(type(entities[0])))
            
        builder.Destroy()
    except Exception as e:
        print("[FAIL] Associative arc creation failed: {}".format(e))

if __name__ == "__main__":
    main()
