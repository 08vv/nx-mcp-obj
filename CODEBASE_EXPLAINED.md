# NX-MCP Codebase — Complete Explained Documentation

---

## 1. High-Level Overview

### What This Project Does

NX-MCP is a **bridge between an AI agent (like Gemini or Claude) and Siemens NX** — a professional CAD/CAE software used for mechanical engineering. It lets an AI send plain-English-style commands (like "create a cube 50mm" or "add a fillet of radius 3mm") and those commands get translated into real NX modeling operations that build actual 3D CAD part files (`.prt`).

### What Problem It Solves

Normally, building a 3D model in Siemens NX requires a human engineer clicking through menus, dragging features, and typing dimensions manually. This project **automates** that process: an AI agent can programmatically create, modify, and export parametric 3D CAD models without anyone touching the NX GUI. This enables AI-driven design, rapid prototyping from text descriptions, and batch CAD generation.

### Overall Flow

```
┌─────────────┐     JSON-RPC / stdio      ┌─────────────────┐
│  AI Agent    │  ─────────────────────►   │  MCP Server     │
│  (Gemini,    │                           │  (server.py)    │
│   Claude,    │  ◄─────────────────────   │  Tool Registry  │
│   etc.)      │     JSON-RPC response     │                 │
└─────────────┘                            └────────┬────────┘
                                                    │
                                    Tool function calls runner.call_nx()
                                                    │
                                                    ▼
                                           ┌────────────────┐
                                           │ Bridge Runner   │
                                           │ (runner.py)     │
                                           │                 │
                                           │ Socket :43210   │
                                           │ OR run_journal  │
                                           └────────┬────────┘
                                                    │
                                      JSON over TCP socket or stdin/stdout
                                                    │
                                                    ▼
                                           ┌────────────────┐
                                           │ NX Bridge       │
                                           │ (nx_bridge.py)  │
                                           │                 │
                                           │ Runs INSIDE     │
                                           │ Siemens NX      │
                                           │ process via     │
                                           │ NXOpen Python   │
                                           │ API             │
                                           └────────┬────────┘
                                                    │
                                             NXOpen API calls
                                                    │
                                                    ▼
                                           ┌────────────────┐
                                           │ Siemens NX      │
                                           │ (CAD Engine)    │
                                           │                 │
                                           │ Creates .prt    │
                                           │ model files     │
                                           └────────────────┘
```

---

## 2. Tech Stack & Dependencies

### Language

- **Python 3.10+** — the entire project is pure Python.

### Key Libraries / SDKs

