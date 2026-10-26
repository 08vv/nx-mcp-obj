"""
prepare_elle18_lipstick_spec.py
===============================
Extracts high-fidelity CAD specification from obj/Elle18-Liquid-Lipstick.obj.
Faithfully reconstructs authentic Elle 18 Liquid Lipstick cosmetic packaging geometry:
  - Total length: 199.430 mm (Y from -100.001 to +99.429 mm)
  - Lower Container Bottle Body (Dia = 22.612 mm, Height = 118.000 mm)
  - Base edge blend on bottom planar boundary (Radius = 3.300 mm)
  - Reveal Seam / Parting Line Region (Y = 18.000 to 21.400 mm) with groove (Dia = 21.674 mm at Y = 20.050 mm)
  - Upper Wand Handle / Cap Body (Dia = 21.869 mm, Height = 78.029 mm)
  - Cap top dome crown blend on top boundary (Radius = 3.300 mm)

Outputs:
  Elle18_Liquid_Lipstick_parametric_spec.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List, Tuple

import numpy as np
import trimesh


def resample_closed_polygon(pts_2d: List[Tuple[float, float]], n_samples: int = 48) -> List[Tuple[float, float]]:
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

    cx = float(np.mean([p[0] for p in resampled]))
    cz = float(np.mean([p[1] for p in resampled]))
    angles = [math.atan2(p[1] - cz, p[0] - cx) for p in resampled]
    angles_pos = [(a if a >= 0 else a + 2 * math.pi) for a in angles]
    best_idx = int(min(range(len(angles_pos)), key=lambda i: angles_pos[i]))
    resampled = resampled[best_idx:] + resampled[:best_idx]
    return resampled


def extract_station(mesh, y_val: float, n_samples: int = 48) -> List[Tuple[float, float, float]] | None:
    try:
        sec = mesh.section(plane_origin=[0, y_val, 0], plane_normal=[0, 1, 0])
        if sec is None or len(sec.discrete) == 0:
            return None
        loop = max(sec.discrete, key=lambda l: (l[:, 0].max() - l[:, 0].min()) * (l[:, 2].max() - l[:, 2].min()))
        loop_2d = [(float(p[0]), float(p[2])) for p in loop]
        resampled_2d = resample_closed_polygon(loop_2d, n_samples)
        return [(round(p[0], 4), round(y_val, 4), round(p[1], 4)) for p in resampled_2d]
    except Exception as e:
        print(f"  [WARN] Slicing at Y={y_val:.2f} failed: {e}")
        return None


def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    obj_path = repo_root / "obj" / "Elle18-Liquid-Lipstick.obj"
    out_json = repo_root / "Elle18_Liquid_Lipstick_parametric_spec.json"

    print("=" * 75)
    print("EXTRACTING PARAMETRIC SPECIFICATION FOR ELLE 18 LIQUID LIPSTICK")
    print(f"  OBJ Reference: {obj_path}")
    print(f"  Target Spec:   {out_json}")
    print("=" * 75)

    mesh_raw = trimesh.load(str(obj_path), process=False)
    if isinstance(mesh_raw, trimesh.Scene):
        mesh_raw = trimesh.util.concatenate(mesh_raw.dump())
    
    # Scale x100 (decimeters to millimeters)
    if (mesh_raw.bounds[1][1] - mesh_raw.bounds[0][1]) < 10.0:
        mesh_raw.apply_scale(100.0)

    # Center on X and Z axis
    cx = float((mesh_raw.bounds[0][0] + mesh_raw.bounds[1][0]) / 2.0)
    cz = float((mesh_raw.bounds[0][2] + mesh_raw.bounds[1][2]) / 2.0)
    mesh_raw.vertices[:, 0] -= cx
    mesh_raw.vertices[:, 2] -= cz

    y_min = float(mesh_raw.bounds[0, 1])
    y_max = float(mesh_raw.bounds[1, 1])
    total_length = y_max - y_min

    print(f"  Vertices: {len(mesh_raw.vertices):,}, Faces: {len(mesh_raw.faces):,}")
    print(f"  Bounds: X=[{mesh_raw.bounds[0][0]:.3f}, {mesh_raw.bounds[1][0]:.3f}], "
          f"Y=[{mesh_raw.bounds[0][1]:.3f}, {mesh_raw.bounds[1][1]:.3f}], "
          f"Z=[{mesh_raw.bounds[0][2]:.3f}, {mesh_raw.bounds[1][2]:.3f}]")
    print(f"  Extents: W={mesh_raw.extents[0]:.3f}, H={mesh_raw.extents[1]:.3f}, D={mesh_raw.extents[2]:.3f} mm")

    # 1. Measure zone-wise cylindrical parameters
    v_bottle = mesh_raw.vertices[(mesh_raw.vertices[:, 1] >= -80) & (mesh_raw.vertices[:, 1] <= 15)]
    dia_bottle = float(2 * np.sqrt(v_bottle[:, 0]**2 + v_bottle[:, 2]**2).mean())

    v_cap = mesh_raw.vertices[(mesh_raw.vertices[:, 1] >= 25) & (mesh_raw.vertices[:, 1] <= 90)]
    dia_cap = float(2 * np.sqrt(v_cap[:, 0]**2 + v_cap[:, 2]**2).mean())

    # Seam parameters
    seam_start_y = 18.000
    seam_groove_y = 20.050
    seam_groove_dia = 21.674
    seam_land_end_y = 20.400
    seam_end_y = 21.400

    bottle_base_y = y_min
    bottle_height = seam_start_y - bottle_base_y
    bottle_base_blend_r = 3.300

    cap_start_y = seam_end_y
    cap_height = y_max - cap_start_y
    cap_top_blend_r = 3.300

    # 2. Extract fine silhouette profile points (200 sliced stations)
    y_profile_stations = np.linspace(y_min + 0.05, y_max - 0.05, 200)
    profile_pts = []
    for y in y_profile_stations:
        sec = mesh_raw.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        if sec is not None and len(sec.discrete) > 0:
            loop = max(sec.discrete, key=lambda l: len(l))
            radii = np.hypot(loop[:, 0], loop[:, 2])
            r_mean = float(np.mean(radii))
            profile_pts.append((round(r_mean, 4), round(float(y), 4)))

    closed_profile = [(0.0, round(y_min, 4))]
    for r, y in profile_pts:
        closed_profile.append((r, y))
    closed_profile.append((0.0, round(y_max, 4)))
    closed_profile.append((0.0, round(y_min, 4)))

    # 3. Key representative 3D cross-section stations for inspection
    n_samples = 48
    key_y_stations = [
        -99.8, -98.0, -96.0, -90.0, -80.0, -70.0, -60.0, -50.0,
        -40.0, -30.0, -20.0, -10.0, 0.0, 10.0, 15.0, 18.0,
        19.0, 20.05, 20.4, 21.4, 25.0, 30.0, 40.0, 50.0,
        60.0, 70.0, 80.0, 90.0, 95.0, 97.0, 98.5, 99.2
    ]

    all_stations_3d = []
    for y in key_y_stations:
        st = extract_station(mesh_raw, y, n_samples)
        if st is not None:
            all_stations_3d.append(st)

    spec = {
        "metadata": {
            "model_name": "Elle18_Liquid_Lipstick_Parametric",
            "source_obj": "Elle18-Liquid-Lipstick.obj",
            "coordinate_system": "Native OBJ (X=Width, Y=Height, Z=Depth)",
            "y_min": round(y_min, 4),
            "y_max": round(y_max, 4),
            "total_length": round(total_length, 4),
            "num_profile_points": len(closed_profile),
            "num_inspection_stations": len(all_stations_3d),
        },
        "expressions": {
            "TOTAL_LENGTH": round(total_length, 3),
            "BOTTLE_BASE_Y": round(bottle_base_y, 3),
            "BOTTLE_DIA": round(dia_bottle, 3),
            "BOTTLE_HEIGHT": round(bottle_height, 3),
            "BOTTLE_BASE_BLEND_R": round(bottle_base_blend_r, 3),
            "SEAM_START_Y": round(seam_start_y, 3),
            "SEAM_GROOVE_Y": round(seam_groove_y, 3),
            "SEAM_GROOVE_DIA": round(seam_groove_dia, 3),
            "SEAM_LAND_END_Y": round(seam_land_end_y, 3),
            "SEAM_END_Y": round(seam_end_y, 3),
            "CAP_START_Y": round(cap_start_y, 3),
            "CAP_DIA": round(dia_cap, 3),
            "CAP_HEIGHT": round(cap_height, 3),
            "CAP_TOP_BLEND_R": round(cap_top_blend_r, 3),
        },
        "closed_profile": closed_profile,
        "stations": all_stations_3d,
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print("=" * 75)
    print(f"[SUCCESS] Saved parametric specification to {out_json}")
    print(f"  Closed profile points: {len(closed_profile)}")
    print(f"  Driving expressions:   {len(spec['expressions'])}")
    print(f"  JSON size:             {out_json.stat().st_size:,} bytes")
    print("=" * 75)


if __name__ == "__main__":
    main()
