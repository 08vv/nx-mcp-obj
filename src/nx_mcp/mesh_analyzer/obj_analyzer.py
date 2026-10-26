"""
obj_analyzer.py
================
Complete OBJ Mesh Analysis Module.

Performs category-independent geometric & topological analysis of the input mesh:
1. Full bounding box [X_min, X_max, Y_min, Y_max, Z_min, Z_max].
2. Connected components decomposition (source_component_count).
3. Geometric metrics: surface area, volume, centroid, principal axes.
4. Per-component bounding box, vertex/face count, surface area, and position.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np
import trimesh


@dataclass
class ComponentInfo:
    """Analysis record for one connected mesh component."""
    component_id: int
    vertex_count: int
    face_count: int
    surface_area_mm2: float
    bounds_mm: np.ndarray       # [[x_min, y_min, z_min], [x_max, y_max, z_max]] in mm
    centroid_mm: np.ndarray     # [cx, cy, cz] in mm
    is_main_body: bool = False
    mesh: trimesh.Trimesh = field(repr=False, default=None)


@dataclass
class OBJAnalysis:
    """Full geometric and topological analysis of source OBJ mesh."""
    total_vertices: int
    total_faces: int
    bounds_mm: np.ndarray          # [[x_min, y_min, z_min], [x_max, y_max, z_max]] in mm
    centroid_mm: np.ndarray        # [cx, cy, cz] in mm
    total_surface_area_mm2: float
    volume_mm3: float
    source_component_count: int
    components: List[ComponentInfo] = field(default_factory=list)
    principal_axes: np.ndarray = field(default_factory=lambda: np.eye(3))

    @property
    def height_mm(self) -> float:
        return float(self.bounds_mm[1][1] - self.bounds_mm[0][1])

    @property
    def width_mm(self) -> float:
        return float(self.bounds_mm[1][0] - self.bounds_mm[0][0])

    @property
    def depth_mm(self) -> float:
        return float(self.bounds_mm[1][2] - self.bounds_mm[0][2])


class OBJAnalyzer:
    """
    Performs comprehensive, category-independent mesh analysis.
    """

    def __init__(self, mesh: trimesh.Trimesh):
        self.mesh = mesh

    def analyze(self) -> OBJAnalysis:
        """Runs complete OBJ analysis."""
        v_mm = self.mesh.vertices * 100.0   # convert to mm
        f = self.mesh.faces

        # Bounding box in mm
        bounds_mm = np.array([
            v_mm.min(axis=0),
            v_mm.max(axis=0)
        ])

        centroid_mm = np.mean(v_mm, axis=0)

        # Surface area in mm² (mesh area is in dm² or m²; scale by 100² = 10,000)
        area_mm2 = float(self.mesh.area * 10000.0)

        # Volume estimation (if watertight, else convex hull volume)
        try:
            vol_mm3 = float(abs(self.mesh.volume) * 1000000.0)
        except Exception:
            vol_mm3 = float(self.mesh.convex_hull.volume * 1000000.0)

        # Principal axes via PCA on vertices
        try:
            cov = np.cov(v_mm.T)
            evals, evecs = np.linalg.eigh(cov)
            idx = np.argsort(evals)[::-1]
            principal_axes = evecs[:, idx]
        except Exception:
            principal_axes = np.eye(3)

        # Connected components analysis
        try:
            sub_meshes = self.mesh.split(only_watertight=False)
        except Exception:
            sub_meshes = [self.mesh]

        component_count = len(sub_meshes)
        components: List[ComponentInfo] = []

        # Find main component by face count / surface area
        main_idx = 0
        max_area = 0.0

        for i, sub in enumerate(sub_meshes):
            # Ignore tiny noise fragments with fewer than 500 faces
            if len(sub.faces) < 500:
                continue
            sub_v_mm = sub.vertices * 100.0
            sub_bounds = np.array([sub_v_mm.min(axis=0), sub_v_mm.max(axis=0)])
            sub_centroid = np.mean(sub_v_mm, axis=0)
            sub_area = float(sub.area * 10000.0)

            c_info = ComponentInfo(
                component_id=len(components),
                vertex_count=len(sub.vertices),
                face_count=len(sub.faces),
                surface_area_mm2=sub_area,
                bounds_mm=sub_bounds,
                centroid_mm=sub_centroid,
                mesh=sub
            )
            components.append(c_info)

            if sub_area > max_area:
                max_area = sub_area
                main_idx = len(components) - 1

        if not components:
            # Fallback if all sub-meshes were < 500 faces
            components.append(ComponentInfo(
                component_id=0,
                vertex_count=len(self.mesh.vertices),
                face_count=len(self.mesh.faces),
                surface_area_mm2=area_mm2,
                bounds_mm=bounds_mm,
                centroid_mm=centroid_mm,
                is_main_body=True,
                mesh=self.mesh
            ))
            main_idx = 0

        if components:
            components[main_idx].is_main_body = True

        return OBJAnalysis(
            total_vertices=len(self.mesh.vertices),
            total_faces=len(self.mesh.faces),
            bounds_mm=bounds_mm,
            centroid_mm=centroid_mm,
            total_surface_area_mm2=area_mm2,
            volume_mm3=vol_mm3,
            source_component_count=component_count,
            components=components,
            principal_axes=principal_axes
        )
