import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_sphere_correct.prt", NXOpen.Part.Units.Millimeters)
        
    builder = part.Features.CreateSphereBuilder(NXOpen.Features.Sphere.Null)
    try:
        print("SphereBuilder attributes:")
        for m in sorted(dir(builder)):
            if not m.startswith("__"):
                print(f"  {m}")
    finally:
        builder.Destroy()

if __name__ == "__main__":
    main()
