import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\Compact_Model.prt"
    
    try:
        result = session.Parts.OpenDisplay(part_path)
        if isinstance(result, tuple):
            part = result[0]
        else:
            part = result
        print("[OK] Opened Compact_Model.prt")
    except Exception as e:
        print("[FAIL] Failed to open:", e)
        sys.exit(1)
    
    print("\n--- All Expressions ---")
    try:
        for expr in part.Expressions:
            print(f"  Name='{expr.Name}' RHS='{expr.RightHandSide}' Value={expr.Value}")
    except Exception as e:
        print(f"  Error iterating expressions: {e}")
        # Try alternate approach
        try:
            expr_list = list(part.Expressions)
            print(f"  Expression count: {len(expr_list)}")
            for expr in expr_list:
                print(f"  Name='{expr.Name}' RHS='{expr.RightHandSide}' Value={expr.Value}")
        except Exception as e2:
            print(f"  Error: {e2}")
    
    print("\n--- All Bodies ---")
    try:
        for b in part.Bodies:
            if b.IsSolidBody:
                face_count = len(list(b.GetFaces() or []))
                print(f"  Body Name='{b.Name}' Faces={face_count}")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    main()
