# NX MCP — Deterministic Model Prompt Format

> **Goal**: One prompt → one exact model, every time. No randomness, no interpretation.

---

## Prompt Structure

Every model prompt must follow this exact 7-section format:

```
## 1. PART IDENTITY
## 2. EXPRESSION TABLE
## 3. BASE BODY
## 4. FEATURE SEQUENCE
## 5. HOLE TABLE
## 6. FINISH OPERATIONS
## 7. EXPORT
```

---

## Section-by-Section Specification

### 1. PART IDENTITY

```
Part name: <filename without .prt>
Units: mm
Plane: XY | XZ | YZ
Origin: (X, Y, Z)
```

> Always specify the sketch plane explicitly. Never say "default" or "auto".

---

### 2. EXPRESSION TABLE

List **every** dimension as a named expression. This is what makes the model parametric and editable.

```
| Expression Name   | Value  | Description                    |
|-------------------|--------|--------------------------------|
| BASE_LENGTH       | 120.0  | Overall length of base plate   |
| BASE_WIDTH        | 60.0   | Overall width of base plate    |
| BASE_HEIGHT       | 10.0   | Thickness of base plate        |
| WALL_HEIGHT       | 45.0   | Height of vertical wall        |
| WALL_THICK        | 8.0    | Thickness of vertical wall     |
| HOLE_DIA          | 8.5    | Mounting hole diameter         |
| HOLE_DEPTH        | 10.0   | Mounting hole depth            |
| FILLET_R          | 3.0    | Edge fillet radius             |
| CHAMFER_OFFSET    | 1.0    | Edge chamfer offset            |
```

> **Rules**:
> - Use UPPER_SNAKE_CASE
> - Every number in the model must come from this table
> - No magic numbers in the feature sequence

---

### 3. BASE BODY

Specify the **first solid body** with exact geometry and position.

```
Create: cuboid | cylinder | extruded_profile
Dimensions: LENGTH × WIDTH × HEIGHT  (reference expression names)
Position: corner at (X, Y, Z) | center at (X, Y, Z)
```

**For extruded profiles**, specify the sketch explicitly:

```
Sketch plane: XY at Z=0
Profile:
  - Rectangle: corner (0, 0), size BASE_LENGTH × BASE_WIDTH
  OR
  - Lines: (x1,y1)→(x2,y2), (x2,y2)→(x3,y3), ...
  OR
  - Circle: center (cx, cy), radius R
Extrude: distance = BASE_HEIGHT, direction = +Z
```

---

### 4. FEATURE SEQUENCE

List each operation **in exact build order**. Each step must specify:

```
Step N: <operation_type>
  Target: <body_name or "last">
  Sketch plane: <plane> at <offset>  (if sketch-based)
  Profile: <exact geometry>
  Parameters: <expression names>
  Direction: +X | -X | +Y | -Y | +Z | -Z
  Boolean: unite | subtract | none
```

**Supported operation types**:

| Operation | Required Fields |
|-----------|----------------|
| `extrude` | sketch plane, profile, distance, direction |
| `extrude_cut` | sketch plane, profile, distance, direction, target |
| `revolve` | sketch plane, profile, axis, angle |
| `revolve_cut` | sketch plane, profile, axis, angle, target |
| `boolean_unite` | target body, tool body |
| `boolean_subtract` | target body, tool body |
| `create_cylinder` | radius, height, position, direction |
| `add_hole` | x, y, z, diameter, depth, direction |
| `mirror_feature` | feature, plane (XY/XZ/YZ) |
| `pattern_feature` | feature, direction, count, pitch |
| `pattern_circular` | feature, axis, count, angle_total |

> **Critical**: Always specify direction as `+X`, `-Z`, etc. Never use `"auto"`.

---

### 5. HOLE TABLE

List every hole with exact coordinates. No phrases like "evenly spaced" or "centered".

```
| Hole # | X      | Y      | Z      | Diameter       | Depth       | Direction |
|--------|--------|--------|--------|----------------|-------------|-----------|
| H1     | 15.0   | 15.0   | 10.0   | HOLE_DIA       | HOLE_DEPTH  | -Z        |
| H2     | 105.0  | 15.0   | 10.0   | HOLE_DIA       | HOLE_DEPTH  | -Z        |
| H3     | 15.0   | 45.0   | 10.0   | HOLE_DIA       | HOLE_DEPTH  | -Z        |
| H4     | 105.0  | 45.0   | 10.0   | HOLE_DIA       | HOLE_DEPTH  | -Z        |
```

> If holes are patterned, use `pattern_feature` or `pattern_circular` instead and specify **one hole + pattern parameters**.

---

### 6. FINISH OPERATIONS

