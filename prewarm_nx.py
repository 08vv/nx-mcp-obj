"""Start the NX GUI socket bridge before an MCP/Cline session."""

import atexit
import os
import subprocess
import sys
import time


os.environ.setdefault("UGII_BASE_DIR", r"C:\Program Files\Siemens\NX2206")
os.environ.setdefault("UGII_ROOT_DIR", r"C:\Program Files\Siemens\NX2206\NXBIN")
os.environ.setdefault("SPLM_LICENSE_SERVER", "28000@192.168.1.19")
os.environ["PATH"] = (
    f"{os.environ['UGII_ROOT_DIR']};{os.environ['UGII_BASE_DIR']}\\UGII;"
    f"{os.environ.get('PATH', '')}"
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.bridge import runner  # noqa: E402


# Leave the GUI process alive after this helper exits.
atexit.unregister(runner.NXBridgeProcess.reset)


def _kill_image(image_name: str) -> None:
    """Best-effort cleanup of a stale NX-related executable."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", image_name, "/T"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception as exc:
        print(f"[WARN] Could not clean up {image_name}: {exc}")


def _cleanup_stale_nx() -> None:
    """Remove processes/metadata only when no responsive bridge exists."""
    print("No live NX bridge found; removing stale NX processes and launch state...")
    _kill_image("run_journal.exe")
    _kill_image("ugraf.exe")
    if runner.CONFIG_PATH.exists():
        try:
            runner.CONFIG_PATH.unlink()
        except OSError as exc:
            print(f"[WARN] Could not remove stale config: {exc}")
    if runner.LOCK_PATH.exists():
        try:
            runner.LOCK_PATH.unlink()
        except OSError as exc:
            print(f"[WARN] Could not remove stale lock: {exc}")
    if runner.LAUNCH_LOCK_PATH.exists():
        try:
            runner.LAUNCH_LOCK_PATH.unlink()
        except OSError as exc:
            print(f"[WARN] Could not remove stale launch lock: {exc}")
    for _ in range(20):
        if runner._find_running_ugraf() is None:
            break
        time.sleep(0.5)
    time.sleep(1)


def _socket_is_live(port: int) -> bool:
    connection = runner.try_connect_socket(port)
    if connection is None:
        return False
    connection.close()
    return True


def prewarm() -> int:
    """Ensure a connectable interactive NX bridge is available."""
    port = runner.LIVE_PORT
    print(f"Checking Siemens NX bridge on 127.0.0.1:{port}...")
    if _socket_is_live(port):
        print(f"[OK] NX is already live and connectable on port {port}; no relaunch needed.")
        return 0

    _cleanup_stale_nx()
    print("Launching Siemens NX through runner.launch_interactive_nx()...")
    if runner.launch_interactive_nx(port=port):
        runner.NXBridgeProcess._ugraf_proc = None
        if hasattr(atexit, "_clear"):
            atexit._clear()
        print(f"[OK] Prewarm complete: NX is live and socket-connectable on port {port}.")
        return 0

    print(f"[FAIL] NX started but its bridge was not connectable on port {port}.")
    return 1


if __name__ == "__main__":
    raise SystemExit(prewarm())
