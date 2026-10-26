# Known Limitations & Technical Context

## Overview

This document provides a realistic and transparent audit of current architectural constraints, edge cases, active guardrails, and completed hardening across the NX-MCP system.

---

## Architectural & Process Constraints

### 1. Serialized Tool Execution
All operations sent to Siemens NX pass through `NXBridgeProcess._lock`. Tool execution is strictly serialized; concurrent parallel tool executions against a single NX process are not supported. Long operations (e.g. executing complex journals, complex Boolean cuts, or large circular patterns) hold the lock until completion.

### 2. Socket-First Execution Model
The live TCP socket on port `43210` is the primary and supported execution transport. The legacy batch stdio fallback (`run_journal.exe` subprocess) has been deprecated due to stdio buffering unreliability in headless environments. If NX is not running and cannot auto-launch within `NX_MCP_LAUNCH_TIMEOUT` (180s), the runner returns `NX_PREWARM_REQUIRED_ERROR`. Developers/users should execute `python prewarm_nx.py` to establish the bridge session.

### 3. HTTP Server Dependencies
The optional HTTP server (`src/nx_mcp/http_server.py`) imports `fastapi` and `uvicorn`. These are optional dependencies not included in the default `pyproject.toml` base dependencies. To run the HTTP server, install them manually via `pip install fastapi uvicorn`.

### 4. Mandatory Part Persistence Guardrail
`create_part` creates a part in Siemens NX **session memory only** — it does NOT write the `.prt` file to disk. You **MUST** explicitly call `save_part()` at the end of every modeling sequence. Any build without an explicit `save_part()` call has not been persisted to disk and will be lost if NX closes.

---

## Geometric & NXOpen Integration Scope

### 1. Advanced Surface, Edit, and Assembly Scope
The codebase contains registered tools across `surface_modeling.py`, `edit_operations.py`, and `assembly.py` (e.g. `match_edge`, `x_form`, `i_form`, `heal_surface`, `sew_sheets`, `reposition_component`). While basic wrapper bindings exist, several of these advanced builders encounter NXOpen C++ signature variations across different NX version releases. For mission-critical workflows, solid modeling primitives, sketches, splines, offset curves, cuts, fillets, holes, and patterns are the verified path.

### 2. Hole Intersection Pre-Check (AABB)
`_validate_hole_intersection()` performs an Axis-Aligned Bounding Box (AABB) overlap check with a 1mm tolerance margin before committing hole operations. While this catches typical out-of-bounds coordinates, it cannot detect empty cavities inside complex hollowed or shelled geometries. A secondary post-operation edge count validation provides an extra safety check.

### 3. Edge Selection Geometric Heuristics
The edge resolver (`_resolve_edges()`) uses endpoint coordinate heuristics against bounding boxes (`UF_SESSION.Modeling.AskBndbox()`) to filter `"top_edges"`, `"vertical_edges"`, `"outer_edges"`, etc. On non-orthogonal, angled, or organic freeform geometry, geometric alignment heuristics may require explicit feature-based edge queries.

### 4. Fillet / Blend Retry Guardrail
After `add_fillet` or `edge_blend` succeeds (even partially), do not retry `add_fillet`/`edge_blend` on the same feature/body with a different edge hint without first checking `list_features`. If a prior fillet already consumed the target edges, retrying blindly will continue to fail.

### 5. Mock vs. Live NXOpen Fidelity
Pytest unit tests run with `NX_MCP_USE_MOCK_NXOPEN=1`, utilizing `nx_mcp/testing/mock_nxopen.py`. The mock environment validates argument parsing, schema compliance, and routing across all 259 tests, but does not simulate Siemens NX Parasolid topological constraint solving. Real geometric validation requires running against a live NX session.

---

## Completed Hardening & Resolved Issues

| Area | Status | Technical Resolution |
|---|:---:|---|
| **Shared Helpers** | **Resolved** | Consolidated `_bridge_result()` and `_use_mock_nxopen()` into `src/nx_mcp/tools/_common.py`. |
| **Expression Collisions** | **Resolved** | Implemented `_next_instance_prefix()` and `_seed_counters_from_part()` to prevent expression overwrites. |
| **Session Bleed-Over** | **Resolved** | Implemented `_reset_transient_session_state()` on `create_part` and `open_part` boundaries. |
| **Fallback File Safety** | **Resolved** | `_ensure_work_part()` checks for existing geometry before reusing default fallback `.prt` files. |
| **Anti-Duplicate Launch Guard** | **Resolved** | Cross-process file mutex (`bridge.launching.lock`) and `_find_running_ugraf()` prevent multiple NX instances. |
| **RC3 Body Registration** | **Resolved** | Fixed feature body lookup ensuring bodies created by composite features (e.g. hole chains, patterns) are reliably registered in `_state["bodies"]`. |
| **Sequential Hole Tracking** | **Resolved** | Preserves active target body references across multi-hole sequences. |
| **Spline-to-Offset Flattening** | **Resolved** | Resolves single curves from history as unrolled curve objects for `offset_curve` and `close_curve_region`. |
| **Pattern Body Preservation** | **Resolved** | Preserves primary solid body during feature patterns and filters degenerate tool instance bodies. |
| **Sketch Z-Offset Consistency** | **Resolved** | Ensures `draw_rounded_rectangle` and 2D sketch curves omit Z coordinates by default to preserve the active sketch plane `z_offset`. |
| **Part Persistence Enforcement** | **Resolved** | Added mandatory `save_part()` persistence rules and guardrails across docs and agent guidelines. |

---

## Future Roadmap (Phase 10+)

1. **Structured Rich Tool Responses**: Expand JSON-RPC response payloads from string messages to structured dictionaries containing created feature tags, body IDs, and bounding box dimensions.
2. **Modularized Bridge Subsystems**: Refactor `src/nx_mcp/bridge/nx_bridge.py` into focused sub-modules (`core`, `solid`, `curves`, `surface`).
3. **Automated Live Integration CI**: Develop automated end-to-end integration tests that execute against a headless or containerized Siemens NX instance.

---

## Related Documentation

- [architecture.md](architecture.md) — Architecture overview.
- [bridge.md](bridge.md) — In-NX bridge execution engine.
- [state.md](state.md) — State management and Geometry Dependency Graph.
- [workflow.md](workflow.md) — Request lifecycle and recipe workflows.
