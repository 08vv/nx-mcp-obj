import NXOpen
import sys

def point(x, y, z):
    return NXOpen.Point3d(float(x), float(y), float(z))

def vec(x, y, z):
    return NXOpen.Vector3d(float(x), float(y), float(z))

def main():
    session = NXOpen.Session.GetSession()
    for p in list(session.Parts or []):
        p.Close(NXOpen.BasePart.CloseModified.CloseWithDiscard, None)

    part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_split_expr.prt", NXOpen.Part.Units.Millimeters)

    part.Expressions.CreateExpression("Number", "Overall_Height = 28.0")
    part.Expressions.CreateExpression("Number", "Base_Height = 15.0")

    # Simple box
    lines = []
    lines.append(part.Curves.CreateLine(point(-40, -40, 0), point(40, -40, 0)))
    lines.append(part.Curves.CreateLine(point(40, -40, 0), point(40, 40, 0)))
    lines.append(part.Curves.CreateLine(point(40, 40, 0), point(-40, 40, 0)))
    lines.append(part.Curves.CreateLine(point(-40, 40, 0), point(-40, -40, 0)))

    ext_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
    rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in lines]
    sec.AddToSection(rules, lines[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                     point(0, 0, 0), NXOpen.Section.Mode.Create, False)
    ext_builder.Section = sec
    ext_builder.Direction = part.Directions.CreateDirection(
        point(0, 0, 0), vec(0, 0, 1), NXOpen.SmartObject.UpdateOption.WithinModeling)
    ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
    ext_builder.Limits.EndExtend.Value.RightHandSide = "Overall_Height"
    ext_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    ext_feat = ext_builder.CommitFeature()
    main_body = ext_feat.GetBodies()[0]
    ext_builder.Destroy()

    # Create standalone plane at Base_Height
    bh = part.Expressions.FindObject("Base_Height").Value
    plane = part.Planes.CreatePlane(
        point(0, 0, bh), vec(0, 0, 1),
        NXOpen.SmartObject.UpdateOption.WithinModeling)
    
    # Try to attach expression for parametric update
    try:
        plane.SetExpression("Base_Height")
        print("SetExpression succeeded, Expression:", plane.Expression.Value if plane.Expression else "None")
    except Exception as e:
        print("SetExpression failed:", e)

    print("Plane Origin:", plane.Origin)
    print("Plane Normal:", plane.Normal)

    # Split
    split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
    try:
        split_builder.TargetBodyCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([main_body], True)
        split_builder.TargetBodyCollector.ReplaceRules([rule], False)
        split_builder.BooleanTool.ToolOption = NXOpen.GeometricUtilities.BooleanToolBuilder.BooleanToolType.NewPlane
        split_builder.BooleanTool.FacePlaneTool.ToolPlane = plane
        split_feat = split_builder.CommitFeature()
        print("[OK] Split succeeded! Bodies:", len([b for b in part.Bodies if b.IsSolidBody]))
    except Exception as e:
        print("[FAIL] Split failed:", e)
    finally:
        split_builder.Destroy()

if __name__ == "__main__":
    main()
