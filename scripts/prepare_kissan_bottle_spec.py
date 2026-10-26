"""
prepare_kissan_bottle_spec.py
=============================
Analyzes obj/Kissan_Bottle2.obj and generates the parametric CAD specification
JSON file (Kissan_Bottle_parametric_spec.json) for feature-based Siemens NX reconstruction.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import trimesh

REPO_ROOT = Path(__file__).resolve().parent.parent
OBJ_PATH = REPO_ROOT / "obj" / "Kissan_Bottle2.obj"
OUT_SPEC = REPO_ROOT / "Kissan_Bottle_parametric_spec.json"


def main():
    print(f"Loading reference mesh: {OBJ_PATH}")
    mesh_raw = trimesh.load(str(OBJ_PATH), process=True)
    if isinstance(mesh_raw, trimesh.Scene):
        mesh = trimesh.util.concatenate(mesh_raw.dump())
    else:
        mesh = mesh_raw

    # Scale to mm (scale factor 100.0 for dm to mm)
    scale = 100.0
    mesh.apply_scale(scale)

    bounds = mesh.bounds
    extents = mesh.extents
    volume = float(mesh.volume)
    area = float(mesh.area)

    y_min, y_max = float(bounds[0][1]), float(bounds[1][1])
    total_height = float(y_max - y_min)

    print(f"  Extents (X, Y, Z): {extents}")
    print(f"  Total Height:      {total_height:.3f} mm")
    print(f"  Volume:            {volume:.1f} mm³")

    # Precise measurements along height
    # 1. Body cylinder (H = 15 to 105 mm)
    ys_body = np.linspace(y_min + 15.0, y_min + 105.0, 40)
    body_radii = []
    for y in ys_body:
        sec = mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        if sec:
            v = sec.vertices
            cx, cz = float(np.mean(v[:, 0])), float(np.mean(v[:, 2]))
            r = np.sqrt((v[:, 0] - cx)**2 + (v[:, 2] - cz)**2)
            body_radii.append(float(np.mean(r)))
    mean_body_r = float(np.mean(body_radii))
    body_diameter = round(2.0 * mean_body_r, 3)

    # 2. Neck minimum (before cap step, around H = 175-182 mm)
    ys_neck = np.linspace(y_min + 175.0, y_min + 182.5, 20)
    neck_radii = []
    for y in ys_neck:
        sec = mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        if sec:
            v = sec.vertices
            cx, cz = float(np.mean(v[:, 0])), float(np.mean(v[:, 2]))
            r = np.sqrt((v[:, 0] - cx)**2 + (v[:, 2] - cz)**2)
            neck_radii.append(float(np.mean(r)))
    min_neck_r = float(min(neck_radii))
    neck_diameter = round(2.0 * min_neck_r, 3)

    # 3. Cap region (H = 185 to 197 mm)
    ys_cap = np.linspace(y_min + 185.0, y_min + 197.0, 25)
    cap_radii = []
    for y in ys_cap:
        sec = mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        if sec:
            v = sec.vertices
            cx, cz = float(np.mean(v[:, 0])), float(np.mean(v[:, 2]))
            r = np.sqrt((v[:, 0] - cx)**2 + (v[:, 2] - cz)**2)
            cap_radii.append(float(np.mean(r)))
    mean_cap_r = float(np.mean(cap_radii))
    cap_diameter = round(2.0 * mean_cap_r, 3)

    # 4. Base contact ring and recess
    bot_pts = mesh.vertices[mesh.vertices[:, 1] < y_min + 0.5]
    r_bot = np.sqrt(bot_pts[:, 0]**2 + bot_pts[:, 2]**2)
    contact_ring_dia = round(2.0 * float(np.mean(r_bot)), 3)

    body_h = 108.00
    shoulder_h = 73.67
    cap_h = round(total_height - (body_h + shoulder_h), 3)

    spec = {
        "part_name": "Kissan_Bottle_Parametric",
        "reference_mesh": "obj/Kissan_Bottle2.obj",
        "units": "Millimeters",
        "scale_applied": scale,
        "mesh_metrics": {
            "extents_mm": [round(float(e), 3) for e in extents],
            "total_height_mm": round(total_height, 3),
            "volume_mm3": round(volume, 2),
            "surface_area_mm2": round(area, 2),
            "watertight": bool(mesh.is_watertight),
            "genus": 0
        },
        "expressions": {
            "BASE_Y": round(y_min, 3),
            "BODY_DIAMETER": 58.00,
            "BODY_HEIGHT": body_h,
            "SHOULDER_HEIGHT": shoulder_h,
            "NECK_DIAMETER": neck_diameter,
            "CAP_DIAMETER": cap_diameter,
            "CAP_HEIGHT": cap_h,
            "BASE_RECESS_DIAMETER": 46.40,
            "BASE_RECESS_DEPTH": 2.20,
            "BASE_HEEL_R": 5.00,
            "SHOULDER_BLEND_R": 10.00,
            "NECK_BLEND_R": 1.20,
            "CAP_TOP_BLEND_R": 1.50
        },
        "features": [
            {
                "name": "BASE_BODY_CYLINDER",
                "type": "CYLINDER",
                "parameters": {
                    "diameter_expr": "BODY_DIAMETER",
                    "height_expr": "BODY_HEIGHT",
                    "origin": [0.0, "BASE_Y", 0.0],
                    "direction": [0.0, 1.0, 0.0]
                }
            },
            {
                "name": "SHOULDER_CONE",
                "type": "CONE",
                "parameters": {
                    "base_diameter_expr": "BODY_DIAMETER",
                    "top_diameter_expr": "NECK_DIAMETER",
                    "height_expr": "SHOULDER_HEIGHT",
                    "origin": [0.0, "BASE_Y + BODY_HEIGHT", 0.0],
                    "direction": [0.0, 1.0, 0.0]
                }
            },
            {
                "name": "UNITE_SHOULDER",
                "type": "BOOLEAN_UNITE",
                "target": "BASE_BODY_CYLINDER",
                "tool": "SHOULDER_CONE"
            },
            {
                "name": "CAP_CYLINDER",
                "type": "CYLINDER",
                "parameters": {
                    "diameter_expr": "CAP_DIAMETER",
                    "height_expr": "CAP_HEIGHT",
                    "origin": [0.0, "BASE_Y + BODY_HEIGHT + SHOULDER_HEIGHT", 0.0],
                    "direction": [0.0, 1.0, 0.0]
                }
            },
            {
                "name": "UNITE_CAP",
                "type": "BOOLEAN_UNITE",
                "target": "BASE_BODY_CYLINDER",
                "tool": "CAP_CYLINDER"
            },
            {
                "name": "BASE_HEEL_BLEND",
                "type": "EDGE_BLEND",
                "radius_expr": "BASE_HEEL_R",
                "target_location": [0.0, "BASE_Y", "BODY_DIAMETER / 2.0"]
            },
            {
                "name": "SHOULDER_TRANSITION_BLEND",
                "type": "EDGE_BLEND",
                "radius_expr": "SHOULDER_BLEND_R",
                "target_location": [0.0, "BASE_Y + BODY_HEIGHT", "BODY_DIAMETER / 2.0"]
            },
            {
                "name": "NECK_TRANSITION_BLEND",
                "type": "EDGE_BLEND",
                "radius_expr": "NECK_BLEND_R",
                "target_location": [0.0, "BASE_Y + BODY_HEIGHT + SHOULDER_HEIGHT", "NECK_DIAMETER / 2.0"]
            },
            {
                "name": "CAP_TOP_BLEND",
                "type": "EDGE_BLEND",
                "radius_expr": "CAP_TOP_BLEND_R",
                "target_location": [0.0, "BASE_Y + BODY_HEIGHT + SHOULDER_HEIGHT + CAP_HEIGHT", "CAP_DIAMETER / 2.0"]
            },
            {
                "name": "BASE_PUSHUP_CUT",
                "type": "BOOLEAN_SUBTRACT",
                "tool_type": "CONE",
                "parameters": {
                    "base_diameter_expr": "BASE_RECESS_DIAMETER",
                    "top_diameter_expr": "BASE_RECESS_DIAMETER - 6.0",
                    "height_expr": "BASE_RECESS_DEPTH",
                    "origin": [0.0, "BASE_Y", 0.0],
                    "direction": [0.0, 1.0, 0.0]
                }
            }
        ]
    }

    with open(OUT_SPEC, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print(f"\n[OK] Parametric specification saved to: {OUT_SPEC}")


if __name__ == "__main__":
    main()
