"""
Step 5 Verification script: Run inspect_part on the generated plate model.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import os
os.environ["NX_MCP_USE_MOCK_NXOPEN"] = "0"

from nx_mcp.tools import modeling, utility, recipe, measure, file_ops

def main():
    part_path = "c:/Users/HP/nx-mcp/plate_step5_final.prt"
    if os.path.exists(part_path):
        try: os.remove(part_path)
        except Exception: pass
        
    utility.reset_nx_bridge()
    file_ops.create_part(part_path)
    
    recipe_steps = [
        {"tool": "create_cylinder", "args": {"radius": 50.0, "height": 10.0, "x": 0.0, "y": 0.0, "z": 0.0, "direction": "Z"}},
        {"tool": "add_hole", "args": {"x": 0.0, "y": 0.0, "z": 10.0, "diameter": 20.0, "depth": 10.0, "target": "last", "direction": "-Z"}},
        {"tool": "add_hole", "args": {"x": 35.0, "y": 0.0, "z": 10.0, "diameter": 8.0, "depth": 10.0, "target": "last", "direction": "-Z"}},
        {"tool": "pattern_circular", "args": {"feature_name": "last", "axis": "Z", "count": 8, "angle_total": 360.0}},
        {"tool": "add_fillet", "args": {"radius": 2.0, "body": "last", "edges": "outer_edges"}}
    ]
    
    print("=== Running Full Recipe ===")
    t0 = time.time()
    res = recipe.run_recipe(recipe_steps)
    dt = time.time() - t0
    print(f"run_recipe completed in {dt:.3f}s")
    print("Recipe Result:", res)
    
    print("\n=== Inspecting Part ===")
    inspect_res = inspect_part()
    print("Inspect Part Result:", inspect_res)
    
    bbox_res = measure.get_bounding_box("last")
    print("Bounding Box Result:", bbox_res)

def inspect_part():
    from nx_mcp.bridge import runner
    return runner.call_nx("inspect_part", {})

if __name__ == "__main__":
    main()
