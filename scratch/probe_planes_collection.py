import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_planes_coll.prt", NXOpen.Part.Units.Millimeters)
        
    print("part.Planes methods:")
    for m in sorted(dir(part.Planes)):
        if not m.startswith("__"):
            print(f"  {m}")

if __name__ == "__main__":
    main()
