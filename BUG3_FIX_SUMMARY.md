# Bug 3 Fix Summary: Edge Classification & Fillet Resolution on Composite Bodies

## Overview
Bug 3 investigated failures in `add_fillet` / `edge_blend` when invoked on composite bodies (e.g. cylinder post tangent-united with slot-shaped arms at varying Z heights and non-colinear angles). Two distinct error modes were analyzed, reproduced live against Siemens NX 2206, and fixed.

---

## 1. Confirmed Root Causes

### Part A: `IndexError` / `NameError` on `top_edges`, `bottom_edges`, `vertical_edges`
- **Root Cause**:
  1. `_resolve_edges()` invoked undefined functions (`get_edge_endpoints`, `_get_endpoints_raw`), causing `NameError` during spatial classification.
  2. The `selected` variable was uninitialized on several filter branches (`z_edges`, `vertical`, `top`, `bottom`, `max_x`, `min_x`, `max_y`, `min_y`), leading to `UnboundLocalError` or empty lists.
  3. When an empty list was returned, `add_fillet` unconditionally indexed `[selected_edges[0]]`, causing `IndexError: list index out of range`.
  4. The `else:` branch of `_resolve_edges()` silently fell back to returning all edges on the body, violating the project rule of "prefer failing loudly over silently resolving to the wrong geometry."

### Part B: `Unable to create Blend` on `outer_edges` & Modifying Features
- **Root Cause**:
  1. `add_fillet` passed `[selected_edges[0]]` to `CreateRuleEdgeMultipleSeedTangent`, forcing NX to blend along whatever edges were tangent to a single arbitrarily chosen seed edge. When `outer_edges` matched 31 edges (including tangent union seams), the blend either selected the wrong chain or failed.
  2. When NX rejected blend geometry (e.g. tangent-continuous union seams, oversized radii exceeding feature dimensions, or un-blendable corner topologies), NX raised raw `NXException: Unable to create Blend.` or `Unable to terminate the blend faces.` without explanatory context.

---

## 2. Fixes Applied

### 1. Robust Edge Endpoint Extraction (`_get_edge_endpoints`)
- Implemented `_get_edge_endpoints(edge)` in `src/nx_mcp/bridge/nx_bridge.py`:
  - Retrieves `Point3d` coordinates from `edge.GetVertices()`.
  - Handles single-vertex closed edges by returning `(p, p)`.
  - Uses `UF.Eval.AskLimits` and `UF.Eval.Evaluate` as a reliable fallback.
- Updated `_edge_midpoint(edge)` to use `_get_edge_endpoints(edge)`.

### 2. Spatial Classification & Fail-Loud Error Handling (`_resolve_edges`)
- Rebuilt `_resolve_edges()` to compute a body-wide `endpoints_map`:
  - **`top_edges` / `top` / `max_z`**: Dynamically evaluates the global `max_z` and selects edges where both endpoints satisfy `z >= max_z - 0.1mm`. On the composite body, accurately identifies the top circular rim of the post at `Z=45.0`.
  - **`bottom_edges` / `bottom` / `min_z`**: Evaluates global `min_z` and selects all planar bottom edges (`Z <= min_z + 0.1mm`).
  - **`vertical_edges` / `vertical` / `z_edges`**: Evaluates `dz > 0.001 and dx < 0.1 and dy < 0.1` or `dz > 0.5 * edge_length`. Accurately extracts all 10 vertical seam and slot edges on the composite body.
  - **`x_edges` / `y_edges` / `max_x` / `min_x` / `max_y` / `min_y`**: Evaluates planar coordinate alignment within 0.1mm tolerance.
  - **Unmatched / Unrecognized Edge Filters**: Raises `SelectionError` with a clear, descriptive message rather than silently defaulting to all edges.

### 3. Edge Collector Rules & Diagnostic Error Handling (`add_fillet`)
- Updated `add_fillet` to construct collector rules across the entire list of `selected_edges` using `CreateRuleEdgeMultipleSeedTangent(selected_edges, 0.5, True)` with fallback to individual `CreateRuleEdgeTangent` rules.
- Added comprehensive exception translation: when NX rejects an invalid blend (e.g. tangent seams or oversized radius), `add_fillet` catches the error and returns:
  `"Failed to create blend (radius=Xmm) on 'Y': NX rejected the blend geometry (Unable to create Blend). Possible causes: tangent-continuous union seams where no concave/convex corner exists, blend radius too large for geometry, or conflicting blend intersections. Try a smaller radius or specify feature-scoped edges (e.g. 'feature:feature_name')."`

