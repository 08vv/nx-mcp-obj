import os
import sys
import tempfile
from pathlib import Path

# Ensure runner doesn't kill ugraf on script exit
from nx_mcp.bridge import runner
import atexit
atexit.unregister(runner.NXBridgeProcess.reset)

def run_tests():
    print("=== STARTING PHASE 1 LIVE NX 2206 VERIFICATION ===")
    
    # Pre-check live bridge connection
    if not runner._wait_for_socket(runner.LIVE_PORT, timeout=20):
        print("[FAIL] NX live socket bridge is not reachable on port 43210.")
        sys.exit(1)
    print("[PASS] NX live socket bridge reachable.")

    tmp_dir = Path(tempfile.mkdtemp(prefix="nx_phase1_test_"))
    print(f"Working in temp directory: {tmp_dir}")

    import time
    ts = int(time.time() * 1000)
    # TEST 1: Part creation & Bounded Plane / Base surface
    p1_path = str(tmp_dir / f"surf_test_{ts}.prt")
    res = runner.call_nx("create_part", {"filename": p1_path})
    print("create_part:", res)
    assert res.get("ok"), f"create_part failed: {res}"

    res = runner.call_nx("create_base_surface", {"plane": "XY", "width": 60.0, "height": 40.0})
    print("create_base_surface:", res)
    assert res.get("ok"), f"create_base_surface failed: {res}"

    # TEST 2: Studio Surface (SectionList in NX 2206)
    p2_path = str(tmp_dir / f"studio_surf_test_{ts}.prt")
    res = runner.call_nx("create_part", {"filename": p2_path})
    assert res.get("ok"), f"create_part failed: {res}"

    # Section 1
    res = runner.call_nx("create_sketch", {"plane": "XY"})
    assert res.get("ok")
    res = runner.call_nx("draw_line", {"x1": 0.0, "y1": 0.0, "x2": 50.0, "y2": 0.0})
    assert res.get("ok")

    # Section 2 on offset plane
    res = runner.call_nx("create_sketch", {"plane": "XZ"})
    assert res.get("ok")
    res = runner.call_nx("draw_line", {"x1": 0.0, "y1": 30.0, "x2": 50.0, "y2": 30.0})
    assert res.get("ok")

    # Create studio surface between the two curves
    res = runner.call_nx("studio_surface", {"section1": "previous", "section2": "last"})
    print("studio_surface:", res)
    assert res.get("ok"), f"studio_surface failed: {res}"

    # TEST 3: Offset Datum Plane validation & creation
    res = runner.call_nx("create_offset_plane", {"base_plane": "XY", "offset": 0.0})
    print("create_offset_plane offset=0.0:", res)
    assert not res.get("ok"), "Expected error for offset=0.0"

    res = runner.call_nx("create_offset_plane", {"base_plane": "XY", "offset": 25.0})
    print("create_offset_plane offset=25.0:", res)
    assert res.get("ok"), f"create_offset_plane failed: {res}"

    # TEST 4: Export directory validation
    bad_step = r"C:\non_existent_dir_12345\test.stp"
    res = runner.call_nx("export_step", {"output_path": bad_step})
    print("export_step bad dir:", res)
    assert not res.get("ok"), "Expected error when export directory does not exist"

    bad_stl = r"C:\non_existent_dir_12345\test.stl"
    res = runner.call_nx("export_stl", {"output_path": bad_stl})
    print("export_stl bad dir:", res)
    assert not res.get("ok"), "Expected error when export directory does not exist"

    # TEST 5: Assembly Component Positioning & Mating
    comp1_path = str(tmp_dir / f"comp1_{ts}.prt")
    comp2_path = str(tmp_dir / f"comp2_{ts}.prt")
    assy_path = str(tmp_dir / f"assembly_{ts}.prt")

    # Build component 1
    res = runner.call_nx("create_part", {"filename": comp1_path})
    assert res.get("ok")
    res = runner.call_nx("create_cuboid", {"length": 40.0, "width": 40.0, "height": 40.0, "x": 0.0, "y": 0.0, "z": 0.0})
    assert res.get("ok")
    res = runner.call_nx("save_part", {})
    assert res.get("ok")

    # Build component 2
    res = runner.call_nx("create_part", {"filename": comp2_path})
    assert res.get("ok")
    res = runner.call_nx("create_cuboid", {"length": 20.0, "width": 20.0, "height": 20.0, "x": 0.0, "y": 0.0, "z": 0.0})
    assert res.get("ok")
    res = runner.call_nx("save_part", {})
    assert res.get("ok")

    # Assemble
    res = runner.call_nx("create_part", {"filename": assy_path})
    assert res.get("ok")
    res = runner.call_nx("add_component", {"part_path": comp1_path, "component_name": "BLOCK1", "x": 0.0, "y": 0.0, "z": 0.0})
    print("add_component BLOCK1:", res)
    assert res.get("ok")

    res = runner.call_nx("add_component", {"part_path": comp2_path, "component_name": "BLOCK2", "x": 100.0, "y": 100.0, "z": 0.0})
    print("add_component BLOCK2:", res)
    assert res.get("ok")

    # Reposition BLOCK2
    res = runner.call_nx("reposition_component", {"component_name": "BLOCK2", "delta_x": -50.0, "delta_y": -50.0, "delta_z": 10.0})
    print("reposition_component BLOCK2:", res)
    assert res.get("ok"), f"reposition_component failed: {res}"

    # Mate BLOCK1 and BLOCK2
    res = runner.call_nx("mate_components", {
        "comp1": "BLOCK1",
        "face1": 0,
        "comp2": "BLOCK2",
        "face2": 0,
        "constraint_type": "Touch"
    })
    print("mate_components BLOCK1 & BLOCK2:", res)
    assert res.get("ok"), f"mate_components failed: {res}"

    # TEST 6: Rollback on invalid command
    res = runner.call_nx("create_cuboid", {"length": -10.0, "width": 20.0, "height": 20.0, "x": 0.0, "y": 0.0, "z": 0.0})
    print("invalid command rollback test:", res)
    assert not res.get("ok"), "Expected failure on negative length"

    print("\n[SUCCESS] ALL PHASE 1 LIVE VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
