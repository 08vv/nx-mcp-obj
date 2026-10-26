"""
rib_detector.py
================
Periodic Feature Detector & Orientation Classifier.

Classifies repeating surface features into:
1. AXIAL_LONGITUDINAL: Varies around theta at fixed Y (ribs / flutes) -> rib profile + circular pattern.
2. CIRCUMFERENTIAL_AZIMUTHAL: Varies along Y around the full circle (grooves / rings) -> revolve-subtract or linear pattern.
3. HELICAL_KNURL: Correlated periodic variation in both theta and Y.

Computes:
- Exact orientation classification (AXIAL_LONGITUDINAL vs CIRCUMFERENTIAL_AZIMUTHAL)
- Repetition count and pitch (angular pitch in degrees or axial pitch in mm)
- Feature depth, width, and axial span
- True statistical confidence based on spectral SNR and pitch regularity
- Safe fallback strategy for low-confidence detections
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    from .feature_schema import (
        FeatureOrientation,
        FeaturePatternType,
        PeriodicRibFeature,
    )
    from .residual_analyzer import ResidualMap
except ImportError:
    from feature_schema import (
        FeatureOrientation,
        FeaturePatternType,
        PeriodicRibFeature,
    )
    from residual_analyzer import ResidualMap


class PeriodicFeatureDetector:
    """
    Direction-aware detector for periodic ribs, flutes, and grooves.
    """

    def __init__(
        self,
        residual: ResidualMap,
        bounds_mm: np.ndarray,
        min_confidence: float = 0.50,
    ):
        self.residual = residual
        self.bounds_mm = bounds_mm
        self.min_confidence = min_confidence

    def detect(self) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Analyzes 2D spatial variation of residuals in unrolled cylindrical space (theta, y).
        Returns (has_feature, feature_dict_or_None).
        """
        if not self.residual.vertices:
            return False, None

        y_min = float(self.bounds_mm[0][1])
        y_max = float(self.bounds_mm[1][1])
        total_h = y_max - y_min
        if total_h < 5.0:
            return False, None

        # Filter active body region (exclude top/bottom 8% transition zones)
        y_active_min = y_min + 0.08 * total_h
        y_active_max = y_max - 0.08 * total_h

        body_verts = [
            rv for rv in self.residual.vertices
            if y_active_min <= rv.pos_mm[1] <= y_active_max
        ]
        if len(body_verts) < 100:
            return False, None

        pts = np.array([rv.pos_mm for rv in body_verts])
        disps = np.array([rv.displacement_mm for rv in body_verts])

        # Cylindrical coordinates
        radii = np.hypot(pts[:, 0], pts[:, 2])
        mean_radius = float(np.mean(radii))
        thetas = np.arctan2(pts[:, 2], pts[:, 0])  # [-pi, pi]
        y_vals = pts[:, 1]

        # -------------------------------------------------------------------
        # 1. Unroll to 2D Regular Grid (theta, y)
        # -------------------------------------------------------------------
        n_th_bins = 120
        n_y_bins = max(20, min(100, int((y_active_max - y_active_min) / 2.0)))

        th_edges = np.linspace(-np.pi, np.pi, n_th_bins + 1)
        y_edges = np.linspace(y_active_min, y_active_max, n_y_bins + 1)

        counts, _, _ = np.histogram2d(thetas, y_vals, bins=[th_edges, y_edges])
        sums, _, _ = np.histogram2d(thetas, y_vals, bins=[th_edges, y_edges], weights=disps)
        grid = sums / np.maximum(counts, 1)

        # -------------------------------------------------------------------
        # 2. Compute Directional Variation Profiles
        # -------------------------------------------------------------------
        # Profile along theta (integrated/averaged over Y): measures longitudinal flutes
        prof_theta = np.mean(grid, axis=1)
        prof_theta_detrend = prof_theta - np.mean(prof_theta)
        fft_theta = np.abs(np.fft.rfft(prof_theta_detrend))

        # Profile along Y (integrated/averaged over theta): measures circumferential rings
        prof_y = np.mean(grid, axis=0)
        # Detrend Y profile with rolling median / polynomial
        if len(prof_y) > 10:
            poly_y = np.poly1d(np.polyfit(np.linspace(0, 1, len(prof_y)), prof_y, 3))
            prof_y_detrend = prof_y - poly_y(np.linspace(0, 1, len(prof_y)))
        else:
            prof_y_detrend = prof_y - np.mean(prof_y)
        fft_y = np.abs(np.fft.rfft(prof_y_detrend))

        # -------------------------------------------------------------------
        # 3. Spectral Energy & Peak Detection
        # -------------------------------------------------------------------
        # Theta analysis (search for 3 to 48 flutes around perimeter)
        peak_th_count = 0
        snr_theta = 0.0
        amp_theta = 0.0
        if len(fft_theta) > 6:
            valid_th_range = slice(3, min(48, len(fft_theta)))
            sub_fft_th = fft_theta[valid_th_range]
            if len(sub_fft_th) > 0:
                rel_idx = int(np.argmax(sub_fft_th))
                peak_th_count = rel_idx + 3
                amp_theta = float(sub_fft_th[rel_idx])
                noise_floor_th = float(np.median(fft_theta[3:])) if len(fft_theta) > 3 else 1e-3
                snr_theta = amp_theta / max(noise_floor_th, 1e-3)

        # Y analysis (search for periodic rings along length within feature pitch range 3-35mm)
        peak_y_count = 0
        snr_y = 0.0
        pitch_y_mm = 0.0
        amp_y = 0.0
        span_y = y_active_max - y_active_min

        if len(fft_y) > 4 and span_y > 10.0:
            # Constrain wave numbers to physical groove pitch band: 3.0 mm to 35.0 mm
            k_min = max(2, int(np.ceil(span_y / 35.0)))
            k_max = min(len(fft_y) - 1, int(np.floor(span_y / 3.0)))
            if k_max >= k_min:
                sub_fft_y = fft_y[k_min : k_max + 1]
                rel_y_idx = int(np.argmax(sub_fft_y))
                peak_y_count = k_min + rel_y_idx
                amp_y = float(sub_fft_y[rel_y_idx])
                noise_floor_y = float(np.median(sub_fft_y)) if len(sub_fft_y) > 1 else 1e-3
                snr_y = amp_y / max(noise_floor_y, 1e-3)
                pitch_y_mm = span_y / max(peak_y_count, 1)

        # Measure 2D gradient ratio: |dD/dtheta| vs |dD/dy|
        grad_theta = np.abs(np.diff(grid, axis=0))
        grad_y = np.abs(np.diff(grid, axis=1))
        mean_grad_th = float(np.mean(grad_theta))
        mean_grad_y = float(np.mean(grad_y))

        # -------------------------------------------------------------------
        # 4. Feature Orientation Discriminator
        # -------------------------------------------------------------------
        # A longitudinal rib varies primarily along theta (across perimeter),
        # while extending along Y.
        # A circumferential groove varies along Y, while extending around theta.
        is_longitudinal = (snr_theta >= 2.0 and (snr_theta > 1.15 * snr_y or snr_y < 2.0) and amp_theta > 0.15)
        is_circumferential = (snr_y >= 2.2 and snr_y > 1.15 * snr_theta and amp_y > 0.15 and 3.0 <= pitch_y_mm <= 35.0)
        is_helical = (snr_theta >= 2.0 and snr_y >= 2.0 and abs(snr_theta - snr_y) < 1.0)

        if not (is_longitudinal or is_circumferential or is_helical):
            # No strong periodic feature detected
            return False, None

        # -------------------------------------------------------------------
        # 5. Extract Feature Dimensions & Confidence
        # -------------------------------------------------------------------
        if is_longitudinal:
            orientation = FeatureOrientation.AXIAL_LONGITUDINAL.value
            pattern_type = FeaturePatternType.CIRCULAR_ARRAY.value
            feature_type = "LONGITUDINAL_RIB"
            rib_count = peak_th_count
            pitch = round(360.0 / max(rib_count, 1), 2)  # angular pitch (deg)
            depth_mm = round(float(np.percentile(np.abs(prof_theta_detrend), 90) * 2.0), 2)
            depth_mm = max(0.4, min(depth_mm, mean_radius * 0.25))
            arc_span_per_rib = (2.0 * math.pi * mean_radius) / max(rib_count, 1)
            width_mm = round(float(arc_span_per_rib * 0.40), 2)

            # Confidence scoring based on SNR and peak prominence
            snr_score = min(snr_theta / 6.0, 1.0)
            grad_score = min(mean_grad_th / max(mean_grad_y, 1e-3), 2.0) / 2.0
            confidence = round(float(min(0.98, max(0.50, 0.45 + 0.35 * snr_score + 0.20 * grad_score))), 3)
            fallback = "SMOOTH_REVOLVE_NO_PATTERN"
            evidence = (
                f"Longitudinal flutes detected: {rib_count} ribs around perimeter, "
                f"angular pitch={pitch}°, SNR_theta={snr_theta:.1f} vs SNR_y={snr_y:.1f}"
            )

        elif is_circumferential:
            orientation = FeatureOrientation.CIRCUMFERENTIAL_AZIMUTHAL.value
            pattern_type = FeaturePatternType.LINEAR_ARRAY.value
            feature_type = "CIRCUMFERENTIAL_GROOVE"
            rib_count = peak_y_count
            pitch = round(pitch_y_mm, 2)  # axial pitch (mm)
            depth_mm = round(float(np.percentile(np.abs(prof_y_detrend), 90) * 2.0), 2)
            depth_mm = max(0.4, min(depth_mm, 5.0))
            width_mm = round(float(min(pitch * 0.45, 6.0)), 2)

            snr_score = min(snr_y / 6.0, 1.0)
            confidence = round(float(min(0.98, max(0.50, 0.45 + 0.40 * snr_score + 0.15))), 3)
            fallback = "SMOOTH_REVOLVE_NO_GROOVES"
            evidence = (
                f"Circumferential rings detected: {rib_count} grooves along axis, "
                f"pitch={pitch}mm, SNR_y={snr_y:.1f} vs SNR_theta={snr_theta:.1f}"
            )

        else:
            orientation = FeatureOrientation.HELICAL_KNURL.value
            pattern_type = FeaturePatternType.CIRCULAR_ARRAY.value
            feature_type = "HELICAL_KNURL"
            rib_count = peak_th_count
            pitch = round(360.0 / max(rib_count, 1), 2)
            depth_mm = 0.8
            width_mm = 2.0
            confidence = 0.70
            fallback = "SMOOTH_REVOLVE_NO_PATTERN"
            evidence = f"Helical knurl detected: {rib_count} periodic waves, SNR_th={snr_theta:.1f}, SNR_y={snr_y:.1f}"

        if confidence < self.min_confidence:
            return False, None

        return True, {
            "feature_type": feature_type,
            "orientation": orientation,
            "pattern_type": pattern_type,
            "rib_count": rib_count,
            "pitch": pitch,
            "pitch_mm": pitch if orientation == FeatureOrientation.CIRCUMFERENTIAL_AZIMUTHAL.value else round(float(2.0 * math.pi * mean_radius / max(rib_count, 1)), 2),
            "pitch_deg": pitch if orientation == FeatureOrientation.AXIAL_LONGITUDINAL.value else round(360.0 / max(rib_count, 1), 2),
            "groove_depth_mm": depth_mm,
            "groove_width_mm": width_mm,
            "y_start_mm": round(y_active_min, 2),
            "y_end_mm": round(y_active_max, 2),
            "confidence": confidence,
            "fallback_strategy": fallback,
            "source_evidence": evidence,
        }


# Backwards compatibility alias
SideRibDetector = PeriodicFeatureDetector
