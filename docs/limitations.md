# Known Limitations & Technical Context

## Overview

This document provides a realistic and transparent audit of current architectural constraints, edge cases, and areas of ongoing hardening across the NX-MCP system.

---

## Architectural & Process Constraints

### 1. Serialized Tool Execution
All operations sent to Siemens NX pass through `NXBridgeProcess._lock`. Tool execution is strictly serialized; concurrent parallel tool executions against a single NX process are not supported. Long operations (e.g. executing complex journals, complex Boolean cuts, or large circular patterns) will hold the lock until completion.

### 2. Socket-First Execution Model
The live TCP socket on port `43210` is the primary and supported execution transport. The legacy batch stdio fallback (`run_journal.exe` subprocess) has been deprecated due to stdio unreliability in headless environments. If NX is not running and cannot auto-launch within `NX_MCP_LAUNCH_TIMEOUT` (180s), the runner returns `NX_PREWARM_REQUIRED_ERROR`. Developers/users should execute `python prewarm_nx.py` to establish the bridge session.

### 3. HTTP Server Dependencies
The optional HTTP server (`src/nx_mcp/http_server.py`) imports `fastapi` and `uvicorn`. These are optional dependencies not included in the default `pyproject.toml` base dependencies. To run the HTTP server, install them manually via `pip install fastapi uvicorn`.

---

## Geometric & NXOpen Integration Scope

### 1. Advanced Surface, Edit, and Assembly Scope
The codebase contains ~65 registered tools across `surface_modeling.py`, `edit_operations.py`, and `assembly.py` (e.g. `match_edge`, `x_form`, `i_form`, `heal_surface`, `sew_sheets`, `reposition_component`). While basic wrapper bindings exist, several of these advanced builders encounter NXOpen C++ signature variations across different NX version releases. For mission-critical workflows, solid modeling primitives, sketches, splines, offset curves, cuts, fillets, holes, and patterns are the verified path.

### 2. Hole Intersection Pre-Check (AABB)
`_validate_hole_intersection()` performs an Axis-Aligned Bounding Box (AABB) overlap check with a 1mm tolerance margin before committing hole operations. While this catches typical out-of-bounds coordinates, it cannot detect empty cavities inside complex hollowed or shelled geometries. A secondary post-operation edge count validation provides an extra safety check.

### 3. Edge Selection Geometric Heuristics
The edge resolver (`_resolve_edges()`) uses endpoint coordinate heuristics against bounding boxes (`UF_SESSION.Modeling.AskBndbox()`) to filter `"top_edges"`, `"vertical_edges"`, `"outer_edges"`, etc. On non-orthogonal, angled, or organic freeform geometry, geometric alignment heuristics may require explicit feature-based edge queries.

### 4. Mock vs. Live NXOpen Fidelity
Pytest unit tests run with `NX_MCP_USE_MOCK_NXOPEN=1`, utilizing `nx_mcp/testing/mock_nxopen.py`. The mock environment validates argument parsing, schema compliance, and routing, but does not simulate Siemens NX geometric kernel constraint solving or Parasolid topological checks. Real geometric validation requires running against a live NX session.

---

## Completed Improvements & Technical Debt Progress

| Area | Status | Notes |
|---|---|---|
| **Shared Helpers** | **Resolved** | Consolidated `_bridge_result()` and `_use_mock_nxopen()` into `src/nx_mcp/tools/_common.py`. |
| **Expression Collisions** | **Resolved** | Implemented `_next_instance_prefix()` and `_seed_counters_from_part()` to prevent expression overwrites. |
| **Session Bleed-Over** | **Resolved** | Implemented `_reset_transient_session_state()` on `create_part` and `open_part` boundaries. |
| **Fallback File Safety** | **Resolved** | `_ensure_work_part()` checks for existing geometry before reusing default fallback `.prt` files. |
| **Anti-Duplicate Launch Guard** | **Resolved** | Cross-process file mutex (`bridge.launching.lock`) and `_find_running_ugraf()` prevent multiple NX instances. |

---

## Future Roadmap

1. **Structured Rich Tool Responses**: Expand JSON-RPC response payloads from string messages to structured dictionaries containing created feature tags, body IDs, and bounding box dimensions.
2. **Modularized Bridge Subsystems**: Refactor `src/nx_mcp/bridge/nx_bridge.py` into focused sub-modules (`core`, `solid`, `curves`, `surface`).
3. **Automated Live Integration Suite**: Develop automated end-to-end integration tests that run against a live Siemens NX instance in CI/local test environments.

---

## Related Documentation

- [architecture.md](architecture.md) — Architecture overview.
- [bridge.md](bridge.md) — In-NX bridge execution engine.
- [state.md](state.md) — State management details.
