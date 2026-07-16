import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_feat_probe.prt", NXOpen.Part.Units.Millimeters)
        
    print("Features methods containing Point or Sphere:")
    for m in sorted(dir(part.Features)):
        if "Point" in m or "Sphere" in m:
            print(f"  {m}")

if __name__ == "__main__":
    main()
