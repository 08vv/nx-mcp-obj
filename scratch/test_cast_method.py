import NXOpen
import sys

def main():
    print("ISurface class attributes:")
    try:
        print("  dir:", dir(NXOpen.ISurface))
    except Exception as e:
        print("  Error:", e)

if __name__ == "__main__":
    main()
