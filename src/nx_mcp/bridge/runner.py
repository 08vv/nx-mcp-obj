import atexit
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from importlib import resources
from pathlib import Path


def get_root_dir():
    env_root = os.environ.get("NX_MCP_ROOT")
    if env_root:
        return Path(env_root)
    try:
        file_path = Path(__file__).resolve()
        for parent in file_path.parents:
            if (parent / ".git").exists() or parent.name == "nx-mcp":
                return parent
        return file_path.parents[3]
    except Exception as e:
        sys.stderr.write(f"[WARN] get_root_dir fallback to cwd: {e}\n")
        return Path(os.getcwd())


ROOT_DIR = get_root_dir()
LIVE_PORT = 43210
CONFIG_PATH = ROOT_DIR / "live_bridge_config.json"
LOCK_PATH = ROOT_DIR / "bridge.lock"
LAUNCH_LOCK_PATH = ROOT_DIR / "bridge.launching.lock"
DEFAULT_SOCKET_TIMEOUT = int(os.environ.get("NX_MCP_SOCKET_TIMEOUT", "60"))
NX_PREWARM_REQUIRED_ERROR = (
    "NX is not running and could not be auto-launched in time. Do not attempt "
    "run_nx_journal_code, do not import NXOpen manually - instead, tell the user "
    "to run 'python prewarm_nx.py' first and wait for it to complete, then retry."
)


def _update_watcher_files(filepath):
    try:
        abs_path = str(Path(filepath).resolve())
        root = ROOT_DIR
        if root.exists():
            latest_txt = root / "latest_nx_result.txt"
            latest_txt.write_text(abs_path, encoding="utf-8")

            # Resolve ugs_router path dynamically
            ugs_router_path = None
            base_dir = os.environ.get("UGII_BASE_DIR")
            if base_dir:
                base_path = Path(base_dir)
                candidates = [
                    base_path / "NXBIN" / "ugs_router.exe",
                    base_path / "UGII" / "ugs_router.exe",
                ]
                ugs_router_path = next((c for c in candidates if c.exists()), None)
            if not ugs_router_path:
                ugs_router_path = Path(r"C:\Program Files\Siemens\NX2206\NXBIN\ugs_router.exe")

            cmd_path = root / "open_current_nx_result.cmd"
            cmd_path.write_text(
                f'@echo off\nstart "" "{ugs_router_path}" -ug -use_file_dir "{abs_path}"\n',
                encoding="utf-8"
            )
            vbs_path = root / "open_latest_nx_result.vbs"
            vbs_path.write_text(
                f'Set shell = CreateObject("WScript.Shell")\nshell.Run """{ugs_router_path}"" -ug -use_file_dir ""{abs_path}""", 0, False\n',
                encoding="utf-8"
            )
    except Exception as e:
        sys.stderr.write(f"[WARN] _update_watcher_files failed: {e}\n")


def _bridge_script_path():
    return Path(resources.files("nx_mcp.bridge").joinpath("nx_bridge.py"))


def verify_nx_environment():
    base_dir = os.environ.get("UGII_BASE_DIR")
    if not base_dir:
        raise RuntimeError(
            "Environment variable UGII_BASE_DIR is not set. Please set it to the "
            "Siemens NX installation directory, such as C:\\Program Files\\Siemens\\NX2206."
        )

    base_path = Path(base_dir)
    missing = []

    # Check run_journal.exe
    run_journal_candidates = [
        base_path / "NXBIN" / "run_journal.exe",
        base_path / "UGII" / "run_journal.exe",
    ]
    run_journal_path = next((c for c in run_journal_candidates if c.exists()), None)
    if not run_journal_path:
        missing.append("run_journal.exe")

    # Check ugraf.exe
    ugraf_candidates = [
        base_path / "NXBIN" / "ugraf.exe",
        base_path / "UGII" / "ugraf.exe",
    ]
    ugraf_path = next((c for c in ugraf_candidates if c.exists()), None)
    if not ugraf_path:
        missing.append("ugraf.exe")

    # Check ugs_router.exe
    ugs_router_candidates = [
        base_path / "NXBIN" / "ugs_router.exe",
        base_path / "UGII" / "ugs_router.exe",
    ]
    ugs_router_path = next((c for c in ugs_router_candidates if c.exists()), None)
    if not ugs_router_path:
        missing.append("ugs_router.exe")

    if missing:
        raise RuntimeError(
            f"Missing required Siemens NX executables under {base_dir}: {', '.join(missing)}"
        )

    return run_journal_path, ugraf_path, ugs_router_path


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                text=True,
                creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            return str(pid) in output
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


