import os
import socket
import sys
from pathlib import Path
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nx_mcp.bridge import runner


def test_tcp_precheck_reuses_existing_bridge(monkeypatch):
    """If try_connect_socket succeeds, launch_interactive_nx reuses existing bridge without Popen."""
    class DummySocket:
        def close(self):
            pass

    monkeypatch.setattr(runner, "try_connect_socket", lambda port=runner.LIVE_PORT: DummySocket())
    
    popen_called = False
    def fake_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise RuntimeError("Should not be called")

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    res = runner.launch_interactive_nx(part_path="test.prt")
    assert res is True
    assert not popen_called


def test_pid_lockfile_prevents_duplicate_launch(monkeypatch, tmp_path):
    """If bridge.lock exists and PID is alive, launch_interactive_nx does not spawn a new process."""
    lock_file = tmp_path / "bridge.lock"
    lock_file.write_text("12345", encoding="utf-8")
    
    monkeypatch.setattr(runner, "LOCK_PATH", lock_file)
    # Pre-check fails
    monkeypatch.setattr(runner, "try_connect_socket", lambda port=runner.LIVE_PORT: None)
    monkeypatch.setattr(runner, "_is_pid_alive", lambda pid: True if pid == 12345 else False)
    monkeypatch.setattr(runner, "_find_running_ugraf", lambda: None)
    monkeypatch.setattr(runner.time, "sleep", lambda secs: None)
    monkeypatch.setenv("NX_MCP_LAUNCH_TIMEOUT", "0")

    popen_called = False
    def fake_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    res = runner.launch_interactive_nx(part_path="test.prt")
    assert res is False
    assert not popen_called
    assert lock_file.exists()


def test_pid_lockfile_stale_cleanup(monkeypatch, tmp_path):
    """If bridge.lock has a dead PID, it is unlinked and process launch proceeds."""
    lock_file = tmp_path / "bridge.lock"
    config_file = tmp_path / "live_bridge_config.json"
    lock_file.write_text("99999", encoding="utf-8")

    monkeypatch.setattr(runner, "LOCK_PATH", lock_file)
    monkeypatch.setattr(runner, "CONFIG_PATH", config_file)
    monkeypatch.setattr(runner, "_is_pid_alive", lambda pid: False)
    monkeypatch.setattr(runner, "_find_running_ugraf", lambda: None)
    monkeypatch.setattr(runner, "_acquire_launch_lock", lambda timeout=30: True)
    monkeypatch.setattr(runner, "_release_launch_lock", lambda: None)
    monkeypatch.setattr(runner, "verify_nx_environment", lambda: ("rj", "ugraf", "ugs"))
    monkeypatch.setattr(runner.time, "sleep", lambda secs: None)

    popen_called = False

    class FakeProc:
        pid = 54321

        def poll(self):
            return None
        def kill(self):
            pass
        def terminate(self):
            pass
        def wait(self, timeout=None):
            pass

    class DummySocket:
        def close(self):
            pass

    # try_connect_socket: fail initially, succeed after Popen is called (simulating socket coming up)
    conn_calls = 0
    def fake_connect(port=runner.LIVE_PORT):
        nonlocal conn_calls
        conn_calls += 1
        # Calls 1-3: pre-check, re-check after lock, first poll → fail
        # Call 4+: socket comes up
        if conn_calls >= 4:
            return DummySocket()
        return None

    monkeypatch.setattr(runner, "try_connect_socket", fake_connect)
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **kw: FakeProc())

    try:
        res = runner.launch_interactive_nx(part_path="test.prt")
        assert res is True  # Socket connected successfully
        assert lock_file.exists()
        assert lock_file.read_text(encoding="utf-8") == "54321"
    finally:
        runner.NXBridgeProcess._ugraf_proc = None


def test_reset_nx_bridge_cleans_lockfile(tmp_path, monkeypatch):
    """NXBridgeProcess.reset unlinks bridge.lock."""
    lock_file = tmp_path / "bridge.lock"
    config_file = tmp_path / "live_bridge_config.json"
    lock_file.write_text("12345", encoding="utf-8")

    monkeypatch.setattr(runner, "LOCK_PATH", lock_file)
    monkeypatch.setattr(runner, "CONFIG_PATH", config_file)
    monkeypatch.setattr(runner, "_is_pid_alive", lambda pid: False)

    runner.reset_nx_bridge()
    assert not lock_file.exists()


