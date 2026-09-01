"""
Benchmark the exact plate build recipe via run_recipe and individual tool timings.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import os
os.environ["NX_MCP_USE_MOCK_NXOPEN"] = "0"

from nx_mcp.tools import modeling, utility, recipe, measure, file_ops

def test_individual_steps():
    print("=== Testing Individual Step Timings ===")
    part_path = "c:/Users/HP/nx-mcp/plate_recipe_test.prt"
    if os.path.exists(part_path):
        try: os.remove(part_path)
        except Exception: pass
        
    utility.reset_nx_bridge()
    file_ops.create_part(part_path)
    
    steps = [
        ("create_cylinder", lambda: modeling.create_cylinder(radius=50.0, height=10.0, x=0.0, y=0.0, z=0.0, direction="Z")),
        ("center_hole", lambda: modeling.add_hole(x=0.0, y=0.0, z=10.0, diameter=20.0, depth=10.0, target="last", direction="-Z")),
        ("bolt_hole", lambda: modeling.add_hole(x=35.0, y=0.0, z=10.0, diameter=8.0, depth=10.0, target="last", direction="-Z")),
        ("pattern_circular", lambda: modeling.pattern_circular(feature_name="last", axis="Z", count=8, angle_total=360.0)),
        ("add_fillet", lambda: modeling.add_fillet(radius=2.0, body="last", edges="outer_edges"))
    ]
    
    timings = {}
    for name, fn in steps:
        t0 = time.time()
        print(f"\n[START] {name}...")
        try:
            res = fn()
            dt = time.time() - t0
            timings[name] = dt
            print(f"[DONE] {name} in {dt:.3f}s: {res}")
        except Exception as e:
            dt = time.time() - t0
            timings[name] = dt
            print(f"[FAIL] {name} in {dt:.3f}s: {e}")
            
    print("\nIndividual Timings Summary:", timings)
    return timings

def test_full_run_recipe():
    print("\n=== Testing Full run_recipe Call ===")
    part_path = "c:/Users/HP/nx-mcp/plate_recipe_full.prt"
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
    
    t0 = time.time()
    res = recipe.run_recipe(recipe_steps)
    dt = time.time() - t0
    print(f"run_recipe finished in {dt:.3f}s")
    print("Result:", res)

if __name__ == "__main__":
    test_individual_steps()
    test_full_run_recipe()
