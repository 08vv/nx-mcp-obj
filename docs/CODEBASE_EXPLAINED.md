# NX-MCP Codebase — Complete Explained Documentation

This document provides a comprehensive, deeply detailed guide to the **NX-MCP** codebase, explaining its architecture, subsystems, data flow, tool inventory, bridge execution, and engineering guidelines.

---

## 1. High-Level System Overview

### Purpose and Value
NX-MCP connects AI coding agents directly to **Siemens NX**, a high-end mechanical CAD/CAM software suite. It translates JSON-RPC 2.0 tool requests, natural language instructions, and declarative CAD operation graphs into real-time NXOpen Python operations, allowing AI assistants to programmatically design, construct, inspect, and export fully parametric 3D CAD parts (`.prt` files).

### The Three Layers
1. **MCP Server Layer (`src/nx_mcp/server.py`, `router.py`, `registry.py`)**: Handles the standard MCP JSON-RPC protocol over `stdio` (or HTTP), parses incoming requests, manages dynamic tool routing, reflects Python function signatures into JSON Schema, and coordinates CAD Spec execution (`spec/`) and the Geometry Dependency Graph (`state/`).
2. **Tool Wrapper Layer (`src/nx_mcp/tools/*.py`)**: 154 modular CAD tools that validate inputs, check test/production modes via `_common.py`, and delegate CAD execution to the runner.
3. **Bridge & Native Execution Layer (`src/nx_mcp/bridge/runner.py`, `nx_bridge.py`)**: Runs across process boundaries. `runner.py` manages `ugraf.exe` process lifecycles and communicates over TCP port `43210` with `nx_bridge.py` (~6032 lines) executing natively inside Siemens NX.

---

## 2. Directory Layout & Key Modules

| Path | Purpose / Contents |
|---|---|
| `README.md` | Primary entry point with architectural summary, quick start, rules, and tool list. |
| `pyproject.toml` | Project configuration, entry points (`nx-mcp`, `nx-mcp-http`, `nx-mcp-nx`). |
| `prewarm_nx.py` | Standalone prewarm script to launch Siemens NX with the socket bridge preloaded. |
| `clean_junk.py` / `.bat` | Utility scripts to safely clean temporary logs, test cache, and build files. |
| `src/nx_mcp/server.py` | MCP JSON-RPC protocol dispatcher with routing and Escape Hatch. |
| `src/nx_mcp/router.py` | Keyword-based scoring router reducing tool schema token overhead by ~70%. |
| `src/nx_mcp/response.py` | `ToolResult` and `ToolError` response formatting classes. |
| `src/nx_mcp/tools/_common.py` | Centralized helpers (`_bridge_result`, `_use_mock_nxopen`). |
| `src/nx_mcp/tools/registry.py` | `@mcp_tool` registration decorator and JSON Schema reflection engine. |
| `src/nx_mcp/tools/modeling.py` | 34 solid modeling tools (cuboid, cylinder, cube, tube, extrude, cut, fillet, hole, pattern, shell, loft, expressions). |
| `src/nx_mcp/tools/sketch.py` | 16 sketch & curve tools (lines, rectangles, circles, splines, offset curve, close region, constraints, profiles). |
| `src/nx_mcp/tools/surface_modeling.py` | 52 surface modeling tools (sweeps, through curves, ruled, n-sided, face blends, trims, sheets). |
| `src/nx_mcp/tools/edit_operations.py` | 17 freeform editing tools (X-Form, I-Form, match edge, heal, variable offset). |
| `src/nx_mcp/tools/combine_operations.py` | 15 combine operations (sew, unsew, make solid, split body, divide face). |
| `src/nx_mcp/tools/file_ops.py` | 6 part file tools (`create_part`, `open_part`, `save_part`, `save_part_as`, `export_step`, `export_stl`). |
| `src/nx_mcp/tools/measure.py` | 5 measurement tools (distance, angle, volume, body volume, bounding box). |
| `src/nx_mcp/tools/utility.py` | 12 inspection and view tools (`set_view`, `fit_view`, `take_screenshot`, `list_features`, `inspect_part`, `run_nx_journal_code`). |
| `src/nx_mcp/tools/assembly.py` | 4 assembly tools (`add_component`, `list_components`, `mate_components`, `reposition_component`). |
| `src/nx_mcp/tools/recipe.py` | Multi-step recipe executor (`run_recipe`), CAD Spec executor (`run_spec`, `resume_spec`, `rerun_spec_node`). |
| `src/nx_mcp/tools/state_tools.py` | 4 Geometry Dependency Graph tools (`get_dependency_graph`, `get_downstream`, `get_upstream`, `validate_dependency_graph`). |
| `src/nx_mcp/tools/discovery.py` | Dynamic tool discovery (`get_relevant_nx_tools`) and coordinate utilities. |
| `src/nx_mcp/spec/` | Declarative CAD Spec DAG engine (schema, safe math calc, geometry math, plausibility, validator, executor, postcheck). |
| `src/nx_mcp/state/` | Persistent Geometry Dependency Graph tracking topological nodes, edges, entity lifecycles, and integrity. |
| `src/nx_mcp/bridge/runner.py` | Process manager, socket client, dynamic timeouts (60s/300s/180s), and launch mutexes. |
| `src/nx_mcp/bridge/nx_bridge.py` | In-NX execution engine (~6032 lines) running inside `ugraf.exe`. |
| `src/nx_mcp/testing/mock_nxopen.py` | Comprehensive mock NXOpen runtime for headless pytest execution (259 tests). |
| `docs/` | In-depth technical documentation suite. |

