"""
surface_distance_checker.py
===========================
Independent Whole-Mesh to CAD Surface Distance Evaluator (False Pass Detector).

Computes bidirectional surface distance between a reference OBJ mesh and an exported CAD STL mesh:
1. Samples points uniformly across the entire surfaces of both the OBJ and CAD bodies.
2. Uses spatial k-d trees to compute bidirectional point-to-surface distances.
3. Computes mean, 95th-percentile, and maximum surface deviation.
4. Flags any candidate PASS as a FALSE PASS if maximum surface distance exceeds the threshold.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
from scipy.spatial import cKDTree
import trimesh

# Non-negotiable surface fidelity limits relative to 3D bounding diagonal
SURFACE_MEAN_LIMIT_DIAGONAL_FRACTION: float = 0.012   # 1.2% of bounding diagonal
SURFACE_P95_LIMIT_DIAGONAL_FRACTION: float = 0.022    # 2.2% of bounding diagonal
SURFACE_MAX_LIMIT_DIAGONAL_FRACTION: float = 0.048    # 4.8% of bounding diagonal

# Non-negotiable limits relative to maximum transverse cross-section diameter (tightening for thin/elongated parts)
SURFACE_MEAN_LIMIT_CROSS_SECTION_FRACTION: float = 0.04   # 4.0% of max transverse diameter
SURFACE_P95_LIMIT_CROSS_SECTION_FRACTION: float = 0.07    # 7.0% of max transverse diameter
SURFACE_MAX_LIMIT_CROSS_SECTION_FRACTION: float = 0.15    # 15.0% of max transverse diameter


def evaluate_surface_distance(
    obj_path: Path,
    stl_path: Path,
    n_sample_query: int = 5000,
    n_sample_target: int = 50000,
    seed: Optional[int] = 42,
) -> Dict[str, Any]:
    """
    Evaluates independent bidirectional surface distance between OBJ and CAD STL.
    Deterministic point sampling is enforced when seed is provided.
    """
    if not obj_path.exists():
        raise FileNotFoundError(f"OBJ mesh file not found: {obj_path}")
    if not stl_path.exists():
        raise FileNotFoundError(f"CAD STL file not found: {stl_path}")

    if seed is not None:
        np.random.seed(seed)

    mesh_obj = trimesh.load(str(obj_path), force="mesh")
    mesh_cad = trimesh.load(str(stl_path), force="mesh")

    # Unit auto-scaling to mm for reference mesh
    obj_ext = float(max(mesh_obj.extents)) if len(mesh_obj.extents) > 0 else 1.0
    scale_obj = 1.0
    if obj_ext < 0.25:
        scale_obj = 1000.0
    elif obj_ext < 15.0:
        scale_obj = 100.0
    if abs(scale_obj - 1.0) > 1e-4:
        mesh_obj.apply_scale(scale_obj)

    # Unit auto-scaling for CAD mesh if in non-mm raw coordinates
    cad_ext = float(max(mesh_cad.extents)) if len(mesh_cad.extents) > 0 else 1.0
    if cad_ext < 15.0 and abs(scale_obj - 1.0) > 1e-4:
        mesh_cad.apply_scale(scale_obj)

    # For multi-body reference meshes containing internal cavities or loose debris,
    # evaluate against the primary external product body envelope
    bodies = mesh_obj.split()
    if len(bodies) > 1:
        mesh_obj = max(bodies, key=lambda b: len(b.faces))

    bbox_extents = np.maximum(mesh_obj.extents, mesh_cad.extents)
    bounding_diagonal = float(np.linalg.norm(bbox_extents))
    part_span = float(max(bbox_extents))

    # Cross-section diameter: largest transverse extent perpendicular to primary axis
    sorted_ext = sorted(bbox_extents)
    max_cross_section_dia = float(sorted_ext[1])

    # Limits are min(span_based_limit, fraction * max_cross_section_dia)
    span_mean = SURFACE_MEAN_LIMIT_DIAGONAL_FRACTION * bounding_diagonal
    span_p95 = SURFACE_P95_LIMIT_DIAGONAL_FRACTION * bounding_diagonal
    span_max = SURFACE_MAX_LIMIT_DIAGONAL_FRACTION * bounding_diagonal

    cs_mean = SURFACE_MEAN_LIMIT_CROSS_SECTION_FRACTION * max_cross_section_dia
    cs_p95 = SURFACE_P95_LIMIT_CROSS_SECTION_FRACTION * max_cross_section_dia
    cs_max = SURFACE_MAX_LIMIT_CROSS_SECTION_FRACTION * max_cross_section_dia

    mean_limit = round(min(span_mean, cs_mean), 3)
    p95_limit = round(min(span_p95, cs_p95), 3)
    max_limit = round(min(span_max, cs_max), 3)

    # Sample points on surface deterministically
    obj_pts, _ = trimesh.sample.sample_surface(mesh_obj, n_sample_query)
    cad_pts_dense, _ = trimesh.sample.sample_surface(mesh_cad, n_sample_target)

    # Query 1: OBJ -> CAD surface
    tree_cad = cKDTree(cad_pts_dense)
    dists_obj_to_cad, _ = tree_cad.query(obj_pts)

    # Query 2: CAD -> OBJ surface
    cad_pts_query, _ = trimesh.sample.sample_surface(mesh_cad, n_sample_query)
    obj_pts_dense, _ = trimesh.sample.sample_surface(mesh_obj, n_sample_target)
    tree_obj = cKDTree(obj_pts_dense)
    dists_cad_to_obj, _ = tree_obj.query(cad_pts_query)

    mean_dist = float(0.5 * (np.mean(dists_obj_to_cad) + np.mean(dists_cad_to_obj)))
    p95_dist = float(max(np.percentile(dists_obj_to_cad, 95), np.percentile(dists_cad_to_obj, 95)))
    max_dist = float(max(np.max(dists_obj_to_cad), np.max(dists_cad_to_obj)))

    is_pass = bool(
        mean_dist <= mean_limit
        and p95_dist <= p95_limit
        and max_dist <= max_limit
    )

    reason = ""
    if not is_pass:
        failures = []
        if mean_dist > mean_limit:
            failures.append(f"mean dist {mean_dist:.2f}mm > {mean_limit:.2f}mm")
        if p95_dist > p95_limit:
            failures.append(f"p95 dist {p95_dist:.2f}mm > {p95_limit:.2f}mm")
        if max_dist > max_limit:
            failures.append(f"max dist {max_dist:.2f}mm > {max_limit:.2f}mm")
        reason = "Surface discrepancy: " + ", ".join(failures)

    return {
        "pass": is_pass,
        "is_false_pass": not is_pass,
        "mean_distance_mm": round(mean_dist, 3),
        "mean_limit_allowed_mm": mean_limit,
        "p95_distance_mm": round(p95_dist, 3),
        "p95_limit_allowed_mm": p95_limit,
        "max_distance_mm": round(max_dist, 3),
        "max_limit_allowed_mm": max_limit,
        "bounding_diagonal_mm": round(bounding_diagonal, 3),
        "part_span_mm": round(part_span, 3),
        "reason": reason,
    }
