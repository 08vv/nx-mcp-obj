# NX-MCP Codebase State Audit

Audit date: 2026-08-27. This document reflects the verified state of the working tree, source code, tests, and NX bridge architecture.

---

## 1. Architecture Overview

The production execution pipeline is **AI Agent → JSON-RPC `server.py` → Tool Wrapper (`tools/*.py`) → `bridge/runner.py` → Live `bridge/nx_bridge.py` inside Siemens NX (`ugraf.exe`)**.

- **Protocol**: MCP JSON-RPC 2.0 over `stdio` (primary) and optional FastAPI HTTP (`http_server.py`).
- **Dynamic Routing**: `router.py` filters `tools/list` responses using keyword weights, reducing prompt token consumption by ~70%. Includes an **Escape Hatch** in `server.py` to re-expose all 141 tools if an unrouted tool is invoked.
- **Process & Socket Bridge**: `runner.py` enforces thread synchronization via `NXBridgeProcess._lock`, guards against duplicate NX launches with `bridge.launching.lock` (`msvcrt.locking`), and transmits newline-delimited JSON commands over TCP port `43210`.
- **In-NX Execution**: `bridge/nx_bridge.py` (~6032 lines) runs inside Siemens NX, maintaining a non-blocking `select.select()` loop, UI event pumping (`ui.ProcessDeviceEvents()`), deep state backup/rollback in `handle_line()`, and 100% parametric expression bindings.
- **Timeouts**:
  - Socket command timeout: `NX_MCP_SOCKET_TIMEOUT`, default **60 s**.
  - Scripting & recipes (`exec_python_code`, `run_recipe`, `run_nx_journal_code`): `NX_MCP_JOURNAL_TIMEOUT`, default **300 s**.
  - NX launch & socket readiness: `NX_MCP_LAUNCH_TIMEOUT`, default **180 s**.

---

## 2. Registered Tool Inventory Summary (141 Tools Total)

| Category | Registered Count | Status & Key Capabilities |
|---|---:|---|
| **Modeling** (`modeling.py`) | 27 | Primitives (`create_cuboid`, `create_cylinder`, `create_cube`), `extrude`, `revolve`, `boolean_unite`, `boolean_subtract`, `add_fillet`, `add_chamfer`, `add_hole`, `add_hole_nx`, `pattern_circular`, `pattern_feature`, `mirror_feature`, `revolve_cut`, `extrude_cut`, `create_rib`, `split_body`, `emboss_body`, `edit_expression`. |
| **Sketch & Curves** (`sketch.py`) | 14 | 2D sketch plane, `draw_line`, `draw_rectangle`, `draw_circle`, `draw_arc`, `draw_rounded_rectangle`, `draw_spline` (Studio Spline), `offset_curve` (normal offset), `close_curve_region` (watertight boundary closure), sketch constraints. |
| **Surface Modeling** (`surface_modeling.py`) | 53 | Studio surface, sweeps, through-curves, ruled, n-sided, fill, bounded plane, trims, sheets, thicken, extensions, face blends. |
| **Combine Operations** (`combine_operations.py`) | 15 | Sheet sewing/unsewing, solid body creation (`make_solid`), face dividing, patch body, trim & extend, sheet boundary analysis. |
| **Edit Operations** (`edit_operations.py`) | 16 | Freeform editing: X-Form, I-Form, match edge, heal surface, normal reversal, enlarge face, deformation, shaping, smoothing. |
| **File Operations** (`file_ops.py`) | 5 | `create_part`, `open_part`, `save_part`, `export_step`, `export_stl`. |
| **Measurement** (`measure.py`) | 5 | `measure_distance`, `measure_angle`, `measure_volume`, `get_bounding_box`, `measure_body_volume`. |
| **Utility** (`utility.py`) | 8 | `set_view`, `fit_view`, `take_screenshot`, `list_features`, `list_feature_edges`, `inspect_part`, `inspect_api`, `reset_nx_bridge`. |
| **Assembly** (`assembly.py`) | 4 | `add_component`, `mate_components`, `reposition_component`, `list_components`. |
| **Recipe** (`recipe.py`) | 1 | `run_recipe` (Deterministic multi-step sequential CAD recipe executor). |
| **Discovery** (`discovery.py`) | 2 | `get_relevant_nx_tools` (Context-aware task discovery), `polar_to_cartesian_points`. |

---

## 3. Reliability & Hardening Mechanisms

1. **State Isolation on Part Boundaries**: `_reset_transient_session_state()` is automatically executed at the beginning of `create_part()` and `open_part()`, clearing cached features, bodies, curves, sketch planes, and counters to eliminate cross-part contamination.
2. **Dynamic In-Memory Rollback**: `handle_line()` captures a deep snapshot of `_state` prior to dispatching any command; if an error or exception occurs, the state is immediately restored to the snapshot.
3. **Expression Collision Prevention**: `_next_instance_prefix()` generates unique prefixes (e.g. `CUBOID_1`, `CUBOID_2`), and `_seed_counters_from_part()` seeds instance counters from existing part expressions upon opening.
4. **Hole Safety Preflight**: `_validate_hole_intersection()` runs an AABB overlap check with a 1mm margin to ensure hole cylinders intersect solid bodies, coupled with post-operation edge count validation.
5. **Anti-Duplicate Launch Guard**: `runner.py` uses OS process scanning (`_find_running_ugraf()`) and file mutex locking (`bridge.launching.lock` via `msvcrt.locking`) to prevent multiple NX GUI instances from spawning.
6. **Fallback Part Protection**: `_ensure_work_part()` inspects default fallback parts (`nx_mcp_result.prt`) for existing geometry and automatically assigns a new numbered fallback file (`nx_mcp_result_N.prt`) if populated.
7. **Consolidated Tool Helpers**: All tool modules use `src/nx_mcp/tools/_common.py` for uniform `_bridge_result()` handling and mock checks.

---

## 4. Test Suite & Verification

- **Pytest Suite**: All tests pass in mock mode (`NX_MCP_USE_MOCK_NXOPEN=1`), validating tool schemas, argument parsing, routing algorithms, escape hatch mechanics, and runner synchronization.
- **Live NX Verification**: Real geometry generation (cuboids, cylinders, studio splines, offset curves, closed regions, extrude cuts, hole patterns) is verified against live Siemens NX sessions via TCP socket communication.

---

## 5. Architectural Index

- [CURRENT_SYSTEM.md](CURRENT_SYSTEM.md) — Grand architecture map.
- [docs/architecture.md](docs/architecture.md) — 3-layer architecture guide.
- [docs/bridge.md](docs/bridge.md) — In-NX bridge execution engine (`nx_bridge.py`).
- [docs/runner.md](docs/runner.md) — Process manager and socket communication (`runner.py`).
- [docs/state.md](docs/state.md) — State management and rollback mechanics.
- [docs/tool_routing.md](docs/tool_routing.md) — Dynamic tool router and category matching.
- [docs/tool_registry.md](docs/tool_registry.md) — Tool registry and schema reflection.
- [docs/workflow.md](docs/workflow.md) — Request lifecycle and recipe workflows.
- [docs/parametric.md](docs/parametric.md) — Parametric expressions and builder patterns.
- [docs/limitations.md](docs/limitations.md) — Known constraints and technical debt.
