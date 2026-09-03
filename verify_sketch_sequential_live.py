#!/usr/bin/env python
"""
Live empirical verification suite for sequential sketch Z-offset positioning via MCP tools.
Verifies multiple sequential sketches with and without boolean operations in a single session.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.tools import file_ops, sketch, modeling, measure

def run():
    print("=== LIVE VERIFICATION: SEQUENTIAL SKETCH Z-OFFSETS ===")
    r0 = file_ops.create_part("verify_sequential_sketch_part")
    print(f"create_part: {r0}")

    # =========================================================================
    # Test A: Multi-Arm with Union (the exact workflow reported in the prompt)
    # =========================================================================
    print("\n--- Test A: Multi-Arm with Union ---")
    # 1. Base Post
    r_post = modeling.create_cylinder(radius=10.0, height=45.0, x=0.0, y=0.0, z=0.0)
    print(f"Post created: {r_post}")

    # 2. Bottom arm at Z=0..6
    r_sk1 = sketch.create_sketch(plane="XY", z_offset=0.0)
    print(f"Sketch 1 (Z=0): {r_sk1}")
    r_dr1 = sketch.draw_rounded_rectangle(arm_length=40.0, arm_width=16.0, end_radius=8.0)
    print(f"Draw 1: {r_dr1}")
    r_ex1 = modeling.extrude_from_sketch(distance=6.0, start=0.0)
    print(f"Extrude 1: {r_ex1}")
    
    # Check bottom arm isolated BBox
    r_bb1 = measure.get_bounding_box(body_reference="last")
    print(f"Arm 1 isolated BBox: {r_bb1}")
    assert "0.00" in str(r_bb1) and "6.00" in str(r_bb1), f"Arm 1 must have Z range [0, 6], got: {r_bb1}"
    
    # 3. Unite bottom arm with post
    r_u1 = modeling.boolean_unite(target="last", tool="body_1")
    print(f"Unite 1: {r_u1}")

    # 4. Top arm at Z=39..45 (rotated 120 deg)
    r_sk2 = sketch.create_sketch(plane="XY", z_offset=39.0, rotate_z_deg=120.0)
    print(f"Sketch 2 (Z=39): {r_sk2}")
    r_dr2 = sketch.draw_rounded_rectangle(arm_length=40.0, arm_width=16.0, end_radius=8.0)
    print(f"Draw 2: {r_dr2}")
    r_ex2 = modeling.extrude_from_sketch(distance=6.0, start=0.0)
    print(f"Extrude 2: {r_ex2}")

    # 5. Check top arm isolated BBox BEFORE union (Critical check)
    r_bb2 = measure.get_bounding_box(body_reference="last")
    print(f"Arm 2 isolated BBox before union: {r_bb2}")
    assert "39.00" in str(r_bb2) and "45.00" in str(r_bb2), (
        f"Arm 2 must have Z range [39, 45], got: {r_bb2}"
    )
    print("[PASS] Test A Passed: Top arm correctly created at Z=[39, 45] after prior sketch+extrude+unite cycle!")

    # 6. Unite top arm with composite body
    r_u2 = modeling.boolean_unite(target="last", tool="body_2")
    print(f"Unite 2: {r_u2}")

    # =========================================================================
    # Test B: Consecutive Sketches WITHOUT Boolean Operations
    # =========================================================================
    print("\n--- Test B: Consecutive Sketches Without Boolean Operations ---")
    # Sketch 3 at Z=15.0
    r_sk3 = sketch.create_sketch(plane="XY", z_offset=15.0)
    print(f"Sketch 3 (Z=15): {r_sk3}")
    r_dr3 = sketch.draw_rounded_rectangle(arm_length=30.0, arm_width=10.0, end_radius=5.0)
    print(f"Draw 3: {r_dr3}")
    r_ex3 = modeling.extrude(distance=5.0, start=0.0)
    print(f"Extrude 3: {r_ex3}")
    r_bb3 = measure.get_bounding_box(body_reference="last")
    print(f"Body 3 isolated BBox: {r_bb3}")
    assert "15.00" in str(r_bb3) and "20.00" in str(r_bb3), (
        f"Body 3 must have Z range [15, 20], got: {r_bb3}"
    )

    # Sketch 4 at Z=55.0
    r_sk4 = sketch.create_sketch(plane="XY", z_offset=55.0)
    print(f"Sketch 4 (Z=55): {r_sk4}")
    r_dr4 = sketch.draw_rounded_rectangle(arm_length=30.0, arm_width=10.0, end_radius=5.0)
    print(f"Draw 4: {r_dr4}")
    r_ex4 = modeling.extrude(distance=5.0, start=0.0)
    print(f"Extrude 4: {r_ex4}")
    r_bb4 = measure.get_bounding_box(body_reference="last")
    print(f"Body 4 isolated BBox: {r_bb4}")
    assert "55.00" in str(r_bb4) and "60.00" in str(r_bb4), (
        f"Body 4 must have Z range [55, 60], got: {r_bb4}"
    )

    print("\n[ALL PASS] Sequential sketch Z-offsets verified live in Siemens NX 2206!")

if __name__ == "__main__":
    run()
