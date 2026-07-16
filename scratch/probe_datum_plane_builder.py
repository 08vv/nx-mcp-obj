import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_datum_probe.prt", NXOpen.Part.Units.Millimeters)
        
    builder = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        print("DatumPlaneBuilder attributes:")
        for m in sorted(dir(builder)):
            if not m.startswith("__"):
                print(f"  {m}: {type(getattr(builder, m))}")
    finally:
        builder.Destroy()

if __name__ == "__main__":
    main()
