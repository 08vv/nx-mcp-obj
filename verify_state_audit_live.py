#!/usr/bin/env python
"""Phase B: Live verification of state-tracking suspects against NX 2206."""
import json, os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.bridge import runner

def send(cmd, **kwargs):
    return runner.call_nx(cmd, kwargs)

def test_rc1_boolean_unite():
    """RC1: boolean_unite doesn't set last_body_id -> stale ID after unite."""
    print("\n=== RC1: boolean_unite last_body_id test ===")
    
    r = send("create_part", filename="rc1_test")
    assert r.get("ok"), f"create_part failed: {r}"
    
    r1 = send("create_cuboid", length=40, width=25, height=20, x=0, y=0, z=0)
    assert r1.get("ok"), f"create_cuboid 1 failed: {r1}"
    bid1 = r1["body_id"]
    print(f"  Cuboid 1: body_id={bid1}")
    
    r2 = send("create_cuboid", length=30, width=25, height=20, x=20, y=0, z=0)
    assert r2.get("ok"), f"create_cuboid 2 failed: {r2}"
    bid2 = r2["body_id"]
    print(f"  Cuboid 2: body_id={bid2}")
    
    ru = send("boolean_unite", target=bid1, tool=bid2)
    assert ru.get("ok"), f"boolean_unite failed: {ru}"
    print(f"  Unite result: body_id={ru.get('body_id')}, modified={ru.get('modified')}")
    
    rb = send("get_bounding_box", body_reference="last")
    print(f"  BBox(last): {rb}")
    
    if rb.get("ok"):
        bbox = rb["bounding_box"]
        dx = bbox["max"][0] - bbox["min"][0]
        dy = bbox["max"][1] - bbox["min"][1]
        dz = bbox["max"][2] - bbox["min"][2]
        print(f"  Extents: DX={dx:.1f}, DY={dy:.1f}, DZ={dz:.1f}")
        if dx >= 45:
            print("  [PASS] BBox reflects united body")
            return True
        else:
            print(f"  [FAIL] BBox too small -- DX={dx:.1f}, expected ~50. 'last' resolved to pre-union body.")
            return False
    else:
        print(f"  [FAIL] get_bounding_box failed: {rb.get('error')}")
        return False

def test_rc1_boolean_subtract():
    """RC1: boolean_subtract doesn't set last_body_id."""
    print("\n=== RC1: boolean_subtract last_body_id test ===")
    
    r = send("create_part", filename="rc1b_test")
    assert r.get("ok"), f"create_part failed: {r}"
    
    r1 = send("create_cuboid", length=40, width=25, height=20)
    assert r1.get("ok"), f"create_cuboid failed: {r1}"
    bid1 = r1["body_id"]
    print(f"  Target cuboid: body_id={bid1}")
    
    r2 = send("create_cylinder", radius=5, height=25, x=20, y=12.5, z=0)
    assert r2.get("ok"), f"create_cylinder failed: {r2}"
    bid2 = r2["body_id"]
    print(f"  Tool cylinder: body_id={bid2}")
    
    rs = send("boolean_subtract", target=bid1, tool=bid2)
    assert rs.get("ok"), f"boolean_subtract failed: {rs}"
    print(f"  Subtract result: body_id={rs.get('body_id')}")
    
    rb = send("get_bounding_box", body_reference="last")
    print(f"  BBox(last): {rb}")
    
    if rb.get("ok"):
        bbox = rb["bounding_box"]
        dx = bbox["max"][0] - bbox["min"][0]
        print(f"  DX={dx:.1f} (should be ~40, the cuboid)")
        if 35 <= dx <= 45:
            print("  [PASS] 'last' correctly resolves to subtracted cuboid")
            return True
        else:
            print(f"  [FAIL] DX={dx:.1f} -- wrong body")
            return False
    else:
        print(f"  [FAIL] get_bounding_box failed: {rb.get('error')}")
        return False

def test_rc2_boolean_combine():
    """RC2: boolean_combine has no post-boolean state management."""
    print("\n=== RC2: boolean_combine state test ===")
    
    r = send("create_part", filename="rc2_test")
    assert r.get("ok"), f"create_part failed: {r}"
    
    r1 = send("create_cuboid", length=40, width=25, height=20)
    assert r1.get("ok"), f"create_cuboid 1 failed: {r1}"
    bid1 = r1["body_id"]
    
    r2 = send("create_cuboid", length=30, width=25, height=20, x=20, y=0, z=0)
    assert r2.get("ok"), f"create_cuboid 2 failed: {r2}"
    bid2 = r2["body_id"]
    
    print(f"  Bodies: {bid1}, {bid2}")
    
    rc = send("boolean_combine", operation="unite", target=bid1, tool=bid2)
    print(f"  boolean_combine result: {rc}")
    
    if not rc.get("ok"):
        print(f"  [FAIL] boolean_combine failed: {rc.get('error')}")
        return False
    
    rb = send("get_bounding_box", body_reference="last")
    print(f"  BBox(last): {rb}")
    
    if rb.get("ok"):
        bbox = rb["bounding_box"]
        dx = bbox["max"][0] - bbox["min"][0]
        print(f"  DX={dx:.1f} (should be ~50 if united)")
        if dx >= 45:
            print("  [PASS] boolean_combine state is correct")
            return True
        else:
            print(f"  [FAIL] DX={dx:.1f} -- 'last' didn't update to united body")
            return False
    else:
        print(f"  [FAIL] get_bounding_box failed: {rb.get('error')}")
        return False

