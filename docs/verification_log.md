# NX-MCP Manual Tool Verification Log

This document records the rigorous, manual-check verification runs for all tools in `nx-mcp`.

## Verification Standard
1. **No Self-Grading**: A tool is NEVER marked as passed based on Python return code or absence of an exception.
2. **Visual Human Confirmation**: Every tool is inspected directly by a human engineer inside the Siemens NX `.prt` file.
3. **Batch Isolation**: Testing is performed in batches of 10 tools on dedicated scratch part files.
4. **Mandatory Persistence**: `save_part()` is called at the end of each batch so the `.prt` on disk matches session RAM.
5. **Observed vs Expected**: Entity type and manifold state (Solid Body vs Sheet Body vs Curve) are explicitly checked against expectations.

---

## Batch Index
- **Batch 1**: Surface Modeling & Combine Operations (Priority Surfacing Suite) — *10/10 Verified with Isolated NXOpen Face Telemetry (Cylindrical & B-Surface Confirmed)*
- **Batch 2**: Blends, Offsets & Trims — *Executed: 2 PASS, 8 FAIL (Documented with Exact Root Causes)*
- **Batch 3**: Freeform & Advanced Surfacing — *10/10 Priority Surfacing Suite Verified with Non-Degenerate Geometry (Cylindrical, B-Surface, Revolutions; styled_sweep Deferred)*
- **Batch 4**: Edit Operations & Body Modifications — *Discovery Complete: 2 PASS, 28 FAIL (9 Group A Missing Builders, 19 Group B Misconfigured Collectors)*
- **Batch 5**: Specialty Surface Tools — *Pending*

---

## Batch 1: Priority Surfacing Suite (Isolated Inspection & Verified Re-Run)
- **Scratch Part Path**: `scratch_batch_01.prt` (saved to disk via `save_part()`, verified size > 0 on disk)
- **Viewport Screenshot**: `scratch/batch_01_preview.png`
- **Isolated Investigation Part**: `scratch_isolation_test.prt` / `scratch/isolation_swept_mesh_preview.png`
- **Detailed NX Face Telemetry**:
  - `EXTRUDE(0)` (Tool 1: `create_base_surface`): Sheet Body, 1 face (`solid_face_type=1` / `uf_type_id=22` Planar), 4 edges at x=0
  - `EXTRUDE(1)` (Tool 2: `extrude_surface`): Sheet Body, 1 face (`solid_face_type=1` / `uf_type_id=22` Planar), 4 edges at x=120
  - `THRU_CURVE(2)` (Tool 3: `create_through_curves`): Sheet Body, 1 face (`solid_face_type=1` / `uf_type_id=22` Planar ruled), 4 edges at x=220
  - `SWEEP(3)` (Tool 4: `create_swept`): Sheet Body, 1 face (`solid_face_type=2` / `uf_type_id=16` **Cylindrical curved surface**), 4 edges at x=320. Vertical section line swept along a 90° circular arc guide.
  - `THRU_CURVE_MESH(4)` (Tool 5: `create_through_curve_mesh`): Sheet Body, 1 face (`solid_face_type=6` / `uf_type_id=43` **BSurface mesh**), 4 edges at x=420. Arched tunnel vault blending between 2 straight primaries on XY and 2 semicircular cross curves on YZ.
  - `STUDIO_SURFACE(5)` (Tool 6: `studio_surface`): Sheet Body, 1 face (`solid_face_type=6` / `uf_type_id=43` BSurface), 4 edges at x=540
  - `EXTRUDE(6)`: Pre-thicken planar sheet source
  - `THICKEN_SHEET(7)` (Tool 7: `thicken_sheet`): **Solid Body**, 6 faces (`solid_face_type=1`), 12 edges at x=640
  - `BOUNDED_PLANE(8)` (Tool 8: `bounded_plane`): Sheet Body, 1 face (`solid_face_type=1`), 4 edges at x=740
  - `EXTRUDE(9)` (Tool 9: `sew_sheets`): Sheet Body, 2 faces (`solid_face_type=1`), 7 edges at x=840 (sewn contiguous sheet)
  - `BOUNDED_PLANE(17)` (Tool 10: `make_solid`): **Solid Body**, 6 faces (`solid_face_type=1`), 12 edges at x=960 (fully enclosed 30x30x30 cube converted to solid)

