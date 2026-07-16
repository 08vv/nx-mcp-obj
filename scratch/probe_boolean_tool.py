import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_bool_tool_probe.prt", NXOpen.Part.Units.Millimeters)
        
    builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
    try:
        tool = builder.BooleanTool
        print("BooleanTool attributes:")
        for m in sorted(dir(tool)):
            if not m.startswith("__"):
                print(f"  {m}: {type(getattr(tool, m))}")
    finally:
        builder.Destroy()

if __name__ == "__main__":
    main()