| Library | Purpose |
|---------|---------|
| **NXOpen** (Siemens Python API) | The official Python SDK that ships with Siemens NX. It provides programmatic access to all NX modeling operations. This is NOT a pip-installable library — it only exists inside the Siemens NX installation directory and can only be imported when running inside the NX process (via `run_journal.exe` or `ugraf.exe -auto=`). |
| **NXOpen.UF** (User Function layer) | A lower-level Siemens API (the "UF" or "User Function" layer) used for operations like revolve, bounding box queries, and edge vertex queries. It predates NXOpen and offers some capabilities NXOpen doesn't directly expose. |
| **FastAPI + uvicorn** | Used only in `http_server.py` — an optional HTTP transport for the MCP server. Not the primary transport. These are NOT listed in `pyproject.toml` dependencies (meaning they'd need manual installation). |
| **pytest** | Listed as an optional dev dependency for running tests. |
| Standard library only | `json`, `socket`, `subprocess`, `threading`, `os`, `sys`, `math`, `ast`, `inspect`, `typing`, `pathlib`, `importlib`, `time`, `select`, `traceback`, `dataclasses` |

### How the MCP Server Is Structured

- **MCP SDK/Framework**: **None** — the server implements the MCP (Model Context Protocol) JSON-RPC 2.0 wire protocol **from scratch**, manually parsing JSON-RPC messages. It does NOT use the official `mcp` Python SDK.
- **Transport**: Primary transport is **stdio** (standard input/output). An optional **HTTP** transport exists via FastAPI (`http_server.py`).
- **Protocol version**: `2024-11-05`
- **Capabilities advertised**: `{"tools": {}}` — only tools, no resources or prompts.

### Config Files

| File | What It Controls |
|------|-----------------|
| `pyproject.toml` | Package metadata, entry points (`nx-mcp`, `nx-mcp-http`, `nx-mcp-nx`), Python version requirement (≥3.10), dev dependency (pytest) |
| `.env.example` | Shows that `NX_RUN_JOURNAL` should point to the NX `run_journal.exe` path. **Not actually loaded** — the code uses `UGII_BASE_DIR` environment variable instead. |
| `live_bridge_config.json` | Auto-generated at runtime. Contains `part_path` and `port` for the socket bridge server. Existence of this file tells NX bridge to run in socket mode vs. stdin mode. |
| `latest_nx_result.txt` | Auto-generated. Contains the absolute path to the last generated .prt file. Used by helper scripts to open the result. |
| `open_current_nx_result.cmd` | Auto-generated batch file that opens the latest result .prt in NX. |
| `open_latest_nx_result.vbs` | Auto-generated VBScript that does the same silently. |

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `UGII_BASE_DIR` | **Required in production.** Must point to the Siemens NX installation directory (e.g., `C:\Program Files\Siemens\NX2206`). The code searches for `run_journal.exe`, `ugraf.exe`, and `ugs_router.exe` under this path. |
| `NX_MCP_USE_MOCK_NXOPEN` | Set to `"1"` to use a mock NXOpen module for testing without Siemens NX installed. |
| `NX_MCP_ROOT` | Optional override for the project root directory. |
| `NX_MCP_DEBUG_LOGS` | Set to `"1"` to enable debug log files written to `scratch/`. |

---

## 3. Folder & File Map

### Directory Tree

```
nx-mcp/
├── src/
│   └── nx_mcp/                          # Main Python package
│       ├── __init__.py                   # Empty package marker
│       ├── server.py                     # ★ CORE: MCP server (stdio JSON-RPC)
│       ├── http_server.py                # Optional HTTP MCP transport
│       ├── nx_session.py                 # NXOpen session singleton (mock mode)
│       ├── nxopen_loader.py              # Loads real or mock NXOpen module
│       ├── response.py                   # ToolResult / ToolError dataclasses
│       ├── bridge/
│       │   ├── __init__.py               # Empty
│       │   ├── runner.py                 # ★ CORE: Bridges MCP server ↔ NX process
│       │   └── nx_bridge.py             # ★ CORE: 4035-line file that runs INSIDE NX
│       ├── tools/
│       │   ├── __init__.py               # Empty
│       │   ├── registry.py               # ★ CORE: @mcp_tool decorator + schema gen
│       │   ├── modeling.py               # Solid modeling tools (cube, extrude, etc.)
│       │   ├── sketch.py                 # Sketch/drawing tools (line, circle, etc.)
│       │   ├── file_ops.py               # File operations (create/open/save/export)
│       │   ├── assembly.py               # Assembly tools (add component, mate, etc.)
│       │   ├── measure.py                # Measurement tools (distance, angle, volume)
│       │   ├── utility.py                # Utility tools (view, screenshot, features)
│       │   ├── surface_modeling.py        # Surface/sheet body tools (sweep, loft, etc.)
│       │   ├── combine_operations.py      # Boolean + sheet combine operations
│       │   └── edit_operations.py         # Surface editing tools (heal, deform, etc.)
│       ├── utils/
│       │   ├── __init__.py               # Empty
│       │   └── geometry.py               # Point3d/Vector3d helper shortcuts
│       └── testing/
│           ├── __init__.py               # Empty
│           └── mock_nxopen.py            # Mock NXOpen module for tests
├── tests/
│   ├── conftest.py                       # Pytest config (sets mock env var)
│   ├── test_tools.py                     # Main test suite (~261 lines)
│   ├── test_nx_bridge.py                 # Bridge-specific tests
│   └── test_surface_tools.py             # Surface modeling tool tests
├── journals/                             # (inside src/nx_mcp/journals/)
│   ├── create_offset_linkage_arm.py      # ~55 journal/build scripts for complex parts
│   ├── create_mounting_plate_v*.py       # Multiple versions of mounting plate
│   ├── create_floral_soap.py            # Consumer product models
│   ├── create_toothbrush.py             # Consumer product models
│   ├── create_persil_bottle*.py         # Bottle modeling scripts
│   ├── ... (many more)                  # Each creates a specific part from scratch
│   └── validate_*.py                    # Validation/probe scripts
├── scratch/                              # Debug/test/exploration scripts
│   ├── test_*.py                        # One-off test scripts (~30 files)
│   ├── inspect_*.py                     # NXOpen API inspection scripts
│   └── debug_*.py                       # Debugging scripts
├── build_*.py                            # Standalone build scripts (~12 files)
│                                         # Each launches NX bridge + builds a specific part
├── live_validation/                      # Feature validation JSON results + test parts
├── docs/
│   └── nx_model_prompt_format.md        # Documentation on NX model prompt format
├── *.prt                                 # Generated NX part files (~30+ files)
├── *.log                                 # Journal execution log files
├── pyproject.toml                        # Project config
├── .env.example                          # Example environment config
└── TODO_NXOPEN_ROADMAP.md               # Development roadmap
```

### File-by-File Explanation

#### Core Logic Files

| File | Role | What's Inside |
|------|------|--------------|
| **`server.py`** | Core — MCP Server | The main entry point. Reads JSON-RPC messages from stdin, routes them to handlers. `handle()` function dispatches `initialize`, `tools/list`, and `tools/call` methods. `main()` sets up logging, verifies NX environment, then loops reading stdin. 70 lines. |
| **`runner.py`** | Core — Bridge Runner | The communication layer between the MCP server process and the NX process. Contains `NXBridgeProcess` class that manages a `run_journal.exe` subprocess OR connects via TCP socket to a live NX GUI session on port 43210. `call_nx()` is the main entry point. 280 lines. |
| **`nx_bridge.py`** | Core — NX Engine | **The largest and most important file (4035 lines, 155KB).** Runs INSIDE the Siemens NX process. Contains ALL actual NXOpen API calls — every create_cube, extrude, fillet, hole, boolean, revolve, pattern, mirror, etc. Also implements the socket server and stdin loop for receiving commands from the runner. Has `dispatch()` function that maps tool names to handler functions via `globals()`. |
| **`registry.py`** | Core — Tool Registry | Defines the `@mcp_tool` decorator that registers tool functions with their name and description. `_get_schema()` auto-generates JSON Schema from Python function signatures (type annotations + docstring `:param` lines). `ToolRegistry` class provides `list_tools()` and `get()`. 71 lines. |

#### Tool Definition Files (These define what the AI agent can call)

| File | Role | Tools Count | What's Inside |
|------|------|-------------|--------------|
| **`modeling.py`** | Solid modeling | ~20 tools | `create_cube`, `create_cuboid`, `create_cylinder`, `extrude`, `revolve`, `boolean_unite/subtract`, `add_fillet`, `add_chamfer`, `add_hole`, `mirror_feature`, `pattern_feature`, `pattern_circular`, `create_real_sketch`, `extrude_from_sketch`, `create_rib`, `edge_blend`, `chamfer`, `revolve_cut`, `extrude_cut`, `mirror_body_feature`. Each validates inputs then calls `runner.call_nx()`. |
| **`sketch.py`** | 2D drawing | ~10 tools | `create_sketch`, `draw_line`, `draw_rectangle`, `draw_circle`, `draw_arc`, `draw_rounded_rectangle`, `create_offset_linkage_arm`, `create_offset_plane`, `add_constraint_horizontal/vertical/fixed`. |
| **`file_ops.py`** | File I/O | 5 tools | `create_part`, `open_part`, `save_part`, `export_step`, `export_stl`. |
| **`assembly.py`** | Assembly | 4 tools | `add_component`, `list_components`, `mate_components`, `reposition_component`. |
| **`measure.py`** | Measurement | 5 tools | `measure_distance`, `measure_angle`, `measure_volume` (pure math), `get_bounding_box`, `measure_body_volume` (NX API). |
| **`utility.py`** | Utilities | 5 tools | `set_view`, `fit_view`, `reset_nx_bridge`, `take_screenshot`, `list_features`. |
| **`surface_modeling.py`** | Surfaces | ~30 tools | `create_base_surface`, `extrude_surface`, `create_swept`, `create_through_curves`, `thicken_sheet`, `offset_surface`, `fill_surface`, `bounded_plane`, and many more advanced surface operations. |
| **`combine_operations.py`** | Boolean/Sheet ops | ~14 tools | `boolean_combine`, `trim_sheet`, `sew_sheets`, `split_body`, `emboss_body`, `make_solid`, `sheet_boundary_analysis`, etc. |
| **`edit_operations.py`** | Surface editing | ~15 tools | `reverse_normal`, `x_form`, `i_form`, `match_edge`, `heal_surface`, `enlarge_face`, `smooth_poles`, etc. |

#### Helper/Utility Files

| File | Role | What's Inside |
|------|------|--------------|
| **`response.py`** | Helper | Two simple dataclasses: `ToolResult` (success) and `ToolError` (failure). Each has `__str__` and `is_ok()` methods. 13 lines. |
| **`nx_session.py`** | Helper | Singleton wrapper around NXOpen session. Used only in mock mode — in production, `nx_bridge.py` manages its own session directly. 31 lines. |
| **`nxopen_loader.py`** | Helper | Loads either real `NXOpen` module or mock `nx_mcp.testing.mock_nxopen` based on `NX_MCP_USE_MOCK_NXOPEN` env var. 26 lines. |
| **`geometry.py`** | Helper | `make_point()`, `make_vector()`, `plane_normal()` — shortcuts for NXOpen geometry objects. 13 lines. |
| **`mock_nxopen.py`** | Testing | A fake NXOpen module using `MagicMock`. Provides stub classes for `Session`, `Part`, `Features`, `Point3d`, `Vector3d`, etc. Used by pytest. 184 lines. |

#### Config/Boilerplate Files

| File | Role |
|------|------|
| `pyproject.toml` | Package build config and entry points |
| `.env.example` | Environment variable documentation |
| `__init__.py` (multiple) | Python package markers (all empty) |
| `conftest.py` | Sets `NX_MCP_USE_MOCK_NXOPEN=1` for all tests |

#### Build Scripts (Root-level `build_*.py`)

These are standalone Python scripts that connect to the NX bridge socket and send commands to build specific parts. They are NOT part of the MCP server — they're like "client scripts" that demonstrate what the AI agent would do. Examples: `build_offset_linkage_arm.py`, `build_floral_soap.py`, `build_toothbrush.py`, etc.

#### Journal Scripts (`src/nx_mcp/journals/`)

These are NX Journal scripts — Python files designed to run inside Siemens NX directly (via `run_journal.exe`). They contain hardcoded NXOpen API calls to build specific parts. They represent an earlier approach before the MCP tool abstraction was built. Some are used by the bridge for complex operations like `create_offset_linkage_arm`.

---

## 4. MCP Server Core

### Where the Server Is Defined

The MCP server lives in [`server.py`](file:///c:/Users/HP/nx-mcp/src/nx_mcp/server.py). It is started via the `nx-mcp` console script entry point (defined in `pyproject.toml` line 15: `nx-mcp = "nx_mcp.server:main"`).

### Server Initialization Flow

1. `main()` is called
2. Logging is configured (DEBUG level to stderr)
3. Tool modules are imported (line 3) — this triggers all `@mcp_tool` decorators, registering every tool
4. If not in mock mode, `verify_nx_environment()` checks that `UGII_BASE_DIR` is set and NX executables exist
5. Enters a `for line in sys.stdin` loop, reading JSON-RPC messages one per line

### MCP Protocol Handling

```python
def handle(req):
    method = req.get("method", "")
    
    "initialize"              → Returns protocol version, capabilities, server info
    "notifications/initialized" → Returns None (no response needed)
    "tools/list"              → Returns list of all registered tools with schemas
    "tools/call"              → Looks up tool by name, calls it, returns result
    anything else             → Returns error -32601 "Unknown method"
```

### Every MCP Tool Exposed

Here is the complete list of **all 108+ tools** registered via `@mcp_tool`:

#### File Operations (5)
| Tool Name | Description |
|-----------|-------------|
| `create_part` | Create a new empty NX part file |
| `open_part` | Open an existing NX part file by full path |
| `save_part` | Save the current work part |
| `export_step` | Export current part as STEP file |
| `export_stl` | Export current part as STL file |

#### Sketch/Drawing (10)
| Tool Name | Description |
|-----------|-------------|
| `create_sketch` | Create a new sketch on a plane XY/XZ/YZ |
| `draw_line` | Draw a line from x1,y1 to x2,y2 |
| `draw_rectangle` | Draw rectangle from corner x,y with width and height |
| `draw_circle` | Draw circle at cx,cy with radius |
| `draw_arc` | Draw arc at cx,cy with radius from start_angle to end_angle degrees |
| `draw_rounded_rectangle` | Draw closed rounded-rectangle (stadium) profile |
| `create_offset_linkage_arm` | Create a fully parametric offset linkage arm |
| `create_offset_plane` | Create an offset datum plane from XY/XZ/YZ |
| `add_constraint_horizontal` | Add horizontal constraint to sketch curve |
| `add_constraint_vertical` | Add vertical constraint to sketch curve |
| `add_constraint_fixed` | Add fixed/anchor constraint to sketch curve |

#### Solid Modeling (20)
| Tool Name | Description |
|-----------|-------------|
| `create_cube` | Create cube with side length |
| `create_cuboid` | Create cuboid with length/width/height |
| `create_two_cuboids` | Create two cuboids next to each other |
| `create_cylinder` | Create cylinder with radius/height |
| `extrude` | Extrude active sketch curves by distance |
| `revolve` | Revolve active sketch around axis |
| `boolean_unite` | Unite two solid bodies |
| `boolean_subtract` | Subtract tool body from target body |
| `add_fillet` | Add edge fillet with radius |
| `add_chamfer` | Add chamfer with offset |
| `add_hole` | Add hole at position with diameter/depth |
| `mirror_feature` | Mirror feature about a plane |
| `pattern_feature` | Linear pattern of features |
| `create_real_sketch` | Create constrained NX Sketch on plane |
| `extrude_from_sketch` | Extrude a named sketch |
| `add_hole_nx` | Alias for add_hole |
| `create_rib` | Create rib/web feature |
| `pattern_circular` | Circular pattern of features |
| `edge_blend` | Fillet edges by selection |
| `chamfer` | Chamfer edges by selection |
| `revolve_cut` | Revolve to cut/remove material |
| `extrude_cut` | Extrude to cut/remove material |
| `mirror_body_feature` | Mirror feature (alias) |
| `edit_expression` | Edit named NX expression and update model |

#### Surface Modeling (30+)
`create_base_surface`, `extrude_surface`, `create_swept`, `create_through_curves`, `create_through_curve_mesh`, `add_face_blend`, `offset_surface`, `thicken_sheet`, `sweep_along_guide`, `variational_sweep`, `create_tube`, `swept_volume`, `create_ruled`, `n_sided_surface`, `fill_surface`, `bounded_plane`, `patch_openings`, `variable_offset`, `sheet_from_curve`, `law_extension`, `studio_surface`, `styled_sweep`, `section_surface`, `aesthetic_face_blend`, `bridge_surface`, `blend_corner`, `styled_corner`, `four_point_surface`, `rapid_surfacing`, `fit_surface`, `variable_offset_face`, `extension_surface`, `silhouette_flange`, `face_pairs`, `user_defined_surface`, `offset_surface_advanced`, `bisector_surface`, `surface_from_poles`, `surface_through_points`, `ribbon_builder`

#### Combine Operations (14)
`boolean_combine`, `trim_sheet`, `extend_sheet`, `trim_and_extend`, `sew_sheets`, `split_body`, `divide_face`, `snip_surface`, `untrim_sheet`, `delete_edge`, `emboss_body`, `patch_body`, `unsew_sheets`, `make_solid`, `sheet_boundary_analysis`, `quilt_sheets`

#### Edit Operations (15)
`reverse_normal`, `local_untrim_extend`, `replace_edge`, `x_form`, `i_form`, `match_edge`, `edge_symmetry`, `global_shaping`, `global_deformation`, `flattening_forming`, `heal_surface`, `edit_uv_direction`, `enlarge_face`, `snip_into_patches`, `smooth_poles`, `refit_face`

#### Assembly (4)
`add_component`, `list_components`, `mate_components`, `reposition_component`

#### Measurement (5)
`measure_distance`, `measure_angle`, `measure_volume`, `get_bounding_box`, `measure_body_volume`

#### Utility (5)
`set_view`, `fit_view`, `reset_nx_bridge`, `take_screenshot`, `list_features`

### MCP Resources / Prompts

**None.** The server only exposes tools. No MCP resources or prompts are defined.

### Full Request Lifecycle (Traced Step by Step)

Let's trace what happens when an AI agent calls `create_cube` with `size=50`:

1. **Agent sends JSON-RPC** over stdin:
   ```json
   {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"create_cube","arguments":{"size":50}}}
   ```

2. **`server.py` `main()`** reads the line from `sys.stdin`, parses JSON

3. **`handle(req)`** is called, sees `method == "tools/call"`, extracts `name="create_cube"` and `args={"size":50}`

4. **`ToolRegistry.get("create_cube")`** returns the registered function reference

5. **`tool["fn"](**args)`** calls `modeling.create_cube(size=50)`

6. **`modeling.create_cube()`** (line 20-35 of modeling.py):
   - Validates `size > 0` ✓
   - Checks `_use_mock_nxopen()` — if False (production), calls `runner.call_nx("create_cube", {"size": 50, "x": 0, "y": 0, "z": 0})`

7. **`runner.call_nx()`** → **`NXBridgeProcess.call()`** (line 195 of runner.py):
   - Calls `verify_nx_environment()` to check NX executables exist
   - Tries to connect to socket on port 43210 (live NX GUI mode)
   - If socket exists: sends `{"tool":"create_cube","args":{"size":50,...}}\n` over TCP
   - If no socket: falls back to batch mode via `run_journal.exe` subprocess

8. **`nx_bridge.py` receives the command** (either via socket in `run_socket_bridge()` or via stdin in `main()`)
   - `handle_line()` parses JSON, calls `dispatch()`
   - `dispatch()` does `globals().get("create_cube")` → finds the `create_cube` function
   - Calls `create_cube(size=50, x=0, y=0, z=0)`

9. **`nx_bridge.create_cube()`** (line 1365 of nx_bridge.py):
   - Calls `_ensure_work_part()` — creates a default part if none open
   - Creates an NX expression: `CUBE_SIZE_1 = 50`
   - Creates a `BlockFeatureBuilder`, sets origin and edge lengths using the expression name
   - Calls `builder.CommitFeature()` — NX builds the actual 3D cube
   - `_remember_feature(feature)` stores reference for later operations
   - `fit_view()` adjusts the viewport
   - Returns `{"ok": true, "message": "Cube 50mm at (0,0,0)"}`

10. **Response flows back**: nx_bridge → socket/stdout → runner → modeling.py → `_bridge_result()` → `ToolResult("Cube 50mm at (0,0,0)")`

11. **`server.py`** wraps it: `{"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"OK: Cube 50mm at (0,0,0)"}]}}`

12. **Written to stdout** → AI agent receives it

---

## 5. NX Integration Layer

### How This Code Talks to Siemens NX

The code uses **NXOpen Python API** — this is the official Siemens-provided Python bindings for NX automation. The key APIs used are:

1. **`NXOpen`** — The main managed API. Provides builders for features (extrude, revolve, block, cylinder, fillet, chamfer, hole, mirror, pattern), sections, curves, sketches, expressions, assemblies, measurement, and file I/O.

2. **`NXOpen.UF`** (User Function) — The older C-style API accessed via `UFSession`. Used for:
   - `UF.Modl.CreateRevolution()` — revolve operations
   - `UF.Modl.AskBoundingBox()` — body bounding box queries  
   - `UF.Modeling.AskEdgeVerts()` — edge endpoint queries
   - `UF.Modeling.AskPointContainment()` — point-in-body checks
   - `UF.Csys` — coordinate system operations
   - `UF.Curve.CreateArc()` — arc creation

### Session / Connection Handling

There are **two execution modes**:

#### Mode 1: Live GUI Socket (Primary)
- `runner.py` launches `ugraf.exe -auto=nx_bridge.py` which opens the NX GUI and runs `nx_bridge.py` as an auto-startup journal
- `nx_bridge.py` starts a TCP socket server on **port 43210** (localhost only)
- Commands are sent as JSON over TCP, responses returned the same way
- NX GUI stays open and visible — you can see the model being built in real-time
- The socket server runs in a polling loop with `time.sleep(0.01)`, processing UI events between commands

#### Mode 2: Batch via run_journal.exe (Fallback)
- `runner.py` starts `run_journal.exe nx_bridge.py` as a subprocess
- Commands sent via subprocess stdin, responses read from stdout
- NX runs headlessly (no GUI window)
- Used when the socket server isn't available

### Session Initialization (Inside NX)

```python
# nx_bridge.py, line 42-43 (runs at import time inside NX)
SESSION = NXOpen.Session.GetSession()
UF_SESSION = NXOpen.UF.UFSession.GetUFSession()
```

These are **global singletons** — there is exactly one NX session per NX process. They are created when the script loads and live for the entire session.

### How Parts Are Created / Opened / Saved

```python
# Create new part:
SESSION.Parts.NewDisplay(filename, NXOpen.Part.Units.Millimeters)

# Open existing:
SESSION.Parts.OpenDisplay(filepath)  # Opens AND makes it the active display part

# Save:
work_part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
               NXOpen.BasePart.CloseAfterSave.FalseValue)
```

After each file operation, `_update_result_files()` writes the file path to `latest_nx_result.txt` and generates `open_current_nx_result.cmd` so you can double-click to open the result.

### Error Handling

- **NX not running**: `verify_nx_environment()` checks for executables at startup. If `UGII_BASE_DIR` is not set or executables are missing, the server exits with an error.
- **Command fails inside NX**: `handle_line()` wraps every command in try/except. If an NXOpen API call throws, the error message and traceback are captured and returned as `{"ok": false, "error": "...", "traceback": "..."}`. The `_state` dictionary is **rolled back** to its pre-command snapshot on error.
- **Socket connection fails**: Returns `{"ok": false, "error": "Socket communication error: ..."}`.
- **NX bridge process crashes**: `runner.py` detects an empty response from stdout and returns `{"ok": false, "error": "NX bridge process exited"}`.

---

## 6. Parametric Modeling Logic

This is the heart of the system. Here's how parameters flow through the code.

### How Parameters Are Defined and Injected

The NX parametric system revolves around **NX Expressions** — named variables stored inside the part file. When you create a feature using an expression name instead of a raw number, the feature becomes parametric: changing the expression value later will automatically update the feature.

#### The Expression Creation Pattern

The key function is `_create_named_expression()` in `nx_bridge.py` (line 162):

```python
def _create_named_expression(work_part, prefix, value):
    # Generates unique name like "CUBOID_L_1", "CUBOID_L_2", etc.
    for counter in range(start, start + 1000):
        name = f"{prefix}_{counter}"
        try:
            work_part.Expressions.FindObject(name)  # Already exists? Skip
        except Exception:
            # Doesn't exist — create it
            work_part.Expressions.CreateExpression("Number", f"{name} = {value}")
            return name
```

This function:
1. Takes a prefix (e.g., `"CUBOID_L"`) and a numeric value (e.g., `40.0`)
2. Generates a unique expression name by appending a counter (e.g., `CUBOID_L_1`)
3. Creates the expression inside the NX part: `CUBOID_L_1 = 40.0`
4. Returns the expression name to be used in feature builders

#### Parameter Flow Example: `create_cuboid(length=120, width=60, height=10)`

1. **User/agent sends**: `length=120, width=60, height=10`

2. **`modeling.create_cuboid()`** validates inputs, calls `runner.call_nx("create_cuboid", {...})`

3. **`nx_bridge.create_cuboid()`** (line 1308):
   ```python
   l_name = _create_named_expression(work_part, "CUBOID_L", 120)  # → "CUBOID_L_1"
   w_name = _create_named_expression(work_part, "CUBOID_W", 60)   # → "CUBOID_W_1"
   h_name = _create_named_expression(work_part, "CUBOID_H", 10)   # → "CUBOID_H_1"
   ```

4. **Feature builder uses expression names**:
   ```python
   builder = work_part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
   builder.SetOriginAndLengths(origin, l_name, w_name, h_name)
   # ↑ NX internally links this block's dimensions to the expressions
   feature = builder.CommitFeature()
   ```

5. **Model regenerates** — NX builds the 3D box. If you later call `edit_expression("CUBOID_L_1", "200")`, the box will stretch to 200mm.

### Every Parametric Feature Supported

| Feature | Code Location | How Parameters Are Used |
|---------|--------------|------------------------|
| **Block (Cube/Cuboid)** | `create_cube()`, `create_cuboid()` | `CUBE_SIZE`, `CUBOID_L/W/H` expressions → `BlockFeatureBuilder.SetOriginAndLengths()` |
| **Cylinder** | `create_cylinder()` | `CYLINDER_R`, `CYLINDER_H` expressions → `CylinderBuilder.Diameter.RightHandSide = "2 * CYLINDER_R_1"` |
| **Extrude** | `extrude()`, `extrude_from_sketch()` | `EXTRUDE_DIST`, `EXTRUDE_START` expressions → `ExtrudeBuilder.Limits.EndExtend.Value.RightHandSide` |
| **Revolve** | `revolve()` | Angle passed as string → `UF.Modl.CreateRevolution()` limits parameter |
| **Fillet (Edge Blend)** | `add_fillet()` | `FILLET_R` expression → `EdgeBlendBuilder.AddChainset(collector, r_name)` |
| **Chamfer** | `add_chamfer()` | `CHAMFER_OFFSET` expression → `ChamferBuilder.FirstOffset = offset_name` |
| **Hole** | `add_hole()`, `add_hole_nx()` | `HOLE_D`, `HOLE_DEPTH` expressions → `HoleBuilder.Diameter.RightHandSide` or cylinder-subtract fallback |
| **Boolean (Unite/Subtract)** | `boolean_unite()`, `boolean_subtract()` | No expressions — operates on body references |
| **Mirror** | `mirror_feature()` | Creates datum plane on specified plane, mirrors selected feature |
| **Linear Pattern** | `pattern_feature()` | `PATTERN_COUNT`, `PATTERN_PITCH` expressions → `PatternService.RectangularDefinition` |
| **Circular Pattern** | `pattern_circular()` | `CIRC_PATTERN_COUNT`, `CIRC_ANGLE_TOTAL` expressions → `PatternService.CircularDefinition` |
| **Extrude Cut** | `extrude_cut()` | Same as extrude but with `BooleanType.Subtract` |
| **Revolve Cut** | `revolve_cut()` | Same as revolve but subtracts from target body |
| **Rib** | `create_rib()` | `RIB_THICK` expression → `RibBuilder.Thickness.RightHandSide` |
| **Edit Expression** | `edit_expression()` | Finds existing expression, sets `RightHandSide`, calls `UpdateManager.DoUpdate()` to regenerate all features |

### How NX Expressions Keep Models Parametric

When you create a feature using expression **names** (like `"CUBOID_L_1"`) instead of raw strings (like `"120"`), NX stores a **link** between the feature dimension and the expression. This means:

1. The expression appears in NX's Expression Editor
2. Changing the expression value (via `edit_expression` tool or manually in NX) automatically updates the feature
3. Expressions can reference other expressions: `"2 * CYLINDER_R_1"` makes the diameter always twice the radius
4. The model remains **fully editable** in NX's native UI

### Expression Evaluation System

The `_eval_val()` function (line 87) handles flexible parameter input:

```python
def _eval_val(val):
    # 1. None → 0.0
    # 2. int/float → direct conversion
    # 3. String → try float() first
    # 4. If string contains math → try NX expression evaluation
    # 5. If that fails → use _safe_math_eval() (AST-based safe eval)
```

This means parameters can be passed as numbers, strings, or even math expressions like `"ARM_LENGTH - 2 * END_RADIUS"`.

### The Offset Linkage Arm — A Complete Parametric Example

The `create_offset_linkage_arm()` function (line 992) is the best example of full parametric modeling. It:

1. **Defines 10 named parameters** as NX Expressions:
   ```
   ARM_LENGTH=90, ARM_WIDTH=24, ARM_THICK=8, END_RADIUS=12,
   HOLE_DIA=10, HOLE_OFFSET=12, CYLINDER_DIA=22, CYLINDER_HEIGHT=55,
   BLEND_RADIUS=2, CHAMFER_OFFSET=0.5
   ```

2. **Derives geometry** from those parameters (all calculated, not hardcoded):
   ```python
   ARM_SPAN = ARM_L - 2.0 * END_R    # 66.0
   LOWER_LEFT_ARC_X = -HOLE_O         # -12.0
   Z_UPPER_TOP = ARM_T + CYL_H + ARM_T  # 71.0
   ```

3. **Builds geometry step by step**:
   - Draws rounded-rectangle profile for lower arm → extrudes 8mm
   - Draws circle → extrudes cylinder from 8mm to 63mm → unites with lower arm
   - Draws rotated profile for upper arm at Z=63 → extrudes 8mm → unites
   - Subtracts 4 holes using parametric cylinders
   - Applies fillet and chamfer to edges

4. **All dimensions are linked** to the NX expressions — changing `ARM_LENGTH` would resize the entire part proportionally.

### Constraints and Dependencies

- Parameter dependencies are **implicit** — they exist in the Python code's arithmetic, not in NX's expression system. For example, `ARM_SPAN = ARM_L - 2.0 * END_R` is calculated in Python and used as a literal value, NOT as an NX expression formula.
- There is no formal constraint system or dependency graph between parameters.
- Edge selection for fillets/chamfers uses geometric queries (bounding box, edge alignment) rather than persistent references, which can be fragile if the model topology changes.

### Template/Master Model Pattern

**No template pattern is used.** Every part is built from scratch by creating a new empty `.prt` file and adding features one by one. There is no master/template part that gets parameters injected into it.

---

## 7. Data Flow Diagram (Text-Based)

```
┌──────────────────┐
│ Agent/User        │
│ Request           │
│ "create a cube    │
│  50mm with 3mm    │
│  fillets"         │
└────────┬─────────┘
         │ tools/call JSON-RPC (stdin)
         ▼
┌──────────────────┐
│ MCP Server        │
│ server.py         │
│                   │
│ handle() routes   │
│ to ToolRegistry   │
└────────┬─────────┘
         │ tool["fn"](**args)
         ▼
┌──────────────────┐
│ Tool Function     │
│ modeling.py       │
│                   │
│ Input validation  │
│ (size > 0, etc.)  │
└────────┬─────────┘
         │ runner.call_nx("create_cube", {...})
         ▼
┌──────────────────┐
│ Bridge Runner     │
│ runner.py         │
│                   │
│ Try socket:43210  │
│ OR run_journal    │
│ subprocess        │
└────────┬─────────┘
         │ JSON over TCP socket or stdin pipe
         ▼
┌──────────────────┐
│ NX Bridge         │
│ nx_bridge.py      │
│ (runs inside NX)  │
│                   │
│ dispatch() →      │
│ create_cube()     │
│                   │
│ _ensure_work_part │
│ _create_expression│
│ BlockFeatureBuilder│
│ CommitFeature()   │
│ _remember_feature │
│ fit_view()        │
└────────┬─────────┘
         │ NXOpen API calls
         ▼
┌──────────────────┐
│ Siemens NX Engine │
│                   │
│ Creates 3D        │
│ geometry          │
│ Updates feature   │
│ tree              │
│ Saves .prt file   │
└────────┬─────────┘
         │ {"ok": true, "message": "Cube 50mm..."}
         ▼
┌──────────────────┐
│ Response bubbles  │
│ back through      │
│ runner → tool →   │
│ server → stdout   │
│ → agent           │
└──────────────────┘
```

---

## 8. Example Walkthrough: `create_cuboid` Line by Line

Let's walk through `nx_bridge.create_cuboid()` (line 1308-1346) as if narrating a story:

```python
def create_cuboid(length=40.0, width=25.0, height=20.0, x=0.0, y=0.0, z=0.0):
```
**Line 1308:** This function accepts 6 parameters with defaults. If the agent just says "create a cuboid," it gets a 40×25×20mm box at the origin.

```python
    length = float(length)
    width = float(width)
    height = float(height)
    x = float(x)
    y = float(y)
    z = float(z)
```
**Lines 1309-1314:** Convert all inputs to floats. This handles cases where the agent might send strings like `"40.0"` instead of numbers.

```python
    if length <= 0.0 or width <= 0.0 or height <= 0.0:
        return {"ok": False, "error": "Cuboid dimensions must be positive"}
```
**Lines 1316-1317:** **Validation gate.** Reject nonsensical dimensions before touching NX. Returns an error dict that the runner will pass back to the agent.

```python
    work_part = _ensure_work_part()
```
**Line 1319:** Makes sure we have an open part file to work with. If nothing is open, it creates a default `nx_mcp_result.prt`. This is like making sure you have a blank sheet of paper before you start drawing.

```python
    l_name = _create_named_expression(work_part, "CUBOID_L", length)
    w_name = _create_named_expression(work_part, "CUBOID_W", width)
    h_name = _create_named_expression(work_part, "CUBOID_H", height)
```
**Lines 1322-1324:** **Creates three NX Expressions.** Instead of just passing `40.0` to the block builder, we create named variables like `CUBOID_L_1 = 40.0` inside NX. This is what makes the cuboid **parametric** — you can later change `CUBOID_L_1` to `80.0` and the box will stretch.

```python
    builder = work_part.Features.CreateBlockFeatureBuilder(
        NXOpen.Features.Feature.Null
    )
```
**Lines 1326-1328:** **Create a Block Feature Builder.** In NXOpen, you don't just "make a box" — you create a "builder" object, configure all its settings, then "commit" it. The `Null` argument means we're creating a new feature (not editing an existing one).

```python
    try:
        origin = NXOpen.Point3d(x, y, z)
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(origin, l_name, w_name, h_name)
```
**Lines 1329-1332:** Configure the builder:
- Set the corner position (origin)
- Tell NX we're defining the box by origin + edge lengths (not by two diagonal corners)
- Pass in the **expression names** (not the numbers!) for length, width, height

```python
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
```
**Lines 1333-1336:** Tell NX this is a "Create" operation (making a new body), not a "Unite" or "Subtract" with an existing body.

```python
        feature = builder.CommitFeature()
        _remember_feature(feature)
```
**Lines 1337-1338:** **CommitFeature() is the magic line** — this is where NX actually creates the 3D geometry. The block appears in the feature tree and the 3D viewport. `_remember_feature()` stores a reference to this feature so later operations (like "add fillet to last feature") can find it.

```python
    finally:
        builder.Destroy()
```
**Lines 1339-1340:** **Cleanup.** Builders in NXOpen allocate internal resources and MUST be destroyed when done, even if an error occurred. The `try/finally` ensures this always happens.

```python
    fit_view()
    return {
        "ok": True,
        "message": f"Cuboid {length}x{width}x{height}mm at ({x},{y},{z})",
    }
```
**Lines 1342-1346:** Zoom the viewport to show the full model, then return success with a human-readable message.

---

## 9. Known Limitations / Things to Watch

### Hardcoded Values

- **NX path fallback** (runner.py line 47, nx_bridge.py line 623): Falls back to `C:\Program Files\Siemens\NX2206\NXBIN\ugs_router.exe` if `UGII_BASE_DIR` is not set. Only works on the original developer's machine.
- **Socket port 43210** (runner.py line 24): Hardcoded, no config option.
- **Output path** (build scripts): Many build scripts have hardcoded paths like `"C:/Users/HP/nx-mcp/..."`.
- **Tolerance values**: Hardcoded to `0.01` in fillet/chamfer builders (nx_bridge.py lines 1609, 1654).

### TODOs / Missing Features

- `TODO_NXOPEN_ROADMAP.md` exists but was not analyzed (it's a development roadmap).
- No support for undo/redo beyond the single-command state rollback.
- No support for multi-body selection beyond `"last"` and name matching.
- Assembly tools (`mate_components`) appear skeletal — they create constraint builders but don't fully configure them.
- Many surface modeling tools (30+) are thin wrappers that just pass args through to the bridge with no implementation visible in `nx_bridge.py` — they may return errors if the corresponding `nx_bridge.py` handler doesn't exist.

### Missing Error Handling

- `_update_result_files()` and `_update_watcher_files()` have bare `except Exception: pass` — errors are silently swallowed.
- `build_*.py` scripts don't always check `r.get("ok")` before continuing — if one step fails silently, later steps may crash cryptically.
- The `dispatch()` function uses `globals().get(tool)` which could theoretically call any global function, though input comes from the MCP server which controls the tool names.

### Fragile Assumptions

- Edge selection relies on geometric position (bounding box, coordinate alignment) rather than persistent NX tags — if model topology changes, the wrong edges may be selected.
- The `_state["last_body"]` pattern assumes serial, sequential operations — no support for naming/tracking multiple bodies in parallel.
- Expression counter `_expression_counters` is in-memory only — restarting the bridge loses track of used names, leading to expression creation collisions.

### Dead/Duplicated Code

- **`add_hole` vs `add_hole_nx`**: `add_hole_nx` in modeling.py (line 392) is explicitly marked as an alias that just calls `add_hole()`. The `nx_bridge.py` has separate implementations for both.
- **`add_fillet` vs `edge_blend`** and **`add_chamfer` vs `chamfer`**: Duplicate tools with different names doing the same thing.
- **`mirror_feature` vs `mirror_body_feature`**: `mirror_body_feature` just calls the same bridge function as `mirror_feature`.
- **`_bridge_result()` function**: Defined identically in 8 different files (every tool module has its own copy).
- **`_use_mock_nxopen()` function**: Also duplicated across 8 files.
- **`nx_bridge.py` (outer)** (`src/nx_mcp/nx_bridge.py`): A 2617-byte file that appears to be an older/unused version — the real bridge is at `src/nx_mcp/bridge/nx_bridge.py`.
- Many journal files in `src/nx_mcp/journals/` (like 8 versions of `create_mounting_plate_v*.py`) appear to be iterative development attempts, not all actively used.

---

## 10. Full Code Quality & Industry-Readiness Audit

### MCP Protocol Correctness

#### Issue: Hand-rolled MCP protocol implementation
- **Where**: `server.py` (entire file)
- **Why it's a problem**: The server manually implements JSON-RPC 2.0 over stdio instead of using the official `mcp` Python SDK. This means it must handle every protocol detail (capability negotiation, error formats, lifecycle) manually — and it misses several. For example, `notifications/initialized` returns `None` but doesn't acknowledge it. There's no `shutdown` handler. No `ping/pong`. No capability negotiation for transport features. As the MCP spec evolves, this code won't automatically get updates.
- **Severity**: Medium
- **Fix suggestion**: Replace with the official `mcp` Python SDK which handles all protocol details correctly.

#### Issue: Tool schemas lack descriptions for most parameters
- **Where**: `registry.py` `_get_schema()`, all tool functions
- **Why it's a problem**: The auto-schema generator only includes descriptions for parameters that have `:param name: description` lines in docstrings. Most tool functions have NO docstrings at all, so the LLM client gets parameter names and types but no explanations of what they mean. For example, `edges` parameter accepts magic strings like `"outer_edges"`, `"vertical_edges"`, `"top_edges"` but the schema doesn't list valid values.
- **Severity**: Medium
- **Fix suggestion**: Add `:param` docstrings to every tool function, or use `typing.Literal` for enum-like parameters.

#### Issue: Tool responses always use type "text" even for structured data
- **Where**: `server.py` line 36
- **Why it's a problem**: `str(result)` converts everything to a plain text string. Tools that return structured data (like bounding box coordinates, feature lists) lose that structure. The AI has to parse text instead of receiving JSON.
- **Severity**: Low
- **Fix suggestion**: Return structured JSON content where appropriate using MCP's content types.

#### Issue: No MCP lifecycle shutdown/cleanup
- **Where**: `server.py` `main()`
- **Why it's a problem**: When the stdin loop ends (agent disconnects), the NX bridge subprocess is NOT cleaned up. The NX process may remain running in the background as a zombie.
- **Severity**: High
- **Fix suggestion**: Add signal handlers and an atexit hook that calls `NXBridgeProcess.reset()`.

---

### NX Session & Resource Management

#### Issue: No cleanup of NX process on server exit
- **Where**: `runner.py` `NXBridgeProcess` class
- **Why it's a problem**: The subprocess (`run_journal.exe`) and the NX GUI process (`ugraf.exe`) are started but never reliably killed when the MCP server exits. Only `reset_nx_bridge` tool manually does this. If the MCP server crashes, NX processes pile up.
- **Severity**: High
- **Fix suggestion**: Register `atexit.register(NXBridgeProcess.reset)` in `runner.py`. Add signal handling for SIGTERM/SIGINT.

#### Issue: No concurrency protection for NX operations
- **Where**: `runner.py` `NXBridgeProcess.call()`, `nx_bridge.py`
- **Why it's a problem**: The runner has a threading lock (`_lock`) for the batch-mode subprocess, but the socket mode has **no locking at all**. If two MCP requests arrive simultaneously and both go through the socket, they'll interleave commands to NX, which is single-threaded and NOT safe for concurrent access. This could corrupt the model state or crash NX.
- **Severity**: Critical
- **Fix suggestion**: Add a mutex/lock around all socket communications. Or document that the server is single-threaded only.

#### Issue: NX GUI left open indefinitely
- **Where**: `runner.py` `launch_interactive_nx()`
- **Why it's a problem**: When the runner launches `ugraf.exe`, it opens NX and never closes it. Even after all work is done, NX stays running consuming an NX license seat. NX licenses are very expensive (often $10,000+/year per seat).
- **Severity**: Medium
- **Fix suggestion**: Add a `close_nx` tool or auto-close after idle timeout.

#### Issue: Temp files / generated parts never cleaned up
- **Where**: Root directory (many `.prt`, `.log`, `.txt`, `.obj` files)
- **Why it's a problem**: The root directory is littered with 30+ generated `.prt` files, `.log` files, debug `.txt` files, and `.obj` exports. There's no cleanup mechanism. Running the server repeatedly will keep accumulating files.
- **Severity**: Low
- **Fix suggestion**: Use a dedicated output directory and add a cleanup tool or cron.

---

### Error Handling & Robustness

#### Issue: Silent exception swallowing in file watcher updates
- **Where**: `runner.py` `_update_watcher_files()` line 59, `nx_bridge.py` `_update_result_files()` line 631
- **Why it's a problem**: Both functions have `except Exception: pass` — if writing helper files fails, you'll never know. This could mask disk-full errors or permission issues.
- **Severity**: Low
- **Fix suggestion**: Log the exception to stderr instead of swallowing it.

#### Issue: State rollback on error is shallow
- **Where**: `nx_bridge.py` `handle_line()` line 3882
- **Why it's a problem**: When a command fails, the `_state` dict is restored to its pre-command snapshot. But the NX model itself is NOT rolled back — if a feature was partially created before the error, it stays in the model. NX's undo system is not used for rollback.
- **Severity**: Medium
- **Fix suggestion**: Set NX undo marks before each operation and roll back on failure.

#### Issue: No timeout on socket reads in bridge
- **Where**: `runner.py` `NXBridgeProcess.call()` line 222
- **Why it's a problem**: When reading the socket response, the code loops `while "\n" not in buffer` with no timeout. If NX hangs (e.g., on a complex operation or dialog box), the MCP server hangs forever.
- **Severity**: High
- **Fix suggestion**: Set `socket.settimeout()` before the read loop.

#### Issue: No validation of file paths
- **Where**: `file_ops.py` `create_part()`, `open_part()`, `export_step()`, `export_stl()`
- **Why it's a problem**: File paths from the AI agent are passed directly to NX without any validation or sanitization. A path like `../../important_file.prt` could potentially overwrite files outside the project directory.
- **Severity**: Medium
- **Fix suggestion**: Validate that paths are within an allowed output directory.

---

### Security

#### Issue: No authentication or authorization on socket bridge
- **Where**: `nx_bridge.py` `run_socket_bridge()` line 3910
- **Why it's a problem**: The socket server on port 43210 accepts connections from any local process with no authentication. Any program on the same machine could send commands to NX. On shared machines/servers this is a security risk.
- **Severity**: Medium (localhost-only mitigates this somewhat)
- **Fix suggestion**: Add a shared secret/token that must be included in each command.

#### Issue: dispatch() uses globals() for function lookup
- **Where**: `nx_bridge.py` `dispatch()` line 3831
- **Why it's a problem**: `func = globals().get(tool)` will look up ANY global function/variable by name. While the tool names come from the MCP server (which validates them against the registry), if someone connects directly to the socket, they could potentially call internal functions not meant to be exposed.
- **Severity**: Low (mitigated by localhost-only socket)
- **Fix suggestion**: Use an explicit allowlist/dispatch table instead of `globals()`.

#### Issue: Hardcoded paths expose user information
- **Where**: `build_offset_linkage_arm.py` line 23, other build scripts
- **Why it's a problem**: `OUTPUT_PATH = "C:/Users/HP/nx-mcp/..."` reveals the developer's Windows username and file structure. Not a security vulnerability per se, but a code hygiene issue that would be embarrassing in shared/client code.
- **Severity**: Low
- **Fix suggestion**: Use relative paths or environment variables.

---

### Parametric Integrity

#### Issue: Expression names are auto-generated with counters, not semantic
- **Where**: `nx_bridge.py` `_create_named_expression()` line 162
- **Why it's a problem**: Every feature creates expressions like `CUBOID_L_1`, `CUBOID_L_2`, `FILLET_R_1`, `FILLET_R_2`. If you create two cuboids, their expressions are `CUBOID_L_1` and `CUBOID_L_2` — there's no way to know which belongs to which cuboid. This makes the part confusing when opened in NX's expression editor.
- **Severity**: Medium
- **Fix suggestion**: Allow callers to specify meaningful expression names, or auto-generate more descriptive names based on feature context.

#### Issue: Derived parameter values are computed in Python, not NX expressions
- **Where**: `nx_bridge.py` `create_offset_linkage_arm()` line 1036
- **Why it's a problem**: `ARM_SPAN = ARM_L - 2.0 * END_R` is computed as `66.0` in Python and used as a literal. It's NOT stored as an NX expression formula `"ARM_LENGTH - 2 * END_RADIUS"`. This means changing `ARM_LENGTH` in NX won't update `ARM_SPAN`-dependent geometry.
- **Severity**: High
- **Fix suggestion**: Create NX expressions with formulas: `work_part.Expressions.CreateExpression("Number", "ARM_SPAN = ARM_LENGTH - 2 * END_RADIUS")`

#### Issue: No parameter range validation for edge cases
- **Where**: Various tool functions
- **Why it's a problem**: While basic checks exist (e.g., `size > 0`), there's no validation for domain-specific edge cases: a fillet radius larger than the edge length, a hole deeper than the body, a cylinder with radius larger than the part it's being subtracted from, etc. These will cause NX API errors that may be cryptic.
- **Severity**: Medium
- **Fix suggestion**: Add geometric pre-checks where feasible, or improve error messages to explain what went wrong in mechanical terms.

#### Issue: No template/master part protection
- **Where**: N/A (no template system exists)
- **Why it's a problem**: Since parts are built from scratch each time, running the same build script twice creates a second `.prt` file or overwrites the first. There's no versioning, no "open template → save-as-copy" pattern. This is fine for prototyping but risky for production workflows.
- **Severity**: Low (for current usage)
- **Fix suggestion**: Implement a template-based workflow for production use.

---

### Code Structure & Maintainability

#### Issue: `_bridge_result()` and `_use_mock_nxopen()` duplicated in every tool file
- **Where**: `modeling.py`, `sketch.py`, `file_ops.py`, `assembly.py`, `measure.py`, `utility.py`, `surface_modeling.py`, `combine_operations.py`, `edit_operations.py` — 9 files
- **Why it's a problem**: The exact same 5-line `_bridge_result()` function and 2-line `_use_mock_nxopen()` function are copy-pasted into every tool module. If you need to change the result formatting, you have to edit 9 files.
- **Severity**: Medium
- **Fix suggestion**: Move to a shared module (e.g., `tools/common.py`) and import from there.

#### Issue: nx_bridge.py is a 4035-line monolith
- **Where**: `src/nx_mcp/bridge/nx_bridge.py`
- **Why it's a problem**: One file contains ALL NX API logic — sketching, solid modeling, surface operations, boolean operations, assembly operations, measurement, expressions, state management, socket server, dispatch, and main loop. This makes it very hard to navigate, test, or modify without risk of breaking something else.
- **Severity**: High
- **Fix suggestion**: Split into modules: `bridge/sketch_ops.py`, `bridge/solid_ops.py`, `bridge/boolean_ops.py`, `bridge/state.py`, `bridge/server.py`, etc.

#### Issue: Minimal logging
- **Where**: Throughout the codebase
- **Why it's a problem**: `server.py` has basic DEBUG logging of method names, but `runner.py` and `nx_bridge.py` have almost no logging. The only debug output is optional file-based logging (`_debug_log()`) gated behind `NX_MCP_DEBUG_LOGS=1`. In production, if something fails, you have very little visibility into what happened.
- **Severity**: Medium
- **Fix suggestion**: Add structured logging at INFO level for all tool calls (name, args, result, duration).

#### Issue: Tests only cover mock mode
- **Where**: `tests/test_tools.py`
- **Why it's a problem**: All tests run with `NX_MCP_USE_MOCK_NXOPEN=1`, meaning they test the MCP tool routing and input validation but NEVER test actual NXOpen API calls. The mock objects return `MagicMock` results that don't validate anything. There are no integration tests that run against a real NX instance.
- **Severity**: High
- **Fix suggestion**: Add integration test scripts that run against a real NX install (can be manual/CI-triggered). Add property-based tests for expression creation logic.

#### Issue: No type hints on nx_bridge.py functions
- **Where**: `nx_bridge.py` (all 4035 lines)
- **Why it's a problem**: Not a single function in `nx_bridge.py` has type annotations. This makes it harder for developers and tools to understand what parameters expect and return.
- **Severity**: Low
- **Fix suggestion**: Add type hints gradually, starting with the `dispatch()` function and public handlers.

---

### Configuration & Environment

#### Issue: `.env.example` points to wrong variable
- **Where**: `.env.example`
- **Why it's a problem**: The file shows `NX_RUN_JOURNAL=C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe` but the code actually uses `UGII_BASE_DIR` (a Siemens-standard variable), not `NX_RUN_JOURNAL`. This documentation is misleading.
- **Severity**: Low
- **Fix suggestion**: Update `.env.example` to show `UGII_BASE_DIR=C:\Program Files\Siemens\NX2206`.

#### Issue: FastAPI/uvicorn not in dependencies
- **Where**: `http_server.py`, `pyproject.toml`
- **Why it's a problem**: `http_server.py` imports `fastapi` and `uvicorn`, but neither is listed in `pyproject.toml` dependencies. Running `nx-mcp-http` will crash with `ModuleNotFoundError`.
- **Severity**: Medium
- **Fix suggestion**: Add `fastapi` and `uvicorn` to `[project.optional-dependencies]` under an `http` extra.

#### Issue: Would not work on another engineer's PC without edits
- **Where**: Build scripts, fallback paths
- **Why it's a problem**: Build scripts have `C:/Users/HP/` hardcoded. The NX path fallback assumes `C:\Program Files\Siemens\NX2206`. Other NX versions (NX2212, NX2306, etc.) have different paths. On another engineer's machine, at minimum `UGII_BASE_DIR` must be set and all build scripts must be edited.
- **Severity**: Medium
- **Fix suggestion**: Use relative paths in build scripts, and remove hardcoded NX path fallbacks.

---

## 11. Prioritized Action Plan

### 🔴 Fix Immediately (Crash/Corruption/Security Risks)

| # | What | Why | Difficulty |
|---|------|-----|-----------|
| 1 | **Add concurrency lock for socket mode** | Two simultaneous requests can corrupt NX model state or crash NX. Since NX is single-threaded, any concurrent access is dangerous. | Quick fix — add a `threading.Lock` around socket send/receive in `runner.py` |
| 2 | **Add NX process cleanup on server exit** | Zombie NX processes waste expensive license seats and consume resources. Add `atexit.register()` and signal handlers. | Quick fix |
| 3 | **Add socket read timeout** | If NX hangs, the entire MCP server hangs forever with no way to recover except killing the process. | Quick fix — add `socket.settimeout(60)` |

### 🟠 Fix Soon (Will Bite You As Usage Grows)

| # | What | Why | Difficulty |
|---|------|-----|-----------|
| 4 | **Split nx_bridge.py into modules** | At 4035 lines, it's unmaintainable. Any change risks breaking unrelated features. | Moderate refactor — extract into 5-6 smaller modules |
| 5 | **Make derived parameters use NX expression formulas** | Currently `ARM_SPAN = 66.0` is hardcoded — changing `ARM_LENGTH` in NX won't update downstream geometry. Defeats the purpose of parametric. | Moderate refactor — change Python arithmetic to NX expression strings |
| 6 | **Add structured logging** | Can't debug production failures with current minimal logging. Need at minimum: tool name, args, success/fail, duration for every call. | Moderate refactor |
| 7 | **Add integration tests against real NX** | Mock tests don't catch NXOpen API issues. Need at least smoke tests that create a cube, add a fillet, and verify the part file exists. | Moderate effort — requires NX installed on CI/test machine |
| 8 | **Eliminate duplicated helper functions** | `_bridge_result()` and `_use_mock_nxopen()` copy-pasted 9 times. Move to shared module. | Quick fix |
| 9 | **Fix `.env.example` and document `UGII_BASE_DIR`** | Current docs are misleading. Engineers will waste time with wrong env var. | Quick fix |
| 10 | **Add FastAPI/uvicorn to optional dependencies** | `nx-mcp-http` entry point crashes without them. | Quick fix |

### 🟡 Improve When Possible (Cleanliness, Testing, Documentation)

| # | What | Why | Difficulty |
|---|------|-----|-----------|
| 11 | **Add parameter descriptions to all tool schemas** | LLM clients get better results when they understand what parameters mean. Add docstrings with `:param` lines. | Moderate effort — 100+ tools to document |
| 12 | **Use official MCP SDK** | Hand-rolled protocol handling will break as MCP spec evolves. | Moderate refactor |
| 13 | **Remove duplicate tools** | `add_fillet`/`edge_blend`, `add_chamfer`/`chamfer`, `add_hole`/`add_hole_nx`, `mirror_feature`/`mirror_body_feature` are confusing duplicates. | Quick fix (deprecate the aliases) |
| 14 | **Add file path validation** | Prevent path traversal and accidental overwrites. | Quick fix |
| 15 | **Clean up root directory** | 30+ generated `.prt` files, `.log` files, debug `.txt` files cluttering the repo. Add to `.gitignore`. | Quick fix |
| 16 | **Add type hints to nx_bridge.py** | Improves readability and enables type-checking tools. | Major effort — 4035 lines |
| 17 | **Remove hardcoded user paths from build scripts** | `C:/Users/HP/` should be relative or env-driven. | Quick fix |
| 18 | **Clean up dead journal versions** | 8 versions of `create_mounting_plate_v*.py` — keep the latest, archive the rest. | Quick fix |

---

## 12. Glossary

| Term | Plain-English Definition |
|------|------------------------|
| **MCP (Model Context Protocol)** | A communication standard that lets AI assistants (like Gemini or Claude) call "tools" on external systems. Think of it like a universal plug that lets any AI talk to any software. The AI sends a request like "call the create_cube tool with size=50" and gets back a result. |
| **JSON-RPC** | A simple messaging format where requests and responses are JSON objects. Each request has a method name (like `tools/call`) and parameters. Each response has either a result or an error. It's how the AI and the MCP server talk to each other. |
| **stdio (Standard Input/Output)** | The simplest way two programs can talk: one writes text to its output, the other reads it from its input. Like two people passing notes through a slot in a wall. The MCP server reads commands from stdin and writes responses to stdout. |
| **NXOpen** | Siemens' official programming interface (API) for controlling NX. It lets you do anything in NX that a human could do with the GUI — create parts, add features, export files — but through code instead of mouse clicks. |
| **NXOpen.UF (User Function)** | An older, lower-level API for NX. Think of NXOpen as the "modern" interface and UF as the "classic" one. Some operations (like revolve) are easier to do through UF. |
| **Expression (NX Expression)** | A named variable stored inside an NX part file. Like a spreadsheet cell: you give it a name (e.g., `PLATE_LENGTH`) and a value (e.g., `120`). Features that use this expression will update automatically when you change the value. This is what makes a model "parametric." |
| **Feature** | A single modeling operation in the NX feature tree — like an extrude, a fillet, a hole, or a pattern. Features are stacked in order: each one modifies the shape built by all previous features. Think of it like layers in Photoshop but for 3D. |
| **Feature Tree** | The ordered list of all features in a part. It's like a recipe: "First create a block, then add a fillet to the top edges, then cut a hole at this position." You can go back and edit any step. |
| **Parametric (Parametric Model)** | A 3D model where dimensions are stored as editable variables (expressions), not just fixed numbers. If you change a variable, the entire model updates automatically. Like a spreadsheet formula — change one cell and all dependent cells recalculate. |
| **Builder (NXOpen Builder)** | A temporary configuration object in NXOpen. To create a feature, you: (1) create a builder, (2) set all its properties, (3) call Commit to create the feature, (4) call Destroy to clean up. It's like filling out a form before submitting it. |
| **Body (Solid Body / Sheet Body)** | The actual 3D shape in NX. A "solid body" is a closed 3D volume (like a real physical object). A "sheet body" is a surface with no thickness (like a piece of paper). |
| **Boolean Operation** | Combining two bodies: **Unite** (merge into one), **Subtract** (cut one from another, like drilling a hole), or **Intersect** (keep only the overlapping part). |
| **Sketch** | A 2D drawing (lines, circles, arcs) on a flat plane that defines a profile shape. This shape can then be extruded (pushed out) or revolved (spun) to create a 3D feature. |
| **Extrude** | Taking a 2D sketch profile and "pushing" it perpendicular to its plane to create a 3D solid. Like pushing a cookie cutter through dough. |
| **Revolve** | Taking a 2D sketch profile and spinning it around an axis to create a 3D solid. Like a potter's wheel — a 2D profile swept around in a circle. |
| **Fillet / Edge Blend** | Rounding off a sharp edge with a smooth curve of a given radius. |
| **Chamfer** | Cutting off a sharp edge at an angle (usually 45°) by a given distance. |
| **Pattern** | Duplicating a feature in a regular arrangement — either in a straight line (linear pattern) or around a circle (circular pattern). |
| **Mirror** | Creating a reflected copy of a feature across a plane of symmetry. |
| **Datum Plane** | An imaginary flat plane used as a reference for building features. The three standard ones are XY (horizontal), XZ (front), and YZ (side). |
| **Journal (NX Journal)** | A Python or VB script that NX can run to automate operations. Think of it as a macro — a recorded sequence of actions. NX provides `run_journal.exe` to execute these scripts. |
| **Bridge** | In this codebase, the "bridge" is the communication layer between the MCP server (which runs in normal Python) and the NX process (which requires NXOpen). The bridge sends commands to NX and receives results. |
| **Socket** | A network connection between two programs, even on the same computer. In this project, a TCP socket on port 43210 connects the bridge runner to the NX bridge script running inside the NX process. |
| **Tool Schema** | A JSON description of what inputs a tool accepts — parameter names, types, which are required, descriptions. This helps the AI agent know how to call the tool correctly. |
| **Concurrency** | Multiple operations happening at the same time. NX is single-threaded (can only do one thing at a time), so if two commands arrive simultaneously, they must be queued — otherwise one might corrupt the other. |
| **Session Management** | How the system starts, maintains, and stops its connection to NX. Like logging in and out of a website — you need a session to do work, and you should clean up when done. |
| **run_journal.exe** | A Siemens NX utility that runs a Python script inside the NX environment (headless, no GUI). Used as the batch-mode fallback. |
| **ugraf.exe** | The main NX GUI executable. When launched with `-auto=script.py`, it opens the NX GUI and automatically runs the given script at startup. |
| **ugs_router.exe** | A Siemens NX utility that opens a `.prt` file in the NX GUI. Used to let you view generated results. |
| **UGII_BASE_DIR** | A standard Siemens environment variable that points to the NX installation directory (e.g., `C:\Program Files\Siemens\NX2206`). |
| **Part File (.prt)** | Siemens NX's native file format for 3D models. Contains the complete feature tree, expressions, geometry, and metadata. |
| **STEP (.stp/.step)** | An industry-standard 3D file format that can be opened by any CAD software. Used for sharing models between different systems. |
| **STL** | A simplified 3D file format that stores only the surface mesh (triangles). Used for 3D printing and visualization. Not parametric. |
| **OBJ** | Another mesh-based 3D file format, similar to STL but with material/texture support. |
