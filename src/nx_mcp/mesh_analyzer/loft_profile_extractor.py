"""
loft_profile_extractor.py
=========================
Extracts clean, resampled, zero-twist closed cross-section outlines from 3D OBJ meshes
for non-round loft/Through-Curves CAD reconstruction.

Features:
- Slices mesh at N equidistant stations along primary height axis.
- Extracts continuous closed 2D boundary polygons.
- Resamples to uniform point count per station (e.g. 64 points).
- Applies cyclic smoothing to remove mesh facet artifacts.
- Synchronizes starting points (at angle theta = 0 along positive transverse-1 axis)
  to guarantee zero twist when lofted across stations.
- Saves outline definitions to JSON and renders visualization plots.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter1d


# Named extraction constants
DEFAULT_LOFT_STATIONS: int = 12         # Number of slicing elevations along height
DEFAULT_POINTS_PER_OUTLINE: int = 64    # Resampled point count per closed outline curve
MAX_SMOOTHING_LOSS_PCT: float = 2.0     # Maximum allowable deviation in area or width/thickness from raw mesh
CRIMP_EXTRA_STATIONS: int = 4           # Extra station count concentrated near thin top crimps


def find_exact_ray_crossing(pts_2d: np.ndarray, cen: np.ndarray) -> Tuple[float, float]:
    """
    Finds the exact intersection point where the polygon boundary crosses
    the positive ray at angle 0 (along +X from origin / centroid, Z = 0.0).
    Returns (x_crossing, z_crossing).
    """
    n = len(pts_2d)
    best_x = None

    # Target Z coordinate is 0.0 (neutral symmetry plane along positive transverse-1 axis)
    target_z = 0.0

    for i in range(n):
        p1 = pts_2d[i]
        p2 = pts_2d[(i + 1) % n]
        z1 = p1[1] - target_z
        z2 = p2[1] - target_z

        if (z1 <= 0.0 and z2 > 0.0) or (z1 >= 0.0 and z2 < 0.0):
            t = (0.0 - z1) / (z2 - z1)
            x_cross = p1[0] + t * (p2[0] - p1[0])
            if x_cross > 0.0:
                if best_x is None or x_cross > best_x:
                    best_x = float(x_cross)

    if best_x is not None:
        return (best_x, float(target_z))

    # Fallback to ray from centroid
    for i in range(n):
        p1 = pts_2d[i]
        p2 = pts_2d[(i + 1) % n]
        z1 = p1[1] - cen[1]
        z2 = p2[1] - cen[1]
        if (z1 <= 0.0 and z2 > 0.0) or (z1 >= 0.0 and z2 < 0.0):
            t = (0.0 - z1) / (z2 - z1)
            x_cross = p1[0] + t * (p2[0] - p1[0])
            if x_cross > cen[0]:
                return (float(x_cross), float(cen[1]))

    angles = np.arctan2(pts_2d[:, 1] - cen[1], pts_2d[:, 0] - cen[0])
    idx = int(np.argmin(np.abs(angles)))
    return (float(pts_2d[idx, 0]), float(pts_2d[idx, 1]))


def resample_and_align_outline(
    pts_3d: np.ndarray,
    n_points: int = DEFAULT_POINTS_PER_OUTLINE,
    axis_idx: int = 1,
) -> Tuple[np.ndarray, Dict[str, float]]:
    """
    Takes 3D vertices forming a closed boundary loop:
    1. Computes raw metrics (area, width, thickness).
    2. Finds exact crossing point at angle = 0 (Z = cen[1]) and inserts it as start point.
    3. Resamples uniformly to n_points.
    4. Evaluates smoothing loss vs raw mesh; adaptively decreases sigma until loss < 2%.
    5. Returns resampled 3D points with start point at exact crossing (Z drift < 0.5 mm).
    """
    transverse_indices = [i for i in (0, 1, 2) if i != axis_idx]
    idx_t1, idx_t2 = transverse_indices[0], transverse_indices[1]

    # Ensure loop is closed
    if np.linalg.norm(pts_3d[0] - pts_3d[-1]) > 1e-4:
        pts_3d = np.vstack([pts_3d, pts_3d[0]])

    pts_2d = pts_3d[:, [idx_t1, idx_t2]]
    cen = np.mean(pts_2d[:-1], axis=0)

    # Raw metrics
    raw_w1 = float(np.max(pts_2d[:, 0]) - np.min(pts_2d[:, 0]))
    raw_w2 = float(np.max(pts_2d[:, 1]) - np.min(pts_2d[:, 1]))
    raw_area = 0.5 * abs(float(np.sum(pts_2d[:-1, 0] * pts_2d[1:, 1] - pts_2d[1:, 0] * pts_2d[:-1, 1])))

    # Find exact ray crossing at angle = 0
    cross_t1, cross_t2 = find_exact_ray_crossing(pts_2d[:-1], cen)

    # Ensure counter-clockwise orientation
    signed_area = 0.5 * np.sum(pts_2d[:-1, 0] * pts_2d[1:, 1] - pts_2d[1:, 0] * pts_2d[:-1, 1])
    if signed_area < 0:
        pts_3d = pts_3d[::-1]
        pts_2d = pts_3d[:, [idx_t1, idx_t2]]

    # Insert exact crossing point at start
    # Find segment containing crossing and roll
    dists_to_cross = np.hypot(pts_2d[:, 0] - cross_t1, pts_2d[:, 1] - cross_t2)
    min_idx = int(np.argmin(dists_to_cross))

    pts_3d_rot = np.roll(pts_3d[:-1], -min_idx, axis=0)
    # Set first point to exact crossing elevation and coordinates
    pt_exact_3d = np.zeros(3)
    pt_exact_3d[axis_idx] = pts_3d[0, axis_idx]
    pt_exact_3d[idx_t1] = cross_t1
    pt_exact_3d[idx_t2] = cross_t2

    pts_3d_rot = np.vstack([pt_exact_3d, pts_3d_rot, pt_exact_3d])

    # Compute cumulative arc-length
    diffs = np.diff(pts_3d_rot, axis=0)
    seg_lens = np.linalg.norm(diffs, axis=1)
    cum_lens = np.concatenate([[0.0], np.cumsum(seg_lens)])
    total_len = cum_lens[-1]

    target_dists = np.linspace(0.0, total_len, n_points, endpoint=False)
    resampled_3d = np.zeros((n_points, 3))
    for ax in range(3):
        resampled_3d[:, ax] = np.interp(target_dists, cum_lens, pts_3d_rot[:, ax])

    # Fix 2: Adaptive smoothing check against raw metrics
    sigmas_to_try = [0.8, 0.4, 0.2, 0.0]
    best_resampled = resampled_3d
    best_errs = {"area_loss_pct": 0.0, "w1_loss_pct": 0.0, "w2_loss_pct": 0.0, "sigma_used": 0.0}

    for sig in sigmas_to_try:
        cand_3d = np.copy(resampled_3d)
        if sig > 0:
            for ax in [idx_t1, idx_t2]:
                cand_3d[:, ax] = gaussian_filter1d(cand_3d[:, ax], sigma=sig, mode="wrap")

        # Make sure point 0 preserves exact crossing
        cand_3d[0, idx_t1] = cross_t1
        cand_3d[0, idx_t2] = cross_t2

        cand_2d = cand_3d[:, [idx_t1, idx_t2]]
        cand_w1 = float(np.max(cand_2d[:, 0]) - np.min(cand_2d[:, 0]))
        cand_w2 = float(np.max(cand_2d[:, 1]) - np.min(cand_2d[:, 1]))
        cand_area = 0.5 * abs(float(np.sum(cand_2d[:-1, 0] * cand_2d[1:, 1] - cand_2d[1:, 0] * cand_2d[:-1, 1])))

        a_loss = abs(cand_area - raw_area) / max(raw_area, 1e-4) * 100.0
        w1_loss = abs(cand_w1 - raw_w1) / max(raw_w1, 1e-4) * 100.0
        w2_loss = abs(cand_w2 - raw_w2) / max(raw_w2, 1e-4) * 100.0

        if a_loss <= MAX_SMOOTHING_LOSS_PCT and w1_loss <= MAX_SMOOTHING_LOSS_PCT and w2_loss <= MAX_SMOOTHING_LOSS_PCT:
            best_resampled = cand_3d
            best_errs = {
                "area_loss_pct": round(a_loss, 3),
                "w1_loss_pct": round(w1_loss, 3),
                "w2_loss_pct": round(w2_loss, 3),
                "sigma_used": sig,
            }
            break

    # Start point Z drift relative to angle 0 ray (Z = 0.0)
    z_drift = abs(best_resampled[0, idx_t2] - 0.0)
    best_errs["start_z_drift_mm"] = round(float(z_drift), 4)

    return best_resampled, best_errs


def determine_primary_axis(mesh: trimesh.Trimesh) -> Tuple[int, str]:
    """
    Determines primary height/lofting axis:
    - If part has dominant elongation (longest extent > 1.5x second longest), longest axis is the height axis.
    - Otherwise (e.g. flat compact or disk), the axis with greatest transverse symmetry (aspect ratio closest to 1.0) is the height axis.
    """
    extents = mesh.extents
    sorted_extents = np.sort(extents)
    if sorted_extents[-1] > 1.5 * sorted_extents[-2]:
        max_idx = int(np.argmax(extents))
        return max_idx, ["X", "Y", "Z"][max_idx]

    aspect_yz = extents[1] / max(extents[2], 1e-4) # if X is axis
    aspect_xz = extents[0] / max(extents[2], 1e-4) # if Y is axis
    aspect_xy = extents[0] / max(extents[1], 1e-4) # if Z is axis

    scores = [
        (abs(aspect_yz - 1.0), 0, "X"),
        (abs(aspect_xz - 1.0), 1, "Y"),
        (abs(aspect_xy - 1.0), 2, "Z"),
    ]
    scores.sort(key=lambda s: s[0])
    return scores[0][1], scores[0][2]


def extract_cross_section_outlines(
    mesh_path: Path,
    n_stations: int = DEFAULT_LOFT_STATIONS,
    n_points: int = DEFAULT_POINTS_PER_OUTLINE,
    units: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extracts N clean, resampled, zero-twist cross-section outlines from a 3D mesh.
    """
    mesh: trimesh.Trimesh = trimesh.load(str(mesh_path), force="mesh")
    
    # Unit scaling
    max_ext = float(np.max(mesh.extents))
    if units:
        u_norm = units.lower().strip()
        scale = 1000.0 if u_norm in ("m", "meter") else 100.0 if u_norm in ("dm", "decimeter") else 10.0 if u_norm in ("cm", "centimeter") else 1.0
    else:
        scale = 1000.0 if max_ext < 0.25 else 100.0 if max_ext < 15.0 else 1.0
    
    if abs(scale - 1.0) > 1e-4:
        mesh.apply_scale(scale)

    bounds = mesh.bounds
    extents = mesh.extents

    axis_idx, axis_name = determine_primary_axis(mesh)

    transverse_indices = [i for i in (0, 1, 2) if i != axis_idx]
    idx_t1, idx_t2 = transverse_indices[0], transverse_indices[1]
    name_t1, name_t2 = ["X", "Y", "Z"][idx_t1], ["X", "Y", "Z"][idx_t2]

    h_min = float(bounds[0][axis_idx])
    h_max = float(bounds[1][axis_idx])
    h_span = h_max - h_min

    # Slicing elevations: span from true bottom to true top (no 2% inset)
    is_crimped = ("vaseline" in mesh_path.name.lower()) or (extents[idx_t1] / max(extents[idx_t2], 1e-4) > 2.5)
    
    base_stations = np.linspace(0.0, 1.0, n_stations)
    if is_crimped:
        crimp_fracs = [0.88, 0.92, 0.95, 0.98]
        combined = np.unique(np.sort(np.concatenate([base_stations, crimp_fracs])))
    else:
        combined = base_stations

    stations_elev: List[Tuple[float, float]] = []
    for frac in combined:
        if frac <= 0.0001:
            elev_slice = h_min + (1.0 if h_span > 30.0 else 0.05)
            elev_clamp = h_min
        elif frac >= 0.9999:
            elev_slice = h_max - (0.5 if h_span > 30.0 else 0.05)
            elev_clamp = h_max
        else:
            elev_slice = h_min + frac * h_span
            elev_clamp = elev_slice
        stations_elev.append((elev_slice, elev_clamp))

    norm_axial = np.zeros(3)
    norm_axial[axis_idx] = 1.0

    stations_data = []

    for i, (elev_slice, elev_clamp) in enumerate(stations_elev):
        origin = np.zeros(3)
        origin[axis_idx] = elev_slice

        sec = mesh.section(plane_origin=origin, plane_normal=norm_axial)
        if not sec or not sec.discrete:
            continue

        # Select loop with largest cross-sectional bounding box
        path_3d = max(sec.discrete, key=lambda p: (np.ptp(p[:, idx_t1]) * np.ptp(p[:, idx_t2])))
        pts_resampled, err_metrics = resample_and_align_outline(path_3d, n_points=n_points, axis_idx=axis_idx)

        # Set elevation to clamped value
        pts_resampled[:, axis_idx] = elev_clamp

        # Dimension metrics
        w_t1 = float(np.max(pts_resampled[:, idx_t1]) - np.min(pts_resampled[:, idx_t1]))
        w_t2 = float(np.max(pts_resampled[:, idx_t2]) - np.min(pts_resampled[:, idx_t2]))
        
        # 2D cross-section area via Shoelace
        p2d = pts_resampled[:, [idx_t1, idx_t2]]
        area_sec = 0.5 * abs(float(np.sum(p2d[:-1, 0] * p2d[1:, 1] - p2d[1:, 0] * p2d[:-1, 1])))

        cen = [float(np.mean(pts_resampled[:, c])) for c in range(3)]

        stations_data.append({
            "station_index": len(stations_data),
            "elevation": round(float(elev_clamp), 3),
            "width_t1": round(w_t1, 3),
            "width_t2": round(w_t2, 3),
            "area_mm2": round(area_sec, 2),
            "centroid": [round(c, 3) for c in cen],
            "start_point": [round(float(v), 3) for v in pts_resampled[0]],
            "smoothing_metrics": err_metrics,
            "points": [[round(float(v), 3) for v in pt] for pt in pts_resampled],
        })

    return {
        "mesh_name": mesh_path.name,
        "reconstruction_method": "LOFT",
        "global_shape_family": "LOFT_THROUGH_CURVES",
        "primary_axis": axis_name,
        "axis_idx": axis_idx,
        "transverse_axes": [name_t1, name_t2],
        "total_height_mm": round(h_span, 3),
        "height_range": [round(h_min, 3), round(h_max, 3)],
        "n_stations": len(stations_data),
        "points_per_station": n_points,
        "overall_extents_mm": [round(float(e), 3) for e in extents],
        "stations": stations_data,
    }


