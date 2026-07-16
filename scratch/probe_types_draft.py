import NXOpen
import sys

def main():
    print("MultiDraft members:")
    try:
        print("  dir:", dir(NXOpen.GeometricUtilities.MultiDraft))
    except Exception as e:
        print("  Error dir MultiDraft:", e)
        
    print("\nSimpleDraftSimpleDraftTypeMemberType members:")
    try:
        print("  dir:", dir(NXOpen.GeometricUtilities.SimpleDraftSimpleDraftTypeMemberType))
    except Exception as e:
        print("  Error dir SimpleDraftSimpleDraftTypeMemberType:", e)

if __name__ == "__main__":
    main()
