import sys
from pathlib import Path
import numpy as np
import pytest
import trimesh

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.run_benchmark import benchmark_single_mesh, find_run_journal_exe

def nx_available() -> bool:
    try:
        find_run_journal_exe()
        return True
    except Exception:
        return False

def make_bottle_mesh() -> trimesh.Trimesh:
    n_theta = 48
    thetas = np.linspace(0, 2 * np.pi, n_theta, endpoint=False)
    y_profile = [
        (0.0, 20.0),
        (12.5, 20.0),
        (25.0, 20.0),
        (32.5, 17.0),
        (40.0, 14.0),
        (47.5, 12.0),
        (55.0, 10.0),
        (62.5, 10.0),
        (70.0, 10.0),
    ]
    verts = [[0.0, 0.0, 0.0]]
    for y, r in y_profile:
        for th in thetas:
            verts.append([r * np.cos(th), y, r * np.sin(th)])
    verts.append([0.0, 70.0, 0.0])

    faces = []
    for i in range(n_theta):
        i_next = (i + 1) % n_theta
        faces.append([0, 1 + i_next, 1 + i])
    for ring in range(len(y_profile) - 1):
        r1_st = 1 + ring * n_theta
        r2_st = 1 + (ring + 1) * n_theta
        for i in range(n_theta):
            i_next = (i + 1) % n_theta
            p1 = r1_st + i
            p2 = r1_st + i_next
            p3 = r2_st + i_next
            p4 = r2_st + i
            faces.append([p1, p2, p3])
            faces.append([p1, p3, p4])
    top_idx = len(verts) - 1
    last_r_st = 1 + (len(y_profile) - 1) * n_theta
    for i in range(n_theta):
        i_next = (i + 1) % n_theta
        faces.append([top_idx, last_r_st + i, last_r_st + i_next])

    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)

def _loft_2d_loops(pts_2d_base: np.ndarray, y_scale_profile: list) -> trimesh.Trimesh:
    n = len(pts_2d_base)
    verts = []
    y_bot, _ = y_scale_profile[0]
    verts.append([0.0, y_bot, 0.0])

    for y, scale in y_scale_profile:
        for x, z in pts_2d_base:
            verts.append([x * scale, y, z * scale])

    y_top, _ = y_scale_profile[-1]
    top_idx = len(verts)
    verts.append([0.0, y_top, 0.0])

    faces = []
    for i in range(n):
        i_next = (i + 1) % n
        faces.append([0, 1 + i_next, 1 + i])

    n_rings = len(y_scale_profile)
    for r in range(n_rings - 1):
        r1_st = 1 + r * n
        r2_st = 1 + (r + 1) * n
        for i in range(n):
            i_next = (i + 1) % n
            b1 = r1_st + i
            b2 = r1_st + i_next
            t1 = r2_st + i
            t2 = r2_st + i_next
            faces.append([b1, b2, t2])
            faces.append([b1, t2, t1])

    last_r_st = 1 + (n_rings - 1) * n
    for i in range(n):
        i_next = (i + 1) % n
        faces.append([top_idx, last_r_st + i, last_r_st + i_next])

    return trimesh.Trimesh(vertices=verts, faces=faces, process=True)

