import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from nx_mcp.bridge.runner import call_nx

def run_step(step_name, tool, args):
    print(f"=== Running: {step_name} ({tool}) ===")
    print(f"Args: {json.dumps(args)}")
    res = call_nx(tool, args)
    print(f"Result: {json.dumps(res, indent=2)}")
    if not res.get("ok"):
        raise RuntimeError(f"Step failed: {step_name} -> {res}")
    return res

def main():
    # 1. Create part
    part_path = str(Path(__file__).parent / "verify_spline_pocket.prt")
    if os.path.exists(part_path):
        try:
            os.remove(part_path)
        except Exception:
            pass
    run_step("Create Part", "create_part", {"filename": part_path})

    # 2. Create Base Solid Body (Cuboid 120 x 80 x 30 centered)
    run_step("Create Cuboid", "create_cuboid", {
        "length": 120.0,
        "width": 80.0,
        "height": 30.0,
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
        "centered": True
    })

    # 3. Create Sketch on Top Face (Z = 15.0)
    run_step("Create Sketch", "create_sketch", {
        "plane": "XY",
        "z_offset": 15.0
    })

    # 4. Draw first dummy line curve (to ensure sketch has multiple curves)
    run_step("Draw Line 1", "draw_line", {
        "x1": -45.0,
        "y1": -25.0,
        "x2": -45.0,
        "y2": 25.0
    })

    # 5. Draw second dummy line curve
    run_step("Draw Line 2", "draw_line", {
        "x1": 45.0,
        "y1": -25.0,
        "x2": 45.0,
        "y2": 25.0
    })

    # 6. Draw Spline with DICT/OBJECT-STYLE points (simulating AI client)
    run_step("Draw Spline (Object Points)", "draw_spline", {
        "points": [
            {"x": -25.0, "y": 0.0},
            {"x": -10.0, "y": 14.0},
            {"x": 10.0, "y": -14.0},
            {"x": 25.0, "y": 0.0}
        ],
        "degree": 3,
        "closed": False,
        "plane": "active"
    })

    # 7. Offset Curve with multi-curve sketch present
    run_step("Offset Curve", "offset_curve", {
        "curve_reference": "last",
        "start_width": 6.0,
        "end_width": 12.0,
        "side": "left"
    })

    # 8. Close Curve Region
    run_step("Close Curve Region", "close_curve_region", {
        "curve1": "last",
        "curve2": "previous",
        "method": "tangent_lines"
    })

    # 9. Extrude Cut (distance=10mm)
    run_step("Extrude Cut", "extrude_cut", {
        "distance": 10.0,
        "target": "last"
    })

    # 10. Save Part
    run_step("Save Part", "save_part", {})

    # 11. Inspect Part (features & volume)
    inspect_res = run_step("Inspect Part", "inspect_part", {})
    print("=== INSPECT PART OUTPUT ===")
    print(json.dumps(inspect_res, indent=2))

    # 12. Take Screenshot
    screenshot_path = str(Path(__file__).parent / "spline_pocket_live_verified.png")
    run_step("Take Screenshot", "take_screenshot", {"output_path": screenshot_path})
    print(f"Screenshot saved to: {screenshot_path}")

if __name__ == "__main__":
    main()
