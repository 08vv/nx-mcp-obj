# State Management & Geometry Dependency Graph

## Overview

State management in NX-MCP operates at two levels:
1. **In-NX Runtime State (`src/nx_mcp/bridge/nx_bridge.py`)**: An in-memory cache inside the Siemens NX process that resolves dynamic references (e.g. `"last"`, `"target"`, `"vertical_edges"`) and manages session boundary isolation and rollback.
2. **Server-Side Persistent Geometry Dependency Graph (`src/nx_mcp/state/dependency_graph.py`)**: A structured Directed Acyclic Graph (DAG) that models the topological lifecycle of CAD entities (bodies, features, sketches, profiles), tracking entity creation, modifications, and consumption to guarantee physical integrity and prevent double consumption.

---

## 1. In-NX Runtime State (`nx_bridge.py`)

### The State Dictionary (`_state`)

```python
_state = {
    "last_curves": [],          # List of NX Curve / Spline objects from the latest sketch/curve tool
    "last_feature": None,       # Most recently committed NX Feature object
    "last_body": None,          # Most recently created or modified NX Body object
    "features": {},             # Dict[str, Feature] — Normalized feature name -> Feature lookup
    "bodies": {},               # Dict[str, Body] — Normalized body name -> Body lookup
    "sketches": {},             # Dict[str, Sketch] — Sketch name -> Sketch lookup
    "active_sketch": None,      # Currently active NX Sketch object
    "sketch_origin": [0.0, 0.0, 0.0], # 3D world coordinate offset for active sketch plane
    "sketch_rotation": 0.0,     # Rotation angle (degrees) for active sketch plane
}
```

### Session Boundary Reset (`_reset_transient_session_state`)

> **Critical Invariant**: Siemens NX (`ugraf.exe`) typically remains open across multiple distinct CAD design requests. Without an explicit reset, stale sketch planes, origin offsets, and cached feature references from a previous part would contaminate a new build.

Whenever `create_part()` or `open_part()` is called, all transient caches are wiped clean:

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

### State Snapshot & Rollback

Before dispatching any command, `handle_line()` captures a deep copy of `_state`:
- **Success (`{"ok": true}`)**: The updated state is retained.
- **Failure (`{"ok": false}`) or Unhandled Exception**: `_state.update(old_state)` immediately restores the exact pre-call state snapshot, ensuring that failed operations leave no corrupted references.

### Reference Resolvers & Name Normalization

Siemens NX assigns automatic incremental names like `"CYLINDER(0)"` or `"BLOCK(1)"`. The normalization helper `_normalize_name()` strips trailing parenthetical indices (`"CYLINDER(0)"` → `"cylinder"`), enabling fuzzy matching:

| Resolver Function | Input Queries Handled | Fallback Strategy |
|---|---|---|
| **`_resolve_body(ref)`** | `"last"`, `"target"`, `"body_1"`, `"body_2"`, body names | If only one solid body exists in the work part, auto-selects it. |
| **`_resolve_feature(ref)`** | `"last"`, `"previous"`, `"HOLE_1"`, feature names | Scans all features in `work_part.Features` using normalized name matching. |
| **`_resolve_edges(body_ref, edge_ref)`** | `"all"`, `"outer_edges"`, `"vertical_edges"`, `"top_edges"`, `"bottom_edges"`, `"x_aligned_edges"`, `"y_aligned_edges"`, `"z_aligned_edges"` | Uses bounding box evaluation (`UF_SESSION.Modeling.AskBndbox()`) to filter edges matching geometric alignments. |
| **`_resolve_single_curve(curve_ref)`** | `"last"`, `"last_curve"`, index numbers (`0`, `1`), curve names | Scans `_state["last_curves"]` or searches `work_part.Curves`. |

### Expression State & Instance Counters

To maintain 100% parametric models while avoiding naming collisions across multiple features:
```python
_expression_counters = {}    # prefix -> next available suffix number
_instance_counters = {}      # feature_type -> next instance number
```

When opening an existing `.prt` file, `_seed_counters_from_part(work_part)` parses all existing NX expressions via regex:
- Scans `CUBOID_1_L`, `CUBOID_2_L` → seeds `_instance_counters["CUBOID"] = 2`.
- The next cuboid created will automatically use prefix `CUBOID_3`, preventing expression collisions.

---

## 2. Server-Side Geometry Dependency Graph (`state/dependency_graph.py`)

While `_state` inside NX holds live C++ pointers, the MCP server maintains a persistent, queryable DAG representing the geometric architecture of the CAD model.

```
┌─────────────────────────────────────────────────────────────┐
│                 Geometry Dependency Graph                   │
├─────────────────────────────────────────────────────────────┤
│ Nodes:                                                      │
│ - Body Nodes (type='body', status='alive'|'consumed')       │
│ - Feature Nodes (type='feature', status='alive'|'consumed') │
│ - Sketch Nodes (type='sketch', status='alive'|'consumed')   │
│ - Profile Nodes (type='profile', status='alive'|'consumed') │
│ - Curve Nodes (type='curve', status='alive'|'consumed')     │
├─────────────────────────────────────────────────────────────┤
│ Edges:                                                      │
│ - 'produced_by': entity was created by feature / node       │
│ - 'consumed_by': entity was boolean-united / subtracted     │
│ - 'modified_by': entity was filleted, chamfered, or drilled │
└─────────────────────────────────────────────────────────────┘
```

### Entity Lifecycles (`alive` vs `consumed`)
In mechanical CAD, operations often "consume" predecessor geometry:
- When Body A and Body B are united via `boolean_unite(target=A, tool=B)`, Body B is **consumed** into Body A.
- Body B transitions to `status = "consumed"`, with a dependency edge `consumed_by -> boolean_unite_feature`.
- Body A remains `status = "alive"`, with an edge `modified_by -> boolean_unite_feature`.

### Double-Consumption Prevention
A common bug in AI-generated CAD recipes is attempting to unite, subtract, or fillet a tool body that was already consumed in an earlier step.
`validate_graph_integrity()` inspects all nodes and edges:
- Asserts that no entity has multiple `consumed_by` edges.
- Asserts that no dangling references exist.
- Emits explicit integrity violations if double consumption is detected.

---

## 3. State Inspection MCP Tools (`state_tools.py`)

NX-MCP exposes four dedicated inspection tools for agents and developers:

### 1. `get_dependency_graph(scope="session")`
Retrieves the complete geometry dependency graph as a formatted JSON document.
- Returns total node count, alive count, consumed count, and edge count.
- Includes the integrity status (`VALID` or lists specific violations).

### 2. `get_downstream(node_id, depth=0)`
Queries all entities and features that depend on or were produced downstream from `node_id`.
- Useful for impact analysis before modifying or deleting an upstream dimension or feature.
- `depth`: Maximum traversal depth (0 for unlimited).

### 3. `get_upstream(node_id, depth=0)`
Queries all predecessor entities and features that contributed to the creation of `node_id`.
- Useful for tracing the lineage of a target body or identifying driving sketches.

### 4. `validate_dependency_graph()`
Performs a fast integrity check across the active session graph.
- Returns whether the graph is topologically sound.
- Detects double-consumption and orphaned entity references.

---

## 4. Related Documentation

- [cad_spec_system.md](cad_spec_system.md) — How the CAD Spec engine interacts with the dependency graph.
- [bridge.md](bridge.md) — In-NX bridge execution engine and `_state` internals.
- [parametric.md](parametric.md) — Parametric expression architecture.
- [workflow.md](workflow.md) — End-to-end request and state lifecycles.
