# Architecture

## Overview

**NX-MCP** is a high-performance Model Context Protocol (MCP) server that connects AI coding assistants and autonomous engineering agents directly to **Siemens NX CAD/CAM** software. It uses a structured 3-layer architecture designed to cleanly separate MCP protocol handling, tool validation, and live NXOpen execution.

NX-MCP supports two transport modes:
- **stdio** (the standard for MCP clients like Cline, Claude Desktop, and Cursor).
- **HTTP** (via FastAPI in `http_server.py` on port `8765` for web and remote network access).

---

## 3-Layer Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Layer 1: AI Client                              │
│                (Cline, Claude Desktop, Cursor, Custom Agent)                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │  JSON-RPC 2.0 (stdio or HTTP POST)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│  Layer 1: MCP Server Core (src/nx_mcp/)                                     │
│  ┌───────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐  │
│  │  server.py            │  │  http_server.py      │  │  response.py     │  │
│  │  (stdio JSON-RPC 2.0) │  │  (FastAPI / :8765)   │  │  ToolResult/Err  │  │
│  └───────────┬───────────┘  └──────────┬───────────┘  └──────────────────┘  │
│              │                         │                                    │
│              └────────────┬────────────┘                                    │
│                           │  handle(req)                                    │
│              ┌────────────▼────────────┐                                    │
│              │   ToolRegistry          │                                    │
│              │   (registry.py)         │                                    │
│              │   154 Tools Registered  │                                    │
│              └────────────┬────────────┘                                    │
│                           │  Filtered by router.py (unless Escape Hatch)   │
│              ┌────────────▼────────────┐                                    │
│              │   Router & Discovery    │                                    │
│              │   (router.py,           │                                    │
│              │    discovery.py)        │                                    │
│              └────────────┬────────────┘                                    │
│                           │                                                 │
│              ┌────────────▼────────────┐  ┌──────────────────────────────┐  │
│              │   CAD Spec Engine       │  │   State Dependency Graph     │  │
│              │   (spec/executor.py)    │  │   (state/dependency_graph.py)│  │
│              └────────────┬────────────┘  └──────────────────────────────┘  │
└───────────────────────────┼─────────────────────────────────────────────────┘
                            │  tool["fn"](**args)
┌───────────────────────────▼─────────────────────────────────────────────────┐
│  Layer 2: Tool Wrapper Layer (src/nx_mcp/tools/)                            │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐ ┌──────────────┐  │
│  │  file_ops    │ │  sketch      │ │  modeling          │ │  discovery   │  │
│  │  (6 tools)   │ │  (16 tools)  │ │  (34 tools)        │ │  (1 tool)    │  │
│  ├──────────────┤ ├──────────────┤ ├────────────────────┤ ├──────────────┤  │
│  │  assembly    │ │  measure     │ │  combine_operations│ │  recipe      │  │
│  │  (4 tools)   │ │  (5 tools)   │ │  (15 tools)        │ │  (4 tools)   │  │
│  ├──────────────┤ ├──────────────┤ ├────────────────────┤ ├──────────────┤  │
│  │  utility     │ │  state_tools │ │  surface_modeling  │ │  edit_ops    │  │
│  │  (12 tools)  │ │  (4 tools)   │ │  (52 tools)        │ │  (17 tools)  │  │
│  └──────────────┘ └──────────────┘ └────────────────────┘ └──────────────┘  │
│              │  runner.call_nx(tool, args) via _common._bridge_result()     │
└──────────────┼──────────────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────────────┐
│  Layer 3: Bridge Layer                                                      │
│                                                                             │
│  MCP Server Side (runner.py):         Siemens NX Side (nx_bridge.py):       │
│  ┌─────────────────────────────┐      ┌──────────────────────────────────┐  │
│  │  NXBridgeProcess            │ TCP  │  In-NX Bridge (~6032 lines)      │  │
│  │  - Thread mutex (_lock)     │:43210│  - run_socket_bridge() loop      │  │
│  │  - launch_interactive_nx()  │──────│  - handle_line() with rollback   │  │
│  │  - verify_nx_environment()  │◀─────│  - dispatch() + arg normalizer   │  │
│  │  - _call_socket()           │ JSON │  - NXOpen API builder executions │  │
│  │  - Watcher file updates     │Lines │  - Expression management         │  │
│  │                             │      │  - Transient state tracking      │  │
│  └─────────────────────────────┘      └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Breakdown of Layers

