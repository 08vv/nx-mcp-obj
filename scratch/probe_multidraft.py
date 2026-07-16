import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\temp_multidraft.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception:
        part = session.Parts.Work

    builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        draft = builder.Draft
        print("MultiDraft properties:")
        for m in sorted(dir(draft)):
            if not m.startswith("__"):
                print(f"  {m}: {type(getattr(draft, m))}")
    finally:
        builder.Destroy()

if __name__ == "__main__":
    main()