---

## 3. Subsystem Architecture & Invariants

### 1. In-NX Bridge Core Engine (`src/nx_mcp/bridge/nx_bridge.py`)
- **Event Loop**: Runs `run_socket_bridge()` on port `43210` using `select.select()` and regularly pumps NX GUI events via `ui.ProcessDeviceEvents()`.
- **State Tracking (`_state`)**: Tracks `features`, `bodies`, `sketches`, `last_curves`, `active_sketch`, `sketch_origin`, and `sketch_rotation`.
- **Session Boundary Isolation**: `_reset_transient_session_state()` clears all caches on `create_part` and `open_part`.
- **State Rollback**: `handle_line()` captures a deep snapshot of `_state` before dispatching. Any error triggers an immediate rollback to the pre-call state.
- **Parametric Hierarchy**: Dimensions are created as named input expressions (`_create_input_expression`) or formulas (`_create_formula_expression`) and bound to Feature Builders by name on the RightHandSide.
- **Instance Prefix System**: Automatically prefixes expressions (`CUBOID_1_L`, `CUBOID_2_L`) and seeds counters from existing parts via `_seed_counters_from_part` to avoid naming collisions.
- **Safety Preflights**: `_validate_hole_intersection()` runs AABB overlap checks before creating holes, and `_ensure_work_part()` prevents overwriting populated default fallback parts.

### 2. Runner & Process Synchronization (`src/nx_mcp/bridge/runner.py`)
- **Lock Management**: `NXBridgeProcess._lock` serializes all tool calls across threads.
- **Anti-Duplicate Launch Guard**: `_find_running_ugraf()` and `bridge.launching.lock` (`msvcrt.locking`) prevent multiple NX windows from spawning simultaneously.
- **Dynamic Timeouts**: 60s for standard modeling (`NX_MCP_SOCKET_TIMEOUT`), 300s for journaling/recipes (`NX_MCP_JOURNAL_TIMEOUT`), 180s for NX launch (`NX_MCP_LAUNCH_TIMEOUT`).
- **Auto-Open Integration**: Updates `latest_nx_result.txt` and generates `open_current_nx_result.cmd` and `open_latest_nx_result.vbs` after creating or opening parts.

