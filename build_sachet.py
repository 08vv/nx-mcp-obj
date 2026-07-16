"""Build Sachet_Model.prt NX part.

Usage:
    python build_sachet.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nx_mcp import nx_bridge

def main():
    root = Path(__file__).parent

    journal = root / "src" / "nx_mcp" / "journals" / "create_sachet.py"
    output = root / "Sachet_Model.prt"
    print("=" * 60)
    print("Building Sachet_Model.prt")
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
        print("[FAIL] Sachet_Model.prt build failed")
        raise SystemExit(1)
    import os
    print("[OK] Sachet_Model.prt saved: {}".format(output))
    print()
    print("=" * 60)
    print("Shampoo Sachet generated successfully!")
    print("  Sachet_Model.prt: {}".format(output))
    print("=" * 60)
    
    # Automatically open the generated .prt file in NX
    try:
        print("Opening {} in NX...".format(output.name))
        os.startfile(str(output))
    except Exception as e:
        print("[WARN] Could not open file automatically: {}".format(e))

if __name__ == "__main__":
    main()
