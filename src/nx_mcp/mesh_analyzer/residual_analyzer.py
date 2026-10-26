"""
residual_analyzer.py
=====================
Residual Geometry Analyzer & Post-Build Surface Residual Validator.

1. Reconstructs the approximate base-body mesh from section stations (matching the full
   ring perimeter point count, not truncated to 16).
2. Computes the signed displacement between every OBJ vertex and that base mesh:
   positive = emboss / outward feature, negative = deboss / inward groove.
3. SurfaceResidualValidator: Re-samples generated CAD geometry against raw mesh surface,
   reporting RMS error, Hausdorff distance, and flagging regions exceeding tolerance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from scipy.spatial import KDTree
import trimesh


@dataclass
class ResidualVertex:
    """Deviation record for one OBJ vertex."""
    pos_mm: np.ndarray          # [x, y, z] in mm
    displacement_mm: float      # + outside body, - inside body (groove)
    normal_disp_mm: float       # displacement along body-surface normal
    body_normal: np.ndarray     # outward normal of nearest base-mesh face


@dataclass
class ResidualMap:
    """Full per-vertex residual dataset for one OBJ."""
    vertices: List[ResidualVertex] = field(default_factory=list)
    threshold_mm: float = 0.8   # minimum displacement treated as 'unexplained'

    @property
    def significant(self) -> List[ResidualVertex]:
        """Vertices with |displacement| above threshold (true surface features)."""
        return [v for v in self.vertices if abs(v.displacement_mm) > self.threshold_mm]

    @property
    def inward(self) -> List[ResidualVertex]:
        """OBJ surface is INSIDE the base body → groove / deboss."""
        return [v for v in self.significant if v.displacement_mm < 0]

    @property
    def outward(self) -> List[ResidualVertex]:
        """OBJ surface is OUTSIDE the base body → boss / emboss."""
        return [v for v in self.significant if v.displacement_mm > 0]


class ResidualAnalyzer:
    """
    Computes OBJ-minus-BaseBody residual deviation map.

    Parameters
    ----------
    mesh : trimesh.Trimesh
        The input OBJ (in trimesh units; multiplied by 100 for mm).
    stations : list[dict]
        Section station list. Each dict has 'y' and 'points_2d' ([x, z] mm).
    threshold_mm : float
        Minimum |displacement| to flag as 'unexplained geometry'.
    """

    def __init__(self, mesh: trimesh.Trimesh, stations: List[dict],
                 threshold_mm: float = 0.8):
        self.mesh = mesh
        self.stations = stations
        self.threshold_mm = threshold_mm

    def compute(self) -> ResidualMap:
        """Build residual map. Returns ResidualMap."""
        base_verts, base_faces, base_normals = self._build_base_mesh()
        residual = self._compute_deviation(base_verts, base_faces, base_normals)
        return residual

    def _build_base_mesh(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Triangulate the base body from section stations.
        Dynamically adapts to the actual number of points in points_2d (e.g. 51),
        forming a closed quad strip across all station pairs.
        """
        if len(self.stations) < 2:
            return np.zeros((1, 3)), np.zeros((1, 3), dtype=int), np.zeros((1, 3))

        # Dynamically determine ring size from first valid station
        n_ring = 16
        for st in self.stations:
            pts = st.get("points_2d", [])
            if len(pts) >= 4:
                n_ring = len(pts)
                break

        all_verts: List[List[float]] = []
        for st in self.stations:
            y_val = float(st["y"])
            pts = st.get("points_2d", [])
            if len(pts) < n_ring:
                pts = (list(pts) + [[0.0, 0.0]] * n_ring)[:n_ring]
            elif len(pts) > n_ring:
                pts = pts[:n_ring]
            for (px, pz) in pts:
                all_verts.append([float(px), y_val, float(pz)])

        verts = np.array(all_verts, dtype=np.float64)
        n_st = len(self.stations)
        all_faces: List[List[int]] = []

        # Build closed quad strip between consecutive rings
        for s in range(n_st - 1):
            base_a = s * n_ring
            base_b = (s + 1) * n_ring
            for k in range(n_ring):
                k_next = (k + 1) % n_ring
                a0 = base_a + k
                a1 = base_a + k_next
                b0 = base_b + k
                b1 = base_b + k_next
                all_faces.append([a0, b0, b1])
                all_faces.append([a0, b1, a1])

        faces = np.array(all_faces, dtype=np.int32)

        # Compute outward unit face normals
        v0 = verts[faces[:, 0]]
        v1 = verts[faces[:, 1]]
        v2 = verts[faces[:, 2]]
        cross = np.cross(v1 - v0, v2 - v0)
        norms = np.linalg.norm(cross, axis=1, keepdims=True)
        norms[norms < 1e-9] = 1.0
        face_normals = cross / norms

        return verts, faces, face_normals

    def _compute_deviation(self, base_verts: np.ndarray,
                           base_faces: np.ndarray,
                           base_normals: np.ndarray) -> ResidualMap:
        """
        Computes signed displacement from OBJ vertices to base mesh surface.
        Uses KDTree on face centroids with vectorized candidate projection.
        """
        obj_verts_mm = self.mesh.vertices * 100.0

        if len(base_faces) == 0:
            rmap = ResidualMap(threshold_mm=self.threshold_mm)
            for pos_mm in obj_verts_mm:
                rmap.vertices.append(ResidualVertex(
                    pos_mm=pos_mm,
                    displacement_mm=0.0,
                    normal_disp_mm=0.0,
                    body_normal=np.array([0.0, 1.0, 0.0])
                ))
            return rmap

        face_centroids = (base_verts[base_faces[:, 0]] +
                          base_verts[base_faces[:, 1]] +
                          base_verts[base_faces[:, 2]]) / 3.0
        tree = KDTree(face_centroids)

        k_query = min(4, len(face_centroids))
        _, face_idxs = tree.query(obj_verts_mm, k=k_query)
        if k_query == 1:
            face_idxs = face_idxs[:, np.newaxis]

        rmap = ResidualMap(threshold_mm=self.threshold_mm)

        # Fast vectorized distance to closest candidate triangle
        n_pts = len(obj_verts_mm)
        best_signed = np.zeros(n_pts, dtype=np.float64)
        best_normals = np.zeros((n_pts, 3), dtype=np.float64)
        best_dists = np.full(n_pts, np.inf, dtype=np.float64)

        for cand_col in range(k_query):
            f_col = face_idxs[:, cand_col]
            tris = base_verts[base_faces[f_col]]  # (N, 3, 3)
            fn = base_normals[f_col]              # (N, 3)

            # Project to triangle plane
            a = tris[:, 0, :]
            diff_plane = obj_verts_mm - a
            dist_normal = np.sum(diff_plane * fn, axis=1)  # signed distance to plane

            # Closest point clamped to triangle
            closest = _batch_closest_point_on_triangles(obj_verts_mm, tris)
            diff_closest = obj_verts_mm - closest
            dists = np.linalg.norm(diff_closest, axis=1)

            better_mask = dists < best_dists
            if np.any(better_mask):
                best_dists[better_mask] = dists[better_mask]
                best_signed[better_mask] = dist_normal[better_mask]
                best_normals[better_mask] = fn[better_mask]

        for i in range(n_pts):
            rmap.vertices.append(ResidualVertex(
                pos_mm=obj_verts_mm[i],
                displacement_mm=float(best_signed[i]),
                normal_disp_mm=float(best_signed[i]),
                body_normal=best_normals[i]
            ))

        return rmap

    @classmethod
    def from_json(cls, mesh: trimesh.Trimesh, json_path: Path,
                  threshold_mm: float = 0.8) -> "ResidualAnalyzer":
        data = json.loads(json_path.read_text(encoding="utf-8"))
        stations = data.get("stations", [])
        return cls(mesh, stations, threshold_mm)


