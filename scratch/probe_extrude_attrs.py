import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\temp_ext_attrs.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception:
        part = session.Parts.Work

    builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        print("EXTRUDE BUILDER DIR:")
        for m in sorted(dir(builder)):
            print(f"  {m}")
    finally:
        builder.Destroy()

if __name__ == "__main__":
    main()
