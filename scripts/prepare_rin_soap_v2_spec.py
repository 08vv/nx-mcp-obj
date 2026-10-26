"""
prepare_rin_soap_v2_spec.py
============================
High-fidelity parametric CAD specification generator for Rin soap bar
from obj/Rin_soap_reduced.obj.

Key goals:
  - Preserve actual concave front-face profile (recess at centre, rails top/bottom)
  - Smooth organic rounded-rectangular cross-section at every station
  - Continuous flowing curvature across both short ends
  - 45 stations x 96 pts per station for spline-quality surface fidelity

Coordinate system in NX:
  X = length (elongated direction, ~200 mm)
  Y = width (~108 mm, front = -Y, back = +Y)
  Z = height (~67 mm)
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import trimesh


# ────────────────────────────────────────────────────────────────────
# Polygon resampling utilities
# ────────────────────────────────────────────────────────────────────

def polygon_arc_lengths(pts: np.ndarray) -> np.ndarray:
    """Cumulative arc-length along a closed polygon."""
    diffs = np.diff(pts, axis=0, prepend=pts[-1:])
    seg_lens = np.linalg.norm(diffs, axis=1)
    return np.cumsum(seg_lens)


def resample_closed_polygon(pts: np.ndarray, n: int = 96) -> np.ndarray:
    """Resample a closed 2D polygon to *n* uniformly-spaced points by arc-length,
    preserving the concave shape (no convex hull)."""
    if len(pts) < 3:
        return np.zeros((n, 2))

    # Close the polygon if not already closed
    if np.linalg.norm(pts[0] - pts[-1]) > 1e-6:
        pts = np.vstack([pts, pts[0:1]])

    # Compute cumulative arc-length
    diffs = np.diff(pts, axis=0)
    seg_lens = np.linalg.norm(diffs, axis=1)
    cum_len = np.concatenate([[0.0], np.cumsum(seg_lens)])
    total = cum_len[-1]

    if total < 1e-6:
        return np.tile(pts[0], (n, 1))

    # Sample at uniform arc-length intervals
    targets = np.linspace(0, total, n, endpoint=False)
    resampled = np.zeros((n, 2))
    seg_idx = 0
    for i, t in enumerate(targets):
        while seg_idx < len(cum_len) - 2 and cum_len[seg_idx + 1] < t:
            seg_idx += 1
        d0, d1 = cum_len[seg_idx], cum_len[seg_idx + 1]
        frac = (t - d0) / (d1 - d0) if (d1 - d0) > 1e-12 else 0.0
        resampled[i] = pts[seg_idx] + frac * (pts[seg_idx + 1] - pts[seg_idx])

    # Ensure CCW winding (positive signed area)
    signed_area = 0.5 * np.sum(
        resampled[:, 0] * np.roll(resampled[:, 1], -1) -
        np.roll(resampled[:, 0], -1) * resampled[:, 1]
    )
    if signed_area < 0:
        resampled = resampled[::-1]

    return resampled


def align_contour_to_previous(
    curr: np.ndarray,
    prev: np.ndarray,
) -> np.ndarray:
    """Cyclically shift *curr* to minimise total squared distance to *prev*."""
    n = len(curr)
    best_shift, best_cost = 0, float("inf")
    for s in range(n):
        rolled = np.roll(curr, -s, axis=0)
        cost = float(np.sum((rolled - prev) ** 2))
        if cost < best_cost:
            best_cost = cost
            best_shift = s
    return np.roll(curr, -best_shift, axis=0)


# ────────────────────────────────────────────────────────────────────
# Mesh section extraction (preserving concavity)
# ────────────────────────────────────────────────────────────────────

def get_section_contour(
    mesh: trimesh.Trimesh,
    x: float,
) -> Optional[np.ndarray]:
    """Intersect mesh at X = x and return the ordered polygon points (Y, Z).

    For multi-path sections (near ends), concatenates all paths and
    traces the outer boundary preserving concavity.
    """
    sec = mesh.section(plane_origin=[x, 0, 0], plane_normal=[1, 0, 0])
    if sec is None:
        return None

    paths = sec.discrete
    if not paths:
        return None

    if len(paths) == 1:
        # Single contour – use directly (preserves concavity)
        pts_3d = paths[0]
        return pts_3d[:, [1, 2]]

    # Multiple paths: merge into single contour
    # Concatenate all path points, then use alpha-shape / ordered boundary
    all_pts = np.vstack([p[:, [1, 2]] for p in paths])

    # Use ordered boundary tracing via trimesh.path
    try:
        from scipy.spatial import ConvexHull
        # For near-end sections with multi-contour, we use the path with most points
        # since the concavity at ends is minimal
        longest_path = max(paths, key=lambda p: len(p))
        return longest_path[:, [1, 2]]
    except Exception:
        return all_pts


# ────────────────────────────────────────────────────────────────────
# Main spec generator
# ────────────────────────────────────────────────────────────────────

def generate_spec(
    obj_path: str = "obj/Rin_soap_reduced.obj",
    output_path: str = "Rin_soap_v2_spec.json",
    n_stations: int = 45,
    n_pts: int = 96,
) -> Dict[str, Any]:
    """Extract high-fidelity parametric specification from OBJ mesh."""

    print(f"Loading mesh: {obj_path}")
    mesh = trimesh.load(obj_path, process=False)
    mesh.apply_scale(100.0)  # assumed dm → mm

    min_x, max_x = float(mesh.bounds[0][0]), float(mesh.bounds[1][0])
    extents = mesh.extents.tolist()

    print(f"  Bounds (mm): X=[{min_x:.2f}, {max_x:.2f}]")
    print(f"  Extents (mm): {extents[0]:.2f} x {extents[1]:.2f} x {extents[2]:.2f}")

    # ── Parametric driving expressions ──────────────────────────
    expressions = {
        "BODY_LENGTH": round(extents[0], 3),
        "BODY_WIDTH": round(extents[1], 3),
        "BODY_HEIGHT": round(extents[2], 3),
        "FRONT_RECESS_Y": 45.97,       # depth of central concave recess from front edge
        "FRONT_RAIL_Y": 54.32,         # depth of upper/lower front rails
        "FRONT_RECESS_Z_HALF": 10.6,   # half-height of recess zone
        "REAR_WALL_Y": 53.75,          # back face Y position
        "TOP_Z": round(extents[2] / 2, 3),
        "BOTTOM_Z": round(-extents[2] / 2, 3),
        "CORNER_BLEND_R": 3.0,         # corner fillet target radius
        "STATION_COUNT": float(n_stations),
        "PTS_PER_STATION": float(n_pts),
    }

    # ── Generate station cross-sections ─────────────────────────
    # Pad inward from true bounds to avoid degenerate end caps
    pad = 0.15 * (max_x - min_x) / n_stations  # ~half a station spacing
    xs = np.linspace(min_x + pad, max_x - pad, n_stations)

    stations = []
    prev_contour = None

    for idx, x in enumerate(xs):
        raw = get_section_contour(mesh, float(x))
        if raw is None or len(raw) < 4:
            print(f"  [SKIP] Station {idx} at X={x:.2f}: no valid section")
            continue

        resampled = resample_closed_polygon(raw, n_pts)

        # Anchor first station; track alignment for subsequent
        if prev_contour is None:
            # Start near rear-center (+Y, Z≈0)
            anchor_idx = int(np.argmin(
                (resampled[:, 0] - 50.0) ** 2 + resampled[:, 1] ** 2
            ))
            resampled = np.roll(resampled, -anchor_idx, axis=0)
        else:
            resampled = align_contour_to_previous(resampled, prev_contour)

        prev_contour = resampled

        # Build 3D contour points [X, Y, Z]
        pts_3d = [
            [round(float(x), 4), round(float(p[0]), 4), round(float(p[1]), 4)]
            for p in resampled
        ]

        # Compute section properties
        area = 0.5 * abs(float(np.sum(
            resampled[:, 0] * np.roll(resampled[:, 1], -1) -
            np.roll(resampled[:, 0], -1) * resampled[:, 1]
        )))
        peri = float(np.sum(np.linalg.norm(np.diff(
            np.vstack([resampled, resampled[0:1]]), axis=0
        ), axis=1)))

        stations.append({
            "station_index": idx,
            "axis_position": round(float(x), 4),
            "area_mm2": round(area, 2),
            "perimeter_mm": round(peri, 2),
            "contour_pts_3d_mm": pts_3d,
        })

        x_str = f"{float(x):7.2f}"
        print(f"  Station {idx:2d}: X={x_str}mm  area={area:.1f}  peri={peri:.1f}  pts={len(pts_3d)}")

    # ── Assemble spec ───────────────────────────────────────────
    spec = {
        "metadata": {
            "source_obj": obj_path,
            "target_part_name": "Rin_soap_v2_Parametric.prt",
            "scale_to_mm": 100.0,
            "build_axis": "X",
            "n_stations": len(stations),
            "n_pts_per_station": n_pts,
            "description": (
                "High-fidelity parametric spec for Rin soap bar. "
                "Preserves concave front face, organic rounded-rectangular "
                "cross-sections, and continuous end transitions."
            ),
        },
        "expressions": expressions,
        "features": [
            {
                "feature_type": "through_curves_loft",
                "name": "BODY_PRIMARY_LOFT",
                "description": "Solid loft through 45 organic cross-section stations",
                "axis": "X",
                "station_count": len(stations),
                "stations": stations,
            },
            {
                "feature_type": "edge_blend",
                "name": "END_BLEND",
                "description": "Fillet blend on end cap edges for smooth organic feel",
                "target_body": "BODY_PRIMARY_LOFT",
                "radius_mm": 3.0,
                "fallback_radii_mm": [2.0, 1.5, 1.0],
                "can_fail_silently": True,
            },
        ],
    }

    out_p = Path(output_path).resolve()
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print(f"\n[OK] Specification saved: {out_p}")
    print(f"     {len(stations)} stations, {n_pts} pts/station")
    return spec


if __name__ == "__main__":
    generate_spec()
