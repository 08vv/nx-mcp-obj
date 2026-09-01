# NX-MCP Codebase — Complete Developer & Agent Handbook

---

## 1. High-Level Overview

### What This Project Does
**NX-MCP** is an enterprise-grade Model Context Protocol (MCP) server that connects AI coding assistants and autonomous engineering agents (such as Claude, Cline, Cursor, or Gemini) directly to **Siemens NX CAD/CAM software**. It translates high-level natural language instructions and structured JSON-RPC tool calls into native Siemens NX parametric CAD modeling operations, producing fully parametric `.prt` 3D CAD files.

### What Problem It Solves
Traditional mechanical CAD modeling requires human designers to manually interact with complex graphical interfaces, draw 2D sketches, apply geometric constraints, and configure feature parameters. NX-MCP **automates** this entire design lifecycle:
- Enables AI agents to programmatically generate 3D CAD parts from mechanical specifications.
- Implements 100% parametric expression bindings so that models can be dynamically resized and updated.
- Provides real-time part inspection, feature tree queries, edge detection, and viewport screenshots.

### High-Level Architecture Flow

```
┌─────────────────┐       MCP JSON-RPC 2.0 (stdio)        ┌─────────────────────────┐
│    AI Agent     │──────────────────────────────────────▶│  MCP Server (server.py) │
│ (Cline / Claude)│◀──────────────────────────────────────│  Tool Registry & Router │
└─────────────────┘                                       └────────────┬────────────┘
                                                                       │ tool["fn"](**args)
                                                                       ▼
                                                          ┌─────────────────────────┐
                                                          │   Tool Wrappers Layer   │
                                                          │  (src/nx_mcp/tools/*.py)│
                                                          └────────────┬────────────┘
                                                                       │ runner.call_nx()
                                                                       ▼
                                                          ┌─────────────────────────┐
                                                          │ Process & Socket Runner │
                                                          │ (bridge/runner.py)      │
                                                          └────────────┬────────────┘
                                                                       │ TCP Socket :43210
                                                                       ▼
                                                          ┌─────────────────────────┐
                                                          │   In-NX Socket Bridge   │
                                                          │ (bridge/nx_bridge.py)   │
                                                          │  Runs INSIDE ugraf.exe  │
                                                          └────────────┬────────────┘
                                                                       │ Native C++ API
                                                                       ▼
                                                          ┌─────────────────────────┐
                                                          │ Siemens NX Native CAD   │
                                                          │ Produces .prt Files     │
                                                          └─────────────────────────┘
```

---

## 2. Tech Stack & Environment

| Component | Technology | Role / Execution Details |
|---|---|---|
| **Language** | Python 3.10+ | Pure Python implementation across server, tools, and bridge. |
| **CAD Engine** | Siemens NX (e.g. NX2206) | Native mechanical CAD kernel running `ugraf.exe`. |
| **CAD API** | `NXOpen` & `NXOpen.UF` | Siemens NX Python bindings running inside NX process memory. |
| **Protocol** | MCP (Model Context Protocol) | Custom JSON-RPC 2.0 implementation over `stdio` (`2024-11-05` spec). |
| **IPC Transport** | Loopback TCP Socket | `127.0.0.1:43210` with non-blocking `select.select()` event loop. |
| **Optional HTTP** | FastAPI + Uvicorn | Optional HTTP server in `http_server.py` on port `8765`. |
| **Testing** | Pytest | Mock-based test harness (`NX_MCP_USE_MOCK_NXOPEN=1`). |

---

## 3. Directory Structure & File Map

