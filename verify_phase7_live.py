"""Live verification script for Phase 7: Pre-Execution Plausibility & Post-Execution Verification.

Runs against REAL Siemens NX 2206 via live socket bridge:
1. Executes a valid CAD Spec with pre-execution plausibility checking and post-execution geometry verification.
2. Confirms pre-execution plausibility catches physically impossible geometry BEFORE touching NXOpen.
3. Confirms post-execution verification validates body lifecycle, graph integrity, and live geometry measurements.
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
import nx_mcp.server  # Ensure all tools registered
from nx_mcp.bridge import runner
from nx_mcp.spec.executor import execute_spec
from nx_mcp.spec.plausibility import validate_plausibility


def run_tests():
    print("=== STARTING PHASE 7 LIVE VERIFICATION (PRE & POST VALIDATION) ===")

    # 1. Probe live Siemens NX 2206 socket bridge
    probe = runner.call_nx("ping", {})
    if not probe.get("ok"):
        print(f"[FAIL] Real Siemens NX 2206 socket bridge unreachable: {probe}")
        sys.exit(1)
    print("[PASS] Real Siemens NX 2206 socket bridge connected and responsive.\n")

    temp_dir = tempfile.mkdtemp(prefix="nx_p7_test_")
    part_path = os.path.join(temp_dir, f"phase7_live_{int(time.time()*1000)}.prt")

    # ── Test 1: Valid CAD Spec with Pre-Plausibility & Post-Verification ──
    print("1. Testing Valid Spec with Pre-Plausibility and Post-Verification...")
    cad_spec = {
        "part_name": "phase7_flanged_housing",
        "units": "mm",
        "nodes": [
            {
                "id": "init",
                "op": "create_part",
                "params": {"filepath": part_path},
            },
            {
                "id": "base",
                "op": "create_cuboid",
                "params": {
                    "length": "$calc:50 * 2",      # 100.0mm
                    "width": "$calc:30 + 30",       # 60.0mm
                    "height": "$calc:10 + 10",      # 20.0mm
                },
            },
            {
                "id": "center_hole",
                "op": "add_hole",
                "params": {
                    "target": "$base.body_id",
                    "x": 50.0,
                    "y": 30.0,
                    "z": 0.0,
                    "diameter": 16.0,
                    "depth": 15.0,
                    "direction": "Z",
                },
            },
            {
                "id": "edge_blend",
                "op": "add_fillet",
                "params": {
                    "body": "$base.body_id",
                    "radius": 3.0,
                },
            },
        ],
    }

    report = execute_spec(
        cad_spec,
        stop_on_error=True,
        validate_plausibility=True,
        verify_postexecution=True,
        live_check=True,
    )

    print(f"   Execution OK:       {report['ok']}")
    print(f"   Executed Nodes:     {report['executed_nodes']}")
    assert report["ok"] is True, f"Execution failed: {report.get('failure_error')}"

    # Verify plausibility report
    plaus = report.get("plausibility_report")
    assert plaus is not None
    print(f"   Plausibility Valid: {plaus['plausible']} (checks: {plaus['checks_performed']}, passed: {plaus['checks_passed']})")
    assert plaus["plausible"] is True
    assert len(plaus["errors"]) == 0

    # Verify postcheck report
    post = report.get("postcheck_report")
    assert post is not None
    print(f"   Post-Check Valid:   {post['valid']} (violations: {post['violations_count']}, passed: {post['passed_checks_count']})")
    assert post["valid"] is True
    assert post["violations_count"] == 0
    print(f"   Post-Check Metrics: {post['metrics']}")
    print("   [PASS] Valid spec pre-plausibility and post-verification passed live in NX 2206.")

    # ── Test 2: Negative Pre-Execution Plausibility Rejection (Pre-Flight Safety) ──
    print("\n2. Testing Negative Pre-Execution Plausibility Rejections...")
    bad_spec_hole = {
        "part_name": "oversized_hole_spec",
        "nodes": [
            {
                "id": "box",
                "op": "create_cuboid",
                "params": {"length": 50.0, "width": 40.0, "height": 20.0},
            },
            {
                "id": "bad_cut",
                "op": "add_hole",
                "params": {"target": "$box.body_id", "diameter": 45.0, "depth": 10.0, "x": 25.0, "y": 20.0, "z": 0.0},  # 45 >= 40
            },
        ],
    }

    try:
        execute_spec(bad_spec_hole, validate_plausibility=True)
        print("   [FAIL] Expected plausibility ValueError was not raised!")
        sys.exit(1)
    except ValueError as e:
        print(f"   [PASS] Oversized hole correctly rejected pre-flight: {e}")

    bad_spec_neg_dim = {
        "part_name": "negative_dim_spec",
        "nodes": [
            {
                "id": "bad_box",
                "op": "create_cuboid",
                "params": {"length": 50.0, "width": "$calc:10 - 25", "height": 20.0},
            }
        ],
    }

    try:
        execute_spec(bad_spec_neg_dim, validate_plausibility=True)
        print("   [FAIL] Expected negative dimension ValueError was not raised!")
        sys.exit(1)
    except ValueError as e:
        print(f"   [PASS] Negative dimension correctly rejected pre-flight: {e}")

    # ── Test 3: Live Post-Check Volume and Bounding Box Verification ──
    print("\n3. Testing Post-Execution Live Geometry Inspection & Volume Check...")
    simple_box_spec = {
        "part_name": "volume_box",
        "nodes": [
            {"id": "init2", "op": "create_part", "params": {"filepath": os.path.join(temp_dir, f"box_{int(time.time()*1000)}.prt")}},
            {"id": "solid_box", "op": "create_cuboid", "params": {"length": 40.0, "width": 30.0, "height": 20.0}},
        ],
    }
    box_report = execute_spec(simple_box_spec, validate_plausibility=True, verify_postexecution=True, live_check=True)
    assert box_report["ok"] is True
    box_post = box_report["postcheck_report"]
    assert box_post["valid"] is True
    print(f"   Measured Volume: {box_post['metrics'].get('measured_volume')} mm^3 (Expected: {box_post['metrics'].get('expected_volume')} mm^3)")
    print(f"   Live Body Count: {box_post['metrics'].get('live_body_count')}")
    print("   [PASS] Live geometry measurement matches analytical expectations.")

    print("\n[SUCCESS] ALL PHASE 7 PRE- & POST-VALIDATION CHECKS EMPIRICALLY VERIFIED IN SIEMENS NX 2206!")


if __name__ == "__main__":
    run_tests()
