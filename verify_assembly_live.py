"""
Live verification script for Fix 1 (mate_components) and Fix 2 (reposition_component)
Tests tool functions against real NX 2206 instance.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
os.environ["NX_MCP_USE_MOCK_NXOPEN"] = "0"

import atexit
from nx_mcp.bridge import runner
from nx_mcp.tools import file_ops, modeling, assembly, utility
atexit.unregister(runner.NXBridgeProcess.reset)

def run_live_test():
    print("=== LIVE ASSEMBLY MATE & REPOSITION VERIFICATION ===")
    ts = int(time.time())
    
    # 1. Create component 1
    p1_path = f"C:/Users/HP/nx-mcp/test_comp1_live_{ts}.prt"
    r1 = file_ops.create_part(p1_path)
    print("Create Part 1:", r1)
    b1 = modeling.create_cuboid(length=50.0, width=50.0, height=50.0)
    print("Cuboid 1:", b1)
    file_ops.save_part()

    # 2. Create component 2
    p2_path = f"C:/Users/HP/nx-mcp/test_comp2_live_{ts}.prt"
    r2 = file_ops.create_part(p2_path)
    print("Create Part 2:", r2)
    b2 = modeling.create_cuboid(length=30.0, width=30.0, height=30.0)
    print("Cuboid 2:", b2)
    file_ops.save_part()

    # 3. Create assembly
    assy_path = f"C:/Users/HP/nx-mcp/test_assy_live_{ts}.prt"
    r_assy = file_ops.create_part(assy_path)
    print("Create Assembly:", r_assy)

    # 4. Add components
    add1 = assembly.add_component(p1_path, 0.0, 0.0, 0.0)
    print("Add Comp 1:", add1)
    add2 = assembly.add_component(p2_path, 100.0, 0.0, 0.0)
    print("Add Comp 2:", add2)

    list_res = assembly.list_components()
    print("List components:", list_res)

    # Extract component names from list
    comp_names = [c.strip() for c in list_res.message.replace("Components:", "").split(",") if c.strip()]
    print("Parsed component names:", comp_names)
    assert len(comp_names) >= 2, f"Expected at least 2 components, got: {comp_names}"

    c1_name = comp_names[0]
    c2_name = comp_names[1]

    # 5. Test reposition_component
    repo_res = assembly.reposition_component(c2_name, 0.0, 0.0, 80.0)
    print("Reposition result:", repo_res)
    assert "Repositioned" in str(repo_res.message), f"Reposition failed: {repo_res}"

    # 6. Test mate_components (Fix 1)
    mate_res = assembly.mate_components(c1_name, "0", c2_name, "0", "Touch")
    print("Mate result:", mate_res)
    assert "Mated components" in str(mate_res.message), f"Mate failed: {mate_res}"

    print("\n[PASS] Live verification for Fix 1 (mate_components) and Fix 2 (reposition_component) SUCCEEDED!")

if __name__ == "__main__":
    run_live_test()
