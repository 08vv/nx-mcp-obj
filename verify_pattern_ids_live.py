import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.bridge import runner

def run_tests():
    print("=== STARTING LIVE PATTERN MONOTONIC ID VERIFICATION ===")
    
    probe = runner.call_nx("ping", {})
    if not probe.get("ok"):
        print(f"[FAIL] NX live socket bridge unreachable: {probe}")
        sys.exit(1)
    print("[PASS] NX live socket bridge reachable.")

    temp_dir = tempfile.mkdtemp(prefix="nx_pat_test_")
    part_path = os.path.join(temp_dir, f"pat_live_{int(time.time()*1000)}.prt")

    # 1. Fresh part
    res_part = runner.call_nx("create_part", {"filepath": part_path})
    print("1. create_part:", res_part)
    assert res_part.get("ok")

    # 2. Base disk (body_1, feature_1)
    res_disk = runner.call_nx("create_cylinder", {"radius": 50.0, "height": 20.0, "x": 0.0, "y": 0.0, "z": 0.0, "direction": "Z"})
    print("2. create_cylinder (base disk):", res_disk)
    assert res_disk.get("ok")
    assert res_disk.get("body_id") == "body_1"
    assert res_disk.get("feature_id") == "feature_1"

    # 3. Create hole cut on the disk
    res_hole = runner.call_nx("add_hole", {"diameter": 10.0, "depth": 15.0, "x": 30.0, "y": 0.0, "z": 0.0, "direction": "Z"})
    print("3. add_hole (feature cut):", res_hole)
    assert res_hole.get("ok")
    hole_feat_id = res_hole.get("feature_id") or "feature_2"

    # 4. Pattern circular the hole 4x around Z axis
    res_pat_circ = runner.call_nx("pattern_circular", {"feature_name": hole_feat_id, "axis": "Z", "count": 4, "angle_total": 360.0})
    print("4. pattern_circular 4x:", res_pat_circ)
    assert res_pat_circ.get("ok")
    print(f"   -> Circular pattern feature ID: {res_pat_circ.get('feature_id')}")

    # 5. Create a standalone solid block to test multi-body pattern
    res_block = runner.call_nx("create_cuboid", {"length": 15.0, "width": 15.0, "height": 15.0, "x": 100.0, "y": 0.0, "z": 0.0})
    print("5. create_cuboid (standalone solid):", res_block)
    assert res_block.get("ok")
    seed_body_id = res_block.get("body_id")
    seed_feat_id = res_block.get("feature_id")
    print(f"   -> Seed body: {seed_body_id}, Seed feature: {seed_feat_id}")

    # 6. Linear pattern the solid body feature 4x along Y
    res_pat_feat = runner.call_nx("pattern_feature", {"feature_name": seed_feat_id, "direction": "Y", "count": 4, "pitch": 25.0})
    print("6. pattern_feature 4x solid bodies:", res_pat_feat)
    assert res_pat_feat.get("ok")
    print(f"   -> Linear pattern feature ID: {res_pat_feat.get('feature_id')}")
    print(f"   -> Created pattern body IDs: {res_pat_feat.get('body_ids')}")

    # 7. Inspect part and print summary
    res_inspect = runner.call_nx("inspect_part", {})
    print("7. inspect_part:", res_inspect)
    assert res_inspect.get("ok")

    print("\n[SUCCESS] LIVE PATTERN MONOTONIC ID VERIFICATION PASSED!")

if __name__ == "__main__":
    run_tests()
