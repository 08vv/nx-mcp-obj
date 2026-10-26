# NX-MCP Documentation Hub & Reading Guide

Welcome to the **NX-MCP** documentation library. This directory contains detailed architectural specifications, runtime guides, subsystem deep dives, and developer manuals.

Use this index to find exactly what you need based on your role or objective.

---

## Recommended Reading Paths

### 1. New to the Project? (Getting Oriented)
1. [**README.md**](../README.md) — High-level executive summary, installation, and quick start.
2. [**CODEBASE_EXPLAINED.md**](CODEBASE_EXPLAINED.md) — Walk-through of the codebase, key concepts, and file layout.
3. [**architecture.md**](architecture.md) — The 3-layer architecture (MCP protocol, tool wrappers, socket bridge).
4. [**workflow.md**](workflow.md) — End-to-end request lifecycle and execution sequences.

### 2. Developing CAD Automation or AI Agents?
1. [**nx_model_prompt_format.md**](nx_model_prompt_format.md) — How to format natural language prompts and CAD specs for best results.
2. [**workflow.md**](workflow.md) — Multi-step recipes (`run_recipe`) and deterministic execution.
3. [**cad_spec_system.md**](cad_spec_system.md) — The declarative CAD Spec DAG engine (`run_spec`), symbolic references (`$node.body_id`), and geometric math.
4. [**parametric.md**](parametric.md) — How parametric expressions and formulas are bound to CAD builders.
5. [**tool_routing.md**](tool_routing.md) — How tool categorization, token saving, and the Escape Hatch work.

### 3. Deep Dive into Runtime & Internals?
1. [**bridge.md**](bridge.md) — In-depth breakdown of `nx_bridge.py` running inside `ugraf.exe`.
2. [**runner.md**](runner.md) — Process supervision, TCP sockets, launch locks, and timeouts.
3. [**state.md**](state.md) — In-memory session state, rollback snapshots, and the persistent Geometry Dependency Graph.
4. [**tool_registry.md**](tool_registry.md) — How `@mcp_tool` works, JSON Schema reflection, and adding new tools.
5. [**limitations.md**](limitations.md) — Current constraints, edge cases, and resolved issues.

---

## Document Catalog

| Document | Focus & Summary | Key Topics |
|---|---|---|
| [**architecture.md**](architecture.md) | **System Architecture & Data Flow** | 3-layer design, transports (stdio & HTTP), protocol adapters, environment dependencies. |
| [**cad_spec_system.md**](cad_spec_system.md) | **Declarative CAD Spec Engine** | DAG operation graphs (`run_spec`), symbolic references (`$n1.body_id`), `$fn:` math helpers, preflight plausibility, execution lifecycle, post-execution verification. |
| [**state.md**](state.md) | **State Management & Dependency Graph** | In-bridge transient state (`_state`), rollback snapshots, session isolation resets, and the server-side persistent Geometry Dependency Graph (`dependency_graph.py`). |
| [**bridge.md**](bridge.md) | **In-NX Execution Engine** | `nx_bridge.py` (~6032 lines), TCP event loop, NXOpen API builders, expression bindings, AABB hole collision checks, and curve operations. |
| [**runner.md**](runner.md) | **Process & Transport Manager** | `runner.py`, socket communication (`127.0.0.1:43210`), mutexes (`bridge.launching.lock`), timeouts (60s/300s/180s), and watcher artifacts. |
| [**parametric.md**](parametric.md) | **Parametric Expression System** | Input expressions, formula expressions, instance prefix counters (`_next_instance_prefix`), counter seeding, and builder RightHandSide bindings. |
| [**tool_routing.md**](tool_routing.md) | **Dynamic Routing & Context Optimization** | 8 functional categories, 154 tools, weighted keyword scoring, prompt token reduction (~70%), spec vocabulary routing, and the Escape Hatch. |
| [**tool_registry.md**](tool_registry.md) | **Tool Registration & JSON Schemas** | `@mcp_tool` decorator, reflection of type hints and docstrings into JSON Schema, and step-by-step instructions for adding new CAD tools. |
| [**workflow.md**](workflow.md) | **Request Lifecycles & Recipes** | JSON-RPC 2.0 flow, multi-step sequential `run_recipe`, `run_spec` execution, mathematical journaling via `run_nx_journal_code`, and error rollback. |
| [**limitations.md**](limitations.md) | **Scope, Edge Cases & Resolved Fixes** | Serialized lock execution, socket-first mode, edge selection heuristics, and comprehensive log of resolved bug fixes. |
| [**nx_model_prompt_format.md**](nx_model_prompt_format.md) | **Mechanical CAD Prompt Guidelines** | Best practices for prompting models, decomposition into ordered features, coordinate math, and mandatory persistence rules. |
| [**codebase.md**](codebase.md) | **Developer & Agent Handbook** | Comprehensive technical manual detailing repository layout, file roles, API surfaces, and engineering invariants. |
| [**CODEBASE_EXPLAINED.md**](CODEBASE_EXPLAINED.md) | **Codebase Walkthrough** | High-level conceptual overview explaining how the pieces fit together for human developers and engineers. |
| [**TODO_NXOPEN_ROADMAP.md**](TODO_NXOPEN_ROADMAP.md) | **Development Milestones & Roadmap** | Historical progression through Phases 1–9 and upcoming Phase 10 roadmap items. |

