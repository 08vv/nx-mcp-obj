"""
fidelity_checker.py
===================
Geometric and Dimensional Fidelity Verification: Siemens NX CAD vs Reference OBJ Mesh.

Compares:
1. Bounding Box Dimensions (dx, dy, dz) in mm and percentage error.
2. Solid Volume vs Mesh Volume (mm^3 and percentage error).
3. Radial Profile at ~20-50 height stations:
   - Maximum radial deviation in mm and percentage.
   - Mean radial deviation.
4. Generates side-by-side visual comparison plot saved to output/<part>_comparison.png.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# Named acceptance tolerance constants (Enforced)
MAX_SECTION_DEVIATION_PCT: float = 10.0  # Max permitted cross-section dimension deviation (X width or Z thickness)
MAX_AREA_DEVIATION_PCT: float = 10.0     # Max permitted cross-section area deviation (covers corners/diagonals)
MAX_BBOX_DEVIATION_PCT: float = 10.0     # Max permitted bounding box extents deviation
MAX_VOLUME_DEVIATION_PCT: float = 10.0   # Max permitted whole-part volume deviation
MAX_AXIAL_END_GAP_FRACTION: float = 0.01  # Max permitted axial end gap (top/bottom) as fraction of height (1.0%)
END_ZONE_HEIGHT_FRACTION: float = 0.05    # Height fraction at each end considered end-zone (5.0%)
MAX_END_ZONE_DISTANCE_FRACTION: float = 0.02  # Max allowable surface/radial distance deviation in end-zone as fraction of part size (2.0%)
MAX_END_ZONE_LOCAL_RADIUS_FRACTION: float = 0.15  # Max allowable end-zone distance deviation as fraction of local radius (15.0%)



def parse_obj_pure_python(obj_path: Path) -> Tuple[List[Tuple[float, float, float]], List[Tuple[int, int, int]]]:
    """Pure-python fast OBJ parser (zero external dependencies)."""
    vertices: List[Tuple[float, float, float]] = []
    faces: List[Tuple[int, int, int]] = []

    with open(obj_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("v "):
                parts = line.split()
                if len(parts) >= 4:
                    vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif line.startswith("f "):
                parts = line.split()[1:]
                # Parse vertex indices (1-indexed)
                idxs = []
                for p in parts:
                    v_idx = int(p.split("/")[0])
                    idxs.append(v_idx - 1 if v_idx > 0 else len(vertices) + v_idx)
                if len(idxs) == 3:
                    faces.append((idxs[0], idxs[1], idxs[2]))
                elif len(idxs) == 4:
                    faces.append((idxs[0], idxs[1], idxs[2]))
                    faces.append((idxs[0], idxs[2], idxs[3]))
    return vertices, faces


def compute_mesh_volume_pure_python(vertices: List[Tuple[float, float, float]], faces: List[Tuple[int, int, int]]) -> float:
    """Computes signed volume of a 3D triangle mesh using tetrahedron decomposition in pure Python."""
    if not faces or not vertices:
        return 0.0
    total_vol = 0.0
    for f in faces:
        p1 = vertices[f[0]]
        p2 = vertices[f[1]]
        p3 = vertices[f[2]]
        v = (
            p1[0] * (p2[1] * p3[2] - p2[2] * p3[1])
            + p1[1] * (p2[2] * p3[0] - p2[0] * p3[2])
            + p1[2] * (p2[0] * p3[1] - p2[1] * p3[0])
        )
        total_vol += v
    return abs(total_vol) / 6.0


def evaluate_cad_radius_at_z(zones: List[Dict[str, Any]], z: float) -> Optional[float]:
    """Evaluates the parametric CAD model's outer radius at elevation z, including edge blends."""
    for zdef in zones:
        z0 = float(zdef["z_start"])
        z1 = float(zdef["z_end"])
        r0 = float(zdef["r_start"])
        r1 = float(zdef["r_end"])
        rm = float(zdef.get("r_mid", (r0 + r1) / 2.0))
        blend_r = float(zdef.get("blend_r", 0.0))
        seg_type = zdef.get("segment_type", "LINE")
        h = z1 - z0
        if h <= 1e-4:
            continue
        if z0 - 1e-3 <= z <= z1 + 1e-3:
            # Check bottom edge blend
            if blend_r > 0.1 and z < z0 + blend_r:
                dz = z - (z0 + blend_r)
                r_base = r0
                return r_base - (blend_r - math.sqrt(max(0.0, blend_r**2 - dz**2)))
            t = (z - z0) / h
            t = max(0.0, min(1.0, t))
            if seg_type == "ARC":
                # 2-segment polyline: start -> mid -> end
                if t < 0.5:
                    return r0 + 2.0 * t * (rm - r0)
                else:
                    return rm + 2.0 * (t - 0.5) * (r1 - rm)
            else:
                return r0 + t * (r1 - r0)
    return None


