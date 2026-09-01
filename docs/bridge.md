# Bridge Layer

## Overview

The bridge layer connects the MCP server (a standard Python process) to **Siemens NX** (which executes its own isolated Python environment with access to native C++ CAD libraries). It consists of two components operating across process boundaries:

- **`src/nx_mcp/bridge/runner.py`** — Runs on the MCP server side; manages NX process lifecycles, locks, timeouts, and TCP communication.
- **`src/nx_mcp/bridge/nx_bridge.py`** — Runs inside Siemens NX (`ugraf.exe`); executes NXOpen API builders, manages expression variables, and tracks geometry state.

---

## Communication Architecture (Socket-First Mode)

All production communication occurs over a local loopback TCP socket on **port 43210**.

```
┌─────────────────────────┐               TCP Loopback              ┌──────────────────────────────────────┐
│  src/nx_mcp/runner.py   │             Port 43210                  │  src/nx_mcp/bridge/nx_bridge.py      │
│  (MCP Server Process)   │────────────────────────────────────────▶│  (Runs INSIDE ugraf.exe process)     │
│                         │   JSON-Lines Payload                    │                                      │
│  - Acquires _lock       │   {"tool": "...", "args": {...}}\n      │  - Non-blocking select.select() loop │
│  - Socket timeout:      │                                         │  - ui.ProcessDeviceEvents() keepalive│
│    60s standard         │◀────────────────────────────────────────│  - handle_line() with deep snapshot  │
│    300s journal/recipe  │   JSON-Lines Response                   │  - dispatch() to NXOpen Builders     │
│  - Launch timeout: 180s │   {"ok": true, "message": "..."}\n      │  - Commits geometry & saves part     │
└─────────────────────────┘                                         └──────────────────────────────────────┘
```

### Execution Protocol

1. `runner.py` calls `try_connect_socket(LIVE_PORT)` to verify connectivity.
2. If disconnected, `launch_interactive_nx()` acquires `bridge.launching.lock`, launches `ugraf.exe -auto=...nx_bridge.py`, and waits for socket readiness.
3. `runner.py` transmits a single JSON line: `{"tool": "<name>", "args": {<kwargs>}}\n`.
4. `nx_bridge.py` receives the stream, parses the JSON command, and creates an in-memory backup of `_state`.
5. `dispatch()` normalizes arguments and invokes the corresponding NXOpen handler.
6. The handler builds the parametric feature, creates NX expressions, commits the builder, and updates geometry caches.
7. `nx_bridge.py` responds with a JSON line: `{"ok": true, "message": "<summary>", "filepath": "<path>"}\n`.
8. If an exception occurs, `handle_line()` catches the error, restores `_state` to its pre-call snapshot, and returns `{"ok": false, "error": "<traceback>"}`.

> **Execution Model Note**: Legacy batch stdio execution (`run_journal.exe` batch mode) is deprecated due to stdio unreliability in headless NX journals. In current code, if a live socket cannot be established, the system returns `NX_PREWARM_REQUIRED_ERROR`, directing the user to run `python prewarm_nx.py`.

---

## In-NX Bridge Subsystems (`src/nx_mcp/bridge/nx_bridge.py`)

`nx_bridge.py` (~6032 lines) is the comprehensive execution engine inside Siemens NX. It is the **only module** that imports `NXOpen` and `NXOpen.UF`.

### 1. Global State Management (`_state`)

```python
SESSION = NXOpen.Session.GetSession()
UF_SESSION = NXOpen.UF.UFSession.GetUFSession()
ACTIVE_SKETCH_PLANE = "XY"          # Reset to "XY" on create_part/open_part

_state = {
    "last_curves": [],          # Curves from latest sketch/curve operation
    "last_feature": None,       # Most recently created NX Feature object
    "last_body": None,          # Most recently created/modified NX Body object
    "features": {},             # Dict[str, Feature] — name -> feature lookup
    "bodies": {},               # Dict[str, Body] — name -> body lookup
    "sketches": {},             # Dict[str, Sketch] — name -> sketch lookup
    "active_sketch": None,      # Currently active NX Sketch object
    "sketch_origin": [0,0,0],   # 3D origin offset for active sketch plane
    "sketch_rotation": 0.0,     # Rotation (deg) for active sketch plane
}
```

### 2. State Reset on Part Boundaries

To eliminate cross-part contamination when multiple parts are modeled in the same NX session, `_reset_transient_session_state()` is automatically invoked at the beginning of `create_part()` and `open_part()`:

