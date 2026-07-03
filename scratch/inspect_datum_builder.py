import NXOpen
import NXOpen.Features

def main():
    session = NXOpen.Session.GetSession()
    work_part = session.Parts.Work
    if work_part is None:
        work_part = session.Parts.NewDisplay("C:/Users/HP/nx-mcp/test_inspect.prt", NXOpen.Part.Units.Millimeters)
    
    datum_builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    print("DatumPlaneBuilder methods and properties:")
    for x in dir(datum_builder):
        print(x)
    datum_builder.Destroy()

if __name__ == "__main__":
    main()