Apply fillets, chamfers, and cosmetic operations **last**, in this exact order:

```
6a. Fillets:
  - Edges: <edge_selector>  (outer_edges | top_edges | bottom_edges | vertical_edges)
  - Radius: FILLET_R

6b. Chamfers:
  - Edges: <edge_selector>
  - Offset: CHAMFER_OFFSET

6c. View: ISO
```

**Valid edge selectors**: `outer_edges`, `top_edges`, `bottom_edges`, `vertical_edges`, `x_aligned_edges`, `y_aligned_edges`, `z_aligned_edges`, `min_z_edges`, `max_z_edges`

---

### 7. EXPORT

```
Save as: <filename>.prt
Export STEP: <filename>.stp  (optional)
Export STL: <filename>.stl   (optional)
```

---

## Anti-Patterns — What NOT to Write

| ❌ Bad (ambiguous) | ✅ Good (deterministic) |
|---|---|
| "Add some mounting holes" | "4 holes at (15,15), (105,15), (15,45), (105,45), Ø8.5mm, depth 10mm, -Z" |
| "Make it about 100mm long" | "BASE_LENGTH = 100.0" |
| "Fillet the edges" | "Fillet outer_edges, radius FILLET_R = 3.0" |
| "Extrude upward" | "Extrude distance 45mm, direction +Z" |
| "Center the hole" | "Hole at (60.0, 30.0, 10.0)" |
| "Add a wall on one side" | "Step 2: Cuboid WALL_THICK × BASE_WIDTH × WALL_HEIGHT at (0, 0, BASE_HEIGHT), unite with base" |
| "Round the corners" | "Fillet vertical_edges, radius 5.0" |
| "Drill through" | "Hole depth = BASE_HEIGHT, direction -Z" |

---

## Complete Example 1: Flanged L-Bracket

```
## 1. PART IDENTITY
Part name: flanged_l_bracket
Units: mm
Plane: XY
Origin: (0, 0, 0)

## 2. EXPRESSION TABLE
| Expression Name   | Value  | Description                     |
|-------------------|--------|---------------------------------|
| BASE_L            | 80.0   | Base plate length (X)           |
| BASE_W            | 50.0   | Base plate width (Y)            |
| BASE_T            | 6.0    | Base plate thickness (Z)        |
| WALL_H            | 60.0   | Vertical wall height (Z)        |
| WALL_T            | 6.0    | Vertical wall thickness (X)     |
| RIB_T             | 4.0    | Gusset rib thickness (Y)        |
| RIB_SIZE          | 30.0   | Gusset rib leg length           |
| MOUNT_HOLE_DIA    | 6.5    | Base mounting hole diameter      |
| MOUNT_HOLE_DEPTH  | 6.0    | Base mounting hole depth         |
| WALL_SLOT_W       | 12.0   | Wall slot width                  |
| WALL_SLOT_H       | 35.0   | Wall slot height                 |
| FILLET_R          | 3.0    | General fillet radius            |
| CHAMFER            | 0.5    | Top edge chamfer                 |

## 3. BASE BODY
Create: cuboid
Dimensions: BASE_L × BASE_W × BASE_T
Position: corner at (0, 0, 0)

## 4. FEATURE SEQUENCE
Step 1: Create vertical wall
  Create: cuboid
  Dimensions: WALL_T × BASE_W × WALL_H
  Position: corner at (0, 0, BASE_T)
  Boolean: unite with base

Step 2: Create gusset rib
  Sketch plane: XZ at Y = BASE_W / 2 - RIB_T / 2
  Profile: Triangle
    - Line: (WALL_T, BASE_T) → (WALL_T + RIB_SIZE, BASE_T)
    - Line: (WALL_T + RIB_SIZE, BASE_T) → (WALL_T, BASE_T + RIB_SIZE)
    - Line: (WALL_T, BASE_T + RIB_SIZE) → (WALL_T, BASE_T)
  Extrude: distance = RIB_T, direction = +Y
  Boolean: unite with base

Step 3: Wall slot (material removal)
  Sketch plane: YZ at X = 0
  Profile: Rectangle
    - Corner: (BASE_W/2 - WALL_SLOT_W/2, BASE_T + 15.0)
    - Size: WALL_SLOT_W × WALL_SLOT_H
  Extrude cut: distance = WALL_T, direction = +X, target = last

## 5. HOLE TABLE
| Hole # | X    | Y    | Z    | Diameter       | Depth            | Direction |
|--------|------|------|------|----------------|------------------|-----------|
| H1     | 15.0 | 12.5 | 6.0  | MOUNT_HOLE_DIA | MOUNT_HOLE_DEPTH | -Z        |
| H2     | 65.0 | 12.5 | 6.0  | MOUNT_HOLE_DIA | MOUNT_HOLE_DEPTH | -Z        |
| H3     | 15.0 | 37.5 | 6.0  | MOUNT_HOLE_DIA | MOUNT_HOLE_DEPTH | -Z        |
| H4     | 65.0 | 37.5 | 6.0  | MOUNT_HOLE_DIA | MOUNT_HOLE_DEPTH | -Z        |

## 6. FINISH OPERATIONS
6a. Fillets:
  - Edges: vertical_edges on base-to-wall junction
  - Radius: FILLET_R

6b. Chamfers:
  - Edges: top_edges
  - Offset: CHAMFER

6c. View: ISO

## 7. EXPORT
Save as: flanged_l_bracket.prt
Export STEP: flanged_l_bracket.stp
```