class SurfaceResidualValidator:
    """
    Post-build residual validator.
    Compares reconstructed CAD surface against original input OBJ mesh.
    Computes Hausdorff distance, RMS error, and flags regions that exceed tolerance.
    """

    @staticmethod
    def validate_surfaces(
        source_mesh: trimesh.Trimesh,
        cad_geometry: Union[trimesh.Trimesh, np.ndarray],
        tolerance_mm: float = 0.8,
        source_scale: float = 100.0,
        sample_count: int = 10000
    ) -> Dict[str, Any]:
        """
        Compares source mesh vertices/surface against CAD geometry.

        Parameters
        ----------
        source_mesh : trimesh.Trimesh
            Raw input OBJ mesh.
        cad_geometry : trimesh.Trimesh or np.ndarray
            Generated CAD mesh (in mm) or point cloud sampled from CAD solid.
        tolerance_mm : float
            Allowable deviation threshold in mm (default: 0.8 mm).
        source_scale : float
            Scale factor to convert source mesh to mm (default: 100.0).
        sample_count : int
            Number of points to sample for validation.
        """
        v_source = source_mesh.vertices * source_scale
        if len(v_source) > sample_count:
            idx = np.random.choice(len(v_source), sample_count, replace=False)
            pts_source = v_source[idx]
        else:
            pts_source = v_source

        if isinstance(cad_geometry, trimesh.Trimesh):
            if len(cad_geometry.faces) > 0:
                pts_cad, _ = trimesh.sample.sample_surface(cad_geometry, sample_count)
            elif len(cad_geometry.vertices) > sample_count:
                idx_c = np.random.choice(len(cad_geometry.vertices), sample_count, replace=False)
                pts_cad = cad_geometry.vertices[idx_c]
            else:
                pts_cad = cad_geometry.vertices
        else:
            pts_cad = np.asarray(cad_geometry)

        # Forward KDTree: source OBJ points -> nearest CAD point
        tree_cad = KDTree(pts_cad)
        dists_src_to_cad, _ = tree_cad.query(pts_source, k=1)

        # Reverse KDTree: CAD points -> nearest source OBJ point
        tree_src = KDTree(pts_source)
        dists_cad_to_src, _ = tree_src.query(pts_cad, k=1)

        rms_error = float(np.sqrt(np.mean(dists_src_to_cad ** 2)))
        mean_error = float(np.mean(dists_src_to_cad))
        hausdorff = float(max(np.max(dists_src_to_cad), np.max(dists_cad_to_src)))
        in_tolerance = float(np.mean(dists_src_to_cad <= tolerance_mm) * 100.0)

        # Identify outlier points exceeding tolerance
        outlier_mask = dists_src_to_cad > tolerance_mm
        outlier_points = pts_source[outlier_mask]
        flagged_regions = []
        if len(outlier_points) > 20:
            # Cluster outliers spatially to report failed feature areas
            y_outliers = outlier_points[:, 1]
            hist, bin_edges = np.histogram(y_outliers, bins=5)
            for i in range(len(hist)):
                if hist[i] > 10:
                    flagged_regions.append({
                        "axial_range_y_mm": [round(float(bin_edges[i]), 2), round(float(bin_edges[i+1]), 2)],
                        "outlier_count": int(hist[i]),
                        "max_deviation_mm": round(float(np.max(dists_src_to_cad[outlier_mask])), 2)
                    })

        is_valid = bool(in_tolerance >= 95.0 and rms_error <= tolerance_mm)

        return {
            "is_valid": is_valid,
            "tolerance_mm": tolerance_mm,
            "in_tolerance_percentage": round(in_tolerance, 2),
            "rms_error_mm": round(rms_error, 3),
            "mean_error_mm": round(mean_error, 3),
            "hausdorff_distance_mm": round(hausdorff, 3),
            "sampled_points_count": len(pts_source),
            "outlier_count": int(np.sum(outlier_mask)),
            "flagged_regions": flagged_regions,
            "summary": (
                f"PASS: {in_tolerance:.1f}% within ±{tolerance_mm}mm (RMS: {rms_error:.2f}mm)"
                if is_valid else
                f"FAIL: Only {in_tolerance:.1f}% within ±{tolerance_mm}mm (RMS: {rms_error:.2f}mm, Max: {hausdorff:.2f}mm)"
            )
        }


