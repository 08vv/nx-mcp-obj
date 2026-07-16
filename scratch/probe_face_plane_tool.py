import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_face_plane_probe.prt", NXOpen.Part.Units.Millimeters)
        
    builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
    try:
        tool = builder.BooleanTool
        print("BooleanToolType members:")
        print("  dir:", dir(tool.BooleanToolType))
        
        fpt = tool.FacePlaneTool
        print("\nFacePlaneTool attributes:")
        for m in sorted(dir(fpt)):
            if not m.startswith("__"):
                print(f"  {m}: {type(getattr(fpt, m))}")
    finally:
        builder.Destroy()

if __name__ == "__main__":
    main()
