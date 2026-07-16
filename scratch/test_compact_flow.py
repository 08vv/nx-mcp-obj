import NXOpen
import math
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\test_flow.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception as e:
        try:
            part = session.Parts.OpenDisplay(part_path)
        except Exception:
            part = session.Parts.Work

    # 1. Create Expressions
    part.Expressions.CreateExpression("Number", "Overall_Length = 80")
    part.Expressions.CreateExpression("Number", "Overall_Width = 80")
    part.Expressions.CreateExpression("Number", "Overall_Height = 28")
    part.Expressions.CreateExpression("Number", "Corner_Radius = 15")
    part.Expressions.CreateExpression("Number", "Base_Height = 15")
    part.Expressions.CreateExpression("Number", "Lid_Height = 12")
    part.Expressions.CreateExpression("Number", "Split_Gap = 0.5")

    # 2. Extrude a simple block to test split
    block_builder = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    origin = NXOpen.Point3d(-40, -40, 0)
    block_builder.SetOriginAndLengths(origin, "Overall_Length", "Overall_Width", "Overall_Height")
    block_builder.SetBooleanOperationAndTarget(NXOpen.Features.Feature.BooleanType.Create, NXOpen.Body.Null)
    block_feat = block_builder.CommitFeature()
    block_body = block_feat.GetBodies()[0]
    block_builder.Destroy()
    print("Block created.")

    # 3. Create Datum Plane at Z = Base_Height
    datum_plane_builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    datum_plane_builder.Type = NXOpen.Features.DatumPlaneBuilder.Types.Offset
    # We want a datum plane offset from XY plane by Base_Height
    # Let's see how they create offset datum planes in mounting plate journals
    # Let's inspect create_mounting_plate.py lines 260-270 or write a quick test
    print("Datum plane builder properties:")
    for m in sorted(dir(datum_plane_builder)):
        if not m.startswith("__"):
            print(f"  {m}")
    datum_plane_builder.Destroy()

if __name__ == "__main__":
    main()
