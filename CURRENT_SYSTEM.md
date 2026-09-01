# CURRENT SYSTEM ARCHITECTURE MAP

This document provides a single comprehensive view of the **NX-MCP** system architecture, tracing the complete execution flow from the AI client down to Siemens NX through NXOpen, featuring actual module names, function signatures, data structures, transport mechanisms, and recent enhancements.

---

## 1. Grand End-to-End System Architecture Diagram

```mermaid
graph TD
    subgraph AI_CLIENT_LAYER ["1. AI Agent / Client Layer"]
        Cline["AI Client (Cline / VSCode / Claude Desktop / Custom Agent)"]
        LLM["LLM (Gemini, Claude, GPT, Local Qwen/DeepSeek)"]
        Cline <-->|Prompts, Schemas & Tool Calls| LLM
    end

    subgraph MCP_TRANSPORT ["2. MCP Protocol Transport"]
        StdIO["JSON-RPC 2.0 over Stdin / Stdout (Primary)"]
        HTTP["FastAPI HTTP Server (http_server.py :8765)"]
        Cline <-->|JSON-RPC Requests / Responses| StdIO
        Cline <-->|HTTP POST /api/mcp| HTTP
    end

    subgraph SERVER_LAYER ["3. MCP Server Core (src/nx_mcp/server.py)"]
        ServerMain["main() - Stdin Line Loop"]
        ServerHandle["handle(req) - Protocol Dispatcher"]
        SessionState["_session_state: active_routed_tool_names, escape_hatch_active, task_prompt"]
        StdIO --> ServerMain --> ServerHandle
        HTTP --> ServerHandle
        ServerHandle <--> SessionState
    end

    subgraph REGISTRY_ROUTER ["4. Tool Registry & Dynamic Router (141 Tools)"]
        Registry["ToolRegistry (src/nx_mcp/tools/registry.py)<br/>- all(): Dict[str, dict]<br/>- get(name): dict<br/>- list_tools(): List[mcp_schema]"]
        Router["Router (src/nx_mcp/router.py)<br/>- route(prompt) -> {categories, confidence, tools}<br/>- CATEGORY_KEYWORDS & CATEGORY_TOOLS<br/>- Tokenizer & Multi-word phrase matcher"]
        DiscoveryTool["get_relevant_nx_tools (discovery.py)<br/>- Dynamic task-based schema filtering"]
        
        ServerHandle -->|tools/list| Router
        ServerHandle -->|tools/call| Registry
        Router -->|Filters Schemas (unless Escape Hatch active)| Registry
        DiscoveryTool --> Router
    end

    subgraph TOOL_WRAPPERS ["5. Tool Wrapper Layer (src/nx_mcp/tools/*.py)"]
        CommonHelper["_common.py: _bridge_result(), _use_mock_nxopen()"]
        ModTools["modeling.py (create_cuboid, create_cylinder, extrude, boolean_subtract, add_fillet, pattern_circular...)"]
        SketchTools["sketch.py (create_sketch, draw_line, draw_spline, offset_curve, close_curve_region...)"]
        SurfTools["surface_modeling.py (trim_sheet, studio_surface, sew_sheets, make_solid...)"]
        UtilTools["utility.py (set_view, fit_view, take_screenshot, list_features, inspect_part, inspect_api...)"]
        EditTools["edit_operations.py (x_form, heal_surface, reverse_normal...)"]
        FileTools["file_ops.py (create_part, open_part, save_part, export_step, export_stl)"]
        RecipeTools["recipe.py (run_recipe: sequential multi-step execution)"]
        MeasureTools["measure.py (measure_distance, measure_angle, measure_volume, get_bounding_box)"]
        AssyTools["assembly.py (add_component, mate_components, list_components)"]
        DiscTools["discovery.py (get_relevant_nx_tools, polar_to_cartesian_points)"]
        
        Registry --> ModTools & SketchTools & SurfTools & UtilTools & EditTools & FileTools & RecipeTools & MeasureTools & AssyTools & DiscTools
        ModTools & SketchTools & SurfTools & UtilTools & EditTools & FileTools & RecipeTools & MeasureTools & AssyTools --> CommonHelper
    end

    subgraph RUNNER_LAYER ["6. Process & Socket Bridge Runner (src/nx_mcp/bridge/runner.py)"]
        RunnerCall["call_nx(tool, args) / run_tool(tool, **args)"]
        NXBridgeProc["NXBridgeProcess (Singleton with Threading Lock _lock)"]
        EnvCheck["verify_nx_environment() (Validates UGII_BASE_DIR, run_journal, ugraf, ugs_router)"]
        LaunchNx["launch_interactive_nx(part_path, port=43210)<br/>- _find_running_ugraf()<br/>- Mutex lock: bridge.launching.lock<br/>- Popen(ugraf.exe -auto=nx_bridge.py)"]
        CallSocket["_call_socket(s, tool, args)<br/>- Dynamic Timeouts: 60s default, 300s journal/recipe<br/>- s.sendall(json_payload)<br/>- s.recv(4096) loop"]
        WatcherFiles["_update_watcher_files(filepath)<br/>- latest_nx_result.txt<br/>- open_current_nx_result.cmd<br/>- open_latest_nx_result.vbs"]
        
        CommonHelper --> RunnerCall
        RunnerCall --> EnvCheck --> NXBridgeProc
        NXBridgeProc -->|Lock acquired & socket missing| LaunchNx
        NXBridgeProc -->|Socket connected| CallSocket
        CallSocket --> WatcherFiles
    end

    subgraph TRANSPORT_SOCKET ["7. Loopback TCP Socket IPC"]
        TCPSocket["127.0.0.1:43210 (JSON-Lines Stream)"]
        CallSocket <-->|TCP Send / Recv| TCPSocket
    end

    subgraph NX_BRIDGE_LAYER ["8. In-NX Bridge Dispatcher (src/nx_mcp/bridge/nx_bridge.py ~6032 lines)"]
        SocketBridge["run_socket_bridge(port=43210)<br/>- select.select() non-blocking loop<br/>- ui.ProcessDeviceEvents() keepalive<br/>- Periodic health logging (every 5m)"]
        HandleLine["handle_line(line)<br/>- json.loads()<br/>- Deep state backup<br/>- Automatic rollback on exception or ok=False"]
        Dispatch["dispatch(command)<br/>- globals().get(tool_name)<br/>- Parameter normalization layer (z_offset->z, radius->offset)<br/>- inspect.signature binding"]
        
        TCPSocket <--> SocketBridge --> HandleLine --> Dispatch
    end

    subgraph BRIDGE_CORE ["9. Bridge Subsystems & Execution Handlers"]
        StateMgr["State Manager (_state)<br/>- features, bodies, sketches, last_curves, active_sketch<br/>- _reset_transient_session_state() on part boundary"]
        ExprMgr["Expression Manager<br/>- _create_input_expression(), _create_formula_expression()<br/>- _next_instance_prefix(), _seed_counters_from_part()"]
        ResMgr["Reference Resolvers<br/>- _resolve_body(), _resolve_feature(), _resolve_edges()<br/>- _normalize_name() fuzzy matching"]
        SafetyMgr["Safety & Validation<br/>- _validate_hole_intersection() AABB check<br/>- _ensure_work_part() fallback collision guard"]
        ExecHandlers["NX CAD Handlers (~140 functions)<br/>- create_cuboid, create_cylinder, extrude, draw_spline<br/>- offset_curve, close_curve_region, boolean_combine, exec_python_code"]
        
        Dispatch --> StateMgr & ExprMgr & ResMgr & SafetyMgr & ExecHandlers
    end

    subgraph NXOPEN_API ["10. Siemens NXOpen API Layer"]
        NXOpenAPI["NXOpen C++/Python Runtime<br/>- NXOpen.Session.GetSession()<br/>- NXOpen.UF.UFSession.GetUFSession()<br/>- Features.CreateBlockFeatureBuilder()<br/>- Features.CreateExtrudeBuilder()<br/>- Features.CreateStudioSplineBuilderEx()"]
        ExecHandlers --> NXOpenAPI
    end

    subgraph SIEMENS_NX ["11. Siemens NX Native CAD Engine"]
        UgrafProc["ugraf.exe (Interactive GUI Process)"]
        NXOpenAPI <-->|C-API Direct Memory Interop| UgrafProc
        UgrafProc --> PRTFiles[".prt CAD Part Files"]
    end
```

