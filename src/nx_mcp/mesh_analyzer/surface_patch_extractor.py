"""
surface_patch_extractor.py
===========================
Extracts UV grid guide curves and boundary contours from freeform mesh patches
for Siemens NX Studio Surface (NURBS B-Surface) fitting.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
import numpy as np
import trimesh


class SurfacePatchExtractor:
    """Extracts UV grid curves for NURBS B-surface construction."""

    def __init__(self, mesh: trimesh.Trimesh):
        self.mesh = mesh

    def extract_patch_curves(self, u_count: int = 5, v_count: int = 5) -> Dict[str, Any]:
        """Generates structured UV grid curves spanning the mesh surface."""
        bounds = self.mesh.bounds
        y_min, y_max = bounds[0][1], bounds[1][1]
        y_stations = np.linspace(y_min, y_max, u_count)

        u_curves = []
        for y_val in y_stations:
            mask = np.abs(self.mesh.vertices[:, 1] - y_val) <= (y_max - y_min) / (u_count * 2)
            if np.any(mask):
                sub_v = self.mesh.vertices[mask]
                pts = sub_v[::max(1, len(sub_v) // v_count)].tolist()
                u_curves.append(pts)

        return {
            "u_count": len(u_curves),
            "v_count": v_count,
            "u_curves": u_curves,
            "bounds_mm": (bounds * 100.0).tolist()
        }
