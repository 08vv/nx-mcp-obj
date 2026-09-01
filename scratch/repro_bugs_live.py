"""Minimal live reproduction script for Bug 1 and Bug 2 in Siemens NX 2206."""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import nx_mcp.server  # Ensure all tools registered
from nx_mcp.bridge import runner


def test_repro():
    print("=== REPRODUCING BUGS LIVE AGAINST SIEMENS NX 2206 ===")

    # Probe socket
    probe = runner.call_nx("ping", {})
    if not probe.get("ok"):
        print(f"[FAIL] NX Bridge not reachable: {probe}")
        sys.exit(1)
    print("[PASS] Connected to Siemens NX 2206.\n")

    temp_dir = tempfile.mkdtemp(prefix="repro_")
    part_path = os.path.join(temp_dir, f"repro_{int(time.time()*1000)}.prt")
    runner.call_nx("create_part", {"filepath": part_path})

    # ── BUG 1 REPRODUCTION ──
    print("1. Reproducing Bug 1: draw_spline -> offset_curve -> close_curve_region...")
    runner.call_nx("create_sketch", {"plane": "XY"})
    pts = [
        {"x": 10.0, "y": 0.0},
        {"x": 20.0, "y": 5.0},
        {"x": 30.0, "y": 15.0},
        {"x": 40.0, "y": 30.0},
        {"x": 45.0, "y": 45.0},
    ]
    spline_res = runner.call_nx("draw_spline", {"points": pts, "degree": 3, "closed": False})
    print(f"   draw_spline result: {spline_res}")

    offset_res = runner.call_nx("offset_curve", {"curve_reference": "last", "start_width": 5.0, "end_width": 7.0})
    print(f"   offset_curve result: {offset_res}")

    close_res = runner.call_nx("close_curve_region", {"curve1": "last", "curve2": "previous", "method": "tangent_lines"})
    print(f"   close_curve_region result: {close_res}")

    # ── BUG 2 REPRODUCTION ──
    print("\n2. Reproducing Bug 2: pattern_circular -> add_fillet / get_bounding_box...")
    # Create a base disk
    cyl_res = runner.call_nx("create_cylinder", {"radius": 60.0, "height": 16.0, "axis": "Z"})
    print(f"   create_cylinder result: {cyl_res}")

    # Create a hole feature
    hole_res = runner.call_nx("add_hole", {"x": 40.0, "y": 0.0, "z": 0.0, "diameter": 8.0, "depth": 16.0, "direction": "Z"})
    print(f"   add_hole result: {hole_res}")

    # Pattern the hole feature circularly
    pat_res = runner.call_nx("pattern_circular", {"feature_name": "last", "count": 6, "angle_total": 360.0, "axis": "Z"})
    print(f"   pattern_circular result: {pat_res}")

    # Try add_fillet with body="last" or default
    fillet_res = runner.call_nx("add_fillet", {"radius": 1.0, "edges": "outer_edges"})
    print(f"   add_fillet result: {fillet_res}")

    # Try get_bounding_box with default body_reference="last"
    bbox_res = runner.call_nx("get_bounding_box", {})
    print(f"   get_bounding_box result: {bbox_res}")


if __name__ == "__main__":
    test_repro()
