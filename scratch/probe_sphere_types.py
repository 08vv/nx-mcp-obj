import NXOpen
import sys

def main():
    print("SphereBuilderTypes members:")
    try:
        print("  dir:", dir(NXOpen.Features.SphereBuilderTypes))
    except Exception as e:
        print("  Error:", e)

if __name__ == "__main__":
    main()
