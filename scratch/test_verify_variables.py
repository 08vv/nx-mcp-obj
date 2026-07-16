import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    # Close all parts and open a new one
    session.Parts.CloseAll(NXOpen.BasePartCloseModified.CloseModified, None)
    part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_verify_var.prt", NXOpen.Part.Units.Millimeters)
    
    # Create expressions
    part.Expressions.CreateExpression("Number", "Overall_Width = 80.0")
    part.Expressions.CreateExpression("Number", "Overall_Length = 80.0")
    part.Expressions.CreateExpression("Number", "Corner_Radius = 15.0")
    
    # Read them
    W = part.Expressions.FindObject("Overall_Width").Value
    L = part.Expressions.FindObject("Overall_Length").Value
    Rc = part.Expressions.FindObject("Corner_Radius").Value
    
    print(f"Read values: W={W} (type={type(W)}), L={L}, Rc={Rc}")

if __name__ == "__main__":
    main()