```
c:\Users\HP\nx-mcp\
├── CURRENT_SYSTEM.md              # Grand architecture diagram & textual call path map
├── CODEBASE_STATE.md              # Full codebase state audit & tool status
├── pyproject.toml                 # Package configuration, entry points, dependencies
├── prewarm_nx.py                  # Standalone prewarm script to launch NX with bridge
│
├── src/nx_mcp/
│   ├── __init__.py                # Package initialization
│   ├── server.py                  # MCP Server entry point (JSON-RPC stdio handling)
│   ├── router.py                  # Dynamic keyword router for context optimization
│   ├── response.py                # ToolResult and ToolError response objects
│   ├── http_server.py             # Optional FastAPI HTTP transport
│   ├── nx_session.py              # Server-side NX session singleton
│   ├── nxopen_loader.py           # Loader for native or mock NXOpen
│   ├── cli_validate.py            # CLI validation utility
│   │
│   ├── tools/                     # 141 Registered MCP Tools
│   │   ├── _common.py             # Shared helpers (_bridge_result, _use_mock_nxopen)
│   │   ├── registry.py            # ToolRegistry and @mcp_tool decorator
│   │   ├── discovery.py           # get_relevant_nx_tools and coordinate conversion
│   │   ├── recipe.py              # run_recipe sequential multi-step tool runner
│   │   ├── modeling.py            # 27 solid modeling tools (cuboid, cylinder, extrude, cut, fillet...)
│   │   ├── sketch.py              # 14 sketch & curve tools (line, circle, spline, offset, close...)
│   │   ├── surface_modeling.py    # 53 surface tools (sweeps, lofts, trims, face blends...)
│   │   ├── edit_operations.py     # 16 freeform edit tools (X-Form, match edge, heal...)
│   │   ├── combine_operations.py  # 15 combine tools (sew, unsew, make solid, split body...)
│   │   ├── file_ops.py            # 5 part file tools (create, open, save, export...)
│   │   ├── measure.py             # 5 measurement tools (distance, angle, volume, bbox...)
│   │   ├── utility.py             # 8 inspection & view tools (viewport, screenshot, features...)
│   │   └── assembly.py            # 4 assembly tools (add component, mate...)
│   │
│   ├── bridge/                    # Bridge Subsystem
│   │   ├── runner.py              # Server-side process manager, socket client, timeouts, locks
│   │   └── nx_bridge.py           # In-NX execution engine (~6032 lines)
│   │
│   ├── journals/templates/        # Reusable CAD part templates (spur gear, impeller, etc.)
│   └── testing/mock_nxopen.py     # Comprehensive mock NXOpen module for pytest
│
├── docs/                          # In-depth architectural documentation
│   ├── architecture.md            # 3-layer architecture & subsystems
│   ├── bridge.md                  # In-NX bridge execution engine deep dive
│   ├── runner.md                  # Process management, sockets, and locks
│   ├── state.md                   # State dictionary, resets, and resolvers
│   ├── tool_routing.md            # Keyword scoring & escape hatch mechanics
│   ├── tool_registry.md           # Tool registration & reflection schemas
│   ├── workflow.md                # End-to-end request lifecycle & recipe execution
│   ├── parametric.md              # Expression hierarchy & feature builder patterns
│   └── limitations.md             # Known constraints, scope, and technical context
│
└── tests/                         # Pytest test suite (100+ tests)
```

---

## 4. Subsystems Deep Dive

### A. MCP Server & Dynamic Router (`server.py`, `router.py`)
- **`server.py`**: Manages the stdio event loop. Parses JSON-RPC 2.0 messages, executes protocol negotiation, enforces the tool registry, and hosts the **Escape Hatch**.
- **Dynamic Routing**: Keyword-scoring engine in `router.py` filters `tools/list` down to relevant categories (Modeling, Sketch, Surface, Combine, Edit, File, Measure, Utility) based on prompt tokens.
- **Escape Hatch**: If an agent requests a tool outside the active routed subset, `server.py` automatically re-exposes all 141 tools for all subsequent turns.

### B. Tool Wrapper Layer & Registry (`tools/`)
- Every tool is decorated with `@mcp_tool(name, description)`.
- Type annotations and `:param` docstrings are dynamically reflected into standard JSON Schema descriptors.
- All tools share `src/nx_mcp/tools/_common.py` to route execution cleanly through `runner.call_nx`.