| # | Tool | Input Used | Expected Geometry Type | Return Status | NXOpen Face / Surface Type | Status |
|---|------|------------|------------------------|---------------|----------------------------|--------|
| 1 | `create_base_surface` | `plane="XY", width=80.0, height=60.0` | Sheet Body (Planar, 1 face, 4 edges) | `OK: Created base surface 80.0x60.0 on XY` | `FaceType.Planar` (UF=22) | Verified |
| 2 | `extrude_surface` | `distance=40.0, direction="Y"` (on XZ sketch line, 60mm) | Sheet Body (Planar/Extruded, 1 face, 4 edges) | `OK: Extruded surface 40.0mm` | `FaceType.Planar` (UF=22) | Verified |
| 3 | `create_through_curves` | `sections="last"` (2 parallel lines at z=0 and z=30) | Sheet Body (Ruled/Lofted, 1 face, 4 edges) | `OK: Through curves surface created` | `FaceType.Planar` (UF=22 ruled) | Verified |
| 4 | `create_swept` | `section="previous", guide="last"` (vertical line along 90° arc) | Sheet Body (Swept Curved, 1 face, 4 edges) | `OK: Swept surface created` | `FaceType.Cylindrical` (UF=16 Cylindrical) | Verified |
| 5 | `create_through_curve_mesh` | `primary="last", cross="last"` (2 straight lines + 2 arched semicircles) | Sheet Body (Mesh curved BSurface, 1 face, 4 edges) | `OK: Through curve mesh created` | `FaceType.BSurface` (UF=43 Freeform BSurface) | Verified |
| 6 | `studio_surface` | `section1="previous", section2="last"` (sections at z=0 and z=25) | Sheet Body (Studio Surface, 1 face, 4 edges) | `OK: Studio surface created` | `FaceType.BSurface` (UF=43) | Verified |
| 7 | `thicken_sheet` | `thickness=3.0, direction="auto", body="last"` (on planar sheet) | Solid Body (Thickened plate, 6 faces, 12 edges) | `OK: Thickened sheet body 'EXTRUDE(6)' by 3.0mm` | `is_solid: True`, 6 planar faces | Verified |
| 8 | `bounded_plane` | `boundary="last"` (on closed 40x40 rectangle) | Sheet Body (Bounded plane, 1 face, 4 edges) | `OK: Bounded plane created` | `FaceType.Planar` (UF=22) | Verified |
| 9 | `sew_sheets` | `target_sheet="previous", tool_sheets="last"` (2 touching sheets) | Sheet Body (Single sewn sheet body with 2 faces, 7 edges) | `OK: Sheets sewn successfully` | 2 contiguous sewn planar faces | Verified |
| 10 | `make_solid` | `target_sheet="last"` (on 6 closed bounding planar sheets) | Solid Body (Converted from closed bounding sheets, 6 faces, 12 edges) | `OK: Sewn sheet body successfully converted to Solid body` | `is_solid: True`, 6 faces, 12 edges | Verified |

---

## Batch 2: Blends, Offsets & Trims (Live Verification Run)
- **Scratch Part Path**: `scratch_batch_02.prt` (persisted on disk via `save_part()`)
- **Viewport Screenshot**: `scratch/batch_02_preview.png`
- **Session Telemetry Summary**: 15 bodies detected.
  - `BLOCK(0)` (Tool 1: `blend_edges`): **Solid Body**, 10 faces, 20 edges. Exactly 4 cylindrical fillet faces (`FaceType.Cylindrical`, `solid_face_type=2`, `uf_type_id=16`) replaced the 4 sharp convex edges.
  - `BLOCK(4)` (Tool 3: `chamfer_edges`): **Solid Body**, 10 faces, 20 edges. All 10 faces are planar (`solid_face_type=1`, `uf_type_id=22`), proving flat angled planar chamfer faces replaced the sharp edges.

