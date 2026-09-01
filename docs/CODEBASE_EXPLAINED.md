# NX-MCP Codebase — Complete Explained Documentation

This document provides a comprehensive, deeply detailed guide to the **NX-MCP** codebase, explaining its architecture, subsystems, data flow, tool inventory, bridge execution, and engineering guidelines.

---

## 1. High-Level System Overview

### Purpose and Value
NX-MCP connects AI coding agents directly to **Siemens NX**, a high-end mechanical CAD/CAM software suite. It translates JSON-RPC 2.0 tool requests into real-time NXOpen Python operations, allowing AI assistants to programmatically design, construct, inspect, and export fully parametric 3D CAD parts (`.prt` files).

### The Three Layers
1. **MCP Server Layer (`src/nx_mcp/server.py`, `router.py`, `registry.py`)**: Handles the standard MCP JSON-RPC protocol over `stdio` (or HTTP), parses incoming requests, manages dynamic tool routing, and dynamically reflects Python function signatures into JSON Schema.
2. **Tool Wrapper Layer (`src/nx_mcp/tools/*.py`)**: 141 modular CAD tools that validate inputs, check test/production modes via `_common.py`, and delegate CAD execution to the runner.
3. **Bridge & Native Execution Layer (`src/nx_mcp/bridge/runner.py`, `nx_bridge.py`)**: Runs across process boundaries. `runner.py` manages `ugraf.exe` process lifecycles and communicates over TCP port `43210` with `nx_bridge.py` (~6032 lines) executing natively inside Siemens NX.

---

## 2. Directory Layout & Key Modules

| Path | Purpose / Contents |
|---|---|
| `CURRENT_SYSTEM.md` | Single-page grand architecture map and textual call path trace. |
| `CODEBASE_STATE.md` | Comprehensive codebase state audit, tool evidence status, and changelog. |
| `pyproject.toml` | Project configuration, entry points (`nx-mcp`, `nx-mcp-http`, `nx-mcp-nx`). |
| `prewarm_nx.py` | Standalone prewarm script to launch Siemens NX with the socket bridge preloaded. |
| `src/nx_mcp/server.py` | MCP JSON-RPC protocol dispatcher with routing and Escape Hatch. |
| `src/nx_mcp/router.py` | Keyword-based scoring router reducing tool schema token overhead by ~70%. |
| `src/nx_mcp/response.py` | `ToolResult` and `ToolError` response formatting classes. |
| `src/nx_mcp/tools/_common.py` | Centralized helpers (`_bridge_result`, `_use_mock_nxopen`). |
| `src/nx_mcp/tools/registry.py` | `@mcp_tool` registration decorator and JSON Schema reflection engine. |
| `src/nx_mcp/tools/modeling.py` | 27 solid modeling tools (cuboid, cylinder, extrude, cut, fillet, hole, pattern). |
| `src/nx_mcp/tools/sketch.py` | 14 sketch & curve tools (line, circle, spline, offset curve, close region). |
| `src/nx_mcp/tools/surface_modeling.py` | 53 surface modeling tools (sweeps, through curves, ruled, face blends). |
| `src/nx_mcp/tools/edit_operations.py` | 16 freeform editing tools (X-Form, I-Form, match edge, heal). |
| `src/nx_mcp/tools/combine_operations.py` | 15 combine operations (sew, unsew, make solid, split body). |
| `src/nx_mcp/tools/file_ops.py` | 5 part file tools (create_part, open_part, save_part, export_step, export_stl). |
| `src/nx_mcp/tools/measure.py` | 5 measurement tools (distance, angle, volume, bounding box). |
| `src/nx_mcp/tools/utility.py` | 8 inspection and view tools (set_view, take_screenshot, list_features, inspect_part). |
| `src/nx_mcp/tools/assembly.py` | 4 assembly tools (add_component, mate_components, reposition_component). |
| `src/nx_mcp/tools/recipe.py` | `run_recipe` multi-step sequential CAD recipe executor. |
| `src/nx_mcp/tools/discovery.py` | `get_relevant_nx_tools` dynamic schema discovery and coordinate utilities. |
| `src/nx_mcp/bridge/runner.py` | Process manager, socket client, timeouts (60s/300s), and launch mutexes. |
| `src/nx_mcp/bridge/nx_bridge.py` | In-NX execution engine (~6032 lines) running inside `ugraf.exe`. |
| `src/nx_mcp/testing/mock_nxopen.py` | Full mock NXOpen runtime for headless pytest execution. |
| `docs/` | In-depth technical documentation suite. |

