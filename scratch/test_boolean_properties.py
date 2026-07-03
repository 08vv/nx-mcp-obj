import NXOpen

def main():
    session = NXOpen.Session.GetSession()
    work_part = session.Parts.Work
    if work_part is None:
        # Create a temp part to inspect the builder
        work_part = session.Parts.NewDisplay("C:/Users/HP/nx-mcp/temp_inspect.prt", NXOpen.Part.Units.Millimeters)
        
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    attrs = dir(builder)
    print("BooleanBuilder attributes: " + str(attrs))
    
    # Also inspect BooleanTool if it exists
    if hasattr(builder, "BooleanTool"):
        bt = builder.BooleanTool
        print("BooleanTool attributes: " + str(dir(bt)))

if __name__ == "__main__":
    main()
