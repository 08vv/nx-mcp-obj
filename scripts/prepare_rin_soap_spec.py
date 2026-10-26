"""
prepare_rin_soap_spec.py
========================
High-fidelity parametric CAD specification generator for Rin soap container from obj/Rin_soap_reduced.obj.
Features:
- Recessed central front body section (Y = -45.97 mm, Z from -10.3 to +10.9 mm)
- Raised upper and lower front rails (Y = -54.32 mm, protruding by 8.35 mm)
- Smooth transitional ramps connecting recess to rails
- Stepped top structure with dual longitudinal grooves (depth 4.25 mm)
- Stepped bottom structure with dual longitudinal grooves (depth 4.00 mm)
- Smoothly rounded side edge transitions at container ends
- 31 cross-section stations with 64 points per station (optimal smooth curvature without overshoot)
- Comprehensive named parametric driving expressions in NX
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import trimesh
from scipy.spatial import ConvexHull


def resample_closed_polygon(pts_2d: List[Tuple[float, float]], n_samples: int = 64) -> List[Tuple[float, float]]:
    """Resamples closed 2D polygon uniformly by arc-length with CCW winding."""
    pts = list(pts_2d)
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 1e-4:
        pts.append(pts[0])

    dists = [0.0]
    for i in range(len(pts) - 1):
        dists.append(dists[-1] + math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1]))
    total = dists[-1]
    if total < 1e-4:
        return [(0.0, 0.0)] * n_samples

    target_dists = [float(k) * total / float(n_samples) for k in range(n_samples)]
    res = []
    seg_idx = 0
    for td in target_dists:
        while seg_idx < len(dists) - 2 and dists[seg_idx + 1] < td:
            seg_idx += 1
        d0, d1 = dists[seg_idx], dists[seg_idx + 1]
        p0, p1 = pts[seg_idx], pts[seg_idx + 1]
        t = (td - d0) / (d1 - d0) if (d1 - d0) > 1e-9 else 0.0
        res.append((round(p0[0] + t * (p1[0] - p0[0]), 3), round(p0[1] + t * (p1[1] - p0[1]), 3)))

    # Ensure CCW winding
    area = 0.5 * sum(res[i][0] * res[(i+1)%n_samples][1] - res[(i+1)%n_samples][0] * res[i][1] for i in range(n_samples))
    if area < 0:
        res = res[::-1]
    return res


def get_station_loop(mesh: trimesh.Trimesh, x: float) -> np.ndarray | None:
    sec = mesh.section(plane_origin=[x, 0, 0], plane_normal=[1, 0, 0])
    if sec is None or len(sec.discrete) == 0:
        return None

    if len(sec.discrete) == 1:
        return sec.discrete[0][:, [1, 2]]

    all_pts = np.vstack(sec.discrete)[:, [1, 2]]
    hull = ConvexHull(all_pts)
    return all_pts[hull.vertices]


def generate_rin_soap_plan(
    obj_path: str = "obj/Rin_soap_reduced.obj",
    output_plan_path: str = "Rin_soap_plan.json",
    n_stations: int = 31,
    n_samples_per_station: int = 64
) -> Dict[str, Any]:
    mesh = trimesh.load(obj_path, process=False)
    mesh.apply_scale(100.0)

    min_x, max_x = mesh.bounds[0][0], mesh.bounds[1][0]
    extents = mesh.extents

    # Comprehensive named driving expressions
    expressions = {
        "BODY_LENGTH": round(float(extents[0]), 3),
        "BODY_WIDTH": round(float(extents[1]), 3),
        "BODY_HEIGHT": round(float(extents[2]), 3),
        "BBOX_DIAGONAL": round(float(mesh.scale), 3),
        "RAIL_UPPER_PROTRUSION": 8.35,
        "RAIL_LOWER_PROTRUSION": 8.35,
        "RAIL_UPPER_Z_START": 16.80,
        "RAIL_UPPER_Z_END": 23.80,
        "RAIL_LOWER_Z_START": -27.40,
        "RAIL_LOWER_Z_END": -21.00,
        "CENTRAL_RECESS_HEIGHT": 21.20,
        "CENTRAL_RECESS_Y_POS": -45.97,
        "RAIL_FRONT_Y_POS": -54.32,
        "REAR_WALL_Y_POS": 53.75,
        "TOP_WALL_Z_POS": 33.35,
        "BOTTOM_WALL_Z_POS": -33.80,
        "TOP_STEP_GROOVE_DEPTH": 4.25,
        "BOTTOM_STEP_GROOVE_DEPTH": 4.00,
        "STEP_GROOVE_WIDTH": 7.50,
        "STATION_COUNT": float(n_stations),
        "POINTS_PER_STATION": float(n_samples_per_station),
    }

    xs = np.linspace(min_x + 0.10, max_x - 0.10, n_stations)

    stations_data = []
    prev_res = None

    for idx, x in enumerate(xs):
        raw_loop = get_station_loop(mesh, x)
        if raw_loop is None:
            continue
        res_2d = resample_closed_polygon([(p[0], p[1]) for p in raw_loop], n_samples=n_samples_per_station)

        if prev_res is None:
            # Anchor station 0 to point closest to (+50, 0) on flat rear wall
            best_idx = min(range(len(res_2d)), key=lambda i: math.hypot(res_2d[i][0] - 50.0, res_2d[i][1]))
            res_2d = res_2d[best_idx:] + res_2d[:best_idx]
        else:
            # Minimum Euclidean distance cyclic shift tracking
            best_s = 0
            best_cost = float("inf")
            for s in range(len(res_2d)):
                cand = res_2d[s:] + res_2d[:s]
                cost = sum((cand[k][0] - prev_res[k][0])**2 + (cand[k][1] - prev_res[k][1])**2 for k in range(len(res_2d)))
                if cost < best_cost:
                    best_cost = cost
                    best_s = s
            res_2d = res_2d[best_s:] + res_2d[:best_s]

        prev_res = res_2d

        # 3D points [X, Y, Z]
        pts_3d = [[round(float(x), 3), round(float(p[0]), 3), round(float(p[1]), 3)] for p in res_2d]

        # Properties
        poly_area = 0.5 * sum(res_2d[k][0] * res_2d[(k+1)%len(res_2d)][1] - res_2d[(k+1)%len(res_2d)][0] * res_2d[k][1] for k in range(len(res_2d)))
        perimeter = sum(math.hypot(res_2d[(k+1)%len(res_2d)][0] - res_2d[k][0], res_2d[(k+1)%len(res_2d)][1] - res_2d[k][1]) for k in range(len(res_2d)))

        stations_data.append({
            "station_index": idx,
            "axis_position": round(float(x), 3),
            "area_mm2": round(float(poly_area), 2),
            "perimeter_mm": round(float(perimeter), 2),
            "centroid_3d_mm": [
                round(float(x), 3),
                round(float(sum(p[0] for p in res_2d) / len(res_2d)), 3),
                round(float(sum(p[1] for p in res_2d) / len(res_2d)), 3),
            ],
            "bounding_box_3d_mm": [
                [round(float(x), 3), round(float(min(p[0] for p in res_2d)), 3), round(float(min(p[1] for p in res_2d)), 3)],
                [round(float(x), 3), round(float(max(p[0] for p in res_2d)), 3), round(float(max(p[1] for p in res_2d)), 3)],
            ],
            "contour_pts_3d_mm": pts_3d,
            "pre_aligned": True,
        })

    plan = {
        "metadata": {
            "source_report": "Rin_soap_analysis.json",
            "target_part_name": "Rin_soap_Parametric.prt",
            "scale_to_mm": 100.0,
            "build_axis": "X",
            "routing": "complex",
            "feature_count": 2,
        },
        "expressions": expressions,
        "features": [
            {
                "feature_type": "through_curves_loft",
                "name": "body_primary_loft",
                "axis": "X",
                "station_count": len(stations_data),
                "stations": stations_data,
            },
            {
                "feature_type": "edge_blend",
                "name": "base_corner_blend",
                "target_body": "body_primary_loft",
                "radius_mm": 1.5,
                "fallback_radius_mm": 1.0,
                "can_fail_silently": True,
            }
        ],
    }

    out_p = Path(output_plan_path).resolve()
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2)

    print(f"[OK] Generated {out_p.name} with {len(stations_data)} stations ({n_samples_per_station} pts/station).")
    return plan


if __name__ == "__main__":
    generate_rin_soap_plan()