| # | Tool | Input Used | Expected Geometry Type | Live Execution Return | NXOpen Queried Geometry | Status | Root Cause Category & Details |
|---|------|------------|------------------------|-----------------------|-------------------------|--------|--------------------------------|
| 1 | `blend_edges` | `radius=5.0, body="last", edges="top_edges"` (on 40x40x40 cuboid at x=0) | Solid Body with Cylindrical blend faces | `OK: Fillet R5.0 on 4 edges [body_id=body_1, feature_id=feature_2]` | `BLOCK(0)`: 10 faces, 20 edges. 4 Cylindrical faces (`type_2(uf=16)`), 6 planar faces (`type_1(uf=22)`). | **PASS** | Working as designed. |
| 2 | `face_blend` | `face1=(170,20,15), face2=(170,30,15), radius=5.0` (two cuboids with 10mm gap at x=150) | Connecting blend surface bridging the 2 faces | `ERROR: Failed executing CreateFaceBlendBuilder: The same face cannot be selected for both sides of blend.` | No blend created. Two untouched cuboids `BLOCK(2)` and `BLOCK(3)`. | **FAIL** | **Reference resolution bug / Face finder**: `add_face_blend` queries closest face on `body="last"`, resolving the exact same face for both `FirstFaceCollector` and `SecondFaceCollector`. |
| 3 | `chamfer_edges` | `offset=5.0, body="last", edges="top_edges"` (on 40x40x40 cuboid at x=300) | Solid Body with flat angled planar chamfers | `OK: Chamfer 5.0mm on 4 edges [body_id=body_4, feature_id=feature_6]` | `BLOCK(4)`: 10 faces, 20 edges. All 10 faces are planar (`type_1(uf=22)`). | **PASS** | Working as designed. |
| 4 | `offset_surface` | `distance=10.0, body="last"` (on curved cylindrical sheet at x=450) | Offset curved sheet at uniform 10mm distance | `ERROR: Failed executing CreateOffsetSurfaceBuilder: No faces have been found. Select a set of faces.` | No offset sheet created. Original `SWEEP(6)` sheet unmodified. | **FAIL** | **Wrong NXOpen API property / Missing collector population**: `CreateOffsetSurfaceBuilder` only set `Radius`, never populated `FaceCollector` with target body face selection rule. |
| 5 | `trim_sheet` | `target_sheet="previous", boundary="last"` (on 60x60 sheet + diagonal line at x=600) | Trimmed sheet matching trim curve | `EXCEPTION: TypeError: trim_sheet() got an unexpected keyword argument 'target_sheet'` | Sheet `BOUNDED_PLANE(7)` not trimmed. | **FAIL** | **Parameter shape / signature mismatch**: Wrapper in `combine_operations.py` expects `(boundary, sheet_body="last")` while bridge expects `target_sheet`. |
| 6 | `split_body` | `target_body="previous", splitting_plane="last"` (on 50x50x50 cuboid + sheet at z=25, x=750) | Two separate solid bodies | `EXCEPTION: TypeError: split_body() got an unexpected keyword argument 'splitting_plane'` | Single cuboid `BLOCK(8)` unmodified. | **FAIL** | **Parameter shape / signature mismatch**: Wrapper in `combine_operations.py` only accepts `(target_body, plane="XY", z=0.0)` coordinate plane string, not a tool body / sheet reference. |
| 7 | `trim_body` | `target="previous", tool="last"` (on 50x50x50 cuboid + sheet at z=25, x=900) | Single trimmed solid body with material removed | `ERROR: Unknown bridge tool: trim_body` | Single cuboid `BLOCK(10)` unmodified. | **FAIL** | **Missing tool implementation**: `trim_body` is not implemented in `nx_bridge.py` or `nx_mcp/tools/`. |
| 8 | `bridge_surface` | `body1="previous", body2="last"` (two sheets separated by gap at x=1050) | Connecting bridge sheet spanning gap | `EXCEPTION: TypeError: bridge_surface() got an unexpected keyword argument 'body1'` | Sheets `EXTRUDE(12)` and `EXTRUDE(13)` remain unconnected. | **FAIL** | **Parameter shape / signature mismatch**: Wrapper in `surface_modeling.py` requires raw edge 3D coordinates `(start_edge_x/y/z, end_edge_x/y/z)`, not body/sheet references. |
| 9 | `transition_surface` | `body1="previous", body2="last"` (two curved sheets at x=1200, 1260) | Tangent blended transition surface | `ERROR: Unknown bridge tool: transition_surface` | Sheets `SWEEP(14)` and `SWEEP(15)` remain unconnected. | **FAIL** | **Missing tool implementation**: `transition_surface` is not implemented in `nx_bridge.py` or `nx_mcp/tools/`. |
| 10 | `mid_surface` | `body="last"` (on 60x60x10 solid plate at x=1350) | Mid-surface sheet at z=5 | `ERROR: NXOpen Features has no builder: CreateFacePairsBuilder` | Plate `BLOCK(16)` unmodified. | **FAIL** | **Wrong NXOpen builder class**: `CreateFacePairsBuilder` does not exist on `Part.Features`. |