---

## 2. Textual Call Path Map

### Step-by-Step Execution Journey

1. **AI Agent Request**:
   - The AI client (e.g. Cline, Claude Desktop) formulates a tool invocation request according to MCP JSON-RPC 2.0 specification:
     ```json
     {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "create_cuboid", "arguments": {"length": 100, "width": 50, "height": 30, "centered": true}}}
     ```
   - Sent via standard input (`stdin`) to `src/nx_mcp/server.py`.

2. **Server Protocol Handling (`src/nx_mcp/server.py`)**:
   - `server.py` reads the JSON string from `sys.stdin`.
   - Passes the parsed object to `handle(req)`.
   - Validates the method (`tools/call`, `tools/list`, `initialize`).
   - Retrieves the tool definition from `ToolRegistry.get(name)`.
   - Verifies routed subset membership; if a tool is called that was not in the active routed view, the **Escape Hatch** is activated, re-exposing all 141 tools for future calls.
   - Invokes the tool wrapper function with unpacked kwargs: `tool["fn"](**args)`.

3. **Tool Wrapper Layer (`src/nx_mcp/tools/*.py`)**:
   - The wrapper function (e.g., `modeling.create_cuboid(...)`) validates argument types and ranges.
   - If `NX_MCP_USE_MOCK_NXOPEN=1` is set (during unit tests), mock objects are returned.
   - In live mode, it delegates execution to the runner via `_bridge_result(runner.call_nx("create_cuboid", args))`.