### Layer 1: MCP Protocol & Routing Layer

1. **`server.py`**:
   - Manages the standard `stdio` line loop, parsing incoming JSON-RPC 2.0 strings and dispatching `initialize`, `notifications/initialized`, `tools/list`, and `tools/call`.
   - Maintains session state (`active_routed_tool_names`, `escape_hatch_active`, `task_prompt`).
   - When routing is active (`NX_MCP_ENABLE_ROUTING=1`), queries `router.py` to filter the exposed tool schemas.
   - Implements the **Escape Hatch**: if an AI client invokes a tool not included in the filtered schema list, the server automatically re-exposes all 154 tools for subsequent requests.

2. **`router.py` & `discovery.py`**:
   - Provides keyword-based semantic categorization across 8 functional CAD domains.
   - Exposes `get_relevant_nx_tools`, allowing an AI agent to dynamically discover tools matching its specific task description, saving up to ~70% prompt tokens.
   - Exposes `get_spec_vocabulary` for filtering legal CAD Spec `op` values and `$fn:` geometry math functions.

3. **`tools/registry.py`**:
   - Central tool catalog storing function references and metadata via the `@mcp_tool` decorator.
   - Automatically reflects Python type annotations and docstrings into standards-compliant JSON Schemas.

4. **`spec/` (CAD Spec Engine)**:
   - Evaluates declarative CAD operation graphs (`run_spec`) with topological sorting, cycle detection, preflight plausibility validation, execution pause/resume (`resume_spec`), and node re-runs (`rerun_spec_node`).

5. **`state/` (Geometry Dependency Graph)**:
   - Tracks entity lifecycles (bodies, features, sketches, curves), topological relationships (`consumed_by`, `produced_by`, `modified_by`), and double-consumption integrity.

---

## Layer 2: Tool Wrapper Layer

Located in `src/nx_mcp/tools/`, this layer exposes **154 discrete tools**:

- **`_common.py`**: Shared helper module providing `_bridge_result()` (bridges execution to `runner.call_nx`) and `_use_mock_nxopen()` (checks if mock test mode is active).
- **`file_ops.py`** (6 tools): Part lifecycle management (`create_part`, `open_part`, `save_part`, `save_part_as`, `export_step`, `export_stl`).
- **`modeling.py`** (34 tools): Solid modeling primitives (`create_cuboid`, `create_cylinder`, `create_cube`, `create_tube`), Booleans (`boolean_unite`, `boolean_subtract`, `boolean_combine`), features (`add_fillet`, `add_chamfer`, `add_hole`, `add_hole_nx`, `pattern_circular`, `pattern_feature`, `mirror_feature`, `revolve_cut`, `extrude_cut`, `shell`, `loft`), and expressions (`create_expression`, `edit_expression`, `list_expressions`).
- **`sketch.py`** (16 tools): 2D sketch plane operations (`create_sketch`, `create_real_sketch`), primitives (`draw_line`, `draw_rectangle`, `draw_rounded_rectangle`, `draw_circle`, `draw_arc`), splines (`draw_spline`), offset curves (`offset_curve`), closed region generation (`close_curve_region`), constraints (`add_constraint_horizontal`, `add_constraint_vertical`, `add_constraint_fixed`), and profile creation (`create_profile`, `polar_to_cartesian_points`).
- **`surface_modeling.py`** (52 tools): Complex surface generation (Studio Surface, Swept, Through Curves, Ruled, N-Sided, Bounded Plane), surface trims, sheets, extensions, and face blends.
- **`combine_operations.py`** (15 tools): Sheet sewing/unsewing, solid body creation, face dividing, and boundary analysis.
- **`edit_operations.py`** (17 tools): Freeform surface manipulation (X-Form, I-Form, matching, smoothing, normal reversal, variable offset).
- **`measure.py`** (5 tools): Distance, angle, volume, body volume, and bounding box queries.
- **`utility.py`** (12 tools): Viewport controls (`set_view`, `fit_view`), screenshot capture (`take_screenshot`), feature inspection (`list_features`, `list_feature_edges`, `inspect_part`, `get_active_part`), API introspection (`inspect_api`), bridge reset (`reset_nx_bridge`), and journal execution (`run_nx_journal_code`).
- **`assembly.py`** (4 tools): Assembly component placement, component listing, and mating.
- **`recipe.py`** (4 tools): Multi-step sequential recipe executor (`run_recipe`), CAD Spec executor (`run_spec`), pause/resume (`resume_spec`), and selective node re-run (`rerun_spec_node`).
- **`state_tools.py`** (4 tools): Geometry dependency graph queries (`get_dependency_graph`, `get_downstream`, `get_upstream`, `validate_dependency_graph`).
- **`discovery.py`** (1 tool): Dynamic tool and spec vocabulary discovery (`get_relevant_nx_tools`).

