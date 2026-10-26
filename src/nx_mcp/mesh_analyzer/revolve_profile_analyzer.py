"""
revolve_profile_analyzer.py
===========================
Mesh Slicing, Circularity Profiling, and Parametric Zone Intent Analyzer.

Analyzes polygonal 3D OBJ meshes to:
1. Determine the principal rotational/up-axis (X, Y, or Z).
2. Slice cross-sections at high resolution (80-120 stations).
3. Compute exact circularity score (isoperimetric quotient C = 4*pi*Area/Perimeter^2).
4. Identify zone transitions (inflection points, diameter steps, neck minima, shoulder maxima).
5. Generate a 100% valid, expression-chained, sketch-in-place specification JSON.
6. Support optional Vision AI semantic tagging via GEMINI_API_KEY when available.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter1d


# Named thresholds for rotational symmetry gating (Enforced)
MIN_CIRCULARITY_THRESHOLD: float = 0.94       # Min isoperimetric circularity (4*pi*Area / Perimeter^2)
MAX_ASPECT_RATIO_THRESHOLD: float = 1.08      # Max bounding rectangle aspect ratio (major / minor)
MAX_RADIAL_VARIATION_THRESHOLD: float = 0.12  # Max allowable (r_max - r_min) / r_max around centroid (12%)
MIN_ROUND_STATION_FRACTION: float = 0.80      # Min fraction of stations that must pass all round criteria (80%)

# Profile Refinement (Closed-Loop) Constants
PROFILE_REFINEMENT_TOLERANCE_PCT: float = 5.0   # Max acceptable profile deviation (%) per station
PROFILE_MAX_ZONES_CAP: int = 12                  # Maximum zone count before giving up refinement


class RefinementStatus(str):
    """
    String subclass representing refinement status, with attached metadata.
    Behaves exactly like a str ("PASS", "NEAR_MISS", "FAR_MISS") in string comparisons,
    while carrying surviving_errors and worst_error_pct.
    """
    def __new__(cls, status_str: str, surviving_errors: Optional[List[Dict[str, Any]]] = None, worst_error_pct: float = 0.0):
        obj = super().__new__(cls, status_str)
        obj.status = status_str
        obj.surviving_errors = surviving_errors or []
        obj.worst_error_pct = worst_error_pct
        return obj


class RevolveProfileAnalyzer:
    """Analyzes mesh geometry for rotational symmetry and zone segmentation."""

    def __init__(self, obj_path: Path, units: Optional[str] = None):
        self.obj_path = obj_path
        self.mesh: trimesh.Trimesh = trimesh.load(str(obj_path), force="mesh")
        
        # Unit scaling rules
        max_extent = float(np.max(self.mesh.extents))
        if units:
            unit_norm = units.lower().strip()
            if unit_norm in ("m", "meter", "meters"):
                self.scale_factor = 1000.0
                self.unit_rule_applied = f"Explicitly scaled from meters (scale = 1000.0x)"
            elif unit_norm in ("dm", "decimeter", "decimeters"):
                self.scale_factor = 100.0
                self.unit_rule_applied = f"Explicitly scaled from decimeters (scale = 100.0x)"
            elif unit_norm in ("cm", "centimeter", "centimeters"):
                self.scale_factor = 10.0
                self.unit_rule_applied = f"Explicitly scaled from centimeters (scale = 10.0x)"
            elif unit_norm in ("mm", "millimeter", "millimeters"):
                self.scale_factor = 1.0
                self.unit_rule_applied = f"Explicitly defined in millimeters (scale = 1.0x, unchanged)"
            else:
                self.scale_factor = 1.0
                self.unit_rule_applied = f"Unrecognized unit '{units}', keeping scale = 1.0x"
        else:
            # Deterministic industrial scale rule for dimensionless Wavefront OBJs:
            # [Rule 1] Extent < 0.25 -> Model authored in meters (m) -> scale x1000.0 to mm
            # [Rule 2] 0.25 <= Extent < 15.0 -> Model authored in decimeters (dm) -> scale x100.0 to mm
            # [Rule 3] Extent >= 15.0 -> Model already authored in millimeters (mm) -> scale x1.0 (no change)
            if max_extent < 0.25:
                self.scale_factor = 1000.0
                self.unit_rule_applied = f"Auto-detected meters (max extent {max_extent:.3f} < 0.25 -> scale x1000.0)"
            elif max_extent < 15.0:
                self.scale_factor = 100.0
                self.unit_rule_applied = f"Auto-detected decimeters (0.25 <= max extent {max_extent:.3f} < 15.0 -> scale x100.0)"
            else:
                self.scale_factor = 1.0
                self.unit_rule_applied = f"Auto-detected millimeters (max extent {max_extent:.2f} mm >= 15.0 -> scale x1.0)"

        if abs(self.scale_factor - 1.0) > 1e-4:
            self.mesh.apply_scale(self.scale_factor)

        # Ensure clean geometry
        if not self.mesh.is_watertight:
            self.mesh.fill_holes()

        self._analyze_principal_axis()


    def _analyze_principal_axis(self) -> None:
        """Determines the primary rotational/axial axis via bounding extents and symmetry."""
        extents = self.mesh.extents
        # Extents along [X, Y, Z]
        aspect_xy = extents[0] / max(extents[1], 1e-4) # if Z is axis, X/Y ~ 1.0
        aspect_xz = extents[0] / max(extents[2], 1e-4) # if Y is axis, X/Z ~ 1.0
        aspect_yz = extents[1] / max(extents[2], 1e-4) # if X is axis, Y/Z ~ 1.0

        scores = [
            (abs(aspect_yz - 1.0), "X", 0),
            (abs(aspect_xz - 1.0), "Y", 1),
            (abs(aspect_xy - 1.0), "Z", 2),
        ]
        scores.sort(key=lambda x: x[0])
        self.primary_axis_name = scores[0][1]
        self.primary_axis_idx = scores[0][2]

        # If elongation is dominant along another axis, confirm axis
        max_idx = int(np.argmax(extents))
        if max_idx != self.primary_axis_idx and scores[0][0] > 0.35:
            self.primary_axis_idx = max_idx
            self.primary_axis_name = ["X", "Y", "Z"][max_idx]

        # Rotate mesh so primary axis maps to canonical +Y
        from src.nx_mcp.mesh_analyzer.pca_align import get_canonical_rotation
        R = get_canonical_rotation(self.primary_axis_name)
        if self.primary_axis_name != "Y":
            self.mesh.vertices = (R @ self.mesh.vertices.T).T
            self.primary_axis_name = "Y"
            self.primary_axis_idx = 1
        self.rotation_matrix = R

    def compute_circularity_profile(self, n_slices: int = 100) -> Dict[str, Any]:
        """
        Slices the mesh along the primary axis and measures circularity, aspect ratio,
        radius variation around centroid, and equivalent radius.
        """
        bounds = self.mesh.bounds
        axis_idx = self.primary_axis_idx
        z_min = float(bounds[0][axis_idx])
        z_max = float(bounds[1][axis_idx])
        height_span = z_max - z_min

        # Avoid boundary singularities (slice within 0.5% to 99.5% to preserve ends)
        z_levels = np.linspace(z_min + 0.005 * height_span, z_max - 0.005 * height_span, n_slices)
        
        station_data = []
        circularities = []
        aspect_ratios = []
        radial_variations = []
        radii = []

        # Axis normal vector for slicing
        plane_normal = np.zeros(3)
        plane_normal[axis_idx] = 1.0

        for z in z_levels:
            plane_origin = np.zeros(3)
            plane_origin[axis_idx] = z
            slice_3d = self.mesh.section(plane_origin=plane_origin, plane_normal=plane_normal)

            if slice_3d is None:
                continue

            try:
                slice_2d, _ = slice_3d.to_planar()
                polygons = getattr(slice_2d, "polygons_closed", [])
                if len(polygons) == 0:
                    polygons = getattr(slice_2d, "polygons_full", [])
                if len(polygons) == 0:
                    continue

                outer_poly = max(polygons, key=lambda p: p.area)
                area = float(outer_poly.area)
                perimeter = float(outer_poly.length)
                
                if perimeter <= 1e-4 or area <= 1e-4:
                    continue

                # Isoperimetric circularity: C = 4 * pi * Area / (Perimeter^2)
                c_score = min(1.0, float(4.0 * math.pi * area / (perimeter ** 2)))

                # Ellipse / Bounding Box Aspect Ratio
                rect = outer_poly.minimum_rotated_rectangle
                ext_coords = rect.exterior.coords
                e1 = float(np.linalg.norm(np.array(ext_coords[0]) - np.array(ext_coords[1])))
                e2 = float(np.linalg.norm(np.array(ext_coords[1]) - np.array(ext_coords[2])))
                ar = max(e1, e2) / max(min(e1, e2), 1e-4)

                # Radius variation around centroid (catches rounded squares / squircles)
                cen = np.array([outer_poly.centroid.x, outer_poly.centroid.y])
                bpts = np.array(outer_poly.exterior.coords)
                dists = np.linalg.norm(bpts - cen, axis=1)
                r_min_c = float(np.min(dists))
                r_max_c = float(np.max(dists))
                rad_var = float((r_max_c - r_min_c) / max(r_max_c, 1e-4))

                r_extent = (e1 + e2) / 4.0
                r_area = math.sqrt(area / math.pi)
                r_equiv = r_extent if ar > 1.15 else min(r_extent, r_area)

                circularities.append(c_score)
                aspect_ratios.append(ar)
                radial_variations.append(rad_var)
                radii.append(r_equiv)
                station_data.append({
                    "z": float(z),
                    "radius": float(r_equiv),
                    "circularity": float(c_score),
                    "aspect_ratio": float(ar),
                    "radial_variation": float(rad_var),
                })
            except Exception:
                continue

        if not station_data:
            return {
                "is_round": False,
                "mean_circularity": 0.0,
                "mean_aspect_ratio": 99.0,
                "mean_radial_variation": 1.0,
                "max_radial_variation": 1.0,
                "round_station_fraction": 0.0,
                "reason": "Failed to extract valid cross sections from mesh."
            }

        mean_circ = float(np.mean(circularities))
        mean_aspect = float(np.mean(aspect_ratios))
        max_aspect = float(np.max(aspect_ratios))
        mean_rad_var = float(np.mean(radial_variations))
        max_rad_var = float(np.max(radial_variations))

        # Station passes only if circularity, aspect ratio, AND radial variation are within thresholds
        round_stations = sum(
            1 for (c, a, r) in zip(circularities, aspect_ratios, radial_variations)
            if c >= MIN_CIRCULARITY_THRESHOLD and a <= MAX_ASPECT_RATIO_THRESHOLD and r <= MAX_RADIAL_VARIATION_THRESHOLD
        )
        round_frac = float(round_stations / len(circularities))

        # Strict roundness gate:
        # Requires high circularity (>= 0.94), low aspect ratio (<= 1.08), low radial variation (<= 0.12), and >= 80% passing stations
        is_round = bool(
            mean_circ >= MIN_CIRCULARITY_THRESHOLD
            and mean_aspect <= MAX_ASPECT_RATIO_THRESHOLD
            and mean_rad_var <= MAX_RADIAL_VARIATION_THRESHOLD
            and round_frac >= MIN_ROUND_STATION_FRACTION
        )
        
        if is_round:
            reason = "Rotational symmetry confirmed across cross sections."
        elif mean_rad_var > MAX_RADIAL_VARIATION_THRESHOLD:
            reason = (
                f"Cross sections have non-circular radial variation ({mean_rad_var*100:.1f}% > {MAX_RADIAL_VARIATION_THRESHOLD*100:.0f}%, "
                f"e.g. rounded-square/squircle with corners farther from center than sides)."
            )
        elif mean_aspect > MAX_ASPECT_RATIO_THRESHOLD:
            reason = (
                f"Cross sections are oval/non-axisymmetric (mean aspect ratio {mean_aspect:.2f} > {MAX_ASPECT_RATIO_THRESHOLD:.2f}, "
                f"circularity {mean_circ:.2f}, round fraction {round_frac*100:.1f}%)."
            )
        else:
            reason = (
                f"Cross sections lack sufficient circularity (mean circularity {mean_circ:.2f} < {MIN_CIRCULARITY_THRESHOLD:.2f}, "
                f"round fraction {round_frac*100:.1f}%)."
            )

        return {
            "is_round": is_round,
            "primary_axis": self.primary_axis_name,
            "axis_idx": self.primary_axis_idx,
            "z_min": z_min,
            "z_max": z_max,
            "total_height": height_span,
            "station_count": len(station_data),
            "mean_circularity": round(mean_circ, 4),
            "mean_aspect_ratio": round(mean_aspect, 4),
            "max_aspect_ratio": round(max_aspect, 4),
            "mean_radial_variation": round(mean_rad_var, 4),
            "max_radial_variation": round(max_rad_var, 4),
            "round_station_fraction": round(round_frac, 4),
            "thresholds": {
                "min_circularity": MIN_CIRCULARITY_THRESHOLD,
                "max_aspect_ratio": MAX_ASPECT_RATIO_THRESHOLD,
                "max_radial_variation": MAX_RADIAL_VARIATION_THRESHOLD,
                "min_round_fraction": MIN_ROUND_STATION_FRACTION,
            },
            "stations": station_data,
            "reason": reason,
            "rotation_matrix": getattr(self, "rotation_matrix", np.eye(3)).tolist(),
        }

    def _fit_line_segment(self, z_s: np.ndarray, r_s: np.ndarray) -> Tuple[np.ndarray, float, float, Tuple]:
        z0, z1 = z_s[0], z_s[-1]
        r0, r1 = r_s[0], r_s[-1]
        if abs(z1 - z0) < 1e-4:
            r_fit = np.full_like(z_s, r0)
        else:
            slope = (r1 - r0) / (z1 - z0)
            r_fit = r0 + slope * (z_s - z0)
        dev = np.abs(r_s - r_fit)
        return r_fit, float(dev.max()), float(dev.mean()), ("LINE", r0, r1)

    def _fit_arc_segment(self, z_s: np.ndarray, r_s: np.ndarray) -> Tuple[np.ndarray, float, float, Tuple]:
        if len(z_s) < 3:
            return self._fit_line_segment(z_s, r_s)
        p1 = np.array([r_s[0], z_s[0]])
        mid_idx = len(z_s) // 2
        p2 = np.array([r_s[mid_idx], z_s[mid_idx]])
        p3 = np.array([r_s[-1], z_s[-1]])
        
        v1 = p2 - p1
        v2 = p3 - p1
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        if abs(cross) < 1e-3:
            return self._fit_line_segment(z_s, r_s)
        
        A = 2 * np.array([
            [p2[0] - p1[0], p2[1] - p1[1]],
            [p3[0] - p2[0], p3[1] - p2[1]]
        ])
        b = np.array([
            p2[0]**2 + p2[1]**2 - (p1[0]**2 + p1[1]**2),
            p3[0]**2 + p3[1]**2 - (p2[0]**2 + p2[1]**2)
        ])
        try:
            center = np.linalg.solve(A, b)
            rc, zc = center[0], center[1]
            arc_R = float(np.linalg.norm(p1 - center))
            dists = np.sqrt((r_s - rc)**2 + (z_s - zc)**2)
            dev = np.abs(dists - arc_R)
            
            disc = arc_R**2 - (z_s - zc)**2
            if np.any(disc < 0):
                return self._fit_line_segment(z_s, r_s)
            sign = 1.0 if p2[0] > rc else -1.0
            r_fit = rc + sign * np.sqrt(disc)
            return r_fit, float(dev.max()), float(dev.mean()), ("ARC", p1, p2, p3, arc_R, (rc, zc))
        except Exception:
            return self._fit_line_segment(z_s, r_s)

    def _adaptive_segmentation(self, z_s: np.ndarray, r_s: np.ndarray, tol: float, min_len: int = 2) -> List[Tuple]:
        l_fit, l_max, l_mean, l_data = self._fit_line_segment(z_s, r_s)
        a_fit, a_max, a_mean, a_data = self._fit_arc_segment(z_s, r_s)
        
        mid_idx = len(r_s) // 2
        sagitta = abs(r_s[mid_idx] - (r_s[0] + r_s[-1]) / 2.0)

        if sagitta < 0.5 or l_max <= tol:
            best_type = "LINE"
            best_fit = l_fit
            best_max = l_max
            best_data = l_data
        elif a_max <= tol:
            best_type = "ARC"
            best_fit = a_fit
            best_max = a_max
            best_data = a_data
        else:
            best_type = "LINE" if l_max <= a_max else "ARC"
            best_fit = l_fit if l_max <= a_max else a_fit
            best_max = min(l_max, a_max)
            best_data = l_data if l_max <= a_max else a_data

        if best_max <= tol or len(z_s) <= min_len * 2:
            return [(z_s, r_s, best_fit, best_type, best_data, best_max)]
        
        dev = np.abs(r_s - best_fit)
        split_idx = int(np.argmax(dev))
        if split_idx < min_len or len(z_s) - split_idx < min_len:
            split_idx = len(z_s) // 2
            
        left = self._adaptive_segmentation(z_s[:split_idx+1], r_s[:split_idx+1], tol, min_len)
        right = self._adaptive_segmentation(z_s[split_idx:], r_s[split_idx:], tol, min_len)
        return left + right

    def segment_zones(self, profile: Dict[str, Any], max_zones: int = 8) -> List[Dict[str, Any]]:
        """
        Partitions the radius profile into adaptive LINE and ARC functional zones.
        Recursively subdivides zones until max radial deviation is <= 2% of max radius.
        """
        stations = profile["stations"]
        if not stations:
            return []

        z_vals = np.array([s["z"] for s in stations])
        r_vals = np.array([s["radius"] for s in stations])
        n = len(stations)

        R_max = float(np.max(r_vals))
        z_min = float(profile.get("z_min", z_vals[0]))
        z_max = float(profile.get("z_max", z_vals[-1]))
        total_h = z_max - z_min

        # 1.5% of maximum radius tolerance (approx 0.6 mm for 42 mm radius)
        tol_dev = max(0.3, 0.015 * R_max)

        # Segment directly on raw r_vals to preserve sharp step discontinuities (collars, shoulders)
        raw_segments = self._adaptive_segmentation(z_vals, r_vals, tol=tol_dev, min_len=2)

        # Merge adjacent collinear LINE segments if their combined deviation is within tolerance
        merged_segments = []
        idx = 0
        while idx < len(raw_segments):
            cur = raw_segments[idx]
            while idx + 1 < len(raw_segments):
                nxt = raw_segments[idx + 1]
                if cur[3] == "LINE" and nxt[3] == "LINE":
                    z_comb = np.concatenate([cur[0][:-1], nxt[0]])
                    r_comb = np.concatenate([cur[1][:-1], nxt[1]])
                    l_fit, l_max, l_mean, l_data = self._fit_line_segment(z_comb, r_comb)
                    if l_max <= tol_dev:
                        cur = (z_comb, r_comb, l_fit, "LINE", l_data, l_max)
                        idx += 1
                        continue
                break
            merged_segments.append(cur)
            idx += 1
        
        num_segs = len(merged_segments)
        zones = []

        for k, seg in enumerate(merged_segments):
            z_s, r_s, r_fit, g_type, data, max_d = seg
            z_start = z_min if k == 0 else float(z_s[0])
            z_end = z_max if k == num_segs - 1 else float(z_s[-1])
            h = z_end - z_start
            r_start = float(r_s[0])
            r_end = float(r_s[-1])

            if g_type == "ARC":
                mid_idx = len(z_s) // 2
                r_mid = float(r_s[mid_idx])
                z_mid = float(z_s[mid_idx])
            else:
                r_mid = (r_start + r_end) / 2.0
                z_mid = (z_start + z_end) / 2.0

            # Geometric functional role classification
            rel_pos = (z_start - z_min) / max(total_h, 1e-4)
            delta_r = r_end - r_start
            rel_r = (r_start + r_end) / (2.0 * R_max)

            if k == 0 or rel_r >= 0.85:
                role = "BODY"
            elif k == num_segs - 1:
                role = "BULB" if (rel_r < 0.40 and (g_type == "ARC" or rel_pos > 0.85)) else "CAP"
            elif delta_r < -0.06 * R_max:
                role = "SHOULDER" if rel_pos < 0.65 else "NECK"
            elif 0.45 <= rel_r < 0.85 and abs(delta_r) < 0.08 * R_max:
                role = "COLLAR"
            elif rel_r < 0.50:
                role = "NECK"
            else:
                role = "BODY"

            zname = f"{role}_{k+1}" if num_segs > 4 else role

            zones.append({
                "zone_idx": k + 1,
                "name": zname,
                "role": role,
                "segment_type": g_type,
                "z_start": round(z_start, 3),
                "z_end": round(z_end, 3),
                "height": round(h, 3),
                "r_start": round(r_start, 3),
                "r_end": round(r_end, 3),
                "r_mid": round(r_mid, 3),
                "z_mid": round(z_mid, 3),
                "dia_start": round(r_start * 2.0, 3),
                "dia_end": round(r_end * 2.0, 3),
                "dia_max": round(max(r_start, r_end, r_mid) * 2.0, 3),
                "max_dev_mm": round(max_d, 3)
            })

        return zones

    def _evaluate_zone_error(
        self,
        z_vals: np.ndarray,
        r_vals: np.ndarray,
        zone: Dict[str, Any],
    ) -> Tuple[float, float, int]:
        """
        Evaluates the maximum profile error for a single zone at dense stations.
        Returns (max_error_pct, max_error_mm, worst_station_idx).
        Uses quadratic Bezier interpolation for ARC segments and linear for LINE.
        """
        z_st = zone["z_start"]
        z_en = zone["z_end"]
        r_b = zone["r_start"]
        r_t = zone["r_end"]
        seg_type = zone.get("segment_type", "LINE")
        r_m = zone.get("r_mid", (r_b + r_t) / 2.0)

        mask = (z_vals >= z_st - 0.1) & (z_vals <= z_en + 0.1)
        if not np.any(mask):
            return 0.0, 0.0, 0

        idxs = np.where(mask)[0]
        max_err_pct = 0.0
        max_err_mm = 0.0
        worst_idx = idxs[0]

        for i in idxs:
            z = z_vals[i]
            r_actual = r_vals[i]
            frac = (z - z_st) / max(z_en - z_st, 1e-4)
            frac = float(np.clip(frac, 0.0, 1.0))

            if seg_type == "ARC":
                r_plan = (1.0 - frac)**2 * r_b + 2.0 * frac * (1.0 - frac) * r_m + frac**2 * r_t
            else:
                r_plan = r_b + frac * (r_t - r_b)

            err_mm = abs(r_actual - r_plan)
            err_pct = (err_mm / max(r_actual, 1e-4)) * 100.0

            if err_pct > max_err_pct:
                max_err_pct = err_pct
                max_err_mm = err_mm
                worst_idx = i

        return max_err_pct, max_err_mm, int(worst_idx)

    def refine_zones(
        self,
        profile: Dict[str, Any],
        zones: List[Dict[str, Any]],
        max_zones_cap: int = PROFILE_MAX_ZONES_CAP,
    ) -> Tuple[List[Dict[str, Any]], RefinementStatus]:
        """
        Closed-loop profile refinement: compares planned profile to mesh at dense
        stations (every 1% of height), splits zones where deviation exceeds
        PROFILE_REFINEMENT_TOLERANCE_PCT, and repeats until all pass or
        max_zones_cap is reached.

        If max zone count is reached with remaining errors: tags the surviving
        failing stations with their error and classifies them as:
            - "near-miss": error < 2x tolerance (< 10%)
            - "far-miss":  error >= 2x tolerance (>= 10%, unsupported geometry)

        Returns:
            (refined_zones, refinement_status)
        """
        stations = profile.get("stations", [])
        if not stations:
            return zones, RefinementStatus("PASS", [], 0.0)

        z_vals = np.array([s["z"] for s in stations])
        r_vals = np.array([s["radius"] for s in stations])
        R_max = float(np.max(r_vals))
        z_min = float(z_vals[0])
        z_max = float(z_vals[-1])
        total_h = z_max - z_min

        max_iterations = 25
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Evaluate errors per zone
            worst_zone_idx = -1
            worst_err_pct = 0.0
            worst_station_idx = 0

            for zi, zone in enumerate(zones):
                err_pct, err_mm, w_idx = self._evaluate_zone_error(z_vals, r_vals, zone)
                if err_pct > worst_err_pct:
                    worst_err_pct = err_pct
                    worst_zone_idx = zi
                    worst_station_idx = w_idx

            if worst_err_pct <= PROFILE_REFINEMENT_TOLERANCE_PCT:
                break

            if len(zones) >= max_zones_cap:
                break

            # Split the worst zone at the worst station
            zone_to_split = zones[worst_zone_idx]
            split_z = float(z_vals[worst_station_idx])

            z_st = zone_to_split["z_start"]
            z_en = zone_to_split["z_end"]
            z_h = z_en - z_st

            # Do not split zones whose height is already below 5.0 mm (produces degenerate micro-zones)
            if z_h < 5.0:
                break

            min_frac = 0.05

            if split_z <= z_st + min_frac * z_h or split_z >= z_en - min_frac * z_h:
                if z_h > 1.0:
                    split_z = (z_st + z_en) / 2.0
                else:
                    break

            closest_idx = int(np.argmin(np.abs(z_vals - split_z)))
            r_split = float(r_vals[closest_idx])

            r_start = zone_to_split["r_start"]
            r_end = zone_to_split["r_end"]

            mask_lo = (z_vals >= z_st - 0.1) & (z_vals <= split_z + 0.1)
            mask_hi = (z_vals >= split_z - 0.1) & (z_vals <= z_en + 0.1)

            lo_z = z_vals[mask_lo]
            lo_r = r_vals[mask_lo]
            hi_z = z_vals[mask_hi]
            hi_r = r_vals[mask_hi]

            tol_dev = max(0.3, 0.015 * R_max)

            def fit_sub(z_s, r_s):
                if len(z_s) < 2:
                    return "LINE", r_s[0] if len(r_s) > 0 else 0.0
                l_fit, l_max, _, _ = self._fit_line_segment(z_s, r_s)
                a_fit, a_max, _, a_data = self._fit_arc_segment(z_s, r_s)
                mid = len(z_s) // 2
                sagitta = abs(r_s[mid] - (r_s[0] + r_s[-1]) / 2.0)
                if sagitta < 0.5 or l_max <= tol_dev:
                    return "LINE", float(r_s[mid])
                elif a_max <= tol_dev:
                    return "ARC", float(r_s[mid])
                elif a_max < l_max:
                    return "ARC", float(r_s[mid])
                else:
                    return "LINE", float(r_s[mid])

            lo_type, lo_mid_r = fit_sub(lo_z, lo_r) if len(lo_z) >= 2 else ("LINE", r_start)
            hi_type, hi_mid_r = fit_sub(hi_z, hi_r) if len(hi_z) >= 2 else ("LINE", r_end)

            num_segs = len(zones) + 1

            def classify_role(z_s, z_e, r_s, r_e, k):
                rel_pos = (z_s - z_min) / max(total_h, 1e-4)
                delta_r = r_e - r_s
                rel_r = (r_s + r_e) / (2.0 * R_max)
                if k == 0 or rel_r >= 0.85:
                    return "BODY"
                elif k == num_segs - 1:
                    return "BULB" if rel_r < 0.40 else "CAP"
                elif delta_r < -0.06 * R_max:
                    return "SHOULDER" if rel_pos < 0.65 else "NECK"
                elif 0.45 <= rel_r < 0.85 and abs(delta_r) < 0.08 * R_max:
                    return "COLLAR"
                elif rel_r < 0.50:
                    return "NECK"
                else:
                    return "BODY"

            lo_h = split_z - z_st
            hi_h = z_en - split_z

            lo_zone = {
                "zone_idx": 0,
                "name": "",
                "role": classify_role(z_st, split_z, r_start, r_split, worst_zone_idx),
                "segment_type": lo_type,
                "z_start": round(z_st, 3),
                "z_end": round(split_z, 3),
                "height": round(lo_h, 3),
                "r_start": round(r_start, 3),
                "r_end": round(r_split, 3),
                "r_mid": round(lo_mid_r, 3),
                "z_mid": round((z_st + split_z) / 2.0, 3),
                "dia_start": round(r_start * 2.0, 3),
                "dia_end": round(r_split * 2.0, 3),
                "dia_max": round(max(r_start, r_split, lo_mid_r) * 2.0, 3),
                "max_dev_mm": 0.0,
            }
            hi_zone = {
                "zone_idx": 0,
                "name": "",
                "role": classify_role(split_z, z_en, r_split, r_end, worst_zone_idx + 1),
                "segment_type": hi_type,
                "z_start": round(split_z, 3),
                "z_end": round(z_en, 3),
                "height": round(hi_h, 3),
                "r_start": round(r_split, 3),
                "r_end": round(r_end, 3),
                "r_mid": round(hi_mid_r, 3),
                "z_mid": round((split_z + z_en) / 2.0, 3),
                "dia_start": round(r_split * 2.0, 3),
                "dia_end": round(r_end * 2.0, 3),
                "dia_max": round(max(r_split, r_end, hi_mid_r) * 2.0, 3),
                "max_dev_mm": 0.0,
            }

            zones = zones[:worst_zone_idx] + [lo_zone, hi_zone] + zones[worst_zone_idx + 1:]

            num_segs = len(zones)
            for k, z in enumerate(zones):
                z["zone_idx"] = k + 1
                role = z["role"]
                z["name"] = f"{role}_{k+1}" if num_segs > 4 else role

        # Tag surviving failing stations per zone and overall
        all_surviving_errors: List[Dict[str, Any]] = []
        worst_final = 0.0

        for zone in zones:
            zone["surviving_errors"] = []
            z_st = zone["z_start"]
            z_en = zone["z_end"]
            r_b = zone["r_start"]
            r_t = zone["r_end"]
            seg_type = zone.get("segment_type", "LINE")
            r_m = zone.get("r_mid", (r_b + r_t) / 2.0)

            mask = (z_vals >= z_st - 0.1) & (z_vals <= z_en + 0.1)
            if not np.any(mask):
                continue

            for idx in np.where(mask)[0]:
                z = float(z_vals[idx])
                r_actual = float(r_vals[idx])
                frac = (z - z_st) / max(z_en - z_st, 1e-4)
                frac = float(np.clip(frac, 0.0, 1.0))

                if seg_type == "ARC":
                    r_plan = (1.0 - frac)**2 * r_b + 2.0 * frac * (1.0 - frac) * r_m + frac**2 * r_t
                else:
                    r_plan = r_b + frac * (r_t - r_b)

                err_mm = abs(r_actual - r_plan)
                err_pct = (err_mm / max(r_actual, 1e-4)) * 100.0
                worst_final = max(worst_final, err_pct)

                if err_pct > PROFILE_REFINEMENT_TOLERANCE_PCT:
                    cls_tag = "near-miss" if err_pct < 2.0 * PROFILE_REFINEMENT_TOLERANCE_PCT else "far-miss"
                    err_info = {
                        "station_idx": int(idx),
                        "z": round(z, 3),
                        "radius_mesh": round(r_actual, 3),
                        "radius_plan": round(float(r_plan), 3),
                        "error_mm": round(err_mm, 3),
                        "error_pct": round(err_pct, 2),
                        "zone_idx": int(zone["zone_idx"]),
                        "zone_name": zone["name"],
                        "classification": cls_tag,
                    }
                    zone["surviving_errors"].append(err_info)
                    all_surviving_errors.append(err_info)

        if not all_surviving_errors:
            status_str = "PASS"
        elif any(e["classification"] == "far-miss" for e in all_surviving_errors):
            status_str = "FAR_MISS"
        else:
            status_str = "NEAR_MISS"

        return zones, RefinementStatus(status_str, all_surviving_errors, worst_final)

    def generate_parametric_spec(
        self,
        profile: Dict[str, Any],
        zones: List[Dict[str, Any]],
        image_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generates the deterministic NX specification JSON with master driver expression,
        proportional ratio-linked diameters, chained elevations, and continuous junctions.
        """
        expressions: List[Tuple[str, str]] = []
        
        # 1. Master Driver Expressions
        max_dia_val = max(z["dia_max"] for z in zones)
        max_dia_val = max(max_dia_val, 1.0)
        
        # Estimate base bottom blend from radius curvature at bottom
        base_blend_r = 1.5
        if zones:
            r_body = zones[0]["r_end"]
            r_bottom = zones[0]["r_start"]
            z1_h = zones[0]["height"]
            base_r_diff = abs(r_body - r_bottom)
            if base_r_diff > 0.8:
                base_blend_r = max(1.0, min(5.0, base_r_diff))
            elif max_dia_val > 40.0:
                base_blend_r = 3.500
            # Cap blend radius at 75% of Zone 1 height so 10% expression perturbations never overflow Zone 1
            base_blend_r = min(base_blend_r, max(0.5, z1_h * 0.75))

        expressions.append(("BODY_MAX_DIA", f"{max_dia_val:.3f}"))
        expressions.append(("BASE_BLEND_R", f"{base_blend_r:.3f}"))

        # 2. Zone chained expressions and continuous ratio linking
        for idx, z in enumerate(zones, start=1):
            prefix = f"ZONE{idx}"
            h_val = f"{z['height']:.3f}"
            
            # Elevation chaining (Rule 4)
            if idx == 1:
                expressions.append((f"{prefix}_START", f"{z['z_start']:.3f}"))
            else:
                prev_prefix = f"ZONE{idx-1}"
                expressions.append((f"{prefix}_START", f"{prev_prefix}_START + {prev_prefix}_HEIGHT"))

            expressions.append((f"{prefix}_HEIGHT", h_val))
            
            # Ratio-linked diameters (Master driver scaling without junction steps)
            ratio_start = z["dia_start"] / max_dia_val
            ratio_end = z["dia_end"] / max_dia_val

            if idx == 1:
                if abs(ratio_start - 1.0) < 1e-3:
                    expressions.append((f"{prefix}_BASE_DIA", "BODY_MAX_DIA"))
                else:
                    expressions.append((f"{prefix}_BASE_DIA", f"BODY_MAX_DIA * {ratio_start:.4f}"))
            else:
                # Check continuity with previous zone top diameter
                prev_dia_end = zones[idx-2]["dia_end"]
                step_gap = abs(z["dia_start"] - prev_dia_end)
                if step_gap < 0.05 * max_dia_val:
                    # Continuous junction: directly share expression
                    expressions.append((f"{prefix}_BASE_DIA", f"ZONE{idx-1}_TOP_DIA"))
                else:
                    # Intentional physical step
                    expressions.append((f"{prefix}_BASE_DIA", f"BODY_MAX_DIA * {ratio_start:.4f}"))

            if abs(ratio_end - 1.0) < 1e-3:
                expressions.append((f"{prefix}_TOP_DIA", "BODY_MAX_DIA"))
            else:
                expressions.append((f"{prefix}_TOP_DIA", f"BODY_MAX_DIA * {ratio_end:.4f}"))

            expressions.append((f"{prefix}_BASE_R", f"{prefix}_BASE_DIA / 2.0"))
            expressions.append((f"{prefix}_TOP_R", f"{prefix}_TOP_DIA / 2.0"))

            # For ARC segments, add mid-radius expression
            if z.get("segment_type", "LINE") == "ARC":
                r_mid_val = z.get("r_mid", (z["dia_start"] + z["dia_end"]) / 4.0)
                dia_mid_val = r_mid_val * 2.0
                ratio_mid = dia_mid_val / max_dia_val
                expressions.append((f"{prefix}_MID_DIA", f"BODY_MAX_DIA * {ratio_mid:.4f}"))
                expressions.append((f"{prefix}_MID_R", f"{prefix}_MID_DIA / 2.0"))

        # 3. Generate Sketch-in-Place Zone definitions
        spec_zones = []
        for idx, z in enumerate(zones, start=1):
            prefix = f"ZONE{idx}"
            zname = z["name"]
            seg_type = z.get("segment_type", "LINE")

            profile_pts = [
                {"x": "0.0", "y": f"{prefix}_START"},
                {"x": f"{prefix}_BASE_R", "y": f"{prefix}_START"},
                {"x": f"{prefix}_TOP_R", "y": f"{prefix}_START + {prefix}_HEIGHT"},
                {"x": "0.0", "y": f"{prefix}_START + {prefix}_HEIGHT"},
            ]

            dims = [
                {"type": "HorizontalDim", "exp": f"{prefix}_BASE_R", "line_idx": 0},
                {"type": "HorizontalDim", "exp": f"{prefix}_TOP_R", "line_idx": 2},
                {"type": "VerticalDim", "exp": f"{prefix}_HEIGHT", "line_idx": 3},
            ]

            blend_exp = "BASE_BLEND_R" if idx == 1 else None

            spec_zones.append({
                "zone_idx": idx,
                "name": zname,
                "role": z.get("role", "BODY"),
                "segment_type": seg_type,
                "sketch_plane": "XY",
                "profile_points": profile_pts,
                "r_start_exp": f"{prefix}_BASE_R",
                "r_end_exp": f"{prefix}_TOP_R",
                "r_mid_exp": f"{prefix}_MID_R" if seg_type == "ARC" else None,
                "z_start_exp": f"{prefix}_START",
                "height_exp": f"{prefix}_HEIGHT",
                "dimensions": dims,
                "revolve_axis": [0.0, 1.0, 0.0],
                "unite": bool(idx > 1),
                "blend_radius_exp": blend_exp,
            })

        spec = {
            "source_mesh": str(self.obj_path.name),
            "global_shape_family": "AXISYMMETRIC_REVOLVE",
            "primary_axis": self.primary_axis_name,
            "axis_idx": self.primary_axis_idx,
            "is_round": True,
            "circularity_score": profile["mean_circularity"],
            "mean_aspect_ratio": profile.get("mean_aspect_ratio", 1.0),
            "round_station_fraction": profile["round_station_fraction"],
            "total_height_mm": profile["total_height"],
            "expressions": expressions,
            "zones": spec_zones,
            "metadata": image_metadata or {},
        }

        return spec


def call_vision_api_optional(image_path: Path, prompt_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Optional Vision API helper using GEMINI_API_KEY environment variable.
    Returns structured semantic zone hints without writing any CAD code.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        import urllib.request
        import base64

        # Read image
        with open(image_path, "rb") as img_f:
            img_b64 = base64.b64encode(img_f.read()).decode("utf-8")

        # Query Gemini API via REST endpoint
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        prompt_text = (
            "Analyze this product reference image. The part is an axisymmetric rotational object with the following "
            f"height levels: {prompt_info.get('height_levels')}. "
            "Return a strictly valid JSON object with keys: "
            "'product_type' (e.g. eyeliner, lipstick, bottle, jar), "
            "'zone_semantic_names' (list of strings for each height level from bottom to top, e.g. ['BARREL', 'COLLAR', 'WAND', 'TIP']), "
            "'notes' (short description)."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text},
                        {
                            "inline_data": {
                                "mime_type": "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg",
                                "data": img_b64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {"response_mime_type": "application/json"}
        }

        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            candidate_text = resp_data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(candidate_text)
    except Exception as e:
        print(f"  [VISION API NOTICE] Offline / skipping vision API ({e})")
        return None
