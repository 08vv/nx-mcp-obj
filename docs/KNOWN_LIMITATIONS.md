# Known Limitations: Deferred Specialty & Class-A Surfacing Tools

## Overview

Following the comprehensive Batch 3 live discovery audit on Siemens NX 2206, the tools below were confirmed non-operational in the current bridge implementation. Per architectural assessment, these tools represent **specialty Class-A styling and esoteric freeform operations** with low real-world utility for industrial parts (ducts, housings, bottles, manifolds, brackets, pipes).

To prevent over-engineering rarely-used surfacing routines, these 17 tools are **deferred** from immediate implementation and documented here for future reference. If a future workflow explicitly demands one of these operations, refer to the technical diagnosis and recommended resolution path below.

---

## Summary of Deferred Tools (18 Tools)

| Tool Name | Module | Discovery Status | Technical Root Cause | Recommended Future Path |
|---|---|---|---|---|
| `styled_sweep` | `surface_modeling` | Confirmed Broken | NX C++ runtime crash (`Internal error: memory access violation`) in `libnxblockstyler.dll`/`libfeatures.dll` on `CommitFeature()` | Use `sweep_along_guide` or `create_through_curves` which generate identical swept topology without memory faults |
| `variational_sweep` | `surface_modeling` | Confirmed Broken | `CreateVariationalSweepBuilder` not on `FeatureCollection` | Use `VariationalSweepBuilder` via feature template or multi-section `CreateThroughCurvesBuilder` |
| `swept_volume` | `surface_modeling` | Confirmed Broken | `CreateSweptVolumeBuilder` not on `FeatureCollection` | Model via discrete solid tool Boolean subtractions along path or `CreateSweptBuilder` |
| `fill_surface` | `surface_modeling` | Confirmed Broken | `CreateFillHoleBuilder` not on `FeatureCollection` | Use `CreateStudioSurfaceBuilder` with tangency constraints or `CreateNSidedSurfaceBuilder` |
| `blend_corner` | `surface_modeling` | Confirmed Broken | `CreateBlendCornerBuilder` not on `FeatureCollection` | Configure setback and corner blend parameters inside `CreateEdgeBlendBuilder` |
| `four_point_surface` | `surface_modeling` | Confirmed Broken | `CreateFourPointSurfaceBuilder` not on `FeatureCollection` | Construct B-surface via `UF_MODL.create_b_surf` with a 2x2 bilinear knot vector |
| `rapid_surfacing` | `surface_modeling` | Confirmed Broken | `CreateRapidSurfacingBuilder` not on `FeatureCollection` (NX method is `CreateRapidSurfaceBuilder`) | Update builder name to `CreateRapidSurfaceBuilder` and configure mesh boundary collector |
| `variable_offset_face` | `surface_modeling` | Confirmed Broken | `CreateVariableOffsetFaceBuilder` not on `FeatureCollection` (NX method is `CreateVarOffsetFaceBuilder`) | Route to `CreateVarOffsetFaceBuilder` or `CreateOffsetFaceBuilder` with variable distance laws |
| `extension_surface` | `surface_modeling` | Confirmed Broken | `CreateExtensionSurfaceBuilder` not on `FeatureCollection` | Route to `CreateLawExtensionBuilder` or `CreateTrimExtendBuilder` |
| `user_defined_surface` | `surface_modeling` | Confirmed Broken | `CreateUserDefinedSurfaceBuilder` not on `FeatureCollection` | Use User Defined Feature (UDF) instantiation or `CreateStudioSurfaceBuilder` |
| `bisector_surface` | `surface_modeling` | Confirmed Broken | `CreateBisectorSurfaceBuilder` not on `FeatureCollection` | Construct mid-datum plane between faces and intersect with bounding boundary |
| `surface_from_poles` | `surface_modeling` | Confirmed Broken | `CreateSurfaceFromPolesBuilder` not on `FeatureCollection` | Connect to `UF_MODL.create_spline_surface` passing pole/weight matrices |
| `surface_through_points` | `surface_modeling` | Confirmed Broken | `CreateSurfaceThroughPointsBuilder` not on `FeatureCollection` | Connect to `CreateThroughPointsBuilder` or `UF_MODL.create_fitted_surface` |
| `styled_corner` | `surface_modeling` | Confirmed Broken | Requires blend face collectors, not vertex coordinates | Route to `CreateStyledCornerBuilder` with adjacent blend face collectors |
| `silhouette_flange` | `surface_modeling` | Confirmed Broken | `No base curve has been selected` | Pre-extract silhouette curve using `UF_CURVE.create_silhouette` before flange builder |
| `aesthetic_face_blend` | `surface_modeling` | Confirmed Broken | Chain 1 face collector configuration mismatch | Configure G2/G3 continuity curve collectors and face collectors via `ScRuleFactory` |
| `section_surface` | `surface_modeling` | Confirmed Broken | Tolerance specification requires 3 numbers | Configure distance, angle, and curvature tolerances via `CreateSectionSurfaceBuilderEx` |
| `ribbon_builder` | `surface_modeling` | Confirmed Broken | Boundary profile continuity error | Ensure input edge chain is continuous and tangent before attaching to ribbon builder |

---

## Batch 4: Deferred Edit Operations & Body Modifications (19 Tools)

