# Declarative CAD Spec Engine (`run_spec`)

## 1. Overview

While individual tool calls (`create_cuboid`, `add_hole`) and procedural lists (`run_recipe`) work well for basic modeling, complex mechanical CAD models often require:
- **Symbolic References**: Passing an unknown body or feature ID produced by an earlier step directly to a downstream step (e.g., using `$n1.body_id` as the target for `$n2`).
- **Computed Geometry Math**: Evaluating formulas or math helper functions without client round trips (e.g., calculating bolt circle hole coordinates or derived dimensions).
- **Physical & Geometric Plausibility Preflights**: Catching impossible geometry (e.g. negative dimensions, extreme aspect ratios, holes larger than their host block) *before* sending them to Siemens NX.
- **Resumable / Steppable Execution**: Pausing after key milestones for visual verification or re-running a specific node and its downstream dependents when tweaking a parameter.
- **Post-Execution Verification**: Ensuring geometry was genuinely created, bodies are manifold, and no topological violations occurred.

The **CAD Spec Engine** (`src/nx_mcp/spec/`) implements this declarative DAG (Directed Acyclic Graph) architecture.

---

## 2. Architecture & Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CAD Spec JSON Document                           │
│     {"part_name": "manifold", "units": "mm", "nodes": [n1, n2, n3...]}      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 1: Structural Validation & Cycle Detection (spec/validator.py)        │
│ - Validates schema, operation names, and required parameters                 │
│ - Infers dependency edges from $node.field references                        │
│ - Detects cyclic dependencies using Kahn's topological sort                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 2: Preflight Plausibility Check (spec/plausibility.py)                │
│ - Evaluates static dimensions for physical feasibility                      │
│ - Checks aspect ratios, positive bounds, and minimum wall thicknesses       │
│ - Validates hole diameters against enclosing body dimensions                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 3: Topological Graph Execution (spec/executor.py)                     │
│ For each node in topological order:                                         │
│   1. Resolve references: $node.field, $expr:NAME, $calc:EXPR, $fn:FUNC(...) │
│   2. Dispatch operation to tool wrapper or NXOpen bridge                     │
│   3. Capture outputs (body_id, feature_id, expressions)                     │
│   4. Update persistent Geometry Dependency Graph (state/dependency_graph.py)│
│   5. Check pause condition (pause_after -> generate execution_token)        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Phase 4: Post-Execution Verification (spec/postcheck.py & geocheck.py)      │
│ - Verifies active solid bodies and face/edge counts                          │
│ - Checks topological integrity in dependency graph (no double-consumption)  │
│ - Automatically saves the finalized part to disk                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Spec Document Schema

A CAD Spec consists of three primary fields:
- `part_name`: (string) Base name for the `.prt` file.
- `units`: (string) Units of measurement, typically `"mm"` or `"inch"`.
- `nodes`: (list of `SpecNode` dicts) The topological operation graph.

### `SpecNode` Schema

```json
{
  "id": "n1",
  "op": "create_cuboid",
  "params": {
    "length": 120.0,
    "width": 80.0,
    "height": 25.0,
    "centered": true
  },
  "depends_on": [],
  "produces": {
    "body_id": "body_1"
  }
}
```

- `id`: (string) Unique identifier for the node within the spec (e.g. `"n1"`, `"base_block"`, `"mounting_holes"`).
- `op`: (string) Any registered NX-MCP tool or CAD operation (e.g. `"create_cuboid"`, `"add_hole"`, `"add_fillet"`, `"extrude"`, `"create_sketch"`).
- `params`: (dict) Input arguments passed to the operation. Parameter values can contain literals, symbolic references, calculations, or math functions.
- `depends_on`: (list of strings, optional) Explicit predecessor node IDs. If omitted, dependencies are automatically inferred from symbolic references in `params`.
- `produces`: (dict, optional) Output mappings specifying which return fields this node publishes for downstream nodes to consume.

---

## 4. Symbolic Reference Syntax

The CAD Spec engine resolves four distinct types of dynamic references at runtime:

### 1. Node Output References: `$node_id.field_name`
Dynamically resolves an output field published by an upstream node after that node has completed execution.
```json
{
  "id": "n2",
  "op": "add_fillet",
  "params": {
    "body": "$n1.body_id",
    "radius": 4.0,
    "edge_reference": "top_edges"
  }
}
```

### 2. Expression References: `$expr:NAME`
Resolves the current numeric value of an NX Expression.
```json
{
  "id": "n3",
  "op": "create_cylinder",
  "params": {
    "diameter": 20.0,
    "height": "$expr:CUBOID_1_H"
  }
}
```

### 3. Calculation References: `$calc:EXPRESSION`
Evaluates a mathematical expression safely using an AST parser (no arbitrary Python `eval`). Calculations can embed node output references and expression references:
```json
{
  "id": "n4",
  "op": "add_hole",
  "params": {
    "x": "$calc:$n1.length / 2 - 15",
    "y": "$calc:$n1.width / 2 - 15",
    "z": 12.5,
    "diameter": 6.0,
    "depth": 25.0,
    "target": "$n1.body_id"
  }
}
```

### 4. Geometry Math Functions: `$fn:func_name(...)`
Invokes pure, deterministic geometric calculation helpers from `src/nx_mcp/spec/geometry_math.py`.

