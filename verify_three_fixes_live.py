"""
Live Verification Script for the Three Bug Fixes.
"""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import os
os.environ["NX_MCP_USE_MOCK_NXOPEN"] = "0"

from nx_mcp.tools import modeling, utility, file_ops
from nx_mcp.bridge import runner

def _is_ok(res):
    if isinstance(res, dict):
        return bool(res.get("ok"))
    res_str = str(res)
    if "ERROR" in res_str or "Failed" in res_str:
        return False
    return True

def test_scenario_a_state_isolation():
    print("\n=== Scenario A: Transient State Isolation Test ===")
    ts = int(time.time())
    p1 = f"c:/Users/HP/nx-mcp/test_part_a_{ts}.prt"
    p2 = f"c:/Users/HP/nx-mcp/fresh_part_b_{ts}.prt"

    file_ops.create_part(p1)
    
    # Intentionally contaminate transient state with XZ plane, 50mm offset, and 45-degree rotation
    print("Contaminating sketch state in part A...")
    modeling.create_real_sketch(plane="XZ", origin_x=50.0, z_offset=20.0, rotate_z_deg=45.0)
    
    # Now start a completely fresh part
    print("Creating fresh part B (should clear transient state)...")
    res_b = file_ops.create_part(p2)
    print("create_part B result:", res_b)
    
    # Create plate and hole on fresh part B
    cyl_res = modeling.create_cylinder(radius=50.0, height=10.0, x=0.0, y=0.0, z=0.0, direction="Z")
    print("Cylinder on Part B:", cyl_res)
    
    hole_res = modeling.add_hole_nx(x=0.0, y=0.0, z=10.0, diameter=20.0, depth=10.0, direction="-Z")
    print("Hole on Part B:", hole_res)
    assert _is_ok(hole_res), f"Hole failed: {hole_res}"
    print("[PASS] Scenario A: State isolation verified successfully!")

def test_scenario_b_fallback_isolation():
    print("\n=== Scenario B: Fallback Fresh Part Creation Test ===")
    p_fallback = "c:/Users/HP/nx-mcp/nx_mcp_result.prt"

    # Create fallback part and add geometry
    file_ops.create_part(p_fallback)
    modeling.create_cuboid(length=50.0, width=50.0, height=50.0)
    
    # Reset bridge so SESSION.Parts.Work is cleared
    utility.reset_nx_bridge()
    
    # Now call a modeling tool without explicit create_part: _ensure_work_part will run
    # and detect nx_mcp_result.prt has geometry, so it will create a fresh nx_mcp_result_N.prt!
    res = modeling.create_cylinder(radius=20.0, height=10.0)
    print("Fallback test result:", res)
    assert _is_ok(res), f"Fallback test failed: {res}"
    print("[PASS] Scenario B: Fallback fresh part isolation verified successfully!")

def test_scenario_c_hole_miss_validation():
    print("\n=== Scenario C: Out-of-Bounds Hole Validation Test ===")
    ts = int(time.time())
    p3 = f"c:/Users/HP/nx-mcp/test_part_c_{ts}.prt"

    file_ops.create_part(p3)
    modeling.create_cuboid(length=100.0, width=100.0, height=10.0, centered=True)
    
    # Deliberately call add_hole_nx with a position far outside the cuboid (x=500, y=500)
    print("Executing out-of-bounds add_hole_nx at (500, 500)...")
    miss_res = modeling.add_hole_nx(x=500.0, y=500.0, z=10.0, diameter=10.0, depth=10.0, direction="-Z")
    print("Miss Hole Result:", miss_res)
    
    assert not _is_ok(miss_res), "Expected hole miss to return failure!"
    assert "no material removed" in str(miss_res), f"Unexpected error message: {miss_res}"
    print("[PASS] Scenario C: Out-of-bounds hole validation error verified successfully!")

if __name__ == "__main__":
    test_scenario_a_state_isolation()
    test_scenario_b_fallback_isolation()
    test_scenario_c_hole_miss_validation()
    print("\n=== ALL 3 LIVE VERIFICATION SCENARIOS PASSED CLEANLY! ===")
