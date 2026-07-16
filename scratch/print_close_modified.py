import NXOpen
import sys

def main():
    print("BasePartCloseModified members:")
    try:
        print("  dir:", dir(NXOpen.BasePartCloseModified))
    except Exception as e:
        print("  Error:", e)
        
    print("\nBasePartCloseWholeTree members:")
    try:
        print("  dir:", dir(NXOpen.BasePartCloseWholeTree))
    except Exception as e:
        print("  Error:", e)

if __name__ == "__main__":
    main()
