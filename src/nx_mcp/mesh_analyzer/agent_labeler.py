"""
agent_labeler.py
================
Module for integrating direct agent visual inspection findings with 3D mesh
analysis. Combines visual observations of product features, proportions, steps,
rings, and components to correct, label, and group CAD zones without requiring
external SDKs.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_ROLES = {
    "BASE", "BODY", "BARREL", "COLLAR", "NECK", "CAP", "CLOSURE",
    "SHOULDER", "WAND", "TIP", "LID", "NOZZLE", "GROOVE", "THREAD",
    "PEDESTAL", "TRANSITION", "FLANGE", "DOME", "WAIST", "LIP"
}


def resolve_visual_analysis_path(
    obj_name: str,
    image_path: Optional[Path],
    explicit_path: Optional[Path] = None
) -> Optional[Path]:
    """
    Locates the visual inspection JSON containing the agent's image observations.
    Checks explicit path, output/<stem>_visual.json, and <stem>_visual.json.
    """
    if explicit_path:
        cand = Path(explicit_path)
        if cand.exists():
            return cand
        return None

    candidates: List[Path] = []
    base_stems = []
    if image_path:
        base_stems.append(image_path.stem)
    base_stems.append(obj_name)

    for stem in base_stems:
        candidates.extend([
            Path("output") / f"{stem}_visual.json",
            Path(f"{stem}_visual.json"),
            Path("img") / f"{stem}_visual.json",
        ])

    for cand in candidates:
        if cand.exists():
            return cand

    return None


def load_and_validate_visual_analysis(
    visual_path: Path,
    zones: Optional[List[Dict[str, Any]]] = None,
    expected_image: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Loads and validates the visual inspection JSON.
    Extracts high-level CAD design directives:
      - split_points: list of height fractions [0.0..1.0] from base to crown
      - groove: position/height/depth fractions relative to total height and radius
      - ribs: target part, count, height/depth fractions
      - edge_style: chamfer vs fillet for base/crown
    Maintains compatibility with legacy zone_labels and visual observations.
    """
    if not visual_path.exists():
        return None, f"Visual analysis file not found: {visual_path}"

    try:
        with open(visual_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return None, f"Failed to parse visual analysis JSON: {e}"

    # Verify image match if specified
    if expected_image:
        recorded_img = Path(data.get("image_file", "")).name.lower()
        exp_name = expected_image.name.lower()
        if recorded_img and recorded_img != exp_name and recorded_img.split(".")[0] != exp_name.split(".")[0]:
            return None, f"Visual analysis file '{visual_path.name}' is for '{recorded_img}', but requested image is '{expected_image.name}'"

    raw_labels = data.get("zone_labels", [])
    validated_labels = []
    if isinstance(raw_labels, list):
        for idx, item in enumerate(raw_labels, start=1):
            role_raw = str(item.get("role", "BODY")).upper().strip()
            role = role_raw if role_raw in ALLOWED_ROLES else "BODY"
            name_raw = str(item.get("name", role)).upper().strip()
            name = name_raw if name_raw else role
            group = str(item.get("suggested_group", "BODY")).upper().strip()

            validated_labels.append({
                "zone_idx": idx,
                "role": role,
                "name": name,
                "suggested_group": group,
                "notes": str(item.get("notes", "")),
            })

    # Extract or infer normalized visual directives (proportions/fractions, never hardcoded mm)
    directives_raw = data.get("directives", {})
    if not isinstance(directives_raw, dict):
        directives_raw = {}

    # 1. split_points
    split_points = directives_raw.get("split_points")
    if split_points is None:
        split_points = data.get("split_points", [])
    if isinstance(split_points, (int, float)):
        split_points = [float(split_points)]
    split_points = [float(sp) for sp in split_points if 0.0 < float(sp) < 1.0]

    # 2. groove
    groove_raw = directives_raw.get("groove", data.get("groove"))
    groove = None
    if isinstance(groove_raw, dict):
        groove = {
            "enabled": bool(groove_raw.get("enabled", True)),
            "position_ratio": float(groove_raw.get("position_ratio", 0.5)),
            "height_ratio": float(groove_raw.get("height_ratio", 0.02)),
            "depth_ratio": float(groove_raw.get("depth_ratio", 0.04)),
            "name": str(groove_raw.get("name", "PARTING_GROOVE")),
        }

    # 3. ribs
    ribs_raw = directives_raw.get("ribs", data.get("ribs"))
    ribs = None
    if isinstance(ribs_raw, dict):
        ribs = {
            "enabled": bool(ribs_raw.get("enabled", True)),
            "target_part": str(ribs_raw.get("target_part", "CAP")).upper(),
            "count": int(ribs_raw.get("count", 36)),
            "position_ratio": float(ribs_raw.get("position_ratio", 0.70)),
            "height_ratio": float(ribs_raw.get("height_ratio", 0.25)),
            "depth_ratio": float(ribs_raw.get("depth_ratio", 0.03)),
            "cutter_dia_ratio": float(ribs_raw.get("cutter_dia_ratio", 0.08)),
        }

    # 4. edge_style
    edge_style_raw = directives_raw.get("edge_style", data.get("edge_style", {}))
    if not isinstance(edge_style_raw, dict):
        edge_style_raw = {}
    edge_style = {
        "base": str(edge_style_raw.get("base", "fillet")).lower(),
        "crown": str(edge_style_raw.get("crown", "fillet")).lower(),
    }

    validated_directives = {
        "split_points": sorted(split_points),
        "groove": groove,
        "ribs": ribs,
        "edge_style": edge_style,
    }

    validated_data = {
        "product_type": str(data.get("product_type", "object")),
        "image_file": str(data.get("image_file", "")),
        "visual_observations": data.get("visual_observations", []),
        "corrections_applied": data.get("corrections_applied", []),
        "directives": validated_directives,
        "zone_labels": validated_labels,
        "suggested_groupings": data.get("suggested_groupings", {}),
        "notes": str(data.get("notes", "")),
    }

    return validated_data, "success"


def apply_visual_analysis_to_zones(
    zones: List[Dict[str, Any]],
    visual_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extracts and returns CAD feature directives from the visual analysis.
    Also updates names and roles for any 1-to-1 matching zones.
    """
    labels = visual_data.get("zone_labels", [])
    if len(labels) == len(zones):
        for z, lbl in zip(zones, labels):
            z["name"] = lbl["name"]
            z["role"] = lbl["role"]
            if "suggested_group" in lbl:
                z["suggested_group"] = lbl["suggested_group"]

    directives = visual_data.get("directives", {})
    return directives


def merge_visual_directives_with_mesh_zones(
    zones: List[Dict[str, Any]],
    directives: Dict[str, Any],
    total_height: float,
    z_min: float,
    max_dia: float,
    profile: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Dict[str, str]]:
    """
    Merge Step:
    Converts normalized fractions (from visual inspection) to absolute mm using
    the 3D mesh dimensions (the immutable source of truth for scale).
    
    1. Splits large monolithic zones along split_points fractions.
    2. Computes parametric groove feature dimensions and runs sanity check against mesh.
    3. Computes parametric rib circular pattern dimensions.
    4. Formulates edge styles (chamfer vs fillet).
    """
    import copy
    refined_zones = copy.deepcopy(zones)
    r_max = max_dia / 2.0

    split_points = directives.get("split_points", [])
    groove_dir = directives.get("groove")
    ribs_dir = directives.get("ribs")
    edge_style = directives.get("edge_style", {"base": "fillet", "crown": "fillet"})

    # 1. ZONE SPLITTING
    # If the mesh analyzer lumped a large section into one zone, split it based on split_points
    for sp in split_points:
        z_target = z_min + sp * total_height
        for i, z in enumerate(refined_zones):
            z_s = z["z_start"]
            z_e = z["z_end"]
            # Split if target falls inside zone with at least 3mm buffer on each side
            if (z_s + 3.0) < z_target < (z_e - 3.0):
                h1 = round(z_target - z_s, 3)
                h2 = round(z_e - z_target, 3)
                
                # Interpolate radius at split elevation (using actual mesh profile when available)
                t = (z_target - z_s) / max(z_e - z_s, 1e-4)
                r_split = round(z["r_start"] + t * (z["r_end"] - z["r_start"]), 3)
                r_mid_lo = round((z["r_start"] + r_split) / 2.0, 3)
                r_mid_hi = round((r_split + z["r_end"]) / 2.0, 3)
                if profile and profile.get("stations"):
                    st_list = profile["stations"]
                    st_split = min(st_list, key=lambda s: abs(s["z"] - z_target))
                    r_split = round(float(st_split["radius"]), 3)
                    z_mid_lo = (z_s + z_target) / 2.0
                    z_mid_hi = (z_target + z_e) / 2.0
                    r_mid_lo = round(float(min(st_list, key=lambda s: abs(s["z"] - z_mid_lo))["radius"]), 3)
                    r_mid_hi = round(float(min(st_list, key=lambda s: abs(s["z"] - z_mid_hi))["radius"]), 3)
                
                orig_name = z["name"]
                orig_role = z["role"]

                lower_zone = {
                    "zone_idx": z["zone_idx"],
                    "name": f"{orig_name}_LOWER" if "LOWER" not in orig_name else orig_name,
                    "role": orig_role,
                    "segment_type": z.get("segment_type", "LINE"),
                    "z_start": z_s,
                    "z_end": z_target,
                    "height": h1,
                    "r_start": z["r_start"],
                    "r_end": r_split,
                    "r_mid": r_mid_lo,
                    "dia_start": round(z["r_start"] * 2.0, 3),
                    "dia_end": round(r_split * 2.0, 3),
                    "dia_max": round(max(z["r_start"], r_split, r_mid_lo) * 2.0, 3),
                }

                upper_zone = {
                    "zone_idx": z["zone_idx"] + 1,
                    "name": f"{orig_name}_UPPER" if "UPPER" not in orig_name else f"{orig_name}_2",
                    "role": orig_role,
                    "segment_type": z.get("segment_type", "LINE"),
                    "z_start": z_target,
                    "z_end": z_e,
                    "height": h2,
                    "r_start": r_split,
                    "r_end": z["r_end"],
                    "r_mid": r_mid_hi,
                    "dia_start": round(r_split * 2.0, 3),
                    "dia_end": round(z["r_end"] * 2.0, 3),
                    "dia_max": round(max(r_split, z["r_end"], r_mid_hi) * 2.0, 3),
                }

                refined_zones = refined_zones[:i] + [lower_zone, upper_zone] + refined_zones[i+1:]
                # Re-index zones
                for new_idx, rz in enumerate(refined_zones, start=1):
                    rz["zone_idx"] = new_idx
                print(f"  [MERGE SPLIT] Split {orig_name} at Y={z_target:.2f} mm into {lower_zone['name']} (H={h1:.1f}mm) and {upper_zone['name']} (H={h2:.1f}mm)")
                break

    # 2. GROOVE SPECIFICATION
    groove_spec = None
    if groove_dir and groove_dir.get("enabled", True):
        pos_ratio = groove_dir.get("position_ratio", 0.5)
        h_ratio = groove_dir.get("height_ratio", 0.02)
        d_ratio = groove_dir.get("depth_ratio", 0.04)

        y_center = z_min + pos_ratio * total_height
        h_groove = max(1.0, round(h_ratio * total_height, 3))
        y_start = round(y_center - h_groove / 2.0, 3)

        # Find nominal radius at y_center from mesh profile or zones
        nom_r = r_max
        for z in refined_zones:
            if z["z_start"] <= y_center <= z["z_end"]:
                t = (y_center - z["z_start"]) / max(z["height"], 1e-4)
                nom_r = z["r_start"] + t * (z["r_end"] - z["r_start"])
                break

        depth = max(0.2, round(nom_r * d_ratio, 3))
        groove_r = round(nom_r - depth, 3)

        # Sanity check against mesh
        print(f"  [SANITY CHECK] Visual directive specified GROOVE at Y={y_center:.2f} mm (H={h_groove:.2f} mm, Depth={depth:.2f} mm).")
        print(f"                 Mesh nominal radius R={nom_r:.2f} mm -> Recessed Groove R={groove_r:.2f} mm.")

        groove_spec = {
            "enabled": True,
            "name": groove_dir.get("name", "PARTING_GROOVE"),
            "y_start": y_start,
            "y_center": y_center,
            "height": h_groove,
            "depth": depth,
            "nominal_r": round(nom_r, 3),
            "groove_r": groove_r,
            "groove_dia": round(groove_r * 2.0, 3),
        }

    # 3. RIBS SPECIFICATION
    ribs_spec = None
    if ribs_dir and ribs_dir.get("enabled", True):
        count = int(ribs_dir.get("count", 36))
        pos_ratio = ribs_dir.get("position_ratio", 0.70)
        h_ratio = ribs_dir.get("height_ratio", 0.25)
        d_ratio = ribs_dir.get("depth_ratio", 0.03)
        c_dia_ratio = ribs_dir.get("cutter_dia_ratio", 0.08)

        target_y = round(z_min + pos_ratio * total_height, 3)
        target_role = str(ribs_dir.get("target_part", "CAP")).upper()

        # Step A: Identify spatial zone encompassing target_y
        spatial_zone = None
        for z in refined_zones:
            if z["z_start"] <= target_y <= z["z_end"]:
                spatial_zone = z
                break

        # Step B: Identify candidate zones matching target_role
        matching_zones = [
            z for z in refined_zones
            if target_role in z.get("role", "").upper() or target_role in z.get("name", "").upper()
        ]

        if matching_zones:
            if spatial_zone in matching_zones:
                tz = spatial_zone
            else:
                # Select candidate zone whose elevation centroid is closest to target_y
                tz = min(matching_zones, key=lambda z: abs((z["z_start"] + z["z_end"]) / 2.0 - target_y))
        else:
            tz = spatial_zone if spatial_zone else refined_zones[-1]

        # Step C: Anchor y_start and height within the selected zone tz
        max_h = max(1.0, round(tz["height"] - 2.0, 3))
        h_ribs = max(1.0, min(round(h_ratio * total_height, 3), max_h))

        if tz["z_start"] <= target_y <= (tz["z_end"] - h_ribs):
            y_start = target_y
        else:
            y_start = round(tz["z_start"] + max(0.5, (tz["height"] - h_ribs) / 2.0), 3)

        # Step D: Interpolate target_r at rib mid-height within tz
        y_mid = y_start + h_ribs / 2.0
        t = (y_mid - tz["z_start"]) / max(tz["height"], 1e-4)
        t = max(0.0, min(1.0, t))
        target_r = round(tz["r_start"] + t * (tz["r_end"] - tz["r_start"]), 3)

        depth = max(0.15, round(target_r * d_ratio, 3))
        cutter_dia = max(0.5, round(target_r * c_dia_ratio, 3))

        print(f"  [SANITY CHECK] Visual directive specified {count} RIBS on {tz['name']} ({tz['role']}) at Y={y_start:.2f} mm (H={h_ribs:.2f} mm, Cutter Dia={cutter_dia:.2f} mm).")

        ribs_spec = {
            "enabled": True,
            "target": tz.get("role", ribs_dir.get("target_part", "CAP")),
            "target_zone": tz.get("name"),
            "count": count,
            "y_start": y_start,
            "height": h_ribs,
            "depth": depth,
            "cutter_dia": cutter_dia,
            "target_r": round(target_r, 3),
        }

    return refined_zones, groove_spec, ribs_spec, edge_style


# Compatibility aliases
apply_agent_labels_to_zones = apply_visual_analysis_to_zones
