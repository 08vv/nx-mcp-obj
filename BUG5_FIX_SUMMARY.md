# Bug 5 Fix Summary: 2D Sketch Geometry & Feature Z-Offset Positioning

## Overview
Bug 5 investigated issues where creating 2D sketch profiles intended to sit at a non-zero height (e.g. `Z=39..45` for a second arm on top of a cylinder post) failed to position or extrude the resulting solid at the expected height.

Live reproduction against Siemens NX 2206 empirically confirmed all three reported failure modes:
1. `create_real_sketch(plane="XY", z_offset=39.0)` failed outright with:
   `"Failed to create sketch in NX: First parameter is invalid. Expecting NXOpen.Sketch type, found NXOpen.Features.Feature."`
2. `create_sketch(plane="XY")` created a plane strictly at `Z=0` with no offset parameters.
3. `draw_rounded_rectangle(..., z=39.0)` accepted `z` and echoed `"z=39.0"` in its response message, but curves were created at `Z=0`, resulting in an extruded solid bounding box spanning `Z=[0.0, 6.0]` instead of `Z=[39.0, 45.0]`.

---

## 1. Confirmed Root Causes

### 1. `create_real_sketch` Builder Factory Type Mismatch
- **Location**: `src/nx_mcp/bridge/nx_bridge.py` (`create_real_sketch`)
- **Root Cause**: `work_part.Sketches.CreateNewSketchInPlaceBuilder(...)` expects an `NXOpen.Sketch` object (or `NXOpen.Sketch.Null`). The implementation passed `NXOpen.Features.Feature.Null`, causing NXOpen to immediately reject the call with `Expecting NXOpen.Sketch type, found NXOpen.Features.Feature`.
- In addition, the builder committed via `CommitFeature()` rather than `sketch_builder.Commit()`, which returns the newly created `NXOpen.Sketch`.

### 2. `_point_on_active_plane` Ignored Curve `z` Parameter
- **Location**: `src/nx_mcp/bridge/nx_bridge.py` (`_point_on_active_plane`, `draw_rounded_rectangle`, `draw_rectangle`, `draw_circle`, `draw_line`, `draw_arc`, `draw_spline`)
- **Root Cause**: `_point_on_active_plane(x, y)` only took `(x, y)` and unconditionally read `oz` from `_state.get("sketch_origin", [0, 0, 0])[2]`. When tools like `draw_rounded_rectangle(..., z=39.0)` accepted `z`, the local `z_val` was formatted into the success message string but never passed into `_point_on_active_plane`. The actual 3D points passed to `Curves.CreateLine` and `Curves.CreateArc` had `Z=0.0`.

### 3. `create_sketch` Lacked Offset Parameters
- **Location**: `src/nx_mcp/tools/sketch.py` & `src/nx_mcp/bridge/nx_bridge.py`
- **Root Cause**: `create_sketch` only accepted `plane="XY"`, always resetting `_state["sketch_origin"] = [0.0, 0.0, 0.0]`.

---

## 2. Fixes Applied

### 1. Unified Point Transformation (`_point_on_active_plane`)
Updated `_point_on_active_plane(x, y, z_override=None)` in [nx_bridge.py](file:///c:/Users/HP/nx-mcp/src/nx_mcp/bridge/nx_bridge.py#L1647-L1665):
- Evaluates `oz` from `_state["sketch_origin"][2]`.
- If `z_override` is passed from any 2D curve tool, `z_override` takes precedence.
- Correctly transforms `(x, y, z)` across `XY`, `XZ`, and `YZ` sketch orientations and plane rotations (`rotate_z_deg`).

### 2. Full Parameter Support in `create_sketch`
Updated `create_sketch(plane="XY", z_offset=0.0, origin_x=0.0, origin_y=0.0, rotate_z_deg=0.0)` in both [nx_bridge.py](file:///c:/Users/HP/nx-mcp/src/nx_mcp/bridge/nx_bridge.py#L1626-L1645) and [sketch.py](file:///c:/Users/HP/nx-mcp/src/nx_mcp/tools/sketch.py#L20-L46):
- Stores `[origin_x, origin_y, z_offset]` in `_state["sketch_origin"]`.
- Sets `_state["sketch_rotation"] = rotate_z_deg`.
- All subsequent 2D drawing calls on this sketch automatically inherit the plane's offset and rotation.

### 3. Fixed `create_real_sketch` Builder Implementation
Updated `create_real_sketch` in [nx_bridge.py](file:///c:/Users/HP/nx-mcp/src/nx_mcp/bridge/nx_bridge.py#L3468-L3537):
- Passes `NXOpen.Sketch.Null` to `CreateNewSketchInPlaceBuilder`.
- Sets `sketch_builder.PlaneReference = plane_obj`.
- Commits via `sketch_builder.Commit()`, extracts `sketch.Feature`, registers `sketch_id`, and stores `sketch` in `_state["sketches"]` using `setdefault`.

### 4. Direct `z` Override on 2D Primitives
Updated `draw_rounded_rectangle`, `draw_rectangle`, `draw_circle`, `draw_line`, `draw_arc`, and `draw_spline` to accept optional `z` parameters and pass `z_override` directly to `_point_on_active_plane`.

### 5. Tool Clarifications & Documentation
- **`create_base_surface`** ([surface_modeling.py](file:///c:/Users/HP/nx-mcp/src/nx_mcp/tools/surface_modeling.py#L12-L28)): Updated docstring to clarify that `create_base_surface` creates a permanent 3D sheet body for surface modeling workflows (trim/sew/thicken) and is **not** a 2D sketch plane.
- **Recommended Path**: Documented that for 2D sketch offset positioning, users/agents should use `create_sketch(plane="XY", z_offset=...)` or `create_real_sketch(plane="XY", z_offset=...)`.

---

## 3. Verification & Live Results

### 1. Live Empirical Verification in Siemens NX 2206 ([verify_bug5_live.py](file:///c:/Users/HP/nx-mcp/verify_bug5_live.py))

| Test Case | Operation | Measured Bounding Box | Result |
| :--- | :--- | :--- | :--- |
| **Test 1** | `create_sketch(plane="XY", z_offset=39.0)` + `draw_rounded_rectangle` + `extrude(6.0)` | `Min=(-8, -8, 39.0), Max=(24, 8, 45.0)` | **PASS** |
| **Test 2** | `create_real_sketch(plane="XY", z_offset=39.0)` + `draw_rectangle(20x20)` + `extrude(10.0)` | `Min=(0, 0, 39.0), Max=(20, 20, 49.0)` | **PASS** |
| **Test 3** | `create_sketch("XY")` (Z=0) + `draw_rounded_rectangle(..., z=39.0)` + `extrude(6.0)` | `Min=(-8, -8, 39.0), Max=(24, 8, 45.0)` | **PASS** |
| **Test 4** | End-to-end composite: Post (Z=0..45) + Bottom arm (Z=0..6) + Top rotated arm (Z=39..45) united into single solid | `Total Z Range: [0.00, 45.00]` + `Fillet R1.0 on 4 top edges` | **PASS** |

### 2. Unit & Regression Tests ([test_sketch_z_offset.py](file:///c:/Users/HP/nx-mcp/tests/test_sketch_z_offset.py))
- `pytest tests -v`: **252 / 252 passed in 1.31s** (100% pass rate).
