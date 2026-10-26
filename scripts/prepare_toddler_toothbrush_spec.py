"""
prepare_toddler_toothbrush_spec.py
===================================
Extracts high-fidelity CAD specification from obj/Todddler_toothbrush.obj
with strict geometric fidelity to the original mesh:
  - Total length: 199.33 mm (Y from -99.94 to +99.40 mm)
  - Lower handle dome & smoothly tapered main handle with front grip details (Y=-99.4 to -8.0)
  - Enlarged character head with raised facial features & wide curved brim/collar (Y=-8.0 to 26.5)
  - Cylindrical transition neck (Y=26.5 to 36.5)
  - Slim elongated upper shaft/stem (Y=36.5 to 74.0)
  - Detailed brush head with backing pad and multi-row raised bristles (Y=74.0 to 98.9)

Resampling:
  - 96 points per station loop for high resolution
  - Aligned to consistent back-spine minimum-Z reference point (X=0, min Z)
  - Continuous CCW winding in (X, Z) plane

Outputs:
  Toddler_Toothbrush_parametric_spec.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List, Tuple

import numpy as np
import trimesh


def resample_polygon_aligned(pts_2d: List[Tuple[float, float]], n_samples: int = 96) -> List[Tuple[float, float]]:
    pts = list(pts_2d)
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 1e-4:
        pts.append(pts[0])

    dists = [0.0]
    for i in range(len(pts) - 1):
        seg = math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1])
        dists.append(dists[-1] + seg)
    total_len = dists[-1]
    if total_len < 1e-4:
        return [(0.0, 0.0)] * n_samples

    target_dists = [float(k) * total_len / float(n_samples) for k in range(n_samples)]
    resampled = []
    seg_idx = 0
    for td in target_dists:
        while seg_idx < len(dists) - 2 and dists[seg_idx + 1] < td:
            seg_idx += 1
        d0, d1 = dists[seg_idx], dists[seg_idx + 1]
        p0, p1 = pts[seg_idx], pts[seg_idx + 1]
        t = (td - d0) / (d1 - d0) if (d1 - d0) > 1e-9 else 0.0
        rx = p0[0] + t * (p1[0] - p0[0])
        rz = p0[1] + t * (p1[1] - p0[1])
        resampled.append((rx, rz))

    # Ensure CCW winding in (X, Z) plane
    area = 0.0
    for i in range(len(resampled)):
        p0 = resampled[i]
        p1 = resampled[(i + 1) % len(resampled)]
        area += (p0[0] * p1[1] - p1[0] * p0[1])
    if area < 0:
        resampled = resampled[::-1]

    # Align start point to the back minimum-Z point (lowest Z, closest to X=0)
    best_idx = int(min(range(len(resampled)), key=lambda i: resampled[i][1] + 0.1 * abs(resampled[i][0])))
    resampled = resampled[best_idx:] + resampled[:best_idx]
    return resampled


def extract_station(mesh, y_val: float, n_samples: int = 96) -> List[Tuple[float, float, float]] | None:
    try:
        sec = mesh.section(plane_origin=[0, y_val, 0], plane_normal=[0, 1, 0])
        if sec is None or len(sec.discrete) == 0:
            return None
        loop = max(sec.discrete, key=lambda l: (l[:, 0].max() - l[:, 0].min()) * (l[:, 2].max() - l[:, 2].min()))
        loop_2d = [(float(p[0]), float(p[2])) for p in loop]
        resampled_2d = resample_polygon_aligned(loop_2d, n_samples)
        return [(round(p[0], 4), round(y_val, 4), round(p[1], 4)) for p in resampled_2d]
    except Exception as e:
        print(f"  [WARN] Slicing at Y={y_val:.2f} failed: {e}")
        return None


def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    obj_path = repo_root / "obj" / "Todddler_toothbrush.obj"
    out_json = repo_root / "Toddler_Toothbrush_parametric_spec.json"

    print("=" * 75)
    print("EXTRACTING HIGH-FIDELITY SPECIFICATION FOR TODDLER TOOTHBRUSH")
    print(f"  OBJ Source: {obj_path}")
    print(f"  Target Spec: {out_json}")
    print("=" * 75)

    mesh_raw = trimesh.load(str(obj_path), process=False)
    if isinstance(mesh_raw, trimesh.Scene):
        mesh_raw = trimesh.util.concatenate(mesh_raw.dump())

    # Scale x100 (decimeters to millimeters)
    if (mesh_raw.bounds[1][1] - mesh_raw.bounds[0][1]) < 10.0:
        mesh_raw.apply_scale(100.0)

    # Extract main body
    comps = mesh_raw.split(only_watertight=False)
    mesh = max(comps, key=lambda c: len(c.faces))

    # Center in X and Z
    cx = float((mesh.bounds[0][0] + mesh.bounds[1][0]) / 2.0)
    cz = float((mesh.bounds[0][2] + mesh.bounds[1][2]) / 2.0)
    mesh.vertices[:, 0] -= cx
    mesh.vertices[:, 2] -= cz

    y_min = float(mesh.bounds[0, 1])
    y_max = float(mesh.bounds[1, 1])
    total_length = y_max - y_min

    print(f"  Mesh bounds: X=[{mesh.bounds[0][0]:.2f}, {mesh.bounds[1][0]:.2f}], "
          f"Y=[{mesh.bounds[0][1]:.2f}, {mesh.bounds[1][1]:.2f}], "
          f"Z=[{mesh.bounds[0][2]:.2f}, {mesh.bounds[1][2]:.2f}]")
    print(f"  Total length: {total_length:.3f} mm")

    n_samples = 96
    zones = {
        "handle_body":        {"y_start": y_min + 0.5, "y_end": -8.0,        "count": 35},
        "char_head_collar":   {"y_start": -8.0,        "y_end": 26.5,        "count": 35},
        "neck_trans":         {"y_start": 26.5,        "y_end": 36.5,        "count": 11},
        "slim_stem":          {"y_start": 36.5,        "y_end": 74.0,        "count": 20},
        "brush_head_bristles":{"y_start": 74.0,        "y_end": y_max - 0.5, "count": 35},
    }

    all_stations = {}
    for zone_name, cfg in zones.items():
        ys = np.linspace(cfg["y_start"], cfg["y_end"], cfg["count"])
        stations = []
        for y in ys:
            st = extract_station(mesh, float(y), n_samples)
            if st is not None:
                stations.append(st)
            else:
                print(f"  [WARN] Zone {zone_name}: Y={y:6.1f} failed")
        all_stations[zone_name] = stations
        print(f"  Zone {zone_name:20s}: {len(stations)} stations ({cfg['y_start']:5.1f} to {cfg['y_end']:5.1f} mm)")

    total_st_count = sum(len(v) for v in all_stations.values())
    print(f"\n  Total extracted stations: {total_st_count} (each with {n_samples} points)")

    spec = {
        "metadata": {
            "model_name": "Toddler_Toothbrush_Parametric",
            "source_obj": "Todddler_toothbrush.obj",
            "coordinate_system": "Centered OBJ (X=Width, Y=Height, Z=Depth)",
            "y_min": round(y_min, 4),
            "y_max": round(y_max, 4),
            "total_length": round(total_length, 4),
            "n_samples_per_station": n_samples,
            "total_stations": total_st_count,
        },
        "expressions": {
            "TOTAL_LENGTH": round(total_length, 3),
            "HANDLE_BASE_Y": round(y_min, 3),
            "HANDLE_MAX_WIDTH": 32.800,
            "HANDLE_MAX_DEPTH": 26.800,
            "CHAR_HEAD_WIDTH": 36.300,
            "COLLAR_BRIM_WIDTH": 50.200,
            "COLLAR_BRIM_DEPTH": 38.500,
            "COLLAR_BRIM_Y": 21.000,
            "NECK_DIAMETER_X": 13.200,
            "NECK_DIAMETER_Z": 8.700,
            "STEM_WIDTH": 13.000,
            "STEM_DEPTH": 8.000,
            "BRUSH_HEAD_LENGTH": 25.000,
            "BRUSH_HEAD_WIDTH": 23.400,
            "BRUSH_HEAD_DEPTH": 19.900,
            "BRISTLE_TIP_Z": 16.100,
            "HANDLE_END_Y": -8.000,
            "HEAD_GUARD_END_Y": 26.500,
            "NECK_END_Y": 36.500,
            "STEM_END_Y": 74.000,
        },
        "zones": all_stations,
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print("=" * 75)
    print(f"[SUCCESS] High-fidelity specification saved to {out_json}")
    print(f"  Driving expressions: {len(spec['expressions'])}")
    print(f"  JSON file size: {out_json.stat().st_size:,} bytes")
    print("=" * 75)


if __name__ == "__main__":
    main()
