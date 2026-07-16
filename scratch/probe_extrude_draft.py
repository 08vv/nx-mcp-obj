import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\temp_ext_draft.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception as e:
        try:
            part = session.Parts.OpenDisplay(part_path)
        except Exception:
            part = session.Parts.Work

    builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        print("ExtrudeBuilder draft-related methods/properties:")
        for m in sorted(dir(builder)):
            if "draft" in m.lower():
                print(f"  {m}: {type(getattr(builder, m))}")
    finally:
        builder.Destroy()

if __name__ == "__main__":
    main()