def test_socket_read_timeout_error(monkeypatch):
    """NXBridgeProcess.call returns specific timeout error message when socket.recv times out."""
    class TimingOutSocket:
        def settimeout(self, timeout):
            pass
        def sendall(self, data):
            pass
        def recv(self, bufsize):
            raise socket.timeout("timed out")
        def close(self):
            pass

    monkeypatch.setattr(runner, "verify_nx_environment", lambda: ("rj", "ugraf", "ugs"))
    monkeypatch.setattr(runner, "try_connect_socket", lambda port=runner.LIVE_PORT: TimingOutSocket())

    res = runner.NXBridgeProcess.call("get_active_part", {})
    assert res["ok"] is False
    assert "NX bridge socket read timed out - bridge may be dead, try reset_nx_bridge" in res["error"]


def test_launch_interactive_nx_configurable_timeout(monkeypatch, tmp_path):
    """launch_interactive_nx respects NX_MCP_LAUNCH_TIMEOUT env var."""
    lock_file = tmp_path / "bridge.lock"
    config_file = tmp_path / "live_bridge_config.json"
    monkeypatch.setattr(runner, "LOCK_PATH", lock_file)
    monkeypatch.setattr(runner, "CONFIG_PATH", config_file)
    monkeypatch.setattr(runner, "try_connect_socket", lambda port=runner.LIVE_PORT: None)
    monkeypatch.setattr(runner, "_find_running_ugraf", lambda: None)
    monkeypatch.setattr(runner, "_acquire_launch_lock", lambda timeout=30: True)
    monkeypatch.setattr(runner, "_release_launch_lock", lambda: None)
    monkeypatch.setattr(runner, "verify_nx_environment", lambda: ("rj", "ugraf", "ugs"))
    monkeypatch.setenv("NX_MCP_LAUNCH_TIMEOUT", "1")

    sleep_count = 0
    def fake_sleep(secs):
        nonlocal sleep_count
        sleep_count += 1

    monkeypatch.setattr(runner.time, "sleep", fake_sleep)

    class FakeProc:
        pid = 1111
        def poll(self): return None
        def kill(self): pass
        def terminate(self): pass
        def wait(self, timeout=None): pass

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **kw: FakeProc())

    start_times = [0.0, 0.2, 0.5, 1.2]
    monkeypatch.setattr(runner.time, "time", lambda: start_times.pop(0) if start_times else 2.0)

    try:
        res = runner.launch_interactive_nx(part_path="test.prt")
        assert res is False
        assert sleep_count >= 2
    finally:
        runner.NXBridgeProcess._ugraf_proc = None


def test_call_waits_for_ugraf_proc_startup(monkeypatch):
    """If ugraf.exe is still alive, call() polls socket before falling back."""
    class DummySocket:
        def settimeout(self, timeout):
            pass
        def sendall(self, data):
            pass
        def recv(self, bufsize):
            return b'{"ok": true}\n'
        def close(self):
            pass

    class FakeUgrafProc:
        def poll(self):
            return None

    conn_attempts = 0
    def fake_connect(port=runner.LIVE_PORT):
        nonlocal conn_attempts
        conn_attempts += 1
        # First 2 checks fail, 3rd succeeds
        if conn_attempts >= 3:
            return DummySocket()
        return None

    monkeypatch.setattr(runner, "verify_nx_environment", lambda: ("rj", "ugraf", "ugs"))
    monkeypatch.setattr(runner, "launch_interactive_nx", lambda part_path=None, port=runner.LIVE_PORT: False)
    monkeypatch.setattr(runner, "try_connect_socket", fake_connect)
    monkeypatch.setattr(runner.time, "sleep", lambda secs: None)

    runner.NXBridgeProcess._ugraf_proc = FakeUgrafProc()
    try:
        res = runner.NXBridgeProcess.call("get_active_part", {})
        assert res == {"ok": True}
        assert conn_attempts >= 3
    finally:
        runner.NXBridgeProcess._ugraf_proc = None


