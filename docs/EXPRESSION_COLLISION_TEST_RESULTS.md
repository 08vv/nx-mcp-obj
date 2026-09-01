# Expression Collision Test Results

This document summarizes the diagnostics run to check if switching from counter-suffixed `_create_named_expression()` (e.g. `CUBOID_L_1`) to fixed-name `_create_input_expression()` (e.g. `CUBOID_L`) introduced a regression when creating multiple features of the same type in a single session.

## Test Script Details

The test script [run_expression_collision_tests.py](file:///c:/Users/HP/nx-mcp/scratch/run_expression_collision_tests.py) was written and run. The script connects to the live NX session over port 43210 using standard socket communications and runs three sequential test cases in clean part files. It calls a new diagnostic tool `get_diagnostics()` added to the bridge to query all existing expressions and body dimensions directly via the NXOpen API.

### Command Run
```bash
python scratch/run_expression_collision_tests.py
```

---

## 1. Test Case: `create_cuboid`

### Calls Executed
1. `create_cuboid(length=100.0, width=20.0, height=5.0, x=0.0, y=0.0, z=0.0)`
2. `create_cuboid(length=40.0, width=40.0, height=40.0, x=200.0, y=0.0, z=0.0)`

### Diagnostic Results

*   **Expressions Found**:
    *   `CUBOID_L` = 40.0
    *   `CUBOID_W` = 40.0
    *   `CUBOID_H` = 40.0
    *   *Count*: Exactly **one set** of expressions exists. The second call updated/overwrote the values.
*   **Bodies Found**:
    *   `BLOCK(0)` (Cuboid 1): Bounding Box size = **40.0 x 40.0 x 40.0** (originally 100x20x5)
    *   `BLOCK(1)` (Cuboid 2): Bounding Box size = **40.0 x 40.0 x 40.0**

### Conclusion
**CONFIRMED REGRESSION**: Both cuboids share expression `CUBOID_L/CUBOID_W/CUBOID_H`, and creating the second cuboid silently resized the first cuboid to 40x40x40.

---

## 2. Test Case: `create_cylinder`

### Calls Executed
1. `create_cylinder(radius=10.0, height=30.0, x=0.0, y=0.0, z=0.0)`
2. `create_cylinder(radius=25.0, height=50.0, x=200.0, y=0.0, z=0.0)`

### Diagnostic Results

*   **Expressions Found**:
    *   `CYLINDER_R` = 25.0
    *   `CYLINDER_H` = 50.0
    *   *Count*: Exactly **one set** of expressions exists. The second call overwrote the values of the first.
*   **Expression Relations**:
    *   First cylinder's diameter parameters (`p0`) reference `2 * CYLINDER_R` (evaluates to 50.0).
    *   Second cylinder's diameter parameters (`p2`) reference `2 * CYLINDER_R` (evaluates to 50.0).
    *   First cylinder's height parameter (`p1`) references `CYLINDER_H` (evaluates to 50.0).
    *   Second cylinder's height parameter (`p3`) references `CYLINDER_H` (evaluates to 50.0).

### Conclusion
**CONFIRMED REGRESSION**: Both cylinders share expression `CYLINDER_R/CYLINDER_H`, and the second cylinder's creation overwrote the first cylinder's radius and height expressions.

---

## 3. Test Case: `create_cube`

### Calls Executed
1. `create_cube(size=15.0, x=0.0, y=0.0, z=0.0)`
2. `create_cube(size=35.0, x=200.0, y=0.0, z=0.0)`

### Diagnostic Results

*   **Expressions Found**:
    *   `CUBE_SIZE` = 35.0
    *   *Count*: Exactly **one set** of expressions exists. The second call updated/overwrote the values.
*   **Bodies Found**:
    *   `BLOCK(0)` (Cube 1): Bounding Box size = **35.0 x 35.0 x 35.0** (originally 15.0)
    *   `BLOCK(1)` (Cube 2): Bounding Box size = **35.0 x 35.0 x 35.0**

### Conclusion
**CONFIRMED REGRESSION**: Both cubes share expression `CUBE_SIZE`, and creating the second cube resized the first cube to 35.0.

---

## Summary Findings

The regression is **universal** across the migrated functions. Using static base names (like `CUBOID_L` or `CUBE_SIZE`) via `_create_input_expression()` causes subsequent feature creations of the same type to overwrite the existing expressions. Because NX links features to expression names, all existing features referencing those names are dynamically resized to match the new values.
