#!/usr/bin/env python3
"""
prepare_makeup_star2_spec.py
============================
Extracts high-fidelity parametric cross-section stations from makeup_cosmetic_star2.obj
and generates Makeup_Cosmetic_Star2_spec.json for the Siemens NX reconstruction.
"""

import json
from pathlib import Path
import numpy as np
import trimesh

def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    obj_path = repo_root / "obj" / "makeup_cosmetic_star2.obj"
    out_spec = repo_root / "Makeup_Cosmetic_Star2_spec.json"

    print(f"Loading OBJ: {obj_path}")
    mesh = trimesh.load(str(obj_path))
    mesh.apply_scale(100.0)  # Scale to mm

    print(f"Mesh bounds: {mesh.bounds.tolist()}")
    print(f"Mesh extents: {mesh.extents.tolist()}")

    n_points = 96  # High resolution points per station (48 crimps * 2 points = exact 96)

    def extract_station(y_val):
        sec = mesh.section(plane_origin=[0.0, float(y_val), 0.0], plane_normal=[0.0, 1.0, 0.0])
        if sec is None or len(sec.vertices) == 0:
            return None
        p = sec.vertices
        ang = np.arctan2(p[:, 2], p[:, 0])
        rad = np.sqrt(p[:, 0]**2 + p[:, 2]**2)

        idx = np.argsort(ang)
        ang_s = ang[idx]
        rad_s = rad[idx]

        # Regular angle grid
        a_grid = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
        r_grid = np.interp(a_grid, ang_s, rad_s, period=2 * np.pi)

        cad_z = float(y_val + 25.5)
        pts_cad = [[round(float(r_grid[i] * np.cos(a_grid[i])), 4),
                    round(float(r_grid[i] * np.sin(a_grid[i])), 4),
                    round(cad_z, 4)] for i in range(n_points)]
        return pts_cad

    # Zone 1 stations (Lower Octagon: Z = 0.5 to 20.5 mm)
    z1_y_levels = [-25.0, -20.0, -15.0, -10.0, -5.0]
    z1_stations = [extract_station(y) for y in z1_y_levels]

    # Zone 2 stations (Crimped Ring: Z = 20.5 to 39.5 mm)
    z2_y_levels = [-5.0, 0.0, 5.0, 10.0, 14.0]
    z2_stations = [extract_station(y) for y in z2_y_levels]

    # Zone 3 stations (Upper Tapered Shoulder: Z = 39.5 to 50.5 mm)
    z3_y_levels = [14.0, 17.0, 20.0, 23.0, 25.0]
    z3_stations = [extract_station(y) for y in z3_y_levels]

    spec = {
        "part_name": "Makeup_Cosmetic_Star2",
        "units": "Millimeters",
        "mesh_stats": {
            "extents_mm": [round(float(x), 3) for x in mesh.extents],
            "bounds_mm": [[round(float(x), 3) for x in b] for b in mesh.bounds],
            "total_height_mm": 50.55,
        },
        "expressions": [
            ["BASE_BOTTOM_BLEND_R", "2.000"],
            ["TOP_RIM_BLEND_R", "1.200"],
        ],
        "zones": {
            "zone1_lower_octagon": {
                "name": "ZONE1_LOWER_OCTAGON",
                "z_start": 0.5,
                "z_end": 20.5,
                "stations": z1_stations
            },
            "zone2_crimped_ring": {
                "name": "ZONE2_CRIMPED_RING",
                "z_start": 20.5,
                "z_end": 39.5,
                "stations": z2_stations
            },
            "zone3_tapered_shoulder": {
                "name": "ZONE3_TAPERED_SHOULDER",
                "z_start": 39.5,
                "z_end": 50.5,
                "stations": z3_stations
            }
        }
    }

    with open(out_spec, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print(f"[OK] Spec written to: {out_spec}")

if __name__ == "__main__":
    main()
