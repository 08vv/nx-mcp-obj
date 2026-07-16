# Expression Collision Fix Summary

This document summarizes the changes applied to fix the expression collision regression. By migrating all feature-creating tools to use a per-call instance prefix (e.g., `CUBOID_1_L`, `CUBOID_2_L`), we have resolved the issue where calling the same geometry tool multiple times in the same session would cause subsequent calls to silently overwrite existing parameters and resize/corrupt previously created features.

---

## 1. Summary of Changes

### Added Naming Helper Function
An instance-prefix helper was added to [nx_bridge.py](file:///c:/Users/HP/nx-mcp/src/nx_mcp/bridge/nx_bridge.py) next to expression creation utilities:
```python
_instance_counters = {}

def _next_instance_prefix(feature_type):
    count = _instance_counters.get(feature_type, 0) + 1
    _instance_counters[feature_type] = count
    return f"{feature_type}_{count}"
```

### Migrated Functions
A total of **31 functions** (plus the 2 formula-based functions) have been updated to call `_next_instance_prefix` at their start and prepend the generated prefix to all expressions:
1. `create_cuboid()` -> `CUBOID_{N}`
2. `create_cube()` -> `CUBE_{N}`
3. `create_cylinder()` -> `CYLINDER_{N}`
4. `add_chamfer()` -> `CHAMFER_{N}`
5. `add_fillet()` -> `FILLET_{N}`
6. `_subtract_cylinder_hole()` -> `HOLE_{N}`
7. `add_hole()` -> `HOLE_{N}`
8. `add_hole_nx()` -> `HOLE_{N}`
9. `pattern_feature()` -> `PATTERN_{N}`
10. `extrude_from_sketch()` -> `EXTRUDE_{N}`
11. `create_rib()` -> `RIB_{N}` (stores `half_t` formula referencing `{prefix}_T`)
12. `pattern_circular()` -> `CIRC_PAT_{N}` (plus circular fallback `CIRC_PAT_{N}_PITCH_DEG`)
13. `revolve_cut()` -> `REVOLVE_CUT_{N}`
14. `extrude_cut()` -> `EXTRUDE_CUT_{N}`
15. `extrude_surface()` -> `EXTRUDE_SURF_{N}`
16. `add_face_blend()` -> `FACE_BLEND_{N}`
17. `offset_surface()` -> `OFFSET_SURF_{N}`
18. `thicken_sheet()` -> `THICKEN_{N}`
19. `create_tube()` -> `TUBE_{N}`
20. `variable_offset()` -> `VAR_OFFSET_{N}`
21. `law_extension()` -> `LAW_EXT_{N}`
22. `aesthetic_face_blend()` -> `AESTHETIC_BLEND_{N}`
23. `blend_corner()` -> `BLEND_CORNER_{N}`
24. `variable_offset_face()` -> `VAR_OFFSET_FACE_{N}`
25. `extension_surface()` -> `EXT_SURF_{N}`
26. `silhouette_flange()` -> `SILHOUETTE_{N}`
27. `face_pairs()` -> `FACE_PAIRS_{N}`
28. `ribbon_builder()` -> `RIBBON_{N}`
29. `extend_sheet()` -> `EXT_SHEET_{N}`
30. `emboss_body()` -> `EMBOSS_{N}`
31. `local_untrim_extend()` -> `LOCAL_EXT_{N}`
32. `enlarge_face()` -> `ENLARGE_{N}`

### Threaded Formula Expressions (`create_offset_linkage_arm`)
In `create_offset_linkage_arm()`, a unique prefix `ARM_{N}` is generated. 
- All **10 base inputs** are created with `{prefix}_{param_name}` (e.g. `ARM_1_ARM_LENGTH`).
- All **13 derived expressions** are created with `{prefix}_{derived_name}` and store formulas referencing `{prefix}_` variables (e.g., `ARM_1_ARM_SPAN` = `ARM_1_ARM_LENGTH - 2.0 * ARM_1_END_RADIUS`).
- Values are read back using the prefixed names.
- Extrude limits and internal hole subtraction helpers are updated to use the prefixed names.

### Additional Robustness Improvements (Cylinder Spacer & Upper Arm Boolean Operations)
We found that executing `builder.BooleanOperation.Type = Unite` and `SetTarget(main_body)` inside `ExtrudeBuilder` raises errors under certain NX setups/versions (throwing `NXOpen.NXException: Invalid boolean type`).
To ensure maximum cross-version compatibility and robustness, the cylinder spacer and upper arm in `create_offset_linkage_arm` are now extruded as clean, separate solid bodies (`Create` type) and then united manually using the bridge's robust `boolean_unite()` function.

---

## 2. Verification Test Results

We re-ran the collision tests using [run_expression_collision_tests.py](file:///c:/Users/HP/nx-mcp/scratch/run_expression_collision_tests.py) inside a live NX session.

### `create_cuboid`
*   **Status**: **PASSED**
*   **Observed Expressions**:
    *   `CUBOID_1_L` = 100.0, `CUBOID_1_W` = 20.0, `CUBOID_1_H` = 5.0
    *   `CUBOID_2_L` = 40.0, `CUBOID_2_W` = 40.0, `CUBOID_2_H` = 40.0
*   **Observed Bodies**:
    *   `BLOCK(0)` (Cuboid 1): **100.0 x 20.0 x 5.0** (retains original dimensions)
    *   `BLOCK(1)` (Cuboid 2): **40.0 x 40.0 x 40.0**

### `create_cylinder`
*   **Status**: **PASSED**
*   **Observed Expressions**:
    *   `CYLINDER_1_R` = 10.0, `CYLINDER_1_H` = 30.0
    *   `CYLINDER_2_R` = 25.0, `CYLINDER_2_H` = 50.0

### `create_cube`
*   **Status**: **PASSED**
*   **Observed Expressions**:
    *   `CUBE_1_SIZE` = 15.0
    *   `CUBE_2_SIZE` = 35.0
*   **Observed Bodies**:
    *   `BLOCK(0)` (Cube 1): **15.0 x 15.0 x 15.0** (retains original dimensions)
    *   `BLOCK(1)` (Cube 2): **35.0 x 35.0 x 35.0**

### `create_offset_linkage_arm` (called twice in same session)
*   **Status**: **PASSED**
*   **Observed Expressions**:
    *   Two complete independent sets: `ARM_1_*` and `ARM_2_*`.
    *   Arm 1 derived parameters (e.g. `ARM_1_ARM_SPAN`) correctly reference `ARM_1_` base variables.
    *   Arm 2 derived parameters (e.g. `ARM_2_ARM_SPAN`) correctly reference `ARM_2_` base variables.
*   **Observed Bodies**:
    *   Two complete, independent arms created without collision.

### Existing Unit Test Suite (`pytest tests/`)
*   **Status**: **PASSED** (51 passed in 0.25s)

---

## 3. In-Memory Counter Naming Limitation

> [!IMPORTANT]
> The `_instance_counters` dictionary is an in-memory structure stored within the running NX socket bridge Python process. It resets if the bridge process restarts.
>
> If a bridge process is restarted, the counters for all feature types will reset to `0` and start naming from `1` again. If you open a previously saved `.prt` file in a new bridge session and call a geometry tool, the newly created expressions (e.g., `CUBOID_1_L`) could collide with and overwrite existing expressions of the same name saved in that part.
>
> To resolve this permanently, we would need to derive the starting counter values by querying the loaded `work_part` expressions when a part is loaded or when a tool is first run. For this task, we have highlighted this limitation as requested.