def test_call_late_socket_check_reuses_socket(monkeypatch, capsys):
    """NXBridgeProcess.call reuses a socket that becomes available after launch."""
    monkeypatch.setattr(runner, "verify_nx_environment", lambda: ("rj", "ugraf", "ugs"))
    monkeypatch.setattr(runner, "_find_running_ugraf", lambda: None)
    monkeypatch.setattr(runner, "launch_interactive_nx", lambda part_path=None, port=runner.LIVE_PORT: False)

    # Test safety net catching late socket connection
    safety_socket_used = False
    class SafetySocket:
        def settimeout(self, timeout):
            pass
        def sendall(self, data):
            pass
        def recv(self, bufsize):
            nonlocal safety_socket_used
            safety_socket_used = True
            return b'{"ok": true}\n'
        def close(self):
            pass

    conn_calls = 0
    def fake_connect(port=runner.LIVE_PORT):
        nonlocal conn_calls
        conn_calls += 1
        # Return socket on second call (safety net check)
        if conn_calls == 2:
            return SafetySocket()
        return None

    monkeypatch.setattr(runner, "try_connect_socket", fake_connect)
    res = runner.NXBridgeProcess.call("get_active_part", {})
    assert res == {"ok": True}
    assert safety_socket_used is True

    captured = capsys.readouterr()
    assert "[INFO] NX bridge socket detected after launch wait. Reusing socket." in captured.err


def test_call_returns_prewarm_instruction_when_launch_fails(monkeypatch):
    """A failed launch must fail fast instead of trying unreliable batch mode."""
    monkeypatch.setattr(runner, "verify_nx_environment", lambda: ("rj", "ugraf", "ugs"))
    monkeypatch.setattr(runner, "_find_running_ugraf", lambda: None)
    monkeypatch.setattr(runner, "launch_interactive_nx", lambda part_path=None, port=runner.LIVE_PORT: False)
    monkeypatch.setattr(runner, "try_connect_socket", lambda port=runner.LIVE_PORT: None)

    res = runner.NXBridgeProcess.call("get_active_part", {})
    assert res == {"ok": False, "error": runner.NX_PREWARM_REQUIRED_ERROR}


def test_os_level_ugraf_detection_prevents_duplicate_launch(monkeypatch):
    """If _find_running_ugraf finds a running ugraf.exe, launch_interactive_nx does NOT launch a new one."""
    # Pre-check fails (no socket)
    monkeypatch.setattr(runner, "try_connect_socket", lambda port=runner.LIVE_PORT: None)
    # OS-level check finds a running ugraf
    monkeypatch.setattr(runner, "_find_running_ugraf", lambda: 77777)
    monkeypatch.setattr(runner.time, "sleep", lambda secs: None)
    monkeypatch.setenv("NX_MCP_LAUNCH_TIMEOUT", "0")

    popen_called = False
    def fake_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise RuntimeError("Should not be called")

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    res = runner.launch_interactive_nx(part_path="test.prt")
    assert res is False  # socket never came up, but...
    assert not popen_called  # ...no new ugraf.exe was spawned


def test_failed_launch_kills_orphan_process(monkeypatch, tmp_path):
    """When socket polling times out, the spawned ugraf.exe is killed and lock file removed."""
    lock_file = tmp_path / "bridge.lock"
    config_file = tmp_path / "live_bridge_config.json"

    monkeypatch.setattr(runner, "LOCK_PATH", lock_file)
    monkeypatch.setattr(runner, "CONFIG_PATH", config_file)
    monkeypatch.setattr(runner, "try_connect_socket", lambda port=runner.LIVE_PORT: None)
    monkeypatch.setattr(runner, "_find_running_ugraf", lambda: None)
    monkeypatch.setattr(runner, "_acquire_launch_lock", lambda timeout=30: True)
    monkeypatch.setattr(runner, "_release_launch_lock", lambda: None)
    monkeypatch.setattr(runner, "verify_nx_environment", lambda: ("rj", "ugraf", "ugs"))
    monkeypatch.setenv("NX_MCP_LAUNCH_TIMEOUT", "0")
    monkeypatch.setattr(runner.time, "sleep", lambda secs: None)

    killed = False

    class FakeProc:
        pid = 88888
        def poll(self): return None
        def kill(self):
            nonlocal killed
            killed = True
        def terminate(self): pass
        def wait(self, timeout=None): pass

    # time.time() returns values that immediately exceed the 0-second timeout
    fake_time = [0.0, 1.0]
    monkeypatch.setattr(runner.time, "time", lambda: fake_time.pop(0) if fake_time else 2.0)
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **kw: FakeProc())

    try:
        res = runner.launch_interactive_nx(part_path="test.prt")
        assert res is False
        assert killed, "Orphan ugraf.exe should have been killed on timeout"
        assert runner.NXBridgeProcess._ugraf_proc is None, "ugraf_proc should be cleared"
        # Lock file should be cleaned up
        assert not lock_file.exists(), "Lock file should be removed after failed launch"
    finally:
        runner.NXBridgeProcess._ugraf_proc = None


