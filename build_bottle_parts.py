"""Build both Bottle_Body.prt and Bottle_Cap.prt NX parts.

Usage:
    python build_bottle_parts.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nx_mcp import nx_bridge


def main():
    root = Path(__file__).parent

    # Build Bottle_Body.prt
    body_journal = root / "src" / "nx_mcp" / "journals" / "create_bottle_body.py"
    body_output = root / "Bottle_Body.prt"
    print("=" * 60)
    print("Building Bottle_Body.prt")
    print("  Journal: {}".format(body_journal))
    print("  Output:  {}".format(body_output))
    print("=" * 60)
    result = nx_bridge.run_journal(body_journal, str(body_output), timeout=600)
    print("Return code: {}".format(result.returncode))
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if not result.ok:
        print("[FAIL] Bottle_Body.prt build failed")
        raise SystemExit(1)
    print("[OK] Bottle_Body.prt saved: {}".format(body_output))
    print()

    # Build Bottle_Cap.prt
    cap_journal = root / "src" / "nx_mcp" / "journals" / "create_bottle_cap.py"
    cap_output = root / "Bottle_Cap.prt"
    print("=" * 60)
    print("Building Bottle_Cap.prt")
    print("  Journal: {}".format(cap_journal))
    print("  Output:  {}".format(cap_output))
    print("=" * 60)
    result = nx_bridge.run_journal(cap_journal, str(cap_output), timeout=600)
    print("Return code: {}".format(result.returncode))
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if not result.ok:
        print("[FAIL] Bottle_Cap.prt build failed")
        raise SystemExit(1)
    print("[OK] Bottle_Cap.prt saved: {}".format(cap_output))
    print()

    print("=" * 60)
    print("Both parts generated successfully!")
    print("  Bottle_Body.prt: {}".format(body_output))
    print("  Bottle_Cap.prt:  {}".format(cap_output))
    print("=" * 60)

    # Automatically open the generated .prt files in NX
    try:
        import os
        print("Opening generated parts in NX...")
        os.startfile(str(body_output))
        os.startfile(str(cap_output))
    except Exception as e:
        print("[WARN] Could not open files automatically: {}".format(e))


if __name__ == "__main__":
    main()
