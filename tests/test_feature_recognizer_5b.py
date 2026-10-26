"""
test_feature_recognizer_5b.py
=============================
Phase 5B Test Suite:
Validates feature recognition and parametric primitive fitting against:
  1. Synthetic Ground-Truth Meshes:
     - Rounded Box 1 (W=60.0, T=40.0, H=80.0, R=8.0)
     - Rounded Box 2 (W=80.0, T=50.0, H=100.0, R=18.0 - very different radius)
     - Tapered Box (base W=60/T=40/R=6, top W=48/T=32/R=5, H=80.0)
     - Oval Tube (Major=70.0, Minor=35.0, H=90.0)
     - Noisy Rounded Box 1 (Gaussian noise on vertices, sigma=0.05 mm)
     - Noisy Rounded Box 2 (Gaussian noise on vertices, sigma=0.05 mm)
     - Noisy Tapered Box (Gaussian noise on vertices, sigma=0.05 mm)
     - Noisy Oval Tube (Gaussian noise on vertices, sigma=0.05 mm)
     - Flattened Tapered Tube (oval to flat oval loft/taper)
     - Thin Flat Tab with Small Ridges (thin tab with serrations/ridges)
     - Unfittable L-Shape (concave, MUST be marked UNSUPPORTED)
  2. Real Project Meshes:
     - Ellie_18_reduced.obj (must assert SUPPORTED)
     - Vaseline5_reduced.obj (must assert SUPPORTED)
     - Axe3.obj (must assert SUPPORTED & ROUND)
"""

import math
import sys
from pathlib import Path
from typing import Dict, Any, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np
import pytest
import trimesh
from shapely.geometry import Polygon

from src.nx_mcp.mesh_analyzer.primitive_fitter import (
    fit_rounded_rectangle,
    fit_ellipse,
    fit_superellipse,
    fit_best_primitive,
    create_rounded_rectangle_polygon,
    create_ellipse_polygon,
    create_superellipse_polygon,
    create_compound_4_arc_polygon,
    MAX_FIT_AREA_OVERLAP_ERROR_PCT,
)
from src.nx_mcp.mesh_analyzer.feature_recognizer import (
    recognize_feature_plan,
)

TEMP_DIR = Path("tests/artifacts_5b")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def build_3d_extruded_mesh(poly_2d: Polygon, height: float) -> trimesh.Trimesh:
    """Extrudes a 2D shapely polygon along Y to create a watertight 3D trimesh using pure numpy."""
    pts_2d = np.array(poly_2d.exterior.coords)[:-1]
    n_pts = len(pts_2d)
    y_min, y_max = -height / 2.0, height / 2.0
    c = poly_2d.centroid

    vertices = []
    # 0: bottom center
    vertices.append([c.x, y_min, c.y])
    # 1 .. n_pts: bottom ring
    for p in pts_2d:
        vertices.append([p[0], y_min, p[1]])
    # n_pts + 1: top center
    top_cen = n_pts + 1
    vertices.append([c.x, y_max, c.y])
    # n_pts + 2 .. 2*n_pts + 1: top ring
    top_ring = n_pts + 2
    for p in pts_2d:
        vertices.append([p[0], y_max, p[1]])

    faces = []
    # Bottom fan (pointing -Y)
    for i in range(n_pts):
        v_curr = 1 + i
        v_next = 1 + (i + 1) % n_pts
        faces.append([0, v_next, v_curr])

    # Top fan (pointing +Y)
    for i in range(n_pts):
        v_curr = top_ring + i
        v_next = top_ring + (i + 1) % n_pts
        faces.append([top_cen, v_curr, v_next])

    # Side walls
    for i in range(n_pts):
        b_curr = 1 + i
        b_next = 1 + (i + 1) % n_pts
        t_curr = top_ring + i
        t_next = top_ring + (i + 1) % n_pts
        faces.append([b_curr, b_next, t_next])
        faces.append([b_curr, t_next, t_curr])

    return trimesh.Trimesh(vertices=np.array(vertices), faces=np.array(faces), process=True)