Following the Batch 4 discovery audit on Siemens NX 2206, the 19 tools below were confirmed non-operational in their current form and deferred from immediate Phase 2 implementation. The 9 high-value production tools (`boolean_combine`, `mirror_feature`, `mirror_body_feature`, `create_rib`, `divide_face`, `emboss_body`, `enlarge_face`, `unsew_sheets`, and `replace_edge`) are prioritized for fixes, while `shell` and `pattern_feature` were already verified passing.

### Group A: Non-Existent or Misnamed NXOpen Builders in NX 2206 (9 Tools)

| Tool Name | Module | Discovery Status | Technical Root Cause | Recommended Future Path |
|---|---|---|---|---|
| `edit_uv_direction` | `edit_operations` | Confirmed Missing | `CreateEditUvDirectionBuilder` not on `FeatureCollection` | Use `UF_MODL.reverse_face_uv` to manipulate surface parameterization directly |
| `flattening_forming` | `edit_operations` | Confirmed Missing | `CreateFlatteningFormingBuilder` not on `FeatureCollection` | Route to NX Sheet Metal flat pattern builders or unform features |
| `global_deformation` | `edit_operations` | Confirmed Missing | `CreateGlobalDeformationBuilder` not on `FeatureCollection` | Route to Global Shaping / Studio Surface warp routines |
| `heal_surface` | `edit_operations` | Confirmed Missing | `CreateHealSurfaceBuilder` not on `FeatureCollection` | Use `CreateSewBuilder` with loose tolerance or `UF_MODL.heal_geometry` |
| `smooth_poles` | `edit_operations` | Confirmed Missing | `CreateSmoothPolesBuilder` not on `FeatureCollection` | Manipulate control point weights directly via `UF_MODL.smooth_b_surf` |
| `snip_into_patches` | `edit_operations` | Confirmed Missing | `CreateSnipIntoPatchesBuilder` not on `FeatureCollection` | Subdivide face via `CreateDivideFaceBuilder` along UV parameter curves |
| `x_form` | `edit_operations` | Confirmed Missing | `CreateXformBuilder` not on `FeatureCollection` | Use direct pole editing via `UF_MODL.move_poles` or Studio Surface constraints |
| `extend_sheet` | `surface_modeling` | Confirmed Missing | `CreateExtendSheetBuilder` not on `FeatureCollection` | Route to `CreateTrimExtendBuilder` using edge extension rules |
| `trim_and_extend` | `surface_modeling` | Confirmed Missing | `CreateTrimAndExtendBuilder` not on `FeatureCollection` | Route to `CreateTrimExtendBuilder` with mutual intersection options |

### Group B: Deferred Specialty Surfacing & Modification Tools (10 Tools)

| Tool Name | Module | Discovery Status | Technical Root Cause | Recommended Future Path |
|---|---|---|---|---|
| `edge_symmetry` | `edit_operations` | Confirmed Broken | `Unable to reference edge to match that is either suppressed or modeled away` | Requires symmetric face/edge pairs and center plane constraints |
| `global_shaping` | `edit_operations` | Confirmed Broken | `Specify faces to deform` | Requires target face collector and complex transformation law curve definitions |
| `i_form` | `edit_operations` | Confirmed Broken | `Unable to extract b-surface from the face` | Requires pre-existing non-analytic B-surface control mesh input |
| `match_edge` | `edit_operations` | Confirmed Broken | `Unable to reference edge to match` | Requires edge-to-edge continuity constraint collectors |
| `refit_face` | `edit_operations` | Confirmed Broken | `Unable to reference face` | Requires UV degree and patch count parametrization |
| `delete_edge` | `edit_operations` | Confirmed Broken | `No edge selected` | Configure edge selection collector on redundant internal sheet edges |
| `patch_body` | `combine_operations` | Confirmed Broken | `Unable to patch body. Tool sheet cannot sew to modified target body` | Requires exact topological coincidence between sheet tool and target solid opening |
| `quilt_sheets` | `surface_modeling` | Confirmed Broken | `Target and Tool faces cannot be from the same body` | Separate target and tool bodies before passing to `CreateSewBuilder` |
| `sheet_boundary_analysis` | `utility` | Read-Only | Operates correctly as analysis inspection tool, but does not mutate or create geometry | Retain as read-only diagnostic utility; not an edit feature |
| `snip_surface` | `surface_modeling` | Confirmed Broken | `Unable to build surface` | Provide valid isoparametric parameter coordinates (U, V $\in [0, 1]$) |

---

## Architectural Notes for Future Maintainers

1. **Class-A vs. Analytic Surfaces**:
   Most industrial design tasks in NX-MCP are served reliably by analytic primitives (`extrude`, `revolve`, `cylinder`, `block`), curve-based sheets (`bounded_plane`, `sheet_from_curve`, `create_through_curves`, `create_through_curve_mesh`), and standard fillets/blends (`edge_blend`, `add_face_blend`, `chamfer_edges`).
2. **Reactivation Trigger**:
   Do not invest engineering cycles into the tools listed above unless a specific CAD spec or part generation workflow specifically requests one of these operations and cannot achieve the geometry through `create_through_curves`, `studio_surface`, or `sweep_along_guide`.

