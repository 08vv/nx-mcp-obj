import NXOpen

def main():
    session = NXOpen.Session.GetSession()
    work_part = session.Parts.Work
    if work_part is None:
        work_part = session.Parts.NewDisplay("C:/Users/HP/nx-mcp/test_inspect_sketches.prt", NXOpen.Part.Units.Millimeters)
    
    print("work_part.Sketches methods and properties:")
    for x in dir(work_part.Sketches):
        print(x)

if __name__ == "__main__":
    main()
