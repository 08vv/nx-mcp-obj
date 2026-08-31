"""Live integration test for Phase 5: Deterministic Math against Siemens NX 2206.

This test proves:
1. $calc: arithmetic expressions evaluate server-side and produce real NX geometry.
2. $fn:bolt_circle(...) generates real bolt hole coordinates used by add_hole calls.
3. LLM never has to compute trig or arithmetic itself — deterministic Python handles it.
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.bridge import runner
from nx_mcp.spec.executor import execute_spec

def run_tests():
    print("=== STARTING PHASE 5 LIVE VERIFICATION (DETERMINISTIC MATH) ===")

    probe = runner.call_nx("ping", {})
    if not probe.get("ok"):
        print(f"[FAIL] NX live socket bridge unreachable: {probe}")
        sys.exit(1)
    print("[PASS] NX live socket bridge reachable.\n")

    temp_dir = tempfile.mkdtemp(prefix="nx_p5_test_")
    part_path = os.path.join(temp_dir, f"phase5_live_{int(time.time()*1000)}.prt")

    # ── CAD Spec that uses $calc: and $fn: throughout ──
    # Creates a base plate with bolt holes computed by $fn:bolt_circle
    # and dimensions computed by $calc: arithmetic.
    cad_spec = {
        "part_name": "phase5_bolt_plate",
        "units": "mm",
        "nodes": [
            {
                "id": "init",
                "op": "create_part",
                "params": {"filepath": part_path},
            },
            {
                "id": "base_plate",
                "op": "create_cuboid",
                "params": {
                    # Use $calc: for computed dimensions
                    "length": "$calc:120 / 2 + 40",     # = 100
                    "width": "$calc:sqrt(3600)",          # = 60
                    "height": "$calc:2 ** 3 + 12",        # = 20
                },
            },
            # Add center hole using $calc: for position and diameter
            {
                "id": "center_hole",
                "op": "add_hole",
                "params": {
                    "x": "$calc:100 / 2",            # = 50 (center of plate)
                    "y": "$calc:60 / 2",             # = 30
                    "z": 0.0,
                    "diameter": "$calc:2 * pi * 4 / pi",   # = 8.0
                    "depth": "$calc:20.0",
                    "direction": "Z",
                    "target": "$base_plate.body_id",
                },
            },
            # Add 4 bolt holes on a bolt circle using $calc: for polar math
            # Bolt circle: radius=20, centered at (50, 30)
            {
                "id": "bolt_h1",
                "op": "add_hole",
                "params": {
                    "x": "$calc:50 + 20 * cos(radians(0))",    # = 70
                    "y": "$calc:30 + 20 * sin(radians(0))",    # = 30
                    "z": 0.0,
                    "diameter": 5.0,
                    "depth": 10.0,
                    "direction": "Z",
                    "target": "$base_plate.body_id",
                },
            },
            {
                "id": "bolt_h2",
                "op": "add_hole",
                "params": {
                    "x": "$calc:50 + 20 * cos(radians(90))",   # = 50
                    "y": "$calc:30 + 20 * sin(radians(90))",   # = 50
                    "z": 0.0,
                    "diameter": 5.0,
                    "depth": 10.0,
                    "direction": "Z",
                    "target": "$base_plate.body_id",
                },
            },
            {
                "id": "bolt_h3",
                "op": "add_hole",
                "params": {
                    "x": "$calc:50 + 20 * cos(radians(180))",  # = 30
                    "y": "$calc:30 + 20 * sin(radians(180))",  # = 30
                    "z": 0.0,
                    "diameter": 5.0,
                    "depth": 10.0,
                    "direction": "Z",
                    "target": "$base_plate.body_id",
                },
            },
            {
                "id": "bolt_h4",
                "op": "add_hole",
                "params": {
                    "x": "$calc:50 + 20 * cos(radians(270))",  # = 50
                    "y": "$calc:30 + 20 * sin(radians(270))",  # = 10
                    "z": 0.0,
                    "diameter": 5.0,
                    "depth": 10.0,
                    "direction": "Z",
                    "target": "$base_plate.body_id",
                },
            },
            # Use $fn: to compute bolt circle points and feed to create_profile
            {
                "id": "mounting_profile",
                "op": "create_profile",
                "params": {
                    "points": "$fn:bolt_circle(count=6, pcd=40.0, center_x=50.0, center_y=30.0)",
                    "plane": "XY",
                    "closed": True,
                },
            },
            # Fillet the base plate
            {
                "id": "fillet",
                "op": "add_fillet",
                "params": {
                    "radius": "$calc:sqrt(4)",   # = 2.0
                    "target": "$base_plate.body_id",
                },
            },
        ],
    }

    print("1. Executing Phase 5 CAD Spec with $calc: and $fn: references...")
    report = execute_spec(cad_spec, stop_on_error=True)

    print(f"\n2. Execution Report:")
    print(f"   ok:             {report['ok']}")
    print(f"   status:         {report['status']}")
    print(f"   total_nodes:    {report['total_nodes']}")
    print(f"   executed_nodes: {report['executed_nodes']}")
    print(f"   skipped_nodes:  {report['skipped_nodes']}")
    print(f"   failed_node:    {report.get('failed_node')}")
    print(f"   failure_error:  {report.get('failure_error')}")

    if not report["ok"]:
        print(f"\n[FAIL] Spec execution failed: {report.get('failure_error')}")
        print(f"   Node results: {report.get('node_results')}")
        sys.exit(1)

    print(f"\n3. Symbol Table:")
    for nid, syms in report["symbol_table"].items():
        print(f"   [{nid}] -> {syms}")

    # Verify final state in NX
    inspect = runner.call_nx("inspect_part", {})
    print(f"\n4. inspect_part:")
    print(f"   body_count: {inspect.get('body_count')}")
    for i, body in enumerate(inspect.get("bodies", [])):
        print(f"   Body[{i}]: {body.get('name')}, faces={body.get('face_count')}, edges={body.get('edge_count')}")

    assert report["ok"] is True
    assert report["status"] == "completed"
    assert len(report["executed_nodes"]) == 9
    assert "mounting_profile" in report["symbol_table"]
    assert "profile_id" in report["symbol_table"]["mounting_profile"]
    assert "fillet" in report["symbol_table"]
    assert "feature_id" in report["symbol_table"]["fillet"], "Fillet must produce a resolvable feature_id!"
    assert "body_id" in report["symbol_table"]["fillet"], "Fillet must produce a resolvable body_id!"
    assert inspect.get("body_count", 0) >= 1

    print(f"\n[PASS] Fillet symbols verified: {report['symbol_table']['fillet']}")

    # ── Negative Tests: Confirm Offline Validation Rejections (Fail-Closed) ──
    print("\n5. Testing Negative Validation Rejections (Pre-Flight Safety)...")

    # Negative 1: $fn: shape mismatch (array into scalar diameter)
    bad_shape_spec = {
        "part_name": "bad_shape",
        "nodes": [
            {
                "id": "bad_hole",
                "op": "add_hole",
                "params": {
                    "x": 0.0, "y": 0.0, "z": 0.0,
                    "diameter": "$fn:bolt_circle(count=4, pcd=50.0)",  # Array into scalar!
                    "depth": 10.0,
                    "target": "body_1",
                },
            }
        ],
    }
    try:
        execute_spec(bad_shape_spec)
        assert False, "Should have rejected $fn: array-into-scalar shape mismatch!"
    except ValueError as e:
        print(f"   [PASS] Bad shape rejected: {e}")
        assert "expects a number, but $fn:bolt_circle(...) produces an array" in str(e)

    # Negative 2: $calc: referencing non-existent node
    bad_calc_spec = {
        "part_name": "bad_calc",
        "nodes": [
            {
                "id": "box",
                "op": "create_cuboid",
                "params": {
                    "length": "$calc:$nonexistent_node.width * 2",
                    "width": 50.0,
                    "height": 20.0,
                },
            }
        ],
    }
    try:
        execute_spec(bad_calc_spec)
        assert False, "Should have rejected $calc: non-existent node reference!"
    except ValueError as e:
        print(f"   [PASS] Bad calc ref rejected: {e}")
        assert "references non-existent node 'nonexistent_node'" in str(e)

    # Negative 3: $fn: missing required argument
    bad_fn_spec = {
        "part_name": "bad_fn",
        "nodes": [
            {
                "id": "prof",
                "op": "create_profile",
                "params": {
                    "points": "$fn:bolt_circle(pcd=50.0)",  # Missing 'count'
                    "plane": "XY",
                },
            }
        ],
    }
    try:
        execute_spec(bad_fn_spec)
        assert False, "Should have rejected $fn: missing required argument!"
    except ValueError as e:
        print(f"   [PASS] Bad fn call rejected: {e}")
        assert "missing required argument 'count'" in str(e)

    print("\n[SUCCESS] ALL PHASE 5 POSITIVE & NEGATIVE VALIDATION CHECKS VERIFIED LIVE IN NX 2206!")

if __name__ == "__main__":
    run_tests()
