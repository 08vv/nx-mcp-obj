# Runner

## Overview

The runner (`src/nx_mcp/bridge/runner.py`) is the process and transport manager on the MCP server side. It provides `call_nx(tool, args)` and `run_tool(tool, **args)` as the primary entry points for dispatching CAD operations to Siemens NX.

---

## Core Components

### 1. `NXBridgeProcess` Singleton

`NXBridgeProcess` coordinates the execution flow, process lifecycle, and socket connections:

```python
class NXBridgeProcess:
    _proc = None             # Optional legacy process reference
    _ugraf_proc = None       # ugraf.exe interactive subprocess reference
    _lock = threading.Lock() # Thread-safety mutex serializing all bridge calls
```

**Thread Safety**: Every call to `NXBridgeProcess.call(tool, args)` is protected by `_lock`, ensuring that parallel requests from MCP clients or asynchronous workers are serialized without race conditions.

---

## 2. Environment Verification (`verify_nx_environment()`)

Before attempting any bridge communication, `verify_nx_environment()` verifies that the host system has a valid Siemens NX installation:

1. Checks that `UGII_BASE_DIR` is set (e.g. `C:\Program Files\Siemens\NX2206`).
2. Searches `NXBIN/` and `UGII/` subdirectories for required executables:
   - `ugraf.exe` — The interactive Siemens NX GUI executable.
   - `run_journal.exe` — The NX journal execution runner.
   - `ugs_router.exe` — The NX file association router used for auto-opening parts.
3. Raises a descriptive `RuntimeError` if any executable is missing.

---

## 3. Launch Safeguards & Anti-Duplicate Mutex

To prevent multiple `ugraf.exe` instances from launching simultaneously when parallel tool calls arrive:

1. **Process Inspection (`_find_running_ugraf`)**: Scans Windows processes via `tasklist` to locate any existing `ugraf.exe` process.
2. **Cross-Process Mutex (`LAUNCH_LOCK_PATH`)**: Uses `bridge.launching.lock` locked via `msvcrt.locking()` to ensure only one thread or process initiates NX launch at a time.
3. **Bridge Config Initialization**: Writes `live_bridge_config.json` containing the initial part path and port `43210`.
4. **Auto-Launch**: Spawns `ugraf.exe -auto=...nx_bridge.py` and monitors socket connection until ready.

---

## 4. Socket Communication Protocol (`_call_socket`)

Communication is handled over TCP port `43210`:

```python
# Timeout Configuration
DEFAULT_SOCKET_TIMEOUT = int(os.environ.get("NX_MCP_SOCKET_TIMEOUT", "60"))    # 60 seconds
JOURNAL_TIMEOUT = int(os.environ.get("NX_MCP_JOURNAL_TIMEOUT", "300"))           # 300 seconds
LAUNCH_TIMEOUT = int(os.environ.get("NX_MCP_LAUNCH_TIMEOUT", "180"))             # 180 seconds
```

- **Per-Tool Timeout Dynamic Adjustment**:
  - Complex scripts and specs (`exec_python_code`, `run_recipe`, `run_spec`, `run_nx_journal_code`, `execute_journal`) receive up to **300 seconds** (`NX_MCP_JOURNAL_TIMEOUT`).
  - Standard CAD modeling tools receive **60 seconds** (`NX_MCP_SOCKET_TIMEOUT`).
- **Payload Framing**: Messages are transmitted as UTF-8 encoded JSON strings terminated by `\n`.
- **Response Parsing**: Reads chunks from the socket buffer until a newline delimiter is received, then parses the JSON response dict.

---

## 5. Execution Flow Chart

```
call_nx(tool, args)
  │
  ├─ Acquire NXBridgeProcess._lock
  ├─ verify_nx_environment()
  │
  ├─ try_connect_socket(43210) ───────────┐ (Socket active?)
  │                                       │
  │  [If NO]                              │ [If YES]
  │   │                                   │
  │   ├─ _find_running_ugraf()            │
  │   │   └─ If running, wait for socket  │
  │   │                                   │
  │   ├─ launch_interactive_nx()          │
  │   │   ├─ Acquire bridge.launching.lock│
  │   │   ├─ Popen(ugraf.exe -auto=...)   │
  │   │   └─ Wait up to 180s for socket   │
  │   │                                   │
  │   └─ try_connect_socket(43210)        │
  │                                       │
  ▼                                       ▼
_call_socket(s, tool, args) ◀─────────────┘
  │
  ├─ Send: {"tool": ..., "args": ...}\n
  ├─ Await newline-terminated JSON response
  ├─ If successful and part created/opened:
  │   └─ _update_watcher_files(filepath)
  └─ Return result dictionary
```

---

## 6. File Watcher & Auto-Open Integration (`_update_watcher_files`)

Whenever a part is created or opened, `runner.py` generates helper artifacts in the project root:

1. **`latest_nx_result.txt`**: Contains the absolute filesystem path of the active `.prt` file.
2. **`open_current_nx_result.cmd`**: Batch script that opens the current `.prt` in Siemens NX via `ugs_router.exe`.
3. **`open_latest_nx_result.vbs`**: Silent VBScript launcher to open the part in the background without command prompt popups.

---

## 7. Prewarm Instructions (`prewarm_nx.py`)

If NX is closed and cannot be auto-launched before the timeout expires, the runner returns `NX_PREWARM_REQUIRED_ERROR`:

```
"NX is not running and could not be auto-launched in time. Do not attempt run_nx_journal_code, 
do not import NXOpen manually - instead, tell the user to run 'python prewarm_nx.py' first 
and wait for it to complete, then retry."
```

Running `python prewarm_nx.py` boots NX with the bridge preloaded, ensuring instant responses for all subsequent tool calls.

---

## 8. Environment Variables Reference

| Variable | Default | Purpose |
|---|---|---|
| `UGII_BASE_DIR` | *None* (Required) | Path to Siemens NX root installation (e.g. `C:\Program Files\Siemens\NX2206`). |
| `NX_MCP_ENABLE_ROUTING` | `1` | Enables dynamic keyword tool routing to optimize prompt token usage. |
| `NX_MCP_SOCKET_TIMEOUT` | `60` | Socket read timeout in seconds for standard modeling operations. |
| `NX_MCP_JOURNAL_TIMEOUT` | `300` | Socket read timeout in seconds for multi-step recipes and scripts. |
| `NX_MCP_LAUNCH_TIMEOUT` | `180` | Maximum wait time in seconds for Siemens NX to boot and open port 43210. |
| `NX_MCP_USE_MOCK_NXOPEN` | `0` | Enables mock NXOpen runtime for pytest testing without Siemens NX. |

---

## 9. Cleanup & Reset (`reset_nx_bridge`)

```python
def reset_nx_bridge(stop_ugraf=False):
    NXBridgeProcess.reset(stop_ugraf=stop_ugraf)
```

- Cleans up configuration files (`live_bridge_config.json`).
- Releases launch lock files.
- Optionally terminates the `ugraf.exe` process if `stop_ugraf=True`.
- Registered automatically with Python's `atexit` handler to prevent orphaned bridge locks.

---

## Related Documentation

- [architecture.md](architecture.md) — System architecture and layer breakdown.
- [bridge.md](bridge.md) — In-NX bridge execution engine (`nx_bridge.py`).
- [workflow.md](workflow.md) — Complete end-to-end request lifecycle.
- [cad_spec_system.md](cad_spec_system.md) — Declarative CAD Spec DAG engine.
