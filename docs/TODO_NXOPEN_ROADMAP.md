# NX-MCP Development Milestones & Roadmap

This document outlines the architectural development history of NX-MCP, recording the milestones completed across Phases 1–9 and detailing the future roadmap for Phase 10 and beyond.

---

## 1. Completed Milestones (Phases 1–9)

### Phase 1: Core MCP Protocol & Testing Harness (Completed)
- Standard Model Context Protocol (MCP) JSON-RPC 2.0 stdio server (`src/nx_mcp/server.py`).
- Centralized `ToolRegistry` with `@mcp_tool` decorator and automatic JSON Schema reflection.
- Comprehensive headless mock testing harness (`src/nx_mcp/testing/mock_nxopen.py`) allowing 100% unit test execution without requiring a live Siemens NX installation.
- Optional FastAPI HTTP server transport (`src/nx_mcp/http_server.py`).

### Phase 2: Socket-First In-NX Bridge (Completed)
- In-NX execution engine (`src/nx_mcp/bridge/nx_bridge.py`) running natively inside `ugraf.exe`.
- Non-blocking loopback TCP socket IPC on port `43210` with `select.select()` and `ui.ProcessDeviceEvents()`.
- Server-side process supervisor (`src/nx_mcp/bridge/runner.py`) with cross-process launch mutexes (`bridge.launching.lock`), thread serialization (`NXBridgeProcess._lock`), and dynamic timeouts (60s/300s/180s).
- Session boundary isolation (`_reset_transient_session_state`) and dynamic state rollback on failure (`handle_line`).

### Phase 3: Parametric Expression Architecture (Completed)
- 100% parametric dimension binding: All solid primitives and features create named NX expressions (`_create_input_expression`, `_create_formula_expression`).
- Feature builders bound via RightHandSide string names.
- Instance prefix system (`_next_instance_prefix`) preventing expression collisions.
- Expression counter seeding from existing `.prt` files (`_seed_counters_from_part`).
- Dynamic downstream re-solving via `edit_expression`.

### Phase 4: Dynamic Router & Context Optimization (Completed)
- Dynamic keyword-scoring router (`src/nx_mcp/router.py`) categorizing 154 tools into 8 functional domains.
- Context optimization reducing active tool schemas per turn by ~70% (~20,000–24,000 prompt tokens saved).
- Automatic server-side **Escape Hatch**: re-exposes all 154 tools instantly if an unexposed tool is invoked.
- Programmatic discovery tool (`get_relevant_nx_tools`) for agent tool pre-filtering.

### Phase 5: Declarative CAD Spec DAG Engine (Completed)
- Declarative CAD Spec architecture (`src/nx_mcp/spec/`) executed via `run_spec`.
- Dynamic symbolic reference resolution (`$node.field`, e.g. `$n1.body_id`).
- Safe AST-based mathematical calculation evaluator (`$calc:`).
- Pure deterministic geometry math functions (`$fn:bolt_circle`, `$fn:polar_to_cartesian`, `$fn:linear_spacing`, `$fn:lerp`).
- Automatic topological sorting and cycle detection (`validator.py`).

### Phase 6: Preflight Plausibility & Verification (Completed)
- Pre-execution geometric and physical plausibility validation (`plausibility.py`).
- Automatic spatial containment checks and aspect ratio sanity verification.
- Post-execution topological verification (`postcheck.py`, `geocheck.py`).
- Steppable execution with pause tokens (`resume_spec`) and selective node re-runs (`rerun_spec_node`).

### Phase 7: Persistent Geometry Dependency Graph (Completed)
- Server-side DAG tracking geometric entity lifecycles (`state/dependency_graph.py`).
- Tracks `alive` vs `consumed` statuses and topological edges (`consumed_by`, `produced_by`, `modified_by`).
- Double-consumption integrity validation.
- Inspection tools: `get_dependency_graph`, `get_downstream`, `get_upstream`, `validate_dependency_graph`.

### Phase 8: Subsystem Hardening & Core Bug Fixes (Completed)
- **RC3 Feature/Body Registration**: Fixed feature body lookup ensuring bodies created by composite features (hole chains, patterns) are reliably registered in `_state["bodies"]`.
- **Sequential Hole Tracking**: Preserves active target body references across multi-hole sequences.
- **Spline-to-Offset Curve Unrolling**: Fixes curve object flattening during spline offset chaining.
- **Pattern Body Preservation**: Preserves primary solid body during feature patterns and filters degenerate tool instance bodies.
- **Sketch Z-Offset Consistency**: Ensures `draw_rounded_rectangle` and 2D sketch curves omit Z coordinates by default to preserve the active sketch plane `z_offset`.

### Phase 9: Part Persistence & Operational Guardrails (Completed)
- Mandatory `save_part()` persistence enforcement across documentation and agent workflows (`create_part` creates session part only; `save_part` writes `.prt` to disk).
- Fillet / blend retry guardrail: Prevents repetitive failed blends on already-modified bodies.
- Prewarm retry re-issuance guardrail: Ensures `create_part` is re-issued after NX is prewarmed.
- 259 passing mock unit tests across all tools, spec engines, and state graphs.

---

## 2. Future Roadmap (Phase 10+)

### Milestone 10.1: Structured Rich Response Payloads
- Expand JSON-RPC response payloads from string messages to structured JSON dictionaries:
  ```json
  {
    "ok": true,
    "message": "Cuboid created successfully",
    "data": {
      "feature_tag": 12345,
      "body_id": "body_1",
      "expressions": {"CUBOID_1_L": 100.0, "CUBOID_1_W": 50.0, "CUBOID_1_H": 30.0},
      "bounding_box": {"min": [0,0,0], "max": [100,50,30]}
    }
  }
  ```
- Standardize return structure across all 154 tools.

### Milestone 10.2: Modularization of `nx_bridge.py`
- Refactor `src/nx_mcp/bridge/nx_bridge.py` (~6032 lines) into focused sub-modules:
  - `nx_bridge_core.py`: Socket server, event loop, state tracking, rollback.
  - `nx_bridge_solid.py`: Solid modeling, primitives, booleans, fillets, holes.
  - `nx_bridge_curves.py`: Sketches, splines, offset curves, regions.
  - `nx_bridge_surfaces.py`: Freeform surfaces, sweeps, lofts, face blends.

### Milestone 10.3: Automated Live Integration CI Suite
- Create an automated end-to-end integration test runner that boots a headless or interactive Siemens NX instance and runs live modeling workflows.
- Add performance benchmarks for socket IPC latency and multi-feature recipe execution.

---

## Related Documentation

- [INDEX.md](INDEX.md) — Master documentation index.
- [architecture.md](architecture.md) — System architecture overview.
- [limitations.md](limitations.md) — Active constraints and resolved fixes.
- [cad_spec_system.md](cad_spec_system.md) — Declarative CAD Spec DAG engine.
