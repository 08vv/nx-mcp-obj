"""Build Compact_Model.prt NX part.

Usage:
    python build_compact.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nx_mcp import nx_bridge

def main():
    root = Path(__file__).parent

    journal = root / "src" / "nx_mcp" / "journals" / "create_compact.py"
    output = root / "Compact_Model.prt"
    print("=" * 60)
    print("Building Compact_Model.prt")
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
        print("[FAIL] Compact_Model.prt build failed")
        raise SystemExit(1)
    print("[OK] Compact_Model.prt saved: {}".format(output))
    print()
    print("=" * 60)
    print("Cosmetic Compact Part generated successfully!")
    print("  Compact_Model.prt: {}".format(output))
    print("=" * 60)

if __name__ == "__main__":
    main()
