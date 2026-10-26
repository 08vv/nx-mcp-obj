# Parametric Modeling & Expression System

## Overview

NX-MCP implements an **expression-first parametric architecture**. Every geometric dimension created by high-level modeling tools is automatically registered as a named Siemens NX Expression in the part file. This allows AI agents or human engineers to later modify driving dimensions via `edit_expression`, triggering automatic downstream geometric updates across the CAD model.

---

## Expression Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                    Input Expressions                        │
│            (Direct numeric driving dimensions)              │
│       e.g., CUBOID_1_L = 100.0, CYLINDER_1_DIA = 50.0       │
└──────────────────────────────┬──────────────────────────────┘
                               │ Referenced by formulas
┌──────────────────────────────▼──────────────────────────────┐
│                   Formula Expressions                       │
│     (Computed mathematical relationships & constraints)     │
│        e.g., CUBOID_1_HALF_L = "CUBOID_1_L / 2"             │
│        e.g., WALL_THICK = "BASE_WIDTH * 0.1"                │
└──────────────────────────────┬──────────────────────────────┘
                               │ Bound to Feature Builders
┌──────────────────────────────▼──────────────────────────────┐
│                    CAD Feature Builders                     │
│    (Features consume Expression names on RightHandSide)     │
│       builder.Length.RightHandSide = "CUBOID_1_L"           │
│       builder.OriginPoint = Point3d(0, 0, 0)                │
└─────────────────────────────────────────────────────────────┘
```

---

## The Three Expression Types

1. **Input Expressions (`_create_input_expression`)**:
   - Represents fundamental user-specified design dimensions (length, width, height, diameter, radius).
   - Created with numerical literals as values:
     ```python
     _create_input_expression(work_part, "CUBOID_1_L", 100.0)
     # NX Expression created: CUBOID_1_L = 100.0
     ```

2. **Formula Expressions (`_create_formula_expression`)**:
   - Represents derived dimensions that dynamically track input expressions:
     ```python
     _create_formula_expression(work_part, "CUBOID_1_HALF_L", "CUBOID_1_L / 2")
     # NX Expression created: CUBOID_1_HALF_L = CUBOID_1_L / 2
     ```
   - When `CUBOID_1_L` is modified, `CUBOID_1_HALF_L` recalculates automatically.

3. **Named Expressions (`_create_named_expression`)**:
   - Internal helper generating sequential unique names (e.g. `RADIUS_1 = 5.0`).

---

## The Instance Prefix System

To prevent expression naming collisions when multiple features of the same type are added to a part (e.g. three separate cuboids):

```python
prefix = _next_instance_prefix("CUBOID")  # Returns "CUBOID_1"
_create_input_expression(wp, f"{prefix}_L", 100.0)

prefix = _next_instance_prefix("CUBOID")  # Returns "CUBOID_2"
_create_input_expression(wp, f"{prefix}_L", 40.0)
```

### Counter Seeding on Existing Parts (`_seed_counters_from_part`)

When opening an existing `.prt` file, `_seed_counters_from_part(work_part)` parses existing expressions using regular expressions:
```python
# Finds existing CUBOID_1, CUBOID_2 -> seeds _instance_counters["CUBOID"] = 2
```
Subsequent operations will automatically allocate `CUBOID_3`, preventing silent overwrites of existing geometry.

---

## The Standard Feature Builder Pattern

Every solid and curve tool in `bridge/nx_bridge.py` follows this standardized pattern:

```python
def create_cuboid(length=100.0, width=50.0, height=30.0, x=0.0, y=0.0, z=0.0, centered=False):
    work_part = _ensure_work_part()
    prefix = _next_instance_prefix("CUBOID")

    # 1. Create Driving Expressions
    _create_input_expression(work_part, f"{prefix}_L", length)
    _create_input_expression(work_part, f"{prefix}_W", width)
    _create_input_expression(work_part, f"{prefix}_H", height)

    # 2. Instantiate Feature Builder
    builder = work_part.Features.CreateBlockFeatureBuilder(Null)
    try:
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        
        # 3. Handle Positioning & Formulas
        if centered:
            _create_formula_expression(work_part, f"{prefix}_X", f"{x} - {prefix}_L / 2")
            _create_formula_expression(work_part, f"{prefix}_Y", f"{y} - {prefix}_W / 2")
            _create_formula_expression(work_part, f"{prefix}_Z", f"{z} - {prefix}_H / 2")
        else:
            _create_input_expression(work_part, f"{prefix}_X", x)
            _create_input_expression(work_part, f"{prefix}_Y", y)
            _create_input_expression(work_part, f"{prefix}_Z", z)

        # 4. Bind Dimensions via RightHandSide Expression References
        builder.SetLengthWidthHeight(f"{prefix}_L", f"{prefix}_W", f"{prefix}_H")
        builder.OriginPoint = Point3d(x, y, z)

        # 5. Commit Geometry
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        # 6. Guaranteed Resource Cleanup
        builder.Destroy()

    # 7. Persist to Disk
    work_part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    return {"ok": True, "message": f"Cuboid {length}x{width}x{height} created", "filepath": str(work_part.FullPath)}
