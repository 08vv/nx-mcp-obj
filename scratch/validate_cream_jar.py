"""Validate the Cream_Jar_Model.prt features, bodies, expressions, and parametric regeneration.

Usage:
  run_journal.exe scratch/validate_cream_jar.py
"""

import sys
from pathlib import Path
import NXOpen

def main():
    session = NXOpen.Session.GetSession()
    # Path is scratch/validate_cream_jar.py. parent is scratch, parent's parent is the workspace root.
    part_path = Path(__file__).resolve().parents[1] / "Cream_Jar_Model.prt"
    
    # Close all parts first to clean memory
    try:
        session.Parts.CloseAll(NXOpen.BasePartCloseModified.CloseModified, None)
    except Exception:
        pass
        
    # Open the model part
    part, load_status = session.Parts.OpenActiveDisplay(
        str(part_path),
        NXOpen.DisplayPartOption.AllowAdditional
    )
    load_status.Dispose()
    part = session.Parts.Work
    print(f"Successfully loaded part: {part.FullPath}")
    
    # Verify solid bodies
    bodies = [b for b in part.Bodies if b.IsSolidBody]
    print(f"Solid body count: {len(bodies)}")
    body_names = []
    for b in bodies:
        name = b.Name
        print(f"  Body found: name='{name}'")
        body_names.append(name)
        
    expected_bodies = ["jar_body", "collar_ring", "lid"]
    body_names_lower = [name.lower() for name in body_names]
    for eb in expected_bodies:
        if eb not in body_names_lower:
            print(f"FAIL: Expected body '{eb}' not found in the model! Found: {body_names}")
            sys.exit(1)
    print("PASS: All 3 expected solid bodies found and correctly named (case-insensitive check passed).")
    
    # Verify expressions
    expected_exprs = [
        "Overall_Diameter", "Overall_Height", "Jar_Diameter", "Jar_Height",
        "Jar_Wall_Thickness", "Base_Thickness", "Bottom_Blend_Radius",
        "Neck_Diameter", "Neck_Height", "Collar_Diameter", "Collar_Height",
        "Collar_Thickness", "Lid_Diameter", "Lid_Height", "Lid_Dome_Height",
        "Lid_Corner_Radius", "Edge_Blend_Radius", "Split_Gap"
    ]
    
    print("Checking Expressions:")
    for ee in expected_exprs:
        try:
            expr = part.Expressions.FindObject(ee)
            print(f"  Expression: {ee} = {expr.RightHandSide} (evaluates to {expr.Value})")
        except Exception:
            print(f"FAIL: Expression '{ee}' not found!")
            sys.exit(1)
    print("PASS: All 18 required Expressions exist in the model.")
    
    # Test parametric update/regeneration
    print("Testing parametric regeneration with modified dimensions...")
    try:
        jd_expr = part.Expressions.FindObject("Jar_Diameter")
        jd_expr.RightHandSide = "80.0"
        
        jh_expr = part.Expressions.FindObject("Jar_Height")
        jh_expr.RightHandSide = "40.0"
        
        # Trigger full model rebuild
        session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)
        print("PASS: Model successfully regenerated without errors after updating Jar_Diameter to 80.0 and Jar_Height to 40.0!")
    except Exception as e:
        print(f"FAIL: Parametric regeneration failed: {e}")
        sys.exit(1)
        
    # Revert parameters to default to keep part clean
    try:
        jd_expr.RightHandSide = "70.0"
        jh_expr.RightHandSide = "32.0"
        session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)
        
        # Save after reverting
        part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
        print("PASS: Successfully reverted expressions and saved the cleaned model.")
    except Exception as e:
        print(f"FAIL: Revert and save failed: {e}")
        sys.exit(1)
        
    print("\nAll validation checks passed successfully!")

if __name__ == "__main__":
    main()