### 3. Declarative CAD Spec Engine (`src/nx_mcp/spec/`)
- **DAG Execution (`run_spec`)**: Processes declarative CAD graphs with automatic dependency inference.
- **Symbolic Resolution**: Resolves `$node.body_id`, `$expr:NAME`, `$calc:EXPRESSION`, and pure math functions (`$fn:bolt_circle`, `$fn:polar_to_cartesian`).
- **Plausibility Preflight**: Catches physical impossibilities (negative sizes, extreme aspect ratios, out-of-bound holes) before calling NX.
- **Steppable & Resumable**: Pauses execution on demand (`resume_spec`) or selectively re-executes a node and its downstream dependents (`rerun_spec_node`).
- **Post-Execution Verification**: Checks manifold topology, face/edge counts, and double-consumption integrity.

### 4. Dynamic Router & Discovery (`router.py`, `discovery.py`)
- **Keyword Scoring**: Evaluates prompt tokens with weights (1.0 single word, 2.0 multi-word phrase). Matches against 8 functional CAD categories.
- **Escape Hatch**: If a client invokes an unexposed tool, `server.py` automatically unlocks and returns all 154 tools for future requests.
- **`get_relevant_nx_tools`**: Allows agents to programmatically query relevant tools based on their specific task description.

---

## 4. CAD Engineering Workflow & Rules for Agents

1. **Tool Discovery**: Always call `get_relevant_nx_tools` first to obtain the relevant tool subset.
2. **Dedicated Part Files**: Always call `create_part` with a unique descriptive name before creating geometry.
3. **MANDATORY PART PERSISTENCE**: Always call `save_part()` as the final step of every build. `create_part` only creates an in-memory session part; the `.prt` file is only written to disk after `save_part()` executes.
4. **Prewarm Retry Re-issuance**: If a tool fails because NX is not running, once NX is ready, re-issue the exact `create_part` call before building geometry. If a filename mismatch occurs, use `save_part_as(filename)` immediately.
5. **Sequential Recipes**: Use `run_recipe` to execute multi-feature parts (block + cuts + fillets + holes + save) in a single deterministic server-side call.
6. **Declarative Graphs**: Use `run_spec` when features require dynamic symbolic references (`$n1.body_id`), bolt circle calculations (`$fn:bolt_circle`), or preflight plausibility validation.
7. **Curves and Profiles**: For splines, blades, and variable-width curved profiles, use `draw_spline` + `offset_curve` + `close_curve_region` followed by `extrude` or `extrude_cut`.
8. **Mathematical Profiles**: For gears, cams, or helical geometry, use `run_nx_journal_code` with pre-computed mathematical formulas.
9. **Origin Semantics**: Primitives (`create_cuboid`, `create_cube`) place origins at the **corner** by default unless `centered=True` is specified.
10. **Fillet Guardrail**: If `add_fillet` or `edge_blend` fails or partially succeeds, check `list_features` first before retrying to verify whether target edges were already consumed.
11. **Honesty & Scope**: Never claim a requirement was met if it was skipped or substituted; disclose any omitted or modified detail explicitly.

---

## 5. Technical Documentation Index

- [INDEX.md](INDEX.md) — Master documentation index and reading guide.
- [architecture.md](architecture.md) — 3-layer architecture guide.
- [cad_spec_system.md](cad_spec_system.md) — Declarative CAD Spec DAG engine (`run_spec`).
- [state.md](state.md) — State management and Geometry Dependency Graph.
- [bridge.md](bridge.md) — In-NX bridge execution engine (`nx_bridge.py`).
- [runner.md](runner.md) — Process manager and socket communication.
- [parametric.md](parametric.md) — Parametric expressions and builder patterns.
- [tool_routing.md](tool_routing.md) — Dynamic tool router and keyword scoring.
- [tool_registry.md](tool_registry.md) — Tool registry and JSON schema reflection.
- [workflow.md](workflow.md) — Request lifecycle and recipe workflows.
- [limitations.md](limitations.md) — Known constraints, edge cases, and resolved issues.
- [nx_model_prompt_format.md](nx_model_prompt_format.md) — CAD prompt engineering guide.
- [codebase.md](codebase.md) — Developer and agent handbook.
