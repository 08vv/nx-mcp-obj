"""
parser.py
=========
Layer A: OBJ parser and mesh repair module using trimesh.
Performs vertex welding, normal fixing, and basic mesh cleanup.
"""

from pathlib import Path
import trimesh
import numpy as np


class MeshIngestionEngine:
    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path).resolve()
        if not self.file_path.exists():
            raise FileNotFoundError(f"OBJ file not found: {self.file_path}")
        try:
            self.raw_mesh = trimesh.load(str(self.file_path), force='mesh')
        except (MemoryError, Exception):
            # Memory-efficient streaming fallback loader for large OBJ meshes (>1M faces / low RAM)
            self.raw_mesh = self._load_obj_streaming(self.file_path)
        self.repaired_mesh = None

    @staticmethod
    def _load_obj_streaming(file_path: Path) -> trimesh.Trimesh:
        import gc
        gc.collect()
        v_list = []
        f_list = []
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("v "):
                    p = line.split()
                    if len(p) >= 4:
                        v_list.append((float(p[1]), float(p[2]), float(p[3])))
                elif line.startswith("f "):
                    p = line.split()
                    if len(p) >= 4:
                        f_list.append((int(p[1].split("/")[0]) - 1, int(p[2].split("/")[0]) - 1, int(p[3].split("/")[0]) - 1))
        
        v_arr = np.array(v_list, dtype=np.float32)
        f_arr = np.array(f_list, dtype=np.int32)
        del v_list
        del f_list
        gc.collect()
        return trimesh.Trimesh(vertices=v_arr, faces=f_arr, process=False)

    def repair(self) -> trimesh.Trimesh:
        """Performs mesh repair: duplicate vertex welding, normal fixing, hole filling."""
        mesh = self.raw_mesh.copy()
        
        # Merge duplicate vertices
        mesh.merge_vertices()
        
        # Fix normals
        mesh.fix_normals()
        
        # Fill small holes if possible
        try:
            mesh.fill_holes()
        except Exception:
            pass

        self.repaired_mesh = mesh
        return mesh

    def get_mesh_info(self) -> dict:
        mesh = self.repaired_mesh or self.raw_mesh
        bounds = mesh.bounds
        dims = bounds[1] - bounds[0]
        return {
            "file_path": str(self.file_path),
            "vertex_count": len(mesh.vertices),
            "face_count": len(mesh.faces),
            "is_watertight": bool(mesh.is_watertight),
            "bounds_min": bounds[0].tolist(),
            "bounds_max": bounds[1].tolist(),
            "dimensions": dims.tolist(),
        }
