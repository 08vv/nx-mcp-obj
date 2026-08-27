import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.bridge import runner

def run_tests():
    print("=== STARTING PHASE 3 LIVE VERIFICATION (GENERAL PARAMETRIC OPERATIONS) ===")
    
    probe = runner.call_nx("ping", {})
    if not probe.get("ok"):
        print(f"[FAIL] NX live socket bridge unreachable: {probe}")
        sys.exit(1)
    print("[PASS] NX live socket bridge reachable.")

    temp_dir = tempfile.mkdtemp(prefix="nx_p3_test_")
    part_path = os.path.join(temp_dir, f"phase3_live_{int(time.time()*1000)}.prt")

    # 1. Fresh part
    res_part = runner.call_nx("create_part", {"filepath": part_path})
    print("1. create_part:", res_part)
    assert res_part.get("ok")

    # 2. Test create_profile (L-shaped closed profile on XY)
    l_points = [
        [0.0, 0.0],
        [60.0, 0.0],
        [60.0, 20.0],
        [20.0, 20.0],
        [20.0, 50.0],
        [0.0, 50.0],
    ]
    res_prof = runner.call_nx("create_profile", {"points": l_points, "plane": "XY", "closed": True})
    print("2. create_profile (L-shape):", res_prof)
    assert res_prof.get("ok")
    assert res_prof.get("profile_id") == "profile_1"
    assert len(res_prof.get("curve_ids", [])) == 6

    # 3. Test extrude_profile
    res_ext = runner.call_nx("extrude_profile", {"profile_id": "profile_1", "distance": 35.0, "direction": "Z"})
    print("3. extrude_profile:", res_ext)
    assert res_ext.get("ok")
    body1_id = res_ext.get("body_id")
    feat1_id = res_ext.get("feature_id")
    print(f"   -> Extruded body: {body1_id}, feature: {feat1_id}")
    assert body1_id == "body_1"

    # 4. Test loft (Through Curves)
    # Section 1: base square 40x40 at z=0 (translated to x=100)
    p_sec1 = [
        [100.0, 0.0, 0.0],
        [140.0, 0.0, 0.0],
        [140.0, 40.0, 0.0],
        [100.0, 40.0, 0.0],
    ]
    res_s1 = runner.call_nx("create_profile", {"points": p_sec1, "plane": "XY", "closed": True})
    prof2_id = res_s1.get("profile_id")
    print("4a. create_profile (Loft section 1):", res_s1)

    # Section 2: top square 20x20 at z=50 (centered above section 1)
    p_sec2 = [
        [110.0, 10.0, 50.0],
        [130.0, 10.0, 50.0],
        [130.0, 30.0, 50.0],
        [110.0, 30.0, 50.0],
    ]
    res_s2 = runner.call_nx("create_profile", {"points": p_sec2, "plane": "XY", "closed": True})
    prof3_id = res_s2.get("profile_id")
    print("4b. create_profile (Loft section 2):", res_s2)

    res_loft = runner.call_nx("loft", {"profile_ids": [prof2_id, prof3_id], "body_type": "solid"})
    print("4c. loft (Through Curves):", res_loft)
    assert res_loft.get("ok")
    loft_body = res_loft.get("body_id")
    print(f"   -> Lofted body: {loft_body}")

    # 5. Test variable_offset (Curve offset with linear law)
    res_voff = runner.call_nx("variable_offset", {"target_ref": prof2_id, "offset_start": 3.0, "offset_end": 8.0, "law": "linear"})
    print("5. variable_offset (curve linear law):", res_voff)
    assert res_voff.get("ok")

    # 6. Test unified pattern (Circular & Linear modes)
    # Circular pattern of a hole on body_1
    res_hole = runner.call_nx("add_hole", {"diameter": 8.0, "depth": 25.0, "x": 10.0, "y": 10.0, "z": 0.0, "direction": "Z", "body": "body_1"})
    hole_feat = res_hole.get("feature_id")
    print("6a. add_hole on body_1:", res_hole)
    assert res_hole.get("ok")

    res_pat_circ = runner.call_nx("pattern", {"feature_ref": hole_feat, "mode": "circular", "count": 3, "angle_total": 180.0, "axis": "Z"})
    print("6b. pattern (mode=circular):", res_pat_circ)
    assert res_pat_circ.get("ok")

    # 7. Test shell (Hollow body with top face open)
    res_box = runner.call_nx("create_cuboid", {"length": 30.0, "width": 30.0, "height": 30.0, "x": 200.0, "y": 0.0, "z": 0.0})
    box_body = res_box.get("body_id")
    print("7a. create_cuboid for shell test:", res_box)

    res_shell = runner.call_nx("shell", {"body_id": box_body, "thickness": 2.0, "faces_to_remove": [{"x": 215.0, "y": 15.0, "z": 30.0}]})
    print("7b. shell (uniform thickness=2.0mm, top face open):", res_shell)
    assert res_shell.get("ok")

    # 8. Inspect part
    res_insp = runner.call_nx("inspect_part", {})
    print("8. inspect_part:", res_insp)
    assert res_insp.get("ok")
    assert res_insp.get("body_count", 0) >= 3

    print("\n[SUCCESS] ALL PHASE 3 GENERAL PARAMETRIC OPERATIONS VERIFIED LIVE!")

if __name__ == "__main__":
    run_tests()
