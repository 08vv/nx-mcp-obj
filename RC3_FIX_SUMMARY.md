# RC3 Root Fix Summary: Feature Registration & Body State Integrity

---

## 1. Executive Summary

During previous audits (RC1-RC6), **RC3** identified that `_register_feature` unconditionally registered every body returned by `feature.GetBodies()`, corrupting `_state["last_body"]` and `_state["last_body_id"]` to point to whichever body was last in the loop. While pattern tools were given a local workaround in that audit, modifying operations like `add_hole`, `mirror_feature`, and the surface builder family remained vulnerable.

This update implements the **root-level fix in `_register_feature` and `_register_body`**, completely closing RC3 across the entire codebase rather than relying on per-tool patches.

---

## 2. Root Cause & Architectural Defect

### The Defect in `_register_feature`
In `nx_bridge.py`, `_register_feature` previously executed:
```python
# DEFECTIVE CODE:
get_bodies = getattr(feature, "GetBodies", None)
if callable(get_bodies):
    for b in get_bodies() or []:
        if _is_real_solid_body(b):
            _register_body(b)  # Unconditionally set last_body = b on every iteration!
```
When `_register_body(b)` was called:
- It unconditionally updated `_state["last_body"] = b` and `_state["last_body_id"] = body_id`.
- If a feature generated multiple bodies (e.g., intermediate tool bodies, unmerged solids, or auxiliary bodies), `last_body` was hijacked by the last body in the list.
- In `add_hole`, when HoleBuilder or the cylinder subtraction executed, the tool body contaminated `_state["last_body"]`, causing subsequent operations or bounding-box queries to resolve to leftover tool bodies or report drift.

---

## 3. Root Fix Implementation

### A. Non-Destructive Registration in `_register_body`
Added an explicit `set_last=True` parameter to `_register_body`:
```python
def _register_body(body, set_last=True):
    if body is None:
        return None
    tag = getattr(body, "Tag", None)
    if tag and tag in _state.get("object_to_id", {}):
        bid = _state["object_to_id"][tag]
        if set_last:
            _state["last_body"] = body
            _state["last_body_id"] = bid
        return bid

    _state["body_counter"] = _state.get("body_counter", 0) + 1
    body_id = f"body_{_state['body_counter']}"
    _state.setdefault("id_map", {})[body_id] = body
    _state.setdefault("bodies", {})[body_id] = body
    if tag:
        _state.setdefault("object_to_id", {})[tag] = body_id
    if set_last:
        _state["last_body"] = body
        _state["last_body_id"] = body_id
    name = _body_name(body)
    _state["bodies"][name.lower()] = body
    return body_id
```

### B. Root Fix in `_register_feature`
`_register_feature` now determines the target body based on feature semantics:
1. **Modifying Feature with Explicit `target_body`**: Registers all bodies with `set_last=False`, then explicitly sets `target_body` as `last_body`.
2. **Initial Solid Creation (`last_body is None`)**: Sets the first valid solid body as `last_body`.
3. **Pure Creation Feature (`is_creation=True`)**: Sets the first valid solid body as `last_body`.
4. **Modifying / Pattern / Mirror Feature (`is_creation=False`)**: Registers all bodies with `set_last=False` and preserves the pre-existing `last_body` / `last_body_id`.

```python
def _register_feature(feature, target_body=None, is_creation=False):
    ...
    try:
        get_bodies = getattr(feature, "GetBodies", None)
        if callable(get_bodies):
            feat_bodies = [b for b in (get_bodies() or []) if _is_real_solid_body(b)]
            prev_last_body = _state.get("last_body")

            for b in feat_bodies:
                _register_body(b, set_last=False)

            if target_body is not None and _is_real_solid_body(target_body):
                _register_body(target_body, set_last=True)
            elif prev_last_body is None and feat_bodies:
                _register_body(feat_bodies[0], set_last=True)
            elif is_creation and feat_bodies:
                _register_body(feat_bodies[0], set_last=True)
            elif prev_last_body is not None and _is_real_solid_body(prev_last_body):
                _register_body(prev_last_body, set_last=True)
    except Exception:
        pass
```

