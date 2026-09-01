"""Build Sunlight_Detergent_Bottle.prt NX part.

Usage:
    python build_bottle_parts.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nx_mcp import nx_bridge


def main():
    root = Path(__file__).parent

    journal = root / "create_bottle_parts.py"
    output = root / "Sunlight_Detergent_Bottle.prt"
    print("=" * 60)
    print("Building Sunlight_Detergent_Bottle.prt")
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
        print("[FAIL] Sunlight_Detergent_Bottle.prt build failed")
        raise SystemExit(1)
    print("[OK] Sunlight_Detergent_Bottle.prt saved: {}".format(output))
    print()
    print("=" * 60)
    print("Part generated successfully!")
    print("  Sunlight_Detergent_Bottle.prt: {}".format(output))
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
