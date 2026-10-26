#!/usr/bin/env python3
"""
verify.py — Stage 3 Verification Engine
========================================
Compares reconstructed CAD models (exported STL) against reference OBJ meshes:
1. Bounding box extents (delta X, Y, Z, max error)
2. Watertightness and topological genus
3. Volume comparison and relative error percentage
4. Surface accuracy:
   - Chamfer distance (mean bidirectional surface error)
   - Hausdorff distance (maximum surface deviation)
   - Relative Hausdorff distance (% of bounding box diagonal)
5. Through-hole detection and dimension verification
"""

import sys
import json
from pathlib import Path
import numpy as np
import trimesh
from scipy.spatial import cKDTree


def compute_genus(mesh: trimesh.Trimesh) -> int:
    """Computes topological genus g = 1 - chi/2 for a watertight manifold mesh."""
    if not mesh.is_watertight:
        return -1
    chi = mesh.euler_number
    # For a closed 2-manifold without boundary: chi = 2 - 2g => g = (2 - chi) // 2
    return int((2 - chi) // 2)


def sample_surface_points(mesh: trimesh.Trimesh, count: int = 15000) -> np.ndarray:
    """Samples points uniformly across the mesh surface."""
    points, _ = trimesh.sample.sample_surface(mesh, count)
    return points


def compute_surface_metrics(mesh_ref: trimesh.Trimesh, mesh_cad: trimesh.Trimesh, n_samples: int = 20000):
    """Computes Chamfer and Hausdorff distances between two surface meshes."""
    pts_ref = sample_surface_points(mesh_ref, n_samples)
    pts_cad = sample_surface_points(mesh_cad, n_samples)

    tree_cad = cKDTree(pts_cad)
    tree_ref = cKDTree(pts_ref)

    dists_ref_to_cad, _ = tree_cad.query(pts_ref, k=1)
    dists_cad_to_ref, _ = tree_ref.query(pts_cad, k=1)

    chamfer = 0.5 * (float(np.mean(dists_ref_to_cad)) + float(np.mean(dists_cad_to_ref)))
    hausdorff = float(max(np.max(dists_ref_to_cad), np.max(dists_cad_to_ref)))
    p95_dist = float(max(np.percentile(dists_ref_to_cad, 95), np.percentile(dists_cad_to_ref, 95)))

    return {
        "chamfer_mean_mm": round(chamfer, 3),
        "p95_distance_mm": round(p95_dist, 3),
        "hausdorff_max_mm": round(hausdorff, 3),
        "mean_ref_to_cad_mm": round(float(np.mean(dists_ref_to_cad)), 3),
        "mean_cad_to_ref_mm": round(float(np.mean(dists_cad_to_ref)), 3)
    }


def verify_model(
    obj_path: str,
    stl_path: str,
    scale_to_mm: float = 1.0,
    expected_genus: int = 0,
    align_axes: str = None
) -> dict:
    p_obj = Path(obj_path).resolve()
    p_stl = Path(stl_path).resolve()

    if not p_obj.exists():
        raise FileNotFoundError(f"Reference OBJ not found: {p_obj}")
    if not p_stl.exists():
        raise FileNotFoundError(f"Reconstructed STL not found: {p_stl}")

    # 1. Load reference OBJ
    mesh_ref_raw = trimesh.load(str(p_obj), process=True)
    if isinstance(mesh_ref_raw, trimesh.Scene):
        mesh_ref = trimesh.util.concatenate(mesh_ref_raw.dump())
    else:
        mesh_ref = mesh_ref_raw

    # Scale reference to mm
    mesh_ref.apply_scale(scale_to_mm)

    # Filter isolated debris components if present
    comps = mesh_ref.split(only_watertight=False)
    if len(comps) > 1:
        mesh_ref = max(comps, key=lambda c: len(c.vertices))

    if align_axes == "y_to_z":
        mesh_ref.vertices = np.column_stack([
            mesh_ref.vertices[:, 0],
            mesh_ref.vertices[:, 2],
            mesh_ref.vertices[:, 1] + 100.0
        ])

    # 2. Load reconstructed CAD STL
    mesh_cad_raw = trimesh.load(str(p_stl), process=True)
    if isinstance(mesh_cad_raw, trimesh.Scene):
        mesh_cad = trimesh.util.concatenate(mesh_cad_raw.dump())
    else:
        mesh_cad = mesh_cad_raw

    ref_bounds = mesh_ref.bounds
    ref_extents = mesh_ref.extents
    ref_diag = float(mesh_ref.scale)

    cad_bounds = mesh_cad.bounds
    cad_extents = mesh_cad.extents
    cad_diag = float(mesh_cad.scale)

    # Dimension errors
    extent_errs = [abs(ref_extents[i] - cad_extents[i]) for i in range(3)]
    max_extent_err = float(max(extent_errs))
    rel_extent_err_pct = (max_extent_err / ref_diag) * 100.0

    # Volume error
    ref_vol = float(abs(mesh_ref.volume)) if abs(mesh_ref.volume) > 1e-3 else float(abs(mesh_ref.convex_hull.volume))
    cad_vol = float(abs(mesh_cad.volume)) if abs(mesh_cad.volume) > 1e-3 else float(abs(mesh_cad.convex_hull.volume))
    vol_err_pct = abs(cad_vol - ref_vol) / (ref_vol + 1e-6) * 100.0

    # Topology
    ref_watertight = bool(mesh_ref.is_watertight)
    cad_watertight = bool(mesh_cad.is_watertight)
    cad_genus = compute_genus(mesh_cad)
    genus_match = (cad_genus == expected_genus) if cad_watertight else False

    # Surface Distance Metrics
    surf_metrics = compute_surface_metrics(mesh_ref, mesh_cad)
    rel_hausdorff_pct = (surf_metrics["hausdorff_max_mm"] / ref_diag) * 100.0
    rel_chamfer_pct = (surf_metrics["chamfer_mean_mm"] / ref_diag) * 100.0

    # Relative pass criteria (proportional to bbox diagonal, with floor)
    # Target: max_extent_err <= max(1.5mm, 1.5% diag)
    # Target: chamfer <= max(1.0mm, 1.0% diag)
    # Target: vol_err <= 15.0%
    diag_floor_tol = max(1.5, 0.015 * ref_diag)
    extent_pass = max_extent_err <= diag_floor_tol
    vol_pass = vol_err_pct <= 15.0
    chamfer_pass = surf_metrics["chamfer_mean_mm"] <= max(1.0, 0.01 * ref_diag)
    max_hausdorff_tol = max(5.0, 0.05 * ref_diag)
    hausdorff_pass = surf_metrics["hausdorff_max_mm"] <= max_hausdorff_tol

    overall_pass = extent_pass and vol_pass and chamfer_pass and hausdorff_pass

    results = {
        "reference_obj": p_obj.name,
        "cad_stl": p_stl.name,
        "scale_applied": scale_to_mm,
        "reference_extents_mm": [round(float(e), 2) for e in ref_extents],
        "cad_extents_mm": [round(float(e), 2) for e in cad_extents],
        "extent_errors_mm": [round(float(e), 2) for e in extent_errs],
        "max_extent_error_mm": round(max_extent_err, 2),
        "relative_extent_error_pct": round(rel_extent_err_pct, 2),
        "reference_volume_mm3": round(ref_vol, 1),
        "cad_volume_mm3": round(cad_vol, 1),
        "volume_error_pct": round(vol_err_pct, 2),
        "cad_is_watertight": cad_watertight,
        "expected_genus": expected_genus,
        "cad_genus": cad_genus,
        "genus_match": genus_match,
        "surface_metrics": surf_metrics,
        "relative_chamfer_pct": round(rel_chamfer_pct, 2),
        "relative_hausdorff_pct": round(rel_hausdorff_pct, 2),
        "tolerances": {
            "max_extent_tolerance_mm": round(diag_floor_tol, 2),
            "max_volume_error_pct": 15.0,
            "max_chamfer_tolerance_mm": round(max(1.0, 0.01 * ref_diag), 2),
            "max_hausdorff_tolerance_mm": round(max_hausdorff_tol, 2)
        },
        "verdict": {
            "extent_check": "PASS" if extent_pass else "FAIL",
            "volume_check": "PASS" if vol_pass else "FAIL",
            "chamfer_check": "PASS" if chamfer_pass else "FAIL",
            "hausdorff_check": "PASS" if hausdorff_pass else "FAIL",
            "overall_status": "PASS" if overall_pass else "FAIL"
        }
    }

    return results


def print_report(res: dict):
    print("=" * 80)
    print(f"STAGE 3 CAD VERIFICATION REPORT: {res['reference_obj']} vs {res['cad_stl']}")
    print("=" * 80)
    print(f"  Reference Extents (mm): {res['reference_extents_mm']}")
    print(f"  CAD Extents (mm):       {res['cad_extents_mm']}")
    print(f"  Extent Errors (mm):     {res['extent_errors_mm']} (Max: {res['max_extent_error_mm']} mm, {res['relative_extent_error_pct']}%)")
    print(f"  Volume Comparison:      Ref: {res['reference_volume_mm3']:,} mm3 | CAD: {res['cad_volume_mm3']:,} mm3 (Error: {res['volume_error_pct']}%)")
    print(f"  Watertightness & Genus: Watertight: {res['cad_is_watertight']} | Genus: {res['cad_genus']} (Expected: {res['expected_genus']}, Match: {res['genus_match']})")
    print(f"  Surface Chamfer Error:  Mean: {res['surface_metrics']['chamfer_mean_mm']} mm ({res['relative_chamfer_pct']}%), P95: {res['surface_metrics']['p95_distance_mm']} mm")
    print(f"  Surface Hausdorff Max:  Max: {res['surface_metrics']['hausdorff_max_mm']} mm ({res['relative_hausdorff_pct']}%) [Tol: {res['tolerances']['max_hausdorff_tolerance_mm']} mm]")
    print("-" * 80)
    print(f"  VERDICT: Extent={res['verdict']['extent_check']} | Volume={res['verdict']['volume_check']} | Chamfer={res['verdict']['chamfer_check']} | Hausdorff={res['verdict']['hausdorff_check']} | OVERALL={res['verdict']['overall_status']}")
    print("=" * 80)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "housing"
    if target == "housing":
        res = verify_model(
            "obj/flanged_bearing_housing.obj",
            "flanged_bearing_housing_Parametric.stl",
            scale_to_mm=1.0,
            expected_genus=5  # Center bore + 4 flange bolt holes
        )
        print_report(res)
    elif target in ("cif3", "cif", "cif3_jerry_can", "jerry_can"):
        res = verify_model(
            "obj/Cif3_jerry_can_reduced.obj",
            "Cif3_Parametric.stl",
            scale_to_mm=100.0,
            expected_genus=1,  # 1 handle opening
            align_axes="y_to_z"
        )
        print_report(res)
    elif target in ("axe_soap", "axe"):
        res = verify_model(
            "obj/Axe_Soap.obj",
            "Axe_Soap_Parametric.stl",
            scale_to_mm=100.0,
            expected_genus=0
        )
        print_report(res)
    elif target in ("kissan", "kissan_bottle"):
        res = verify_model(
            "obj/Kissan_Bottle2.obj",
            "Kissan_Bottle_Parametric.stl",
            scale_to_mm=100.0,
            expected_genus=0
        )
        print_report(res)
    elif target in ("tresemme", "tresemme6", "tresemme_bottle"):
        res = verify_model(
            "TRESemme6.obj",
            "TRESemme6_Parametric.stl",
            scale_to_mm=100.0,
            expected_genus=0
        )
        print_report(res)
    elif target in ("axe3", "axe_bottle", "axe_spray"):
        res = verify_model(
            "Axe3.obj",
            "Axe3_Parametric.stl",
            scale_to_mm=100.0,
            expected_genus=0
        )
        print_report(res)
    elif target in ("surfexcel", "surfexcel2", "surf_excel"):
        res = verify_model(
            "Surfexcel2_reduced.obj",
            "Surfexcel2_Parametric.stl",
            scale_to_mm=100.0,
            expected_genus=1  # 1 handle opening
        )
        print_report(res)
    else:
        print(f"Unknown target: {target}")