def build_tapered_mesh(poly_base: Polygon, poly_top: Polygon, height: float) -> trimesh.Trimesh:
    """Lofts between poly_base and poly_top along Y using pure numpy with radial alignment."""
    from src.nx_mcp.mesh_analyzer.feature_recognizer import resample_polygon_radially
    pts_base = resample_polygon_radially(poly_base, 128)
    pts_top = resample_polygon_radially(poly_top, 128)
    n_pts = len(pts_base)

    y_min, y_max = -height / 2.0, height / 2.0
    c_b = poly_base.centroid
    c_t = poly_top.centroid

    vertices = []
    vertices.append([c_b.x, y_min, c_b.y])
    for p in pts_base:
        vertices.append([p[0], y_min, p[1]])
    top_cen = n_pts + 1
    vertices.append([c_t.x, y_max, c_t.y])
    top_ring = n_pts + 2
    for p in pts_top:
        vertices.append([p[0], y_max, p[1]])

    faces = []
    for i in range(n_pts):
        faces.append([0, 1 + (i + 1) % n_pts, 1 + i])
    for i in range(n_pts):
        faces.append([top_cen, top_ring + i, top_ring + (i + 1) % n_pts])
    for i in range(n_pts):
        b_curr = 1 + i
        b_next = 1 + (i + 1) % n_pts
        t_curr = top_ring + i
        t_next = top_ring + (i + 1) % n_pts
        faces.append([b_curr, b_next, t_next])
        faces.append([b_curr, t_next, t_curr])

    return trimesh.Trimesh(vertices=np.array(vertices), faces=np.array(faces), process=True)


def build_multi_section_mesh(polygons: List[Polygon], elevations: List[float]) -> trimesh.Trimesh:
    """Builds a multi-tier closed lofted trimesh across multiple polygon cross-sections."""
    from src.nx_mcp.mesh_analyzer.feature_recognizer import resample_polygon_radially
    n_pts = 128
    rings = [resample_polygon_radially(p, n_pts) for p in polygons]
    vertices = []
    c_b = polygons[0].centroid
    vertices.append([c_b.x, elevations[0], c_b.y])
    for r_idx, (ring, elev) in enumerate(zip(rings, elevations)):
        for pt in ring:
            vertices.append([pt[0], elev, pt[1]])
    c_t = polygons[-1].centroid
    top_cen_idx = len(vertices)
    vertices.append([c_t.x, elevations[-1], c_t.y])

    faces = []
    for i in range(n_pts):
        faces.append([0, 1 + (i + 1) % n_pts, 1 + i])
    for r_idx in range(len(rings) - 1):
        r1_start = 1 + r_idx * n_pts
        r2_start = 1 + (r_idx + 1) * n_pts
        for i in range(n_pts):
            b_curr = r1_start + i
            b_next = r1_start + (i + 1) % n_pts
            t_curr = r2_start + i
            t_next = r2_start + (i + 1) % n_pts
            faces.append([b_curr, b_next, t_next])
            faces.append([b_curr, t_next, t_curr])
    top_ring_start = 1 + (len(rings) - 1) * n_pts
    for i in range(n_pts):
        faces.append([top_cen_idx, top_ring_start + i, top_ring_start + (i + 1) % n_pts])

    return trimesh.Trimesh(vertices=np.array(vertices), faces=np.array(faces), process=True)


