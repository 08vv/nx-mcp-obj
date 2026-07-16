import NXOpen
import math
import os
import sys

def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))

def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\temp_draft_direction.prt"
    
    session.Parts.CloseAll(NXOpen.BasePartCloseModified.CloseModified, None)
    if os.path.exists(part_path):
        try:
            os.remove(part_path)
        except Exception:
            pass

    part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)

    # Expressions
    part.Expressions.CreateExpression("Number", "Overall_Height = 28.0")
    part.Expressions.CreateExpression("Number", "Side_Draft_Angle = 3.0")

    # Create sketch circle
    factory2 = getattr(part.Sketches, "CreateSketchInPlaceBuilder2", None)
    builder = factory2(None)
    matrix = NXOpen.Matrix3x3()
    matrix.Xx = 1.0; matrix.Xy = 0.0; matrix.Xz = 0.0
    matrix.Yx = 0.0; matrix.Yy = 1.0; matrix.Yz = 0.0
    matrix.Zx = 0.0; matrix.Zy = 0.0; matrix.Zz = 1.0
    builder.Csystem = part.CoordinateSystems.CreateCoordinateSystem(point(0.0, 0.0, 0.0), part.NXMatrices.Create(matrix), True)
    sketch_feat = builder.CommitFeature()
    builder.Destroy()
    sketch = sketch_feat.Sketch if hasattr(sketch_feat, "Sketch") else sketch_feat

    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    # Circle of radius 40.0
    c = part.Curves.CreateArc(point(0.0, 0.0, 0.0), vec(1.0,0.0,0.0), vec(0.0,1.0,0.0), 40.0, 0.0, 2.0 * math.pi)
    sketch.AddGeometry(c)
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    sketch_curves = list(sketch.GetAllGeometry())

    for test_angle in ["Side_Draft_Angle", "-Side_Draft_Angle"]:
        ext_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
        try:
            sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
            rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in sketch_curves]
            sec.AddToSection(rules, sketch_curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, point(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
            ext_builder.Section = sec
            ext_builder.Direction = part.Directions.CreateDirection(point(0.0, 0.0, 0.0), vec(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
            ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
            ext_builder.Limits.EndExtend.Value.RightHandSide = "Overall_Height"
            
            draft = ext_builder.Draft
            draft.DraftOption = NXOpen.GeometricUtilities.SimpleDraftSimpleDraftType.SimpleFromStart
            draft.FrontDraftAngle.RightHandSide = test_angle
            
            ext_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
            ext_feat = ext_builder.CommitFeature()
            body = ext_feat.GetBodies()[0]
            
            # Measure top face area or bounding box to determine taper direction
            # Top face should be at Z=28
            top_face = None
            for f in body.GetFaces():
                box = f.GetEnvelope()
                if abs(box[2] - 28.0) < 1e-4 and abs(box[5] - 28.0) < 1e-4:
                    top_face = f
                    break
                    
            if top_face is not None:
                # Top face radius = sqrt(area / pi)
                # Bounding box width = box[3] - box[0]
                box = top_face.GetEnvelope()
                width = box[3] - box[0]
                height = box[4] - box[1]
                print(f"Angle {test_angle}: Top face bounding box width={width:.4f}, height={height:.4f}")
                if width < 80.0:
                    print(f"  -> Tapers INWARD")
                else:
                    print(f"  -> Tapers OUTWARD")
                    
            part.Features.DeleteFeatures([ext_feat])
        except Exception as e:
            print(f"Failed with {test_angle}: {e}")
        finally:
            ext_builder.Destroy()

if __name__ == "__main__":
    main()
