"""
prepare_elle18_spec.py
======================
Extracts high-fidelity CAD specification from obj/elle18-enamel-jar_reduced.obj.
Preserves native OBJ coordinates:
  X = width   ([-50.86, 50.11], span ~ 100.97 mm)
  Y = height  ([-100.00, 99.50], span ~ 199.50 mm)
  Z = depth   ([-47.25, 46.55], span ~ 93.80 mm)

Direct 1:1 cross-section slicing captures:
  - Rounded bottom transition
  - Lower body distinct curved / ring features (Y ~ -78 to -68 mm)
  - Gently tapered tall cylindrical / oblate main body
  - Upper body horizontal transition ring (Y ~ 36 to 42 mm)
  - Wide rounded shoulder near the top (Y ~ 42 to 49 mm)
  - Narrow neck transition below cap (Y ~ 49.5 to 52.5 mm, dia ~ 53.8 mm)
  - Large cylindrical cap (Y ~ 53 to 95 mm, dia ~ 59.2 mm)
  - Rounded cap top edge dome
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
        # Largest loop by bounding box area (ensures outer perimeter is picked)
        loop = max(sec.discrete, key=lambda l: (l[:, 0].max() - l[:, 0].min()) * (l[:, 2].max() - l[:, 2].min()))
        loop_2d = [(float(p[0]), float(p[2])) for p in loop]
        resampled_2d = resample_closed_polygon(loop_2d, n_samples)
        return [(round(p[0], 3), round(y_val, 3), round(p[1], 3)) for p in resampled_2d]
    except Exception as e:
        print(f"  [WARN] Slicing at Y={y_val:.2f} failed: {e}")
        return None


def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    obj_path = repo_root / "obj" / "elle18-enamel-jar_reduced.obj"
    if not obj_path.exists():
        obj_path = repo_root / "elle18-enamel-jar_reduced.obj"
    out_json = repo_root / "Elle18_parametric_spec.json"

    print("=" * 70)
    print("EXTRACTING PARAMETRIC SPECIFICATION FOR ELLE18 ENAMEL JAR")
    print(f"  OBJ Reference: {obj_path}")
    print(f"  Target Spec:   {out_json}")
    print("=" * 70)

    mesh_raw = trimesh.load(str(obj_path), process=False)
    if isinstance(mesh_raw, trimesh.Scene):
        mesh_raw = trimesh.util.concatenate(mesh_raw.dump())
    mesh_raw.apply_scale(100.0)

    # Filter out internal debris components
    comps = mesh_raw.split(only_watertight=False)
    mesh = max(comps, key=lambda c: len(c.vertices))

    print(f"  Vertices: {len(mesh.vertices):,}, Faces: {len(mesh.faces):,}")
    print(f"  Bounds: X=[{mesh.bounds[0][0]:.2f}, {mesh.bounds[1][0]:.2f}], "
          f"Y=[{mesh.bounds[0][1]:.2f}, {mesh.bounds[1][1]:.2f}], "
          f"Z=[{mesh.bounds[0][2]:.2f}, {mesh.bounds[1][2]:.2f}]")
    print(f"  Extents: W={mesh.extents[0]:.2f}, H={mesh.extents[1]:.2f}, D={mesh.extents[2]:.2f} mm")

    n_samples = 48

    # Carefully curated stations from Y=-98.0 to Y=97.5 (clean full loops)
    y_stations = [
        # --- Base & bottom rounded transition (-98.0 to -90.0) ---
        -98.0, -96.5, -94.0, -91.0, -88.0,
        # --- Lower body & distinct curved ring features (-85.0 to -64.0) ---
        -85.0, -82.0, -79.0, -76.0, -73.0, -70.0, -67.0, -64.0,
        # --- Tapered cylindrical main body (-60.0 to 20.0) ---
        -60.0, -55.0, -50.0, -45.0, -40.0, -35.0, -30.0, -25.0, -20.0, -15.0, -10.0, -5.0,
        0.0, 5.0, 10.0, 15.0, 20.0,
        # --- Upper body horizontal transition ring (24.0 to 42.0) ---
        24.0, 28.0, 32.0, 36.0, 38.5, 40.5, 42.0,
        # --- Wide rounded shoulder transition (43.5 to 49.5) ---
        43.5, 45.0, 46.5, 48.0, 49.2,
        # --- Narrow neck transition groove (50.2 to 52.4) ---
        50.2, 51.0, 51.8, 52.4,
        # --- Cylindrical cap base & body (53.0 to 95.0) ---
        53.0, 54.0, 56.0, 60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0, 93.0, 95.0,
        # --- Cap top dome rounding (96.5 to 97.5) ---
        96.5, 97.5
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
            "model_name": "Elle18_Parametric",
            "source_obj": "elle18-enamel-jar_reduced.obj",
            "coordinate_system": "Native OBJ (X=Width, Y=Height, Z=Depth)",
            "num_stations": len(all_stations_3d),
            "points_per_station": n_samples,
        },
        "expressions": {
            "BODY_WIDTH": 100.97,
            "BODY_DEPTH": 93.80,
            "BODY_HEIGHT": 145.00,
            "LOWER_RING_DIAMETER": 95.20,
            "UPPER_RING_DIAMETER": 88.00,
            "SHOULDER_HEIGHT": 8.00,
            "NECK_DIAMETER": 53.80,
            "NECK_HEIGHT": 3.00,
            "CAP_DIAMETER": 59.20,
            "CAP_HEIGHT": 46.50,
            "TOTAL_HEIGHT": 199.50,
            "BASE_BLEND_RADIUS": 2.00,
            "CAP_TOP_BLEND_RADIUS": 2.00,
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
