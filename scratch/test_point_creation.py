import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_point_test.prt", NXOpen.Part.Units.Millimeters)
        
    try:
        p3d = NXOpen.Point3d(0.0, 0.0, 10.0)
        pt = part.Points.CreatePoint(p3d)
        print("Created point successfully:", pt, type(pt))
    except Exception as e:
        print("Failed to create point:", e)

if __name__ == "__main__":
    main()
