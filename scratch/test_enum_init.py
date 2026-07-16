import NXOpen
import sys

def main():
    EnumClass = NXOpen.GeometricUtilities.SimpleDraftSimpleDraftTypeMemberType
    print("EnumClass name:", EnumClass.__name__)
    
    # Let's try to instantiate it with different values
    for val in [0, 1, 2, "Simple", "None"]:
        try:
            inst = EnumClass(val)
            print(f"Instantiated successfully with {repr(val)}: {inst} (value={getattr(inst, 'value', 'no value')})")
        except Exception as e:
            print(f"Failed to instantiate with {repr(val)}: {e}")

if __name__ == "__main__":
    main()