### C. Runner Layer (`bridge/runner.py`)
- **Mutex Synchronization**: Uses `NXBridgeProcess._lock` for thread safety and `bridge.launching.lock` (`msvcrt.locking`) for cross-process launch protection.
- **Anti-Duplicate Launch Guard**: Scans active processes for `ugraf.exe` before spawning a new instance.
- **Dynamic Timeouts**:
  - Standard CAD Operations: `60s` (`NX_MCP_SOCKET_TIMEOUT`).
  - Journal & Recipe Operations: `300s` (`NX_MCP_JOURNAL_TIMEOUT`).
  - Process Launch: `180s` (`NX_MCP_LAUNCH_TIMEOUT`).
- **External Artifacts**: Generates `latest_nx_result.txt` and `open_current_nx_result.cmd` upon successful part creation/opening.

### D. In-NX Bridge Core Engine (`bridge/nx_bridge.py` ~6032 lines)
- **Execution Loop**: Listens on TCP port `43210` using `select.select()` and calls `ui.ProcessDeviceEvents()` to keep the NX GUI interactive.
- **State Management**: Tracks `_state` containing `features`, `bodies`, `sketches`, `last_curves`, `sketch_origin`, and `sketch_rotation`.
- **Session Isolation**: `_reset_transient_session_state()` clears all caches on `create_part` and `open_part` boundaries.
- **Rollback Safety**: `handle_line()` captures a deep copy of `_state` before executing any command; any error restores the exact previous state.
- **Expression Engine**: Creates input expressions (`_create_input_expression`) and formula expressions (`_create_formula_expression`), indexed via `_next_instance_prefix("FEATURE")`.
- **Reference Resolvers**: Resolves bodies, features, curves, and edges using normalized names (`_normalize_name()`) and geometric boundary heuristics.
- **Safety Preflights**: `_validate_hole_intersection()` runs AABB bounding box checks to guarantee hole cylinders intersect solid bodies.

---

## 5. Agent CAD Engineering Rules & Best Practices

When operating as an AI CAD engineer within NX-MCP, follow these rules:

1. **Tool Discovery First**: Always call `get_relevant_nx_tools` with your task description first to discover the best tools for the job.
2. **Explicit Part Creation**: Always call `create_part` with a unique descriptive filename at the start of a build. Never build onto an unconfirmed session part.
3. **Prefer Recipes (`run_recipe`)**: For multi-step parts (e.g. Block + Holes + Fillets), send the entire sequence as a single `run_recipe` call to execute deterministically in one round-trip.
4. **Curves & Profiles**: For splines, blades, cams, and variable-width curved profiles, use `draw_spline` + `offset_curve` + `close_curve_region` followed by `extrude` or `extrude_cut`.
5. **Raw Scripting for Mathematical Profiles**: For involute gears, helical paths, or complex mathematical formulas, use `run_nx_journal_code` with pre-computed math.
6. **Origin Semantics**: Remember that `create_cuboid` and `create_cube` place their origin at the **corner** by default unless `centered=True` is explicitly passed.
7. **Post-Build Inspection**: Always call `inspect_part` or `take_screenshot` after completing geometry to verify features and solid bodies.

---

## 6. Related Documentation Files

- [CURRENT_SYSTEM.md](../CURRENT_SYSTEM.md) — Comprehensive visual architecture map.
- [CODEBASE_STATE.md](../CODEBASE_STATE.md) — Full codebase state and tool audit.
- [architecture.md](architecture.md) — 3-layer architecture and data flow.
- [bridge.md](bridge.md) — In-NX bridge execution engine.
- [runner.md](runner.md) — Process manager and socket communication.
- [state.md](state.md) — State management and rollback mechanics.
- [tool_routing.md](tool_routing.md) — Dynamic tool router and category keyword matching.
- [tool_registry.md](tool_registry.md) — Tool registration and schema reflection.
- [workflow.md](workflow.md) — Request lifecycle and recipe workflows.
- [parametric.md](parametric.md) — Parametric expressions and builder patterns.
- [limitations.md](limitations.md) — Known constraints and technical debt.
