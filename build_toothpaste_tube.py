"""Build Toothpaste_Tube.prt NX part.

Usage:
    python build_toothpaste_tube.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nx_mcp import nx_bridge


def main():
    root = Path(__file__).parent

    journal = root / "src" / "nx_mcp" / "journals" / "create_toothpaste_tube.py"
    output = root / "Toothpaste_Tube.prt"
    print("=" * 60)
    print("Building Toothpaste_Tube.prt")
    print("  Journal: {}".format(journal))
    print("  Output:  {}".format(output))
    print("=" * 60)
    result = nx_bridge.run_journal(journal, str(output), timeout=600)
    print("Return code: {}".format(result.returncode))
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if not result.ok:
        print("[FAIL] Toothpaste_Tube.prt build failed")
        raise SystemExit(1)
    print("[OK] Toothpaste_Tube.prt saved: {}".format(output))
    print()
    print("=" * 60)
    print("Toothpaste Tube Part generated successfully!")
    print("  Toothpaste_Tube.prt: {}".format(output))
    print("=" * 60)


if __name__ == "__main__":
    main()
