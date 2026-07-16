"""Build the EVEROMINO parametric pump bottle from the reference image."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nx_mcp import nx_bridge


def main():
    root = Path(__file__).parent
    journal = root / "src" / "nx_mcp" / "journals" / "create_everomino_pump_bottle.py"
    output = root / "everomino_pump_bottle.prt"

    print(f"Running journal: {journal}")
    result = nx_bridge.run_journal(journal, str(output), timeout=600)
    print(f"Return code: {result.returncode}")
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if not result.ok:
        raise SystemExit(1)
    print(f"Part saved: {output}")


if __name__ == "__main__":
    main()
