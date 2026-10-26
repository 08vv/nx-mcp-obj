"""
prepare_cif3_spec.py
====================
Extracts high-fidelity CAD specification from Cif3_jerry_can_reduced.obj.
Captures exact body stations without spline ringing, organic handle arch,
tangent line+arc handle cutout, offset neck & cap, and no artificial ribs.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import List, Tuple

import trimesh


def resample_closed_polygon(pts_2d: List[Tuple[float, float]], n_samples: int = 48) -> List[Tuple[float, float]]:
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
        ry = p0[1] + t * (p1[1] - p0[1])
        resampled.append((rx, ry))

    # CCW check
    area = 0.0
    for i in range(len(resampled)):
        p0 = resampled[i]
        p1 = resampled[(i + 1) % len(resampled)]
        area += (p0[0] * p1[1] - p1[0] * p0[1])
    if area < 0:
        resampled = resampled[::-1]

    # Align starting point: point closest to positive X axis
    angles = [math.atan2(p[1], p[0]) for p in resampled]
    angles_pos = [(a if a >= 0 else a + 2 * math.pi) for a in angles]
    best_idx = int(min(range(len(angles_pos)), key=lambda i: angles_pos[i]))

    resampled = resampled[best_idx:] + resampled[:best_idx]
    return resampled


def build_rounded_rectangle_station(cx: float, cy: float, cz: float,
                                     width: float, depth: float, radius: float,
                                     n_samples: int = 48) -> List[Tuple[float, float, float]]:
    hw = width / 2.0
    hd = depth / 2.0
    r = min(radius, hw * 0.9, hd * 0.9)

    pts_2d = []
    pts_2d.append((cx + hw, cy - hd + r))
    pts_2d.append((cx + hw, cy + hd - r))
    for a in range(1, 8):
        theta = float(a) * (math.pi / 2.0) / 8.0
        pts_2d.append((cx + hw - r + r * math.cos(theta), cy + hd - r + r * math.sin(theta)))
    pts_2d.append((cx + hw - r, cy + hd))
    pts_2d.append((cx - hw + r, cy + hd))
    for a in range(1, 8):
        theta = (math.pi / 2.0) + float(a) * (math.pi / 2.0) / 8.0
        pts_2d.append((cx - hw + r + r * math.cos(theta), cy + hd - r + r * math.sin(theta)))
    pts_2d.append((cx - hw, cy + hd - r))
    pts_2d.append((cx - hw, cy - hd + r))
    for a in range(1, 8):
        theta = math.pi + float(a) * (math.pi / 2.0) / 8.0
        pts_2d.append((cx - hw + r + r * math.cos(theta), cy - hd + r + r * math.sin(theta)))
    pts_2d.append((cx - hw + r, cy - hd))
    pts_2d.append((cx + hw - r, cy - hd))
    for a in range(1, 8):
        theta = 1.5 * math.pi + float(a) * (math.pi / 2.0) / 8.0
        pts_2d.append((cx + hw - r + r * math.cos(theta), cy - hd + r + r * math.sin(theta)))

    resampled = resample_closed_polygon(pts_2d, n_samples)
    return [(round(p[0], 3), round(p[1], 3), round(cz, 3)) for p in resampled]


def extract_station_at_z(mesh: trimesh.Trimesh, z: float, n_samples: int = 48) -> List[Tuple[float, float, float]]:
    y_obj = z - 100.0
    sec = mesh.section(plane_origin=[0, y_obj, 0], plane_normal=[0, 1, 0])
    if sec and len(sec.discrete) > 0:
        loop = max(sec.discrete, key=lambda l: l[:, 0].max() - l[:, 0].min())
        loop_2d = [(float(p[0]), float(p[2])) for p in loop]
        resampled = resample_closed_polygon(loop_2d, n_samples)
        return [(round(p[0], 3), round(p[1], 3), round(z, 3)) for p in resampled]
    return build_rounded_rectangle_station(0.0, 0.0, z, 134.0, 53.0, 18.0, n_samples)


def main():
    repo_root = Path(__file__).resolve().parent.parent
    if len(sys.argv) > 1:
        obj_path = Path(sys.argv[1]).resolve()
    else:
        obj_path = repo_root / "obj" / "Cif3_jerry_can_reduced.obj"
        if not obj_path.exists():
            obj_path = repo_root / "Cif3_jerry_can_reduced.obj"

    if len(sys.argv) > 2:
        out_json = Path(sys.argv[2]).resolve()
    else:
        out_json = repo_root / "Cif3_parametric_spec.json"

    print(f"Loading {obj_path.name}...")
    mesh = trimesh.load(str(obj_path), process=False)
    mesh.apply_scale(100.0)

    spec = {}
    n_pts_station = 48

    # 1. Driving Expressions Architecture (Chained, Zero Orphans)
    spec["expressions"] = [
        ("BASE_EXTENSION_HEIGHT", "2.000"),
        ("BASE_BLEND_R", "1.500"),
        ("SHOULDER_START_Z", "145.000"),
        ("SHOULDER_HEIGHT", "17.000"),
        ("NECK_START_Z", "SHOULDER_START_Z + SHOULDER_HEIGHT"),
        ("COLLAR_DIA", "31.000"),
        ("COLLAR_HEIGHT", "22.500"),
        ("CAP_START_Z", "NECK_START_Z + COLLAR_HEIGHT"),
        ("CAP_DIA", "27.500"),
        ("CAP_HEIGHT", "14.970"),
        ("CAP_BLEND_R", "1.200"),
    ]

    # 2. Zone Stations
    # Lower Body: Z = 2.0 to 75.0 mm (H = 73.0 mm)
    lower_heights_z = [2.0, 5.0, 10.0, 18.0, 28.0, 38.0, 50.0, 65.0, 75.0]
    spec["lower_stations"] = [extract_station_at_z(mesh, z, n_pts_station) for z in lower_heights_z]

    # Mid Body: Z = 75.0 to 145.0 mm (H = 70.0 mm)
    mid_heights_z = [75.0, 85.0, 100.0, 115.0, 128.0, 138.0, 145.0]
    spec["mid_stations"] = [extract_station_at_z(mesh, z, n_pts_station) for z in mid_heights_z]

    # Upper Shoulder: Z = 145.0 to 164.0 mm (H = 19.0 mm)
    shoulder_heights_z = [145.0, 150.0, 155.0, 160.0, 164.0]
    spec["shoulder_stations"] = [extract_station_at_z(mesh, z, n_pts_station) for z in shoulder_heights_z]

    # Handle Solid Arch: Z = 160.0 to 199.45 mm (H = 39.45 mm)
    handle_specs = [
        # (z, width, depth, cx, cy, radius)
        (160.0, 90.3, 36.0, 19.2, 0.0, 12.0),
        (168.0, 88.0, 32.0, 18.5, 0.0, 10.0),
        (176.0, 84.5, 28.0, 17.8, 0.0, 9.0),
        (184.0, 79.0, 24.0, 17.5, 0.0, 8.0),
        (192.0, 72.0, 21.0, 17.3, 0.0, 7.0),
        (197.0, 56.0, 16.5, 13.0, 0.0, 6.0),
        (199.45, 44.0, 12.0, 9.0, 0.0, 5.0),
    ]
    spec["handle_stations"] = [
        build_rounded_rectangle_station(hcx, hcy, hz, hw, hd, hr, n_pts_station)
        for (hz, hw, hd, hcx, hcy, hr) in handle_specs
    ]

    # 3. Handle Opening Analytical Parameters (lines + tangent arcs)
    spec["handle_opening"] = {
        "x_min": -11.39,
        "x_max": 45.67,
        "z_min": 164.34,
        "z_max": 189.00,
        "corner_radius": 8.0,
        "y_cut_start": -35.0,
        "y_cut_depth": 70.0,
    }

    # 4. Offset Neck Collar and Cap Details (Smooth cylinders, no extra ribs)
    spec["neck"] = {
        "collar_pos_x": -48.2,
        "collar_pos_y": -0.5,
        "collar_dia": 31.0,
        "collar_height": 22.5,
        "cap_dia": 27.5,
        "cap_height": 14.97,
        "cap_top_blend_radius": 1.2,
    }

    # 5. Bottom Base Extension
    spec["bottom_base"] = {
        "height": 2.0,
        "blend_radius": 1.5,
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print(f"Saved refined CAD specification to {out_json} ({out_json.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