---

## Codebase Structure Reference

```
c:\Users\HP\nx-mcp\
├── README.md                      # Primary project overview and quickstart
├── pyproject.toml                 # Packaging, scripts, and dev dependencies
├── prewarm_nx.py                  # Standalone launcher to prewarm Siemens NX + socket
├── clean_junk.py / clean_junk.bat # Utility to clean temporary build and test artifacts
│
├── docs/                          # Comprehensive technical documentation suite
│   ├── INDEX.md                   # This master documentation navigation index
│   ├── architecture.md            # 3-layer architecture & subsystems
│   ├── cad_spec_system.md         # Declarative CAD Spec DAG engine
│   ├── state.md                   # State management & Geometry Dependency Graph
│   ├── bridge.md                  # In-NX execution engine (nx_bridge.py)
│   ├── runner.md                  # Process management, sockets, and locks
│   ├── parametric.md              # Expression hierarchy & builder patterns
│   ├── tool_routing.md            # Keyword scoring & escape hatch mechanics
│   ├── tool_registry.md           # Tool registration & reflection schemas
│   ├── workflow.md                # End-to-end request lifecycle & recipes
│   ├── limitations.md             # Known constraints & resolved issues
│   ├── nx_model_prompt_format.md  # CAD prompt engineering guide
│   ├── codebase.md                # Developer & agent handbook
│   ├── CODEBASE_EXPLAINED.md      # Codebase explained walkthrough
│   └── TODO_NXOPEN_ROADMAP.md     # Development milestones & roadmap
│
├── src/nx_mcp/                    # Python Source Root
│   ├── server.py                  # MCP stdio server entry point
│   ├── http_server.py             # Optional FastAPI HTTP transport
│   ├── router.py                  # Dynamic keyword router (154 tools, 8 categories)
│   ├── response.py                # ToolResult and ToolError response objects
│   ├── nx_session.py              # NX session singleton
│   ├── nxopen_loader.py           # Loader for native or mock NXOpen
│   ├── cli_validate.py            # CLI validation utility
│   │
│   ├── spec/                      # Declarative CAD Spec Engine
│   │   ├── schema.py              # CAD Spec JSON schema definitions
│   │   ├── calc.py                # Safe math evaluator & $fn: expression parser
│   │   ├── geometry_math.py       # Geometric calculation helpers (bolt circles, polar)
│   │   ├── plausibility.py        # Preflight geometric & physical plausibility checks
│   │   ├── validator.py           # DAG topological validator & cycle detector
│   │   ├── executor.py            # Spec DAG executor, pause/resume, and node re-runs
│   │   ├── postcheck.py           # Post-execution geometric verification
│   │   └── geocheck.py            # Body, face, and edge geometric validation
│   │
│   ├── state/                     # Persistent State Subsystem
│   │   └── dependency_graph.py    # Geometry Dependency Graph (nodes, edges, integrity)
│   │
│   ├── tools/                     # 154 Registered MCP Tools
│   │   ├── _common.py             # Shared helpers (_bridge_result, _use_mock_nxopen)
│   │   ├── registry.py            # ToolRegistry and @mcp_tool decorator
│   │   ├── discovery.py           # get_relevant_nx_tools & coordinate utilities
│   │   ├── recipe.py              # run_recipe, run_spec, resume_spec, rerun_spec_node
│   │   ├── state_tools.py         # get_dependency_graph, upstream/downstream tools
│   │   ├── modeling.py            # 34 solid modeling tools (cuboid, cylinder, cuts...)
│   │   ├── sketch.py              # 16 sketch & curve tools (lines, splines, offsets...)
│   │   ├── surface_modeling.py    # 52 surface tools (studio surface, sweeps, lofts...)
│   │   ├── edit_operations.py     # 17 freeform edit tools (x-form, match edge...)
│   │   ├── combine_operations.py  # 15 combine tools (sew, unsew, make solid...)
│   │   ├── file_ops.py            # 6 part lifecycle tools (create, open, save, save_as...)
│   │   ├── measure.py             # 5 measurement tools (distance, volume, bbox...)
│   │   ├── utility.py             # 12 viewport & inspection tools (screenshot, inspect...)
│   │   └── assembly.py            # 4 assembly tools (add component, mate...)
│   │
│   ├── bridge/                    # Bridge Subsystem
│   │   ├── runner.py              # Server-side process manager, socket client, locks
│   │   └── nx_bridge.py           # In-NX execution engine (~6032 lines) inside ugraf.exe
│   │
│   ├── journals/templates/        # Reusable CAD templates (spur gear, impeller, etc.)
│   └── testing/mock_nxopen.py     # Comprehensive mock NXOpen module for pytest
│
└── tests/                         # Pytest test suite (259 passing tests)
```
