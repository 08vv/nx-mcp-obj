# Parametric CAD Reconstruction Playbook

This playbook defines the standardized, battle-tested recipe for reverse-engineering 3D mesh models (`.obj`) into genuine, fully editable Siemens NX CAD parts (`.prt`).

---

## 1. Geometric Feature Decision Table

When analyzing mesh zones along the primary axis, classify each zone into its native Siemens NX feature:

| Zone Geometry Type | NX Feature Type | NXOpen Builder / Tool | Expression Bindings |
| :--- | :--- | :--- | :--- |
| **Straight Cylindrical** (uniform diameter) | `CYLINDER` | `Features.CreateCylinderBuilder` | `Diameter.RightHandSide`, `Height.RightHandSide` |
| **Conical Tapered** (linear diameter change) | `CONE` | `Features.CreateConeBuilder` (`DiametersAndHeight`) | `BaseDiameter.RHS`, `TopDiameter.RHS`, `Height.RHS` |
| **Profiled / Grooved / Lands / Domes** (annular details) | `REVOLVE` | `UF.Modl.CreateRevolution` / `RevolveBuilder` | Associative scalar points (`pt_assoc`) driven by expressions |
| **Prismatic / Rounded Rectangular** | `EXTRUDE` or `BLOCK` + `BLEND` | `Features.CreateBlockFeatureBuilder` or `ExtrudeBuilder` | Dimension expressions (`LENGTH`, `WIDTH`, `HEIGHT`) |
| **Stepped Shelves / Waist Concavities** | `SUBTRACT` | `Features.CreateBooleanBuilder(Subtract)` | Position, diameter, and depth expressions |
| **Freeform Morphing / Asymmetric Void** | `THROUGH_CURVES` (zone only) | `Features.CreateThroughCurvesBuilder` | Station spacing & extent expressions (flag in report) |
| **Fillets, Rounds, Chimes** | `EDGE_BLEND` | `Features.CreateEdgeBlendBuilder` | `CreateRuleOuterEdgesOfFaces([face])` |

---

## 2. Step-by-Step Construction Recipe

### Step 1: Axial Zone Segmentation
- Determine primary elongation axis ($Z$ or $Y$).
- Slice the mesh or examine cross-section gradients $\frac{dr}{dh}$ to identify transition stations:
  - Base zone (bottom chime / pedestal)
  - Lower body / reservoir
  - Waist / transition taper
  - Shoulder / neck collar
  - Closure / nozzle / dispenser cap
- Never lump distinct zones into one continuous loft!

### Step 2: Parametric Expression Architecture
Define all dimensions in `part.Expressions` using **chained dependencies**:
```python
exp_defs = [
    # Zone 1: Base Barrel
    ("ZONE1_START_Z", "0.000"),
    ("ZONE1_HEIGHT",  "50.000"),
    ("ZONE1_BASE_DIA", "45.000"),
    ("ZONE1_TOP_DIA",  "48.000"),
    
    # Zone 2: Waist Taper (Chained to Zone 1)
    ("ZONE2_START_Z", "ZONE1_START_Z + ZONE1_HEIGHT"),
    ("ZONE2_HEIGHT",  "30.000"),
    ("ZONE2_TOP_DIA", "42.000"),
    
    # Zone 3: Neck Collar (Chained to Zone 2)
    ("ZONE3_START_Z", "ZONE2_START_Z + ZONE2_HEIGHT"),
    ("ZONE3_HEIGHT",  "25.000"),
    ("ZONE3_DIA",     "28.000"),
]
for name, val in exp_defs:
    part.Expressions.CreateExpression("Number", f"{name} = {val}")
```
**Rule**: Zero orphan expressions. If modifying an expression does not alter the CAD solid body, it is invalid.