def test_concurrent_launch_lock_prevents_second_launch(monkeypatch, tmp_path):
    """When launch lock cannot be acquired, launch_interactive_nx waits for socket instead of launching."""
    lock_file = tmp_path / "bridge.lock"
    config_file = tmp_path / "live_bridge_config.json"

    monkeypatch.setattr(runner, "LOCK_PATH", lock_file)
    monkeypatch.setattr(runner, "CONFIG_PATH", config_file)
    monkeypatch.setattr(runner, "try_connect_socket", lambda port=runner.LIVE_PORT: None)
    monkeypatch.setattr(runner, "_find_running_ugraf", lambda: None)
    # Simulate lock already held by another process
    monkeypatch.setattr(runner, "_acquire_launch_lock", lambda timeout=30: False)
    monkeypatch.setattr(runner, "_release_launch_lock", lambda: None)
    monkeypatch.setattr(runner.time, "sleep", lambda secs: None)
    monkeypatch.setenv("NX_MCP_LAUNCH_TIMEOUT", "0")

    popen_called = False
    def fake_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise RuntimeError("Should not be called")

    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    res = runner.launch_interactive_nx(part_path="test.prt")
    assert res is False  # socket didn't come up
    assert not popen_called  # but no duplicate ugraf.exe was spawned


def test_call_startup_guard_detects_running_ugraf(monkeypatch):
    """NXBridgeProcess.call() detects OS-level ugraf.exe before attempting to launch a new one."""
    class DummySocket:
        def settimeout(self, timeout): pass
        def sendall(self, data): pass
        def recv(self, bufsize): return b'{"ok": true}\n'
        def close(self): pass

    conn_calls = 0
    def fake_connect(port=runner.LIVE_PORT):
        nonlocal conn_calls
        conn_calls += 1
        # First call (initial check): fail. Later calls: succeed (socket came up).
        if conn_calls >= 2:
            return DummySocket()
        return None

    monkeypatch.setattr(runner, "verify_nx_environment", lambda: ("rj", "ugraf", "ugs"))
    monkeypatch.setattr(runner, "try_connect_socket", fake_connect)
    # OS-level check finds ugraf running
    monkeypatch.setattr(runner, "_find_running_ugraf", lambda: 99999)
    monkeypatch.setattr(runner.time, "sleep", lambda secs: None)

    launch_called = False
    def fake_launch(part_path=None, port=runner.LIVE_PORT):
        nonlocal launch_called
        launch_called = True
        return False

    monkeypatch.setattr(runner, "launch_interactive_nx", fake_launch)

    res = runner.NXBridgeProcess.call("get_active_part", {})
    assert res == {"ok": True}
    assert not launch_called, "launch_interactive_nx should NOT be called when ugraf is already running"


def test_handle_line_rollback_on_failure(monkeypatch):
    import json, sys
    from unittest.mock import MagicMock

    mock_session = MagicMock()
    mock_session.SetUndoMark.return_value = 42

    orig_nxopen = sys.modules.get("NXOpen")
    mock_nxopen = MagicMock()
    mock_nxopen.Session.GetSession.return_value = mock_session
    mock_nxopen.Session.MarkVisibility.Invisible = 0
    sys.modules["NXOpen"] = mock_nxopen

    try:
        from nx_mcp.bridge import nx_bridge

        monkeypatch.setattr(nx_bridge, "SESSION", mock_session)
        monkeypatch.setattr(nx_bridge, "dispatch", lambda cmd: {"ok": False, "error": "simulated_error"})

        res = nx_bridge.handle_line(json.dumps({"tool": "unknown_tool"}))
        assert res == {"ok": False, "error": "simulated_error"}

        assert mock_session.SetUndoMark.called
        assert mock_session.SetUndoMark.call_args[0][1] == "nx_mcp_command"
        mock_session.UndoToMark.assert_called_once_with(42, "nx_mcp_command")
    finally:
        if orig_nxopen:
            sys.modules["NXOpen"] = orig_nxopen
        else:
            sys.modules.pop("NXOpen", None)