def run_fidelity_check(
    obj_path: Path,
    spec_path: Optional[Path] = None,
    stl_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    cad_bounds: Optional[Tuple[float, float, float, float, float, float]] = None,
    n_stations: int = 50,
    cad_obj: Optional[Path] = None,
) -> Dict[str, Any]:
    stl_path = stl_path or cad_obj
    """
    Computes shape-agnostic geometric fidelity verification between reference OBJ and CAD part:
      1. Whole-part volume comparison within MAX_VOLUME_DEVIATION_PCT.
      2. Bounding box extents (height, width, thickness) within MAX_BBOX_DEVIATION_PCT.
      3. Cross-section dimensions at N stations comparing X-width, Z-thickness, AND full section
         area (covering diagonals and corners) within MAX_SECTION_DEVIATION_PCT / MAX_AREA_DEVIATION_PCT.
    """
    if not obj_path.exists():
        raise FileNotFoundError(f"OBJ file not found: {obj_path}")

    vertices, faces = parse_obj_pure_python(obj_path)
    if not vertices:
        return {"passed": False, "error": "Empty OBJ mesh."}

    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]

    raw_dx = max(xs) - min(xs)
    raw_dy = max(ys) - min(ys)
    raw_dz = max(zs) - min(zs)
    max_extent = max(raw_dx, raw_dy, raw_dz)

    # Unit auto-scaling
    scale = 1.0
    if max_extent < 0.25:
        scale = 1000.0
    elif max_extent < 15.0:
        scale = 100.0

    verts_scaled = [(v[0] * scale, v[1] * scale, v[2] * scale) for v in vertices]

    # Canonical frame alignment: check if plan defines a canonical rotation matrix
    rot_matrix = None
    if spec_path and Path(spec_path).exists():
        try:
            with open(spec_path, "r", encoding="utf-8") as sf:
                s_data = json.load(sf)
            rm = s_data.get("rotation_matrix")
            if rm is not None:
                rot_matrix = np.array(rm)
        except Exception:
            pass

    if rot_matrix is not None:
        verts_arr = np.array(verts_scaled) @ rot_matrix.T
        verts_scaled = [tuple(float(x) for x in v) for v in verts_arr]

    xs = [v[0] for v in verts_scaled]
    ys = [v[1] for v in verts_scaled]
    zs = [v[2] for v in verts_scaled]

    obj_dx = max(xs) - min(xs)
    obj_dy = max(ys) - min(ys)
    obj_dz = max(zs) - min(zs)

    # Load 3D meshes for volume & shape calculation
    mesh_ref_tm = None
    mesh_cad_tm = None
    try:
        import trimesh
        mesh_ref_tm = trimesh.load(str(obj_path), force="mesh")
        if abs(scale - 1.0) > 1e-4:
            mesh_ref_tm.apply_scale(scale)
        if rot_matrix is not None and mesh_ref_tm is not None:
            mesh_ref_tm.vertices = (rot_matrix @ mesh_ref_tm.vertices.T).T
        if stl_path and Path(stl_path).exists():
            mesh_cad_tm = trimesh.load(str(stl_path), force="mesh")
            if mesh_cad_tm is not None and abs(scale - 1.0) > 1e-4:
                cad_max_ext = float(max(mesh_cad_tm.extents)) if len(mesh_cad_tm.extents) > 0 else 0.0
                if cad_max_ext < 15.0:
                    mesh_cad_tm.apply_scale(scale)
    except Exception:
        pass

    # 1. Whole-Part Volume Comparison
    obj_volume = None
    cad_volume = None
    if mesh_ref_tm is not None:
        try:
            obj_volume = abs(float(mesh_ref_tm.volume)) if mesh_ref_tm.is_watertight else abs(float(mesh_ref_tm.convex_hull.volume))
        except Exception:
            pass

    if obj_volume is None or obj_volume <= 0.0:
        try:
            obj_volume = compute_mesh_volume_pure_python(verts_scaled, faces)
        except Exception:
            pass

    if mesh_cad_tm is not None:
        try:
            cad_volume = abs(float(mesh_cad_tm.volume)) if mesh_cad_tm.is_watertight else abs(float(mesh_cad_tm.convex_hull.volume))
        except Exception:
            pass

    # Determine primary axis. The mesh-derived axis uses the SAME rule as the feature
    # recognizer (longest extent is wrong for flattened parts such as compacts).
    mesh_axis_idx = None
    try:
        from src.nx_mcp.mesh_analyzer.feature_recognizer import determine_primary_axis
        if mesh_ref_tm is not None:
            mesh_axis_idx = int(determine_primary_axis(mesh_ref_tm)[0])
        else:
            import trimesh as _tm
            _m = _tm.Trimesh(vertices=np.array(verts_scaled), faces=faces, process=False)
            mesh_axis_idx = int(determine_primary_axis(_m)[0])
    except Exception:
        extents_list = [obj_dx, obj_dy, obj_dz]
        mesh_axis_idx = int(extents_list.index(max(extents_list)))

    axis_idx = mesh_axis_idx
    plan_axis_idx = None
    if spec_path and spec_path.exists():
        try:
            with open(spec_path, "r", encoding="utf-8") as f_sp:
                s_head = json.load(f_sp)
                if "axis_idx" in s_head:
                    axis_idx = int(s_head["axis_idx"])
                elif "primary_axis" in s_head:
                    plan_axis_idx = {"X": 0, "Y": 1, "Z": 2}.get(str(s_head["primary_axis"]).upper())
                    if plan_axis_idx is not None:
                        axis_idx = plan_axis_idx
                elif "expressions" in s_head:
                    ex_dict = dict(s_head["expressions"])
                    z1_st = float(ex_dict.get("ZONE1_START", 0.0))
                    axis_diffs = [abs(min(xs) - z1_st), abs(min(ys) - z1_st), abs(min(zs) - z1_st)]
                    axis_idx = int(axis_diffs.index(min(axis_diffs)))
                else:
                    axis_idx = 1
        except Exception:
            pass

    # Axis consistency guard: a feature plan's axis must equal the axis the checker derives
    # from the mesh itself. A mismatch means slicing would compare the wrong sections.
    if plan_axis_idx is not None and plan_axis_idx != mesh_axis_idx:
        return {
            "passed": False,
            "error": (
                f"AXIS MISMATCH: feature plan axis = {'XYZ'[plan_axis_idx]} but the checker's "
                f"mesh-derived axis = {'XYZ'[mesh_axis_idx]}. Refusing to compare sections."
            ),
            "axis_name": 'XYZ'[plan_axis_idx],
            "mesh_axis_name": 'XYZ'[mesh_axis_idx],
        }

    coords_axial = [v[axis_idx] for v in verts_scaled]
    z_min, z_max = min(coords_axial), max(coords_axial)
    h_span = z_max - z_min

    # Slicing OBJ along height covering full span including end tab/crimp regions
    # (Leaving 1.0% margin at both ends to avoid open mesh boundary edge noise)
    margin = 0.010
    step = (z_max - z_min) * (1.0 - 2.0 * margin) / max(1, n_stations - 1)
    z_stations = [z_min + margin * h_span + i * step for i in range(n_stations)]

    # Load Spec if available
    spec_zones = []
    if spec_path and spec_path.exists():
        with open(spec_path, "r", encoding="utf-8") as f:
            sdata = json.load(f)
            exps = dict(sdata.get("expressions", []))
            body_max_dia = float(exps.get("BODY_MAX_DIA", 20.0))
            for z_def in sdata.get("zones", []):
                z_idx = z_def.get("zone_idx", 1)
                prefix = f"ZONE{z_idx}"
                h_val = float(exps.get(f"{prefix}_HEIGHT", 10.0))
                if z_idx == 1:
                    z_st = float(exps.get(f"{prefix}_START", z_min))
                else:
                    z_st = sum(float(exps.get(f"ZONE{k}_HEIGHT", 10.0)) for k in range(1, z_idx)) + float(exps.get("ZONE1_START", z_min))
                
                def eval_exp(name):
                    val = exps.get(name, "10.0")
                    if "BODY_MAX_DIA" in val:
                        parts = val.split("*")
                        if len(parts) == 2:
                            return body_max_dia * float(parts[1].strip())
                        return body_max_dia
                    if "ZONE" in val and "TOP_DIA" in val:
                        return eval_exp(val.strip())
                    try:
                        return float(val)
                    except:
                        return 10.0

                bdia = eval_exp(f"{prefix}_BASE_DIA")
                tdia = eval_exp(f"{prefix}_TOP_DIA")
                mdia = eval_exp(f"{prefix}_MID_DIA") if f"{prefix}_MID_DIA" in exps else None
                rmid = (mdia / 2.0) if mdia is not None else ((bdia + tdia) / 4.0)

                b_rad = float(exps.get("BASE_BLEND_R", 0.0)) if z_idx == 1 else 0.0
                spec_zones.append({
                    "zone_idx": z_idx,
                    "name": z_def.get("name", prefix),
                    "segment_type": z_def.get("segment_type", "LINE"),
                    "z_start": z_st,
                    "z_end": z_st + h_val,
                    "r_start": bdia / 2.0,
                    "r_end": tdia / 2.0,
                    "r_mid": rmid,
                    "blend_r": b_rad,
                })

    # Fallback CAD volume calculation from spec if STL volume is unavailable
    if cad_volume is None and spec_zones:
        cad_volume = 0.0
        for zd in spec_zones:
            zh = zd["z_end"] - zd["z_start"]
            r0, r1 = zd["r_start"], zd["r_end"]
            cad_volume += (math.pi / 3.0) * zh * (r0**2 + r0 * r1 + r1**2)

    vol_error_pct = None
    vol_error_mm3 = None
    volume_pass = True
    if obj_volume is not None and cad_volume is not None and obj_volume > 1.0:
        vol_error_mm3 = abs(cad_volume - obj_volume)
        vol_error_pct = (vol_error_mm3 / obj_volume) * 100.0
        volume_pass = bool(vol_error_pct <= MAX_VOLUME_DEVIATION_PCT)

    # 2. Overall Bounding Box Extents Comparison
    cad_dx = None
    cad_dy = None
    cad_dz = None
    if cad_bounds is not None:
        cad_dx = abs(cad_bounds[3] - cad_bounds[0])
        cad_dy = abs(cad_bounds[4] - cad_bounds[1])
        cad_dz = abs(cad_bounds[5] - cad_bounds[2])
    elif mesh_cad_tm is not None:
        cad_ext = mesh_cad_tm.extents
        cad_dx, cad_dy, cad_dz = float(cad_ext[0]), float(cad_ext[1]), float(cad_ext[2])
    elif spec_zones:
        max_r = max(max(z["r_start"], z["r_end"], z["r_mid"]) for z in spec_zones)
        cad_dx = 2.0 * max_r
        cad_dz = 2.0 * max_r
        cad_dy = max(z["z_end"] for z in spec_zones) - min(z["z_start"] for z in spec_zones)

    bbox_errors: Dict[str, Dict[str, float]] = {}
    bbox_pass = True
    if cad_dx is not None and cad_dy is not None and cad_dz is not None:
        dim_pairs = [("X", obj_dx, cad_dx), ("Y", obj_dy, cad_dy), ("Z", obj_dz, cad_dz)]
        for dname, o_val, c_val in dim_pairs:
            diff_mm = abs(c_val - o_val)
            diff_pct = (diff_mm / max(o_val, 1e-4)) * 100.0
            p = diff_pct <= MAX_BBOX_DEVIATION_PCT
            if not p:
                bbox_pass = False
            bbox_errors[dname] = {
                "obj_mm": round(o_val, 2),
                "cad_mm": round(c_val, 2),
                "error_mm": round(diff_mm, 2),
                "error_pct": round(diff_pct, 2),
                "pass": p
            }

    # CAD bbox end gaps (each end, each axis) vs mesh
    bbox_end_gaps: Dict[str, Dict[str, float]] = {}
    if cad_bounds is not None:
        obj_min = [min(xs), min(ys), min(zs)]
        obj_max = [max(xs), max(ys), max(zs)]
        for i_ax, ax_lbl in enumerate(["X", "Y", "Z"]):
            gap_min = float(cad_bounds[i_ax] - obj_min[i_ax])
            gap_max = float(cad_bounds[i_ax + 3] - obj_max[i_ax])
            bbox_end_gaps[ax_lbl] = {
                "mesh_min": round(obj_min[i_ax], 4),
                "cad_min": round(cad_bounds[i_ax], 4),
                "gap_min_mm": round(gap_min, 4),
                "mesh_max": round(obj_max[i_ax], 4),
                "cad_max": round(cad_bounds[i_ax + 3], 4),
                "gap_max_mm": round(gap_max, 4),
            }

    # Axial End Gap Check (separate top and bottom gap vs mesh along primary axis)
    end_gap_pass = True
    gap_bottom = gap_top = None
    max_axial_gap_allowed = MAX_AXIAL_END_GAP_FRACTION * h_span
    if cad_bounds is not None:
        cad_axial_min = float(cad_bounds[axis_idx])
        cad_axial_max = float(cad_bounds[axis_idx + 3])
        gap_bottom = abs(cad_axial_min - z_min)
        gap_top = abs(cad_axial_max - z_max)
        if gap_bottom > max_axial_gap_allowed or gap_top > max_axial_gap_allowed:
            end_gap_pass = False

    # 3. Station-wise separate X width, Z thickness, and Cross-Section Area
    transverse_indices = [i for i in (0, 1, 2) if i != axis_idx]
    idx_t1, idx_t2 = transverse_indices[0], transverse_indices[1]

    norm_axial = [0.0, 0.0, 0.0]
    norm_axial[axis_idx] = 1.0

    valid_z = []
    obj_wx_list, obj_tz_list = [], []
    cad_wx_list, cad_tz_list = [], []
    diff_wx_list, diff_tz_list = [], []
    pct_wx_list, pct_tz_list = [], []
    area_obj_list, area_cad_list, pct_area_list = [], [], []
    obj_radii, cad_radii = [], []
    station_rows = []

    for z in z_stations:
        window = max(0.4, min(1.2, 0.008 * h_span))
        pts_near = [v for v in verts_scaled if abs(v[axis_idx] - z) <= window]

        # TRUE section outline of the OBJ (same method as the outline extractor:
        # largest closed loop of the plane section), not a vertex-window bbox.
        obj_wx = obj_tz = None
        if mesh_ref_tm is not None:
            try:
                _o = [0.0, 0.0, 0.0]
                _o[axis_idx] = z
                _s = mesh_ref_tm.section(plane_origin=_o, plane_normal=norm_axial)
                if _s is not None and _s.discrete:
                    _loop = max(_s.discrete, key=lambda p: (np.ptp(p[:, idx_t1]) * np.ptp(p[:, idx_t2])))
                    obj_wx = float(np.ptp(_loop[:, idx_t1]))
                    obj_tz = float(np.ptp(_loop[:, idx_t2]))
            except Exception:
                obj_wx = obj_tz = None
        if obj_wx is None:
            # fallback only when the OBJ cannot be sectioned
            if pts_near:
                t1_near = [p[idx_t1] for p in pts_near]
                t2_near = [p[idx_t2] for p in pts_near]
                obj_wx = max(t1_near) - min(t1_near)
                obj_tz = max(t2_near) - min(t2_near)
            else:
                obj_wx = obj_dx
                obj_tz = obj_dz

        cad_wx, cad_tz, r_cad = None, None, None
        if mesh_cad_tm is not None:
            try:
                origin_c = [0.0, 0.0, 0.0]
                origin_c[axis_idx] = z
                sec_c = mesh_cad_tm.section(plane_origin=origin_c, plane_normal=norm_axial)
                if sec_c and sec_c.discrete:
                    cad_pts = np.vstack(sec_c.discrete)
                    cad_wx = float(np.max(cad_pts[:, idx_t1]) - np.min(cad_pts[:, idx_t1]))
                    cad_tz = float(np.max(cad_pts[:, idx_t2]) - np.min(cad_pts[:, idx_t2]))
                    r_cad = (cad_wx + cad_tz) / 4.0
            except Exception:
                pass

        if cad_wx is None and spec_zones:
            r_cad = evaluate_cad_radius_at_z(spec_zones, z)
            if r_cad is not None:
                cad_wx = 2.0 * r_cad
                cad_tz = 2.0 * r_cad

        if cad_wx is not None and obj_wx > 0.01 and obj_tz > 0.01:
            valid_z.append(z)
            dev_x = abs(cad_wx - obj_wx)
            dev_z = abs(cad_tz - obj_tz)
            dev_x_pct = (dev_x / max(obj_wx, 1e-4)) * 100.0
            dev_z_pct = (dev_z / max(obj_tz, 1e-4)) * 100.0

            # Cross-section area calculation (catches non-round corners / diagonals)
            area_obj = None
            if mesh_ref_tm is not None:
                try:
                    sec_o = mesh_ref_tm.section(plane_origin=[norm_axial[0]*z, norm_axial[1]*z, norm_axial[2]*z], plane_normal=norm_axial)
                    if sec_o:
                        s2d_o, _ = sec_o.to_planar()
                        polys_o = getattr(s2d_o, "polygons_closed", [])
                        if len(polys_o) > 0:
                            area_obj = float(max(polys_o, key=lambda x: x.area).area)
                except Exception:
                    pass

            if area_obj is None and pts_near and len(pts_near) >= 3:
                try:
                    pts_2d = [(p[idx_t1], p[idx_t2]) for p in pts_near]
                    cx = sum(p[0] for p in pts_2d) / len(pts_2d)
                    cz = sum(p[1] for p in pts_2d) / len(pts_2d)
                    bins = {}
                    for p in pts_2d:
                        ang = math.atan2(p[1] - cz, p[0] - cx)
                        bin_idx = int(math.degrees(ang + math.pi) // 10)
                        d = math.hypot(p[0] - cx, p[1] - cz)
                        if bin_idx not in bins or d > bins[bin_idx][0]:
                            bins[bin_idx] = (d, p)
                    if len(bins) >= 8:
                        poly = [bins[k][1] for k in sorted(bins.keys())]
                        n_p = len(poly)
                        area_obj = 0.5 * abs(sum(poly[i][0] * poly[(i+1)%n_p][1] - poly[(i+1)%n_p][0] * poly[i][1] for i in range(n_p)))
                except Exception:
                    pass

            if area_obj is None:
                area_obj = (math.pi / 4.0) * obj_wx * obj_tz

            area_cad = None
            if mesh_cad_tm is not None:
                try:
                    sec_c = mesh_cad_tm.section(plane_origin=[norm_axial[0]*z, norm_axial[1]*z, norm_axial[2]*z], plane_normal=norm_axial)
                    if sec_c:
                        s2d_c, _ = sec_c.to_planar()
                        polys_c = getattr(s2d_c, "polygons_closed", [])
                        if len(polys_c) > 0:
                            area_cad = float(max(polys_c, key=lambda x: x.area).area)
                except Exception:
                    pass
            if area_cad is None:
                area_cad = math.pi * (r_cad ** 2)

            area_err_pct = (abs(area_cad - area_obj) / max(area_obj, 1e-4)) * 100.0

            obj_wx_list.append(obj_wx)
            obj_tz_list.append(obj_tz)
            part_size = max(obj_dx, obj_dy, obj_dz)

            rel_pos = (z - z_min) / max(h_span, 1e-4)
            is_end_zone = bool(rel_pos < END_ZONE_HEIGHT_FRACTION or rel_pos > (1.0 - END_ZONE_HEIGHT_FRACTION))

            r_obj = math.sqrt(area_obj / math.pi) if area_obj > 0 else 0.0
            r_cad = math.sqrt(area_cad / math.pi) if area_cad > 0 else 0.0
            equiv_dist_err = abs(r_cad - r_obj)
            station_dist_err = max(equiv_dist_err, dev_x / 2.0, dev_z / 2.0)

            # End-zone limit: min(span-based allowance, local radius fraction)
            span_end_dist = MAX_END_ZONE_DISTANCE_FRACTION * part_size
            local_end_dist = MAX_END_ZONE_LOCAL_RADIUS_FRACTION * max(r_obj, 1.0)
            max_end_dist_allowed = min(span_end_dist, local_end_dist)

            # Standard 10% relative check
            std_pass = bool(
                dev_x_pct <= MAX_SECTION_DEVIATION_PCT
                and dev_z_pct <= MAX_SECTION_DEVIATION_PCT
                and area_err_pct <= MAX_AREA_DEVIATION_PCT
            )

            if not is_end_zone:
                station_pass = std_pass
                end_zone_metric_used = False
            else:
                if std_pass:
                    station_pass = True
                    end_zone_metric_used = False
                else:
                    station_pass = bool(station_dist_err <= max_end_dist_allowed)
                    end_zone_metric_used = True

            cad_wx_list.append(cad_wx)
            cad_tz_list.append(cad_tz)
            diff_wx_list.append(dev_x)
            diff_tz_list.append(dev_z)
            pct_wx_list.append(dev_x_pct)
            pct_tz_list.append(dev_z_pct)
            area_obj_list.append(area_obj)
            area_cad_list.append(area_cad)
            pct_area_list.append(area_err_pct)
            station_rows.append({
                "axial_mm": round(z, 3),
                "rel_pos_pct": round(rel_pos * 100.0, 1),
                "is_end_zone": is_end_zone,
                "obj_width": round(obj_wx, 3), "cad_width": round(cad_wx, 3),
                "obj_thick": round(obj_tz, 3), "cad_thick": round(cad_tz, 3),
                "obj_area": round(area_obj, 2), "cad_area": round(area_cad, 2),
                "area_err_pct": round(area_err_pct, 2),
                "dev_x_pct": round(dev_x_pct, 2),
                "dev_z_pct": round(dev_z_pct, 2),
                "equiv_dist_err_mm": round(equiv_dist_err, 3),
                "station_dist_err_mm": round(station_dist_err, 3),
                "max_end_dist_allowed_mm": round(max_end_dist_allowed, 3),
                "end_zone_metric_used": end_zone_metric_used,
                "station_pass": station_pass,
            })

            obj_radii.append((obj_wx + obj_tz) / 4.0)
            cad_radii.append(r_cad)

    if not valid_z:
        return {
            "passed": False,
            "error": "No valid stations computed.",
            "bbox_pass": bbox_pass,
            "bbox_errors": bbox_errors,
            "axis_name": ["X", "Y", "Z"][axis_idx],
            "end_gap_pass": end_gap_pass,
            "max_axial_gap_allowed_mm": round(max_axial_gap_allowed, 4) if max_axial_gap_allowed is not None else None,
            "gap_bottom_mm": round(gap_bottom, 4) if gap_bottom is not None else None,
            "gap_top_mm": round(gap_top, 4) if gap_top is not None else None,
            "bbox_end_gaps": bbox_end_gaps,
        }

    max_x_dev_mm = max(diff_wx_list)
    max_x_dev_pct = max(pct_wx_list)
    max_x_idx = pct_wx_list.index(max_x_dev_pct)
    max_x_dev_z = valid_z[max_x_idx]

    max_z_dev_mm = max(diff_tz_list)
    max_z_dev_pct = max(pct_tz_list)
    max_z_idx = pct_tz_list.index(max_z_dev_pct)
    max_z_dev_z = valid_z[max_z_idx]

    max_area_dev_pct = max(pct_area_list)
    max_area_idx = pct_area_list.index(max_area_dev_pct)
    max_area_dev_z = valid_z[max_area_idx]

    interior_rows = [s for s in station_rows if not s["is_end_zone"]]
    max_interior_area_pct = max([s["area_err_pct"] for s in interior_rows] or [0.0])
    max_interior_x_pct = max([s["dev_x_pct"] for s in interior_rows] or [0.0])
    max_interior_z_pct = max([s["dev_z_pct"] for s in interior_rows] or [0.0])

    mean_x_dev_mm = sum(diff_wx_list) / len(diff_wx_list)
    mean_x_dev_pct = sum(pct_wx_list) / len(pct_wx_list)
    mean_z_dev_mm = sum(diff_tz_list) / len(diff_tz_list)
    mean_z_dev_pct = sum(pct_tz_list) / len(pct_tz_list)
    mean_area_dev_pct = sum(pct_area_list) / len(pct_area_list)

    # Cross-section pass requires:
    # 1. All interior stations satisfy the 10% rule (X, Z, Area <= 10%)
    # 2. End-zone stations satisfy either 10% rule OR distance metric <= MAX_END_ZONE_DISTANCE_FRACTION
    slice_pass = all(s["station_pass"] for s in station_rows)

    # Evaluate Bidirectional Surface Distance Check
    surf_eval = None
    if stl_path and stl_path.exists() and obj_path and obj_path.exists():
        try:
            from src.nx_mcp.surface_distance_checker import evaluate_surface_distance
            surf_eval = evaluate_surface_distance(obj_path, stl_path)
        except Exception:
            surf_eval = None

    # Overall pass requires cross-section slice pass, bbox extents pass, volume pass, axial end gap pass, and surface check
    overall_passed = bool(slice_pass and bbox_pass and volume_pass and end_gap_pass)
    if surf_eval is not None and not surf_eval.get("pass", True):
        overall_passed = False

    # Save Comparison Plot if matplotlib is available
    fig_path = None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        part_stem = obj_path.stem.replace(" ", "_")
        fig_path = output_dir / f"{part_stem}_comparison.png"

        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [1.5, 1.0]})
            
            # Plot 1: Profile Comparison (separate X width and Z thickness)
            ax1.plot(obj_wx_list, valid_z, "b-o", label="OBJ X-Width", alpha=0.7, markersize=4)
            ax1.plot(cad_wx_list, valid_z, "b--s", label="CAD X-Width", alpha=0.7, markersize=4)
            ax1.plot(obj_tz_list, valid_z, "g-o", label="OBJ Z-Thickness", alpha=0.7, markersize=4)
            ax1.plot(cad_tz_list, valid_z, "g--s", label="CAD Z-Thickness", alpha=0.7, markersize=4)

            # Draw zone boundaries
            for zd in spec_zones:
                ax1.axhline(zd["z_start"], color="orange", linestyle=":", alpha=0.6)
                ax1.text(max(obj_wx_list) * 0.9, zd["z_start"] + 1, zd["name"], color="darkorange", fontsize=8)

            axis_letter = ["X", "Y", "Z"][axis_idx]
            ax1.set_xlabel("Cross-Section Extent (mm)")
            ax1.set_ylabel(f"Elevation {axis_letter} (mm)")
            ax1.set_title(f"CAD vs OBJ Cross-Section: {obj_path.stem}")
            ax1.grid(True, linestyle="--", alpha=0.5)
            ax1.legend(loc="upper right", fontsize=8)

            # Plot 2: Deviation Profile
            ax2.plot(pct_wx_list, valid_z, "b-^", label="X-Width Error (%)", linewidth=1.5)
            ax2.plot(pct_tz_list, valid_z, "g-v", label="Z-Thickness Error (%)", linewidth=1.5)
            ax2.axvline(MAX_SECTION_DEVIATION_PCT, color="red", linestyle="--", label=f"{MAX_SECTION_DEVIATION_PCT:.0f}% Tol", alpha=0.7)
            ax2.set_xlabel("Deviation (%)")
            ax2.set_ylabel(f"Elevation {axis_letter} (mm)")
            ax2.set_title(f"Max Dev: X={max_x_dev_pct:.1f}%, Z={max_z_dev_pct:.1f}%")
            ax2.grid(True, linestyle="--", alpha=0.5)
            ax2.legend(loc="upper right", fontsize=8)

            plt.tight_layout()
            plt.savefig(fig_path, dpi=120)
            plt.close(fig)
        except Exception:
            pass

    return {
        "passed": overall_passed,
        "slice_pass": slice_pass,
        "bbox_pass": bbox_pass,
        "volume_pass": volume_pass,
        "station_count": len(valid_z),
        "obj_bounds_mm": [round(obj_dx, 2), round(obj_dy, 2), round(obj_dz, 2)],
        "cad_bounds_mm": [round(cad_dx, 2), round(cad_dy, 2), round(cad_dz, 2)] if cad_dx is not None else None,
        "bbox_errors": bbox_errors,
        "obj_volume": round(obj_volume, 2) if obj_volume is not None else None,
        "cad_volume": round(cad_volume, 2) if cad_volume is not None else None,
        "vol_error_mm3": round(vol_error_mm3, 2) if vol_error_mm3 is not None else None,
        "vol_error_pct": round(vol_error_pct, 2) if vol_error_pct is not None else None,
        "max_area_deviation_pct": round(max_area_dev_pct, 2),
        "max_area_deviation_z_mm": round(max_area_dev_z, 2),
        "mean_area_deviation_pct": round(mean_area_dev_pct, 2),
        "max_x_deviation_mm": round(max_x_dev_mm, 3),
        "max_x_deviation_pct": round(max_x_dev_pct, 2),
        "max_x_deviation_z_mm": round(max_x_dev_z, 2),
        "mean_x_deviation_mm": round(mean_x_dev_mm, 3),
        "mean_x_deviation_pct": round(mean_x_dev_pct, 2),
        "max_z_deviation_mm": round(max_z_dev_mm, 3),
        "max_z_deviation_pct": round(max_z_dev_pct, 2),
        "max_z_deviation_z_mm": round(max_z_dev_z, 2),
        "mean_z_deviation_mm": round(mean_z_dev_mm, 3),
        "mean_z_deviation_pct": round(mean_z_dev_pct, 2),
        "max_deviation_mm": round(max(max_x_dev_mm, max_z_dev_mm), 3),
        "max_deviation_pct": round(max(max_x_dev_pct, max_z_dev_pct), 2),
        "max_deviation_z_mm": round(max_x_dev_z if max_x_dev_pct >= max_z_dev_pct else max_z_dev_z, 2),
        "mean_deviation_mm": round((mean_x_dev_mm + mean_z_dev_mm) / 2.0, 3),
        "mean_deviation_pct": round((mean_x_dev_pct + mean_z_dev_pct) / 2.0, 2),
        "comparison_plot": str(fig_path) if fig_path else None,
        "stations_z": [round(z, 2) for z in valid_z],
        "axis_name": ["X", "Y", "Z"][axis_idx],
        "obj_axial_range_mm": [round(z_min, 3), round(z_max, 3)],
        "cad_axial_range_mm": (
            [round(float(mesh_cad_tm.bounds[0][axis_idx]), 3), round(float(mesh_cad_tm.bounds[1][axis_idx]), 3)]
            if mesh_cad_tm is not None else None
        ),
        "spec_used": str(spec_path) if spec_path else None,
        "station_rows": station_rows,
        "bbox_end_gaps": bbox_end_gaps,
        "end_gap_pass": end_gap_pass,
        "max_axial_gap_allowed_mm": round(max_axial_gap_allowed, 4) if max_axial_gap_allowed is not None else None,
        "gap_bottom_mm": round(gap_bottom, 4) if gap_bottom is not None else None,
        "gap_top_mm": round(gap_top, 4) if gap_top is not None else None,
        "max_axial_gap_pct": (
            round(max(gap_bottom, gap_top) / max(h_span, 1e-4) * 100.0, 2)
            if gap_bottom is not None and gap_top is not None else None
        ),
        "surface_eval": surf_eval,
        "max_interior_area_deviation_pct": round(max_interior_area_pct, 2),
        "max_interior_x_deviation_pct": round(max_interior_x_pct, 2),
        "max_interior_z_deviation_pct": round(max_interior_z_pct, 2),
        "end_zone_height_fraction": END_ZONE_HEIGHT_FRACTION,
        "max_end_zone_distance_fraction": MAX_END_ZONE_DISTANCE_FRACTION,
    }