# ---------------------------------------------------------------------------
# Vectorized Point-to-Triangle Helpers
# ---------------------------------------------------------------------------

def _batch_closest_point_on_triangles(pts: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """
    Vectorized closest point on triangle for N points and N triangles.
    pts: (N, 3), tris: (N, 3, 3)
    Returns: (N, 3) closest points.
    """
    a = tris[:, 0, :]
    b = tris[:, 1, :]
    c = tris[:, 2, :]

    ab = b - a
    ac = c - a
    ap = pts - a

    d1 = np.sum(ab * ap, axis=1)
    d2 = np.sum(ac * ap, axis=1)

    bp = pts - b
    d3 = np.sum(ab * bp, axis=1)
    d4 = np.sum(ac * bp, axis=1)

    cp = pts - c
    d5 = np.sum(ab * cp, axis=1)
    d6 = np.sum(ac * cp, axis=1)

    closest = np.zeros_like(pts)

    # Voronoi regions
    mask_a = (d1 <= 0.0) & (d2 <= 0.0)
    closest[mask_a] = a[mask_a]

    mask_b = (d3 >= 0.0) & (d4 <= d3)
    closest[mask_b] = b[mask_b]

    mask_c = (d6 >= 0.0) & (d5 <= d6)
    closest[mask_c] = c[mask_c]

    vc = d1 * d4 - d3 * d2
    mask_ab = (vc <= 0.0) & (d1 >= 0.0) & (d3 <= 0.0)
    denom_ab = np.maximum(d1 - d3, 1e-9)
    v_ab = np.expand_dims(d1 / denom_ab, 1)
    closest[mask_ab] = a[mask_ab] + v_ab[mask_ab] * ab[mask_ab]

    vb = d5 * d2 - d1 * d6
    mask_ac = (vb <= 0.0) & (d2 >= 0.0) & (d6 <= 0.0)
    denom_ac = np.maximum(d2 - d6, 1e-9)
    w_ac = np.expand_dims(d2 / denom_ac, 1)
    closest[mask_ac] = a[mask_ac] + w_ac[mask_ac] * ac[mask_ac]

    va = d3 * d6 - d5 * d4
    mask_bc = (va <= 0.0) & ((d4 - d3) >= 0.0) & ((d5 - d6) >= 0.0)
    denom_bc = np.maximum((d4 - d3) + (d5 - d6), 1e-9)
    w_bc = np.expand_dims((d4 - d3) / denom_bc, 1)
    closest[mask_bc] = b[mask_bc] + w_bc[mask_bc] * (c[mask_bc] - b[mask_bc])

    # Interior of face
    mask_interior = ~(mask_a | mask_b | mask_c | mask_ab | mask_ac | mask_bc)
    denom_in = np.maximum(va + vb + vc, 1e-9)
    v_in = np.expand_dims(vb / denom_in, 1)
    w_in = np.expand_dims(vc / denom_in, 1)
    closest[mask_interior] = a[mask_interior] + v_in[mask_interior] * ab[mask_interior] + w_in[mask_interior] * ac[mask_interior]

    return closest
