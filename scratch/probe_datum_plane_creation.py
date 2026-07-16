import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_datum_creation.prt", NXOpen.Part.Units.Millimeters)
        
    print("Part.DatumPlanes methods:")
    try:
        for m in sorted(dir(part.DatumPlanes)):
            if not m.startswith("__") and "Plane" in m:
                print(f"  part.DatumPlanes.{m}")
    except Exception as e:
        print("  Error:", e)
        
    print("Part.Features methods:")
    try:
        for m in sorted(dir(part.Features)):
            if not m.startswith("__") and "DatumPlane" in m:
                print(f"  part.Features.{m}")
    except Exception as e:
        print("  Error:", e)

if __name__ == "__main__":
    main()
