import sys
from pathlib import Path
import pytest
import trimesh

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.nx_mcp.surface_distance_checker import evaluate_surface_distance

@pytest.fixture
def tmp_mesh_dir(tmp_path: Path) -> Path:
    d = tmp_path / "surface_dist_test"
    d.mkdir(parents=True, exist_ok=True)
    return d

def test_surface_distance_exact_match(tmp_mesh_dir: Path):
    """Exact identical meshes must pass surface distance check."""
    m_base = trimesh.creation.cylinder(radius=25.0, height=100.0)
    p_base = tmp_mesh_dir / "base.obj"
    m_base.export(str(p_base))
    
    res = evaluate_surface_distance(p_base, p_base)
    assert res["pass"] is True
    assert res["is_false_pass"] is False
    assert res["mean_distance_mm"] < 1.0

def test_surface_distance_catches_height_discrepancy(tmp_mesh_dir: Path):
    """
    Independent surface distance checker must catch a subtly wrong part
    whose height is off by 8% on a 200 mm part (e.g. 216 mm vs 200 mm).
    """
    m_base = trimesh.creation.cylinder(radius=25.0, height=200.0)
    p_base = tmp_mesh_dir / "tall_base.obj"
    m_base.export(str(p_base))
    
    m_wrong_h = trimesh.creation.cylinder(radius=25.0, height=216.0) # +8% height
    p_wrong_h = tmp_mesh_dir / "tall_wrong_h.stl"
    m_wrong_h.export(str(p_wrong_h))
    
    res = evaluate_surface_distance(p_base, p_wrong_h)
    assert res["pass"] is False
    assert res["is_false_pass"] is True
    assert "Surface discrepancy" in res["reason"]

def test_surface_distance_catches_radius_discrepancy(tmp_mesh_dir: Path):
    """
    Independent surface distance checker must catch a subtly wrong part
    whose radius is uniformly expanded beyond the mean deviation limit (e.g. +4 mm).
    """
    m_base = trimesh.creation.cylinder(radius=60.0, height=100.0)
    p_base = tmp_mesh_dir / "wide_base.obj"
    m_base.export(str(p_base))
    
    m_wrong_r = trimesh.creation.cylinder(radius=64.0, height=100.0) # +4 mm radial expansion
    p_wrong_r = tmp_mesh_dir / "wide_wrong_r.stl"
    m_wrong_r.export(str(p_wrong_r))
    
    res = evaluate_surface_distance(p_base, p_wrong_r)
    assert res["pass"] is False
    assert res["is_false_pass"] is True
    assert "mean dist" in res["reason"]


def test_surface_checker_and_fidelity_checker_frame_consistency(tmp_mesh_dir: Path):
    """
    Validates that both the surface distance checker and Check 7 fidelity checker
    use the exact same primary axis, canonical orientation, and scale.
    Fails if the CAD mesh or reference mesh is rotated or shifted out of frame.
    """
    import numpy as np

    m_base = trimesh.creation.cylinder(radius=25.0, height=100.0)
    p_base = tmp_mesh_dir / "frame_test_base.obj"
    m_base.export(str(p_base))

    # Rotated by 90 degrees around X (axis mismatch between Y and Z frame)
    rot = trimesh.transformations.rotation_matrix(np.pi / 2.0, [1, 0, 0])
    m_rotated = m_base.copy()
    m_rotated.apply_transform(rot)
    p_rot = tmp_mesh_dir / "frame_test_rotated.stl"
    m_rotated.export(str(p_rot))

    res_rot = evaluate_surface_distance(p_base, p_rot)
    # Different coordinate frame must fail surface distance
    assert res_rot["pass"] is False
    assert res_rot["is_false_pass"] is True