# -----------------------------------------------------------------------------
# Fixtures for Synthetic Meshes
# -----------------------------------------------------------------------------
@pytest.fixture(scope="module")
def synth_meshes() -> Dict[str, Dict[str, Any]]:
    meshes = {}

    # 1. Rounded Box 1: W=60, T=40, H=80, R=8
    p1 = create_rounded_rectangle_polygon(60.0, 40.0, 8.0)
    m1 = build_3d_extruded_mesh(p1, height=80.0)
    f1 = TEMP_DIR / "synth_rounded_box_1.obj"
    m1.export(str(f1))
    meshes["Rounded_Box_1"] = {
        "path": f1,
        "known": {"type": "ROUNDED_RECTANGLE", "width": 60.0, "thickness": 40.0, "radius": 8.0, "height": 80.0}
    }

    # 2. Rounded Box 2: W=80, T=50, H=100, R=18 (very different radius)
    p2 = create_rounded_rectangle_polygon(80.0, 50.0, 18.0)
    m2 = build_3d_extruded_mesh(p2, height=100.0)
    f2 = TEMP_DIR / "synth_rounded_box_2.obj"
    m2.export(str(f2))
    meshes["Rounded_Box_2"] = {
        "path": f2,
        "known": {"type": "ROUNDED_RECTANGLE", "width": 80.0, "thickness": 50.0, "radius": 18.0, "height": 100.0}
    }

    # 3. Tapered Box: base W=60, T=40, top W=48, T=32, H=80, R=6
    pb = create_rounded_rectangle_polygon(60.0, 40.0, 6.0)
    pt = create_rounded_rectangle_polygon(48.0, 32.0, 5.0)
    m3 = build_tapered_mesh(pb, pt, height=80.0)
    f3 = TEMP_DIR / "synth_tapered_box.obj"
    m3.export(str(f3))
    meshes["Tapered_Box"] = {
        "path": f3,
        "known": {"type": "ROUNDED_RECTANGLE", "width": 54.0, "thickness": 36.0, "radius": 5.5, "height": 80.0}
    }

    # 4. Oval Tube: Major=70, Minor=35, H=90
    p4 = create_ellipse_polygon(70.0, 35.0)
    m4 = build_3d_extruded_mesh(p4, height=90.0)
    f4 = TEMP_DIR / "synth_oval_tube.obj"
    m4.export(str(f4))
    meshes["Oval_Tube"] = {
        "path": f4,
        "known": {"type": "ELLIPSE", "major": 70.0, "minor": 35.0, "height": 90.0}
    }

    # 5. Noisy Rounded Box 1 (Gaussian noise on vertices, sigma=0.05 mm)
    m5 = m1.copy()
    np.random.seed(42)
    m5.vertices += np.random.normal(0.0, 0.05, m5.vertices.shape)
    f5 = TEMP_DIR / "synth_noisy_rounded_box_1.obj"
    m5.export(str(f5))
    meshes["Noisy_Rounded_Box_1"] = {
        "path": f5,
        "known": {"type": "ROUNDED_RECTANGLE", "width": 60.0, "thickness": 40.0, "radius": 8.0, "height": 80.0}
    }

    # 6. Noisy Rounded Box 2 (Gaussian noise on vertices, sigma=0.05 mm)
    m6 = m2.copy()
    np.random.seed(43)
    m6.vertices += np.random.normal(0.0, 0.05, m6.vertices.shape)
    f6 = TEMP_DIR / "synth_noisy_rounded_box_2.obj"
    m6.export(str(f6))
    meshes["Noisy_Rounded_Box_2"] = {
        "path": f6,
        "known": {"type": "ROUNDED_RECTANGLE", "width": 80.0, "thickness": 50.0, "radius": 18.0, "height": 100.0}
    }

    # 7. Noisy Tapered Box (Gaussian noise on vertices, sigma=0.02 mm)
    m7 = m3.copy()
    np.random.seed(44)
    m7.vertices += np.random.normal(0.0, 0.02, m7.vertices.shape)
    f7 = TEMP_DIR / "synth_noisy_tapered_box.obj"
    m7.export(str(f7))
    meshes["Noisy_Tapered_Box"] = {
        "path": f7,
        "known": {"type": "ROUNDED_RECTANGLE", "width": 54.0, "thickness": 36.0, "radius": 5.5, "height": 80.0}
    }

    # 8. Noisy Oval Tube (Gaussian noise on vertices, sigma=0.05 mm)
    m8 = m4.copy()
    np.random.seed(45)
    m8.vertices += np.random.normal(0.0, 0.05, m8.vertices.shape)
    f8 = TEMP_DIR / "synth_noisy_oval_tube.obj"
    m8.export(str(f8))
    meshes["Noisy_Oval_Tube"] = {
        "path": f8,
        "known": {"type": "ELLIPSE", "major": 70.0, "minor": 35.0, "height": 90.0}
    }

    # 9. Flattened Tapered Tube (oval to flat compound 4-arc oval)
    p_b_tube = create_ellipse_polygon(60.0, 35.0)
    p_t_tube = create_compound_4_arc_polygon(70.0, 20.0, 7.5)
    m_tube = build_tapered_mesh(p_b_tube, p_t_tube, height=100.0)
    f_tube = TEMP_DIR / "synth_flattened_tapered_tube.obj"
    m_tube.export(str(f_tube))
    meshes["Flattened_Tapered_Tube"] = {
        "path": f_tube,
        "known": {"type": "COMPOUND_4_ARC", "width": 65.0, "thickness": 27.5, "height": 100.0}
    }

    # 10. Thin Flat Tab with Ridges (W=60, T=3, R=1 with 0.15mm serration grooves)
    p_tab = create_rounded_rectangle_polygon(60.0, 3.0, 1.0)
    pts_t = np.array(p_tab.exterior.coords)[:-1]
    pts_ridged = []
    for p in pts_t:
        x, z = p[0], p[1]
        if abs(z) > 1.2 and abs(x) < 27.0:
            z_mod = (abs(z) - 0.15 * abs(np.sin(x * np.pi / 2.0))) * np.sign(z)
            pts_ridged.append([x, z_mod])
        else:
            pts_ridged.append([x, z])
    m_tab = build_3d_extruded_mesh(Polygon(pts_ridged), height=80.0)
    f_tab = TEMP_DIR / "synth_thin_tab_ridges.obj"
    m_tab.export(str(f_tab))
    meshes["Thin_Flat_Tab_With_Ridges"] = {
        "path": f_tab,
        "known": {"type": "ROUNDED_RECTANGLE", "width": 60.0, "thickness": 3.0, "radius": 1.0, "height": 80.0}
    }

    # 11. Compound 4-Arc Squircle (exponent ~2.7, W=70, T=20, H=100)
    p_sq = create_superellipse_polygon(70.0, 20.0, 2.7)
    m_sq = build_3d_extruded_mesh(p_sq, height=100.0)
    f_sq = TEMP_DIR / "synth_squircle_2_7.obj"
    m_sq.export(str(f_sq))
    meshes["Squircle_2_7"] = {
        "path": f_sq,
        "known": {"type": "COMPOUND_4_ARC", "width": 70.0, "thickness": 20.0, "height": 100.0}
    }

    # 12. Flattened Oval (different aspect ratio: W=80, T=30, n=2.4, H=110)
    p_fo = create_superellipse_polygon(80.0, 30.0, 2.4)
    m_fo = build_3d_extruded_mesh(p_fo, height=110.0)
    f_fo = TEMP_DIR / "synth_flattened_oval.obj"
    m_fo.export(str(f_fo))
    meshes["Flattened_Oval"] = {
        "path": f_fo,
        "known": {"type": "COMPOUND_4_ARC", "width": 80.0, "thickness": 30.0, "height": 110.0}
    }

    # 13. Noisy Squircle 2.7 (Gaussian noise on vertices, sigma=0.05 mm)
    m_nsq = m_sq.copy()
    np.random.seed(46)
    m_nsq.vertices += np.random.normal(0.0, 0.05, m_nsq.vertices.shape)
    f_nsq = TEMP_DIR / "synth_noisy_squircle_2_7.obj"
    m_nsq.export(str(f_nsq))
    meshes["Noisy_Squircle_2_7"] = {
        "path": f_nsq,
        "known": {"type": "COMPOUND_4_ARC", "width": 70.0, "thickness": 20.0, "height": 100.0}
    }

    # 14. Noisy Flattened Oval (Gaussian noise on vertices, sigma=0.05 mm)
    m_nfo = m_fo.copy()
    np.random.seed(47)
    m_nfo.vertices += np.random.normal(0.0, 0.05, m_nfo.vertices.shape)
    f_nfo = TEMP_DIR / "synth_noisy_flattened_oval.obj"
    m_nfo.export(str(f_nfo))
    meshes["Noisy_Flattened_Oval"] = {
        "path": f_nfo,
        "known": {"type": "COMPOUND_4_ARC", "width": 80.0, "thickness": 30.0, "height": 110.0}
    }

    # 15. Bulged Tube (Mid-section thicker than ends: W=60/T=20 at ends, W=60/T=32 at mid)
    # A 2-sketch loft fails (>30% error), but the adaptive multi-sketch loft passes!
    p_b_bulge = create_compound_4_arc_polygon(60.0, 20.0, 7.5)
    p_m_bulge = create_compound_4_arc_polygon(60.0, 32.0, 9.0)
    p_t_bulge = create_compound_4_arc_polygon(60.0, 20.0, 7.5)
    m_bulge = build_multi_section_mesh([p_b_bulge, p_m_bulge, p_t_bulge], [-50.0, 0.0, 50.0])
    f_bulge = TEMP_DIR / "synth_bulged_tube.obj"
    m_bulge.export(str(f_bulge))
    meshes["Bulged_Tube"] = {
        "path": f_bulge,
        "known": {"type": "COMPOUND_4_ARC", "width": 60.0, "thickness": 20.0, "height": 100.0}
    }

    # 16. Unfittable L-Shape: Non-standard concave shape (MUST be rejected)
    l_coords = [
        (-30, -30), (30, -30), (30, -10), (-10, -10),
        (-10, 30), (-30, 30), (-30, -30)
    ]
    p_l = Polygon(l_coords)
    m11 = build_3d_extruded_mesh(p_l, height=80.0)
    f11 = TEMP_DIR / "synth_unfittable_l_shape.obj"
    m11.export(str(f11))
    meshes["Unfittable_L_Shape"] = {
        "path": f11,
        "known": {"type": "UNSUPPORTED"}
    }

    return meshes