---

## Complete Example 2: Motor Mount Plate

```
## 1. PART IDENTITY
Part name: motor_mount_plate
Units: mm
Plane: XY
Origin: (0, 0, 0)

## 2. EXPRESSION TABLE
| Expression Name   | Value  | Description                      |
|-------------------|--------|----------------------------------|
| PLATE_L           | 100.0  | Plate length (X)                 |
| PLATE_W           | 80.0   | Plate width (Y)                  |
| PLATE_T           | 5.0    | Plate thickness (Z)              |
| CENTER_HOLE_DIA   | 25.0   | Center bore for motor shaft      |
| MOUNT_HOLE_DIA    | 5.0    | Corner mounting hole diameter    |
| MOUNT_HOLE_DEPTH  | 5.0    | Corner mounting hole depth       |
| MOUNT_INSET       | 10.0   | Hole inset from plate edge       |
| MOTOR_PCD         | 50.0   | Motor bolt circle diameter       |
| MOTOR_HOLE_DIA    | 4.2    | Motor mounting hole diameter     |
| MOTOR_HOLE_DEPTH  | 5.0    | Motor mounting hole depth        |
| CORNER_R          | 8.0    | Corner rounding radius           |

## 3. BASE BODY
Create: cuboid
Dimensions: PLATE_L × PLATE_W × PLATE_T
Position: corner at (0, 0, 0)

## 4. FEATURE SEQUENCE
Step 1: Center bore (through hole)
  add_hole:
    x = PLATE_L / 2 = 50.0
    y = PLATE_W / 2 = 40.0
    z = PLATE_T = 5.0
    diameter = CENTER_HOLE_DIA
    depth = PLATE_T
    direction = -Z

Step 2: Motor bolt holes (4× on bolt circle)
  First hole:
    x = 50.0 + MOTOR_PCD/2 = 75.0
    y = 40.0
    z = 5.0
    diameter = MOTOR_HOLE_DIA
    depth = MOTOR_HOLE_DEPTH
    direction = -Z
  Pattern: pattern_circular
    axis = Z
    count = 4
    angle_total = 360.0

## 5. HOLE TABLE
| Hole # | X    | Y    | Z   | Diameter       | Depth            | Direction |
|--------|------|------|-----|----------------|------------------|-----------|
| H1     | 10.0 | 10.0 | 5.0 | MOUNT_HOLE_DIA | MOUNT_HOLE_DEPTH | -Z        |
| H2     | 90.0 | 10.0 | 5.0 | MOUNT_HOLE_DIA | MOUNT_HOLE_DEPTH | -Z        |
| H3     | 10.0 | 70.0 | 5.0 | MOUNT_HOLE_DIA | MOUNT_HOLE_DEPTH | -Z        |
| H4     | 90.0 | 70.0 | 5.0 | MOUNT_HOLE_DIA | MOUNT_HOLE_DEPTH | -Z        |

## 6. FINISH OPERATIONS
6a. Fillets:
  - Edges: vertical_edges
  - Radius: CORNER_R

6b. View: ISO

## 7. EXPORT
Save as: motor_mount_plate.prt
Export STEP: motor_mount_plate.stp
```

---

## Quick Checklist Before Submitting a Prompt

- [ ] Every dimension is a named expression (no bare numbers in operations)
- [ ] Every coordinate is absolute (no "center", "middle", "evenly spaced")
- [ ] Every direction is explicit (+X, -Z, etc., never "auto" or "up")
- [ ] Every edge selector is a valid keyword (outer_edges, top_edges, etc.)
- [ ] Features are in build order (base → additions → subtractions → finish)
- [ ] Holes list exact (X, Y, Z) positions
- [ ] Boolean operations specify target and tool bodies
- [ ] Sketch profiles have closed geometry (all lines connect)
- [ ] Part name and export paths are specified