---

## 3. Subsystem Architecture & Invariants

### 1. In-NX Bridge Core Engine (`src/nx_mcp/bridge/nx_bridge.py`)
- **Event Loop**: Runs `run_socket_bridge()` on port `43210` using `select.select()` and regularly pumps NX GUI events via `ui.ProcessDeviceEvents()`.
- **State Tracking (`_state`)**: Tracks `features`, `bodies`, `sketches`, `last_curves`, `active_sketch`, `sketch_origin`, and `sketch_rotation`.
- **Session Boundary Isolation**: `_reset_transient_session_state()` clears all caches on `create_part` and `open_part`.
- **State Rollback**: `handle_line()` captures a deep snapshot of `_state` before dispatching. Any error triggers an immediate rollback to the pre-call state.
- **Parametric Hierarchy**: Dimensions are created as named input expressions (`_create_input_expression`) or formulas (`_create_formula_expression`) and bound to Feature Builders by name on the RightHandSide.
- **Safety Preflights**: `_validate_hole_intersection()` runs AABB overlap checks before creating holes, and `_ensure_work_part()` prevents overwriting populated default fallback parts.

### 2. Runner & Process Synchronization (`src/nx_mcp/bridge/runner.py`)
- **Lock Management**: `NXBridgeProcess._lock` serializes all tool calls across threads.
- **Anti-Duplicate Launch Guard**: `_find_running_ugraf()` and `bridge.launching.lock` (`msvcrt.locking`) prevent multiple NX windows from spawning.
- **Dynamic Timeouts**: 60s for standard modeling (`NX_MCP_SOCKET_TIMEOUT`), 300s for journaling/recipes (`NX_MCP_JOURNAL_TIMEOUT`), 180s for NX launch (`NX_MCP_LAUNCH_TIMEOUT`).
- **Auto-Open Integration**: Updates `latest_nx_result.txt` and generates `open_current_nx_result.cmd` after creating or opening parts.

### 3. Dynamic Router & Discovery (`router.py`, `discovery.py`)
- **Keyword Scoring**: Evaluates prompt tokens with weights (1.0 single word, 2.0 multi-word phrase). Matches against 8 functional CAD categories.
- **Escape Hatch**: If a client invokes an unexposed tool, `server.py` automatically unlocks and returns all 141 tools for future requests.
- **`get_relevant_nx_tools`**: Allows agents to programmatically query relevant tools based on their specific task description.

---

## 4. CAD Engineering Workflow & Rules for Agents

1. **Tool Discovery**: Always call `get_relevant_nx_tools` first to obtain the relevant tool subset.
2. **Dedicated Part Files**: Always call `create_part` with a unique descriptive name before creating geometry.
3. **Sequential Recipes**: Use `run_recipe` to execute multi-feature parts (block + cuts + fillets + holes) in a single deterministic server-side call.
4. **Curves and Profiles**: For splines, blades, and variable-width curved profiles, use `draw_spline` + `offset_curve` + `close_curve_region` followed by `extrude` or `extrude_cut`.
5. **Mathematical Profiles**: For gears, cams, or helical geometry, use `run_nx_journal_code` with pre-computed mathematical formulas.
6. **Origin Semantics**: Primitives (`create_cuboid`, `create_cube`) place origins at the **corner** by default unless `centered=True` is specified.
7. **Post-Operation Verification**: Always run `inspect_part` or `take_screenshot` to verify feature counts, bodies, and geometry.

---

## 5. Technical Documentation Index

- [CURRENT_SYSTEM.md](../CURRENT_SYSTEM.md) — Grand architecture map.
- [CODEBASE_STATE.md](../CODEBASE_STATE.md) — Codebase state audit.
- [docs/architecture.md](architecture.md) — 3-layer architecture guide.
- [docs/bridge.md](bridge.md) — In-NX bridge execution engine.
- [docs/runner.md](runner.md) — Process manager and socket communication.
- [docs/state.md](state.md) — State management and rollback.
- [docs/tool_routing.md](tool_routing.md) — Dynamic tool router.
- [docs/tool_registry.md](tool_registry.md) — Tool registry and JSON schema reflection.
- [docs/workflow.md](workflow.md) — Request lifecycle and recipe workflows.
- [docs/parametric.md](parametric.md) — Parametric expressions and builder patterns.
- [docs/limitations.md](limitations.md) — Known constraints and scope.