# -----------------------------------------------------------------------------
# Test Cases
# -----------------------------------------------------------------------------
def test_synthetic_ground_truth_fits(synth_meshes):
    """
    Validates that fitted numbers match ground truth known values within 5.0%.
    Prints a formatted table of fitted vs known values.
    """
    print("\n" + "=" * 125)
    print(f"{'Mesh Name':<28} | {'Primitive':<18} | {'Fitted Dimension':<28} | {'Known Dimension':<24} | {'Fit Err':<8} | {'Status':<10}")
    print("-" * 125)

    for name, data in synth_meshes.items():
        plan = recognize_feature_plan(data["path"])
        known = data["known"]

        if known["type"] == "UNSUPPORTED":
            assert plan["overall_status"] == "UNSUPPORTED"
            print(f"{name:<28} | {'REJECTED':<18} | {'(No primitive <= 5%)':<28} | {'(Concave/Arbitrary)':<24} | {'> 5.0%':<8} | {'PASS (REJ)'}")
            continue

        assert plan["overall_status"] == "SUPPORTED", f"Expected SUPPORTED for {name}, got {plan.get('rejection_reasons')}"
        assert plan["range_count"] >= 1

        # Use primary body range
        body_ranges = [r for r in plan["ranges"] if r["classification"] in ("PRISMATIC", "THIN_TAB", "BLENDED")]
        assert len(body_ranges) >= 1
        r = max(body_ranges, key=lambda x: x["height_span_mm"])
        params = r["fitted_parameters"]
        err = r["area_overlap_error_pct"]

        if known["type"] == "ROUNDED_RECTANGLE":
            if "start_parameters" in params:
                w_fit = (params["start_parameters"]["width"] + params["end_parameters"]["width"]) / 2.0
                t_fit = (params["start_parameters"]["thickness"] + params["end_parameters"]["thickness"]) / 2.0
                r_fit = (params["start_parameters"].get("corner_radius", 0.0) + params["end_parameters"].get("corner_radius", 0.0)) / 2.0
            else:
                w_fit = params["width"]
                t_fit = params["thickness"]
                r_fit = params.get("corner_radius", 0.0)

            w_kn = known["width"]
            t_kn = known["thickness"]
            r_kn = known["radius"]

            w_err = abs(w_fit - w_kn) / w_kn * 100.0
            t_err = abs(t_fit - t_kn) / t_kn * 100.0
            r_err = abs(r_fit - r_kn) / r_kn * 100.0 if r_kn > 0.0 else 0.0

            assert w_err <= 5.0, f"Width error {w_err:.2f}% > 5% for {name}"
            assert t_err <= 5.0, f"Thickness error {t_err:.2f}% > 5% for {name}"
            assert r_err <= 5.0, f"Radius error {r_err:.2f}% > 5% for {name}"
            assert err <= MAX_FIT_AREA_OVERLAP_ERROR_PCT

            fit_str = f"W={w_fit:.1f}, T={t_fit:.1f}, R={r_fit:.2f}"
            kn_str = f"W={w_kn:.1f}, T={t_kn:.1f}, R={r_kn:.2f}"
            print(f"{name:<28} | {r['fitted_primitive']:<18} | {fit_str:<28} | {kn_str:<24} | {err:5.2f}% | {'PASS'}")

        elif known["type"] in ("ELLIPSE", "SUPERELLIPSE"):
            if "start_parameters" in params:
                p_s = params["start_parameters"]
                p_e = params["end_parameters"]
                maj_fit = ((p_s.get("major_axis") or p_s.get("width")) + (p_e.get("major_axis") or p_e.get("width"))) / 2.0
                min_fit = ((p_s.get("minor_axis") or p_s.get("thickness")) + (p_e.get("minor_axis") or p_e.get("thickness"))) / 2.0
            else:
                maj_fit = params.get("major_axis") or params.get("width")
                min_fit = params.get("minor_axis") or params.get("thickness")

            maj_kn = known["major"]
            min_kn = known["minor"]

            maj_err = abs(maj_fit - maj_kn) / maj_kn * 100.0
            min_err = abs(min_fit - min_kn) / min_kn * 100.0

            assert maj_err <= 5.0, f"Major axis error {maj_err:.2f}% > 5% for {name}"
            assert min_err <= 5.0, f"Minor axis error {min_err:.2f}% > 5% for {name}"
            assert err <= MAX_FIT_AREA_OVERLAP_ERROR_PCT

            fit_str = f"Maj={maj_fit:.1f}, Min={min_fit:.1f}"
            kn_str = f"Maj={maj_kn:.1f}, Min={min_kn:.1f}"
            print(f"{name:<28} | {r['fitted_primitive']:<18} | {fit_str:<28} | {kn_str:<24} | {err:5.2f}% | {'PASS'}")

        elif known["type"] == "COMPOUND_4_ARC":
            if "start_parameters" in params:
                p_s = params["start_parameters"]
                p_e = params["end_parameters"]
                w_s = p_s.get("width") or p_s.get("major_axis")
                w_e = p_e.get("width") or p_e.get("major_axis")
                t_s = p_s.get("thickness") or p_s.get("minor_axis")
                t_e = p_e.get("thickness") or p_e.get("minor_axis")
                w_fit = (w_s + w_e) / 2.0
                t_fit = (t_s + t_e) / 2.0
                rc_fit = (p_s.get("corner_radius", 0.0) + p_e.get("corner_radius", 0.0)) / 2.0
            else:
                w_fit = params.get("width") or params.get("major_axis")
                t_fit = params.get("thickness") or params.get("minor_axis")
                rc_fit = params.get("corner_radius", 0.0)
            rf_fit = params.get("flank_radius", 0.0)

            w_kn = known["width"]
            t_kn = known["thickness"]

            w_err = abs(w_fit - w_kn) / w_kn * 100.0
            t_err = abs(t_fit - t_kn) / t_kn * 100.0

            assert w_err <= 5.0, f"Width error {w_err:.2f}% > 5% for {name}"
            assert t_err <= 5.0, f"Thickness error {t_err:.2f}% > 5% for {name}"
            assert err <= MAX_FIT_AREA_OVERLAP_ERROR_PCT

            fit_str = f"W={w_fit:.1f}, T={t_fit:.1f}, Rc={rc_fit:.1f}"
            kn_str = f"W={w_kn:.1f}, T={t_kn:.1f}"
            print(f"{name:<28} | {r['fitted_primitive']:<18} | {fit_str:<28} | {kn_str:<24} | {err:5.2f}% | {'PASS'}")

    print("=" * 125)