### C. Modifying Feature Tool Updates
- **`add_hole` & `add_hole_nx`**: Both the native `HoleBuilder` and `_subtract_cylinder_hole_parametric` paths now preserve `pre_bid`, re-resolve the target body, call `_rebind_body_id(pre_bid, fresh_body)`, pass `target_body=target_body, is_creation=False` to `_remember_feature`, and return structured responses (`body_id`, `modified: [pre_bid]`).
- **`mirror_feature` & `pattern_feature`**: Explicitly pass `target_body=target_body, is_creation=False` and maintain target body bindings.
- **`_execute_surface_builder`**: Surface sheet operations pass `is_creation=False` to prevent sheet bodies from hijacking solid body tracking.
- **Creation Primitives (`create_cylinder`, `create_cuboid`, `create_cube`, `extrude`, `revolve`, `extrude_from_sketch`)**: Explicitly pass `is_creation=True` so newly generated solids become `last_body`.

---

## 4. Verification & Results

### A. Live Empirical Verification in Siemens NX 2206 ([verify_rc3_live.py](file:///c:/Users/HP/nx-mcp/verify_rc3_live.py))
- **Step 1 (Base Cylinder Post R=10, H=45)**: Created `body_1` -> **[PASS]**
- **Step 2 (Bottom Arm Z=0..6 & Unite)**: Created `body_2` -> **[PASS]**
- **Step 3 (Top Arm Z=39..45 & Unite)**:
  - Local isolated check before union verified: `Z range = [39.00, 45.00]` -> **[PASS]**
  - Unified into composite solid `body_3` -> **[PASS]**
- **Step 4 (3 Sequential Holes on Composite Body)**:
  - **Hole 1 (Arm 1 tip at X=24, Y=0, Z=6)**: `body_id=body_3, consumed=['body_4'], modified=['body_3']` -> **[PASS]**
  - **Hole 2 (Arm 2 tip at X=-12, Y=20.785, Z=45)**: `body_id=body_3, consumed=['body_5'], modified=['body_3']` -> **[PASS]**
  - **Hole 3 (Post center at X=0, Y=0, Z=45, D=8, depth=20)**: `body_id=body_3, consumed=['body_6'], modified=['body_3']` -> **[PASS]**
  - After all 3 holes, `last_body_id` remained strictly bound to `body_3`, and intermediate tool bodies (`body_4`, `body_5`, `body_6`) were completely purged from `_state["bodies"]` and `_state["id_map"]`.
- **Step 5 (Edge Blend on Bottom Edges)**: `Fillet R1.0 on 5 edges` succeeded on `body_3` -> **[PASS]**

### B. Automated Unit Tests ([test_rc3_feature_registration.py](file:///c:/Users/HP/nx-mcp/tests/test_rc3_feature_registration.py))
- `test_register_body_set_last_flag`: Verified `set_last=False` preserves active `last_body`.
- `test_register_feature_does_not_hijack_last_body`: Verified multi-body features do not corrupt `last_body`.
- `test_sequential_holes_state_tracking_mock`: Verified sequential holes maintain stable `last_body_id`.
- **Full Test Suite**: **255 passed in 0.85s**.

---

## 5. Documented Caveat: Bounding Box Verification on Composite Bodies

> [!IMPORTANT]
> **Verification Caveat: Composite Body Bounding Box vs Sub-Feature Position**
> 
> Checking the overall bounding box of a composite body (e.g. `get_bounding_box("last") -> Z=[0, 45]`) is **not** sufficient proof that a newly added sub-feature merged at the correct height if an existing feature (such as the base cylinder post) already spans that entire range (`0 to 45`).
> 
> **Standard Verification Procedure Going Forward:**
> 1. **Pre-Union / Local Check**: Query `get_bounding_box` on the isolated sub-feature solid *immediately after extrusion* (before executing `boolean_unite`), confirming its exact local coordinates (e.g. `Z=[39.0, 45.0]`).
> 2. **Feature-Scoped Inspection**: Inspect the specific feature's faces or edge tags post-union using feature-scoped queries (`_resolve_feature_edges` / feature-specific bounds).
