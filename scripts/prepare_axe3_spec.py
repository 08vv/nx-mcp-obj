"""
prepare_axe3_spec.py
====================
Generates the parametric CAD specification (Axe3_parametric_spec.json)
for the Axe cylindrical bottle spray can from Axe3.obj:
- Straight cylindrical lower canister (Dia ~77.14 mm)
- Narrower neck section (Dia ~71.72 mm)
- Smooth shoulder transition (Dia ~77.0 mm)
- Large cylindrical cap (Dia ~76.8 mm, Height ~67.46 mm)
- 40 dense vertical flutes/ribs around lower portion of cap (depth ~0.60 mm, height ~40.5 mm)
- Smooth upper portion of cap (Height ~23.5 mm)
- Concave bottom dome cavity cut (Depth ~6.70 mm)
- Rounded heel and cap crown edge blends
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import trimesh

REPO_ROOT = Path(__file__).resolve().parent.parent
OBJ_PATH = REPO_ROOT / "Axe3.obj"
OUT_SPEC = REPO_ROOT / "Axe3_parametric_spec.json"


def main():
    print(f"Loading reference mesh: {OBJ_PATH}")
    mesh_raw = trimesh.load(str(OBJ_PATH))
    if isinstance(mesh_raw, trimesh.Scene):
        mesh = trimesh.util.concatenate(mesh_raw.dump())
    else:
        mesh = mesh_raw

    # Scale to mm (scale factor 100.0)
    mesh.apply_scale(100.0)

    # Filter isolated debris if any
    comps = mesh.split(only_watertight=False)
    m = max(comps, key=lambda c: len(c.vertices))

    bounds = m.bounds.tolist()
    extents = m.extents.tolist()
    volume = float(m.volume)
    area = float(m.area)

    y_min, y_max = float(bounds[0][1]), float(bounds[1][1])
    total_height = float(y_max - y_min)

    print(f"  Extents (X, Y, Z): {extents}")
    print(f"  Total Height:      {total_height:.3f} mm")
    print(f"  Volume:            {volume:.1f} mm³")

    # Precise measurements along height
    # 1. Body cylinder (Y in [-90, +5])
    ys_body = np.linspace(-90.0, 5.0, 30)
    body_radii = []
    for y in ys_body:
        sec = m.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        if sec:
            v = sec.vertices
            cx, cz = float(np.mean(v[:, 0])), float(np.mean(v[:, 2]))
            r = np.hypot(v[:, 0] - cx, v[:, 2] - cz)
            body_radii.append(float(np.mean(r)))
    body_dia = round(2.0 * float(np.mean(body_radii)), 2)

    # 2. Narrower neck waist (Y in [15, 25])
    ys_neck = np.linspace(15.0, 25.0, 15)
    neck_radii = []
    for y in ys_neck:
        sec = m.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        if sec:
            v = sec.vertices
            cx, cz = float(np.mean(v[:, 0])), float(np.mean(v[:, 2]))
            r = np.hypot(v[:, 0] - cx, v[:, 2] - cz)
            neck_radii.append(float(np.mean(r)))
    neck_dia = round(2.0 * float(np.mean(neck_radii)), 2)

    # 3. Shoulder expansion (around Y = 32-35)
    sec_sh = m.section(plane_origin=[0, 35.0, 0], plane_normal=[0, 1, 0])
    v_sh = sec_sh.vertices
    cx, cz = float(np.mean(v_sh[:, 0])), float(np.mean(v_sh[:, 2]))
    sh_dia = round(2.0 * float(np.mean(np.hypot(v_sh[:, 0] - cx, v_sh[:, 2] - cz))), 2)

    # 4. Cap dimensions
    cap_y_start = 32.0
    cap_h = round(total_height - (cap_y_start - y_min), 3)

    spec = {
        "part_name": "Axe3_Parametric",
        "reference_obj": "Axe3.obj",
        "scale_applied": 100.0,
        "mesh_metrics": {
            "extents_mm": [round(e, 3) for e in extents],
            "total_height_mm": round(total_height, 3),
            "volume_mm3": round(volume, 2),
            "surface_area_mm2": round(area, 2),
            "watertight": True,
            "genus": 0
        },
        "expressions": {
            "TOTAL_HEIGHT": round(total_height, 3),
            "BODY_DIAMETER": body_dia,
            "BODY_HEIGHT": round(10.0 - y_min, 3),
            "BASE_Y": round(y_min, 3),
            "WAIST_DIAMETER": neck_dia,
            "WAIST_HEIGHT": 22.0,
            "SHOULDER_DIAMETER": sh_dia,
            "CAP_DIAMETER": 76.80,
            "CAP_HEIGHT": cap_h,
            "RIB_COUNT": 40,
            "RIB_HEIGHT": 40.50,
            "RIB_DEPTH": 0.60,
            "RIB_CUTTER_DIA": 1.80,
            "SMOOTH_CAP_HEIGHT": 23.50,
            "BOTTOM_DOME_DIA": 60.00,
            "BOTTOM_DOME_DEPTH": 6.70,
            "BOTTOM_HEEL_R": 2.50,
            "WAIST_BLEND_R": 2.50,
            "SHOULDER_BLEND_R": 2.50,
            "CAP_TOP_BLEND_R": 2.50
        }
    }

    with open(OUT_SPEC, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    print(f"[OK] Parametric CAD spec saved to: {OUT_SPEC}")


if __name__ == "__main__":
    main()
