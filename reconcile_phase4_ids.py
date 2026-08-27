"""Phase 4 body ID reconciliation: re-run the exact Phase 4 live spec and reconcile
every body_id in the symbol table against what NX actually reports via inspect_part."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from nx_mcp.bridge import runner
from nx_mcp.spec.executor import execute_spec

def run_reconciliation():
    print("=== PHASE 4 BODY-ID RECONCILIATION ===\n")

    probe = runner.call_nx("ping", {})
    if not probe.get("ok"):
        print(f"[FAIL] NX bridge unreachable: {probe}")
        sys.exit(1)
    print("[OK] NX bridge reachable.\n")

    temp_dir = tempfile.mkdtemp(prefix="nx_p4_recon_")
    part_path = os.path.join(temp_dir, f"recon_{int(time.time()*1000)}.prt")

    # Exact Phase 4 spec: create_part -> profile x2 -> loft -> hole -> shell -> pattern
    cad_spec = {
        "part_name": "reconciliation_test",
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
                    "x": 30.0, "y": 30.0, "z": 0.0,
                    "diameter": 12.0, "depth": 20.0,
                    "direction": "Z",
                    "target": "$loft_mount.body_id",
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
        ],
    }

    print("1. Executing exact Phase 4 CAD Spec...")
    report = execute_spec(cad_spec, stop_on_error=True)
    assert report["ok"], f"Spec failed: {report.get('failure_error')}"
    print(f"   Status: {report['status']}")
    print(f"   Executed: {report['executed_nodes']}\n")

    print("2. Symbol table (per-node resolved IDs):")
    for nid, syms in report["symbol_table"].items():
        print(f"   [{nid}] -> {syms}")

    print("\n3. inspect_part (full NX body listing):")
    inspect = runner.call_nx("inspect_part", {})
    print(f"   ok={inspect.get('ok')}, body_count={inspect.get('body_count')}")
    for i, body in enumerate(inspect.get("bodies", [])):
        print(f"   Body[{i}]: name='{body.get('name')}', faces={body.get('face_count')}, edges={body.get('edge_count')}")

    # Now reconcile
    sym_body_ids = set()
    for nid, syms in report["symbol_table"].items():
        if "body_id" in syms:
            sym_body_ids.add(syms["body_id"])
        if "body_ids" in syms:
            for bid in syms["body_ids"]:
                sym_body_ids.add(bid)

    print(f"\n4. RECONCILIATION:")
    print(f"   Symbol table body IDs: {sorted(sym_body_ids)}")
    print(f"   NX actual body count:  {inspect.get('body_count')}")
    print(f"   NX body names:         {[b.get('name') for b in inspect.get('bodies', [])]}")

    # Check bridge state for full body registry
    state = runner.call_nx("inspect_api", {"target": "state"})
    if state.get("ok") and "bodies" in str(state):
        print(f"   Bridge _state bodies: {state}")

    print("\n[DONE] Reconciliation complete.")

if __name__ == "__main__":
    run_reconciliation()