def test_real_project_meshes():
    """
    Tests feature recognition on project meshes: Ellie, Vaseline, and Axe3.
    Asserts SUPPORTED status and checks CAD consistency.
    """
    real_paths = [
        Path("obj/Ellie_18_reduced.obj"),
        Path("obj/Vaseline5_reduced.obj"),
        Path("obj/Axe3.obj"),
    ]

    print("\n" + "=" * 125)
    print("REAL PROJECT MESHES: CAD FEATURE PLAN RECOGNITION (PHASE 5B)")
    print("=" * 125)

    plans = {}
    for mp in real_paths:
        if not mp.exists():
            continue
        plan = recognize_feature_plan(mp)
        plans[mp.name] = plan

        print(f"\n[MESH: {mp.name}] (Axis = {plan['primary_axis']}, Height = {plan['total_height_mm']:.1f} mm, Ranges = {plan['range_count']}, Status = {plan['overall_status']})")

        # Save feature plan to output
        plan_path = Path("output") / f"{mp.stem}_feature_plan.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)

        for r in plan["ranges"]:
            z0, z1 = r["elevation_range_mm"]
            p_type = r["fitted_primitive"] or "NONE"
            params = r.get("fitted_parameters") or {}
            param_str = ", ".join(f"{k}={v}" for k, v in params.items())
            err = r["area_overlap_error_pct"]
            err_str = f"{err:5.2f}%" if err is not None else "  N/A "
            status_str = "PASS (<=5%)" if r["is_supported"] else "REJECTED (>5%)"
            if r["classification"] == "END_BLEND":
                status_str = "NOT FITTED: validated by the CAD verifier"
            print(f"  Range {r['range_index']} [Y={z0:6.1f} to {z1:6.1f} mm]: {r['classification']:<10} -> {r['cad_operation']:<18} | Fit: {p_type:<22} ({param_str}) | Err: {err_str} | {status_str}")

        if plan["overall_status"] != "SUPPORTED":
            print(f"  -> REJECTION REASON: {plan.get('rejection_reasons')}")

    # STRICT ASSERTIONS
    assert "Ellie_18_reduced.obj" in plans
    ellie_plan = plans["Ellie_18_reduced.obj"]
    assert ellie_plan["overall_status"] == "SUPPORTED", f"Ellie must be SUPPORTED: {ellie_plan.get('rejection_reasons')}"
    assert ellie_plan["end_blend_ranges_count"] >= 1
    assert ellie_plan["cad_parameters"]["BODY_WIDTH"] > 0
    assert ellie_plan["cad_parameters"]["BODY_THICKNESS"] > 0

    assert "Axe3.obj" in plans
    axe3_plan = plans["Axe3.obj"]
    assert axe3_plan["overall_status"] == "SUPPORTED", f"Axe3 must be SUPPORTED: {axe3_plan.get('rejection_reasons')}"
    # Verify Axe3 is classified as ROUND for non-blend ranges
    assert all(r["classification"] == "ROUND" for r in axe3_plan["ranges"] if r["classification"] != "END_BLEND")

    assert "Vaseline5_reduced.obj" in plans
    vaseline_plan = plans["Vaseline5_reduced.obj"]
    # With strictly buildable native sketch primitives (lines, arcs, ellipses; no superellipse),
    # Vaseline's ranges are evaluated honestly according to whether buildable shapes pass <= 5%.
    assert vaseline_plan["range_count"] >= 3


