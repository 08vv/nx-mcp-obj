# State Management

## Overview

The NX bridge (`src/nx_mcp/bridge/nx_bridge.py`) maintains transient in-memory state during an active Siemens NX session. This state allows multi-step CAD workflows (e.g. sketching, extruding, filleting, cutting) to reference previously created features, bodies, curves, and sketch planes without requiring the AI agent to remember low-level NX internal tag pointers.

---

## The Bridge State Dictionary (`_state`)

```python
_state = {
    "last_curves": [],          # List of NX Curve / Spline objects from the latest sketch/curve tool
    "last_feature": None,       # Most recently committed NX Feature object
    "last_body": None,          # Most recently created or modified NX Body object
    "features": {},             # Dict[str, Feature] — Normalized feature name -> Feature lookup
    "bodies": {},               # Dict[str, Body] — Normalized body name -> Body lookup
    "sketches": {},             # Dict[str, Sketch] — Sketch name -> Sketch lookup
    "active_sketch": None,      # Currently active NX Sketch object
    "sketch_origin": [0,0,0],   # 3D world coordinate offset for the active sketch plane
    "sketch_rotation": 0.0,     # Rotation angle (degrees) for the active sketch plane
}
```

---

## Session Isolation & State Reset

> **Critical Invariant**: Siemens NX (`ugraf.exe`) typically remains open across multiple distinct CAD design requests. Without an explicit reset, stale sketch planes, origin offsets, and cached feature references from a previous part would contaminate a new build.

### Part Boundary Reset (`_reset_transient_session_state`)

Whenever `create_part()` or `open_part()` is called, the bridge wipes all transient caches:

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

---

## Tracking and Resolution Subsystems

### 1. Feature & Body Tracking

After any feature builder successfully commits geometry:
- **`_remember_feature(feature)`**:
  1. Sets `_state["last_feature"] = feature`.
  2. Generates feature name variants (via `_feature_name()`) and registers them in `_state["features"]`.
  3. Iterates over all bodies produced by the feature and invokes `_remember_body(body)`.
- **`_remember_body(body)`**:
  1. Sets `_state["last_body"] = body`.
  2. Generates body name variants (via `_body_name()`) and registers them in `_state["bodies"]`.

### 2. Name Normalization (`_normalize_name`)

Siemens NX assigns automatic incremental names like `"CYLINDER(0)"` or `"BLOCK(1)"`. The normalization helper strips trailing parenthetical indices:
- `"CYLINDER(0)"` → `"cylinder"`
- `"Block(1)"` → `"block"`
- `"Extrude(3)"` → `"extrude"`

This allows queries like `_resolve_body("cylinder")` to successfully resolve `"CYLINDER(0)"`.

### 3. Resolvers

| Resolver Function | Input Queries Handled | Fallback Strategy |
|---|---|---|
| **`_resolve_body(ref)`** | `"last"`, `"target"`, `"body_1"`, `"body_2"`, body names | If only one solid body exists in the entire work part, auto-selects it. |
| **`_resolve_feature(ref)`** | `"last"`, `"previous"`, `"HOLE_1"`, feature names | Scans all features in `work_part.Features` using normalized name matching. |
| **`_resolve_edges(body_ref, edge_ref)`** | `"all"`, `"outer_edges"`, `"vertical_edges"`, `"top_edges"`, `"bottom_edges"`, `"x_aligned_edges"`, `"y_aligned_edges"`, `"z_aligned_edges"` | Uses bounding box evaluation (`UF_SESSION.Modeling.AskBndbox()`) to filter edges matching geometric alignments. |
| **`_resolve_single_curve(curve_ref)`** | `"last"`, `"last_curve"`, index numbers (`0`, `1`), curve names | Scans `_state["last_curves"]` or searches `work_part.Curves`. |

---

## Active Sketch Plane Transforms

When drawing 2D profiles or placing holes:
1. `ACTIVE_SKETCH_PLANE` ("XY", "XZ", or "YZ") establishes the primary coordinate system.
2. `sketch_origin` provides a 3D translation offset.
3. `sketch_rotation` provides an in-plane angular offset.
4. **`_point_on_active_plane(x, y)`**: Translates 2D coordinates `(x, y)` into an absolute 3D world coordinate `Point3d(X, Y, Z)` according to the active plane and offsets.

---

## Expression State & Instance Counters

To maintain 100% parametric models while avoiding naming collisions across multiple features:

```python
_expression_counters = {}    # prefix -> next available suffix number
_instance_counters = {}      # feature_type -> next instance number
```

### Counter Seeding (`_seed_counters_from_part`)

When opening an existing `.prt` file, `_seed_counters_from_part(work_part)` parses all existing NX expressions using regular expressions:
- Scans `CUBOID_1_L`, `CUBOID_2_L` → seeds `_instance_counters["CUBOID"] = 2`.
- Next cuboid created will automatically use prefix `CUBOID_3`, preventing expression collision.

---

## State Snapshot & Rollback

Before executing any command, `handle_line()` captures a deep copy of `_state`:
- If the tool completes successfully (`{"ok": true}`), the updated state is retained.
- If the tool fails or raises an unhandled exception, `_state.update(old_state)` restores the exact pre-call state.

---

## Related Documentation

- [bridge.md](bridge.md) — Bridge architecture and NXOpen dispatching.
- [parametric.md](parametric.md) — Parametric expression architecture.
- [workflow.md](workflow.md) — End-to-end request and state lifecycle.
