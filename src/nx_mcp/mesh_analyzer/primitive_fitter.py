"""
primitive_fitter.py
===================
Fits parametric 2D cross-section primitives to raw mesh cross-sections:
  1. Rounded Rectangle: width (W), thickness (T), corner radius (R)
  2. Ellipse / Oval: major axis (A), minor axis (B)
  3. Superellipse / Squircle: major axis (A), minor axis (B), exponent (N)
  4. Rounded Slot / Stadium: length (L), cap radius (R)

Strictly non-negotiable rules:
  - Every threshold is a named constant.
  - No part-specific constants (no Ellie or Vaseline numbers in code).
  - Corner radius and primitive dimensions are fit by DIRECT DISTANCE / IoU
    MINIMIZATION between candidate outline boundary and real section points.
  - Rejects with 'UNSUPPORTED' if area overlap error exceeds 5.0%.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize_scalar, minimize
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union

# -----------------------------------------------------------------------------
# Named Constants & Thresholds
# -----------------------------------------------------------------------------
MAX_FIT_AREA_OVERLAP_ERROR_PCT: float = 5.0   # Non-negotiable max error threshold (%)
CONFIDENCE_HIGH_THRESHOLD: float = 0.95       # High confidence marker
MIN_CORNER_RADIUS_MM: float = 0.1             # Below this is treated as sharp corner
NUM_POLYGON_SAMPLES: int = 128                # Polygonal discretization resolution
SUPERELLIPSE_MIN_EXPONENT: float = 1.6        # Minimum superellipse exponent
SUPERELLIPSE_MAX_EXPONENT: float = 8.0        # Maximum superellipse exponent
OPTIMIZATION_TOLERANCE: float = 1e-3          # Numerical optimization convergence tolerance


def create_rounded_rectangle_polygon(width: float, thickness: float, radius: float, num_pts: int = NUM_POLYGON_SAMPLES) -> Polygon:
    """Generates a Shapely Polygon for a centered rounded rectangle."""
    w = max(width, 1e-4)
    t = max(thickness, 1e-4)
    max_r = min(w, t) / 2.0 - 1e-4
    r = max(0.0, min(radius, max_r))

    if r < MIN_CORNER_RADIUS_MM:
        # Sharp rectangle
        hw, ht = w / 2.0, t / 2.0
        return Polygon([(-hw, -ht), (hw, -ht), (hw, ht), (-hw, ht)])

    # Rounded rectangle centered at origin
    pts = []
    pts_per_corner = max(8, num_pts // 4)
    corners = [
        (w / 2.0 - r, t / 2.0 - r, 0.0, math.pi / 2.0),
        (-w / 2.0 + r, t / 2.0 - r, math.pi / 2.0, math.pi),
        (-w / 2.0 + r, -t / 2.0 + r, math.pi, 1.5 * math.pi),
        (w / 2.0 - r, -t / 2.0 + r, 1.5 * math.pi, 2.0 * math.pi),
    ]
    for cx, cy, start_ang, end_ang in corners:
        angles = np.linspace(start_ang, end_ang, pts_per_corner, endpoint=False)
        for ang in angles:
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return Polygon(pts)


def create_ellipse_polygon(axis_a: float, axis_b: float, num_pts: int = NUM_POLYGON_SAMPLES) -> Polygon:
    """Generates a Shapely Polygon for a centered ellipse with full width A and thickness B."""
    ra = max(axis_a / 2.0, 1e-4)
    rb = max(axis_b / 2.0, 1e-4)
    angles = np.linspace(0.0, 2.0 * math.pi, num_pts, endpoint=False)
    pts = [(ra * math.cos(ang), rb * math.sin(ang)) for ang in angles]
    return Polygon(pts)


def create_superellipse_polygon(axis_a: float, axis_b: float, n_exp: float, num_pts: int = NUM_POLYGON_SAMPLES) -> Polygon:
    """
    Generates a Shapely Polygon for a centered superellipse (|x/a|^n + |y/b|^n <= 1).
    """
    ra = max(axis_a / 2.0, 1e-4)
    rb = max(axis_b / 2.0, 1e-4)
    n = max(SUPERELLIPSE_MIN_EXPONENT, min(n_exp, SUPERELLIPSE_MAX_EXPONENT))
    angles = np.linspace(0.0, 2.0 * math.pi, num_pts, endpoint=False)
    pts = []
    for ang in angles:
        c, s = math.cos(ang), math.sin(ang)
        x = ra * math.copysign(abs(c) ** (2.0 / n), c)
        y = rb * math.copysign(abs(s) ** (2.0 / n), s)
        pts.append((x, y))
    return Polygon(pts)


def create_rounded_slot_polygon(length: float, width: float, num_pts: int = NUM_POLYGON_SAMPLES) -> Polygon:
    """Generates a Shapely Polygon for a stadium / rounded slot."""
    l = max(length, 1e-4)
    w = max(width, 1e-4)
    if l >= w:
        r = w / 2.0
        straight_l = l - 2.0 * r
        if straight_l <= 1e-4:
            return create_ellipse_polygon(l, w, num_pts)
        pts = []
        n_cap = max(8, num_pts // 2)
        # Right semicircular cap
        cx_r = straight_l / 2.0
        for ang in np.linspace(-math.pi / 2.0, math.pi / 2.0, n_cap):
            pts.append((cx_r + r * math.cos(ang), r * math.sin(ang)))
        # Left semicircular cap
        cx_l = -straight_l / 2.0
        for ang in np.linspace(math.pi / 2.0, 1.5 * math.pi, n_cap):
            pts.append((cx_l + r * math.cos(ang), r * math.sin(ang)))
        return Polygon(pts)
    else:
        # Vertical slot
        r = l / 2.0
        straight_h = w - 2.0 * r
        pts = []
        n_cap = max(8, num_pts // 2)
        # Top cap
        cy_t = straight_h / 2.0
        for ang in np.linspace(0.0, math.pi, n_cap):
            pts.append((r * math.cos(ang), cy_t + r * math.sin(ang)))
        # Bottom cap
        cy_b = -straight_h / 2.0
        for ang in np.linspace(math.pi, 2.0 * math.pi, n_cap):
            pts.append((r * math.cos(ang), cy_b + r * math.sin(ang)))
        return Polygon(pts)


def distance_point_to_rounded_box(pt: Tuple[float, float], w: float, t: float, r: float) -> float:
    """
    Exact closed-form signed/Euclidean distance from point (x, y) to the boundary
    of a centered rounded rectangle with width w, thickness t, and corner radius r.
    """
    x, y = abs(pt[0]), abs(pt[1])
    hw, ht = w / 2.0, t / 2.0
    r = max(0.0, min(r, min(hw, ht) - 1e-4))
    x0, y0 = hw - r, ht - r

    if x <= x0 and y <= ht:
        return abs(y - ht)
    elif y <= y0 and x <= hw:
        return abs(x - hw)
    elif x > x0 and y > y0:
        # Distance to corner circular arc
        dist_to_center = math.hypot(x - x0, y - y0)
        return abs(dist_to_center - r)
    else:
        # Point outside bounding box
        dx = max(0.0, x - x0)
        dy = max(0.0, y - y0)
        dist_to_center = math.hypot(dx, dy)
        return abs(dist_to_center - r)


def compute_polygon_iou_error(poly_raw: Polygon, poly_candidate: Polygon) -> Tuple[float, float, float]:
    """
    Computes Intersection-over-Union (IoU) error percentage and area deviation.
    Returns: (area_overlap_error_pct, area_dev_pct, iou)
    """
    if not poly_raw.is_valid:
        poly_raw = poly_raw.buffer(0)
    if not poly_candidate.is_valid:
        poly_candidate = poly_candidate.buffer(0)

    area_raw = poly_raw.area
    area_cand = poly_candidate.area

    if area_raw <= 1e-6 or area_cand <= 1e-6:
        return 100.0, 100.0, 0.0

    try:
        inter = poly_raw.intersection(poly_candidate).area
        union = poly_raw.union(poly_candidate).area
        iou = inter / max(union, 1e-6)
        overlap_error_pct = (1.0 - iou) * 100.0
    except Exception:
        # Fallback to symmetric difference approximation
        sym_diff = poly_raw.symmetric_difference(poly_candidate).area
        overlap_error_pct = (sym_diff / max(area_raw, 1e-6)) * 100.0
        iou = max(0.0, 1.0 - overlap_error_pct / 100.0)

    area_dev_pct = abs(area_cand - area_raw) / max(area_raw, 1e-6) * 100.0
    return overlap_error_pct, area_dev_pct, iou


def fit_rounded_rectangle(points_2d: np.ndarray) -> Dict[str, Any]:
    """
    Fits a rounded rectangle to 2D cross-section points by minimizing the
    mean Euclidean distance from the section points to the candidate boundary over R.
    """
    cen = (np.max(points_2d, axis=0) + np.min(points_2d, axis=0)) / 2.0
    pts = points_2d - cen
    raw_poly = Polygon(pts)
    if not raw_poly.is_valid:
        raw_poly = raw_poly.buffer(0)

    w = float(np.max(pts[:, 0]) - np.min(pts[:, 0]))
    t = float(np.max(pts[:, 1]) - np.min(pts[:, 1]))
    max_r = min(w, t) / 2.0 - 1e-3

    if max_r <= MIN_CORNER_RADIUS_MM:
        best_r = 0.0
    else:
        # Objective: minimize sum of squared distances to candidate rounded boundary
        def objective(cand_r: float) -> float:
            dists = [distance_point_to_rounded_box(p, w, t, cand_r) for p in pts]
            return float(np.mean(np.array(dists) ** 2))

        res = minimize_scalar(objective, bounds=(0.0, max_r), method="bounded", options={"xatol": OPTIMIZATION_TOLERANCE})
        best_r = float(res.x)

    cand_poly = create_rounded_rectangle_polygon(w, t, best_r)
    overlap_err, area_dev, iou = compute_polygon_iou_error(raw_poly, cand_poly)

    # Compute max Euclidean distance
    dists = [distance_point_to_rounded_box(p, w, t, best_r) for p in pts]
    max_dist = float(np.max(dists))
    confidence = max(0.0, min(1.0, 1.0 - (overlap_err / 10.0)))

    return {
        "primitive_type": "ROUNDED_RECTANGLE",
        "parameters": {
            "width": round(w, 3),
            "thickness": round(t, 3),
            "corner_radius": round(best_r, 3),
        },
        "area_overlap_error_pct": round(overlap_err, 2),
        "area_deviation_pct": round(area_dev, 2),
        "max_distance_mm": round(max_dist, 3),
        "iou": round(iou, 4),
        "confidence": round(confidence, 3),
        "is_supported": overlap_err <= MAX_FIT_AREA_OVERLAP_ERROR_PCT,
    }


def fit_ellipse(points_2d: np.ndarray) -> Dict[str, Any]:
    """
    Fits an ellipse / oval to 2D cross-section points by minimizing
    the boundary distance / IoU area overlap error over semi-axes (a, b).
    """
    cen = (np.max(points_2d, axis=0) + np.min(points_2d, axis=0)) / 2.0
    pts = points_2d - cen
    raw_poly = Polygon(pts)
    if not raw_poly.is_valid:
        raw_poly = raw_poly.buffer(0)

    w0 = float(np.max(pts[:, 0]) - np.min(pts[:, 0]))
    t0 = float(np.max(pts[:, 1]) - np.min(pts[:, 1]))

    def objective(params: List[float]) -> float:
        a_val, b_val = params
        poly = create_ellipse_polygon(2.0 * a_val, 2.0 * b_val)
        err, _, _ = compute_polygon_iou_error(raw_poly, poly)
        return err

    init_guess = [w0 / 2.0, t0 / 2.0]
    bounds = [(w0 * 0.35, w0 * 0.65), (t0 * 0.35, t0 * 0.65)]
    res = minimize(objective, init_guess, bounds=bounds, method="Nelder-Mead", options={"xatol": OPTIMIZATION_TOLERANCE})
    best_a, best_b = float(res.x[0]), float(res.x[1])
    best_w, best_t = 2.0 * best_a, 2.0 * best_b

    cand_poly = create_ellipse_polygon(best_w, best_t)
    overlap_err, area_dev, iou = compute_polygon_iou_error(raw_poly, cand_poly)

    # Approximate max distance to ellipse boundary
    r_pts = np.hypot(pts[:, 0], pts[:, 1])
    theta = np.arctan2(pts[:, 1], pts[:, 0])
    r_ellipse = (best_a * best_b) / np.sqrt((best_b * np.cos(theta)) ** 2 + (best_a * np.sin(theta)) ** 2 + 1e-6)
    max_dist = float(np.max(np.abs(r_pts - r_ellipse)))

    confidence = max(0.0, min(1.0, 1.0 - (overlap_err / 10.0)))

    return {
        "primitive_type": "ELLIPSE",
        "parameters": {
            "major_axis": round(max(best_w, best_t), 3),
            "minor_axis": round(min(best_w, best_t), 3),
            "width": round(best_w, 3),
            "thickness": round(best_t, 3),
        },
        "area_overlap_error_pct": round(overlap_err, 2),
        "area_deviation_pct": round(area_dev, 2),
        "max_distance_mm": round(max_dist, 3),
        "iou": round(iou, 4),
        "confidence": round(confidence, 3),
        "is_supported": overlap_err <= MAX_FIT_AREA_OVERLAP_ERROR_PCT,
    }


def fit_superellipse(points_2d: np.ndarray) -> Dict[str, Any]:
    """
    Fits a superellipse (|x/a|^n + |y/b|^n <= 1) to 2D cross-section points by
    minimizing boundary distance / IoU area overlap error over semi-axes (a, b) and exponent n.
    """
    cen = (np.max(points_2d, axis=0) + np.min(points_2d, axis=0)) / 2.0
    pts = points_2d - cen
    raw_poly = Polygon(pts)
    if not raw_poly.is_valid:
        raw_poly = raw_poly.buffer(0)

    w0 = float(np.max(pts[:, 0]) - np.min(pts[:, 0]))
    t0 = float(np.max(pts[:, 1]) - np.min(pts[:, 1]))

    def objective(params: List[float]) -> float:
        a_val, b_val, n_val = params
        poly = create_superellipse_polygon(2.0 * a_val, 2.0 * b_val, n_val)
        err, _, _ = compute_polygon_iou_error(raw_poly, poly)
        return err

    init_guess = [w0 / 2.0, t0 / 2.0, 2.5]
    bounds = [(w0 * 0.35, w0 * 0.65), (t0 * 0.35, t0 * 0.65), (SUPERELLIPSE_MIN_EXPONENT, SUPERELLIPSE_MAX_EXPONENT)]
    res = minimize(objective, init_guess, bounds=bounds, method="Nelder-Mead", options={"xatol": OPTIMIZATION_TOLERANCE})
    best_a, best_b, best_n = float(res.x[0]), float(res.x[1]), float(res.x[2])
    best_w, best_t = 2.0 * best_a, 2.0 * best_b

    cand_poly = create_superellipse_polygon(best_w, best_t, best_n)
    overlap_err, area_dev, iou = compute_polygon_iou_error(raw_poly, cand_poly)

    cand_line = cand_poly.exterior
    max_dist = float(np.max([cand_line.distance(Point(p[0], p[1])) for p in pts]))
    confidence = max(0.0, min(1.0, 1.0 - (overlap_err / 10.0)))

    return {
        "primitive_type": "SUPERELLIPSE",
        "parameters": {
            "major_axis": round(max(best_w, best_t), 3),
            "minor_axis": round(min(best_w, best_t), 3),
            "width": round(best_w, 3),
            "thickness": round(best_t, 3),
            "exponent_n": round(best_n, 3),
        },
        "area_overlap_error_pct": round(overlap_err, 2),
        "area_deviation_pct": round(area_dev, 2),
        "max_distance_mm": round(max_dist, 3),
        "iou": round(iou, 4),
        "confidence": round(confidence, 3),
        "is_supported": overlap_err <= MAX_FIT_AREA_OVERLAP_ERROR_PCT,
    }


def fit_rounded_slot(points_2d: np.ndarray) -> Dict[str, Any]:
    """
    Fits a rounded slot / stadium shape to 2D cross-section points.
    """
    cen = (np.max(points_2d, axis=0) + np.min(points_2d, axis=0)) / 2.0
    pts = points_2d - cen
    raw_poly = Polygon(pts)
    if not raw_poly.is_valid:
        raw_poly = raw_poly.buffer(0)

    w = float(np.max(pts[:, 0]) - np.min(pts[:, 0]))
    t = float(np.max(pts[:, 1]) - np.min(pts[:, 1]))

    cand_poly = create_rounded_slot_polygon(w, t)
    overlap_err, area_dev, iou = compute_polygon_iou_error(raw_poly, cand_poly)

    cand_line = cand_poly.exterior
    max_dist = float(np.max([cand_line.distance(Point(p[0], p[1])) for p in pts]))
    confidence = max(0.0, min(1.0, 1.0 - (overlap_err / 10.0)))

    return {
        "primitive_type": "ROUNDED_SLOT",
        "parameters": {
            "length": round(max(w, t), 3),
            "slot_width": round(min(w, t), 3),
            "cap_radius": round(min(w, t) / 2.0, 3),
        },
        "area_overlap_error_pct": round(overlap_err, 2),
        "area_deviation_pct": round(area_dev, 2),
        "max_distance_mm": round(max_dist, 3),
        "iou": round(iou, 4),
        "confidence": round(confidence, 3),
        "is_supported": overlap_err <= MAX_FIT_AREA_OVERLAP_ERROR_PCT,
    }


def create_compound_4_arc_points(
    width: float,
    thickness: float,
    corner_radius: float,
    num_points: int = NUM_POLYGON_SAMPLES
) -> Tuple[np.ndarray, float]:
    """
    Constructs a 100% native 4-arc compound oval (two flank arcs + two corner arcs,
    tangent at join points) symmetric around the origin.
    Returns (points_2d, flank_radius).
    """
    w = max(width, 1e-3)
    t = max(thickness, 1e-3)
    a = w / 2.0
    b = t / 2.0
    rc = max(0.001, min(corner_radius, b - 0.001))
    rf = (a**2 + b**2 - 2.0 * a * rc) / max(2.0 * (b - rc), 1e-6)

    c1 = np.array([a - rc, 0.0])
    c3 = np.array([0.0, b - rf])
    theta_join = math.atan2(rf - b, a - rc)

    n_per_quad = max(8, num_points // 4)
    # 1. Right corner arc (upper half): 0 to +theta_join
    t_c1_up = np.linspace(0.0, theta_join, n_per_quad // 2, endpoint=False)
    pts_c1_up = c1 + rc * np.column_stack([np.cos(t_c1_up), np.sin(t_c1_up)])

    # 2. Top flank arc: theta_join to pi - theta_join
    t_top = np.linspace(theta_join, math.pi - theta_join, n_per_quad, endpoint=False)
    pts_top = c3 + rf * np.column_stack([np.cos(t_top), np.sin(t_top)])

    # 3. Left corner arc: pi - theta_join to pi + theta_join
    c2 = np.array([-a + rc, 0.0])
    t_c2 = np.linspace(math.pi - theta_join, math.pi + theta_join, n_per_quad, endpoint=False)
    pts_c2 = c2 + rc * np.column_stack([np.cos(t_c2), np.sin(t_c2)])

    # 4. Bottom flank arc: -pi + theta_join to -theta_join (mapped to positive angles)
    c4 = np.array([0.0, -b + rf])
    t_bot = np.linspace(math.pi + theta_join, 2.0 * math.pi - theta_join, n_per_quad, endpoint=False)
    pts_bot = c4 + rf * np.column_stack([np.cos(t_bot), np.sin(t_bot)])

    # 5. Right corner arc (lower half): -theta_join to 0 (mapped to 2*pi - theta_join to 2*pi)
    t_c1_dn = np.linspace(2.0 * math.pi - theta_join, 2.0 * math.pi, n_per_quad // 2, endpoint=False)
    pts_c1_dn = c1 + rc * np.column_stack([np.cos(t_c1_dn), np.sin(t_c1_dn)])

    return np.vstack([pts_c1_up, pts_top, pts_c2, pts_bot, pts_c1_dn]), rf


def create_compound_4_arc_polygon(
    width: float,
    thickness: float,
    corner_radius: float,
    num_points: int = NUM_POLYGON_SAMPLES
) -> Polygon:
    """Creates a Shapely Polygon for a centered compound 4-arc oval."""
    pts, _ = create_compound_4_arc_points(width, thickness, corner_radius, num_points)
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


def fit_compound_4_arc(points_2d: np.ndarray) -> Dict[str, Any]:
    """
    Fits a compound 4-arc oval (2 flank arcs + 2 corner arcs, tangent at joins)
    by minimizing distance/IoU error to the real outline over corner radius Rc.
    Native CAD entities: 4 tangent circular arcs, zero splines.
    """
    cen = (np.max(points_2d, axis=0) + np.min(points_2d, axis=0)) / 2.0
    pts_c = points_2d - cen
    w_raw = float(np.ptp(pts_c[:, 0]))
    t_raw = float(np.ptp(pts_c[:, 1]))
    swapped = False
    if w_raw < t_raw:
        pts_c = pts_c[:, [1, 0]]
        w_raw, t_raw = t_raw, w_raw
        swapped = True

    poly_real = Polygon(pts_c)
    if not poly_real.is_valid:
        poly_real = poly_real.buffer(0)

    b = t_raw / 2.0

    # 1D bounded minimization of IoU overlap error over corner radius Rc
    def loss_rc(rc: float) -> float:
        try:
            cand_pts, _ = create_compound_4_arc_points(w_raw, t_raw, rc)
            p_cand = Polygon(cand_pts)
            if not p_cand.is_valid:
                return 100.0
            inter = poly_real.intersection(p_cand).area
            union = poly_real.union(p_cand).area
            return (1.0 - inter / max(union, 1e-6)) * 100.0
        except Exception:
            return 100.0

    res1d = minimize_scalar(loss_rc, bounds=(0.02 * b, 0.98 * b), method="bounded", options={"xatol": OPTIMIZATION_TOLERANCE})
    rc_opt = float(res1d.x)

    w_opt, t_opt = w_raw, t_raw
    cand_opt, rf_opt = create_compound_4_arc_points(w_opt, t_opt, rc_opt)
    p_opt = Polygon(cand_opt)
    if not p_opt.is_valid:
        p_opt = p_opt.buffer(0)
    err, area_dev, max_d = compute_polygon_iou_error(poly_real, p_opt)

    if swapped:
        w_opt, t_opt = t_opt, w_opt

    return {
        "primitive_type": "COMPOUND_4_ARC",
        "parameters": {
            "width": round(float(w_opt), 3),
            "thickness": round(float(t_opt), 3),
            "corner_radius": round(float(rc_opt), 3),
            "flank_radius": round(float(rf_opt), 3),
        },
        "area_overlap_error_pct": round(float(err), 2),
        "area_deviation_pct": round(float(area_dev), 2),
        "max_distance_mm": round(float(max_d), 3),
        "confidence": round(max(0.0, 1.0 - err / MAX_FIT_AREA_OVERLAP_ERROR_PCT), 3),
        "is_supported": bool(err <= MAX_FIT_AREA_OVERLAP_ERROR_PCT),
    }


def fit_best_primitive(points_2d: np.ndarray, is_thin_tab: bool = False) -> Dict[str, Any]:
    """
    Fits all candidate primitives and selects the best one (lowest area overlap error).
    If is_thin_tab is True (crimp-like range), fits the OUTER ENVELOPE (convex hull) of the outline
    so local serrations / ridges are ignored.
    If no primitive satisfies the 5.0% threshold, marks the range UNSUPPORTED.
    """
    pts = points_2d
    if is_thin_tab:
        # Use outer envelope (convex hull) to ignore surface serrations/ridges
        poly = Polygon(points_2d)
        if not poly.is_valid:
            poly = poly.buffer(0)
        hull = poly.convex_hull
        pts = np.array(hull.exterior.coords)[:-1]

    cands = [
        fit_rounded_rectangle(pts),
        fit_ellipse(pts),
        fit_superellipse(pts),
        fit_rounded_slot(pts),
        fit_compound_4_arc(pts),
    ]

    # Only primitives that Siemens NX can construct with native sketch entities
    # (lines, arcs, ellipses) count as SUPPORTED for CAD reconstruction:
    # ROUNDED_RECTANGLE (lines + arcs), ELLIPSE (native ellipse), ROUNDED_SLOT (lines + arcs),
    # COMPOUND_4_ARC (4 native tangent circular arcs).
    # SUPERELLIPSE is an organic/spline shape that cannot be a native sketch, so it cannot count.
    NATIVE_SKETCH_PRIMITIVES = ("ROUNDED_RECTANGLE", "ELLIPSE", "ROUNDED_SLOT", "COMPOUND_4_ARC")
    native_cands = [c for c in cands if c["primitive_type"] in NATIVE_SKETCH_PRIMITIVES]
    native_cands.sort(key=lambda c: c["area_overlap_error_pct"])
    best_native = native_cands[0]

    # Also sort all candidates (including superellipse) for reporting diagnostics
    cands.sort(key=lambda c: c["area_overlap_error_pct"])
    best_overall = cands[0]

    # If the best buildable native primitive satisfies the <= 5.0% threshold, select it
    if best_native["area_overlap_error_pct"] <= MAX_FIT_AREA_OVERLAP_ERROR_PCT:
        return best_native

    # If no buildable native primitive passes <= 5.0%, mark as UNSUPPORTED
    rejection_msg = (
        f"No buildable native CAD sketch primitive (lines, arcs, ellipses) could fit the cross-section "
        f"within {MAX_FIT_AREA_OVERLAP_ERROR_PCT}% error. "
        f"Best buildable primitive was {best_native['primitive_type']} at {best_native['area_overlap_error_pct']:.2f}% error."
    )
    if best_overall["primitive_type"] == "SUPERELLIPSE":
        rejection_msg += f" (Superellipse achieved {best_overall['area_overlap_error_pct']:.2f}% error but cannot be a native CAD sketch)."

    return {
        "primitive_type": "UNSUPPORTED",
        "best_attempted_type": best_overall["primitive_type"],
        "best_attempted_parameters": best_overall["parameters"],
        "best_native_type": best_native["primitive_type"],
        "best_native_parameters": best_native["parameters"],
        "area_overlap_error_pct": best_native["area_overlap_error_pct"],
        "area_deviation_pct": best_native["area_deviation_pct"],
        "max_distance_mm": best_native["max_distance_mm"],
        "is_supported": False,
        "rejection_reason": rejection_msg
    }
