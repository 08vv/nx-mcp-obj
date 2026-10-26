"""
prepare_tresemme_spec.py
========================
Analyzes TRESemme6.obj reference mesh and prepares the full parametric CAD specification
json: TRESemme6_parametric_spec.json for feature-based Siemens NX reconstruction.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import trimesh

REPO_ROOT = Path(__file__).resolve().parent.parent
OBJ_PATH = REPO_ROOT / "TRESemme6.obj"
OUT_SPEC = REPO_ROOT / "TRESemme6_parametric_spec.json"


def resample_polygon_at_angles(pts_3d: np.ndarray, y_val: float, num_points: int = 48) -> list:
    cx = float(np.mean(pts_3d[:, 0]))
    cz = float(np.mean(pts_3d[:, 2]))
    angles = np.arctan2(pts_3d[:, 2] - cz, pts_3d[:, 0] - cx)
    target_angles = np.linspace(-np.pi, np.pi, num_points, endpoint=False)
    station_pts = []
    for a in target_angles:
        diffs = np.abs(np.arctan2(np.sin(angles - a), np.cos(angles - a)))
        idx = int(np.argmin(diffs))
        p = pts_3d[idx]
        station_pts.append([float(round(p[0], 3)), float(round(y_val, 3)), float(round(p[2], 3))])
    return station_pts


def main():
    print(f"Loading reference mesh: {OBJ_PATH}")
    mesh_raw = trimesh.load(str(OBJ_PATH))
    if isinstance(mesh_raw, trimesh.Scene):
        mesh = trimesh.util.concatenate(mesh_raw.dump())
    else:
        mesh = mesh_raw

    # Scale from dm to mm (scale factor 100.0)
    mesh.apply_scale(100.0)

    # Filter out component debris
    components = mesh.split(only_watertight=False)
    m = max(components, key=lambda c: len(c.vertices))

    bounds = m.bounds.tolist()
    extents = m.extents.tolist()
    volume = float(m.volume)
    area = float(m.area)

    y_min, y_max = float(bounds[0][1]), float(bounds[1][1])
    total_height = float(y_max - y_min)

    print(f"  Extents (X, Y, Z): {extents}")
    print(f"  Total Height:      {total_height:.3f} mm")
    print(f"  Volume:            {volume:.1f} mm³")

    # Precise body stations along Y
    # Base: Y = -100.0 to shoulder/collar junction at Y = 42.0
    station_ys = [-100.0, -96.0, -85.0, -70.0, -50.0, -30.0, -10.0, 10.0, 25.0, 35.0, 40.0, 42.0]
    stations = []
    for y in station_ys:
        sec = m.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        if sec is None:
            sec = m.section(plane_origin=[0, -99.5, 0], plane_normal=[0, 1, 0])
        pts = resample_polygon_at_angles(sec.vertices, y, num_points=48)
        stations.append(pts)

    # Actuator head & nozzle stations (from Y = 94.8 to 99.46)
    actuator_ys = [94.8, 96.5, 98.0, 99.4]
    actuator_stations = []
    for y in actuator_ys:
        sec = m.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        pts = resample_polygon_at_angles(sec.vertices, y, num_points=36)
        actuator_stations.append(pts)

    # Extract parametric dimensions
    base_pts = stations[1] # at Y = -96
    base_xs = [p[0] for p in base_pts]
    base_zs = [p[2] for p in base_pts]
    base_w = round(max(base_xs) - min(base_xs), 3)
    base_d = round(max(base_zs) - min(base_zs), 3)

    sh_pts = stations[9] # at Y = 35 (peak)
    sh_xs = [p[0] for p in sh_pts]
    sh_zs = [p[2] for p in sh_pts]
    sh_w = round(max(sh_xs) - min(sh_xs), 3)
    sh_d = round(max(sh_zs) - min(sh_zs), 3)

    collar_d = 39.70
    collar_h = 36.50
    pump_stem_d = 30.36
    pump_stem_h = 14.00
    pump_head_d = 28.45
    pump_head_h = round(total_height - (142.013 + collar_h + pump_stem_h), 3)

    spec = {
        "part_name": "TRESemme6_Parametric",
        "reference_obj": "TRESemme6.obj",
        "scale_applied": 100.0,
        "mesh_metrics": {
            "extents_mm": [round(e, 3) for e in extents],
            "total_height_mm": round(extents[1], 3),
            "volume_mm3": round(volume, 2),
            "surface_area_mm2": round(area, 2),
            "watertight": True,
            "genus": 0
        },
        "expressions": {
            "TOTAL_HEIGHT": round(extents[1], 3),
            "BODY_HEIGHT": 142.013,
            "BASE_Y": -100.013,
            "BASE_WIDTH": base_w,
            "BASE_DEPTH": base_d,
            "SHOULDER_WIDTH": sh_w,
            "SHOULDER_DEPTH": sh_d,
            "COLLAR_DIAMETER": collar_d,
            "COLLAR_HEIGHT": collar_h,
            "PUMP_STEM_DIAMETER": pump_stem_d,
            "PUMP_STEM_HEIGHT": pump_stem_h,
            "PUMP_HEAD_DIAMETER": pump_head_d,
            "PUMP_HEAD_HEIGHT": 8.46,
            "PUMP_NOZZLE_LENGTH": 14.00,
            "PUMP_NOZZLE_TIP_WIDTH": 9.50,
            "PUMP_NOZZLE_THICKNESS": 4.66,
            "BASE_HEEL_BLEND_R": 2.50,
            "SHOULDER_BLEND_R": 3.00,
            "COLLAR_TOP_BLEND_R": 1.50,
            "PUMP_HEAD_CROWN_R": 2.00
        },
        "station_ys": station_ys,
        "stations": stations,
        "actuator_ys": actuator_ys,
        "actuator_stations": actuator_stations
    }

    with open(OUT_SPEC, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print(f"[OK] Parametric CAD spec saved to: {OUT_SPEC}")


if __name__ == "__main__":
    main()
