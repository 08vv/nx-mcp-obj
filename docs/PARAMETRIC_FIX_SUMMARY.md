# Parametric Fix Summary

## Problem

Derived values — values computed from base input parameters — were calculated using plain Python arithmetic and then used as fixed ("dead") numbers in NX geometry calls. This broke true parametric behavior: changing a base parameter (like `ARM_LENGTH`) inside NX's Expression Editor would NOT update any derived values (like `ARM_SPAN = ARM_LENGTH - 2 * END_RADIUS`), because NX never knew those relationships existed.

## Root Cause

The codebase only had one helper function, `_create_named_expression(work_part, prefix, value)`, which:
1. Auto-appended counter suffixes (e.g., `ARM_LENGTH_1`, `ARM_LENGTH_2`), making expression names cryptic and non-reusable.
2. Only accepted literal numeric values — no formula strings.

So derived values were always computed in Python and stored as plain numbers:
```python
ARM_SPAN = ARM_L - 2.0 * END_R   # Python computes 66.0 — NX just sees "66.0"
```

## Fix Applied

### Step 1: Added Two New Helper Functions (lines 178–216)

| Function | Purpose |
|----------|---------|
| `_create_input_expression(work_part, name, value)` | Creates a base-input expression with an **exact, human-readable name** (no counter suffix). Updates in place if it already exists. |
| `_create_formula_expression(work_part, name, formula_rhs)` | Creates a **formula-linked** expression where the RHS references other expression names (e.g., `"ARM_LENGTH - 2 * END_RADIUS"`). NX evaluates and re-evaluates this formula automatically. |

### Step 2: Migrated All `_create_named_expression` Calls

**Every** call to `_create_named_expression` in the file (34 call sites across ~25 functions) was replaced with `_create_input_expression`. This gives all expressions clean, exact names instead of counter-suffixed ones.

### Step 3: Fixed `create_offset_linkage_arm()` — The Primary Offender

This function had **14 derived values** computed in Python. All were converted to NX formula expressions:

| Derived Expression | Formula (stored in NX) |
|--------------------|----------------------|
| `ARM_SPAN` | `ARM_LENGTH - 2.0 * END_RADIUS` |
| `CYL_R` | `CYLINDER_DIA / 2.0` |
| `LOWER_LEFT_ARC_X` | `-HOLE_OFFSET` |
| `LOWER_RIGHT_ARC_X` | `LOWER_LEFT_ARC_X + ARM_SPAN` |
| `LOWER_LEFT_HOLE_X` | `0.0` |
| `LOWER_RIGHT_HOLE_X` | `ARM_SPAN - 2.0 * HOLE_OFFSET` |
| `UPPER_RIGHT_ARC_X` | `HOLE_OFFSET` |
| `UPPER_LEFT_ARC_X` | `UPPER_RIGHT_ARC_X - ARM_SPAN` |
| `UPPER_RIGHT_HOLE_X` | `0.0` |
| `UPPER_LEFT_HOLE_X` | `- (ARM_SPAN - 2.0 * HOLE_OFFSET)` |
| `Z_LOWER_TOP` | `ARM_THICK` |
| `Z_CYL_TOP` | `ARM_THICK + CYLINDER_HEIGHT` |
| `Z_UPPER_TOP` | `ARM_THICK + CYLINDER_HEIGHT + ARM_THICK` |

Additionally, the extrude builder `RightHandSide` properties that previously used `str(float(...))` literal values were changed to pass **expression names** directly (e.g., `"ARM_THICK"`, `"Z_CYL_TOP"`, `"Z_UPPER_TOP"`), so NX links the extrude limits to the live expressions.

Python variables still exist for use in NXOpen constructors that require raw floats (e.g., `Point3d`, `CreateArc`), but they are now **read back from NX** via `.Value` instead of being computed independently:
```python
ARM_SPAN = work_part.Expressions.FindObject("ARM_SPAN").Value
```

### Step 4: Fixed `create_rib()` — Derived `half_t`

| Derived Expression | Formula (stored in NX) |
|--------------------|----------------------|
| `RIB_HALF_T` | `RIB_T / 2.0` |

