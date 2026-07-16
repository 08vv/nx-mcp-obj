import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\test_ext_draft_exec.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception as e:
        try:
            part = session.Parts.OpenDisplay(part_path)
        except Exception:
            part = session.Parts.Work

    # Expressions
    part.Expressions.CreateExpression("Number", "Side_Draft_Angle = 3.0")

    # Create solid block
    block_builder = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    block_builder.SetOriginAndLengths(NXOpen.Point3d(-40, -40, 0), "80", "80", "28")
    block_feat = block_builder.CommitFeature()
    body = block_feat.GetBodies()[0]
    block_builder.Destroy()

    # Now let's test ExtrudeBuilder with Draft
    ext_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        # Create a simple sketch
        factory2 = getattr(part.Sketches, "CreateSketchInPlaceBuilder2", None)
        builder = factory2(None)
        matrix = NXOpen.Matrix3x3()
        matrix.Xx = 1.0; matrix.Xy = 0.0; matrix.Xz = 0.0
        matrix.Yx = 0.0; matrix.Yy = 1.0; matrix.Yz = 0.0
        matrix.Zx = 0.0; matrix.Zy = 0.0; matrix.Zz = 1.0
        builder.Csystem = part.CoordinateSystems.CreateCoordinateSystem(NXOpen.Point3d(0,0,0), part.NXMatrices.Create(matrix), True)
        sketch_feat = builder.CommitFeature()
        builder.Destroy()
        sketch = sketch_feat.Sketch
        
        sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
        c = part.Curves.CreateArc(NXOpen.Point3d(0, 0, 0), NXOpen.Vector3d(1,0,0), NXOpen.Vector3d(0,1,0), 30.0, 0.0, 2.0 * 3.14159)
        sketch.AddGeometry(c)
        sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
        
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        sketch_curves = list(sketch.GetAllGeometry())
        rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in sketch_curves]
        sec.AddToSection(rules, sketch_curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, NXOpen.Point3d(0,0,0), NXOpen.Section.Mode.Create, False)
        
        ext_builder.Section = sec
        ext_builder.Direction = part.Directions.CreateDirection(NXOpen.Point3d(0,0,0), NXOpen.Vector3d(0,0,1), NXOpen.SmartObject.UpdateOption.WithinModeling)
        ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_builder.Limits.EndExtend.Value.RightHandSide = "50"
        
        # Configure draft
        draft_settings = ext_builder.DraftSettings
        # Set draft type
        # Let's check the enum types in NXOpen.GeometricUtilities.FeatureDraft.Types
        print("FeatureDraft Types:")
        print("  dir:", dir(NXOpen.GeometricUtilities.FeatureDraft.Types))
        # Simple draft
        draft_settings.DraftOption = NXOpen.GeometricUtilities.FeatureDraft.Types.FromStartLimit
        draft_settings.Angle.RightHandSide = "-Side_Draft_Angle" # negative to draft inward
        
        ext_feat = ext_builder.CommitFeature()
        print("Extruded with draft successfully!")
    except Exception as e:
        print(f"Failed to extrude with draft: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ext_builder.Destroy()

if __name__ == "__main__":
    main()
