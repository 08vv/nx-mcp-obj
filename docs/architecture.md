# Architecture

## Overview

**NX-MCP** is a Model Context Protocol (MCP) server that connects AI coding agents (such as Claude, Cline, Cursor, or custom LLM orchestrators) directly to **Siemens NX CAD/CAM** software. It uses a structured 3-layer architecture designed to cleanly separate MCP protocol handling, tool validation, and live NXOpen execution.

NX-MCP supports two transport modes: **stdio** (the standard for MCP clients like Cline/Claude Desktop) and **HTTP** (via FastAPI in `http_server.py` for web/remote access).

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
│              │   141 Tools Registered  │                                    │
│              └────────────┬────────────┘                                    │
│                           │  Filtered by router.py (unless Escape Hatch)   │
│              ┌────────────▼────────────┐                                    │
│              │   Router / Discovery    │                                    │
│              │   (router.py,           │                                    │
│              │    discovery.py)        │                                    │
│              └────────────┬────────────┘                                    │
└───────────────────────────┼─────────────────────────────────────────────────┘
                            │  tool["fn"](**args)
┌───────────────────────────▼─────────────────────────────────────────────────┐
│  Layer 2: Tool Wrapper Layer (src/nx_mcp/tools/)                            │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐ ┌──────────────┐  │
│  │  file_ops    │ │  sketch      │ │  modeling          │ │  discovery   │  │
│  ├──────────────┤ ├──────────────┤ ├────────────────────┤ ├──────────────┤  │
│  │  assembly    │ │  measure     │ │  combine_operations│ │  recipe      │  │
│  ├──────────────┤ ├──────────────┤ ├────────────────────┤ ├──────────────┤  │
│  │  utility     │ │  _common.py  │ │  surface_modeling  │ │  edit_ops    │  │
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
   - Maintains `_session_state` (`active_routed_tool_names`, `escape_hatch_active`, `task_prompt`).
   - When routing is active (`NX_MCP_ENABLE_ROUTING=1`), queries `router.py` to filter the exposed tool schemas.
   - Implements the **Escape Hatch**: if an AI client invokes a tool not included in the filtered schema list, the server automatically re-exposes all 141 tools for subsequent requests.

2. **`router.py` & `discovery.py`**:
   - Provides keyword-based and task-based semantic categorization across 8 functional CAD domains.
   - Exposes `get_relevant_nx_tools` which allows an AI to dynamically query for relevant tools based on a task prompt, dramatically saving prompt tokens.

3. **`tools/registry.py`**:
   - Central tool catalog storing function references and metadata via the `@mcp_tool` decorator.
   - Automatically generates standards-compliant JSON Schemas by inspecting Python type annotations and docstrings.

---

### Layer 2: Tool Wrapper Layer

Located in `src/nx_mcp/tools/`, this layer exposes 141 discrete tools:

- **`_common.py`**: Shared helper module providing `_bridge_result()` (bridges execution to `runner.call_nx`) and `_use_mock_nxopen()` (checks if mock mode is active).
- **`modeling.py`** (27 tools): Solid modeling primitives (`create_cuboid`, `create_cylinder`), booleans (`boolean_unite`, `boolean_subtract`), features (`add_fillet`, `add_chamfer`, `add_hole`, `pattern_circular`, `revolve_cut`, `extrude_cut`).
- **`sketch.py`** (14 tools): 2D sketch plane operations, lines, rectangles, circles, splines (`draw_spline`), offset curves (`offset_curve`), closed region generation (`close_curve_region`), and constraints.
- **`surface_modeling.py`** (53 tools): Complex surface generation (Studio Surface, Swept, Through Curves, Ruled, N-Sided, Bounded Plane), surface trims, sheets, and extensions.
- **`combine_operations.py`** (15 tools): Sheet sewing/unsewing, solid body creation, face dividing, and boundary analysis.
- **`edit_operations.py`** (16 tools): Freeform surface manipulation (X-Form, I-Form, matching, smoothing, normal reversal).
- **`file_ops.py`** (5 tools): Part lifecycle management (`create_part`, `open_part`, `save_part`, `export_step`, `export_stl`).
- **`measure.py`** (5 tools): Distance, angle, volume, and bounding box queries.
- **`utility.py`** (8 tools): Viewport controls (`set_view`, `fit_view`), screenshot capture (`take_screenshot`), feature inspection (`list_features`, `list_feature_edges`, `inspect_part`), API introspection (`inspect_api`), and bridge reset (`reset_nx_bridge`).
- **`assembly.py`** (4 tools): Assembly component placement and mating.
- **`recipe.py`** (1 tool): Deterministic server-side multi-step sequential tool executor (`run_recipe`).

---

### Layer 3: Process & Socket Bridge Layer

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
   - Runs directly inside the Siemens NX process environment with native access to `NXOpen` and `NXOpen.UF`.
   - Maintains a non-blocking `select.select()` socket server event loop on TCP port `43210`.
   - Periodically calls `ui.ProcessDeviceEvents()` to keep the NX CAD GUI fully responsive.
   - Intercepts commands, creates state backup checkpoints, normalizes legacy parameter aliases, dispatches to builder handlers, commits CAD geometry, and executes automatic rollback if any error occurs.

---

## Environment & Dependency Constraints

| Component | Execution Context | Dependencies |
|---|---|---|
| **MCP Server** (`server.py`, `runner.py`, `tools/`) | Standard Python 3.10+ process | Python Standard Library (`json`, `socket`, `subprocess`, `threading`, `pathlib`, `select`, `msvcrt`). Optional: `fastapi`, `uvicorn` for HTTP. |
| **NX Bridge** (`nx_bridge.py`) | Siemens NX Embedded Python Runtime | `NXOpen`, `NXOpen.UF`, `NXOpen.Features`, `NXOpen.GeometricUtilities`. Ships exclusively with Siemens NX. |
| **Testing Harness** (`tests/`) | Pytest runner | `pytest`. In unit test mode (`NX_MCP_USE_MOCK_NXOPEN=1`), `nx_mcp/testing/mock_nxopen.py` mocks all NXOpen objects. |

---

## Related Documentation

- [bridge.md](bridge.md) — Comprehensive guide to `nx_bridge.py` internals.
- [runner.md](runner.md) — Process lifecycle, timeouts, and socket communication.
- [state.md](state.md) — Session state management, geometry caches, and rollback mechanics.
- [parametric.md](parametric.md) — NX Expression system, builder patterns, and formula variables.
- [tool_routing.md](tool_routing.md) — Dynamic tool filtering and category keyword matching.
- [tool_registry.md](tool_registry.md) — Tool registration and JSON Schema reflection.
- [workflow.md](workflow.md) — Complete end-to-end request lifecycle and recipe execution.
- [limitations.md](limitations.md) — Known constraints, technical debt, and future roadmap.
