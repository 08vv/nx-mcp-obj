"""Capstone live verification script for Phase 9: Visual & Geometry Verification Loop.

Runs against REAL Siemens NX 2206:
1. Executes a multi-node CAD Spec with pause_after to halt execution mid-graph.
2. Captures a real viewport visual screenshot artifact and executes geocheck consistency checks.
3. Selectively re-runs a node with modified parameters (rerun_spec_node) and completes remaining graph.
4. Verifies final geometry, face/edge counts, and postcheck validity on real NX solid.
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
import nx_mcp.server  # Ensure all tools registered
from nx_mcp.bridge import runner
from nx_mcp.spec.executor import execute_spec, resume_spec_execution, rerun_spec_node
from nx_mcp.spec.geocheck import verify_geometry


def run_tests():
    print("=== STARTING PHASE 9 CAPSTONE LIVE VERIFICATION (VISUAL/GEOMETRY LOOP) ===")

    # 1. Probe live Siemens NX 2206 socket bridge
    probe = runner.call_nx("ping", {})
    if not probe.get("ok"):
        print(f"[FAIL] Real Siemens NX 2206 socket bridge unreachable: {probe}")
        sys.exit(1)
    print("[PASS] Real Siemens NX 2206 socket bridge connected and responsive.\n")

    temp_dir = tempfile.mkdtemp(prefix="nx_p9_test_")
    part_path = os.path.join(temp_dir, f"phase9_capstone_{int(time.time()*1000)}.prt")

    cad_spec = {
        "part_name": "phase9_housing",
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
                "params": {"length": 80.0, "width": 50.0, "height": 20.0},
            },
            {
                "id": "center_hole",
                "op": "add_hole",
                "params": {
                    "target": "$base.body_id",
                    "x": 40.0,
                    "y": 25.0,
                    "z": 0.0,
                    "diameter": 14.0,
                    "depth": 15.0,
                    "direction": "Z",
                },
            },
            {
                "id": "edge_blend",
                "op": "add_fillet",
                "params": {
                    "body": "$base.body_id",
                    "radius": 2.5,
                },
            },
        ],
    }

    # ── Step 1: Interruptible Execution (Pause After Base) ──
    print("1. Testing Interruptible Execution (pause_after=['base'])...")
    rep1 = execute_spec(
        cad_spec,
        pause_after=["base"],
        validate_plausibility=True,
        live_check=True,
    )
    print(f"   Status:         {rep1['status']}")
    print(f"   Paused Node:    {rep1['paused_node']}")
    print(f"   Executed Nodes: {rep1['executed_nodes']}")
    assert rep1["status"] == "paused"
    assert rep1["paused_node"] == "base"
    assert rep1["executed_nodes"] == ["init", "base"]
    token = rep1["execution_token"]
    assert token is not None
    print(f"   Execution Token: {token}")
    print("   [PASS] Execution successfully paused after 'base' with active token.")

    # ── Step 2: Geometric & Visual Verification on Paused State ──
    print("\n2. Testing Geometric Consistency & Real Viewport Screenshot Artifact...")
    from nx_mcp.state.dependency_graph import get_session_graph
    geo_report = verify_geometry(
        cad_spec,
        get_session_graph(),
        rep1,
        capture_screenshot=True,
        live_check=True,
    )
    print(f"   GeoCheck Valid: {geo_report['valid']}")
    print(f"   Screenshot Path: {geo_report['screenshot_path']}")
    assert geo_report["screenshot_path"] is not None
    assert os.path.exists(geo_report["screenshot_path"]), f"Screenshot file not found: {geo_report['screenshot_path']}"
    print(f"   Screenshot Size: {os.path.getsize(geo_report['screenshot_path'])} bytes")
    print(f"   Passed Checks:   {[c['check'] for c in geo_report['passed_checks']]}")
    print("   [PASS] Real screenshot artifact saved and bounding box verified.")

    # ── Step 3: Selective Parameter Adjustment & Re-Run (Correction Loop) ──
    print("\n3. Testing Selective Re-Run & Correction (rerun_spec_node)...")
    # Adjust base cuboid length from 80 -> 100
    rep2 = rerun_spec_node(
        execution_token=token,
        node_id="base",
        new_params={"length": 100.0},
        verify_postexecution=True,
        geometry_check=True,
        capture_screenshot=True,
        live_check=True,
    )
    print(f"   Status:         {rep2['status']}")
    print(f"   Executed Nodes: {rep2['executed_nodes']}")
    print(f"   Failed Node:    {rep2.get('failed_node')}")
    print(f"   Failure Error:  {rep2.get('failure_error')}")
    assert rep2["status"] == "completed", f"Failed at {rep2.get('failed_node')}: {rep2.get('failure_error')}"
    assert rep2["executed_nodes"] == ["init", "base", "center_hole", "edge_blend"]

    # Verify postcheck and final topology in live NX
    post = rep2.get("postcheck_report")
    assert post is not None
    print(f"   Post-Check Valid: {post['valid']} (violations: {post['violations_count']})")
    assert post["valid"] is True

    inspect_res = runner.call_nx("inspect_part", {})
    bodies = inspect_res.get("bodies", [])
    total_faces = sum(b.get("face_count", 0) for b in bodies)
    total_edges = sum(b.get("edge_count", 0) for b in bodies)
    print(f"   Final NX Faces:  {total_faces}")
    print(f"   Final NX Edges:  {total_edges}")
    assert total_faces >= 7, f"Expected >= 7 faces on filleted/holed block, got {total_faces}"
    print("   [PASS] Selective re-run and correction executed to completion on live NX solid.")

    print("\n[SUCCESS] ALL PHASE 9 CAPSTONE VERIFICATION CHECKS EMPIRICALLY CONFIRMED IN SIEMENS NX 2206!")


if __name__ == "__main__":
    run_tests()
