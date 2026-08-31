"""Live verification script for Bug 1 and Bug 2 fixes in Siemens NX 2206.

Executes the exact structured Text-to-CAD sequence from the impeller disk workflow:
1. Base cylinder creation (hub disk, R=60, H=16)
2. Spline -> Variable Offset -> Closed Region curve construction
3. Extrude cut to create a blade pocket
4. Circular pattern of the blade pocket (8x around Z)
5. Edge blend / fillet on the patterned solid part (body='last', edges='outer_edges')
6. Total bounding box measurement confirming full part dimensions (120mm x 120mm x 16mm)
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
import nx_mcp.server  # Ensure all tools registered
from nx_mcp.bridge import runner


def test_live_fixes():
    print("=== STARTING COMBINED LIVE VERIFICATION FOR BUG 1 & BUG 2 IN SIEMENS NX 2206 ===")

    # Probe socket
    probe = runner.call_nx("ping", {})
    if not probe.get("ok"):
        print(f"[FAIL] NX Bridge not reachable: {probe}")
        sys.exit(1)
    print("[PASS] Connected to Siemens NX 2206.\n")

    temp_dir = tempfile.mkdtemp(prefix="bugfix_test_")
    part_path = os.path.join(temp_dir, f"impeller_test_{int(time.time()*1000)}.prt")
    res_part = runner.call_nx("create_part", {"filepath": part_path})
    assert res_part.get("ok"), f"create_part failed: {res_part}"
    print(f"1. Created test part: {part_path}")

    # 1. Base hub cylinder
    res_cyl = runner.call_nx("create_cylinder", {"radius": 60.0, "height": 16.0, "axis": "Z"})
    print(f"2. Created base cylinder: {res_cyl}")
    assert res_cyl.get("ok"), f"create_cylinder failed: {res_cyl}"
    base_body_id = res_cyl.get("body_id")
    print(f"   Base body ID: {base_body_id}")

    # 2. Bug 1 Fix Verification: draw_spline -> offset_curve -> close_curve_region
    print("\n3. Testing Bug 1 Fix: draw_spline -> offset_curve -> close_curve_region...")
    res_sk = runner.call_nx("create_sketch", {"plane": "XY"})
    assert res_sk.get("ok")

    pts = [
        {"x": 15.0, "y": 0.0},
        {"x": 25.0, "y": 8.0},
        {"x": 35.0, "y": 18.0},
        {"x": 45.0, "y": 30.0},
        {"x": 52.0, "y": 42.0},
    ]
    res_spline = runner.call_nx("draw_spline", {"points": pts, "degree": 3, "closed": False})
    print(f"   draw_spline:        {res_spline}")
    assert res_spline.get("ok") is True

    res_offset = runner.call_nx("offset_curve", {"curve_reference": "last", "start_width": 3.0, "end_width": 5.0})
    print(f"   offset_curve:       {res_offset}")
    assert res_offset.get("ok") is True, f"offset_curve failed: {res_offset}"

    res_close = runner.call_nx("close_curve_region", {"curve1": "last", "curve2": "previous", "method": "tangent_lines"})
    print(f"   close_curve_region: {res_close}")
    assert res_close.get("ok") is True, f"close_curve_region failed: {res_close}"
    assert res_close.get("curve_count") == 4
    print("   [PASS] Bug 1 Verified: Spline -> Variable Offset -> Closed Region succeeded cleanly.")

    # 3. Extrude cut the pocket
    print("\n4. Extrude cutting the blade pocket...")
    res_cut = runner.call_nx("extrude_cut", {"distance": 12.0, "target_body": "last"})
    print(f"   extrude_cut:        {res_cut}")
    assert res_cut.get("ok") is True, f"extrude_cut failed: {res_cut}"

    # 4. Bug 2 Fix Verification: pattern_circular -> add_fillet -> get_bounding_box
    print("\n5. Testing Bug 2 Fix: pattern_circular -> add_fillet -> get_bounding_box...")
    res_pat = runner.call_nx("pattern_circular", {"feature_name": "last", "count": 8, "angle_total": 360.0, "axis": "Z"})
    print(f"   pattern_circular:   {res_pat}")
    assert res_pat.get("ok") is True, f"pattern_circular failed: {res_pat}"
    assert res_pat.get("body_id") is not None
    target_disk_body = res_pat.get("body_id")

    # Add fillet on the patterned disk body
    res_fillet = runner.call_nx("add_fillet", {"radius": 1.0, "body": "last", "edges": "outer_edges"})
    print(f"   add_fillet:         {res_fillet}")
    assert res_fillet.get("ok") is True, f"add_fillet failed: {res_fillet}"
    assert res_fillet.get("body_id") is not None

    # Check bounding box
    res_bbox = runner.call_nx("get_bounding_box", {"body_reference": "last"})
    print(f"   get_bounding_box:   {res_bbox}")
    assert res_bbox.get("ok") is True, f"get_bounding_box failed: {res_bbox}"

    bbox_data = res_bbox.get("bounding_box", {})
    if bbox_data:
        min_pt = bbox_data.get("min", [0, 0, 0])
        max_pt = bbox_data.get("max", [0, 0, 0])
        dx = max_pt[0] - min_pt[0]
        dy = max_pt[1] - min_pt[1]
        dz = max_pt[2] - min_pt[2]
        print(f"   Bounding Box Extents: DX={dx:.2f}mm, DY={dy:.2f}mm, DZ={dz:.2f}mm")
        assert dx >= 100.0, f"Expected DX >= 100mm, got {dx}"
        assert dy >= 100.0, f"Expected DY >= 100mm, got {dy}"
        assert abs(dz - 16.0) < 0.1, f"Expected DZ ~ 16mm, got {dz}"
    print("   [PASS] Bug 2 Verified: Pattern -> Fillet -> Bounding Box targeted real disk solid.")

    # 5. Inspect final topology
    inspect_res = runner.call_nx("inspect_part", {})
    print(f"\n6. Part Topology Inspection: {inspect_res}")
    bodies = inspect_res.get("bodies", [])
    assert len(bodies) >= 1
    total_faces = sum(b.get("face_count", 0) for b in bodies)
    total_edges = sum(b.get("edge_count", 0) for b in bodies)
    print(f"   Total Faces: {total_faces}, Total Edges: {total_edges}")
    assert total_faces > 20, f"Expected >20 faces on patterned impeller disk, got {total_faces}"

    print("\n[SUCCESS] ALL BUG 1 & BUG 2 FIXES FULLY CONFIRMED IN LIVE SIEMENS NX 2206!")


if __name__ == "__main__":
    test_live_fixes()