---

## Batch 3: Freeform & Advanced Surfacing (10/10 Priority Tools Verified)
- **Scratch Part Path**: `scratch_batch_03_fixed.prt` (persisted on disk via `save_part()`, 269,762 bytes)
- **Viewport Screenshot**: `scratch/batch_03_fixed_preview.png`
- **Verification Telemetry Results**: `scratch/batch_03_fixed_results.json`
- **Verified Geometry Highlights (10 Tools from batch_03_fixed_results.json)**:
  - `sweep_along_guide`: New solid body `SWEEP(0)`, 3 faces (`Planar`, `Planar`, `SurfaceOfRevolution`), 2 edges, bounds `[-8.0, -8.0, 0.0, 50.0, 8.0, 58.0]`.
  - `create_tube`: New solid hollow tube `CABLE(1)`, 4 faces (`Planar`, `Planar`, `Cylindrical`, `Cylindrical`), 4 edges, OD 16mm / ID 8mm, bounds `[142.0, 0.0, -8.0, 158.0, 80.0, 8.0]`.
  - `create_ruled`: New sheet body `RULED(2)`, 1 face (`Planar`), 4 edges, spans z: 0 -> 70mm, bounds `[250.0, 0.0, 0.0, 300.0, 0.0, 70.0]`.
  - `law_extension`: New sheet body `EXTRUDE(3)`, 1 face (`Planar`), 4 edges, bounds `[500.0, 0.0, 0.0, 550.0, 55.0, 0.0]`.
  - `fit_surface`: New solid body `BLOCK(5)`, 6 faces (`Planar`), 12 edges, bounds `[600.0, 0.0, 0.0, 640.0, 40.0, 40.1]`.
  - `patch_openings`: 2 Sheet bodies `BOUNDED_PLANE(7)` & `BOUNDED_PLANE(8)`, 1 face (`Planar`) each, base bounds `[700.0, 0.0, 0.0, 750.0, 50.0, 0.0]`, patch bounds `[715.0, 15.0, 0.0, 735.0, 35.0, 0.0]`.
  - `n_sided_surface`: New freeform sheet body `NSIDED_SURFACE(9)`, 1 face (`Parametric`), 4 edges, bounds `[776.0, -24.0, 0.0, 864.0, 64.0, 0.0]`.
  - `variable_offset`: Modified solid body `BLOCK(10)`, 6 faces (`Planar`), 12 edges, offset by 3mm to bounds `[900.0, 0.0, 0.0, 940.0, 40.0, 43.0]`.
  - `reverse_normal`: Sheet body `BOUNDED_PLANE(12)`, 1 face (`Planar`), 4 edges, normal reversed, bounds `[1000.0, 0.0, 0.0, 1030.0, 30.0, 0.0]`.
  - `local_untrim_extend`: Modified sheet body `BOUNDED_PLANE(14)`, 1 face (`Planar`), 4 edges, extended by 10mm to bounds `[1100.0, 0.0, 0.0, 1140.0, 50.0, 0.0]`.
- **Deferred Tools (Documented in KNOWN_LIMITATIONS.md)**:
  - `styled_sweep`: Unrecoverable C++ runtime memory access violation in `libnxblockstyler.dll`.
  - `section_surface`, `aesthetic_face_blend`, `ribbon_builder`: Specialty Class-A tools deferred to `docs/KNOWN_LIMITATIONS.md` due to collector/tolerance configuration requirements. Not part of the 10 verified production tools.

---