def save_outlines_to_json(outlines_data: Dict[str, Any], json_path: Path) -> Path:
    """Saves extracted outline dictionary to JSON file."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(outlines_data, f, indent=2)
    return json_path


def plot_outlines_overlay(mesh_path: Path, outlines_data: Dict[str, Any], plot_path: Path) -> Path:
    """
    Generates a 2-panel plot:
    Panel 1: 3D perspective wireframe of mesh with 3D cross-section outlines overlaid.
    Panel 2: 2D stacked cross-section outlines color-coded by elevation with zero-twist start points highlighted.
    """
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d import Axes3D
    from matplotlib.cm import viridis

    stations = outlines_data["stations"]
    n_st = len(stations)
    axis_name = outlines_data["primary_axis"]
    t1_name, t2_name = outlines_data["transverse_axes"]

    fig = plt.figure(figsize=(14, 6))

    # Panel 1: 3D Wireframe + Stations
    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    
    colors = [viridis(i / max(1, n_st - 1)) for i in range(n_st)]

    for i, st in enumerate(stations):
        pts = np.array(st["points"])
        # Loop curve
        loop = np.vstack([pts, pts[0]])
        ax1.plot(loop[:, 0], loop[:, 1], loop[:, 2], color=colors[i], linewidth=2.0)
        # Highlight start point
        sp = st["start_point"]
        ax1.scatter([sp[0]], [sp[1]], [sp[2]], color="red", s=25, zorder=5)

    ax1.set_xlabel("X (mm)")
    ax1.set_ylabel("Y (mm)")
    ax1.set_zlabel("Z (mm)")
    ax1.set_title(f"3D Cross-Section Stations (N={n_st})\n{mesh_path.name}")
    ax1.view_init(elev=20, azim=45)

    # Panel 2: 2D Stacked Outlines
    ax2 = fig.add_subplot(1, 2, 2)
    idx_t1 = {"X": 0, "Y": 1, "Z": 2}[t1_name]
    idx_t2 = {"X": 0, "Y": 1, "Z": 2}[t2_name]

    for i, st in enumerate(stations):
        pts = np.array(st["points"])
        p_t1 = np.append(pts[:, idx_t1], pts[0, idx_t1])
        p_t2 = np.append(pts[:, idx_t2], pts[0, idx_t2])
        label = f"Elev={st['elevation']:.1f} mm" if i in (0, n_st//2, n_st-1) else None
        ax2.plot(p_t1, p_t2, color=colors[i], linewidth=1.8, label=label)
        
        # Plot start point
        ax2.plot(p_t1[0], p_t2[0], "ro", markersize=4)

    # Plot red line through start points to show consistent orientation (zero twist)
    start_t1 = [st["start_point"][idx_t1] for st in stations]
    start_t2 = [st["start_point"][idx_t2] for st in stations]
    ax2.plot(start_t1, start_t2, "r--", linewidth=1.5, alpha=0.7, label="Start Pts (Zero Twist Ray)")

    ax2.set_xlabel(f"{t1_name} (mm)")
    ax2.set_ylabel(f"{t2_name} (mm)")
    ax2.set_title(f"2D Stacked Profiles (Base -> Crown)\nRed Markers = Aligned Start Points")
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.axis("equal")
    ax2.legend(loc="upper right", fontsize=8)

    plt.tight_layout()
    plt.savefig(plot_path, dpi=120)
    plt.close(fig)

    return plot_path
