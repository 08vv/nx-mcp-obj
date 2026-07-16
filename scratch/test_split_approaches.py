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

    part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_split_test.prt", NXOpen.Part.Units.Millimeters)

    part.Expressions.CreateExpression("Number", "Overall_Height = 28.0")
    part.Expressions.CreateExpression("Number", "Base_Height = 15.0")
    part.Expressions.CreateExpression("Number", "Side_Draft_Angle = 3.0")

    # Simple box extrude
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
    print("[OK] Box extruded, Z range 0 to 28")

    # --- Approach A: Standalone Plane via part.Planes.CreatePlane() with no feature ---
    try:
        plane_a = part.Planes.CreatePlane(point(0, 0, 15), vec(0, 0, 1),
                                          NXOpen.SmartObject.UpdateOption.WithinModeling)
        print("Approach A: Standalone Plane created")
        print("  Origin:", plane_a.Origin)
        print("  Normal:", plane_a.Normal)

        split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
        split_builder.TargetBodyCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([main_body], True)
        split_builder.TargetBodyCollector.ReplaceRules([rule], False)
        split_builder.BooleanTool.ToolOption = NXOpen.GeometricUtilities.BooleanToolBuilder.BooleanToolType.NewPlane
        split_builder.BooleanTool.FacePlaneTool.ToolPlane = plane_a
        split_feat = split_builder.CommitFeature()
        print("[OK] Approach A: Split succeeded!")
        result_bodies = [b for b in part.Bodies if b.IsSolidBody]
        print("  Result bodies:", len(result_bodies))
        split_builder.Destroy()
    except Exception as e:
        print("[FAIL] Approach A:", e)
        try:
            split_builder.Destroy()
        except:
            pass

    # --- Approach B: Use DatumPlane feature, then SetExpression on Plane from feature ---
    # Undo previous split first
    try:
        session.UndoLastNVisibleEdits(1)
        main_body = [b for b in part.Bodies if b.IsSolidBody][0]
        print("\n[OK] Undo succeeded, retrying Approach B")
    except Exception as e:
        print("[WARN] Undo failed:", e)
        main_body = [b for b in part.Bodies if b.IsSolidBody][0]

    try:
        plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
        sp = plane_builder.GetPlane()
        sp.Origin = point(0, 0, 0)
        sp.Normal = vec(0, 0, 1)
        sp.SetExpression("Base_Height")
        plane_feat = plane_builder.CommitFeature()

        plane_b = part.Planes.CreatePlane(plane_feat)
        # Re-apply expression
        plane_b.SetExpression("Base_Height")
        print("Approach B: Plane from feature with re-applied expression")
        print("  Origin:", plane_b.Origin)
        print("  Normal:", plane_b.Normal)
        print("  Expression:", plane_b.Expression.Value if plane_b.Expression else "None")

        split_builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
        split_builder.TargetBodyCollector = part.ScCollectors.CreateCollector()
        rule = part.ScRuleFactory.CreateRuleBodyDumb([main_body], True)
        split_builder.TargetBodyCollector.ReplaceRules([rule], False)
        split_builder.BooleanTool.ToolOption = NXOpen.GeometricUtilities.BooleanToolBuilder.BooleanToolType.NewPlane
        split_builder.BooleanTool.FacePlaneTool.ToolPlane = plane_b
        split_feat = split_builder.CommitFeature()
        print("[OK] Approach B: Split succeeded!")
        result_bodies = [b for b in part.Bodies if b.IsSolidBody]
        print("  Result bodies:", len(result_bodies))
        split_builder.Destroy()
        plane_builder.Destroy()
    except Exception as e:
        print("[FAIL] Approach B:", e)
        try:
            split_builder.Destroy()
            plane_builder.Destroy()
        except:
            pass

if __name__ == "__main__":
    main()
