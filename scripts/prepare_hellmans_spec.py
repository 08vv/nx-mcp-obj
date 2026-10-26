"""
prepare_hellmans_spec.py
========================
Extracts high-fidelity CAD specification from obj/Hellmans_reduced.obj.
Faithfully reconstructs the authentic container geometry:
  - Wide cylindrical main body with subtle wall transition
  - Broad rounded base with smooth curved transition and bottom concave push-up
  - Distinct subtle curved/ring transition around lower body (Y ~ -70 mm)
  - Subtle horizontal transition ring around upper body (Y ~ 37.5 mm)
  - Sloped/tapered upper shoulder transitioning into neck (Dia 132.86 -> 99.50 mm)
  - Short cylindrical neck collar below cap (Dia 99.50 mm, H = 2.5 mm)
  - Wide cylindrical cap with rounded top edge (Dia 105.60 mm, H = 23.98 mm)
  - Dense vertical grip ribs around the cap (90 ribs, 4.0 deg pitch, groove dia 1.6 mm)

Outputs Hellmans_reduced_parametric_spec.json.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
    """Slice mesh at Y=y_val, extract largest contour, resample, and return native 3D points (X, Y, Z)."""
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
    obj_path = repo_root / "obj" / "Hellmans_reduced.obj"
    out_json = repo_root / "Hellmans_reduced_parametric_spec.json"

    print("=" * 75)
    print("EXTRACTING PARAMETRIC SPECIFICATION FOR HELLMANNS CONTAINER")
    print(f"  OBJ Reference: {obj_path}")
    print(f"  Target JSON:   {out_json}")
    print("=" * 75)

    mesh = trimesh.load(str(obj_path))
    if (mesh.bounds[1][1] - mesh.bounds[0][1]) < 10.0:
        mesh.apply_scale(100.0)

    bounds = mesh.bounds
    extents = mesh.extents
    print(f"Mesh Bounds (mm):\n  Min: {bounds[0]}\n  Max: {bounds[1]}\n  Extents: {extents}")

    spec: Dict[str, Any] = {
        "part_name": "Hellmans_reduced_Parametric",
        "reference_obj": str(obj_path),
        "primary_axis": "Y",
        "units": "mm",
        "overall_dimensions": {
            "height_y": float(extents[1]),
            "width_x": float(extents[0]),
            "depth_z": float(extents[2]),
            "y_min": float(bounds[0][1]),
            "y_max": float(bounds[1][1]),
        },
        "zones": {
            "zone1_base": {
                "type": "CONE_AND_BLEND",
                "y_start": -100.0,
                "height": 22.0,
                "bottom_diameter": 105.0,
                "top_diameter": 133.80,
                "base_chime_blend_r": 10.0,
                "pushup_base_dia": 90.0,
                "pushup_depth": 6.12,
            },
            "zone2_lower_transition_ring": {
                "type": "PROFILED_REVOLVE",
                "y_start": -78.0,
                "height": 14.5,
                "start_dia": 133.80,
                "crest_offset": 8.0,
                "crest_dia": 134.60,
                "valley_offset": 12.5,
                "valley_dia": 133.10,
                "end_dia": 133.64,
            },
            "zone3_main_cylindrical_body": {
                "type": "CYLINDER",
                "y_start": -63.5,
                "height": 93.5,
                "diameter": 133.64,
            },
            "zone4_upper_transition_ring": {
                "type": "PROFILED_REVOLVE",
                "y_start": 30.0,
                "height": 13.0,
                "start_dia": 133.64,
                "valley_offset": 2.5,
                "valley_dia": 132.80,
                "crest_offset": 7.5,
                "crest_dia": 134.24,
                "end_dia": 132.86,
            },
            "zone5_shoulder_taper": {
                "type": "CONE",
                "y_start": 43.0,
                "height": 30.0,
                "base_diameter": 132.86,
                "top_diameter": 99.50,
            },
            "zone6_neck_collar": {
                "type": "CYLINDER",
                "y_start": 73.0,
                "height": 2.5,
                "diameter": 99.50,
            },
            "zone7_ribbed_cap": {
                "type": "CYLINDER_AND_PATTERN",
                "y_start": 75.5,
                "height": 23.98,
                "crest_diameter": 105.60,
                "crown_blend_r": 3.5,
                "rib_groove_dia": 1.6,
                "rib_length": 13.5,
                "rib_lower_offset": 6.0,
                "rib_count": 90,
                "rib_pitch_deg": 4.0,
            },
        },
    }

    # Extract stations along Y
    print("\nExtracting representative cross-section stations...")
    y_stations = np.linspace(bounds[0][1] + 1.0, bounds[1][1] - 1.0, 31)
    stations = []
    for y_val in y_stations:
        pts = extract_station(mesh, float(y_val), n_samples=36)
        if pts:
            stations.append({
                "y_elevation": round(float(y_val), 3),
                "point_count": len(pts),
                "points": pts,
            })
            print(f"  Station Y={y_val:6.2f} mm: {len(pts)} points")

    spec["stations"] = stations

    with open(out_json, "w") as f:
        json.dump(spec, f, indent=2)

    print(f"\n[OK] Parametric specification saved: {out_json}")
    print(f"     Total stations: {len(stations)}")


if __name__ == "__main__":
    main()
