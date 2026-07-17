"""Build Sweet_Spicy_Sauce_Bottle.prt NX part.

Usage:
    python build_sauce_bottle.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nx_mcp import nx_bridge


def main():
    root = Path(__file__).parent

    journal = root / "src" / "nx_mcp" / "journals" / "create_sauce_bottle.py"
    output = root / "Sweet_Spicy_Sauce_Bottle.prt"
    print("=" * 60)
    print("Building Sweet_Spicy_Sauce_Bottle.prt")
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
        print("[FAIL] Sweet_Spicy_Sauce_Bottle.prt build failed")
        raise SystemExit(1)
    print("[OK] Sweet_Spicy_Sauce_Bottle.prt saved: {}".format(output))
    print()
    print("=" * 60)
    print("Sauce Bottle Part generated successfully!")
    print("  Sweet_Spicy_Sauce_Bottle.prt: {}".format(output))
    print("=" * 60)

    # Automatically open the generated .prt file in NX
    try:
        import os
        print("Opening {} in NX...".format(output.name))
        os.startfile(str(output))
    except Exception as e:
        print("[WARN] Could not open file automatically: {}".format(e))


if __name__ == "__main__":
    main()
