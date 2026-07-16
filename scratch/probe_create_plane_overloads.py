import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_overloads.prt", NXOpen.Part.Units.Millimeters)
        
    print("CreatePlane doc:")
    print(part.Planes.CreatePlane.__doc__)
    
    print("\nCreateFixedPlane doc:")
    print(part.Planes.CreateFixedPlane.__doc__)
    
    print("\nCreateFixedTypePlane doc:")
    print(part.Planes.CreateFixedTypePlane.__doc__)

if __name__ == "__main__":
    main()
