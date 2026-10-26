"""
prepare_glass_jar_spec.py
=========================
Extracts high-fidelity parametric CAD specification from obj/Glass jar_reduced.obj.
Preserves native OBJ coordinates:
  X = width   ([-44.15, 43.64], span ~ 87.79 mm)
  Y = height  ([-99.95, 99.44], span ~ 199.39 mm)
  Z = depth   ([-36.38, 35.80], span ~ 72.18 mm)

Direct 1:1 cross-section slicing captures:
  - Base edge curvature and bottom flat surface
  - Rounded-square body with large corner radii (R ~ 13mm)
  - Front (and back) recessed panel geometry, width, height, corner radii, and blended borders
  - Smooth shoulder transition into narrow neck
  - Distinct narrow neck transition ring (Y ~ -14 to -8 mm, dia ~ 53.8 mm)
  - Tall cylindrical cap with gentle taper and top dome rounding
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
    # Centroid
    cx = float(np.mean([p[0] for p in resampled]))
    cz = float(np.mean([p[1] for p in resampled]))
    angles = [math.atan2(p[1] - cz, p[0] - cx) for p in resampled]
    angles_pos = [(a if a >= 0 else a + 2 * math.pi) for a in angles]
    best_idx = int(min(range(len(angles_pos)), key=lambda i: angles_pos[i]))
    resampled = resampled[best_idx:] + resampled[:best_idx]
    return resampled


def extract_station(mesh, y_val: float, n_samples: int = 48) -> List[Tuple[float, float, float]] | None:
    """Slice mesh at Y=y_val, extract largest contour, resample, and return native 3D points (X, Y, Z)."""
    try:
        sec = mesh.section(plane_origin=[0, y_val, 0], plane_normal=[0, 1, 0])
        if sec is None or len(sec.discrete) == 0:
            return None
        # Largest loop by perimeter
        loop = max(sec.discrete, key=lambda l: len(l))
        # loop columns are: OBJ X (idx 0), OBJ Y (idx 1), OBJ Z (idx 2)
        loop_2d = [(float(p[0]), float(p[2])) for p in loop]
        resampled_2d = resample_closed_polygon(loop_2d, n_samples)
        # Return native 3D points (X, Y, Z)
        return [(round(p[0], 3), round(y_val, 3), round(p[1], 3)) for p in resampled_2d]
    except Exception as e:
        print(f"  [WARN] Slicing at Y={y_val:.2f} failed: {e}")
        return None


def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    obj_path = repo_root / "obj" / "Glass jar_reduced.obj"
    if not obj_path.exists():
        obj_path = repo_root / "Glass jar_reduced.obj"
    out_json = repo_root / "Glass_jar_parametric_spec.json"

    print("=" * 70)
    print("EXTRACTING PARAMETRIC SPECIFICATION FOR GLASS JAR")
    print(f"  OBJ Reference: {obj_path}")
    print(f"  Target Spec:   {out_json}")
    print("=" * 70)

    mesh = trimesh.load(str(obj_path), process=False)
    if isinstance(mesh, trimesh.Scene):
        mesh = trimesh.util.concatenate(mesh.dump())
    mesh.apply_scale(100.0)  # dm to mm

    print(f"  Vertices: {len(mesh.vertices):,}, Faces: {len(mesh.faces):,}")
    print(f"  Bounds: X=[{mesh.bounds[0][0]:.2f}, {mesh.bounds[1][0]:.2f}], "
          f"Y=[{mesh.bounds[0][1]:.2f}, {mesh.bounds[1][1]:.2f}], "
          f"Z=[{mesh.bounds[0][2]:.2f}, {mesh.bounds[1][2]:.2f}]")
    print(f"  Extents: W={mesh.extents[0]:.2f}, H={mesh.extents[1]:.2f}, D={mesh.extents[2]:.2f} mm")

    n_samples = 48

    # Complete list of stations capturing all features cleanly:
    y_stations = [
        # --- Base & rounding (-99.0 to -90.0) ---
        -99.0, -97.5, -95.0, -92.0, -88.0,
        # --- Lower body & panel transition start (-85.0 to -72.0) ---
        -85.0, -82.0, -80.0, -78.0, -76.0, -74.0, -72.0,
        # --- Main body & recessed front/back panel (-70.0 to -22.0) ---
        -70.0, -66.0, -62.0, -58.0, -54.0, -50.0, -46.0, -42.0, -38.0, -34.0, -30.0, -26.0, -23.0,
        # --- Shoulder transition zone (-21.0 to -14.0) ---
        -21.0, -19.5, -18.0, -16.5, -15.0, -14.0,
        # --- Shoulder to neck & narrow neck ring (-13.0 to -8.5) ---
        -13.0, -12.0, -11.0, -10.0, -9.2, -8.6,
        # --- Cap base step & cylindrical cap (-8.0 to +94.0) ---
        -8.0, -7.0, -5.0, 0.0, 10.0, 20.0, 35.0, 50.0, 65.0, 80.0, 90.0, 94.0,
        # --- Cap top dome & blend (+96.0 to +99.0) ---
        96.0, 97.5, 98.5, 99.0
    ]

    all_stations_3d = []
    for y in y_stations:
        st = extract_station(mesh, y, n_samples)
        if st is not None:
            all_stations_3d.append(st)
            print(f"  Station Y={y:6.1f} mm: OK ({len(st)} pts)")
        else:
            print(f"  Station Y={y:6.1f} mm: FAILED")

    spec = {
        "metadata": {
            "model_name": "Glass_jar_Parametric",
            "source_obj": "Glass jar_reduced.obj",
            "coordinate_system": "Native OBJ (X=Width, Y=Height, Z=Depth)",
            "num_stations": len(all_stations_3d),
            "points_per_station": n_samples,
        },
        "expressions": {
            "BODY_WIDTH": 87.79,
            "BODY_DEPTH": 72.18,
            "BODY_HEIGHT": 86.0,
            "BODY_CORNER_RADIUS": 13.0,
            "PANEL_WIDTH": 64.0,
            "PANEL_HEIGHT": 60.0,
            "PANEL_DEPTH": 1.65,
            "PANEL_CORNER_RADIUS": 8.0,
            "SHOULDER_HEIGHT": 14.0,
            "NECK_DIAMETER": 53.8,
            "NECK_HEIGHT": 4.0,
            "CAP_DIAMETER_BASE": 58.2,
            "CAP_DIAMETER_TOP": 55.0,
            "CAP_HEIGHT": 107.4,
            "TOTAL_HEIGHT": 199.39,
            "BASE_BLEND_RADIUS": 4.0,
            "CAP_TOP_BLEND_RADIUS": 2.5,
        },
        "stations": all_stations_3d,
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print("=" * 70)
    print(f"[SUCCESS] Saved {len(all_stations_3d)} stations to {out_json}")
    print(f"  JSON size: {out_json.stat().st_size:,} bytes")
    print("=" * 70)


if __name__ == "__main__":
    main()
