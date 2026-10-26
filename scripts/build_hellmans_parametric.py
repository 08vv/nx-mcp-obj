"""
build_hellmans_parametric.py
============================
Constructs a 100% parametric, feature-based Siemens NX CAD model for the
Hellmann's Mayonnaise Jar (obj/Hellmans_reduced.obj).

Architecture:
  1. Fully Chained Parametric Expressions (0 orphans)
  2. Zone 1: Base Foot Ring & Chamfer (Cone + Associative Base Blend)
  3. Zone 2: Main Jar Body (Cylinder + Unite)
  4. Zone 3: Lower & Upper Label Bumper Ridges (Cylinders + Unites)
  5. Zone 4: Shoulder Transition (Cone + Unite + Associative Shoulder Blend)
  6. Zone 5: Neck & Collar Ring (Cylinder + Unite)
  7. Zone 6: Cap / Lid Body (Cylinder + Unite + Top Face Blend)
  8. Zone 7: Cap Knurled Grip Flutes (Subtractive Array + Expressions)

Usage:
  run_journal.exe scripts/build_hellmans_parametric.py -args [output_prt]
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from src.nx_mcp.parametric_helpers import (
    setup_nx_license,
    populate_expressions,
    create_cylinder,
    create_cone,
    boolean_unite,
    boolean_subtract,
    create_associative_blend_by_face,
    create_scalar_point,
    create_direction,
    set_feature_name,
)
setup_nx_license()

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF

UF = NXOpen.UF.UFSession.GetUFSession()


def get_dir_z(part):
    return part.Directions.CreateDirection(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling
    )


def export_stl(session, part, main_body, out_stl_path: Path):
    print(f"\nExporting STL: {out_stl_path}")
    if out_stl_path.exists():
        try:
            out_stl_path.unlink()
        except Exception:
            pass

    stl_exp = session.DexManager.CreateStlCreator()
    try:
        stl_exp.OutputFile = str(out_stl_path)
        stl_exp.ExportSelectionBlock.Add(main_body)
        stl_exp.Commit()
        print(f"  [OK] STL exported successfully: {out_stl_path} ({out_stl_path.stat().st_size:,} bytes)")
    except Exception as e:
        print(f"  [ERROR] STL export failed: {e}")
    finally:
        stl_exp.Destroy()


def main():
    default_prt = repo_root / "Hellmans_mayonnaise_jar.prt"
    out_prt = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and sys.argv[1].endswith(".prt") else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: HELLMANN'S MAYONNAISE JAR")
    print("  FEATURE-BASED MULTI-ZONE ARCHITECTURE")
    print(f"  Target PRT: {out_prt}")
    print("=" * 75)

    if out_prt.exists():
        try:
            out_prt.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(out_prt), NXOpen.Part.Units.Millimeters)

    # =========================================================================
    # 1. DRIVING PARAMETRIC EXPRESSIONS (CHAINED, ZERO ORPHANS)
    # =========================================================================
    print("\n[1/6] Creating driving expressions...")
    exp_defs = [
        # Zone 1: Base Foot Ring & Chamfer
        ("BASE_START_Z", "0.0"),
        ("BASE_HEIGHT", "12.0"),
        ("BASE_BOTTOM_DIA", "96.0"),
        ("BASE_TOP_DIA", "133.6"),
        ("BASE_BOTTOM_BLEND_R", "3.5"),
        ("BASE_END_Z", "BASE_START_Z + BASE_HEIGHT"),

        # Zone 2: Main Body
        ("BODY_START_Z", "BASE_END_Z"),
        ("BODY_HEIGHT", "126.0"),
        ("BODY_DIA", "133.6"),
        ("BODY_END_Z", "BODY_START_Z + BODY_HEIGHT"),

        # Zone 3: Lower & Upper Label Ridges
        ("LOWER_RIDGE_OFFSET", "15.0"),
        ("LOWER_RIDGE_Z", "BODY_START_Z + LOWER_RIDGE_OFFSET"),
        ("LOWER_RIDGE_HEIGHT", "4.0"),
        ("LOWER_RIDGE_DIA", "134.4"),

        ("UPPER_RIDGE_OFFSET", "112.0"),
        ("UPPER_RIDGE_Z", "BODY_START_Z + UPPER_RIDGE_OFFSET"),
        ("UPPER_RIDGE_HEIGHT", "4.0"),
        ("UPPER_RIDGE_DIA", "134.4"),

        # Zone 4: Shoulder Transition
        ("SHOULDER_START_Z", "BODY_END_Z"),
        ("SHOULDER_HEIGHT", "33.0"),
        ("SHOULDER_BASE_DIA", "BODY_DIA"),
        ("SHOULDER_TOP_DIA", "101.6"),
        ("SHOULDER_BLEND_R", "2.5"),
        ("SHOULDER_END_Z", "SHOULDER_START_Z + SHOULDER_HEIGHT"),

        # Zone 5: Neck & Collar Bead
        ("NECK_START_Z", "SHOULDER_END_Z"),
        ("NECK_HEIGHT", "4.5"),
        ("NECK_DIA", "101.6"),
        ("NECK_END_Z", "NECK_START_Z + NECK_HEIGHT"),

        # Zone 6: Cap / Lid Body
        ("CAP_START_Z", "NECK_END_Z"),
        ("CAP_HEIGHT", "25.0"),
        ("CAP_DIA", "105.0"),
        ("CAP_TOP_BLEND_R", "2.0"),

        # Zone 7: Secondary Flutes
        ("FLUTE_RADIUS", "2.0"),
        ("FLUTE_DIA", "FLUTE_RADIUS * 2.0"),
        ("FLUTE_HEIGHT", "CAP_HEIGHT - 4.0"),
        ("FLUTE_OFFSET_R", "(CAP_DIA / 2.0) - 0.8"),
        ("FLUTE_START_Z", "CAP_START_Z + 1.5"),
        ("FLUTE_NEG_OFFSET_R", "-FLUTE_OFFSET_R"),
    ]

    populate_expressions(part, exp_defs)
    for name, form in exp_defs:
        print(f"  {name} = {form}")

    # =========================================================================
    # 2. ZONE 1: BASE FOOT RING & CHAMFER
    # =========================================================================
    print("\n[2/6] Building Zone 1: Base Foot Ring & Chamfer...")
    p_base = create_scalar_point(part, "0.0", "0.0", "BASE_START_Z")
    base_feat, main_body = create_cone(
        part, p_base,
        base_dia_rhs="BASE_BOTTOM_DIA",
        top_dia_rhs="BASE_TOP_DIA",
        height_rhs="BASE_HEIGHT",
        direction=get_dir_z(part),
        name="BASE_CONE"
    )
    print("  [OK] Feature: BASE_CONE")

    # Associative blend on bottom planar face
    base_faces = [f for f in base_feat.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    if base_faces:
        base_bottom_face = min(base_faces, key=lambda f: f.GetCenter()[2] if hasattr(f, "GetCenter") else 0.0)
        blend_base = create_associative_blend_by_face(part, base_bottom_face, "BASE_BOTTOM_BLEND_R", name="BASE_BOTTOM_BLEND")
        if blend_base:
            print("  [OK] Feature: BASE_BOTTOM_BLEND (associative face boundary rule)")

    # =========================================================================
    # 3. ZONE 2: MAIN JAR BODY
    # =========================================================================
    print("\n[3/6] Building Zone 2: Main Jar Body...")
    p_body = create_scalar_point(part, "0.0", "0.0", "BODY_START_Z")
    body_feat, body_body = create_cylinder(
        part, p_body,
        diameter_rhs="BODY_DIA",
        height_rhs="BODY_HEIGHT",
        direction=get_dir_z(part),
        name="BODY_CYLINDER"
    )
    boolean_unite(part, main_body, body_body, name="UNITE_BODY")
    print("  [OK] Feature: BODY_CYLINDER & UNITE_BODY")

    # =========================================================================
    # 4. ZONE 3: LOWER & UPPER LABEL RIDGES
    # =========================================================================
    print("\n[4/6] Building Zone 3: Lower & Upper Label Ridges...")
    p_ridge_low = create_scalar_point(part, "0.0", "0.0", "LOWER_RIDGE_Z")
    ridge_low_feat, ridge_low_body = create_cylinder(
        part, p_ridge_low,
        diameter_rhs="LOWER_RIDGE_DIA",
        height_rhs="LOWER_RIDGE_HEIGHT",
        direction=get_dir_z(part),
        name="LOWER_RIDGE_CYLINDER"
    )
    boolean_unite(part, main_body, ridge_low_body, name="UNITE_LOWER_RIDGE")
    print("  [OK] Feature: LOWER_RIDGE_CYLINDER & UNITE_LOWER_RIDGE")

    p_ridge_high = create_scalar_point(part, "0.0", "0.0", "UPPER_RIDGE_Z")
    ridge_high_feat, ridge_high_body = create_cylinder(
        part, p_ridge_high,
        diameter_rhs="UPPER_RIDGE_DIA",
        height_rhs="UPPER_RIDGE_HEIGHT",
        direction=get_dir_z(part),
        name="UPPER_RIDGE_CYLINDER"
    )
    boolean_unite(part, main_body, ridge_high_body, name="UNITE_UPPER_RIDGE")
    print("  [OK] Feature: UPPER_RIDGE_CYLINDER & UNITE_UPPER_RIDGE")

    # =========================================================================
    # 5. ZONE 4 & 5: SHOULDER TRANSITION & NECK
    # =========================================================================
    print("\n[5/6] Building Zone 4 & 5: Shoulder & Neck...")
    p_shoulder = create_scalar_point(part, "0.0", "0.0", "SHOULDER_START_Z")
    shoulder_feat, shoulder_body = create_cone(
        part, p_shoulder,
        base_dia_rhs="SHOULDER_BASE_DIA",
        top_dia_rhs="SHOULDER_TOP_DIA",
        height_rhs="SHOULDER_HEIGHT",
        direction=get_dir_z(part),
        name="SHOULDER_CONE"
    )
    boolean_unite(part, main_body, shoulder_body, name="UNITE_SHOULDER")
    print("  [OK] Feature: SHOULDER_CONE & UNITE_SHOULDER")

    # Associative blend on shoulder transition face boundary
    shoulder_cone_faces = [f for f in shoulder_feat.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Conical]
    if shoulder_cone_faces:
        blend_sh = create_associative_blend_by_face(part, shoulder_cone_faces[0], "SHOULDER_BLEND_R", name="SHOULDER_BLEND")
        if blend_sh:
            print("  [OK] Feature: SHOULDER_BLEND (associative conical face boundary)")

    # Neck
    p_neck = create_scalar_point(part, "0.0", "0.0", "NECK_START_Z")
    neck_feat, neck_body = create_cylinder(
        part, p_neck,
        diameter_rhs="NECK_DIA",
        height_rhs="NECK_HEIGHT",
        direction=get_dir_z(part),
        name="NECK_CYLINDER"
    )
    boolean_unite(part, main_body, neck_body, name="UNITE_NECK")
    print("  [OK] Feature: NECK_CYLINDER & UNITE_NECK")

    # =========================================================================
    # 6. ZONE 6 & 7: CAP / LID BODY & KNURLED FLUTES
    # =========================================================================
    print("\n[6/6] Building Zone 6 & 7: Cap / Lid Body & Secondary Flutes...")
    p_cap = create_scalar_point(part, "0.0", "0.0", "CAP_START_Z")
    cap_feat, cap_body = create_cylinder(
        part, p_cap,
        diameter_rhs="CAP_DIA",
        height_rhs="CAP_HEIGHT",
        direction=get_dir_z(part),
        name="CAP_CYLINDER"
    )
    boolean_unite(part, main_body, cap_body, name="UNITE_CAP")
    print("  [OK] Feature: CAP_CYLINDER & UNITE_CAP")

    # Associative blend on top planar face of cap
    cap_faces = [f for f in cap_feat.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    if cap_faces:
        cap_top_face = max(cap_faces, key=lambda f: f.GetCenter()[2] if hasattr(f, "GetCenter") else 0.0)
        blend_top = create_associative_blend_by_face(part, cap_top_face, "CAP_TOP_BLEND_R", name="CAP_TOP_BLEND")
        if blend_top:
            print("  [OK] Feature: CAP_TOP_BLEND (associative face boundary rule)")

    # Secondary flutes on cap skirt
    print("  Adding knurled flutes around cap skirt...")
    flute_configs = [
        ("+X", "FLUTE_OFFSET_R", "0.0"),
        ("-X", "FLUTE_NEG_OFFSET_R", "0.0"),
        ("+Y", "0.0", "FLUTE_OFFSET_R"),
        ("-Y", "0.0", "FLUTE_NEG_OFFSET_R"),
    ]
    for tag, x_rhs, y_rhs in flute_configs:
        p_flute = create_scalar_point(part, x_rhs, y_rhs, "FLUTE_START_Z")
        flute_feat, flute_body = create_cylinder(
            part, p_flute,
            diameter_rhs="FLUTE_DIA",
            height_rhs="FLUTE_HEIGHT",
            direction=get_dir_z(part),
            name=f"FLUTE_CYLINDER_{tag}"
        )
        boolean_subtract(part, main_body, flute_body, name=f"SUBTRACT_FLUTE_{tag}")

    print(f"  [OK] Created associative flutes on cap skirt")

    # Save and Export
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"\n[SAVED] Part saved: {out_prt}")

    export_stl(session, part, main_body, out_stl)

    # Update latest pointer files
    latest_txt = repo_root / "latest_nx_result.txt"
    latest_cmd = repo_root / "open_current_nx_result.cmd"
    try:
        latest_txt.write_text(f"{out_prt}\n", encoding="utf-8")
        latest_cmd.write_text(f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugraf.exe" "{out_prt}"\n', encoding="utf-8")
        print("  [OK] Updated latest_nx_result.txt and open_current_nx_result.cmd")
    except Exception as e:
        print(f"  [WARN] Updating pointer files: {e}")

    print("\n" + "=" * 75)
    print("BUILD COMPLETE: HELLMANN'S MAYONNAISE JAR")
    print("=" * 75)


if __name__ == "__main__":
    main()
