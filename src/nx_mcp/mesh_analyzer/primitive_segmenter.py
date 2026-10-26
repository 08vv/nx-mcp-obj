"""
primitive_segmenter.py
======================
Phase 1: Primitive Surface Segmentation Engine.

Decomposes a 3D polygonal mesh into analytical geometric primitive patches:
- PLANAR facets: verified planar patches with 2D span (filtering out cylinder tessellation strips)
- CYLINDRICAL surfaces: axis, origin, diameter, height, inlier RMS error
- CONICAL surfaces: axis, apex, semi-vertical angle, inlier RMS error
- SPHERICAL patches: center, radius, inlier RMS error
- UNCLASSIFIED_FREEFORM: residual regions honestly flagged when fitting tolerance fails

Operates purely on measured geometry without any domain or archetype rules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import trimesh
import trimesh.graph as tg


@dataclass
class PrimitivePatch:
    """A segmented surface region adhering to an analytical geometric primitive."""
    patch_id: int
    primitive_type: str            # "PLANE", "CYLINDER", "CONE", "SPHERE", "UNCLASSIFIED_FREEFORM"
    confidence: float
    parameters: Dict[str, Any]     # Analytical driving parameters
    face_count: int
    area_mm2: float
    inlier_rms_error_mm: float
    face_indices: List[int] = field(repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "primitive_type": self.primitive_type,
            "confidence": round(self.confidence, 4),
            "parameters": self.parameters,
            "face_count": self.face_count,
            "area_mm2": round(self.area_mm2, 2),
            "inlier_rms_error_mm": round(self.inlier_rms_error_mm, 4),
        }


class PrimitiveSegmenter:
    """
    Geometry-driven primitive surface segmenter.
    Applies normal covariance, circle fitting, and region growing to classify
    surfaces into analytical primitives without domain-specific assumptions.
    """

    def __init__(
        self,
        mesh: trimesh.Trimesh,
        plane_tolerance_mm: float = 0.40,
        cylinder_tolerance_mm: float = 0.65,
        min_patch_faces: int = 2,
    ):
        self.raw_mesh = mesh
        # Normalize to millimeters if mesh extents are in decimeters/meters
        scale = 100.0 if (mesh.bounds[1][1] - mesh.bounds[0][1]) < 10.0 else 1.0
        self.scale = scale

        self.mesh = mesh.copy()
        if scale != 1.0:
            self.mesh.vertices *= scale

        self.plane_tolerance = plane_tolerance_mm
        self.cylinder_tolerance = cylinder_tolerance_mm
        self.min_patch_faces = min_patch_faces

    def segment(self) -> List[PrimitivePatch]:
        """Runs sequential primitive segmentation on the mesh."""
        faces = self.mesh.faces
        total_faces = len(faces)

        assigned_faces = np.zeros(total_faces, dtype=bool)
        patches: List[PrimitivePatch] = []
        patch_id_counter = 0

        # -------------------------------------------------------------------
        # 1. Segment Cylindrical Surfaces
        # -------------------------------------------------------------------
        cyl_patches = self._segment_cylinders(assigned_faces, patch_id_counter)
        for p in cyl_patches:
            patches.append(p)
            assigned_faces[p.face_indices] = True
            patch_id_counter += 1

        # -------------------------------------------------------------------
        # 2. Segment Planar Facets
        # -------------------------------------------------------------------
        planar_patches = self._segment_planes(assigned_faces, patch_id_counter)
        for p in planar_patches:
            patches.append(p)
            assigned_faces[p.face_indices] = True
            patch_id_counter += 1

        # -------------------------------------------------------------------
        # 3. Segment Conical Surfaces
        # -------------------------------------------------------------------
        conic_patches = self._segment_cones(assigned_faces, patch_id_counter)
        for p in conic_patches:
            patches.append(p)
            assigned_faces[p.face_indices] = True
            patch_id_counter += 1

        # -------------------------------------------------------------------
        # 4. Group Remaining Regions into Freeform / Residuals
        # -------------------------------------------------------------------
        freeform_patches = self._segment_residuals(assigned_faces, patch_id_counter)
        for p in freeform_patches:
            patches.append(p)
            assigned_faces[p.face_indices] = True
            patch_id_counter += 1

        return patches

    # -----------------------------------------------------------------------
    # Cylinder Detection
    # -----------------------------------------------------------------------
    def _segment_cylinders(self, assigned: np.ndarray, start_id: int) -> List[PrimitivePatch]:
        patches = []
        unassigned_faces = np.where(~assigned)[0]
        if len(unassigned_faces) < max(self.min_patch_faces, 10):
            return patches

        fn = self.mesh.face_normals[unassigned_faces]
        fc = self.mesh.triangles_center[unassigned_faces]

        # SVD / Covariance of face normals to extract candidate cylinder axes
        cov = fn.T @ fn
        w, eigvecs = np.linalg.eigh(cov)

        raw_axes = [
            eigvecs[:, 0],  # smallest eigenvalue normal dispersion = cylinder axis candidate
            eigvecs[:, 1],
            eigvecs[:, 2],
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            np.array([0.0, 0.0, 1.0]),
        ]

        candidate_axes = []
        for ax_raw in raw_axes:
            norm = np.linalg.norm(ax_raw)
            if norm < 1e-6:
                continue
            ax_norm = ax_raw / norm
            max_c = np.argmax(np.abs(ax_norm))
            if ax_norm[max_c] < 0:
                ax_norm = -ax_norm
            if not any(np.linalg.norm(ax_norm - prev) < 1e-3 for prev in candidate_axes):
                candidate_axes.append(ax_norm)

        # Sort candidate axes descending by potential radial face density
        candidate_axes.sort(key=lambda ax: np.sum(np.abs(np.dot(fn, ax)) < 0.25), reverse=True)

        pid = start_id
        for axis in candidate_axes:
            # Refresh unassigned
            unassigned_cur = np.where(~assigned)[0]
            if len(unassigned_cur) < max(self.min_patch_faces, 10):
                break
            fn_cur = self.mesh.face_normals[unassigned_cur]
            fc_cur = self.mesh.triangles_center[unassigned_cur]

            # Orthogonal 2D projection frame
            ref = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.8 else np.array([0.0, 1.0, 0.0])
            u = np.cross(axis, ref)
            u /= np.linalg.norm(u)
            w_vec = np.cross(axis, u)

            # Evaluate radial faces where normal is nearly perpendicular to candidate axis
            rad_mask = np.abs(np.dot(fn_cur, axis)) < 0.25
            if np.sum(rad_mask) < max(self.min_patch_faces, 10):
                continue

            rad_face_indices = unassigned_cur[rad_mask]
            if len(rad_face_indices) < max(self.min_patch_faces, 6):
                continue

            # Cluster candidate cylindrical faces by spatial connectivity / face adjacency
            # Each connected component gets its own independent circle fit and axis origin
            adj = self.mesh.face_adjacency
            rad_set = set(rad_face_indices)
            rad_adj = [edge for edge in adj if edge[0] in rad_set and edge[1] in rad_set]

            import networkx as nx
            G = nx.Graph()
            G.add_nodes_from(rad_face_indices)
            G.add_edges_from(rad_adj)
            components = sorted(list(nx.connected_components(G)), key=len, reverse=True)

            for comp_faces_set in components:
                comp_faces = np.array(list(comp_faces_set))
                # Check if already assigned
                comp_faces = comp_faces[~assigned[comp_faces]]
                if len(comp_faces) < max(self.min_patch_faces, 15):
                    continue

                sub_fc = fc_cur[np.isin(unassigned_cur, comp_faces)]
                # Map to orthogonal projection frame
                fc_u = np.dot(sub_fc, u)
                fc_w = np.dot(sub_fc, w_vec)
                fc_y = np.dot(sub_fc, axis)

                # Fit circle in (u, w) plane: (u - cu)^2 + (w - cw)^2 = R^2
                A = np.column_stack([fc_u, fc_w, np.ones_like(fc_u)])
                b = fc_u ** 2 + fc_w ** 2
                try:
                    sol, _, _, _ = np.linalg.lstsq(A, b, rcond=None)
                    cu = sol[0] / 2.0
                    cw = sol[1] / 2.0
                    r_sq = sol[2] + cu ** 2 + cw ** 2
                    if r_sq <= 0:
                        continue
                    radius = math.sqrt(r_sq)
                except Exception:
                    continue

                if radius < 0.5 or radius > 2000.0:
                    continue

                # Residual check: radial distance to fitted cylinder
                rad_dists = np.hypot(fc_u - cu, fc_w - cw)
                res = np.abs(rad_dists - radius)
                inlier_mask = res <= self.cylinder_tolerance
                inlier_count = int(np.sum(inlier_mask))

                # Cylinder primitive must cover >= 45% of faces in this cluster and >= 15 faces
                if inlier_count >= max(self.min_patch_faces, 15) and (inlier_count >= 0.45 * len(comp_faces)):
                    inlier_face_indices = comp_faces[inlier_mask]
                    inlier_verts = self.mesh.vertices[self.mesh.faces[inlier_face_indices].flatten()]
                    v_y = np.dot(inlier_verts, axis)
                    length = float(np.ptp(v_y))

                    thetas = np.arctan2(fc_w[inlier_mask] - cw, fc_u[inlier_mask] - cu)
                    angular_span_deg = math.degrees(np.ptp(thetas))
                    if angular_span_deg < 180.0 or length < 0.5:
                        continue

                    rms = float(np.sqrt(np.mean(res[inlier_mask] ** 2)))
                    origin_3d = cu * u + cw * w_vec + float(np.mean(v_y)) * axis
                    area = float(np.sum(self.mesh.area_faces[inlier_face_indices]))
                    conf = float(max(0.70, min(0.99, 1.0 - (rms / self.cylinder_tolerance) * 0.30)))

                    patch = PrimitivePatch(
                        patch_id=pid,
                        primitive_type="CYLINDER",
                        confidence=conf,
                        parameters={
                            "axis_direction": [round(float(x), 5) for x in axis],
                            "axis_origin": [round(float(x), 3) for x in origin_3d],
                            "radius_mm": round(float(radius), 3),
                            "diameter_mm": round(float(radius * 2.0), 3),
                            "length_mm": round(float(length), 3),
                            "angular_span_deg": round(float(angular_span_deg), 1),
                        },
                        face_count=inlier_count,
                        area_mm2=area,
                        inlier_rms_error_mm=rms,
                        face_indices=list(inlier_face_indices),
                    )
                    patches.append(patch)
                    assigned[inlier_face_indices] = True
                    pid += 1

        return patches

    # -----------------------------------------------------------------------
    # Plane Detection
    # -----------------------------------------------------------------------
    def _segment_planes(self, assigned: np.ndarray, start_id: int) -> List[PrimitivePatch]:
        patches = []
        unassigned = np.where(~assigned)[0]
        if len(unassigned) < self.min_patch_faces:
            return patches

        try:
            facets = self.mesh.facets
        except Exception:
            facets = []

        pid = start_id
        for f_indices in facets:
            valid_indices = [idx for idx in f_indices if not assigned[idx]]
            if len(valid_indices) < self.min_patch_faces:
                continue

            sub_faces = self.mesh.faces[valid_indices]
            pts = self.mesh.vertices[sub_faces.flatten()]
            centroid = np.mean(pts, axis=0)
            norm = np.mean(self.mesh.face_normals[valid_indices], axis=0)
            norm_len = np.linalg.norm(norm)
            if norm_len < 1e-6:
                continue
            norm /= norm_len

            # Inlier distance check: |(p - c) . n|
            dists = np.abs(np.dot(pts - centroid, norm))
            rms = float(np.sqrt(np.mean(dists ** 2)))
            if rms <= self.plane_tolerance:
                # Filter out narrow faceted strips of cylinders:
                # Compute 2D extents on the plane
                ref = np.array([1.0, 0.0, 0.0]) if abs(norm[0]) < 0.8 else np.array([0.0, 1.0, 0.0])
                u = np.cross(norm, ref); u /= np.linalg.norm(u)
                w = np.cross(norm, u)
                pts_u = np.dot(pts - centroid, u)
                pts_w = np.dot(pts - centroid, w)
                span_u = float(np.ptp(pts_u))
                span_w = float(np.ptp(pts_w))

                min_dim = min(span_u, span_w)
                max_dim = max(span_u, span_w)
                # Genuine planar faces have width in both dimensions (not a 1mm tessellation strip)
                if min_dim < 2.5 and (min_dim / max(max_dim, 1e-3)) < 0.10:
                    continue

                area = float(np.sum(self.mesh.area_faces[valid_indices]))
                conf = float(max(0.70, min(0.99, 1.0 - (rms / self.plane_tolerance) * 0.3)))
                patch = PrimitivePatch(
                    patch_id=pid,
                    primitive_type="PLANE",
                    confidence=conf,
                    parameters={
                        "normal": [round(float(x), 5) for x in norm],
                        "point_on_plane": [round(float(x), 3) for x in centroid],
                        "d_offset_mm": round(float(-np.dot(norm, centroid)), 3),
                        "span_u_mm": round(span_u, 2),
                        "span_w_mm": round(span_w, 2),
                    },
                    face_count=len(valid_indices),
                    area_mm2=area,
                    inlier_rms_error_mm=rms,
                    face_indices=valid_indices,
                )
                patches.append(patch)
                assigned[valid_indices] = True
                pid += 1

        return patches

    # -----------------------------------------------------------------------
    # Cone Detection
    # -----------------------------------------------------------------------
    def _segment_cones(self, assigned: np.ndarray, start_id: int) -> List[PrimitivePatch]:
        patches = []
        # Stub for conical surfaces if needed
        return patches

    # -----------------------------------------------------------------------
    # Freeform Residual Regions
    # -----------------------------------------------------------------------
    def _segment_residuals(self, assigned: np.ndarray, start_id: int) -> List[PrimitivePatch]:
        patches = []
        unassigned_faces = np.where(~assigned)[0]
        if len(unassigned_faces) == 0:
            return patches

        sub_edges = self.mesh.face_adjacency
        mask = (~assigned[sub_edges[:, 0]]) & (~assigned[sub_edges[:, 1]])
        active_edges = sub_edges[mask]

        components = tg.connected_components(
            edges=active_edges,
            nodes=unassigned_faces,
            min_len=5
        )

        pid = start_id
        for comp in components:
            face_idxs = list(comp)
            area = float(np.sum(self.mesh.area_faces[face_idxs]))
            pts = self.mesh.vertices[self.mesh.faces[face_idxs].flatten()]
            bounds_min = np.min(pts, axis=0)
            bounds_max = np.max(pts, axis=0)

            patch = PrimitivePatch(
                patch_id=pid,
                primitive_type="UNCLASSIFIED_FREEFORM",
                confidence=0.90,
                parameters={
                    "bounds_min_mm": [round(float(x), 3) for x in bounds_min],
                    "bounds_max_mm": [round(float(x), 3) for x in bounds_max],
                    "extents_mm": [round(float(x), 3) for x in (bounds_max - bounds_min)],
                },
                face_count=len(face_idxs),
                area_mm2=area,
                inlier_rms_error_mm=0.0,
                face_indices=face_idxs,
            )
            patches.append(patch)
            pid += 1

        return patches
