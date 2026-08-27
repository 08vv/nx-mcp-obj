# Phase 5 Summary: Deterministic Math

## 1. Phase 4 Unresolved Items Addendum

Before constructing Phase 5, the two unresolved items from Phase 4 were audited and reconciled:

1. **Body ID Lineage Reconciliation (`reconcile_phase4_ids.py`)**:
   - Re-ran the exact Phase 4 live graph: `create_part` $\rightarrow$ `create_profile` $\times 2$ $\rightarrow$ `loft` $\rightarrow$ `add_hole` $\rightarrow$ `shell` $\rightarrow$ `pattern`.
   - Reconciled the symbol table body IDs against NX `inspect_part`:
     - `body_1` (THRU_CURVE): Successfully created by `loft`, hollowed by `shell`, and preserved as the persistent boolean target through hole subtraction.
     - `body_2` (Cylinder tool body): Created transiently to subtract the center hole and consumed during the boolean operation. Because NX absorbed it into `body_1`, it no longer existed as an independent body.
     - `body_3` .. `body_6` (Pattern instances): The 4 patterned hole bodies.
   - **Conclusion**: The missing `body_2` in the final part body list was expected and correct behavior resulting from boolean target survival.

2. **Validation Invocation in `run_spec`**:
   - Verified that `run_spec` dispatches to `execute_spec(spec, stop_on_error=True)`, which initializes `SpecExecutor(spec, auto_validate=True)`.
   - Offline static validation is **automatic and fail-closed**. Any invalid spec fails before NX bridge dispatch.

---

## 2. Calc Expression Engine (`src/nx_mcp/spec/calc.py`)

### Architecture & Design Decisions
- **Safe AST Evaluator**: Replaces Python's `eval()` and `exec()` with an `ast.parse`-based evaluator (`mode="eval"`).
- **Security & Rejection Rules**:
  - Rejects imports, assignments, attribute lookups, lambdas, string literals, and arbitrary function calls.
  - Permits arithmetic operators (`+`, `-`, `*`, `/`, `//`, `%`, `**`), unary signs (`+`, `-`), comparisons, and ternary conditionals (`a if cond else b`).
  - Supports mathematical constants: `pi`, `e`, `tau`.
  - Supports safe deterministic mathematical functions: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `radians`, `degrees`, `sqrt`, `abs`, `round`, `ceil`, `floor`, `min`, `max`, `hypot`, `log`, `log10`, `exp`.
- **Execution Locality Decision**:
  - Calc evaluation is performed **server-side in the MCP process** without unnecessary bridge overhead.
  - If a `$calc:` expression references `$nodeId.field`, the executor substitutes the value directly from the in-memory `symbol_table`.
  - If a `$calc:` expression references `$expr:NAME`, the executor queries live NX expressions via a single `runner.call_nx("list_expressions")` round-trip at node execution time, substituting the real float value before invoking `safe_calc_eval`.

---

## 3. Geometry Math Function Library (`src/nx_mcp/spec/geometry_math.py`)

A pure, deterministic geometry math library providing callable functions via the `$fn:<name>(<args>)` grammar.

| Function | Signature | Return Type | Purpose |
| :--- | :--- | :--- | :--- |
| **`polar_to_cartesian`** | `(radius, angle_deg, center_x=0.0, center_y=0.0)` | `[x, y]` | Converts polar coordinates to 2D Cartesian point. |
| **`cartesian_to_polar`** | `(x, y, center_x=0.0, center_y=0.0)` | `{"radius": r, "angle_deg": theta}` | Converts 2D Cartesian point to polar coordinates. |
| **`bolt_circle`** | `(count, pcd, start_angle_deg=0.0, center_x=0.0, center_y=0.0)` | `[[x, y], ...]` | Computes evenly spaced bolt hole coordinate points on a pitch circle. |
| **`linear_spacing`** | `(count, pitch, start_x=0.0, start_y=0.0, direction_deg=0.0)` | `[[x, y], ...]` | Generates point coordinates along a directional pitch vector. |
| **`offset_point_along_vector`** | `(x, y, distance, direction_deg)` | `[x, y]` | Offsets a 2D point along an angle by a given distance. |

