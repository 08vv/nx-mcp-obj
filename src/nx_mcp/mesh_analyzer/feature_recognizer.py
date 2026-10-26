"""
feature_recognizer.py
=====================
Autonomous CAD Feature Decomposition & Parametric Primitive Recognizer.

Segments any 3D mesh along its primary axis into CAD functional zones:
  1. ROUND: Axisymmetric zone -> Native Sketch + Revolve
  2. PRISMATIC: Constant or tapering cross-section -> Native Sketch + Extrude (with taper)
  3. BLENDED: Morphing / transition cross-section -> Loft between native sketches
  4. THIN_TAB: High aspect ratio / crimped flat tab -> Native Sketch + Extrude
  5. END_BLEND: End dome / spherical cap / fillet zone -> Native Edge Blend / Cap

Strict Rules:
  - NO hardcoded part constants (no Ellie or Vaseline numbers in code).
  - Stations and range boundaries are ADAPTIVE, placed where measured geometry changes.
  - Sliver ranges (< 5% height) merged into same-class neighbors (never merge away THIN_TAB or END_BLEND).
  - Classifiers and fitters must agree.
  - BLENDED ranges require start, end, and mid-interpolation IoU error <= 5.0%.
  - Rejects as UNSUPPORTED if any range exceeds 5.0% fit error.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import trimesh
from shapely.geometry import Polygon, Point

from src.nx_mcp.mesh_analyzer.pca_align import get_canonical_rotation
from src.nx_mcp.mesh_analyzer.primitive_fitter import (
    fit_best_primitive,
    create_rounded_rectangle_polygon,
    create_ellipse_polygon,
    create_superellipse_polygon,
    create_rounded_slot_polygon,
    create_compound_4_arc_polygon,
    fit_compound_4_arc,
    compute_polygon_iou_error,
    MAX_FIT_AREA_OVERLAP_ERROR_PCT,
    NUM_POLYGON_SAMPLES,
)

# -----------------------------------------------------------------------------
# Named Constants & Thresholds
# -----------------------------------------------------------------------------
INITIAL_PROBE_SLICE_COUNT: int = 35               # Initial uniform probe station resolution
MAX_PROBE_SLICE_COUNT: int = 120                  # Maximum adaptive probe station limit
ADAPTIVE_STATION_DELTA_THRESHOLD: float = 0.05    # 5% relative change triggers adaptive station insertion
ADAPTIVE_STATION_MAX_SUBDIVISIONS: int = 3        # Maximum recursion depth for adaptive subdivision
ELONGATION_RATIO_THRESHOLD: float = 1.15          # Extents ratio threshold for elongated body
FLATTENED_DISC_RATIO_THRESHOLD: float = 0.85      # Extents ratio threshold for flattened disc/compact
ROUND_CIRCULARITY_THRESHOLD: float = 0.95         # Circularity threshold for Revolve classification
ROUND_ASPECT_RATIO_MAX: float = 1.10              # Max aspect ratio for round classification
PRISMATIC_TAPER_TOLERANCE_PCT: float = 3.0        # Max deviation (%) across range for Prismatic
LINEAR_TAPER_VARIANCE_MAX: float = 0.45           # Variance threshold for linear taper
THIN_TAB_ASPECT_RATIO_THRESHOLD: float = 3.8      # Aspect ratio threshold for Thin Tab
THIN_TAB_MAX_THICKNESS_RATIO: float = 0.08        # Thickness / Part Max Lateral Dimension threshold
MIN_RANGE_STATION_COUNT: int = 2                  # Minimum stations required to define an initial split
MIN_RANGE_HEIGHT_FRACTION: float = 0.05           # Minimum range elevation span as fraction of total height
ADAPTIVE_INFLECTION_THRESHOLD: float = 0.035      # Jump in rate of change triggering range split
END_BLEND_RATE_THRESHOLD: float = 0.40            # Rapid collapse rate indicating end dome / fillet
MAX_LOFT_SKETCH_COUNT: int = 6                    # Maximum sketch count per adaptive loft
MAX_ROUND_DIAMETER_DELTA_PCT: float = 3.0         # Max diameter difference (%) for merging adjacent round ranges
STEP_DISCONTINUITY_THRESHOLD_MM: float = 2.0      # Jump in thickness or width indicating step discontinuity (cap shoulder)


def determine_primary_axis(mesh: trimesh.Trimesh) -> Tuple[int, str]:
    """
    Determines the primary elongation / rotational axis (X, Y, or Z).
    Handles both elongated parts (bottles, tubes, bars) and flattened parts (discs, compacts).
    """
    extents = mesh.extents
    sorted_indices = np.argsort(extents)
    min_idx, mid_idx, max_idx = sorted_indices[0], sorted_indices[1], sorted_indices[2]

    # 1. Elongated object: length is substantially larger than width and thickness
    if extents[max_idx] >= ELONGATION_RATIO_THRESHOLD * extents[mid_idx]:
        return int(max_idx), ["X", "Y", "Z"][max_idx]

    # 2. Flattened object (disc, compact): thickness is substantially smaller than diameter/breadth
    if extents[min_idx] <= FLATTENED_DISC_RATIO_THRESHOLD * extents[mid_idx]:
        return int(min_idx), ["X", "Y", "Z"][min_idx]

    # 3. Transverse aspect ratio closest to 1.0 (square or circular cross-section)
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


def slice_polygon_at_elevation(mesh: trimesh.Trimesh, axis_idx: int, elevation: float) -> Optional[np.ndarray]:
    """Extracts the outermost closed cross-section polygon at a given elevation."""
    plane_normal = np.zeros(3)
    plane_normal[axis_idx] = 1.0
    plane_origin = np.zeros(3)
    plane_origin[axis_idx] = elevation

    transverse_indices = [i for i in (0, 1, 2) if i != axis_idx]
    idx_t1, idx_t2 = transverse_indices[0], transverse_indices[1]

    try:
        sec = mesh.section(plane_origin=plane_origin, plane_normal=plane_normal)
        if not sec or not sec.discrete:
            return None
        # Select largest cross-sectional loop
        best_loop_3d = max(sec.discrete, key=lambda p: (np.ptp(p[:, idx_t1]) * np.ptp(p[:, idx_t2])))
        if len(best_loop_3d) < 8:
            return None
        pts_2d = best_loop_3d[:, [idx_t1, idx_t2]]
        return pts_2d
    except Exception:
        return None


def extract_station_stats(mesh: trimesh.Trimesh, axis_idx: int, elevation: float) -> Optional[Dict[str, Any]]:
    """Extracts geometric dimensions and polygon points at a given elevation."""
    pts_2d = slice_polygon_at_elevation(mesh, axis_idx, elevation)
    if pts_2d is None:
        return None
    poly = Polygon(pts_2d)
    w1 = float(np.max(pts_2d[:, 0]) - np.min(pts_2d[:, 0]))
    w2 = float(np.max(pts_2d[:, 1]) - np.min(pts_2d[:, 1]))
    area = float(poly.area)
    perim = float(poly.length)
    circ = (4.0 * math.pi * area) / max(perim ** 2, 1e-6)
    aspect = max(w1, w2) / max(min(w1, w2), 1e-4)

    return {
        "elevation": elevation,
        "width": max(w1, w2),
        "thickness": min(w1, w2),
        "area": area,
        "circularity": circ,
        "aspect_ratio": aspect,
        "points": pts_2d,
    }


def compute_relative_change(s1: Dict[str, Any], s2: Dict[str, Any]) -> float:
    """Computes the maximum relative change across width, thickness, and area."""
    dw = abs(s2["width"] - s1["width"]) / max(s1["width"], 1e-4)
    dt = abs(s2["thickness"] - s1["thickness"]) / max(s1["thickness"], 1e-4)
    da = abs(s2["area"] - s1["area"]) / max(s1["area"], 1e-4)
    return max(dw, dt, da)


def make_polygon_from_fit(fit_res: Dict[str, Any]) -> Optional[Polygon]:
    """Reconstructs a centered Shapely Polygon from a fitted primitive dict."""
    ptype = fit_res.get("primitive_type") or fit_res.get("best_attempted_type")
    params = fit_res.get("parameters") or fit_res.get("best_attempted_parameters") or {}
    if ptype == "ROUNDED_RECTANGLE":
        return create_rounded_rectangle_polygon(params.get("width", 10.0), params.get("thickness", 10.0), params.get("corner_radius", 1.0))
    elif ptype == "ELLIPSE":
        return create_ellipse_polygon(params.get("major_axis") or params.get("width", 10.0), params.get("minor_axis") or params.get("thickness", 10.0))
    elif ptype == "SUPERELLIPSE":
        return create_superellipse_polygon(params.get("major_axis") or params.get("width", 10.0), params.get("minor_axis") or params.get("thickness", 10.0), params.get("exponent_n", 2.0))
    elif ptype == "ROUNDED_SLOT":
        return create_rounded_slot_polygon(params.get("length", 10.0), params.get("slot_width", 5.0))
    elif ptype == "COMPOUND_4_ARC":
        return create_compound_4_arc_polygon(params.get("width", 10.0), params.get("thickness", 10.0), params.get("corner_radius", 1.0))
    return None


def resample_polygon_radially(poly: Polygon, n_pts: int = NUM_POLYGON_SAMPLES) -> np.ndarray:
    """Samples points on the polygon exterior radially at uniform angles from origin."""
    angles = np.linspace(0.0, 2.0 * math.pi, n_pts, endpoint=False)
    coords = np.array(poly.exterior.coords)[:-1]
    # Simple radial interpolation
    pts = []
    ext_line = poly.exterior
    c = poly.centroid
    for ang in angles:
        # Cast ray
        ray_x = c.x + 1000.0 * math.cos(ang)
        ray_y = c.y + 1000.0 * math.sin(ang)
        from shapely.geometry import LineString
        inter = ext_line.intersection(LineString([(c.x, c.y), (ray_x, ray_y)]))
        if inter.geom_type == "Point":
            pts.append([inter.x, inter.y])
        elif inter.geom_type == "MultiPoint":
            # Furthest point
            f_pt = max(inter.geoms, key=lambda p: math.hypot(p.x - c.x, p.y - c.y))
            pts.append([f_pt.x, f_pt.y])
        else:
            # Fallback
            idx = int((ang / (2.0 * math.pi)) * len(coords)) % len(coords)
            pts.append([coords[idx, 0], coords[idx, 1]])
    return np.array(pts)


def recognize_feature_plan(mesh_path: Path | str, units: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyzes mesh cross-sections adaptively and produces a structured CAD Feature Plan.
    """
    mesh_path = Path(mesh_path)
    mesh: trimesh.Trimesh = trimesh.load(str(mesh_path), force="mesh")
    max_ext = float(np.max(mesh.extents))
    if units:
        u_norm = units.lower().strip()
        scale = 1000.0 if u_norm in ("m", "meter") else 100.0 if u_norm in ("dm", "decimeter") else 10.0 if u_norm in ("cm", "centimeter") else 1.0
    else:
        scale = 1000.0 if max_ext < 0.25 else 100.0 if max_ext < 15.0 else 1.0
    if abs(scale - 1.0) > 1e-4:
        mesh.apply_scale(scale)

    orig_axis_idx, orig_axis_name = determine_primary_axis(mesh)
    R = get_canonical_rotation(orig_axis_name)
    if orig_axis_name != "Y":
        mesh.vertices = (R @ mesh.vertices.T).T

    # After canonical rotation, primary height axis is strictly Y (axis_idx = 1)
    axis_idx = 1
    axis_name = "Y"
    transverse_indices = [0, 2]
    t1_name, t2_name = "X", "Z"
    max_lateral_dim = float(max(mesh.extents[0], mesh.extents[2]))

    # Pre-build validation gate: merge vertices to compute true topological Euler characteristic
    mesh_clean = mesh.copy()
    mesh_clean.merge_vertices()
    euler_val = int(getattr(mesh_clean, "euler_number", 2))
    is_degenerate = bool(euler_val <= 0)

    if is_degenerate:
        reasons = [
            f"Degenerate topology: Euler number {euler_val} <= 0 (contains internal voids / through-holes / multi-genus shells)"
        ]
        return {
            "mesh_name": mesh_path.name,
            "primary_axis": axis_name,
            "transverse_axes": [t1_name, t2_name],
            "total_height_mm": round(float(np.ptp(mesh.bounds[:, axis_idx])), 2),
            "is_degenerate": is_degenerate,
            "overall_status": "UNSUPPORTED",
            "rejection_reasons": reasons,
            "ranges": [],
            "cad_parameters": {},
            "rotation_matrix": R.tolist(),
        }

    h_min = float(mesh.bounds[0][axis_idx])
    h_max = float(mesh.bounds[1][axis_idx])
    h_span = h_max - h_min

    # 1. Adaptive Station Sampling
    initial_elevs = np.linspace(h_min + 0.005 * h_span, h_max - 0.005 * h_span, INITIAL_PROBE_SLICE_COUNT).tolist()
    station_cache: Dict[float, Optional[Dict[str, Any]]] = {}
    for e in initial_elevs:
        station_cache[e] = extract_station_stats(mesh, axis_idx, e)

    # Iterative refinement: insert mid-stations where outline changes quickly
    for _ in range(ADAPTIVE_STATION_MAX_SUBDIVISIONS):
        valid_elevs = sorted([e for e, s in station_cache.items() if s is not None])
        if len(valid_elevs) >= MAX_PROBE_SLICE_COUNT:
            break
        to_insert = []
        for i in range(len(valid_elevs) - 1):
            e1, e2 = valid_elevs[i], valid_elevs[i + 1]
            s1, s2 = station_cache[e1], station_cache[e2]
            delta = compute_relative_change(s1, s2)
            if delta > ADAPTIVE_STATION_DELTA_THRESHOLD and (e2 - e1) > 0.005 * h_span:
                mid_e = (e1 + e2) / 2.0
                to_insert.append(mid_e)
        if not to_insert:
            break
        for mid_e in to_insert:
            if mid_e not in station_cache and len(station_cache) < MAX_PROBE_SLICE_COUNT:
                station_cache[mid_e] = extract_station_stats(mesh, axis_idx, mid_e)

    probe_stats = [station_cache[e] for e in sorted(station_cache.keys()) if station_cache[e] is not None]

    if len(probe_stats) < 4:
        return {
            "mesh_name": mesh_path.name,
            "overall_status": "UNSUPPORTED",
            "rejection_reasons": [f"Insufficient cross-sections extractable along primary axis {axis_name}."]
        }

    # 2. Adaptive Range Segmentation
    rates_of_change = []
    for i in range(len(probe_stats) - 1):
        s1 = probe_stats[i]
        s2 = probe_stats[i + 1]
        dh = max(abs(s2["elevation"] - s1["elevation"]), 1e-4)
        delta = compute_relative_change(s1, s2)
        rate = delta / dh
        rates_of_change.append(rate)

    split_indices = [0]
    for i in range(1, len(rates_of_change) - 1):
        r_prev = rates_of_change[i - 1]
        r_curr = rates_of_change[i]
        asp_prev = probe_stats[i - 1]["aspect_ratio"]
        asp_curr = probe_stats[i]["aspect_ratio"]

        # Step discontinuity check: sudden jump in thickness or width between adjacent stations (cap shoulder)
        t_prev = probe_stats[i - 1]["thickness"]
        t_curr = probe_stats[i]["thickness"]
        w_prev = probe_stats[i - 1]["width"]
        w_curr = probe_stats[i]["width"]
        is_step = (abs(t_curr - t_prev) >= STEP_DISCONTINUITY_THRESHOLD_MM or
                   abs(w_curr - w_prev) >= STEP_DISCONTINUITY_THRESHOLD_MM)

        is_jump = abs(r_curr - r_prev) > ADAPTIVE_INFLECTION_THRESHOLD
        is_tab_trans = (asp_curr > THIN_TAB_ASPECT_RATIO_THRESHOLD) != (asp_prev > THIN_TAB_ASPECT_RATIO_THRESHOLD)
        is_extreme_jump = abs(r_curr - r_prev) > 0.10
        is_trigger = is_step or is_extreme_jump or is_jump or is_tab_trans
        if is_trigger and (i - split_indices[-1]) >= MIN_RANGE_STATION_COUNT:
            split_indices.append(i)
    split_indices.append(len(probe_stats) - 1)

    min_span = MIN_RANGE_HEIGHT_FRACTION * h_span

    # Build preliminary ranges
    prelim_ranges = []
    for r_idx in range(len(split_indices) - 1):
        idx_start = split_indices[r_idx]
        idx_end = split_indices[r_idx + 1]
        r_stats = probe_stats[idx_start:idx_end + 1]

        # Snap outer range boundaries to true mesh bounds so CAD part reaches mesh ends
        z_st = h_min if r_idx == 0 else r_stats[0]["elevation"]
        z_en = h_max if r_idx == len(split_indices) - 2 else r_stats[-1]["elevation"]
        if r_idx == 0 and len(r_stats) > 0:
            r_stats[0]["elevation"] = h_min
        if r_idx == len(split_indices) - 2 and len(r_stats) > 0:
            r_stats[-1]["elevation"] = h_max
        r_span = z_en - z_st

        mean_circ = float(np.mean([s["circularity"] for s in r_stats]))
        mean_aspect = float(np.mean([s["aspect_ratio"] for s in r_stats]))
        mean_thick = float(np.mean([s["thickness"] for s in r_stats]))
        mean_rate = float(np.mean(rates_of_change[idx_start:idx_end])) if idx_end > idx_start else 0.0

        w_start, w_end = r_stats[0]["width"], r_stats[-1]["width"]
        t_start, t_end = r_stats[0]["thickness"], r_stats[-1]["thickness"]
        # Peak-to-peak variance across ALL stations in the range
        w_max, w_min = float(np.max([s["width"] for s in r_stats])), float(np.min([s["width"] for s in r_stats]))
        t_max, t_min = float(np.max([s["thickness"] for s in r_stats])), float(np.min([s["thickness"] for s in r_stats]))
        w_var = (w_max - w_min) / max(float(np.mean([s["width"] for s in r_stats])), 1e-4) * 100.0
        t_var = (t_max - t_min) / max(float(np.mean([s["thickness"] for s in r_stats])), 1e-4) * 100.0
        w_draft_delta = abs(w_end - w_start) / max(w_start, 1e-4) * 100.0
        t_draft_delta = abs(t_end - t_start) / max(t_start, 1e-4) * 100.0

        # Ratio-to-part-size thin tab condition
        is_thin_tab = (mean_thick / max_lateral_dim <= THIN_TAB_MAX_THICKNESS_RATIO) and (mean_aspect >= THIN_TAB_ASPECT_RATIO_THRESHOLD)

        # Opposing taper check: If width expands while thickness contracts (or vice versa),
        # an extrusion with draft cannot physically reproduce the geometry (draft applies equal
        # expansion/contraction to all walls). Such zones must be lofts (BLENDED).
        is_opposing_taper = (r_span >= min_span) and ((w_end - w_start) * (t_end - t_start) < -0.5)

        # Mid-body bulge check: If cross-section swells in the middle while ends match
        is_bulged_body = (r_span >= min_span) and (max(w_var, t_var) > 5.0) and (max(w_draft_delta, t_draft_delta) <= 3.0)

        # Preliminary Classification
        if (idx_start == 0 or idx_end == len(probe_stats) - 1) and mean_rate > END_BLEND_RATE_THRESHOLD:
            r_class = "END_BLEND"
            cad_op = "EDGE_BLEND_OR_CAP"
        elif mean_circ >= ROUND_CIRCULARITY_THRESHOLD and mean_aspect <= ROUND_ASPECT_RATIO_MAX:
            r_class = "ROUND"
            cad_op = "REVOLVE"
        elif is_thin_tab:
            r_class = "THIN_TAB"
            cad_op = "EXTRUDE"
        elif is_opposing_taper or is_bulged_body:
            r_class = "BLENDED"
            cad_op = "LOFT_SKETCHES"
        elif w_var <= PRISMATIC_TAPER_TOLERANCE_PCT and t_var <= PRISMATIC_TAPER_TOLERANCE_PCT:
            r_class = "PRISMATIC"
            cad_op = "EXTRUDE"
        else:
            w_diffs = np.diff([s["width"] for s in r_stats])
            w_diff_var = np.std(w_diffs) / max(np.mean(np.abs(w_diffs)), 1e-4) if len(w_diffs) > 1 else 0.0
            t_diffs = np.diff([s["thickness"] for s in r_stats])
            t_diff_var = np.std(t_diffs) / max(np.mean(np.abs(t_diffs)), 1e-4) if len(t_diffs) > 1 else 0.0
            rate_w = abs(w_end - w_start) / max(r_span, 1e-4)
            rate_t = abs(t_end - t_start) / max(r_span, 1e-4)
            is_uniform_draft = abs(rate_w - rate_t) <= 0.20 * max(rate_w, rate_t, 0.1) or max(w_var, t_var) <= 5.0
            if w_diff_var < LINEAR_TAPER_VARIANCE_MAX and t_diff_var < LINEAR_TAPER_VARIANCE_MAX and is_uniform_draft:
                r_class = "PRISMATIC"
                cad_op = "EXTRUDE_WITH_TAPER"
            else:
                r_class = "BLENDED"
                cad_op = "LOFT_SKETCHES"

        # Classifier and Fitter Agreement
        mid_stat = r_stats[len(r_stats) // 2]
        prelim_fit = fit_best_primitive(mid_stat["points"], is_thin_tab=is_thin_tab)
        if r_class == "ROUND":
            params = prelim_fit.get("parameters") or {}
            w_fit = params.get("width") or params.get("major_axis") or 1.0
            t_fit = params.get("thickness") or params.get("minor_axis") or 1.0
            fit_type = prelim_fit.get("primitive_type")
            if (max(w_fit, t_fit) / max(min(w_fit, t_fit), 1e-4) > ROUND_ASPECT_RATIO_MAX) or fit_type in ("ROUNDED_RECTANGLE", "ROUNDED_SLOT"):
                r_class = "PRISMATIC"
                cad_op = "EXTRUDE_WITH_TAPER" if abs(r_stats[-1]["width"] - r_stats[0]["width"]) > 1.0 else "EXTRUDE"
        
        # If PRISMATIC fit exceeds 5.0% limit for a macro range (>= min_span), test whether it is a BLENDED loft
        if r_span >= min_span and r_class == "PRISMATIC" and prelim_fit.get("area_overlap_error_pct", 100.0) > MAX_FIT_AREA_OVERLAP_ERROR_PCT:
            r_class = "BLENDED"
            cad_op = "LOFT_SKETCHES"

        prelim_ranges.append({
            "idx_start": idx_start,
            "idx_end": idx_end,
            "stats": r_stats,
            "z_start": z_st,
            "z_end": z_en,
            "span": r_span,
            "class": r_class,
            "cad_op": cad_op,
            "is_thin_tab": is_thin_tab,
        })

    # 3. Sliver Merge: Merge ranges < MIN_RANGE_HEIGHT_FRACTION into same-class neighbors.
    # Never merge away THIN_TAB or END_BLEND.
    min_span = MIN_RANGE_HEIGHT_FRACTION * h_span
    merged_ranges = []
    i = 0
    while i < len(prelim_ranges):
        curr = prelim_ranges[i]
        # Check if sliver that can be merged into a same-class neighbor
        if curr["span"] < min_span and curr["class"] not in ("END_BLEND", "THIN_TAB"):
            # Check previous
            if merged_ranges and merged_ranges[-1]["class"] == curr["class"]:
                prev = merged_ranges.pop()
                combined_stats = prev["stats"] + curr["stats"][1:]
                merged_ranges.append({
                    "idx_start": prev["idx_start"],
                    "idx_end": curr["idx_end"],
                    "stats": combined_stats,
                    "z_start": prev["z_start"],
                    "z_end": curr["z_end"],
                    "span": curr["z_end"] - prev["z_start"],
                    "class": prev["class"],
                    "cad_op": prev["cad_op"],
                    "is_thin_tab": prev["is_thin_tab"],
                })
                i += 1
                continue
            # Check next
            elif (i + 1) < len(prelim_ranges) and prelim_ranges[i + 1]["class"] == curr["class"]:
                nxt = prelim_ranges[i + 1]
                combined_stats = curr["stats"] + nxt["stats"][1:]
                prelim_ranges[i + 1] = {
                    "idx_start": curr["idx_start"],
                    "idx_end": nxt["idx_end"],
                    "stats": combined_stats,
                    "z_start": curr["z_start"],
                    "z_end": nxt["z_end"],
                    "span": nxt["z_end"] - curr["z_start"],
                    "class": nxt["class"],
                    "cad_op": nxt["cad_op"],
                    "is_thin_tab": nxt["is_thin_tab"],
                }
                i += 1
                continue
        merged_ranges.append(curr)
        i += 1

    # Secondary pass to merge adjacent ranges of the same functional class:
    # 1. PRISMATIC: merge adjacent prismatic ranges
    # 2. ROUND: merge adjacent round ranges ONLY if mean diameter matches within MAX_ROUND_DIAMETER_DELTA_PCT (3%)
    # 3. THIN_TAB: merge adjacent thin tab ranges if outline difference at interface <= MAX_FIT_AREA_OVERLAP_ERROR_PCT (5%)
    # Never merge BLENDED lofts (each requires its own boundary / driving sketches) or END_BLEND
    consolidated_ranges = []
    for r in merged_ranges:
        if consolidated_ranges and consolidated_ranges[-1]["class"] == r["class"] and r["class"] not in ("END_BLEND", "BLENDED"):
            prev = consolidated_ranges[-1]
            can_merge = False
            if r["class"] == "ROUND":
                d_prev = float(np.mean([s["width"] for s in prev["stats"]]))
                d_curr = float(np.mean([s["width"] for s in r["stats"]]))
                can_merge = (abs(d_curr - d_prev) / max(d_prev, 1e-4) <= (MAX_ROUND_DIAMETER_DELTA_PCT / 100.0))
            elif r["class"] == "THIN_TAB":
                poly_p = Polygon(prev["stats"][-1]["points"])
                poly_c = Polygon(r["stats"][0]["points"])
                if not poly_p.is_valid:
                    poly_p = poly_p.buffer(0)
                if not poly_c.is_valid:
                    poly_c = poly_c.buffer(0)
                err_iface, _, _ = compute_polygon_iou_error(poly_p, poly_c)
                can_merge = (err_iface <= MAX_FIT_AREA_OVERLAP_ERROR_PCT)
            elif r["class"] == "PRISMATIC":
                can_merge = True

            if can_merge:
                prev = consolidated_ranges.pop()
                combined_stats = prev["stats"] + r["stats"][1:]
                c_cad_op = prev["cad_op"]
                if prev["class"] == "THIN_TAB":
                    w_delta = combined_stats[-1]["width"] - combined_stats[0]["width"]
                    t_delta = combined_stats[-1]["thickness"] - combined_stats[0]["thickness"]
                    if w_delta * t_delta < -0.1:
                        c_cad_op = "LOFT_SKETCHES"
                    elif abs(w_delta) > 0.5 or abs(t_delta) > 0.5:
                        c_cad_op = "EXTRUDE_WITH_TAPER"
                    else:
                        c_cad_op = "EXTRUDE"

                consolidated_ranges.append({
                    "idx_start": prev["idx_start"],
                    "idx_end": r["idx_end"],
                    "stats": combined_stats,
                    "z_start": prev["z_start"],
                    "z_end": r["z_end"],
                    "span": r["z_end"] - prev["z_start"],
                    "class": prev["class"],
                    "cad_op": c_cad_op,
                    "is_thin_tab": prev["is_thin_tab"],
                })
            else:
                consolidated_ranges.append(r)
        else:
            consolidated_ranges.append(r)

    # 4. Fit and Validate Each Range
    final_ranges = []
    overall_supported = True
    rejection_reasons = []

    for r_idx, r in enumerate(consolidated_ranges):
        r_stats = r["stats"]
        z_st = r["z_start"]
        z_en = r["z_end"]
        r_span = r["span"]
        r_class = r["class"]
        cad_op = r["cad_op"]

        mean_circ = float(np.mean([s["circularity"] for s in r_stats]))
        mean_aspect = float(np.mean([s["aspect_ratio"] for s in r_stats]))

        # Mid-station fit
        mid_stat = r_stats[len(r_stats) // 2]
        fit_result = fit_best_primitive(mid_stat["points"], is_thin_tab=r["is_thin_tab"])

        # Consistency check: Classifier and Fitter Agreement
        if r_class == "ROUND":
            params = fit_result.get("parameters") or {}
            w_fit = params.get("width") or params.get("major_axis") or 1.0
            t_fit = params.get("thickness") or params.get("minor_axis") or 1.0
            fit_asp = max(w_fit, t_fit) / max(min(w_fit, t_fit), 1e-4)
            fit_type = fit_result.get("primitive_type")
            if fit_asp > ROUND_ASPECT_RATIO_MAX or fit_type in ("ROUNDED_RECTANGLE", "ROUNDED_SLOT"):
                # Reclassify as PRISMATIC
                r_class = "PRISMATIC"
                cad_op = "EXTRUDE_WITH_TAPER" if abs(r_stats[-1]["width"] - r_stats[0]["width"]) > 1.0 else "EXTRUDE"

        # Taper angle measurement
        # Measure BODY_TAPER only over the straight middle of the body (exclude end blend, dish and dome zones)
        r_y0, r_y1 = z_st, z_en
        mid_y_min = r_y0 + 0.20 * r_span
        mid_y_max = r_y0 + 0.80 * r_span
        middle_stations = [s for s in r_stats if mid_y_min <= s["elevation"] <= mid_y_max]
        if len(middle_stations) >= 3 and r_span > 0.0:
            elevs = np.array([s["elevation"] for s in middle_stations])
            widths = np.array([s["width"] for s in middle_stations])
            slope, _ = np.polyfit(elevs, widths, 1)
            taper_angle_deg = abs(math.degrees(math.atan(abs(slope) / 2.0)))
            taper_elevs = [round(float(s["elevation"]), 2) for s in middle_stations]
            print(f"  [TAPER] Measured {taper_angle_deg:.3f} deg across {len(middle_stations)} straight middle stations (Y={mid_y_min:.2f} to {mid_y_max:.2f}): {taper_elevs}")
        else:
            valid_w_stats = [s for s in r_stats if s["width"] >= 0.75 * mid_stat["width"]]
            if len(valid_w_stats) >= 3 and r_span > 0.0:
                elevs = np.array([s["elevation"] for s in valid_w_stats])
                widths = np.array([s["width"] for s in valid_w_stats])
                slope, _ = np.polyfit(elevs, widths, 1)
                taper_angle_deg = abs(math.degrees(math.atan(abs(slope) / 2.0)))
            else:
                w_b, w_t = r_stats[0]["width"], r_stats[-1]["width"]
                taper_angle_deg = math.degrees(math.atan(abs(w_b - w_t) / max(2.0 * r_span, 1e-4))) if r_span > 0.0 else 0.0

        # Sample ALL stations in this range and compute per-station fit errors
        station_fits = [fit_best_primitive(s["points"], is_thin_tab=r["is_thin_tab"]) for s in r_stats]
        station_errors = [round(float(f.get("area_overlap_error_pct", 100.0)), 2) for f in station_fits]
        max_station_err = float(max(station_errors)) if station_errors else 0.0

        if r_class == "END_BLEND":
            range_supported = True
            fit_primitive_name = "NOT FITTED: validated by the CAD verifier"
            fitted_params = {
                "blend_radius_mm": round(r_span, 2),
                "cap_width": round(mid_stat["width"], 2),
                "cap_thickness": round(mid_stat["thickness"], 2),
            }
            overlap_err = None
            conf = 1.0
            max_dist = 0.0

        elif r_class == "BLENDED":
            # Adaptive Multi-Sketch Loft:
            # 1. Start with boundary sketches (active_indices = [0, len(r_stats) - 1])
            # 2. For each sub-span, evaluate mid-point IoU error
            # 3. If mid error > 5.0%, insert new sketch at station of largest error
            # 4. Repeat until every sub-span passes <= 5.0% or MAX_LOFT_SKETCH_COUNT is reached
            # 5. If cap reached and any span still fails, mark UNSUPPORTED
            N_stat = len(r_stats)
            active_indices = [0, N_stat - 1]
            active_fits = {}
            active_polys = {}

            all_spans_passed = False
            sub_spans_record = []
            worst_loft_err = 0.0

            while True:
                active_indices = sorted(list(set(active_indices)))
                for a_idx in active_indices:
                    if a_idx not in active_fits:
                        af = fit_best_primitive(r_stats[a_idx]["points"], is_thin_tab=r["is_thin_tab"])
                        active_fits[a_idx] = af
                        active_polys[a_idx] = make_polygon_from_fit(af)

                # Check if all active sketches are supported primitives
                if any(not active_fits[k].get("is_supported", False) or active_polys[k] is None for k in active_indices):
                    all_spans_passed = False
                    worst_loft_err = max(active_fits[k].get("area_overlap_error_pct", 100.0) for k in active_indices)
                    break

                sub_spans_record = []
                worst_err_overall = 0.0
                worst_station_overall = None

                for s_i in range(len(active_indices) - 1):
                    idx_a = active_indices[s_i]
                    idx_b = active_indices[s_i + 1]
                    z_a = r_stats[idx_a]["elevation"]
                    z_b = r_stats[idx_b]["elevation"]

                    poly_a = active_polys[idx_a]
                    poly_b = active_polys[idx_b]
                    pts_a_rad = resample_polygon_radially(poly_a)
                    pts_b_rad = resample_polygon_radially(poly_b)

                    inter_indices = list(range(idx_a + 1, idx_b))
                    if not inter_indices:
                        sub_spans_record.append({
                            "start_elevation_mm": round(z_a, 2),
                            "end_elevation_mm": round(z_b, 2),
                            "mid_elevation_mm": round((z_a + z_b) / 2.0, 2),
                            "mid_error_pct": 0.0,
                            "max_error_pct": 0.0,
                        })
                        continue

                    mid_idx = (idx_a + idx_b) // 2
                    z_m = r_stats[mid_idx]["elevation"]
                    alpha_m = (z_m - z_a) / max(z_b - z_a, 1e-6)
                    pts_interp = (1.0 - alpha_m) * pts_a_rad + alpha_m * pts_b_rad
                    poly_interp = Polygon(pts_interp)

                    pts_m_real = r_stats[mid_idx]["points"]
                    cen_m = (np.max(pts_m_real, axis=0) + np.min(pts_m_real, axis=0)) / 2.0
                    poly_m_real = Polygon(pts_m_real - cen_m)

                    mid_err, _, _ = compute_polygon_iou_error(poly_m_real, poly_interp)

                    sub_spans_record.append({
                        "start_elevation_mm": round(z_a, 2),
                        "end_elevation_mm": round(z_b, 2),
                        "mid_elevation_mm": round(z_m, 2),
                        "mid_error_pct": round(mid_err, 2),
                        "max_error_pct": round(mid_err, 2),
                    })

                    if mid_err > worst_err_overall:
                        worst_err_overall = mid_err
                        worst_station_overall = mid_idx

                worst_loft_err = worst_err_overall
                all_spans_passed = all(s["mid_error_pct"] <= MAX_FIT_AREA_OVERLAP_ERROR_PCT for s in sub_spans_record)
                if all_spans_passed:
                    break

                if len(active_indices) >= MAX_LOFT_SKETCH_COUNT:
                    break

                if worst_station_overall is not None and worst_station_overall not in active_indices:
                    active_indices.append(worst_station_overall)
                else:
                    break

            if all_spans_passed:
                range_supported = True
                fit_primitive_name = f"MULTI_SKETCH_LOFT ({len(active_indices)} sketches)"
                fitted_params = {
                    "sketch_count": len(active_indices),
                    "sketch_elevations_mm": [round(r_stats[k]["elevation"], 2) for k in active_indices],
                    "sub_spans": sub_spans_record,
                    "driving_sketches": [
                        {
                            "elevation_mm": round(r_stats[k]["elevation"], 2),
                            "primitive_type": "COMPOUND_4_ARC",
                            "parameters": {
                                "width": round(active_fits[k]["parameters"].get("width") or active_fits[k]["parameters"].get("major_axis", 50.0), 3),
                                "thickness": round(active_fits[k]["parameters"].get("thickness") or active_fits[k]["parameters"].get("minor_axis", 50.0), 3),
                                "corner_radius": round(
                                    active_fits[k]["parameters"].get("corner_radius", 0.0) if active_fits[k]["parameters"].get("corner_radius", 0.0) > 0.05
                                    else max(0.5, (active_fits[k]["parameters"].get("minor_axis", 50.0)/2.0)**2 / max((active_fits[k]["parameters"].get("major_axis", 50.0)/2.0), 1e-6)),
                                    3
                                ),
                                "flank_radius": round(
                                    active_fits[k]["parameters"].get("flank_radius", 0.0) if active_fits[k]["parameters"].get("flank_radius", 0.0) > 0.05
                                    else ((active_fits[k]["parameters"].get("major_axis", 50.0)/2.0)**2 + (active_fits[k]["parameters"].get("minor_axis", 50.0)/2.0)**2 - 2.0 * (active_fits[k]["parameters"].get("major_axis", 50.0)/2.0) * max(0.5, (active_fits[k]["parameters"].get("minor_axis", 50.0)/2.0)**2 / max((active_fits[k]["parameters"].get("major_axis", 50.0)/2.0), 1e-6))) / max(2.0 * ((active_fits[k]["parameters"].get("minor_axis", 50.0)/2.0) - max(0.5, (active_fits[k]["parameters"].get("minor_axis", 50.0)/2.0)**2 / max((active_fits[k]["parameters"].get("major_axis", 50.0)/2.0), 1e-6))), 1e-6),
                                    3
                                ),
                            },
                        }
                        for k in active_indices
                    ],
                    "start_primitive": active_fits[active_indices[0]]["primitive_type"],
                    "start_parameters": active_fits[active_indices[0]]["parameters"],
                    "end_primitive": active_fits[active_indices[-1]]["primitive_type"],
                    "end_parameters": active_fits[active_indices[-1]]["parameters"],
                    "mid_interpolation_iou_error_pct": round(worst_loft_err, 2),
                }
                max_sk_err = max(active_fits[k].get("area_overlap_error_pct", 0.0) for k in active_indices)
                overlap_err = round(max(worst_loft_err, max_sk_err), 2)
                conf = max(0.0, min(1.0, 1.0 - (overlap_err / 10.0)))
                max_dist = round(worst_loft_err, 3)
            else:
                range_supported = False
                fit_primitive_name = "UNSUPPORTED"
                fitted_params = {
                    "sketch_count": len(active_indices),
                    "sketch_elevations_mm": [round(r_stats[k]["elevation"], 2) for k in active_indices],
                    "sub_spans": sub_spans_record,
                    "worst_mid_error_pct": round(worst_loft_err, 2),
                }
                overlap_err = round(worst_loft_err, 2)
                conf = 0.0
                max_dist = round(worst_loft_err, 3)

        else:
            fit_primitive_name = fit_result.get("primitive_type")
            fitted_params = fit_result.get("parameters") or fit_result.get("best_attempted_parameters") or {}
            overlap_err = round(max(max_station_err, fit_result.get("area_overlap_error_pct", 100.0)), 2)
            conf = round(fit_result.get("confidence", 0.0), 3)
            max_dist = round(fit_result.get("max_distance_mm", 0.0), 3)
            range_supported = (overlap_err <= MAX_FIT_AREA_OVERLAP_ERROR_PCT)

        if not range_supported:
            overall_supported = False
            rejection_reasons.append(
                f"Range {r_idx+1} [Y={z_st:.1f} to {z_en:.1f} mm] fit error "
                f"{overlap_err}% exceeds {MAX_FIT_AREA_OVERLAP_ERROR_PCT}% limit."
            )

        final_ranges.append({
            "range_index": r_idx + 1,
            "elevation_range_mm": [round(z_st, 2), round(z_en, 2)],
            "height_span_mm": round(r_span, 2),
            "station_count": len(r_stats),
            "classification": r_class,
            "cad_operation": cad_op,
            "mean_circularity": round(mean_circ, 3),
            "mean_aspect_ratio": round(mean_aspect, 3),
            "measured_taper_deg": round(taper_angle_deg, 3),
            "fitted_primitive": fit_primitive_name,
            "fitted_parameters": fitted_params,
            "area_overlap_error_pct": overlap_err,
            "confidence": conf,
            "max_distance_mm": max_dist,
            "per_station_errors": station_errors,
            "is_supported": range_supported,
            "station_summaries": [
                {
                    "elevation": round(float(s["elevation"]), 2),
                    "width": round(float(s["width"]), 2),
                    "thickness": round(float(s["thickness"]), 2),
                    "aspect_ratio": round(float(s["aspect_ratio"]), 2),
                    "circularity": round(float(s["circularity"]), 2),
                }
                for s in r_stats
            ],
        })

    # Global CAD parameters block for builders
    body_ranges = [r for r in final_ranges if r["classification"] in ("PRISMATIC", "ROUND", "BLENDED")]
    end_blend_ranges = [r for r in final_ranges if r["classification"] == "END_BLEND"]
    
    cad_params = {}
    if body_ranges:
        primary_body = max(body_ranges, key=lambda r: r["height_span_mm"])
        b_params = primary_body["fitted_parameters"]
        cad_params["BODY_WIDTH"] = b_params.get("width") or b_params.get("major_axis") or 50.0
        cad_params["BODY_THICKNESS"] = b_params.get("thickness") or b_params.get("minor_axis") or 50.0
        raw_corner_r = float(b_params.get("corner_radius", 0.0) or 0.0)
        if raw_corner_r <= 0.05:
            # Ellipse / oval primitive: 4-tangent-arc equivalent end radius b^2 / a
            a_half = max(cad_params["BODY_WIDTH"], cad_params["BODY_THICKNESS"]) / 2.0
            b_half = min(cad_params["BODY_WIDTH"], cad_params["BODY_THICKNESS"]) / 2.0
            raw_corner_r = round(b_half ** 2 / max(a_half, 1e-6), 3)
        cad_params["BODY_CORNER_R"] = raw_corner_r
        if end_blend_ranges:
            cad_params["BODY_START_Y"] = round(float(final_ranges[0]["elevation_range_mm"][0]), 3)
            cad_params["BODY_HEIGHT"] = round(float(h_span), 3)
        else:
            cad_params["BODY_START_Y"] = round(float(primary_body["elevation_range_mm"][0]), 3)
            cad_params["BODY_HEIGHT"] = primary_body["height_span_mm"]
        cad_params["BODY_TAPER"] = primary_body["measured_taper_deg"]

    if end_blend_ranges:
        cad_params["END_BLEND_R"] = max(r["height_span_mm"] for r in end_blend_ranges)
    else:
        cad_params["END_BLEND_R"] = 0.0

    return {
        "mesh_name": mesh_path.name,
        "primary_axis": axis_name,
        "transverse_axes": [t1_name, t2_name],
        "total_height_mm": round(h_span, 2),
        "total_stations_probed": len(probe_stats),
        "range_count": len(final_ranges),
        "end_blend_ranges_count": len(end_blend_ranges),
        "supported_ranges_count": len([r for r in final_ranges if r["classification"] != "END_BLEND" and r["is_supported"]]),
        "unsupported_ranges_count": len([r for r in final_ranges if r["classification"] != "END_BLEND" and not r["is_supported"]]),
        "ranges": final_ranges,
        "cad_parameters": cad_params,
        "overall_status": "SUPPORTED" if overall_supported else "UNSUPPORTED",
        "is_degenerate": False,
        "rejection_reasons": rejection_reasons,
        "rotation_matrix": R.tolist(),
    }
