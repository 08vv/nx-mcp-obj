# Bug-Fix Summary: Impeller Disk End-to-End Defects

## Context
Two defects were surfaced during a real end-to-end structured-tools-only impeller disk
build: `create_cylinder → draw_spline → offset_curve → close_curve_region → extrude_cut
→ pattern_circular → add_fillet → get_bounding_box`. Neither bug was caught by any
phase's own live verification because no phase exercised the exact cross-tool combination
that triggers them.

---

## Bug 1: `offset_curve` / `close_curve_region` fail with `'list' object has no attribute 'Tag'`

### Reproduction
```python
draw_spline(points=[...5 points...])    # succeeds, returns curve
offset_curve(curve_reference="last")    # FAILS: 'list' object has no attribute 'Tag'
close_curve_region(curve1="last", ...)  # FAILS: same error
```

### Root Cause
`draw_spline` stores curves in `_state["curve_history"]` as `[spline_curve]` (a list
wrapping each curve). `_resolve_single_curve` iterated over `curve_history` entries
treating each item as a raw curve object, but since each item was actually a list, calls
like `getattr(c, "Tag", "")` on the list returned `""`, filtering out all valid curves.
The fallback `history[-1]` returned `[spline_curve]` (the list), and subsequent
`source_curve.Tag` raised `AttributeError`.

### Fix (Commit `af9d471`)
- Rewrote `_resolve_single_curve()` to **flatten** `curve_history` entries — unwrapping
  any nested lists/tuples into individual curve objects before filtering.
- Added ID-map lookup (`curve_N` references) and broadened `ref_str` matching to include
  `"last_curve"`, `"previous_curve"` etc.
- Rewrote `_resolve_curve_group()` with the same flattening logic.
- Added 2 regression tests in `tests/test_sketch_spline_offset.py`.

---

## Bug 2: `add_fillet` / `get_bounding_box` target wrong body after `pattern_circular`

### Reproduction
```python
create_cylinder(radius=60, height=16)        # body_1
add_hole(x=30, y=0, diameter=5, depth=16)    # modifies body_1
pattern_circular(feature_name="last", count=9, angle_total=360)
  # NX internally creates SUBTRACT(3:1B) tool instance bodies with zero extent
  # pattern_circular registered these as body_3, displacing body_1 from last_body
add_fillet(radius=0.5, edges="outer_edges")  # Filleted body_3 (zero-extent) instead of body_1!
get_bounding_box()                           # Returns (0,0,0)→(0,0,0) for body_3
```

### Root Cause
NX's `PatternFeature` on subtract/hole features generates internal unconsumed tool bodies
named `SUBTRACT(N:NB)` with zero bounding-box extent. The post-pattern body diff loop
detected these as "new" bodies, called `_register_body()` on them, displacing the actual
solid disk from `_state["last_body"]`. All subsequent `body="last"` references then
resolved to the degenerate tool body.

### Fix (Commit `bbe5fab`)
Multi-layered defense:

1. **`_is_real_solid_body(body)`** — new helper checks `IsSolidBody` flag and validates
   non-zero bounding box extent (dx, dy, dz > 1e-4).

2. **`_body_volume_metric(body)`** — new helper returns approximate bounding box volume
   for ranking bodies when multiple candidates exist.

3. **`pattern_feature()` / `pattern_circular()`** — when `pre_last_body` exists (feature
   is being patterned on an existing solid), skip body registration entirely and restore
   `_state["last_body"]` to the pre-pattern target body.

4. **`_resolve_body("last")`** — when falling back to part bodies, selects the body with
   the largest bounding box volume via `_body_volume_metric`, ensuring the primary solid
   part body is always preferred over degenerate tool instances.

5. **`_remember_feature()`** — only registers feature-produced bodies when no existing
   `last_body` is set, preventing subtractive features from displacing the target.

6. **`extrude_cut()`** — explicitly restores `_state["last_body"]` to the target body
   after the cut, and returns proper `body_id`/`modified`/`produced` metadata.

7. **`get_bounding_box()`** — supports `"all"`/`"part"` references for whole-part union
   bounding boxes, and always returns structured `bounding_box: {min, max}` data.

- Added 2 regression tests in `tests/test_pattern_fillet_resolution.py`.

---

## Test Coverage

| Suite | Tests | Status |
|-------|-------|--------|
| Full offline pytest | 246 | ✅ All passing |
| `test_sketch_spline_offset.py` | 2 | ✅ Bug 1 regression |
| `test_pattern_fillet_resolution.py` | 2 | ✅ Bug 2 regression |

## Live Verification

### Bug 1: ✅ Confirmed Fixed
```
draw_spline:        ok=True, curve_id='curve_1'
offset_curve:       ok=True, 'Variable offset spline 3.0→5.0mm'
close_curve_region: ok=True, curve_count=4
```
Previously: `'list' object has no attribute 'Tag'`

### Bug 2: ✅ Confirmed Fixed
```
pattern_circular:   ok=True, body_id='body_1', modified=['body_1'], produced=[]
add_fillet:         ok=True, 'Fillet R1.0 on 2 edges', body_id='body_1'
get_bounding_box:   ok=True, Min=(-60, -60, 0), Max=(60, 60, 16)
```
Previously: `body_id='body_3'` (zero-extent SUBTRACT tool body), `get_bounding_box` raised
`SelectionError: Could not determine body bounds for 'CYLINDER(0)'`.

### Bounding Box Resolution Fix
The `_body_bounds()` function's edge-radius fallback (`_edge_z_and_radius`) was returning
`(0.0, 0.0)` for all circular edges because it tried `uf.Eval` arc detection *after*
face-data extraction (which failed due to wrong `AskFaceData` tuple indexing). Fix:
- Promoted `uf.Eval.Initialize → IsArc → AskArc` to run *before* the face-data fallback.
- Hardened `AskArc` attribute access (`arc.Center` vs `arc.center`, `arc.Radius` vs `arc.radius`).
- Fixed `AskFaceData` cylinder radius extraction (index 4, not index 3).
- Added exhaustive bounding box method discovery (`AskBoundingBox`, `AskBoundingBoxExact`,
  `AskBbox`, `AskBodyBoundingBox`, `AskObjectBoundingBox`) with `TypeError` fallback for
  methods requiring additional parameters.

## Files Modified

- `src/nx_mcp/bridge/nx_bridge.py` — core fixes in curve/body resolution, bounding box, edge radius
- `tests/test_sketch_spline_offset.py` — Bug 1 regression tests [NEW]
- `tests/test_pattern_fillet_resolution.py` — Bug 2 regression tests [NEW]
- `verify_bugfix_live.py` — combined live verification script [NEW]

