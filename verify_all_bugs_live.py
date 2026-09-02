#!/usr/bin/env python
"""Comprehensive live verification of all audited state tracking bugs."""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.bridge import runner

def send(cmd, **kwargs):
    return runner.call_nx(cmd, kwargs)

def test_bug1_spline_offset_close():
    """Bug 1: draw_spline -> offset_curve -> close_curve_region."""
    print("\n=== Test Bug 1: Spline -> Offset -> Close Region ===")
    r = send("create_part", filename="bug1_test")
    assert r.get("ok"), f"create_part failed: {r}"
    
    send("create_sketch", plane="XY")
    pts = [[0, 0], [10, 15], [25, 20], [40, 10], [50, 0]]
    rs = send("draw_spline", points=pts)
    print("  draw_spline:", rs)
    if not rs.get("ok"):
        return False
        
    ro = send("offset_curve", curve_reference="last", start_width=5.0, end_width=8.0)
    print("  offset_curve:", ro)
    if not ro.get("ok"):
        return False
        
    rc = send("close_curve_region", curve1="last", curve2="previous")
    print("  close_curve_region:", rc)
    if not rc.get("ok"):
        return False
        
    # Now try to extrude this closed curve region
    re = send("extrude", distance=15)
    print("  extrude closed region:", re)
    if not re.get("ok"):
        return False
        
    rb = send("get_bounding_box", body_reference="last")
    print("  BBox:", rb)
    return rb.get("ok", False)

def test_bug2_pattern_circular():
    """Bug 2: Main disc -> hole -> pattern hole -> get_bounding_box / add_fillet."""
    print("\n=== Test Bug 2: Disc -> Hole -> Pattern Circular ===")
    r = send("create_part", filename="bug2_test")
    assert r.get("ok"), f"create_part failed: {r}"
    
    # Main disc: radius=50, height=20
    r1 = send("create_cylinder", radius=50, height=20, x=0, y=0, z=0)
    disc_id = r1["body_id"]
    print("  Main disc:", r1)
    
    # Hole cylinder at radius 35
    r2 = send("create_cylinder", radius=5, height=30, x=35, y=0, z=-5)
    hole_id = r2["body_id"]
    
    # Subtract hole from disc
    rsub = send("boolean_subtract", target=disc_id, tool=hole_id)
    print("  Subtract hole:", rsub)
    feat_hole = rsub["feature_id"]
    
    # Pattern hole 4x around Z
    rp = send("pattern_circular", feature_name=feat_hole, count=4, angle_total=360, axis="Z")
    print("  pattern_circular:", rp)
    
    # Check bounding box of "last" (should be the full disc ~100mm diameter)
    rb = send("get_bounding_box", body_reference="last")
    print("  BBox after pattern:", rb)
    if rb.get("ok"):
        dx = rb["bounding_box"]["max"][0] - rb["bounding_box"]["min"][0]
        print(f"  DX={dx:.1f} (expected ~100)")
        return dx >= 90
    return False

def test_bug4_boolean_unite():
    """Bug 4: Cylinder + cuboid unite -> check bounding box of 'last'."""
    print("\n=== Test Bug 4: Boolean Unite State ===")
    r = send("create_part", filename="bug4_test")
    assert r.get("ok"), f"create_part failed: {r}"
    
    r1 = send("create_cylinder", radius=20, height=30)
    bid1 = r1["body_id"]
    r2 = send("create_cuboid", length=60, width=15, height=15, x=-30, y=-7.5, z=15)
    bid2 = r2["body_id"]
    
    ru = send("boolean_unite", target=bid1, tool=bid2)
    print("  Unite result:", ru)
    
    rb = send("get_bounding_box", body_reference="last")
    print("  BBox after unite:", rb)
    if rb.get("ok"):
        dx = rb["bounding_box"]["max"][0] - rb["bounding_box"]["min"][0]
        print(f"  DX={dx:.1f} (expected ~60)")
        return dx >= 55
    return False

if __name__ == "__main__":
    print("=== LIVE STATE TRACKING AUDIT VERIFICATION ===")
    for test_fn in [test_bug1_spline_offset_close, test_bug2_pattern_circular, test_bug4_boolean_unite]:
        try:
            res = test_fn()
            print("  Result:", "[PASS]" if res else "[FAIL]")
        except Exception as e:
            print("  [ERROR]:", e)