Supported `$fn:` functions:
- **`$fn:polar_to_cartesian(radius, angle_deg, center_x=0, center_y=0)`**: Returns `[x, y]` coordinates.
- **`$fn:cartesian_to_polar(x, y, center_x=0, center_y=0)`**: Returns `{"radius": r, "angle_deg": theta}`.
- **`$fn:bolt_circle(count, pcd, start_angle_deg=0, center_x=0, center_y=0)`**: Generates a list of `[x, y]` pairs spaced evenly around a Pitch Circle Diameter (PCD).
- **`$fn:linear_spacing(count, pitch, start_x=0, start_y=0, direction_deg=0)`**: Generates a list of `[x, y]` pairs along a line.
- **`$fn:offset_point_along_vector(x, y, distance, direction_deg)`**: Offsets a 2D point along a vector.
- **`$fn:lerp(start, end, t)`**: Linear interpolation between two scalar values (`t` from `0.0` to `1.0`).
- **`$fn:deg_to_rad(deg)`** / **`$fn:rad_to_deg(rad)`**: Angular unit conversions.

---

## 5. Complete Example: Flanged Bearing Housing

Here is a complete, real-world CAD Spec demonstrating symbolic references, `$calc:`, and `$fn:bolt_circle`:

```json
{
  "part_name": "flanged_bearing_housing",
  "units": "mm",
  "nodes": [
    {
      "id": "base_flange",
      "op": "create_cylinder",
      "params": {
        "diameter": 120.0,
        "height": 15.0,
        "axis": "Z"
      }
    },
    {
      "id": "hub",
      "op": "create_cylinder",
      "params": {
        "diameter": 70.0,
        "height": 45.0,
        "axis": "Z",
        "z": 15.0
      }
    },
    {
      "id": "join_solids",
      "op": "boolean_unite",
      "params": {
        "target": "$base_flange.body_id",
        "tool": "$hub.body_id"
      }
    },
    {
      "id": "center_bore",
      "op": "add_hole",
      "params": {
        "target": "$join_solids.body_id",
        "x": 0.0,
        "y": 0.0,
        "z": 60.0,
        "diameter": 40.0,
        "depth": 60.0,
        "direction": "-Z"
      }
    },
    {
      "id": "mounting_holes",
      "op": "pattern_circular",
      "params": {
        "feature": "$mounting_hole_1.feature_id",
        "count": 4,
        "angle_total": 360.0
      },
      "depends_on": ["mounting_hole_1"]
    },
    {
      "id": "flange_blend",
      "op": "add_fillet",
      "params": {
        "body": "$join_solids.body_id",
        "radius": 3.0,
        "edge_reference": "top_edges"
      }
    }
  ]
}
```

---

## 6. Execution Lifecycle & Steppable Tools

The CAD Spec engine provides four dedicated MCP tools in `src/nx_mcp/tools/recipe.py`:

### 1. `run_spec(spec, stop_on_error=True, validate_plausibility=True, verify_postexecution=True, pause_after=None)`
Executes the spec graph.
- If `pause_after` is set (e.g. `["hub"]` or `"every_node"`), execution stops after that node. The return payload includes an `execution_token` (e.g. `"spec_exec_a1b2c3d4"`).
- If execution finishes completely, runs post-execution geometric validation, saves the `.prt` file to disk, and returns a detailed execution summary.

### 2. `resume_spec(execution_token, pause_after=None, stop_on_error=True, verify_postexecution=True)`
Resumes execution of a paused CAD Spec graph using the `execution_token`. Downstream nodes pick up accumulated state and resolved references seamlessly.

### 3. `rerun_spec_node(execution_token, node_id, new_params=None, pause_after=None)`
Allows parametric experimentation during an active session:
- Selectively updates `new_params` for `node_id`.
- Invalidates and re-executes `node_id` and all downstream dependent nodes in topological order.
- Leaves unaffected upstream nodes untouched, saving significant computation time.

---

## 7. Preflight Plausibility Rules (`spec/plausibility.py`)

Before any NXOpen command is dispatched, the plausibility validator evaluates the spec:
1. **Positive Dimensional Bounds**: Rejects negative or zero values for lengths, widths, heights, diameters, and radii.
2. **Aspect Ratio Sanity**: Rejects extreme dimension ratios (e.g. length-to-thickness > 1000:1) that lead to Parasolid kernel numerical instabilities.
3. **Geometric Inclusion**: Checks that hole diameters do not exceed the boundaries of host blocks or cylinders.
4. **Fillet Radius Bounds**: Checks that fillet radii do not exceed half the smallest adjacent edge dimension.

If any rule fails, `run_spec` aborts immediately with an actionable `PlausibilityError` detailing the offending node, parameter, and physical reason.

---

## 8. Related Documentation

- [state.md](state.md) — How `run_spec` populates the persistent Geometry Dependency Graph.
- [workflow.md](workflow.md) — Comparing `run_spec` vs `run_recipe` vs direct tool calls.
- [parametric.md](parametric.md) — Expression bindings and formula evaluation.
- [tool_routing.md](tool_routing.md) — Spec vocabulary filtering for local LLMs.