def make_filleted_rounded_box_mesh(w=60.0, t=40.0, cr=8.0, h=80.0) -> trimesh.Trimesh:
    hw, ht = w / 2.0, t / 2.0
    n_arc = 12
    pts_2d = []
    for a in np.linspace(0, np.pi/2, n_arc, endpoint=False):
        pts_2d.append([hw - cr + cr * np.cos(a), ht - cr + cr * np.sin(a)])
    for a in np.linspace(np.pi/2, np.pi, n_arc, endpoint=False):
        pts_2d.append([-hw + cr + cr * np.cos(a), ht - cr + cr * np.sin(a)])
    for a in np.linspace(np.pi, 3*np.pi/2, n_arc, endpoint=False):
        pts_2d.append([-hw + cr + cr * np.cos(a), -ht + cr + cr * np.sin(a)])
    for a in np.linspace(3*np.pi/2, 2*np.pi, n_arc, endpoint=False):
        pts_2d.append([hw - cr + cr * np.cos(a), -ht + cr + cr * np.sin(a)])
    pts_2d = np.array(pts_2d)

    half_h = h / 2.0
    profile = [
        (-half_h, 0.40),
        (-half_h + 0.4, 0.80),
        (-half_h + 0.7, 0.96),
        (-half_h + 0.9, 0.995),
        (-half_h + 1.0, 1.00),
        (0.0, 1.00),
        (half_h - 1.0, 1.00),
        (half_h - 0.9, 0.995),
        (half_h - 0.7, 0.96),
        (half_h - 0.4, 0.80),
        (half_h, 0.40),
    ]
    return _loft_2d_loops(pts_2d, profile)

def make_filleted_oval_mesh(w=50.0, t=30.0, h=80.0) -> trimesh.Trimesh:
    n_pts = 48
    thetas = np.linspace(0, 2*np.pi, n_pts, endpoint=False)
    pts_2d = np.array([[(w/2.0)*np.cos(th), (t/2.0)*np.sin(th)] for th in thetas])

    half_h = h / 2.0
    profile = [
        (-half_h, 0.40),
        (-half_h + 0.4, 0.80),
        (-half_h + 0.7, 0.96),
        (-half_h + 0.9, 0.995),
        (-half_h + 1.0, 1.00),
        (0.0, 1.00),
        (half_h - 1.0, 1.00),
        (half_h - 0.9, 0.995),
        (half_h - 0.7, 0.96),
        (half_h - 0.4, 0.80),
        (half_h, 0.40),
    ]
    return _loft_2d_loops(pts_2d, profile)


@pytest.mark.skipif(not nx_available(), reason="Siemens NX run_journal.exe not available")
def test_synthetic_bottle_real_pipeline(tmp_path: Path):
    """End-to-end test of synthetic bottle through real NX reconstruction pipeline."""
    mesh = make_bottle_mesh()
    obj_p = tmp_path / "synthetic_bottle.obj"
    mesh.export(str(obj_p))

    res = benchmark_single_mesh(obj_p, "DEV", tmp_path, timeout_sec=120)
    assert res["final_result"] == "PASS"
    for i in range(1, 9):
        assert res[f"C{i}"] == "PASS", f"Check C{i} failed: {res.get('reason')}"
    assert res["vol_error_pct"] < 5.0


@pytest.mark.skipif(not nx_available(), reason="Siemens NX run_journal.exe not available")
def test_synthetic_rounded_box_real_pipeline(tmp_path: Path):
    """End-to-end test of synthetic rounded box through real NX reconstruction pipeline."""
    mesh = make_filleted_rounded_box_mesh()
    obj_p = tmp_path / "synthetic_rounded_box.obj"
    mesh.export(str(obj_p))

    res = benchmark_single_mesh(obj_p, "DEV", tmp_path, timeout_sec=120)
    assert res["final_result"] == "PASS"
    for i in range(1, 9):
        assert res[f"C{i}"] == "PASS", f"Check C{i} failed: {res.get('reason')}"
    assert res["vol_error_pct"] < 5.0


@pytest.mark.skipif(not nx_available(), reason="Siemens NX run_journal.exe not available")
def test_synthetic_oval_tube_real_pipeline(tmp_path: Path):
    """End-to-end test of synthetic oval tube through real NX reconstruction pipeline."""
    mesh = make_filleted_oval_mesh()
    obj_p = tmp_path / "synthetic_oval_tube.obj"
    mesh.export(str(obj_p))

    res = benchmark_single_mesh(obj_p, "DEV", tmp_path, timeout_sec=120)
    assert res["final_result"] == "PASS"
    for i in range(1, 9):
        assert res[f"C{i}"] == "PASS", f"Check C{i} failed: {res.get('reason')}"
    assert res["vol_error_pct"] < 5.0
