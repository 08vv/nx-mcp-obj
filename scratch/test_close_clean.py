import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    try:
        # Try flat name BasePartCloseModified
        session.Parts.CloseAll(NXOpen.BasePartCloseModified.CloseWithNoSave, None)
        print("[OK] Closed all parts successfully using flat enum name!")
    except Exception as e:
        print(f"[FAIL] Flat enum failed: {e}")
        
    try:
        # Try nested name BasePart.CloseModified
        session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseWithNoSave, None)
        print("[OK] Closed all parts successfully using nested enum name!")
    except Exception as e:
        print(f"[FAIL] Nested enum failed: {e}")

if __name__ == "__main__":
    main()