```

---

## Safe Mathematical Expression Evaluation (`_safe_math_eval` & `spec/calc.py`)

To evaluate arithmetic expressions securely without exposing arbitrary code execution vulnerabilities through Python's `eval()`:
- `_safe_math_eval(expr_str)` uses `ast.parse()` to evaluate mathematical expressions (`+`, `-`, `*`, `/`, `**`).
- Function calls, variable assignments, and imports are strictly rejected.
- In CAD Specs, `$calc:` references allow expressions such as `$calc:$n1.length / 2 - 5` to be evaluated safely.

---

## Dynamic Parametric Editing (`edit_expression`)

```python
edit_expression(name="CUBOID_1_L", value="150.0")
```

When `edit_expression` is called:
1. `work_part.Expressions.FindObject(name)` locates the target expression.
2. Updates `expression.RightHandSide = str(value)`.
3. Invokes `session.UpdateManager.DoUpdate(undo_mark)` to trigger a full model re-solve.
4. NX automatically updates all dependent geometry and saves the part.

---

## Composable Parametric Operations

The following composable geometry operations allow building arbitrary parametric models without templates:

| Operation | Inputs | Expression Prefixes | Builders Used |
| :--- | :--- | :--- | :--- |
| `create_profile` | `points`, `plane="XY"`, `closed=True` | Wireframe curves registered to `profile_X` | `Curves.CreateLine` |
| `extrude_profile` | `profile_id`, `distance`, `start`, `direction`, `boolean`, `target` | `EXTRUDE_PROF_N_DIST`, `EXTRUDE_PROF_N_START` | `CreateExtrudeBuilder` |
| `loft` | `profile_ids`, `guide_curve_ids`, `body_type` | Multi-section through-curves | `CreateThroughCurvesBuilder` |
| `variable_offset` | `target_ref`, `offset_start`, `offset_end`, `law`, `body` | `OFFSET_CRV_N_START`, `OFFSET_CRV_N_END` / `OFFSET_FACE_N_DIST` | `CreateOffsetCurveBuilder`, `CreateOffsetFaceBuilder` |
| `pattern` | `feature_ref`, `mode`, `count`, `pitch`, `angle_total`, `axis`, `direction` | `PATTERN_N_COUNT`, `PATTERN_N_PITCH` / `CIRC_PAT_N_COUNT`, `CIRC_PAT_N_ANGLE` | `CreatePatternFeatureBuilder` |
| `shell` | `body_id`, `thickness`, `faces_to_remove` | `SHELL_N_THICK` | `CreateShellBuilder` |

---

## Related Documentation

- [cad_spec_system.md](cad_spec_system.md) — Declarative CAD Spec engine and `$expr:` / `$calc:` references.
- [bridge.md](bridge.md) — In-NX bridge execution and dispatching.
- [state.md](state.md) — State management and instance counters.
- [workflow.md](workflow.md) — Request lifecycle and recipe execution.
