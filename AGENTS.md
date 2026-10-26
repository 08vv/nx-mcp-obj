# AGENTS.md — Critical Rules for OBJ-to-CAD Reconstruction

## HARD RULES FOR ALL AGENTS
1. **NEVER BUILD THE WHOLE PRODUCT AS ONE THROUGH CURVES, REVOLVE, OR LOFT.**
   - Slicing an entire mesh into 30–50 cross-sections and lofting a single body produces uneditable CAD geometry and breaks feature selection.
   - Any model whose primary body is a single loft spanning the part is a **FAILURE**.

2. **SPLIT THE PRODUCT PER ZONE ALONG ITS AXIS & USE NATIVE SKETCH-IN-PLACE FEATURES.**
   - Segment the product along its primary axis into distinct functional zones.
   - For profiled, stepped, or prismatic zones, use **native `SketchInPlace` features on datum planes** (`CreateSketchInPlaceBuilder2` / `create_sketch_in_place`) followed by `Revolve` / `Extrude` so explicit sketch features appear in the NX Part Navigator tree.
   - Each zone MUST be its own named Siemens NX feature or sketch operation:
     - Profiled zone (grooves, steps, accent ridges, necks, barrels) $\rightarrow$ Native `Sketch` + `Revolve`
     - Prismatic / rectangular / shaped zone $\rightarrow$ Native `Sketch` + `Extrude` + corner blends
     - Straight uniform cylindrical zone $\rightarrow$ `Cylinder` or `Sketch` + `Revolve`
     - Conical tapered zone $\rightarrow$ `Cone` or `Sketch` + `Revolve`
     - Truly non-axisymmetric / organic morphing zone $\rightarrow$ `Through Curves` for **that zone ONLY**.
   - Unite zones sequentially via `Boolean` (`Unite`), then apply associative edge blends.

3. **EVERY EXPRESSION MUST DRIVE GEOMETRY. ZERO ORPHAN EXPRESSIONS.**
   - Every user expression created in `part.Expressions` must actively drive a feature dimension, limit, or sketch parameter.
   - If an expression can be altered by 10% without altering the solid body geometry, it is an orphan and the model **FAILS**.

4. **ZONE START POSITIONS MUST BE CHAINED EXPRESSIONS.**
   - Zone elevations must never be hardcoded constants:
     - `ZONE1_START = 0.0`
     - `ZONE1_HEIGHT = ...`
     - `ZONE2_START = ZONE1_START + ZONE1_HEIGHT`
     - `ZONE3_START = ZONE2_START + ZONE2_HEIGHT`
   - Modifying a zone height must automatically shift subsequent zones.

5. **BLENDS MUST BE ASSOCIATIVE — NEVER DUMB EDGE RULES.**
   - Blends must select edges using parent feature faces via `CreateRuleOuterEdgesOfFaces` or `CreateRuleEdgeFeature`.
   - **NEVER** use `CreateRuleEdgeDumb` with coordinate thresholds or raw vertex scraping.

6. **THROUGH CURVES CONSTRAINTS:**
   - Allowed **ONLY** for genuinely non-axisymmetric organic zones (e.g. ergonomic handle grips, organic transition lofts).
   - Never for the whole part.
   - Must be explicitly documented and flagged in the final report.

7. **BEFORE BUILDING:**
   - Read [docs/parametric_playbook.md](file:///c:/Users/HP/Downloads/nx-mcp-obj/docs/parametric_playbook.md).
   - Review working reference implementations:
     - [scripts/build_ellie_18_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_ellie_18_parametric.py) (multi-zone axisymmetric cosmetic applicator)
     - [scripts/build_axe_soap_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_axe_soap_parametric.py) (prismatic base + cylindrical subtracts + stepped shelves)
     - [scripts/build_rin_soap_v2_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_rin_soap_v2_parametric.py) (organic soap body + end blends)
   - Import shared builders and helpers from `src.nx_mcp.parametric_helpers`.

8. **MANDATORY VERIFICATION CHECKER:**
   - Before reporting any CAD model as complete, you MUST execute:
     ```bash
     & "C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe" scripts/check_parametric_quality.py <output_part.prt>
     ```
   - Paste the checker's PASS/FAIL output in your final report. A failing model is NOT acceptable.
