import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\scratch\temp_split_probe.prt"
    try:
        part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    except Exception as e:
        try:
            part = session.Parts.OpenDisplay(part_path)
        except Exception:
            part = session.Parts.Work

    if part is None:
        print("Error: part is None")
        return

    features = part.Features
    builder = features.CreateSplitBodyBuilder(NXOpen.Features.Feature.Null)
    try:
        print("SplitBodyBuilder methods/properties:")
        for m in sorted(dir(builder)):
            if not m.startswith("__"):
                print(f"  {m}")
    finally:
        builder.Destroy()

if __name__ == "__main__":
    main()
