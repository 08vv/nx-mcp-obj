import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_pt_overloads.prt", NXOpen.Part.Units.Millimeters)
        
    ex = part.Expressions.CreateExpression("Number", "px = 0.0")
    ey = part.Expressions.CreateExpression("Number", "py = 0.0")
    ez = part.Expressions.CreateExpression("Number", "pz = 10.0")
    
    # Test CreatePoint with Expression objects
    try:
        pt = part.Points.CreatePoint(ex, ey, ez)
        print("[OK] Created point from expressions successfully:", pt)
    except Exception as e:
        print("[FAIL] Expression objects failed:", e)

    # Test CreatePoint with float values
    try:
        pt2 = part.Points.CreatePoint(0.0, 0.0, 10.0)
        print("[OK] Created point from float values successfully:", pt2)
    except Exception as e:
        print("[FAIL] Float values failed:", e)

if __name__ == "__main__":
    main()