4. **Runner & Lock Management (`src/nx_mcp/bridge/runner.py`)**:
   - `NXBridgeProcess.call(tool, args)` acquires `NXBridgeProcess._lock` (thread-safety mutex).
   - Verifies NX environment via `verify_nx_environment()`.
   - Attempts socket connection to `127.0.0.1:43210` via `try_connect_socket(LIVE_PORT)`.
   - If disconnected:
     - Checks if `ugraf.exe` is already running (`_find_running_ugraf()`) to prevent duplicate instances.
     - Acquires cross-process mutex `bridge.launching.lock` via `msvcrt.locking`.
     - Spawns `ugraf.exe -auto=...nx_bridge.py` and waits up to `NX_MCP_LAUNCH_TIMEOUT` (180s).
   - Once connected, calls `_call_socket(s, tool, args)`:
     - Sets socket timeout: 300s for journal/recipe tools (`NX_MCP_JOURNAL_TIMEOUT`), 60s for standard operations (`NX_MCP_SOCKET_TIMEOUT`).
     - Transmits `{"tool": "create_cuboid", "args": {...}}\n`.
     - Awaits newline-delimited JSON response.
     - On success, updates `latest_nx_result.txt` and helper scripts (`open_current_nx_result.cmd`, `open_latest_nx_result.vbs`).

5. **In-NX Socket Bridge (`src/nx_mcp/bridge/nx_bridge.py`)**:
   - `run_socket_bridge()` runs an event loop inside `ugraf.exe` using `select.select()` and pumps UI events via `NXOpen.UI.GetUI().ProcessDeviceEvents()`.
   - Incoming payload is passed to `handle_line(line)`.
   - `handle_line()` makes a deep snapshot of `_state` (features, bodies, sketches, curves).
   - Passes command to `dispatch(command)`.

6. **Bridge Dispatch & Parameter Normalization**:
   - `dispatch()` resolves the function in `globals()`.
   - Performs compatibility normalization (e.g. converting `z_offset` to `z`, normalizing dimension parameter aliases).
   - Maps arguments to function signature using `inspect.signature`.

7. **Parametric Modeling & NXOpen Execution**:
   - `_ensure_work_part()` acquires or creates the active `.prt` file (with collision-avoidance logic).
   - Expression names are generated via `_next_instance_prefix("CUBOID")` (e.g. `CUBOID_1_L`, `CUBOID_1_W`, `CUBOID_1_H`).
   - Expressions are created in the NX part model: `_create_input_expression(work_part, "CUBOID_1_L", 100.0)`.
   - Feature Builder is instantiated: `work_part.Features.CreateBlockFeatureBuilder(Null)`.
   - Dimensions are bound by Expression Name RHS to guarantee 100% parametric editing.
   - `builder.CommitFeature()` executes the CAD kernel operation in native C++ memory.
   - `builder.Destroy()` is guaranteed in a `finally` block.
   - Created features and bodies are cached in `_state["features"]` and `_state["bodies"]` for downstream referencing.
   - `work_part.Save()` commits changes to disk.

