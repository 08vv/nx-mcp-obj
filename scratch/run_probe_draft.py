import sys
from pathlib import Path

# Add src to python path to use nx_bridge
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nx_mcp import nx_bridge

def main():
    root = Path(__file__).parent.parent
    journal = root / "scratch" / "probe_draft.py"
    output = root / "scratch" / "temp_draft_probe.prt"
    
    print(f"Running probe_draft.py via run_journal")
    result = nx_bridge.run_journal(journal, str(output), timeout=60)
    print(f"Return code: {result.returncode}")
    if result.stdout:
        print("--- STDOUT ---")
        print(result.stdout)
    if result.stderr:
        print("--- STDERR ---")
        print(result.stderr)

if __name__ == "__main__":
    main()
