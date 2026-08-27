import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.bridge import runner

def run_tests():
    print("=== STARTING PHASE 2 LIVE NX 2206 PERSISTENT OBJECT IDENTITY VERIFICATION ===")
    
    # 1. Health check
    probe = runner.call_nx("ping", {})
    if not probe.get("ok"):
        print(f"[FAIL] NX live socket bridge unreachable: {probe}")
        sys.exit(1)
    print("[PASS] NX live socket bridge reachable.")

    temp_dir = tempfile.mkdtemp(prefix="nx_phase2_test_")
    print(f"Working in temp directory: {temp_dir}")
    part_path = os.path.join(temp_dir, f"phase2_live_{int(time.time()*1000)}.prt")

    # Step 1: Create fresh part
    res_part = runner.call_nx("create_part", {"filepath": part_path})
    print("create_part:", res_part)
    assert res_part.get("ok"), f"create_part failed: {res_part}"

    # Step 2: Create base body_1
    res_cube1 = runner.call_nx("create_cuboid", {"length": 60.0, "width": 40.0, "height": 30.0, "x": 0.0, "y": 0.0, "z": 0.0})
    print("create_cuboid (body_1):", res_cube1)
    assert res_cube1.get("ok"), f"create_cuboid failed: {res_cube1}"
    assert res_cube1.get("body_id") == "body_1", f"Expected body_1, got {res_cube1.get('body_id')}"
    assert res_cube1.get("feature_id") == "feature_1", f"Expected feature_1, got {res_cube1.get('feature_id')}"

    # Step 3: Create cutting cylinder (body_2)
    res_cyl = runner.call_nx("create_cylinder", {"radius": 10.0, "height": 50.0, "x": 30.0, "y": 20.0, "z": -10.0, "direction": "Z"})
    print("create_cylinder (body_2):", res_cyl)
    assert res_cyl.get("ok"), f"create_cylinder failed: {res_cyl}"
    assert res_cyl.get("body_id") == "body_2", f"Expected body_2, got {res_cyl.get('body_id')}"
    assert res_cyl.get("feature_id") == "feature_2", f"Expected feature_2, got {res_cyl.get('feature_id')}"

    # Step 4: Boolean subtract referencing persistent IDs 'body_1' and 'body_2'
    res_sub = runner.call_nx("boolean_subtract", {"target": "body_1", "tool": "body_2"})
    print("boolean_subtract(target='body_1', tool='body_2'):", res_sub)
    assert res_sub.get("ok"), f"boolean_subtract failed: {res_sub}"
    assert res_sub.get("body_id") == "body_1", f"Expected body_1 to survive boolean subtract, got {res_sub.get('body_id')}"

    # Step 5: Create addition boss (body_3) with volumetric intersection
    res_boss = runner.call_nx("create_cuboid", {"length": 20.0, "width": 20.0, "height": 15.0, "x": 20.0, "y": 10.0, "z": 25.0})
    print("create_cuboid boss (body_3):", res_boss)
    assert res_boss.get("ok"), f"create_cuboid boss failed: {res_boss}"
    boss_body_id = res_boss.get("body_id")
    print(f"Boss body registered as: {boss_body_id}")
    assert boss_body_id is not None

    # Step 6: Boolean unite referencing persistent IDs 'body_1' and boss_body_id
    res_unite = runner.call_nx("boolean_unite", {"target": "body_1", "tool": boss_body_id})
    print(f"boolean_unite(target='body_1', tool='{boss_body_id}'):", res_unite)
    assert res_unite.get("ok"), f"boolean_unite failed: {res_unite}"
    assert res_unite.get("body_id") == "body_1", f"Expected body_1 to survive boolean unite, got {res_unite.get('body_id')}"

    # Step 7: Sketch and curve persistent identity
    res_sk = runner.call_nx("create_sketch", {"plane": "XY"})
    print("create_sketch:", res_sk)
    assert res_sk.get("ok"), f"create_sketch failed: {res_sk}"
    assert res_sk.get("sketch_id") == "sketch_1", f"Expected sketch_1, got {res_sk.get('sketch_id')}"

    res_circ = runner.call_nx("draw_circle", {"cx": 10.0, "cy": 10.0, "radius": 5.0})
    print("draw_circle:", res_circ)
    assert res_circ.get("ok"), f"draw_circle failed: {res_circ}"
    curve_id = res_circ.get("curve_id")
    print(f"Circle curve registered as: {curve_id}")
    assert curve_id is not None

    # Step 8: Extrude using curve_id
    res_ext = runner.call_nx("extrude", {"distance": 20.0, "start": 0.0, "direction": "Z"})
    print("extrude:", res_ext)
    assert res_ext.get("ok"), f"extrude failed: {res_ext}"
    assert res_ext.get("body_id") is not None

    # Step 9: Verify inspect_part reports clean structure
    res_inspect = runner.call_nx("inspect_part", {})
    print("inspect_part:", res_inspect)
    assert res_inspect.get("ok"), f"inspect_part failed: {res_inspect}"

    print("\n[SUCCESS] ALL PHASE 2 LIVE PERSISTENT OBJECT IDENTITY TESTS PASSED!")

if __name__ == "__main__":
    run_tests()
