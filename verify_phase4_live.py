"""Live integration test for Phase 4 CAD Spec graph executor against Siemens NX 2206."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.bridge import runner
from nx_mcp.spec.executor import execute_spec

def run_tests():
    print("=== STARTING PHASE 4 LIVE CAD SPEC GRAPH VERIFICATION ===")
    
    probe = runner.call_nx("ping", {})
    if not probe.get("ok"):
        print(f"[FAIL] NX live socket bridge unreachable: {probe}")
        sys.exit(1)
    print("[PASS] NX live socket bridge reachable.")

    temp_dir = tempfile.mkdtemp(prefix="nx_p4_test_")
    part_path = os.path.join(temp_dir, f"phase4_live_{int(time.time()*1000)}.prt")

    cad_spec = {
        "part_name": "phase4_parametric_mount",
        "units": "mm",
        "nodes": [
            {
                "id": "init_part",
                "op": "create_part",
                "params": {"filepath": part_path},
            },
            {
                "id": "sec1",
                "op": "create_profile",
                "params": {
                    "points": [[0.0, 0.0], [60.0, 0.0], [60.0, 60.0], [0.0, 60.0]],
                    "plane": "XY",
                    "closed": True,
                },
            },
            {
                "id": "sec2",
                "op": "create_profile",
                "params": {
                    "points": [[10.0, 10.0, 50.0], [50.0, 10.0, 50.0], [50.0, 50.0, 50.0], [10.0, 50.0, 50.0]],
                    "plane": "XY",
                    "closed": True,
                },
            },
            {
                "id": "loft_mount",
                "op": "loft",
                "params": {
                    "profile_ids": ["$sec1.profile_id", "$sec2.profile_id"],
                    "body_type": "solid",
                },
            },
            {
                "id": "center_cut",
                "op": "add_hole",
                "params": {
                    "x": 30.0,
                    "y": 30.0,
                    "z": 0.0,
                    "diameter": 12.0,
                    "depth": 20.0,
                    "direction": "Z",
                    "target": "$loft_mount.body_id",
                },
            },
            {
                "id": "hole_pattern",
                "op": "pattern",
                "params": {
                    "feature_ref": "$center_cut.feature_id",
                    "mode": "circular",
                    "count": 4,
                    "angle_total": 360.0,
                    "axis": "Z",
                },
            },
            {
                "id": "shell_mount",
                "op": "shell",
                "params": {
                    "body_id": "$loft_mount.body_id",
                    "thickness": 2.0,
                    "faces_to_remove": [{"x": 30.0, "y": 30.0, "z": 50.0}],
                },
            },
        ],
    }

    print("\n1. Executing CAD Spec via execute_spec()...")
    report = execute_spec(cad_spec, stop_on_error=True)
    print("Execution Report:", report)

    assert report["ok"] is True, f"Spec execution failed: {report.get('failure_error')}"
    assert report["status"] == "completed"
    assert len(report["executed_nodes"]) == 7
    assert report["skipped_nodes"] == []

    # Verify symbol resolution across graph
    symbols = report["symbol_table"]
    print("\n2. Resolved Symbol Table:")
    for node_id, node_syms in symbols.items():
        print(f"   [{node_id}] -> {node_syms}")

    assert "loft_mount" in symbols and "body_id" in symbols["loft_mount"]
    assert "center_cut" in symbols and "feature_id" in symbols["center_cut"]
    assert "shell_mount" in symbols and "feature_id" in symbols["shell_mount"]

    # Verify final part inspection in NX
    res_inspect = runner.call_nx("inspect_part", {})
    print("\n3. Final inspect_part:", res_inspect)
    assert res_inspect.get("ok")
    assert res_inspect.get("body_count", 0) >= 1

    print("\n[SUCCESS] PHASE 4 CAD SPEC GRAPH EXECUTOR FULLY VERIFIED LIVE IN NX 2206!")

if __name__ == "__main__":
    run_tests()