def test_rc4_extrude_cut():
    """RC4: extrude_cut sets last_body to stale pre-cut target reference."""
    print("\n=== RC4: extrude_cut stale reference test ===")
    
    r = send("create_part", filename="rc4_test")
    assert r.get("ok"), f"create_part failed: {r}"
    
    r1 = send("create_cylinder", radius=30, height=20)
    assert r1.get("ok"), f"create_cylinder failed: {r1}"
    bid1 = r1["body_id"]
    print(f"  Cylinder: body_id={bid1}")
    
    send("create_sketch", plane="XY")
    send("draw_rectangle", x=-5, y=-5, width=10, height=10)
    
    rc = send("extrude_cut", distance=20, target=bid1)
    print(f"  extrude_cut result: {rc}")
    
    if not rc.get("ok"):
        print(f"  [FAIL] extrude_cut failed: {rc.get('error')}")
        return False
    
    rb = send("get_bounding_box", body_reference="last")
    print(f"  BBox(last): {rb}")
    
    if rb.get("ok"):
        bbox = rb["bounding_box"]
        dx = bbox["max"][0] - bbox["min"][0]
        print(f"  DX={dx:.1f} (should be ~60, the full cylinder diameter)")
        if dx >= 55:
            print("  [PASS] last_body correctly references the cut cylinder")
            return True
        else:
            print(f"  [FAIL] DX={dx:.1f} -- stale or wrong body")
            return False
    else:
        print(f"  [FAIL] get_bounding_box failed: {rb.get('error')}")
        return False

def test_rc5_extrude_from_sketch():
    """RC5: extrude_from_sketch missing body_id/feature_id in response."""
    print("\n=== RC5: extrude_from_sketch response metadata test ===")
    
    r = send("create_part", filename="rc5_test")
    assert r.get("ok"), f"create_part failed: {r}"
    
    send("create_sketch", plane="XY")
    send("draw_rectangle", x=0, y=0, width=20, height=20)
    
    re = send("extrude_from_sketch", distance=10)
    print(f"  extrude_from_sketch result: {re}")
    
    if not re.get("ok"):
        print(f"  [FAIL] extrude_from_sketch failed: {re.get('error')}")
        return False
    
    has_bid = "body_id" in re
    has_fid = "feature_id" in re
    print(f"  Has body_id: {has_bid}, Has feature_id: {has_fid}")
    
    rb = send("get_bounding_box", body_reference="last")
    print(f"  BBox(last): {rb}")
    
    if not has_bid:
        print("  [FAIL] Response missing body_id")
        return False
    
    if rb.get("ok"):
        print("  [PASS] extrude_from_sketch response and state are correct")
        return True
    else:
        print(f"  [FAIL-PARTIAL] Response had body_id={has_bid} but bbox failed: {rb.get('error')}")
        return False

if __name__ == "__main__":
    print("=== PHASE B: Live Verification of State-Tracking Suspects ===")
    
    try:
        r = send("ping")
        if not r.get("ok"):
            print(f"Bridge not ready: {r}")
            sys.exit(1)
        print(f"[OK] Connected to NX bridge: {r}\n")
    except Exception as e:
        print(f"[FAIL] Cannot connect to NX bridge: {e}")
        sys.exit(1)
    
    results = {}
    for name, test_fn in [
        ("RC1-unite", test_rc1_boolean_unite),
        ("RC1-subtract", test_rc1_boolean_subtract),
        ("RC2-combine", test_rc2_boolean_combine),
        ("RC4-extrude_cut", test_rc4_extrude_cut),
        ("RC5-extrude_from_sketch", test_rc5_extrude_from_sketch),
    ]:
        try:
            results[name] = test_fn()
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
            results[name] = False
    
    print("\n=== PHASE B RESULTS ===")
    all_pass = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: [{status}]")
        if not passed:
            all_pass = False
    
    if all_pass:
        print("\n[ALL PASS] No state-tracking bugs confirmed live.")
    else:
        failed = [n for n, p in results.items() if not p]
        print(f"\n[CONFIRMED] {len(failed)} state-tracking bug(s) confirmed live: {', '.join(failed)}")
    
    sys.exit(0 if all_pass else 1)