### Step 3: Zone Feature Building (Sketch-Per-Zone Architecture)
Use `src.nx_mcp.parametric_helpers` to create zone sketch features:
- Every functional zone is built from its own named **Sketch** on a datum plane (e.g. `SKETCH_BOTTLE_BASE`, `SKETCH_COLLAR`, `SKETCH_CAP`, `SKETCH_CROWN`).
- Each sketch has:
  - Central axis line constrained collinear to the revolve/extrusion axis.
  - Driving dimensional constraints (`HorizontalDim` for radii, `VerticalDim` for heights) directly linked to named part expressions.
  - Associative start elevation constraint (`VerticalDim` from sketch origin) linked to chained zone elevation expressions (`COLLAR_Z0`, `CAP_Z0`, `CROWN_Z0`).
- Each zone is revolved (`REVOLVE_...`) or extruded (`EXTRUDE_...`) as its own named feature.
- Sequentially unite each new body into the main solid body via `boolean_unite(...)` (`UNITE_COLLAR`, `UNITE_CAP`, `UNITE_CROWN`).

### Step 4: Associative Edge Blends
Never use `CreateRuleEdgeDumb` with manual coordinate queries. Edge blend collectors must be topological:
```python
from src.nx_mcp.parametric_helpers import create_associative_blend_by_face

# Select parent feature's planar face (e.g. bottom chime)
planar_faces = [f for f in main_body.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
base_face = min(planar_faces, key=lambda f: min(v.Z for e in f.GetEdges() for v in e.GetVertices()))

# Apply blend associatively through the face boundary
blend_feat = create_associative_blend_by_face(part, base_face, "BASE_BLEND_R", name="BASE_BOTTOM_BLEND")
```

### Step 5: Verification & Quality Enforcement
Run the quality checker before finishing:
```bash
& "C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe" scripts/check_parametric_quality.py -args <part.prt>
```
The checker guarantees:
1. No single feature covers $>80\%$ of total part height.
2. At least 5 distinct named features in Part Navigator.
3. Every expression actively drives geometry when varied by $10\%$.
4. No dumb edge rules are used.
5. `session.UpdateManager.DoUpdate()` executes with 0 errors across perturbations.

---

## 3. Working Reference Scripts

Study these production-quality reference scripts in `scripts/`:

1. **[scripts/build_elle18_lipstick_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_elle18_lipstick_parametric.py)**:
   - **Gold Standard Multi-Zone Sketch-Driven Architecture** (18 distinct features).
   - Zone 1: `SKETCH_BOTTLE_BASE` -> `REVOLVE_BOTTLE_BASE`.
   - Zone 2: `SKETCH_COLLAR` -> `REVOLVE_COLLAR` -> `UNITE_COLLAR`.
   - Zone 3: `SKETCH_CAP` -> `REVOLVE_CAP` -> `UNITE_CAP`.
   - Zone 4: `SKETCH_CROWN` -> `REVOLVE_CROWN` -> `UNITE_CROWN`.
   - Associative edge blends: `BASE_BOTTOM_BLEND` (R=2.0 mm) and `CROWN_APEX_BLEND` (R=1.5 mm).
   - Dynamic update test verified with 0 errors.

2. **[scripts/build_axe_soap_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_axe_soap_parametric.py)**:
   - Prismatic base block + cylindrical subtracts + stepped shelves.

3. **[scripts/build_rin_soap_v2_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_rin_soap_v2_parametric.py)**:
   - Organic soap body + end blends.

   - Zone 4: Tip cone + apex dome blend.
   - 100% chained expressions, 0 orphans, 0 dumb edge rules.

2. **[scripts/build_axe_soap_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_axe_soap_parametric.py)**:
   - Prismatic bar with concave waist cutouts and stepped end shelves (14 distinct features).
   - Demonstrates primitive Block base, Cylindrical subtracts, Stepped Shelf cutouts, and corner blends.

3. **[scripts/build_rin_soap_v2_parametric.py](file:///c:/Users/HP/Downloads/nx-mcp-obj/scripts/build_rin_soap_v2_parametric.py)**:
   - Organic soap bar with concave recess face.
   - Demonstrates valid usage of `Through Curves` strictly bounded to an organic shape zone, with driving dimensions.
