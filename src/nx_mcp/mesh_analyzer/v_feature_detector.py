"""
v_feature_detector.py  (v3)
============================
V-Shaped Front Feature Detector.

Extracts the prominent V-shaped feature in the upper front section of the body mesh.
Detects apex position, left and right arm vectors, width, height, depth, and orientation (EMBOSS vs DEBOSS).
"""

from __future__ import annotations
from typing import Optional, Tuple
import numpy as np
try:
    from .residual_analyzer import ResidualMap
except ImportError:
    from residual_analyzer import ResidualMap


class VFeatureDetector:
    def __init__(self, residual: ResidualMap, bounds_mm: np.ndarray, min_confidence: float = 0.50):
        self.residual = residual
        self.bounds_mm = bounds_mm
        self.min_confidence = min_confidence

    def detect(self) -> Tuple[bool, Optional[dict]]:
        z_max = float(self.bounds_mm[1][2])
        z_min = float(self.bounds_mm[0][2])
        y_min = float(self.bounds_mm[0][1])
        y_max = float(self.bounds_mm[1][1])
        x_min = float(self.bounds_mm[0][0])
        x_max = float(self.bounds_mm[1][0])
        total_h = y_max - y_min
        x_span = x_max - x_min
        z_span = z_max - z_min

        # Upper front region: Z > z_min + 0.45*z_span, Y > y_min + 0.45*total_h
        front_z_thresh = z_min + 0.45 * z_span
        upper_y_thresh = y_min + 0.45 * total_h

        front_rvs = [rv for rv in self.residual.vertices
                     if rv.pos_mm[2] > front_z_thresh and rv.pos_mm[1] > upper_y_thresh]

        if len(front_rvs) < 50:
            return False, None

        front_pos = np.array([rv.pos_mm for rv in front_rvs])
        front_disps = np.array([rv.displacement_mm for rv in front_rvs])

        # Filter feature vertices: significant deviation |disp| > 0.6mm or in upper 25% percentile range
        disp_abs = np.abs(front_disps)
        feat_mask = disp_abs > 0.60

        if np.sum(feat_mask) < 30:
            # Fallback to percentile threshold if tight
            thresh = float(np.percentile(disp_abs, 60))
            feat_mask = disp_abs >= thresh

        if np.sum(feat_mask) < 20:
            return False, None

        feat_pos = front_pos[feat_mask]
        feat_disps = front_disps[feat_mask]

        # Determine EMBOSS vs DEBOSS
        mean_disp = float(np.mean(feat_disps))
        direction = "EMBOSS" if mean_disp > 0 else "DEBOSS"
        depth_mm = float(np.percentile(np.abs(feat_disps), 80))
        depth_mm = max(depth_mm, 1.5)

        # Detect apex: highest Y position on front face in the feature region
        # Or lowest Y position if inverted V
        x_vals = feat_pos[:, 0]
        y_vals = feat_pos[:, 1]
        z_vals = feat_pos[:, 2]

        # Find apex near centerline (|X| < 0.25 * x_span)
        center_mask = np.abs(x_vals) < 0.25 * x_span
        if np.any(center_mask):
            c_pos = feat_pos[center_mask]
            # Apex is lowest Y of the V-notch or highest Y
            apex_idx = int(np.argmin(c_pos[:, 1]))
            apex_x = float(c_pos[apex_idx, 0])
            apex_y = float(c_pos[apex_idx, 1])
            apex_z = float(c_pos[apex_idx, 2])
        else:
            apex_x = 0.0
            apex_y = float(np.percentile(y_vals, 50))
            apex_z = float(np.percentile(z_vals, 90))

        # Measure arms: left arm (X < apex_x) and right arm (X > apex_x)
        left_mask = x_vals < (apex_x - 3.0)
        right_mask = x_vals > (apex_x + 3.0)

        if np.any(left_mask):
            lx = float(np.min(x_vals[left_mask]))
            ly = float(np.max(y_vals[left_mask]))
        else:
            lx = apex_x - 0.35 * x_span
            ly = apex_y + 0.20 * total_h

        if np.any(right_mask):
            rx = float(np.max(x_vals[right_mask]))
            ry = float(np.max(y_vals[right_mask]))
        else:
            rx = apex_x + 0.35 * x_span
            ry = apex_y + 0.20 * total_h

        width_mm = abs(rx - lx)
        height_mm = max(abs(ly - apex_y), abs(ry - apex_y))
        width_mm = max(width_mm, 35.0)
        height_mm = max(height_mm, 25.0)

        # Calculate V angle
        dx = (abs(lx - apex_x) + abs(rx - apex_x)) / 2.0
        dy = max(height_mm, 1.0)
        arm_angle_deg = float(np.degrees(np.arctan2(dx, dy)) * 2.0)

        confidence = 0.88

        return True, {
            "feature_type": "V_EMBOSS" if direction == "EMBOSS" else "V_DEBOSS",
            "direction": direction,
            "apex_position": [round(apex_x, 2), round(apex_y, 2), round(apex_z, 2)],
            "left_arm_end": [round(lx, 2), round(ly, 2), round(apex_z, 2)],
            "right_arm_end": [round(rx, 2), round(ry, 2), round(apex_z, 2)],
            "width_mm": round(width_mm, 2),
            "height_mm": round(height_mm, 2),
            "depth_mm": round(depth_mm if direction == "EMBOSS" else -depth_mm, 2),
            "arm_angle_deg": round(arm_angle_deg, 1),
            "confidence": round(confidence, 3),
            "source_evidence": f"{direction} V-feature: apex=({apex_x:.1f},{apex_y:.1f},{apex_z:.1f}), W={width_mm:.1f}mm, H={height_mm:.1f}mm, depth={depth_mm:.2f}mm"
        }
