"""
pca_align.py
============
Layer A: PCA (Principal Component Analysis) axis alignment module.
Detects principal rotational axis and transforms mesh to NX modeling CSYS.
"""

import numpy as np
import trimesh


class PCAMeshAligner:
    def __init__(self, mesh: trimesh.Trimesh):
        self.mesh = mesh
        self.aligned_mesh = None
        self.transform_matrix = np.eye(4)

    def align(self, target_axis: str = 'Y') -> tuple[trimesh.Trimesh, np.ndarray]:
        """Aligns principal axis of the mesh to target coordinate axis (default: Y height axis)."""
        verts = self.mesh.vertices.copy()
        centroid = verts.mean(axis=0)
        centered_verts = verts - centroid

        # Compute covariance matrix & eigenvectors
        cov = np.cov(centered_verts, rowvar=False)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)

        # Sort eigenvectors by variance (descending)
        sort_idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[sort_idx]
        eigenvectors = eigenvectors[:, sort_idx]

        e0, e1, e2 = eigenvalues[0], eigenvalues[1], eigenvalues[2]

        # Check rotational symmetry ratio
        ratio = e1 / max(e0, 1e-9)
        is_axisymmetric = bool(ratio > 0.85 and e2 > 3.0 * e1)

        self.is_axisymmetric = is_axisymmetric

        # Smart Aspect-Ratio Axis Classifier:
        # If e1 / e0 > 0.80 and e2 / e1 < 0.55 (two nearly equal large footprint dimensions e0, e1 and one short height dimension e2):
        # then object is a squat / compact powder case, circular tub, or shallow square enclosure.
        # Its height axis is the smallest variance eigenvector (e2).
        # Otherwise (tall bodies, long shafts, jars, bottles), height axis is max variance eigenvector (e0).
        if (e1 / max(e0, 1e-9) > 0.80) and (e2 / max(e1, 1e-9) < 0.55):
            v_height = eigenvectors[:, 2]
            v_rad1 = eigenvectors[:, 0]
            v_rad2 = eigenvectors[:, 1]
        else:
            v_height = eigenvectors[:, 0]
            v_rad1 = eigenvectors[:, 1]
            v_rad2 = eigenvectors[:, 2]

        # Ensure consistent sign with original coordinate system (+Y remains +Y if aligned)
        if v_height[1] < 0:
            v_height = -v_height
            v_rad1 = -v_rad1

        R = np.column_stack([v_rad1, v_height, v_rad2])
        if np.linalg.det(R) < 0:
            R[:, 2] = -R[:, 2]

        T = np.eye(4)
        T[:3, :3] = R.T
        T[:3, 3] = -R.T @ centroid

        aligned = self.mesh.copy()
        aligned.apply_transform(T)

        self.aligned_mesh = aligned
        self.transform_matrix = T

        return aligned, T

    def get_alignment_info(self) -> dict:
        if self.aligned_mesh is None:
            self.align()
        bounds = self.aligned_mesh.bounds
        dims = bounds[1] - bounds[0]
        return {
            "is_axisymmetric": getattr(self, "is_axisymmetric", False),
            "aligned_height_y": float(dims[1]),
            "aligned_radius_max": float(max(dims[0], dims[2]) / 2.0),
            "transform_matrix": self.transform_matrix.tolist(),
        }


def align_to_principal_axes(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Convenience helper to align a mesh to principal axes and return aligned mesh."""
    aligner = PCAMeshAligner(mesh)
    aligned, _ = aligner.align()
    return aligned


def get_canonical_rotation(axis_name: str) -> np.ndarray:
    """Returns 3x3 rotation matrix mapping axis_name ('X', 'Y', 'Z') to +Y."""
    if axis_name.upper() == "Y":
        return np.eye(3)
    elif axis_name.upper() == "X":
        # Map X -> Y: rotation around Z by +90 deg
        return np.array([
            [0.0, -1.0, 0.0],
            [1.0,  0.0, 0.0],
            [0.0,  0.0, 1.0]
        ])
    elif axis_name.upper() == "Z":
        # Map Z -> Y: rotation around X by -90 deg
        return np.array([
            [1.0,  0.0,  0.0],
            [0.0,  0.0,  1.0],
            [0.0, -1.0,  0.0]
        ])
    return np.eye(3)


