"""
generate_vaseline_strict_spec.py
================================
Extracts high-fidelity cross-section stations along the functional zones of the
Vaseline 5 squeeze tube (obj/Vaseline5_reduced.obj) into a structured JSON specification.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import trimesh


def resample_polygon_aligned(pts_2d: List[Tuple[float, float]], n_samples: int = 128) -> List[Tuple[float, float]]:
    pts = list(pts_2d)
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 1e-4:
        pts.append(pts[0])

    dists = [0.0]
    for i in range(len(pts) - 1):
        seg = math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
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
        area += (p0[0] * p1[1] - p0[1] * p1[0])
    if area < 0:
        resampled = resampled[::-1]

    # Align start point to the back minimum-Z point (lowest Z, closest to X=0)
    best_idx = int(min(range(len(resampled)), key=lambda i: resampled[i][1] + 0.1 * abs(resampled[i][0])))
    resampled = resampled[best_idx:] + resampled[:best_idx]
    return resampled


def extract_station(mesh: trimesh.Trimesh, y_val: float, n_samples: int = 128) -> Optional[List[Tuple[float, float, float]]]:
    try:
        sec = mesh.section(plane_origin=[0, y_val, 0], plane_normal=[0, 1, 0])
        if sec is None or len(sec.discrete) == 0:
            return None
        loop = max(
            sec.discrete,
            key=lambda l: (l[:, 0].max() - l[:, 0].min()) * (l[:, 2].max() - l[:, 2].min()),
        )
        loop_2d = [(float(p[0]), float(p[2])) for p in loop]
        resampled_2d = resample_polygon_aligned(loop_2d, n_samples)
        return [(round(p[0], 4), round(y_val, 4), round(p[1], 4)) for p in resampled_2d]
    except Exception as e:
        print(f"  [WARN] Slicing at Y={y_val:.2f} failed: {e}")
        return None


def main():
    repo_root = Path(__file__).resolve().parent.parent
    obj_path = repo_root / "obj" / "Vaseline5_reduced.obj"
    print(f"Loading OBJ: {obj_path}")

    mesh_raw = trimesh.load(str(obj_path), process=False)
    # Check scale: extents are ~0.76 x 1.99 x 0.28 dm -> scale by 100 to mm
    if (mesh_raw.bounds[1][1] - mesh_raw.bounds[0][1]) < 10.0:
        mesh_raw.apply_scale(100.0)

    comps = mesh_raw.split(only_watertight=False)
    mesh = max(comps, key=lambda c: len(c.faces))

    # Center in X and Z
    cx = float((mesh.bounds[0][0] + mesh.bounds[1][0]) / 2.0)
    cz = float((mesh.bounds[0][2] + mesh.bounds[1][2]) / 2.0)
    mesh.vertices[:, 0] -= cx
    mesh.vertices[:, 2] -= cz

    y_min = float(mesh.bounds[0, 1])
    y_max = float(mesh.bounds[1, 1])
    print(
        f"Mesh bounds: X=[{mesh.bounds[0][0]:.2f}, {mesh.bounds[1][0]:.2f}], "
        f"Y=[{y_min:.2f}, {y_max:.2f}], "
        f"Z=[{mesh.bounds[0][2]:.2f}, {mesh.bounds[1][2]:.2f}]"
    )

    n_samples = 128
    zones = {
        "cap_base":         {"y_start": y_min + 0.15, "y_end": -75.40,      "count": 20},
        "shoulder_step":    {"y_start": -75.40,       "y_end": -70.00,      "count": 10},
        "lower_tube_body":  {"y_start": -70.00,       "y_end":  10.00,      "count": 30},
        "upper_tube_body":  {"y_start":  10.00,       "y_end":  87.00,      "count": 30},
        "crimp_transition": {"y_start":  87.00,       "y_end":  90.50,      "count": 10},
        "crimp_seal":       {"y_start":  90.50,       "y_end": y_max - 0.15,"count": 20},
    }

    all_stations: Dict[str, Any] = {}
    for zone_name, cfg in zones.items():
        ys = np.linspace(cfg["y_start"], cfg["y_end"], cfg["count"])
        stations = []
        for y in ys:
            st = extract_station(mesh, float(y), n_samples)
            if st is not None:
                stations.append(st)
        all_stations[zone_name] = stations
        print(f"Zone {zone_name:18s}: {len(stations)} stations ({cfg['y_start']:6.2f} to {cfg['y_end']:6.2f} mm)")

    out_json = repo_root / "Vaseline5_strict_spec.json"
    spec = {
        "model_name": "Vaseline5_Parametric_Strict",
        "source_obj": str(obj_path),
        "bounds_mm": {
            "min": [float(mesh.bounds[0][0]), float(y_min), float(mesh.bounds[0][2])],
            "max": [float(mesh.bounds[1][0]), float(y_max), float(mesh.bounds[1][2])],
            "extents": [
                float(mesh.bounds[1][0] - mesh.bounds[0][0]),
                float(y_max - y_min),
                float(mesh.bounds[1][2] - mesh.bounds[0][2]),
            ],
        },
        "n_samples": n_samples,
        "zones": all_stations,
        "expressions": {
            "BASE_BLEND_R": 1.800,
        },
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print(f"Saved specification to: {out_json} ({out_json.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
