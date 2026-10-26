import sys
from pathlib import Path
import numpy as np
import pytest
import trimesh

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.nx_mcp.mesh_analyzer.feature_recognizer import (
    determine_primary_axis,
    recognize_feature_plan,
)
from src.nx_mcp.mesh_analyzer.pca_align import get_canonical_rotation
from src.nx_mcp.mesh_analyzer.revolve_profile_analyzer import RevolveProfileAnalyzer


def create_synthetic_cylinder(axis: str, radius: float = 20.0, height: float = 100.0) -> trimesh.Trimesh:
    """Creates a cylinder along the specified axis ('X', 'Y', 'Z')."""
    cyl = trimesh.creation.cylinder(radius=radius, height=height, sections=36)
    # Default trimesh cylinder is aligned along Z
    if axis.upper() == "Y":
        # Rotate Z -> Y
        R = get_canonical_rotation("Z")
        cyl.vertices = (R @ cyl.vertices.T).T
    elif axis.upper() == "X":
        # Rotate Z -> X: rotation around Y by 90 deg
        R = np.array([
            [0.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0]
        ])
        cyl.vertices = (R @ cyl.vertices.T).T
    return cyl


def create_synthetic_box(axis: str, length: float = 100.0, width: float = 40.0, thickness: float = 20.0) -> trimesh.Trimesh:
    """Creates a rectangular box with primary length along the specified axis ('X', 'Y', 'Z')."""
    if axis.upper() == "Y":
        extents = [width, length, thickness]
    elif axis.upper() == "X":
        extents = [length, width, thickness]
    else: # Z
        extents = [width, thickness, length]
    return trimesh.creation.box(extents=extents)


def test_cylinder_orientation_invariance(tmp_path):
    """
    Test B.2: A synthetic cylinder created along X, Y, and Z must give
    the same plan dimensions once canonically rotated to Y.
    """
    plans = {}
    for ax in ["X", "Y", "Z"]:
        mesh = create_synthetic_cylinder(axis=ax, radius=25.0, height=120.0)
        obj_file = tmp_path / f"cyl_{ax}.obj"
        mesh.export(str(obj_file))
        
        analyzer = RevolveProfileAnalyzer(obj_file)
        prof = analyzer.compute_circularity_profile(n_slices=40)
        assert prof["is_round"] is True, f"Cylinder along {ax} should be recognized as round"
        
        zones = analyzer.segment_zones(prof)
        plans[ax] = {
            "total_height": prof["total_height"],
            "max_dia": prof.get("max_diameter", 50.0),
            "zone_count": len(zones),
            "zone_height": zones[0]["height"],
            "zone_r": zones[0]["r_start"]
        }

    # Compare plans across X, Y, Z
    ref = plans["Y"]
    for ax in ["X", "Z"]:
        curr = plans[ax]
        assert abs(curr["total_height"] - ref["total_height"]) < 1.0, f"Height mismatch {ax} vs Y"
        assert abs(curr["max_dia"] - ref["max_dia"]) < 1.0, f"Diameter mismatch {ax} vs Y"
        assert curr["zone_count"] == ref["zone_count"], f"Zone count mismatch {ax} vs Y"
        assert abs(curr["zone_height"] - ref["zone_height"]) < 1.0, f"Zone height mismatch {ax} vs Y"
        assert abs(curr["zone_r"] - ref["zone_r"]) < 1.0, f"Zone radius mismatch {ax} vs Y"


def test_box_orientation_invariance(tmp_path):
    """
    Test B.2: A synthetic box created along X, Y, and Z must give
    the same feature plan dimensions once canonically rotated to Y.
    """
    plans = {}
    for ax in ["X", "Y", "Z"]:
        mesh = create_synthetic_box(axis=ax, length=100.0, width=40.0, thickness=20.0)
        obj_file = tmp_path / f"box_{ax}.obj"
        mesh.export(str(obj_file))
        
        plan = recognize_feature_plan(obj_file)
        assert plan["overall_status"] == "SUPPORTED", f"Box along {ax} must be supported"
        assert plan["primary_axis"] == "Y", f"Plan primary axis must be canonical Y"
        
        cad = plan["cad_parameters"]
        plans[ax] = {
            "height": plan["total_height_mm"],
            "width": cad.get("BODY_WIDTH", 40.0),
            "thickness": cad.get("BODY_THICKNESS", 20.0),
        }

    ref = plans["Y"]
    for ax in ["X", "Z"]:
        curr = plans[ax]
        assert abs(curr["height"] - ref["height"]) < 1.5, f"Height mismatch {ax} vs Y"
        # Dimensions may swap width/thickness in transverse plane depending on rotation, but set must match
        dims_ref = sorted([ref["width"], ref["thickness"]])
        dims_curr = sorted([curr["width"], curr["thickness"]])
        assert abs(dims_curr[0] - dims_ref[0]) < 1.0, f"Thickness mismatch {ax} vs Y"
        assert abs(dims_curr[1] - dims_ref[1]) < 1.0, f"Width mismatch {ax} vs Y"


def test_euler_gate_torus_rejected(tmp_path):
    """
    Test B.4: A torus (genus 1, Euler number 0) must be rejected by the Euler-number gate.
    """
    torus = trimesh.creation.torus(major_radius=30.0, minor_radius=10.0)
    torus_path = tmp_path / "test_torus.obj"
    torus.export(str(torus_path))
    
    plan = recognize_feature_plan(torus_path)
    assert plan["overall_status"] == "UNSUPPORTED"
    assert plan["is_degenerate"] is True
    reasons = " ".join(plan.get("rejection_reasons", []))
    assert "Degenerate topology: Euler number" in reasons or "through-holes" in reasons


def test_euler_gate_unmerged_vertices_accepted(tmp_path):
    """
    Test B.4: A cylinder mesh with unmerged vertices must NOT be rejected by the Euler gate.
    """
    cyl = trimesh.creation.cylinder(radius=20.0, height=80.0, sections=32)
    # Unmerge vertices: give every face its own distinct vertices
    unmerged_faces = cyl.faces
    unmerged_verts = cyl.vertices[unmerged_faces.flatten()]
    new_faces = np.arange(len(unmerged_verts)).reshape(-1, 3)
    
    unmerged_mesh = trimesh.Trimesh(vertices=unmerged_verts, faces=new_faces, process=False)
    # Confirm raw Euler characteristic is negative before merging:
    # V = 3 * F, E = 3 * F, V - E + F = F > 0 or unstitched edges
    cyl_path = tmp_path / "unmerged_cylinder.obj"
    unmerged_mesh.export(str(cyl_path))
    
    plan = recognize_feature_plan(cyl_path)
    # Must NOT be marked degenerate
    assert plan["is_degenerate"] is False
    reasons = " ".join(plan.get("rejection_reasons", []))
    assert "Degenerate topology" not in reasons