8. **Response Propagation**:
   - `nx_bridge.py` returns `{"ok": true, "message": "Cuboid 100x50x30 created", "filepath": "..."}` over the TCP socket.
   - `runner.py` receives and returns the dict.
   - Tool wrapper packages it into a `ToolResult`.
   - `server.py` serializes it into MCP JSON-RPC format:
     ```json
     {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "OK: Cuboid 100x50x30 created"}]}}
     ```
   - AI Agent receives the result and proceeds to the next modeling step.

---

## 3. Tool Inventory Overview by Module

| Module | Registered Tools | Key Capabilities |
|---|---:|---|
| `src/nx_mcp/tools/modeling.py` | 27 | Primitives (cube, cuboid, cylinder), extrude, revolve, booleans (unite, subtract, combine), fillets, chamfers, holes, patterns (circular, feature), ribs, split body, emboss |
| `src/nx_mcp/tools/sketch.py` | 14 | 2D sketch plane setup, line, rectangle, circle, arc, spline (`draw_spline`), curve offset (`offset_curve`), curve closure (`close_curve_region`), constraints (horizontal, vertical, fixed) |
| `src/nx_mcp/tools/surface_modeling.py` | 53 | Studio surface, sweeps, through-curves, ruled surfaces, n-sided, fill, bounded plane, trims, sheets, thicken, extensions, face blends |
| `src/nx_mcp/tools/edit_operations.py` | 16 | X-Form, I-Form, match edge, heal surface, normal reversal, enlarge face, deformation, shaping, smoothing |
| `src/nx_mcp/tools/combine_operations.py` | 15 | Sew, unsew, make solid, divide face, patch body, trim & extend, sheet boundary analysis |
| `src/nx_mcp/tools/file_ops.py` | 5 | `create_part`, `open_part`, `save_part`, `export_step`, `export_stl` |
| `src/nx_mcp/tools/measure.py` | 5 | `measure_distance`, `measure_angle`, `measure_volume`, `get_bounding_box`, `measure_body_volume` |
| `src/nx_mcp/tools/utility.py` | 8 | Viewport control (`set_view`, `fit_view`), `take_screenshot`, `list_features`, `list_feature_edges`, `inspect_part`, `inspect_api`, `reset_nx_bridge` |
| `src/nx_mcp/tools/assembly.py` | 4 | `add_component`, `mate_components`, `reposition_component`, `list_components` |
| `src/nx_mcp/tools/recipe.py` | 1 | `run_recipe` (Deterministic ordered execution of multi-step tool recipes) |
| `src/nx_mcp/tools/discovery.py` | 2 | `get_relevant_nx_tools` (Context-aware tool discovery), `polar_to_cartesian_points` |
| **Total Registered** | **141** | Full spectrum parametric CAD automation |

---

## 4. Key Architectural Invariants

1. **Single Point of NXOpen Import**: `src/nx_mcp/bridge/nx_bridge.py` is the **only** production file that imports `NXOpen`. The MCP server and tools run in standard Python 3.10+ without NXOpen binaries.
2. **Socket-First Execution**: Communication with Siemens NX happens strictly over TCP `127.0.0.1:43210`. The legacy batch stdio mode is deprecated and returns `NX_PREWARM_REQUIRED_ERROR` to prompt running `prewarm_nx.py`.
3. **Parametric Integrity**: All dimensions are defined as named NX Expressions (e.g. `CUBOID_1_L = 100.0`) and features reference those expressions by name, allowing post-creation edits via `edit_expression`.
4. **Session Isolation**: Every `create_part` or `open_part` call triggers `_reset_transient_session_state()` to clear caches, sketch planes, and counters, guaranteeing zero state leakage between CAD builds.
5. **Fail-Safe Rollback**: If an exception occurs inside NX, `handle_line()` restores `_state` to its pre-command snapshot, preventing corrupted references in subsequent steps.