---

## Layer 3: Process & Socket Bridge Layer

1. **`bridge/runner.py` (Server-Side Bridge Manager)**:
   - Coordinates NX process lifecycle and TCP socket communication on port `43210`.
   - Enforces execution serialization through `NXBridgeProcess._lock`.
   - Prevents duplicate NX launches using cross-process lock files (`bridge.launching.lock` via `msvcrt.locking`) and OS process checks (`_find_running_ugraf()`).
   - Dynamically manages socket timeouts:
     - Standard commands: `60s` (`NX_MCP_SOCKET_TIMEOUT`).
     - Scripting & recipes: `300s` (`NX_MCP_JOURNAL_TIMEOUT`).
     - Process launch: `180s` (`NX_MCP_LAUNCH_TIMEOUT`).
   - Automatically maintains external result artifacts (`latest_nx_result.txt`, `open_current_nx_result.cmd`, `open_latest_nx_result.vbs`).

2. **`bridge/nx_bridge.py` (In-NX Execution Engine ~6032 lines)**:
   - Runs directly inside the Siemens NX process environment (`ugraf.exe`) with native access to `NXOpen` and `NXOpen.UF`.
   - Maintains a non-blocking `select.select()` socket server event loop on TCP port `43210`.
   - Periodically calls `ui.ProcessDeviceEvents()` to keep the NX CAD GUI interactive.
   - Intercepts commands, creates state backup checkpoints, normalizes legacy parameter aliases, dispatches to builder handlers, commits CAD geometry, and executes automatic rollback if any error occurs.
   - Ensures 100% parametric expression bindings with automatic instance prefixing (`_next_instance_prefix`) and existing part counter seeding (`_seed_counters_from_part`).

---

## Environment & Dependency Constraints

| Component | Execution Context | Dependencies |
|---|---|---|
| **MCP Server** (`server.py`, `runner.py`, `tools/`, `spec/`, `state/`) | Standard Python 3.10+ process | Python Standard Library (`json`, `socket`, `subprocess`, `threading`, `pathlib`, `select`, `msvcrt`). Optional: `fastapi`, `uvicorn` for HTTP. |
| **NX Bridge** (`nx_bridge.py`) | Siemens NX Embedded Python Runtime | `NXOpen`, `NXOpen.UF`, `NXOpen.Features`, `NXOpen.GeometricUtilities`. Ships exclusively with Siemens NX. |
| **Testing Harness** (`tests/`) | Pytest runner | `pytest`. In unit test mode (`NX_MCP_USE_MOCK_NXOPEN=1`), `nx_mcp/testing/mock_nxopen.py` mocks all NXOpen objects. |

---

## Related Documentation

- [INDEX.md](INDEX.md) — Master documentation index.
- [bridge.md](bridge.md) — Comprehensive guide to `nx_bridge.py` internals.
- [runner.md](runner.md) — Process lifecycle, timeouts, and socket communication.
- [state.md](state.md) — Session state management, geometry caches, and rollback mechanics.
- [cad_spec_system.md](cad_spec_system.md) — Declarative CAD Spec engine (`run_spec`).
- [parametric.md](parametric.md) — NX Expression system, builder patterns, and formula variables.
- [tool_routing.md](tool_routing.md) — Dynamic tool filtering and category keyword matching.
- [tool_registry.md](tool_registry.md) — Tool registration and JSON Schema reflection.
- [workflow.md](workflow.md) — Complete end-to-end request lifecycle and recipe execution.
- [limitations.md](limitations.md) — Known constraints, technical debt, and future roadmap.