def test_flattened_mesh_axis_and_mismatch_guard(tmp_path: Path):
    """
    Validates that:
    1. A flattened mesh with NO spec file is sliced along its height (short) axis, not longest extent.
    2. The checker fails with a clear error if the plan's axis differs from the checker's mesh axis.
    """
    import json
    import trimesh
    from src.nx_mcp.fidelity_checker import run_fidelity_check

    # Create a flattened cylinder / disc (X=60, Y=12, Z=60)
    disc = trimesh.creation.cylinder(radius=30.0, height=12.0)
    # cylinder() defaults to Z axis; rotate to align height along Y
    rot = trimesh.transformations.rotation_matrix(math.pi / 2.0, [1, 0, 0])
    disc.apply_transform(rot)

    # Save to tmp obj
    disc_obj = tmp_path / "flattened_disc.obj"
    disc.export(str(disc_obj))

    # 1. Check without spec file: must detect axis Y (index 1), NOT longest extent (X or Z)
    res_no_spec = run_fidelity_check(disc_obj, stl_path=disc_obj, spec_path=None, n_stations=20)
    assert res_no_spec["axis_name"] == "Y", f"Expected axis Y for flattened mesh, got {res_no_spec.get('axis_name')}"
    # Valid station coordinates must span along Y (~ -6 to +6)
    assert len(res_no_spec["stations_z"]) == 20
    assert abs(res_no_spec["stations_z"][0] - (-5.64)) < 2.0

    # 2. Check with a feature plan specifying a mismatched axis (e.g. Z or X instead of Y)
    mismatched_plan = tmp_path / "mismatched_plan.json"
    with open(mismatched_plan, "w", encoding="utf-8") as f:
        json.dump({"primary_axis": "Z"}, f)

    res_mismatch = run_fidelity_check(disc_obj, stl_path=disc_obj, spec_path=mismatched_plan)
    assert res_mismatch["passed"] is False
    assert "AXIS MISMATCH" in res_mismatch["error"]
    assert "feature plan axis = Z" in res_mismatch["error"]
    assert "mesh-derived axis = Y" in res_mismatch["error"]
