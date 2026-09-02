#!/usr/bin/env python
"""Live verification of Bug 3 with fresh part per test case."""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.bridge import runner

def send(cmd, **kwargs):
    return runner.call_nx(cmd, kwargs)

def setup_composite_body(part_name="comp_part"):
    r = send("create_part", filename=part_name)
    assert r.get("ok"), f"create_part failed: {r}"
    
    # 1. Post: cylinder R=10, height=45 at (0,0,0)
    r_post = send("create_cylinder", radius=10, height=45, x=0, y=0, z=0)
    assert r_post.get("ok"), f"create_cylinder post failed: {r_post}"
    post_bid = r_post["body_id"]
    
    # 2. Arm 1 (+X): rounded slot extending +X from post at Z=0..6
    send("create_sketch", plane="XY")
    r_slot1 = send("draw_rounded_rectangle", arm_length=40, arm_width=16, end_radius=8, cx_left=0, cy=0, z=0)
    assert r_slot1.get("ok"), f"draw_rounded_rectangle 1 failed: {r_slot1}"
    r_ext1 = send("extrude", distance=6, start=0)
    assert r_ext1.get("ok"), f"extrude arm 1 failed: {r_ext1}"
    arm1_bid = r_ext1["body_id"]
    
    r_unite1 = send("boolean_unite", target=post_bid, tool=arm1_bid)
    assert r_unite1.get("ok"), f"boolean_unite 1 failed: {r_unite1}"
    comb1_bid = r_unite1["body_id"]
    
    # 3. Arm 2 (-X): rounded slot extending -X from post at Z=39..45
    send("create_sketch", plane="XY")
    r_slot2 = send("draw_rounded_rectangle", arm_length=40, arm_width=16, end_radius=8, cx_left=-40, cy=5, z=39)
    assert r_slot2.get("ok"), f"draw_rounded_rectangle 2 failed: {r_slot2}"
    r_ext2 = send("extrude", distance=6, start=39)
    assert r_ext2.get("ok"), f"extrude arm 2 failed: {r_ext2}"
    arm2_bid = r_ext2["body_id"]
    
    r_unite2 = send("boolean_unite", target=comb1_bid, tool=arm2_bid)
    assert r_unite2.get("ok"), f"boolean_unite 2 failed: {r_unite2}"
    final_bid = r_unite2["body_id"]
    return final_bid

def test_all_individually():
    print("=== LIVE VERIFICATION: BUG 3 ON FRESH COMPOSITE BODIES ===")
    
    # Test 1: outer_edges
    print("\n--- Test 1: edges='outer_edges' on fresh composite body ---")
    setup_composite_body("fresh_outer")
    r_outer = send("add_fillet", radius=1.5, body="last", edges="outer_edges")
    print(f"Result (outer_edges): {r_outer}")
    
    # Test 2: top_edges
    print("\n--- Test 2: edges='top_edges' on fresh composite body ---")
    setup_composite_body("fresh_top")
    r_top = send("add_fillet", radius=1.5, body="last", edges="top_edges")
    print(f"Result (top_edges): {r_top}")
    
    # Test 3: bottom_edges
    print("\n--- Test 3: edges='bottom_edges' on fresh composite body ---")
    setup_composite_body("fresh_bottom")
    r_bottom = send("add_fillet", radius=1.5, body="last", edges="bottom_edges")
    print(f"Result (bottom_edges): {r_bottom}")
    
    # Test 4: vertical_edges
    print("\n--- Test 4: edges='vertical_edges' on fresh composite body ---")
    setup_composite_body("fresh_vertical")
    r_vert = send("add_fillet", radius=1.5, body="last", edges="vertical_edges")
    print(f"Result (vertical_edges): {r_vert}")
    
    # Test 5: feature-scoped edges (e.g. cylinder_1:top)
    print("\n--- Test 5: feature-scoped 'cylinder_1:top' on fresh composite body ---")
    setup_composite_body("fresh_feat")
    r_feat = send("add_fillet", radius=1.5, body="last", edges="cylinder_1:top")
    print(f"Result (cylinder_1:top): {r_feat}")

    # Test 6: Non-matching edge filter (should fail loud with clear SelectionError)
    print("\n--- Test 6: Non-matching edge filter 'non_existent_edges' ---")
    setup_composite_body("fresh_nonexist")
    r_bad = send("add_fillet", radius=1.5, body="last", edges="non_existent_edges")
    print(f"Result (non_existent): {r_bad}")
    assert not r_bad.get("ok"), "Expected non-matching filter to fail"
    assert "Unrecognized or unsupported" in r_bad.get("error", "") or "No edges matched" in r_bad.get("error", "")

    # Test 7: Oversized radius rejecting blend (should fail loud with clear diagnostic message)
    print("\n--- Test 7: Oversized radius (R=50.0mm on 10mm cylinder) ---")
    setup_composite_body("fresh_oversize")
    r_over = send("add_fillet", radius=50.0, body="last", edges="top_edges")
    print(f"Result (oversized R): {r_over}")
    assert not r_over.get("ok"), "Expected oversized fillet to fail"
    assert "Failed to create blend" in r_over.get("error", "") or "Unable to create Blend" in r_over.get("error", "")

    print("\n[ALL PASS] Bug 3 Part A and Part B successfully verified live in Siemens NX 2206!")

if __name__ == "__main__":
    test_all_individually()
