#!/usr/bin/env python
"""
Live empirical verification suite for Bug 5 in Siemens NX 2206.
Tests:
1. create_sketch(plane="XY", z_offset=39.0) -> draw_rounded_rectangle -> extrude -> verify Z in [39, 45]
2. create_real_sketch(plane="XY", z_offset=39.0) -> draw_rectangle -> extrude -> verify Z in [39, 49]
3. create_sketch("XY") at Z=0 + draw_rounded_rectangle(..., z=39.0) -> extrude -> verify Z in [39, 45]
4. Full composite dog-leg post + dual offset arms (Z=0 and Z=39..45) end-to-end modeling
"""
import math, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.bridge import runner

def send(cmd, **kwargs):
    res = runner.call_nx(cmd, kwargs)
    return res

def run_bug5_verification():
    print("=== LIVE EMPIRICAL VERIFICATION: BUG 5 IN SIEMENS NX 2206 ===")
    
    # -------------------------------------------------------------
    # Test 1: create_sketch with z_offset=39.0 + draw_rounded_rectangle
    # -------------------------------------------------------------
    print("\n--- Test 1: create_sketch(z_offset=39.0) + draw_rounded_rectangle ---")
    send("create_part", filename="bug5_test1")
    r_sk = send("create_sketch", plane="XY", z_offset=39.0)
    print(f"create_sketch: {r_sk}")
    assert r_sk.get("ok"), f"create_sketch failed: {r_sk}"
    
    r_rect = send("draw_rounded_rectangle", arm_length=40.0, arm_width=16.0, end_radius=8.0, cx_left=0.0, cy=0.0)
    print(f"draw_rounded_rectangle: {r_rect}")
    assert r_rect.get("ok"), f"draw_rounded_rectangle failed: {r_rect}"
    
    r_ext = send("extrude", distance=6.0, start=0.0)
    print(f"extrude: {r_ext}")
    assert r_ext.get("ok"), f"extrude failed: {r_ext}"
    
    r_bbox = send("get_bounding_box", body_reference="last")
    print(f"bounding_box: {r_bbox}")
    assert r_bbox.get("ok"), f"get_bounding_box failed: {r_bbox}"
    z_min = r_bbox["bounding_box"]["min"][2]
    z_max = r_bbox["bounding_box"]["max"][2]
    print(f"Solid Z range: [{z_min:.2f}, {z_max:.2f}]")
    assert abs(z_min - 39.0) < 0.1, f"Expected z_min=39.0, got {z_min}"
    assert abs(z_max - 45.0) < 0.1, f"Expected z_max=45.0, got {z_max}"
    print("[PASS] Test 1: create_sketch with z_offset produces extruded solid at Z=[39, 45]")
    
    # -------------------------------------------------------------
    # Test 2: create_real_sketch with z_offset=39.0 + draw_rectangle
    # -------------------------------------------------------------
    print("\n--- Test 2: create_real_sketch(z_offset=39.0) + draw_rectangle ---")
    send("create_part", filename="bug5_test2")
    r_rsk = send("create_real_sketch", plane="XY", z_offset=39.0)
    print(f"create_real_sketch: {r_rsk}")
    assert r_rsk.get("ok"), f"create_real_sketch failed: {r_rsk}"
    
    r_draw = send("draw_rectangle", x=0.0, y=0.0, width=20.0, height=20.0)
    print(f"draw_rectangle: {r_draw}")
    assert r_draw.get("ok"), f"draw_rectangle failed: {r_draw}"
    
    r_ext = send("extrude", distance=10.0, start=0.0)
    print(f"extrude: {r_ext}")
    assert r_ext.get("ok"), f"extrude failed: {r_ext}"
    
    r_bbox = send("get_bounding_box", body_reference="last")
    print(f"bounding_box: {r_bbox}")
    assert r_bbox.get("ok"), f"get_bounding_box failed: {r_bbox}"
    z_min = r_bbox["bounding_box"]["min"][2]
    z_max = r_bbox["bounding_box"]["max"][2]
    print(f"Solid Z range: [{z_min:.2f}, {z_max:.2f}]")
    assert abs(z_min - 39.0) < 0.1, f"Expected z_min=39.0, got {z_min}"
    assert abs(z_max - 49.0) < 0.1, f"Expected z_max=49.0, got {z_max}"
    print("[PASS] Test 2: create_real_sketch produces extruded solid at Z=[39, 49]")
    
    # -------------------------------------------------------------
    # Test 3: draw_rounded_rectangle(..., z=39.0) direct override
    # -------------------------------------------------------------
    print("\n--- Test 3: draw_rounded_rectangle(..., z=39.0) on base sketch ---")
    send("create_part", filename="bug5_test3")
    send("create_sketch", plane="XY")
    r_rect = send("draw_rounded_rectangle", arm_length=40.0, arm_width=16.0, end_radius=8.0, cx_left=0.0, cy=0.0, z=39.0)
    print(f"draw_rounded_rectangle(z=39): {r_rect}")
    assert r_rect.get("ok"), f"draw_rounded_rectangle failed: {r_rect}"
    
    r_ext = send("extrude", distance=6.0, start=0.0)
    print(f"extrude: {r_ext}")
    assert r_ext.get("ok"), f"extrude failed: {r_ext}"
    
    r_bbox = send("get_bounding_box", body_reference="last")
    print(f"bounding_box: {r_bbox}")
    assert r_bbox.get("ok"), f"get_bounding_box failed: {r_bbox}"
    z_min = r_bbox["bounding_box"]["min"][2]
    z_max = r_bbox["bounding_box"]["max"][2]
    print(f"Solid Z range: [{z_min:.2f}, {z_max:.2f}]")
    assert abs(z_min - 39.0) < 0.1, f"Expected z_min=39.0, got {z_min}"
    assert abs(z_max - 45.0) < 0.1, f"Expected z_max=45.0, got {z_max}"
    print("[PASS] Test 3: draw_rounded_rectangle with z=39.0 places curves and solid at Z=[39, 45]")
    
    # -------------------------------------------------------------
    # Test 4: End-to-end composite dog-leg post + dual offset arms
    # -------------------------------------------------------------
    print("\n--- Test 4: Composite post + bottom arm (Z=0..6) + top rotated arm (Z=39..45) ---")
    send("create_part", filename="bug5_test4_composite")
    
    # 1. Post: cylinder R=10, H=45 at (0,0,0)
    r_post = send("create_cylinder", radius=10.0, height=45.0, x=0.0, y=0.0, z=0.0)
    print(f"create_cylinder (post): {r_post}")
    assert r_post.get("ok"), f"create_cylinder failed: {r_post}"
    
    # 2. Bottom arm: +X arm at Z=0..6
    send("create_sketch", plane="XY", z_offset=0.0)
    send("draw_rounded_rectangle", arm_length=40.0, arm_width=16.0, end_radius=8.0, cx_left=0.0, cy=0.0)
    r_arm1 = send("extrude", distance=6.0, start=0.0)
    print(f"extrude arm1: {r_arm1}")
    r_unite1 = send("boolean_unite", target_body="last", tool_body="body_1")
    print(f"unite arm1 + post: {r_unite1}")
    assert r_unite1.get("ok"), f"boolean_unite 1 failed: {r_unite1}"
    
    # 3. Top arm: -X rotated arm at Z=39..45
    send("create_sketch", plane="XY", z_offset=39.0, rotate_z_deg=120.0)
    send("draw_rounded_rectangle", arm_length=40.0, arm_width=16.0, end_radius=8.0, cx_left=0.0, cy=0.0)
    r_arm2 = send("extrude", distance=6.0, start=0.0)
    print(f"extrude arm2: {r_arm2}")
    r_unite2 = send("boolean_unite", target_body="last", tool_body="body_1")
    print(f"unite arm2 + composite: {r_unite2}")
    assert r_unite2.get("ok"), f"boolean_unite 2 failed: {r_unite2}"
    
    # Check total composite bounding box
    r_comp_bbox = send("get_bounding_box", body_reference="last")
    print(f"composite bounding_box: {r_comp_bbox}")
    assert r_comp_bbox.get("ok")
    z_min_total = r_comp_bbox["bounding_box"]["min"][2]
    z_max_total = r_comp_bbox["bounding_box"]["max"][2]
    print(f"Composite solid total Z range: [{z_min_total:.2f}, {z_max_total:.2f}]")
    assert abs(z_min_total - 0.0) < 0.1, f"Expected z_min=0.0, got {z_min_total}"
    assert abs(z_max_total - 45.0) < 0.1, f"Expected z_max=45.0, got {z_max_total}"
    
    # Fillet top rim
    r_fillet = send("add_fillet", edges="top_edges", radius=1.0, body_reference="last")
    print(f"fillet on top_edges: {r_fillet}")
    assert r_fillet.get("ok"), f"add_fillet failed: {r_fillet}"
    
    print("\n[ALL PASS] All Bug 5 tests successfully verified live in Siemens NX 2206!")

if __name__ == "__main__":
    run_bug5_verification()
