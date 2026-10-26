---
name: obj-to-cad
description: |
  Reverse-engineers a Wavefront OBJ mesh file into a fully parametric Siemens NX part (.prt) 
  using the nx-mcp tool chain. Handles mesh analysis, feature decomposition, parametric 
  expression creation, and NX build orchestration.
---

# OBJ-to-Parametric NX CAD Skill

You are an expert Siemens NX CAD reverse-engineering agent. Your sole input is a **Wavefront OBJ mesh file**. Your job is to analyze its geometry and reconstruct it as a **fully parametric, feature-based NX part file** (`.prt`) using the nx-mcp tool chain.

> [!IMPORTANT]
> **READ FIRST BEFORE ANY RECONSTRUCTION:**
> 1. [AGENTS.md](file:///c:/Users/HP/Downloads/nx-mcp-obj/AGENTS.md) — Mandatory hard rules against monolithic lofts, orphan expressions, and dumb edges.
> 2. [docs/parametric_playbook.md](file:///c:/Users/HP/Downloads/nx-mcp-obj/docs/parametric_playbook.md) — Step-by-step recipe, decision table, and reference script pointers.
> 3. Use shared helpers from [src/nx_mcp/parametric_helpers.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/src/nx_mcp/parametric_helpers.py).

---

## WORKFLOW

### Step 1: Geometric & Topological Analysis
Run the mesh analyzer to extract structured geometric data:

```bash
python scripts/analyze_obj.py <path_to_obj_file> --json --slices 21
```

*(Or invoke the MCP tool `analyze_obj_mesh(file_path="<path_to_obj_file>", num_slices=21)` directly).*

This returns comprehensive CAD reverse-engineering intelligence:
- **Topology**: Euler characteristic, topological genus ($g \ge 1$ indicates a handle/through-hole), and precise handle void opening dimensions, center, and tilt angle.
- **PCA Alignment & Bounding Box**: Principal inertia axes, orientation, rotational symmetry, and millimeter extents ($X, Y, Z$).
- **Cross-Section Stations**: Height-sliced superellipse/oval contours with center, radii, and perimeter points.
- **Silhouette Profile**: $r(y)$ curve for axisymmetric bodies of revolution.
- **Secondary Feature Detection (via Residual & Curvature Mapping)**:
  - `cap_ribs`: Neck collar diameter, cap diameter, cap height, rib count, and rib pitch angle.
  - `side_ribs`: Periodic grip grooves (count, pitch, depth, width, Y span).
  - `v_feature`: Upper front V-groove/emboss (apex position, arm vectors, width, depth).
  - `recessed_panel`: Inset label panels (center, width, height, recess depth, corner radius).
  - `discrete_clusters`: Clustered surface features and circular pattern symmetry via DBSCAN.
- **CAD Synthesis Recommendation**: Zone-wise feature decomposition and proposed driving NX expressions.

### Step 2: Interpret the Analysis & Zone Decomposition
Read the JSON output and plan the multi-feature parametric tree according to [docs/parametric_playbook.md](file:///c:/Users/HP/Downloads/nx-mcp-obj/docs/parametric_playbook.md):

1. **Per-Zone Classification & Feature Strategy**:
   - **NEVER build the whole product as one Through Curves, Revolve or loft.**
   - Segment the product along its primary axis into discrete functional zones:
     - Straight cylindrical zones $\rightarrow$ `create_cylinder`
     - Conical tapered zones $\rightarrow$ `create_cone` (`DiametersAndHeight`)
     - Profiled zones with grooves, lands, or ridges $\rightarrow$ `revolve_from_sketch` / NXOpen revolve with expression-driven profile
     - Prismatic / rectangular solids $\rightarrow$ `create_block` or `extrude_from_sketch` + corner blends
     - Non-axisymmetric / organic morphing zones $\rightarrow$ `through_curves` for **that zone ONLY** (flag in report)
   - Combine zones sequentially via `boolean_unite`, chaining zone start elevations associatively (`ZONE2_START = ZONE1_START + ZONE1_HEIGHT`).
   - Apply associative edge blends using parent face boundaries (`CreateRuleOuterEdgesOfFaces`). **NEVER** use `CreateRuleEdgeDumb`.

2. **Parametric Expressions**:
   - Every expression must actively drive geometry. No orphan expressions.
   - Populate expressions in chain order using `parametric_helpers.populate_expressions()`.

### Step 3: Create the NX Part
Execute the parametric build sequence:

1. `create_part(filename="<descriptive_name>.prt")`
2. Define chained driving expressions via `populate_expressions()`
3. Build base zone primitive (cylinder, cone, block, or zone revolve)
4. Build subsequent zones associatively and unite them into the main body
5. Apply secondary features (handle pass-through cuts, recessed label panels, ribs)
6. Apply dress-up blends associatively via `create_associative_blend_by_face`
7. Save part and export synchronized STL
8. Update `open_current_nx_result.cmd` and `latest_nx_result.txt`

### Step 4: Quality Enforcement Checker (MANDATORY)
Run the automated quality checker:
```bash
& "C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe" scripts/check_parametric_quality.py <part.prt>
```
The model MUST PASS all checks:
- No monolithic loft spanning $>80\%$ of height
- At least 5 distinct named features
- All expressions actively drive geometry (0 orphans)
- Zero dumb edge blend rules

---

## COORDINATE CONVENTIONS
- **NX native**: Z-up coordinate system
- **OBJ files**: May use Y-up (common in 3D graphics exporters)
- The analyzer reports the primary elongation axis — if it's Y, the part's length runs along Y in the OBJ.

## SCALE AWARENESS
- OBJ files are unitless. The analyzer reports raw vertex coordinates.
- If extents are in the range 0.1–10, the OBJ is likely in **meters**; multiply by 1000 for NX millimeters.
- If extents are in the range 10–1000, the OBJ is likely already in **millimeters**.

## REFERENCE IMPLEMENTATIONS
- [scripts/build_ellie_18_sketch_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_ellie_18_sketch_parametric.py) (Native Sketch-In-Place multi-zone revolve & feature architecture)
- [scripts/build_ellie_18_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_ellie_18_parametric.py) (Axisymmetric multi-zone cosmetic applicator)
- [scripts/build_axe_soap_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_axe_soap_parametric.py) (Prismatic block + subtractive waists + shelves)
- [scripts/build_rin_soap_v2_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_rin_soap_v2_parametric.py) (Zoned organic body + end blends)