---

## 3. Outcome for `outer_edges` & Spatial Hints on Composite Bodies

- **`outer_edges`**: **SUCCEEDS LIVE**. Fillets all outer perimeter edges across the composite body (`31 edges` blended in a single operation).
- **`top_edges`**: **SUCCEEDS LIVE**. Accurately targets the global post top rim (`1 edge`, `Z=45.0`).
- **`bottom_edges`**: **SUCCEEDS LIVE**. Accurately targets the bottom perimeter loop (`4 edges`, `Z=0.0`).
- **`vertical_edges`**: **SUCCEEDS LIVE**. Accurately targets all vertical edges (`10 edges`).
- **`cylinder_1:top`**: **SUCCEEDS LIVE**. Feature-scoped edge targeting accurately isolates the top rim.
- **Unrecognized / Oversized Fillets**: **FAILS LOUDLY AND CLEARLY** with actionable diagnostic error messages.

---

## 4. Live Verification Results (Siemens NX 2206)

Executed via [verify_bug3_live.py](file:///c:/Users/HP/nx-mcp/verify_bug3_live.py):

```
=== LIVE VERIFICATION: BUG 3 ON FRESH COMPOSITE BODIES ===

--- Test 1: edges='outer_edges' on fresh composite body ---
Result (outer_edges): {'ok': True, 'message': 'Fillet R1.5 on 31 edges', 'feature_id': 'feature_6', 'body_id': 'body_1', 'consumed': [], 'modified': ['body_1'], 'produced': []}

--- Test 2: edges='top_edges' on fresh composite body ---
Result (top_edges): {'ok': True, 'message': 'Fillet R1.5 on 1 edges', 'feature_id': 'feature_6', 'body_id': 'body_1', 'consumed': [], 'modified': ['body_1'], 'produced': []}

--- Test 3: edges='bottom_edges' on fresh composite body ---
Result (bottom_edges): {'ok': True, 'message': 'Fillet R1.5 on 4 edges', 'feature_id': 'feature_6', 'body_id': 'body_1', 'consumed': [], 'modified': ['body_1'], 'produced': []}

--- Test 4: edges='vertical_edges' on fresh composite body ---
Result (vertical_edges): {'ok': True, 'message': 'Fillet R1.5 on 10 edges', 'feature_id': 'feature_6', 'body_id': 'body_1', 'consumed': [], 'modified': ['body_1'], 'produced': []}

--- Test 5: feature-scoped 'cylinder_1:top' on fresh composite body ---
Result (cylinder_1:top): {'ok': True, 'message': 'Fillet R1.5 on 1 edges', 'feature_id': 'feature_6', 'body_id': 'body_1', 'consumed': [], 'modified': ['body_1'], 'produced': []}

--- Test 6: Non-matching edge filter 'non_existent_edges' ---
Result (non_existent): {'ok': False, 'error': "Failed to execute add_fillet: Unrecognized or unsupported edge reference: 'non_existent_edges' on body 'CYLINDER(0)'. Supported references: 'outer_edges', 'top_edges', 'bottom_edges', 'vertical_edges', 'x_edges', 'y_edges', 'z_edges', 'max_x', 'min_x', 'max_y', 'min_y', or feature-scoped 'feature_name:top'."}

--- Test 7: Oversized radius (R=50.0mm on 10mm cylinder) ---
Result (oversized R): {'ok': False, 'error': "Failed to create blend (radius=50.0mm) on 'top_edges': NX rejected the blend geometry (Unable to terminate the blend faces. Blend adjacent edges first or reduce the radius.). Possible causes: tangent-continuous union seams where no concave/convex corner exists, blend radius too large for geometry, or conflicting blend intersections. Try a smaller radius or specify feature-scoped edges (e.g. 'feature:feature_name')."}

[ALL PASS] Bug 3 Part A and Part B successfully verified live in Siemens NX 2206!
```

---

## 5. Test Suite Status
- **Offline Pytest**: `247 passed in 1.36s` (100% passing across all unit tests including new composite body spatial edge tests in `tests/test_edge_filtering.py`).
- **Live NX 2206 Integration**: All reproduction scripts (`verify_bug3_live.py`, `verify_all_bugs_live.py`, `verify_state_audit_live.py`, `verify_phase8_live.py`) pass.
