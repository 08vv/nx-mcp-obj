"""
feature_segmenter.py
====================
Layer A & B Feature Segmentation Engine.

Detects discrete local features (indents, ribs, holes, pockets) by:
1. Computing residual point deviations |M_raw - B_base|.
2. Running DBSCAN spatial clustering to isolate discrete feature instances.
3. Analyzing rotational pattern symmetry (count N, pitch angle delta_theta).
"""

from __future__ import annotations

import math
import numpy as np
import trimesh
try:
    from sklearn.cluster import DBSCAN
except ImportError:
    DBSCAN = None


class FeatureSegmenter:
    def __init__(self, raw_mesh: trimesh.Trimesh, base_mesh: trimesh.Trimesh | None = None):
        self.raw_mesh = raw_mesh
        self.base_mesh = base_mesh

    def segment_features(self, distance_threshold_mm: float = 0.5, eps_mm: float = 5.0, min_samples: int = 10) -> dict:
        """Segments discrete local features and detects circular pattern layout."""
        verts = self.raw_mesh.vertices
        
        if self.base_mesh is not None:
            # Distance from raw mesh vertices to base mesh surface
            closest_pts, distances, _ = trimesh.proximity.closest_point(self.base_mesh, verts)
        else:
            # Fallback: distance from PCA cylindrical surface
            r_coords = np.hypot(verts[:, 0], verts[:, 2])
            r_mean = np.mean(r_coords)
            distances = np.abs(r_coords - r_mean)

        # Active feature points exceeding threshold
        feature_mask = distances > (distance_threshold_mm / 100.0 if verts[:, 1].max() < 5.0 else distance_threshold_mm)
        feature_pts = verts[feature_mask]

        if len(feature_pts) < min_samples:
            return {
                "features_found": False,
                "feature_count": 0,
                "features": [],
                "pattern": {"type": "none", "count": 1, "pitch_angle_deg": 0.0}
            }

        if DBSCAN is None:
            return {
                "features_found": False,
                "feature_count": 0,
                "features": [],
                "pattern": {"type": "none", "count": 1, "pitch_angle_deg": 0.0},
                "warning": "scikit-learn not available for DBSCAN clustering"
            }

        # DBSCAN Spatial Clustering
        db = DBSCAN(eps=eps_mm, min_samples=min_samples).fit(feature_pts)
        labels = db.labels_
        unique_labels = [lbl for lbl in set(labels) if lbl != -1]

        features = []
        angles_deg = []

        for lbl in unique_labels:
            cluster_pts = feature_pts[labels == lbl]
            centroid = cluster_pts.mean(axis=0)
            pt_min = cluster_pts.min(axis=0)
            pt_max = cluster_pts.max(axis=0)
            bbox_size = (pt_max - pt_min).tolist()

            angle_rad = math.atan2(centroid[2], centroid[0])
            angle_deg = (math.degrees(angle_rad) + 360.0) % 360.0
            angles_deg.append(angle_deg)

            features.append({
                "id": int(lbl + 1),
                "centroid": [float(c) for c in centroid],
                "bounding_size_mm": [float(s) for s in bbox_size],
                "angle_deg": float(angle_deg),
                "point_count": len(cluster_pts)
            })

        # Pattern Recognition (Rotational Symmetry)
        pattern_info = {"type": "none", "count": len(unique_labels), "pitch_angle_deg": 0.0}
        if len(angles_deg) >= 2:
            sorted_angles = sorted(angles_deg)
            diffs = np.diff(sorted_angles)
            wrap_diff = (360.0 - sorted_angles[-1]) + sorted_angles[0]
            all_diffs = np.append(diffs, wrap_diff)

            mean_diff = float(np.mean(all_diffs))
            std_diff = float(np.std(all_diffs))

            # If angular spacing is uniform (std < 15 degrees)
            if std_diff < 15.0:
                pattern_info = {
                    "type": "circular",
                    "count": len(unique_labels),
                    "pitch_angle_deg": round(360.0 / len(unique_labels), 2),
                    "is_uniform": True
                }
            else:
                pattern_info = {
                    "type": "circular",
                    "count": len(unique_labels),
                    "pitch_angle_deg": round(mean_diff, 2),
                    "is_uniform": False
                }

        return {
            "features_found": len(unique_labels) > 0,
            "feature_count": len(unique_labels),
            "features": features,
            "pattern": pattern_info
        }
