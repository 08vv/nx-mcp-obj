import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nx_mcp import nx_bridge

def main():
    root = Path(__file__).parent.parent
    journal = root / "scratch" / "verify_pouch.py"
    print("=" * 60)
    print("Verifying Parametric Pouch Model")
    print("  Journal: {}".format(journal))
    print("=" * 60)
    result = nx_bridge.run_journal(journal, timeout=300)
    print("Return code: {}".format(result.returncode))
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if not result.ok:
        print("[FAIL] Parametric verification failed!")
        sys.exit(1)
    print("[OK] Verification passed successfully!")

if __name__ == "__main__":
    main()