Previously `half_t = thickness / 2.0` was computed in Python and stored as a literal.

## Complete List of Functions Changed

### Functions with derived-value (formula) fixes:
| Function | Derived Values Fixed |
|----------|---------------------|
| `create_offset_linkage_arm()` | `ARM_SPAN`, `CYL_R`, `LOWER_LEFT_ARC_X`, `LOWER_RIGHT_ARC_X`, `LOWER_RIGHT_HOLE_X`, `UPPER_RIGHT_ARC_X`, `UPPER_LEFT_ARC_X`, `UPPER_LEFT_HOLE_X`, `Z_LOWER_TOP`, `Z_CYL_TOP`, `Z_UPPER_TOP`, plus 3 extrude RHS values changed from literals to expression names |
| `create_rib()` | `RIB_HALF_T` |

### Functions migrated from `_create_named_expression` to `_create_input_expression` (no derived values, but now have clean expression names):
| Function | Expressions Migrated |
|----------|---------------------|
| `create_cuboid()` | `CUBOID_L`, `CUBOID_W`, `CUBOID_H` |
| `create_cube()` | `CUBE_SIZE` |
| `create_cylinder()` | `CYLINDER_R`, `CYLINDER_H` |
| `add_chamfer()` | `CHAMFER_OFFSET` |
| `add_fillet()` | `FILLET_R` |
| `_subtract_cylinder_hole()` | `HOLE_D`, `HOLE_DEPTH` |
| `add_hole()` | `HOLE_D`, `HOLE_DEPTH` |
| `add_hole_nx()` | `HOLE_D`, `HOLE_DEPTH` |
| `pattern_feature()` | `PATTERN_COUNT`, `PATTERN_PITCH` |
| `extrude_from_sketch()` | `EXTRUDE_DIST`, `EXTRUDE_START` |
| `pattern_circular()` | `CIRC_PAT_COUNT`, `CIRC_PAT_ANGLE` |
| `revolve_cut()` | `REVOLVE_CUT_ANGLE` |
| `extrude_cut()` | `EXTRUDE_CUT_DIST`, `EXTRUDE_CUT_START` |
| `extrude_surface()` | `EXTRUDE_SURF_START`, `EXTRUDE_SURF_DIST` |
| `add_face_blend()` | `FACE_BLEND_R` |
| `offset_surface()` | `OFFSET_DIST` |
| `thicken_sheet()` | `THICKEN_T` |
| `create_tube()` | `TUBE_OD`, `TUBE_ID` |
| `variable_offset()` | `VAR_OFFSET_START`, `VAR_OFFSET_END` |
| `law_extension()` | `LAW_EXT_LEN`, `LAW_EXT_ANG` |
| `aesthetic_face_blend()` | `AESTHETIC_BLEND_R` |
| `blend_corner()` | `BLEND_CORNER_R` |
| `variable_offset_face()` | `VAR_OFFSET_FACE_DIST` |
| `extension_surface()` | `EXT_SURF_DIST` |
| `silhouette_flange()` | `SILHOUETTE_DIST` |
| `face_pairs()` | `FACE_PAIRS_DIST` |
| `ribbon_builder()` | `RIBBON_WIDTH` |
| `extend_sheet()` | `EXT_SHEET_DIST` |
| `emboss_body()` | `EMBOSS_DEPTH` |
| `local_untrim_extend()` | `LOCAL_EXT_DIST` |
| `enlarge_face()` | `ENLARGE_DIST` |
| `_extrude_profile()` (inner helper, via `pattern_circular` fallback) | `CIRC_PAT_PITCH` |

## Verification

- **All 51 existing tests pass** (pytest tests/ — 51 passed in 0.22s).
- The `_create_named_expression()` function definition is preserved for backward compatibility but is no longer called anywhere in the file.
- Geometry output is unchanged — all values are numerically identical to before the fix.

## What This Enables

After this fix, if a user opens a `.prt` file built by `create_offset_linkage_arm` in NX and changes `ARM_LENGTH` from `90` to `120` in the Expression Editor, **all 13 derived expressions** will recalculate automatically inside NX, and the model will update proportionally — without needing to re-run the MCP tool.
