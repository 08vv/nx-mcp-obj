"""
Real-machine verification of core solid modeling tool fixes.
Tests feature/body resolution, mirror, pattern, boolean subtraction, list_features, and set_view against real live NX.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from nx_mcp.tools import modeling, utility, measure, file_ops

def run_step(step_name, func, *args, **kwargs):
    print(f"\n--- [RUNNING] {step_name} ---")
    try:
        res = func(*args, **kwargs)
        print(f"Status: {res.__class__.__name__}")
        print(f"Result message: {getattr(res, 'message', '') or getattr(res, 'error', '')}")
        return res
    except Exception as e:
        print(f"Exception: {e}")
        return None

def main():
    # Make sure we use the real NX, not the mock
    os.environ["NX_MCP_USE_MOCK_NXOPEN"] = "0"
    
    # Delete existing part to avoid 'File already exists' error
    part_path = "c:/Users/HP/nx-mcp/verify_solid.prt"
    if os.path.exists(part_path):
        try:
            os.remove(part_path)
            print(f"Deleted existing part: {part_path}")
        except Exception as e:
            print(f"Could not remove existing part: {e}")

    # 1. Reset/Clean slate
    run_step("Reset NX Bridge", utility.reset_nx_bridge)
    time.sleep(2)
    
    # 2. Create target part and base body
    run_step("Create Part", file_ops.create_part, part_path)
    time.sleep(2)
    
    # Create base block
    cube_res = run_step("Create Cuboid (Target)", modeling.create_cuboid, 50.0, 50.0, 50.0, 0.0, 0.0, 0.0)
    print("Cube Details:", cube_res)
    
    # List features
    run_step("List Features (should show Cuboid)", utility.list_features)
    
    # 3. Add a hole to mirror/pattern (on the top face of the cuboid, Z=50)
    # The cuboid is the target body
    hole_res = run_step("Add Hole", modeling.add_hole, 10.0, 10.0, 50.0, 5.0, 10.0, target="last", direction="-Z")
    
    # List features to see the hole name (should show Cuboid & Hole)
    run_step("List Features after Hole", utility.list_features)
    
    # 4. Mirror the hole across the YZ plane
    # The hole is represented by the subtract feature 'Subtract(2)'
    run_step("Mirror Feature (subtract_2 across YZ)", modeling.mirror_feature, "subtract_2", "YZ")
    
    # 5. Pattern the hole along X direction
    run_step("Pattern Feature (subtract_2 along X)", modeling.pattern_feature, "subtract_2", "X", 3, 10.0)
    
    # 6. Create a cylinder to subtract
    cyl_res = run_step("Create Cylinder (Tool)", modeling.create_cylinder, 15.0, 60.0, 25.0, 25.0, 0.0, "Z")
    
    # List features again
    run_step("List Features (should show Cuboid, Hole, Mirror, Pattern, Cylinder)", utility.list_features)
    
    # Get bounding box to check body references
    run_step("Get Bounding Box (last)", measure.get_bounding_box, "last")
    
    # 7. Perform boolean subtract
    # Subtract cylinder from cuboid (using names "last" and "block_0")
    print("\nAttempting Boolean Subtract of Cylinder from Cuboid...")
    sub_res = run_step("Boolean Subtract (last from block_0)", modeling.boolean_subtract, "block_0", "last")
    
    # 8. Set views
    run_step("Set View to TOP", utility.set_view, "TOP")
    time.sleep(1)
    run_step("Set View to FRONT", utility.set_view, "FRONT")
    time.sleep(1)
    run_step("Set View to ISO", utility.set_view, "ISO")
    
    print("\n--- Verification Completed ---")

if __name__ == "__main__":
    main()
