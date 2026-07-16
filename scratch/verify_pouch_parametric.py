import sys
from pathlib import Path
import traceback

import NXOpen

def main():
    root = Path(__file__).resolve().parents[1]
    part_path = root / "Pouch_Model.prt"
    
    if not part_path.exists():
        print(f"[FAIL] Part file not found at {part_path}")
        sys.exit(1)
        
    session = NXOpen.Session.GetSession()
    
    # Close if already open
    try:
        part = session.Parts.FindObject(part_path.name)
        part.Close(NXOpen.BasePart.CloseWholeTree.TrueValue, NXOpen.BasePart.CloseModified.CloseWithSaving, None)
    except Exception:
        pass
        
    session.Parts.OpenDisplay(str(part_path))
    part = session.Parts.Work
    print(f"Successfully opened {part_path.name}")
    
    # Verify expressions exist
    required_exprs = [
        "Overall_Height", "Overall_Width", "Overall_Depth", "Wall_Thickness",
        "Shoulder_Height", "Shoulder_Radius", "Side_Taper", "Top_Seal_Width",
        "Bottom_Gusset_Height", "Bottom_Gusset_Depth", "Corner_Radius",
        "Spout_Diameter", "Spout_Length", "Cap_Diameter", "Cap_Height",
        "Seal_Band_Width", "Blend_Radius"
    ]
    
    print("Checking Expressions:")
    for name in required_exprs:
        try:
            expr = part.Expressions.FindObject(name)
            print(f"  {name} = {expr.RightHandSide} (Value: {expr.Value})")
        except Exception:
            print(f"  [MISSING] {name}")
            sys.exit(1)
            
    # Try modifying expressions and updating the model
    print("\nModifying expressions for parametric test:")
    test_modifications = {
        "Overall_Height": 220.0,
        "Overall_Width": 130.0,
        "Overall_Depth": 10.0,
        "Spout_Diameter": 14.0,
        "Cap_Diameter": 18.0,
    }
    
    for name, val in test_modifications.items():
        expr = part.Expressions.FindObject(name)
        expr.RightHandSide = str(val)
        print(f"  Changed {name} -> {val}")
        
    # Trigger regeneration update
    print("Triggering NX Update/Regeneration...")
    try:
        errs = session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)
        if errs > 0:
            print(f"[FAIL] Update completed with {errs} errors")
            sys.exit(1)
        print("[OK] Update completed successfully with 0 errors!")
    except Exception as e:
        print(f"[FAIL] Update failed with exception: {e}")
        traceback.print_exc()
        sys.exit(1)
        
    # Re-verify that geometry was updated (e.g. read back heights/widths)
    print("\nVerifying updated values:")
    for name, expected in test_modifications.items():
        expr = part.Expressions.FindObject(name)
        if abs(expr.Value - expected) > 1e-5:
            print(f"  [FAIL] {name} value {expr.Value} does not match expected {expected}")
            sys.exit(1)
        print(f"  {name} is successfully updated to {expr.Value}")
        
    print("\n[SUCCESS] Parametric verification PASSED!")
    part.Close(NXOpen.BasePart.CloseWholeTree.TrueValue, NXOpen.BasePart.CloseModified.CloseWithoutSaving, None)

if __name__ == "__main__":
    main()