```python
def _reset_transient_session_state():
    global ACTIVE_SKETCH_PLANE
    ACTIVE_SKETCH_PLANE = "XY"
    _state["last_curves"] = []
    _state["last_feature"] = None
    _state["last_body"] = None
    _state["features"] = {}
    _state["bodies"] = {}
    _state["sketches"] = {}
    _state["active_sketch"] = None
    _state["sketch_origin"] = [0.0, 0.0, 0.0]
    _state["sketch_rotation"] = 0.0
    _expression_counters.clear()
    _instance_counters.clear()
```

### 3. Fallback Part Safety (`_ensure_work_part`)

Before any modeling operation, `_ensure_work_part()` validates the active CAD part. If no part is open:
- It inspects the default fallback part `nx_mcp_result.prt`.
- If the default fallback already contains features or bodies from an older session, it automatically allocates a fresh timestamped/numbered fallback part (e.g. `nx_mcp_result_1.prt`) to prevent accidental geometric collisions.

### 4. Dynamic State Rollback (`handle_line`)

```python
def handle_line(line):
    old_state = dict(_state)
    old_state["features"] = dict(_state.get("features", {}))
    old_state["bodies"] = dict(_state.get("bodies", {}))
    old_state["sketches"] = dict(_state.get("sketches", {}))
    old_state["last_curves"] = list(_state.get("last_curves", []))
    
    try:
        result = dispatch(json.loads(line))
        if not result.get("ok"):
            _state.update(old_state)   # Rollback on logical CAD error
        return result
    except Exception as exc:
        _state.update(old_state)       # Rollback on unhandled exception
        return {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
```

### 5. Reference Resolvers & Fuzzy Matching

When tools reference features, bodies, or edges (e.g. `"target"`, `"last"`, `"CUBOID_1"`, `"vertical_edges"`), resolution helpers dynamically locate the NX objects:

- **`_resolve_body(reference)`**: Resolves `"last"`, `"body_1"`, or exact/fuzzy body names via `_normalize_name()`.
- **`_resolve_feature(reference)`**: Resolves `"last"`, `"previous"`, or feature names by checking `_state["features"]` and scanning `work_part.Features`.
- **`_resolve_edges(body_ref, edge_ref)`**: Uses geometric boundary queries (`UF_SESSION.Modeling.AskBndbox()`) to filter edges matching geometric criteria (`"all"`, `"outer_edges"`, `"vertical_edges"`, `"top_edges"`, `"bottom_edges"`, `"x_aligned_edges"`, `"y_aligned_edges"`, `"z_aligned_edges"`).

### 6. Hole Intersection Validation

To prevent silent geometric failures when placing holes, `_validate_hole_intersection()` runs an AABB (Axis-Aligned Bounding Box) preflight check:

```python
def _validate_hole_intersection(target_body, x, y, z, diameter, depth, direction_str):
    (b_min, b_max) = _body_bounds(target_body)
    # Calculates hole cylinder bounding box with 1mm tolerance
    # Verifies overlap against target body bounding box
    if not intersects:
        return False, "Hole position does not intersect the target body - no material removed"
    return True, None
```
Post-operation edge count validation confirms that material was genuinely removed.

### 7. Curve Subsystem (`draw_spline`, `offset_curve`, `close_curve_region`)

- **`draw_spline(points, is_periodic)`**: Instantiates `NXOpen.Features.StudioSplineBuilderEx` to construct smooth, multi-point B-splines on the active sketch plane or in 3D world space.
- **`offset_curve(curve_reference, offset_distance_start, offset_distance_end)`**: Computes normal offsets across spline defining poles to generate constant or variable-width offset profiles.
- **`close_curve_region(curve_references, method)`**: Connects curve endpoints with bridge segments to produce a watertight closed region ready for `extrude` or `extrude_cut`.

### 8. Python Journal Scripting (`exec_python_code` / `run_nx_journal_code`)

When mathematically complex geometry (such as involute gear teeth or mathematical cams) cannot be represented by primitive tools:
- The script is executed inside NX via `exec_python_code`.
- Global variables (`SESSION`, `UF_SESSION`, `work_part`, `NXOpen`, `Point3d`, `Vector3d`, `Null`, `math`) are pre-injected.
- All standard `print()` statements are captured and returned in the MCP response output.

---

## Dispatch and Parameter Normalization

The `dispatch(command)` function acts as the internal router:
1. Maps incoming tool names to internal function symbols in `globals()`.
2. Normalizes legacy parameter naming conventions (e.g. `z_offset` ↔ `z`, `offset` ↔ `radius`).
3. Uses `inspect.signature` to bind incoming arguments to declared defaults.
4. Executes the handler and serializes the return dictionary.

---

## Related Documentation

- [runner.md](runner.md) — Process manager, locks, and launch configurations.
- [state.md](state.md) — Deep dive into state management and geometry caches.
- [parametric.md](parametric.md) — NX Expressions and builder patterns.
- [workflow.md](workflow.md) — Request lifecycle from client to NX and back.
