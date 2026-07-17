import sys
from pathlib import Path

# Add src folder to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nx_mcp import nx_bridge

def main():
    root = Path(__file__).parent.parent
    journal = root / "scratch" / "verify_compact_elle18.py"
    print("============================================================")
    print("Running verify_compact.py via NX Bridge")
    print("============================================================")
    result = nx_bridge.run_journal(journal, timeout=600)
    print("Return code: {}".format(result.returncode))
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if not result.ok:
        print("[FAIL] Verification journal failed")
        sys.exit(1)
    print("[OK] Verification journal completed successfully")

if __name__ == "__main__":
    main()