### Downstream Integration
- Functions like `bolt_circle` and `linear_spacing` return `List[List[float]]` (list of `[x, y]` pairs), matching `create_profile(points=...)`'s exact schema expectation.
- Functions returning single points or scalars seamlessly plug into scalar parameters (`x`, `y`, `diameter`, `radius`, `distance`).

---

## 4. Grammar & Reference Forms

CAD Spec parameters support 4 symbolic reference forms:
1. **`"$<node_id>.<field>"`**: Node output resolution (e.g. `"$base_plate.body_id"`).
2. **`"$expr:<NAME>"`**: NX expression binding (e.g. `"$expr:CUBOID_1_L"`).
3. **`"$calc:<expression>"`**: Arithmetic/trigonometric expressions (e.g. `"$calc:50 + 20 * cos(radians(60))"`).
4. **`"$fn:<func_name>(<args>)"`**: Geometry math library calls (e.g. `"$fn:bolt_circle(count=6, pcd=40.0, center_x=50.0, center_y=30.0)"`).

---

## 5. Validation Rules Added

The static validator (`src/nx_mcp/spec/validator.py`) has been upgraded with:
- **`$fn:` Function Inspection**: Introspects registered functions in `GEOMETRY_FUNCTIONS` using `inspect.signature` to verify function existence and required argument completeness.
- **Embedded Reference Validation**: Inspects `$calc:` strings to ensure any nested `$nodeId.field` references point to existing, topologically preceding nodes producing the requested output.
- **Type Bypass Tolerance**: Allows `$fn:` references alongside `$calc:` and `$nodeId.field` to pass static schema type checks for deferred runtime resolution.

---

## 6. Live Integration Verification ([verify_phase5_live.py](file:///c:/Users/HP/nx-mcp/verify_phase5_live.py))

A 9-node CAD Spec exercising `$calc:` expressions, `$fn:bolt_circle`, profile generation, hole subtraction, and edge blending was executed live against Siemens NX 2206:

```
=== STARTING PHASE 5 LIVE VERIFICATION (DETERMINISTIC MATH) ===
[PASS] NX live socket bridge reachable.

1. Executing Phase 5 CAD Spec with $calc: and $fn: references...

2. Execution Report:
   ok:             True
   status:         completed
   total_nodes:    9
   executed_nodes: ['init', 'base_plate', 'mounting_profile', 'center_hole', 'bolt_h1', 'bolt_h2', 'bolt_h3', 'bolt_h4', 'fillet']
   skipped_nodes:  []

3. Symbol Table:
   [init] -> {'filepath': '...\\phase5_live_1787834771941.prt'}
   [base_plate] -> {'body_id': 'body_1', 'feature_id': 'feature_1'}
   [mounting_profile] -> {'profile_id': 'profile_1', 'curve_ids': ['curve_1', 'curve_2', 'curve_3', 'curve_4', 'curve_5', 'curve_6']}
   [center_hole] -> {'body_id': 'body_1', 'feature_id': 'feature_3'}
   [bolt_h1] -> {'body_id': 'body_1', 'feature_id': 'feature_5'}
   [bolt_h2] -> {'body_id': 'body_1', 'feature_id': 'feature_7'}
   [bolt_h3] -> {'body_id': 'body_1', 'feature_id': 'feature_9'}
   [bolt_h4] -> {'body_id': 'body_1', 'feature_id': 'feature_11'}
   [fillet] -> {}

4. inspect_part: body_count = 1 (BLOCK(0), faces=16, edges=25)
[SUCCESS] PHASE 5 DETERMINISTIC MATH FULLY VERIFIED LIVE IN NX 2206!
```

---

## 7. Test Suite Status

- **Unit Tests (`pytest`)**: **194 / 194 passing** across 12 test files (`tests/test_calc.py`, `tests/test_geometry_math.py`, `tests/test_spec_executor.py`, `tests/test_spec_validator.py`, etc.).
- **Live NX 2206 Integration**: `verify_phase5_live.py` passed with exit code 0.
