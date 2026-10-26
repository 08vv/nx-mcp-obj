"""
prepare_ellie_18_spec.py
========================
Extracts high-fidelity CAD specification from obj/Ellie_18_eye_liner.obj.
Faithfully reconstructs the authentic cosmetic eyeliner geometry:
  - Extremely long and slender overall proportions (Length ~ 199.47 mm, Dia ~ 14.23 mm)
  - Narrow cylindrical main body with subtle gradual flare/taper
  - Distinct enlarged transition/collar region near the middle (Dia ~ 14.23 mm at Y ~ 15 mm)
  - Multiple smooth curved ring transitions around the collar:
      * Step down to intermediate land (Dia ~ 12.41 mm at Y ~ 22.3 mm)
      * Annular groove (Dia ~ 11.48 mm at Y ~ 26.8 mm)
      * Raised accent ring ridge (Dia ~ 11.92 mm at Y ~ 29.5 mm)
  - Gradual smooth taper from collar into long upper section (Dia 10.58 -> 8.78 mm)
  - Slender upper wand section with subtle swell (Dia ~ 8.78 mm to 8.85 mm)
  - Tapered tip curving smoothly down to rounded dome apex
  - Smooth rounded bottom end

Outputs Ellie_18_eye_liner_parametric_spec.json.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List, Tuple

import numpy as np
import trimesh


def resample_closed_polygon(pts_2d: List[Tuple[float, float]], n_samples: int = 48) -> List[Tuple[float, float]]:
    """Uniformly resample a closed 2D polygon (X, Z) by arc-length with CCW winding and consistent start."""
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

    # Align starting point: closest to positive X axis (+X, Z ~ 0)
    cx = float(np.mean([p[0] for p in resampled]))
    cz = float(np.mean([p[1] for p in resampled]))
    angles = [math.atan2(p[1] - cz, p[0] - cx) for p in resampled]
    angles_pos = [(a if a >= 0 else a + 2 * math.pi) for a in angles]
    best_idx = int(min(range(len(angles_pos)), key=lambda i: angles_pos[i]))
    resampled = resampled[best_idx:] + resampled[:best_idx]
    return resampled


def extract_station(mesh, y_val: float, n_samples: int = 48) -> List[Tuple[float, float, float]] | None:
    """Slice mesh at Y=y_val, extract largest contour by bbox area, resample, and return native 3D points (X, Y, Z)."""
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
    obj_path = repo_root / "obj" / "Ellie_18_eye_liner.obj"
    out_json = repo_root / "Ellie_18_eye_liner_parametric_spec.json"

    print("=" * 75)
    print("EXTRACTING PARAMETRIC SPECIFICATION FOR ELLIE 18 EYELINER")
    print(f"  OBJ Reference: {obj_path}")
    print(f"  Target Spec:   {out_json}")
    print("=" * 75)

    mesh_raw = trimesh.load(str(obj_path), process=False)
    if isinstance(mesh_raw, trimesh.Scene):
        mesh_raw = trimesh.util.concatenate(mesh_raw.dump())
    
    # Scale x100 (decimeters to millimeters)
    mesh_raw.apply_scale(100.0)

    # Filter out single-vertex debris
    comps = mesh_raw.split(only_watertight=False)
    mesh = max(comps, key=lambda c: len(c.faces))

    # Center on X and Z axis for concentric revolution
    cx = float(np.mean(mesh.vertices[:, 0]))
    cz = float(np.mean(mesh.vertices[:, 2]))
    mesh.vertices[:, 0] -= cx
    mesh.vertices[:, 2] -= cz

    y_min = float(mesh.bounds[0, 1])
    y_max = float(mesh.bounds[1, 1])
    total_length = y_max - y_min

    print(f"  Vertices: {len(mesh.vertices):,}, Faces: {len(mesh.faces):,}")
    print(f"  Bounds: X=[{mesh.bounds[0][0]:.3f}, {mesh.bounds[1][0]:.3f}], "
          f"Y=[{mesh.bounds[0][1]:.3f}, {mesh.bounds[1][1]:.3f}], "
          f"Z=[{mesh.bounds[0][2]:.3f}, {mesh.bounds[1][2]:.3f}]")
    print(f"  Extents: W={mesh.extents[0]:.3f}, H={mesh.extents[1]:.3f}, D={mesh.extents[2]:.3f} mm")

    # 1. Extract fine silhouette profile points (180 sliced stations)
    y_profile_stations = np.linspace(y_min + 0.02, y_max - 0.02, 180)
    profile_pts = []
    for y in y_profile_stations:
        sec = mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        if sec is not None and len(sec.discrete) > 0:
            loop = max(sec.discrete, key=lambda l: len(l))
            radii = np.hypot(loop[:, 0], loop[:, 2])
            r_mean = float(np.mean(radii))
            profile_pts.append((round(r_mean, 4), round(float(y), 4)))

    # Closed profile curve points for 360-deg revolution
    # Start at bottom center (0, y_min), flat bottom to (r0, y_min), through all profile points, to apex (0, y_max)
    closed_profile = [(0.0, round(y_min, 4))]
    for r, y in profile_pts:
        closed_profile.append((r, y))
    closed_profile.append((0.0, round(y_max, 4)))
    closed_profile.append((0.0, round(y_min, 4)))

    # 2. Key representative 3D cross-section stations for inspection
    n_samples = 48
    key_y_stations = [
        -99.8, -99.0, -97.0, -90.0, -80.0, -70.0, -60.0, -50.0,
        -40.0, -30.0, -20.0, -10.0, 0.0, 10.0, 15.08, 17.5,
        20.5, 22.3, 25.0, 26.82, 28.5, 29.5, 32.0, 35.0,
        40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0,
        80.0, 85.0, 88.0, 91.0, 94.0, 97.0, 99.0
    ]

    all_stations_3d = []
    for y in key_y_stations:
        st = extract_station(mesh, y, n_samples)
        if st is not None:
            all_stations_3d.append(st)

    spec = {
        "metadata": {
            "model_name": "Ellie_18_eye_liner_Parametric",
            "source_obj": "Ellie_18_eye_liner.obj",
            "coordinate_system": "Native OBJ (X=Width, Y=Height, Z=Depth)",
            "y_min": round(y_min, 4),
            "y_max": round(y_max, 4),
            "total_length": round(total_length, 4),
            "num_profile_points": len(closed_profile),
            "num_inspection_stations": len(all_stations_3d),
        },
        "expressions": {
            "TOTAL_LENGTH": round(total_length, 3),
            "BASE_BLEND_RADIUS": 1.800,
            "BARREL_BASE_DIAMETER": 13.800,
            "BARREL_MID_DIAMETER": 13.900,
            "BARREL_TOP_DIAMETER": 14.220,
            "BARREL_LENGTH": round(15.080 - y_min, 3),
            "COLLAR_MAX_DIAMETER": 14.230,
            "COLLAR_START_HEIGHT": 15.080,
            "COLLAR_STEP_DIAMETER": 12.410,
            "COLLAR_STEP_HEIGHT": 22.300,
            "ANNULAR_GROOVE_DIAMETER": 11.480,
            "ANNULAR_GROOVE_HEIGHT": 26.820,
            "ACCENT_RIDGE_DIAMETER": 11.920,
            "ACCENT_RIDGE_HEIGHT": 28.500,
            "COLLAR_END_DIAMETER": 10.580,
            "COLLAR_LENGTH": 19.920,
            "WAND_TRANS_LENGTH": 23.500,
            "WAND_TRANS_MID_DIAM": 9.480,
            "WAND_STEM_DIAMETER": 8.780,
            "WAND_SWELL_DIAMETER": 8.850,
            "WAND_SWELL_HEIGHT": 80.000,
            "WAND_STEM_LENGTH": 26.500,
            "TIP_START_HEIGHT": 85.000,
            "TIP_MID_DIAMETER": 6.020,
            "TIP_LENGTH": round(y_max - 85.000, 3),
            "TIP_APEX_RADIUS": 0.500,
            "TIP_BLEND_RADIUS": 0.800,
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