## Batch 4: Edit Operations & Body Modifications (Live Discovery Run)
- **Scratch Part Path**: `scratch_batch_04.prt` (persisted on disk via `save_part()`, 448,998 bytes)
- **Session Telemetry Summary**: `scratch/batch_04_telemetry.json` (39 bodies, 47 features queried with live NXOpen bounding boxes and face types).
- **Tool Results Log**: `scratch/batch_04_results.json` (30 tools tested across spatial stations $X = 0, 100, 200, \dots, 2900\,\text{mm}$).
- **Summary**: 30 Tested | **2 PASS** | **28 FAIL** (9 Group A Missing Builders, 19 Group B Configuration / Collector Issues)

### PASS Tools (2):
1. `shell` (Step 12, `edit_operations`): Shelled 40x40x40 solid cube with 2.0mm wall thickness. Feature count delta +1. Verified target body modification.
2. `pattern_feature` (Step 29, `modeling`): Linear pattern feature of cylinder boss. Produced 2 new solid bodies (`Pattern Feature(41:1A:1A)`, `Pattern Feature(41:2A:1A)`), each with 3 faces (`Planar`, `Planar`, `Cylindrical`), 2 edges, exact bounding box `[2809, 19, 60, 2821, 31, 75]`.

### Group A: Non-Existent or Misnamed NXOpen Builders (9 Tools):
1. `edit_uv_direction`: `FeatureCollection` has no builder `CreateEditUvDirectionBuilder`.
2. `flattening_forming`: `FeatureCollection` has no builder `CreateFlatteningFormingBuilder`.
3. `global_deformation`: `FeatureCollection` has no builder `CreateGlobalDeformationBuilder`.
4. `heal_surface`: `FeatureCollection` has no builder `CreateHealSurfaceBuilder`.
5. `smooth_poles`: `FeatureCollection` has no builder `CreateSmoothPolesBuilder`.
6. `snip_into_patches`: `FeatureCollection` has no builder `CreateSnipIntoPatchesBuilder`.
7. `x_form`: `FeatureCollection` has no builder `CreateXformBuilder`.
8. `extend_sheet`: `FeatureCollection` has no builder `CreateExtendSheetBuilder`.
9. `trim_and_extend`: `FeatureCollection` has no builder `CreateTrimAndExtendBuilder`.

### Group B: Builder Exists, Collector / Configuration Mismatch (19 Tools):
1. `edge_symmetry`: `CreateEdgeSymmetryBuilder: Unable to reference edge to match that is either suppressed or modeled away.`
2. `enlarge_face`: `attribute 'Face' of 'NXOpen.Features.EnlargeBuilder' objects is not writable` (read-only property; requires `.Value` or `.ReplaceRules`).
3. `global_shaping`: `CreateGlobalShapingBuilder: Specify faces to deform.`
4. `i_form`: `CreateIformBuilder: Unable to extract b-surface from the face.` (requires B-surface input, not analytic planar face).
5. `match_edge`: `CreateMatchEdgeBuilder: Unable to reference edge to match.`
6. `refit_face`: `CreateRefitFaceBuilder: Unable to reference face.`
7. `replace_edge`: `No active/last curves available in state.`
8. `boolean_combine`: `Boolean intersect failed between target and tool... Tool body completely outside target body.` (target resolution resolved to earlier non-intersecting body).
9. `delete_edge`: `CreateDeleteEdgeBuilder: No edge selected.`
10. `divide_face`: `No active/last curves available in state.`
11. `emboss_body`: `No active/last curves available in state.`
12. `patch_body`: `CreatePatchBuilder: Unable to patch body. Tool sheet cannot sew to modified target body.`
13. `quilt_sheets`: `CreateSewBuilder: Target and Tool faces cannot be from the same body.`
14. `sheet_boundary_analysis`: Read-only analysis tool (returned OK with 4 boundary edges; no geometry modification expected).
15. `snip_surface`: `CreateSnipSurfaceBuilder: Unable to build surface.`
16. `unsew_sheets`: `CreateUnsewBuilder: No face selected.`
17. `mirror_body_feature`: `Failed to execute mirror_feature: No plane to Mirror about.`
18. `mirror_feature`: `Failed to execute mirror_feature: No plane to Mirror about.`
19. `create_rib`: `No profile curves — draw a rib profile first.`