def _find_running_ugraf() -> int | None:
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(
                ["tasklist", "/FI", "IMAGENAME eq ugraf.exe", "/FO", "CSV", "/NH"],
                text=True,
                creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            for line in output.strip().splitlines():
                parts = [p.strip('"') for p in line.split(",")]
                if len(parts) >= 2 and parts[0].lower() == "ugraf.exe":
                    try:
                        return int(parts[1])
                    except ValueError:
                        pass
        except Exception:
            pass
    return None


def _acquire_launch_lock(timeout=60) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            fd = os.open(str(LAUNCH_LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if LAUNCH_LOCK_PATH.exists():
                    mtime = LAUNCH_LOCK_PATH.stat().st_mtime
                    if time.time() - mtime > 120:
                        LAUNCH_LOCK_PATH.unlink(missing_ok=True)
            except Exception:
                pass
            time.sleep(0.2)
        except Exception:
            return False
    return False


def _release_launch_lock():
    try:
        if LAUNCH_LOCK_PATH.exists():
            LAUNCH_LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def try_connect_socket(port=LIVE_PORT):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(("127.0.0.1", port))
        return s
    except Exception:
        return None


def _wait_for_socket(port=LIVE_PORT, timeout=12) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        s = try_connect_socket(port)
        if s:
            s.close()
            return True
        time.sleep(0.5)
    s = try_connect_socket(port)
    if s:
        s.close()
        return True
    return False


def launch_interactive_nx(part_path=None, port=LIVE_PORT):
    timeout = int(os.environ.get("NX_MCP_LAUNCH_TIMEOUT", "180"))

    # 1. Quick TCP pre-check
    s = try_connect_socket(port)
    if s:
        s.close()
        return True

    # 2. OS-level check: is ugraf already running?
    existing_pid = _find_running_ugraf()
    if existing_pid is not None:
        sys.stderr.write(
            f"[INFO] ugraf.exe already running (PID {existing_pid}). "
            f"Waiting for socket instead of launching a new instance.\n"
        )
        return _wait_for_socket(port, timeout)

    # 3. Check lock / pidfile mechanism
    if LOCK_PATH.exists():
        try:
            pid_str = LOCK_PATH.read_text(encoding="utf-8").strip()
            if pid_str.isdigit():
                pid = int(pid_str)
                if _is_pid_alive(pid):
                    sys.stderr.write(
                        f"[INFO] Existing bridge process with PID {pid} is running. Reusing process.\n"
                    )
                    return _wait_for_socket(port, timeout)
        except Exception as e:
            sys.stderr.write(f"[WARN] Error reading bridge lock file: {e}\n")
        try:
            LOCK_PATH.unlink()
        except Exception:
            pass

    # 4. Acquire cross-process launch lock
    lock_acquired = _acquire_launch_lock(timeout=min(timeout, 30))
    if not lock_acquired:
        sys.stderr.write(
            "[WARN] Could not acquire launch lock — another launch may be in progress. "
            "Waiting for socket...\n"
        )
        return _wait_for_socket(port, timeout)

    try:
        # 5. Re-check after lock
        s = try_connect_socket(port)
        if s:
            s.close()
            return True

        existing_pid = _find_running_ugraf()
        if existing_pid is not None:
            sys.stderr.write(
                f"[INFO] ugraf.exe appeared (PID {existing_pid}) while waiting for lock. "
                f"Waiting for socket.\n"
            )
            return _wait_for_socket(port, timeout)

        # 6. Actually launch ugraf.exe
        run_journal_path, ugraf_path, ugs_router_path = verify_nx_environment()

        config = {
            "part_path": str(Path(part_path).resolve()) if part_path else "",
            "port": port,
        }
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(config, f)

        bridge_script = _bridge_script_path()
        popen_kwargs = {}
        if sys.platform == "win32":
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            popen_kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
            popen_kwargs["close_fds"] = True

        ugraf_proc = subprocess.Popen(
            [str(ugraf_path), f"-auto={bridge_script}"],
            **popen_kwargs
        )
        NXBridgeProcess._ugraf_proc = ugraf_proc

        try:
            LOCK_PATH.write_text(str(ugraf_proc.pid), encoding="utf-8")
        except Exception as e:
            sys.stderr.write(f"[WARN] Failed to write bridge lock file: {e}\n")

        # 7. Poll for socket connection
        if _wait_for_socket(port, timeout):
            return True

        # 8. Timed out -> kill orphan
        sys.stderr.write(
            f"[ERROR] NX launch timed out after {timeout}s. "
            f"Killing orphan ugraf.exe (PID {ugraf_proc.pid}).\n"
        )
        try:
            ugraf_proc.kill()
            ugraf_proc.wait(timeout=10)
        except Exception as e:
            sys.stderr.write(f"[WARN] Failed to kill orphan ugraf.exe: {e}\n")
        NXBridgeProcess._ugraf_proc = None
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except Exception:
            pass
        return False
    finally:
        _release_launch_lock()


class NXBridgeProcess:
    _proc = None
    _ugraf_proc = None
    _lock = threading.Lock()

    @classmethod
    def reset(cls, stop_ugraf=False):
        with cls._lock:
            if stop_ugraf and LOCK_PATH.exists():
                try:
                    pid_str = LOCK_PATH.read_text(encoding="utf-8").strip()
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        if _is_pid_alive(pid):
                            try:
                                if sys.platform == "win32":
                                    subprocess.run(
                                        ["taskkill", "/F", "/PID", str(pid)],
                                        capture_output=True,
                                    )
                                else:
                                    os.kill(pid, 9)
                            except Exception:
                                pass
                except Exception:
                    pass

            if LOCK_PATH.exists():
                try:
                    LOCK_PATH.unlink()
                except Exception:
                    pass

            if stop_ugraf and CONFIG_PATH.exists():
                try:
                    CONFIG_PATH.unlink()
                except Exception:
                    pass

            proc = cls._proc
            cls._proc = None
            if proc is not None and proc.poll() is None:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                try:
                    proc.terminate()
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()

            if stop_ugraf:
                ugraf = cls._ugraf_proc
                cls._ugraf_proc = None
                if ugraf is not None and ugraf.poll() is None:
                    try:
                        ugraf.terminate()
                        ugraf.wait(timeout=10)
                    except Exception:
                        try:
                            ugraf.kill()
                        except Exception:
                            pass

    @classmethod
    def _call_socket(cls, s, tool, args):
        try:
            s.settimeout(DEFAULT_SOCKET_TIMEOUT)
            payload = json.dumps({"tool": tool, "args": args}) + "\n"
            s.sendall(payload.encode("utf-8"))
            buffer = ""
            while "\n" not in buffer:
                chunk = s.recv(4096).decode("utf-8")
                if not chunk:
                    break
                buffer += chunk

            if "\n" in buffer:
                line, _ = buffer.split("\n", 1)
                res = json.loads(line)
                if res.get("ok"):
                    p = (
                        args.get("filename")
                        if tool == "create_part"
                        else (args.get("filepath") if tool == "open_part" else res.get("filepath"))
                    )
                    if p:
                        _update_watcher_files(p)
                return res
            return {"ok": False, "error": "NX bridge socket closed without sending a response"}
        except socket.timeout:
            return {
                "ok": False,
                "error": "NX bridge socket read timed out - bridge may be dead, try reset_nx_bridge",
            }
        except Exception as e:
            return {"ok": False, "error": f"Socket communication error: {e}"}
        finally:
            try:
                s.close()
            except Exception:
                pass

    @classmethod
    def call(cls, tool, args):
        verify_nx_environment()

        part_path = None
        if tool == "create_part":
            part_path = args.get("filename")
        elif tool == "open_part":
            part_path = args.get("filepath")

        with cls._lock:
            # 1. Try connect
            s = try_connect_socket(LIVE_PORT)

            # 2. Check running ugraf
            if s is None:
                existing_pid = _find_running_ugraf()
                if existing_pid is not None:
                    sys.stderr.write(
                        f"[INFO] Startup guard: ugraf.exe is already running (PID {existing_pid}). "
                        f"Waiting for socket...\n"
                    )
                    timeout = int(os.environ.get("NX_MCP_LAUNCH_TIMEOUT", "180"))
                    if _wait_for_socket(LIVE_PORT, timeout):
                        s = try_connect_socket(LIVE_PORT)

            # 3. Launch interactive NX if needed
            if s is None:
                launched = launch_interactive_nx(part_path, LIVE_PORT)
                if launched:
                    s = try_connect_socket(LIVE_PORT)

            # 4. Check if ugraf is still booting
            if s is None and cls._ugraf_proc is not None and cls._ugraf_proc.poll() is None:
                timeout = int(os.environ.get("NX_MCP_LAUNCH_TIMEOUT", "180"))
                start = time.time()
                while time.time() - start < timeout:
                    if cls._ugraf_proc.poll() is not None:
                        break
                    s = try_connect_socket(LIVE_PORT)
                    if s is not None:
                        break
                    time.sleep(0.5)

            # 5. Late socket check
            if s is None:
                s = try_connect_socket(LIVE_PORT)
                if s is not None:
                    sys.stderr.write(
                        "[INFO] NX bridge socket detected after launch wait. Reusing socket.\n"
                    )

            if s is not None:
                return cls._call_socket(s, tool, args)

            return {"ok": False, "error": NX_PREWARM_REQUIRED_ERROR}


def call_nx(tool, args):
    return NXBridgeProcess.call(tool, args)


def reset_nx_bridge(stop_ugraf=False):
    NXBridgeProcess.reset(stop_ugraf=stop_ugraf)


def run_tool(tool, **args):
    return call_nx(tool, args)


atexit.register(NXBridgeProcess.reset)
