"""Build Liquid_Lip_Colour.prt NX part.

Usage:
    python build_lip_colour.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nx_mcp import nx_bridge

def main():
    root = Path(__file__).parent

    journal = root / "src" / "nx_mcp" / "journals" / "create_lip_colour.py"
    output = root / "Liquid_Lip_Colour.prt"
    print("=" * 60)
    print("Building Liquid_Lip_Colour.prt")
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
        print("[FAIL] Liquid_Lip_Colour.prt build failed")
        raise SystemExit(1)
    import os
    print("[OK] Liquid_Lip_Colour.prt saved: {}".format(output))
    print()
    print("=" * 60)
    print("Liquid Lip Colour container generated successfully!")
    print("  Liquid_Lip_Colour.prt: {}".format(output))
    print("=" * 60)
    
    # Automatically open the generated .prt file in NX
    try:
        print("Opening {} in NX...".format(output.name))
        os.startfile(str(output))
    except Exception as e:
        print("[WARN] Could not open file automatically: {}".format(e))

if __name__ == "__main__":
    main()
