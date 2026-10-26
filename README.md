# NX-MCP — Siemens NX Model Context Protocol Server

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Protocol](https://img.shields.io/badge/MCP-2024--11--05-green.svg)](https://modelcontextprotocol.io/)
[![Siemens NX](https://img.shields.io/badge/CAD-Siemens%20NX-orange.svg)](https://www.plm.automation.siemens.com/global/en/products/nx/)
[![Tests](https://img.shields.io/badge/tests-259%20passed-brightgreen.svg)](tests/)

**NX-MCP** is an enterprise-grade Model Context Protocol (MCP) server that connects AI coding assistants and autonomous engineering agents (such as Claude, Cline, Cursor, or custom LLM orchestrators) directly to **Siemens NX CAD/CAM**.

It translates high-level natural language instructions, structured JSON-RPC tool requests, and declarative CAD operation graphs into native Siemens NX parametric CAD operations, producing production-ready, fully parametric 3D CAD files (`.prt`).

---

## Key Highlights

- **154 Registered MCP CAD Tools**: Covering solid modeling, 2D sketches, complex freeform surfaces, sheet operations, assembly, measurement, and viewport controls.
- **Socket-First Architecture**: High-speed, non-blocking TCP loopback IPC (`127.0.0.1:43210`) directly into an interactive `ugraf.exe` process running `nx_bridge.py`.
- **100% Parametric Expression Architecture**: Every geometric dimension is bound to native NX Expressions (`CUBOID_1_L`, `CYLINDER_1_DIA`), allowing downstream modifications via `edit_expression`.
- **Declarative CAD Spec Engine (`run_spec`)**: Execute complete DAG-based CAD operation graphs with symbolic reference resolution (`$n1.body_id`), preflight geometric plausibility validation, execution pause/resume, and post-execution geometric verification.
- **Persistent Geometry Dependency Graph**: Real-time state tracking of bodies, features, and curves, mapping consumption (`consumed_by`), production (`produced_by`), and modification (`modified_by`) with double-consumption integrity validation.
- **Dynamic Tool Router & Context Optimizer**: Keyword-scoring engine in `router.py` filters the active tool schema list from 154 down to the relevant ~30–45 tools per turn, reducing prompt token consumption by ~70% while providing an automatic **Escape Hatch** if an unrouted tool is invoked.
- **Sequential Recipe Execution (`run_recipe`)**: Multi-step CAD operations (base block + cuts + fillets + holes + save) run server-side in a single deterministic round-trip.
- **259 Mock Unit Tests**: Comprehensive test suite verifying all tools, routing, dependency graphs, and spec executors without requiring an active Siemens NX license.

---

## Architecture at a Glance

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

## 154 Registered Tools Across 8 Functional Categories

| Category | Count | Primary Capabilities & Key Tools |
|---|:---:|---|
| **Modeling** | 34 | Primitives (`create_cuboid`, `create_cylinder`, `create_cube`, `create_tube`), Booleans (`boolean_unite`, `boolean_subtract`, `boolean_combine`), Extrusions & Revolves (`extrude`, `revolve`, `extrude_cut`, `revolve_cut`), Detail Features (`add_fillet`, `add_chamfer`, `add_hole`, `add_hole_nx`, `create_rib`), Patterns (`pattern_circular`, `pattern_feature`, `mirror_feature`, `pattern`), Shell & Loft (`shell`, `loft`), Expressions (`create_expression`, `edit_expression`, `list_expressions`). |
| **Sketch & Curves** | 16 | 2D sketch plane setup (`create_sketch`, `create_real_sketch`), basic geometry (`draw_line`, `draw_rectangle`, `draw_rounded_rectangle`, `draw_circle`, `draw_arc`), splines & offsets (`draw_spline`, `offset_curve`, `close_curve_region`), geometric constraints (`add_constraint_horizontal`, `add_constraint_vertical`, `add_constraint_fixed`), wireframe profiles (`create_profile`, `polar_to_cartesian_points`). |
| **Surface Modeling** | 52 | Freeform surfaces (`studio_surface`, `create_through_curves`, `create_through_curve_mesh`, `create_swept`, `create_ruled`, `n_sided_surface`, `bounded_plane`), blends & transitions (`add_face_blend`, `aesthetic_face_blend`, `bridge_surface`, `blend_corner`), sheets (`thicken_sheet`, `trim_sheet`, `extend_sheet`, `sew_sheets`, `unsew_sheets`), advanced offsets (`offset_surface`, `variable_offset_face`). |
| **Edit Operations** | 17 | Freeform manipulation (`x_form`, `i_form`, `match_edge`, `edge_symmetry`, `global_shaping`, `global_deformation`, `flattening_forming`, `heal_surface`, `enlarge_face`, `reverse_normal`, `smooth_poles`, `variable_offset`). |
| **File Operations** | 6 | Part lifecycle management: `create_part`, `open_part`, `save_part`, `save_part_as`, `export_step`, `export_stl`. |
| **Measurement** | 5 | Geometric queries: `measure_distance`, `measure_angle`, `measure_volume`, `measure_body_volume`, `get_bounding_box`. |
| **Assembly** | 4 | Multi-component management: `add_component`, `list_components`, `mate_components`, `reposition_component`. |
| **Utility & State** | 20 | Viewport controls (`set_view`, `fit_view`, `take_screenshot`), Inspection (`list_features`, `list_feature_edges`, `inspect_part`, `inspect_api`, `get_active_part`), Bridge lifecycle (`reset_nx_bridge`), Journal execution (`run_nx_journal_code`), Discovery (`get_relevant_nx_tools`), Recipes & Specs (`run_recipe`, `run_spec`, `resume_spec`, `rerun_spec_node`), Dependency Graph (`get_dependency_graph`, `get_downstream`, `get_upstream`, `validate_dependency_graph`). |

---

## Quick Start

### 1. Prerequisites
- **Python 3.10+** (tested on 3.11/3.12).
- **Siemens NX** (e.g. NX 2206 or newer) installed with `UGII_BASE_DIR` configured in Windows environment variables.

### 2. Installation
Clone the repository and install dependencies in editable mode:
```powershell
git clone <repo-url> nx-mcp
cd nx-mcp
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e .
```

### 3. Run Unit Tests (Mock Mode)
All unit tests execute against `src/nx_mcp/testing/mock_nxopen.py` without requiring Siemens NX to be running:
```powershell
pytest
```
*Expected: 259 passed.*

### 4. Starting Siemens NX with Prewarm
To eliminate launch latency and avoid connection timeouts during agent sessions, prewarm NX:
```powershell
python prewarm_nx.py
```
This boots `ugraf.exe` and initializes the socket listener on TCP port `43210`.

### 5. Configuring Your AI Assistant (Cline / Claude Desktop)
Add the server entry to your MCP settings configuration:

```json
{
  "mcpServers": {
    "nx-mcp": {
      "command": "c:\\Users\\HP\\nx-mcp\\venv\\Scripts\\python.exe",
      "args": ["-m", "nx_mcp.server"],
      "env": {
        "UGII_BASE_DIR": "C:\\Program Files\\Siemens\\NX2206",
        "NX_MCP_ENABLE_ROUTING": "1",
        "NX_MCP_SOCKET_TIMEOUT": "60",
        "NX_MCP_JOURNAL_TIMEOUT": "300"
      }
    }
  }
}
```

---

## Critical Rules for AI Agents & Users

> [!IMPORTANT]
> **1. Mandatory Part Persistence (`save_part`)**
> `create_part` initializes a new part in Siemens NX **session memory only**; it does NOT write the `.prt` file to disk. You **MUST** call `save_part()` at the end of every modeling sequence or recipe.
>
> **2. Prewarm Retry Re-issuance**
> If a tool fails because NX was not running yet, once NX is prewarmed or ready, you **MUST** re-issue the original `create_part` call before building geometry. Never build on an unconfirmed default open part. If a name mismatch occurs, use `save_part_as(filename)` immediately.
>
> **3. Sequential Recipes (`run_recipe`)**
> For multi-step parts, send the feature sequence as a single `run_recipe` call. It executes deterministically server-side in one round trip.
>
> **4. Mathematical Profiles (`run_nx_journal_code`)**
> For mathematically defined curves (involute gear teeth, aerodynamic airfoils, cam profiles), use `run_nx_journal_code` with pre-computed math rather than chaining primitives.
>
> **5. Origin Semantics**
> `create_cuboid` and `create_cube` place their origin at the **corner** by default. Pass `centered=True` if you want the block centered on `(x, y, z)`.
>
> **6. Fillet / Blend Retries**
> If an `add_fillet` or `edge_blend` call fails or partially succeeds, do not retry blindly on the same body. Check `list_features` first to determine whether target edges were already consumed or modified.

---

## Documentation Index

Explore the comprehensive technical guides in the [`docs/`](docs/) directory:

- [**docs/INDEX.md**](docs/INDEX.md) — Master reading map and documentation hub.
- [**docs/architecture.md**](docs/architecture.md) — 3-layer architecture, subsystems, and data flow.
- [**docs/cad_spec_system.md**](docs/cad_spec_system.md) — Complete guide to the declarative CAD Spec DAG engine (`run_spec`).
- [**docs/bridge.md**](docs/bridge.md) — In-NX bridge execution engine (`nx_bridge.py`) deep dive.
- [**docs/runner.md**](docs/runner.md) — Process manager, socket communications, timeouts, and locks.
- [**docs/state.md**](docs/state.md) — State management: runtime `_state` and persistent Geometry Dependency Graph.
- [**docs/tool_routing.md**](docs/tool_routing.md) — Dynamic tool router, category scoring, and Escape Hatch.
- [**docs/tool_registry.md**](docs/tool_registry.md) — `@mcp_tool` registration and JSON Schema reflection.
- [**docs/workflow.md**](docs/workflow.md) — Request lifecycles, recipes, and error recovery.
- [**docs/parametric.md**](docs/parametric.md) — Expression hierarchy, builder patterns, and formula variables.
- [**docs/limitations.md**](docs/limitations.md) — Architectural scope, resolved bug fixes, and active constraints.
- [**docs/nx_model_prompt_format.md**](docs/nx_model_prompt_format.md) — Guidelines for drafting mechanical design specifications.
- [**docs/codebase.md**](docs/codebase.md) — Detailed developer and agent handbook.
- [**docs/CODEBASE_EXPLAINED.md**](docs/CODEBASE_EXPLAINED.md) — High-level explanatory walk-through of the codebase.
