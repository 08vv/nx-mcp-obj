"""Build Industrial_Profile_Model.prt NX part.

Usage:
    python build_profile.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nx_mcp import nx_bridge

def main():
    root = Path(__file__).parent

    journal = root / "src" / "nx_mcp" / "journals" / "create_profile.py"
    output = root / "Industrial_Profile_Model.prt"
    print("=" * 60)
    print("Building Industrial_Profile_Model.prt")
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
        print("[FAIL] Industrial_Profile_Model.prt build failed")
        raise SystemExit(1)
    import os
    print("[OK] Industrial_Profile_Model.prt saved: {}".format(output))
    print()
    print("=" * 60)
    print("Industrial Profile Part generated successfully!")
    print("  Industrial_Profile_Model.prt: {}".format(output))
    print("=" * 60)
    
    # Automatically open the generated .prt file in NX
    try:
        print("Opening {} in NX...".format(output.name))
        os.startfile(str(output))
    except Exception as e:
        print("[WARN] Could not open file automatically: {}".format(e))

if __name__ == "__main__":
    main()
