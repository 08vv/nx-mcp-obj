"""Build Compact_Model_Elle18.prt NX part.

Usage:
    python build_compact_elle18.py
"""

import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from nx_mcp import nx_bridge

def main():
    root = Path(__file__).parent

    journal = root / "src" / "nx_mcp" / "journals" / "create_compact_elle18.py"
    output = root / "Compact_Model_Elle18.prt"
    print("=" * 60)
    print("Building Compact_Model_Elle18.prt")
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
        print("[FAIL] Compact_Model_Elle18.prt build failed")
        raise SystemExit(1)
    print("[OK] Compact_Model_Elle18.prt saved: {}".format(output))
    print()
    print("=" * 60)
    print("Elle 18 Compact Part generated successfully!")
    print("  Compact_Model_Elle18.prt: {}".format(output))
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
