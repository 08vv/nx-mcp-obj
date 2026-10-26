"""
build_elle18_lipstick_parametric.py
===================================
Constructs a true multi-zone, sketch-driven parametric Siemens NX CAD model for
the Elle 18 Liquid Lipstick (obj/Elle18-Liquid-Lipstick.obj).

Architecture (Separate Sketches per Zone Layout):
  1. Input validation pre-check & ratio loading from proportions.json
  2. Parametric Expressions with chained zone elevations (All driving, 0 orphans)
  3. Zone 1: SKETCH_BOTTLE_BASE  -> REVOLVE_BOTTLE_BASE
  4. Zone 2: SKETCH_COLLAR       -> REVOLVE_COLLAR       -> UNITE_COLLAR
  5. Zone 3: SKETCH_CAP          -> REVOLVE_CAP          -> UNITE_CAP
  6. Zone 4: SKETCH_CROWN        -> REVOLVE_CROWN        -> UNITE_CROWN
  7. Associative Edge Blends: BASE_BOTTOM_BLEND & CROWN_APEX_BLEND
  8. Verification: Dynamic update test (CAP_DIA & CAP_HEIGHT) with 0 errors

Usage:
  run_journal.exe scripts/build_elle18_lipstick_parametric.py [output_prt]
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, List, Tuple

# Configure license servers
if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.5" not in os.environ.get("SPLM_LICENSE_SERVER", ""):
    curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.5;28000@SunFibo19;28000@192.168.1.29;28000@192.168.1.3;{curr}"

repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
sys.path.insert(0, str(repo_root))

from src.nx_mcp.parametric_helpers import (
    setup_nx_license,
    populate_expressions,
    create_fixed_datum_plane_xz,
    create_sketch_in_place,
    add_sketch_driving_dim_radius,
    add_sketch_driving_dim_height,
    add_sketch_driving_dim_length,
    add_sketch_driving_dim_elevation,
    create_sketch_revolve,
    boolean_unite,
    create_associative_blend_by_face,
    set_feature_name,
)

setup_nx_license()

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities


def validate_inputs(cap_dia: float, cap_height: float, ratios: dict) -> None:
    """Pre-check input sanity; raise ValueError on invalid design parameters."""
    if cap_dia <= 0:
        raise ValueError(f"Invalid cap diameter ({cap_dia} mm): must be positive.")
    if cap_height <= 0:
        raise ValueError(f"Invalid cap height ({cap_height} mm): must be positive.")
    
    r_bottle_dia = ratios.get("ratio_bottle_to_cap_dia", 1.033)
    if r_bottle_dia <= 0.5:
        raise ValueError(f"Invalid ratio_bottle_to_cap_dia ({r_bottle_dia}): bottle body must be reasonably proportioned.")


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
    default_prt = repo_root / "Elle18_Liquid_Lipstick_Parametric.prt"
    out_prt = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else default_prt
    out_stl = out_prt.with_suffix(".stl")
    prop_path = repo_root / "proportions.json"

    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: ELLE 18 LIQUID LIPSTICK")
    print("  MULTI-ZONE SKETCH-BASED FULLY PARAMETRIC CAD MODEL")
    print(f"  Target PRT: {out_prt}")
    print("=" * 75)

    with open(prop_path, "r") as f:
        config = json.load(f)["elle18_lipstick"]
    
    ratios = config["ratios"]
    defaults = config["defaults"]

    cap_dia = float(defaults["cap_diameter"])
    cap_height = float(defaults["cap_height"])
    base_blend_r = float(defaults.get("base_blend_r", 2.0))
    crown_apex_r = float(defaults.get("crown_apex_r", 1.5))

    validate_inputs(cap_dia, cap_height, ratios)
    print("  [OK] Python input pre-checks passed.")

    if out_prt.exists():
        try:
            out_prt.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(out_prt), NXOpen.Part.Units.Millimeters)

    # -------------------------------------------------------------------------
    # 1. POPULATE CHAINED PARAMETRIC EXPRESSIONS (ALL ACTIVE, 0 ORPHANS)
    # -------------------------------------------------------------------------
    print("\n[1/6] Populating chained driving expressions...")
    exp_defs = [
        # Master inputs
        ("CAP_DIA", f"{cap_dia}"),
        ("CAP_HEIGHT", f"{cap_height}"),

        # Proportions from proportions.json
        ("RATIO_BOTTLE_CAP_DIA", f"{ratios['ratio_bottle_to_cap_dia']}"),
        ("RATIO_BOTTLE_CAP_H",   f"{ratios['ratio_bottle_to_cap_height']}"),
        ("RATIO_COLLAR_H",       f"{ratios['ratio_collar_height']}"),
        ("RATIO_CROWN_H",        f"{ratios['ratio_crown_height']}"),
        ("RATIO_CROWN_APEX_DIA", f"{ratios['ratio_crown_apex_dia']}"),

        # Derived dimensions
        ("BOTTLE_DIA", "CAP_DIA * RATIO_BOTTLE_CAP_DIA"),
        ("CROWN_TOP_DIA", "max(CAP_DIA * RATIO_CROWN_APEX_DIA, 2.0)"),
        ("BOTTLE_HEIGHT", "CAP_HEIGHT * RATIO_BOTTLE_CAP_H"),
        ("COLLAR_HEIGHT", "CAP_HEIGHT * RATIO_COLLAR_H"),
        ("CROWN_HEIGHT", "CAP_HEIGHT * RATIO_CROWN_H"),

        ("BOTTLE_RADIUS", "BOTTLE_DIA / 2.0"),
        ("CAP_RADIUS", "CAP_DIA / 2.0"),
        ("CROWN_APEX_RADIUS", "CROWN_TOP_DIA / 2.0"),

        # Chained zone elevations
        ("COLLAR_Z0", "BOTTLE_HEIGHT"),
        ("CAP_Z0", "COLLAR_Z0 + COLLAR_HEIGHT"),
        ("CROWN_Z0", "CAP_Z0 + CAP_HEIGHT"),

        # Fillet blend radii
        ("BASE_BLEND_R", f"{base_blend_r}"),
        ("CROWN_APEX_R", f"{crown_apex_r}"),
    ]

    populate_expressions(part, exp_defs)
    for name, rhs in exp_defs:
        print(f"  {name} = {rhs}")

    dp_xz = create_fixed_datum_plane_xz(part, (0.0, 0.0, 0.0))

    r_bottle = cap_dia * ratios['ratio_bottle_to_cap_dia'] / 2.0
    r_cap    = cap_dia / 2.0
    r_apex   = cap_dia * ratios['ratio_crown_apex_dia'] / 2.0

    h_bottle = cap_height * ratios['ratio_bottle_to_cap_height']
    h_collar = cap_height * ratios['ratio_collar_height']
    h_cap    = cap_height
    h_crown  = cap_height * ratios['ratio_crown_height']

    z0 = 0.0
    z_collar = z0 + h_bottle
    z_cap    = z_collar + h_collar
    z_crown  = z_cap + h_cap
    z_top    = z_crown + h_crown

    # -------------------------------------------------------------------------
    # 2. ZONE 1: BOTTLE BASE CYLINDER (SKETCH + REVOLVE)
    # -------------------------------------------------------------------------
    print("\n[2/6] Building Zone 1: Bottle Base Cylinder...")
    sk_base = create_sketch_in_place(part, dp_xz, name="SKETCH_BOTTLE_BASE")
    sk_base.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    l1_axis = part.Curves.CreateLine(NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Point3d(0.0, 0.0, z_collar))
    l1_top  = part.Curves.CreateLine(NXOpen.Point3d(0.0, 0.0, z_collar), NXOpen.Point3d(r_bottle, 0.0, z_collar))
    l1_side = part.Curves.CreateLine(NXOpen.Point3d(r_bottle, 0.0, z_collar), NXOpen.Point3d(r_bottle, 0.0, 0.0))
    l1_bot  = part.Curves.CreateLine(NXOpen.Point3d(r_bottle, 0.0, 0.0), NXOpen.Point3d(0.0, 0.0, 0.0))

    for l in [l1_axis, l1_top, l1_side, l1_bot]:
        sk_base.AddGeometry(l, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)

    cg1 = NXOpen.Sketch.ConstraintGeometry()
    cg1.Geometry = l1_axis
    sk_base.CreateFixedConstraint(cg1)

    add_sketch_driving_dim_radius(sk_base, part, l1_axis, l1_side, "BOTTLE_RADIUS", r_bottle / 2.0, z_collar / 2.0)
    add_sketch_driving_dim_height(sk_base, part, l1_side, "BOTTLE_HEIGHT", r_bottle + 5.0, z_collar / 2.0)

    sk_base.Update()
    sk_base.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    rev_base_feat, main_body = create_sketch_revolve(part, sk_base, l1_axis, name="REVOLVE_BOTTLE_BASE")
    print("  [OK] Features: SKETCH_BOTTLE_BASE -> REVOLVE_BOTTLE_BASE")

    # -------------------------------------------------------------------------
    # 3. ZONE 2: COLLAR STEP CONE (SKETCH + REVOLVE + UNITE)
    # -------------------------------------------------------------------------
    print("\n[3/6] Building Zone 2: Collar Step Cone...")
    sk_col = create_sketch_in_place(part, dp_xz, name="SKETCH_COLLAR")
    sk_col.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    l2_axis = part.Curves.CreateLine(NXOpen.Point3d(0.0, 0.0, z_collar), NXOpen.Point3d(0.0, 0.0, z_cap))
    l2_top  = part.Curves.CreateLine(NXOpen.Point3d(0.0, 0.0, z_cap), NXOpen.Point3d(r_cap, 0.0, z_cap))
    l2_side = part.Curves.CreateLine(NXOpen.Point3d(r_cap, 0.0, z_cap), NXOpen.Point3d(r_bottle, 0.0, z_collar))
    l2_bot  = part.Curves.CreateLine(NXOpen.Point3d(r_bottle, 0.0, z_collar), NXOpen.Point3d(0.0, 0.0, z_collar))

    for l in [l2_axis, l2_top, l2_side, l2_bot]:
        sk_col.AddGeometry(l, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)

    cg2 = NXOpen.Sketch.ConstraintGeometry()
    cg2.Geometry = l2_axis
    sk_col.CreateFixedConstraint(cg2)

    # Origin elevation anchor
    pt_orig2 = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    sk_col.AddGeometry(pt_orig2, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    cg_pt2 = NXOpen.Sketch.ConstraintGeometry()
    cg_pt2.Geometry = pt_orig2
    sk_col.CreateFixedConstraint(cg_pt2)

    add_sketch_driving_dim_elevation(sk_col, part, pt_orig2, l2_axis, "COLLAR_Z0", -10.0, z_collar / 2.0)
    add_sketch_driving_dim_height(sk_col, part, l2_axis, "COLLAR_HEIGHT", -5.0, z_collar + h_collar / 2.0)
    add_sketch_driving_dim_length(sk_col, part, l2_top, "CAP_RADIUS", r_cap / 2.0, z_cap + 2.0)
    add_sketch_driving_dim_length(sk_col, part, l2_bot, "BOTTLE_RADIUS", r_bottle / 2.0, z_collar - 2.0)

    sk_col.Update()
    sk_col.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    rev_col_feat, col_body = create_sketch_revolve(part, sk_col, l2_axis, name="REVOLVE_COLLAR")
    unite_col_feat = boolean_unite(part, main_body, col_body, name="UNITE_COLLAR")
    main_body = [b for b in part.Bodies if b.IsSolidBody][-1]
    print("  [OK] Features: SKETCH_COLLAR -> REVOLVE_COLLAR -> UNITE_COLLAR")

    # -------------------------------------------------------------------------
    # 4. ZONE 3: CAP CYLINDER (SKETCH + REVOLVE + UNITE)
    # -------------------------------------------------------------------------
    print("\n[4/6] Building Zone 3: Cap Cylinder...")
    sk_cap = create_sketch_in_place(part, dp_xz, name="SKETCH_CAP")
    sk_cap.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    l3_axis = part.Curves.CreateLine(NXOpen.Point3d(0.0, 0.0, z_cap), NXOpen.Point3d(0.0, 0.0, z_crown))
    l3_top  = part.Curves.CreateLine(NXOpen.Point3d(0.0, 0.0, z_crown), NXOpen.Point3d(r_cap, 0.0, z_crown))
    l3_side = part.Curves.CreateLine(NXOpen.Point3d(r_cap, 0.0, z_crown), NXOpen.Point3d(r_cap, 0.0, z_cap))
    l3_bot  = part.Curves.CreateLine(NXOpen.Point3d(r_cap, 0.0, z_cap), NXOpen.Point3d(0.0, 0.0, z_cap))

    for l in [l3_axis, l3_top, l3_side, l3_bot]:
        sk_cap.AddGeometry(l, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)

    cg3 = NXOpen.Sketch.ConstraintGeometry()
    cg3.Geometry = l3_axis
    sk_cap.CreateFixedConstraint(cg3)

    pt_orig3 = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    sk_cap.AddGeometry(pt_orig3, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    cg_pt3 = NXOpen.Sketch.ConstraintGeometry()
    cg_pt3.Geometry = pt_orig3
    sk_cap.CreateFixedConstraint(cg_pt3)

    add_sketch_driving_dim_elevation(sk_cap, part, pt_orig3, l3_axis, "CAP_Z0", -10.0, z_cap / 2.0)
    add_sketch_driving_dim_height(sk_cap, part, l3_axis, "CAP_HEIGHT", -5.0, z_cap + h_cap / 2.0)
    add_sketch_driving_dim_radius(sk_cap, part, l3_axis, l3_side, "CAP_RADIUS", r_cap / 2.0, z_cap + h_cap / 2.0)

    sk_cap.Update()
    sk_cap.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    rev_cap_feat, cap_body = create_sketch_revolve(part, sk_cap, l3_axis, name="REVOLVE_CAP")
    unite_cap_feat = boolean_unite(part, main_body, cap_body, name="UNITE_CAP")
    main_body = [b for b in part.Bodies if b.IsSolidBody][-1]
    print("  [OK] Features: SKETCH_CAP -> REVOLVE_CAP -> UNITE_CAP")

    # -------------------------------------------------------------------------
    # 5. ZONE 4: CROWN DOME (SKETCH + REVOLVE + UNITE)
    # -------------------------------------------------------------------------
    print("\n[5/6] Building Zone 4: Crown Dome / Taper...")
    sk_crown = create_sketch_in_place(part, dp_xz, name="SKETCH_CROWN")
    sk_crown.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    l4_axis = part.Curves.CreateLine(NXOpen.Point3d(0.0, 0.0, z_crown), NXOpen.Point3d(0.0, 0.0, z_top))
    l4_top  = part.Curves.CreateLine(NXOpen.Point3d(0.0, 0.0, z_top), NXOpen.Point3d(r_apex, 0.0, z_top))
    l4_side = part.Curves.CreateLine(NXOpen.Point3d(r_apex, 0.0, z_top), NXOpen.Point3d(r_cap, 0.0, z_crown))
    l4_bot  = part.Curves.CreateLine(NXOpen.Point3d(r_cap, 0.0, z_crown), NXOpen.Point3d(0.0, 0.0, z_crown))

    for l in [l4_axis, l4_top, l4_side, l4_bot]:
        sk_crown.AddGeometry(l, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)

    cg4 = NXOpen.Sketch.ConstraintGeometry()
    cg4.Geometry = l4_axis
    sk_crown.CreateFixedConstraint(cg4)

    pt_orig4 = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    sk_crown.AddGeometry(pt_orig4, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    cg_pt4 = NXOpen.Sketch.ConstraintGeometry()
    cg_pt4.Geometry = pt_orig4
    sk_crown.CreateFixedConstraint(cg_pt4)

    add_sketch_driving_dim_elevation(sk_crown, part, pt_orig4, l4_axis, "CROWN_Z0", -10.0, z_crown / 2.0)
    add_sketch_driving_dim_height(sk_crown, part, l4_axis, "CROWN_HEIGHT", -5.0, z_crown + h_crown / 2.0)
    add_sketch_driving_dim_length(sk_crown, part, l4_top, "CROWN_APEX_RADIUS", r_apex / 2.0, z_top + 2.0)
    add_sketch_driving_dim_length(sk_crown, part, l4_bot, "CAP_RADIUS", r_cap / 2.0, z_crown - 2.0)

    sk_crown.Update()
    sk_crown.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    rev_crown_feat, crown_body = create_sketch_revolve(part, sk_crown, l4_axis, name="REVOLVE_CROWN")
    unite_crown_feat = boolean_unite(part, main_body, crown_body, name="UNITE_CROWN")
    main_body = [b for b in part.Bodies if b.IsSolidBody][-1]
    print("  [OK] Features: SKETCH_CROWN -> REVOLVE_CROWN -> UNITE_CROWN")

    # -------------------------------------------------------------------------
    # 6. ASSOCIATIVE EDGE BLENDS
    # -------------------------------------------------------------------------
    print("\n[6/6] Applying Associative Edge Blends...")
    planar_faces = [f for f in main_body.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    base_face = min(planar_faces, key=lambda f: min(v.Z for e in f.GetEdges() for v in e.GetVertices()))
    blend_base = create_associative_blend_by_face(part, base_face, "BASE_BLEND_R", name="BASE_BOTTOM_BLEND")
    print("  [OK] Feature: BASE_BOTTOM_BLEND (R = BASE_BLEND_R)")

    apex_face = max(planar_faces, key=lambda f: max(v.Z for e in f.GetEdges() for v in e.GetVertices()))
    blend_crown = create_associative_blend_by_face(part, apex_face, "CROWN_APEX_R", name="CROWN_APEX_BLEND")
    print("  [OK] Feature: CROWN_APEX_BLEND (R = CROWN_APEX_R)")

    # -------------------------------------------------------------------------
    # REPORT PART NAVIGATOR FEATURES
    # -------------------------------------------------------------------------
    print("\n" + "=" * 75)
    print("PART NAVIGATOR FEATURE TREE:")
    print("=" * 75)
    all_features = list(part.Features)
    for idx, f in enumerate(all_features, 1):
        print(f"  [{idx:2d}] {f.GetFeatureName():<25} (Type: {f.FeatureType})")

    # -------------------------------------------------------------------------
    # DYNAMIC PARAMETRIC UPDATE VERIFICATION
    # -------------------------------------------------------------------------
    print("\n" + "=" * 75)
    print("DYNAMIC UPDATE VERIFICATION TEST:")
    print("=" * 75)
    def get_circular_radii(p):
        rs = []
        for b in p.Bodies:
            if b.IsSolidBody:
                for e in b.GetEdges():
                    if e.SolidEdgeType == NXOpen.Edge.EdgeType.Circular:
                        rs.append(round(e.GetLength() / (2.0 * math.pi), 2))
        return sorted(list(set([r for r in rs if r > 0.5])))

    print("  Initial Circular Radii on Body:", get_circular_radii(part))

    new_cap_dia = 28.0      # 21.88 -> 28.0 mm
    new_cap_height = 90.0   # 75.5  -> 90.0 mm
    print(f"  Modifying Expressions: CAP_DIA -> {new_cap_dia} mm, CAP_HEIGHT -> {new_cap_height} mm")
    
    exp_cap_d = part.Expressions.FindObject("CAP_DIA")
    exp_cap_h = part.Expressions.FindObject("CAP_HEIGHT")
    exp_cap_d.RightHandSide = f"{new_cap_dia}"
    exp_cap_h.RightHandSide = f"{new_cap_height}"

    mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "ParamUpdate")
    n_err = session.UpdateManager.DoUpdate(mark)
    print(f"  session.UpdateManager.DoUpdate() completed with {n_err} errors.")

    updated_radii = get_circular_radii(part)
    print("  Updated Circular Radii on Body:", updated_radii)
    expected_cap_r = new_cap_dia / 2.0
    expected_bottle_r = new_cap_dia * ratios['ratio_bottle_to_cap_dia'] / 2.0

    cap_ok = any(abs(r - expected_cap_r) < 0.2 for r in updated_radii)
    bottle_ok = any(abs(r - expected_bottle_r) < 0.2 for r in updated_radii)

    print(f"  [CHECK] Cap Radius Resized ({expected_cap_r:.2f} mm): {'PASS' if cap_ok else 'FAIL'}")
    print(f"  [CHECK] Bottle Radius Resized ({expected_bottle_r:.2f} mm): {'PASS' if bottle_ok else 'FAIL'}")
    print(f"  [CHECK] Update Errors == 0: {'PASS' if n_err == 0 else 'FAIL'}")

    # Revert back to original default for target PRT
    exp_cap_d.RightHandSide = f"{cap_dia}"
    exp_cap_h.RightHandSide = f"{cap_height}"
    session.UpdateManager.DoUpdate(mark)

    # -------------------------------------------------------------------------
    # SAVE & EXPORT
    # -------------------------------------------------------------------------
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"\n[OK] Part successfully saved to: {out_prt}")

    active_body = [b for b in part.Bodies if b.IsSolidBody][-1]
    export_stl(session, part, active_body, out_stl)

    # Update quick-launch files
    cmd_file = repo_root / "open_current_nx_result.cmd"
    cmd_file.write_text(f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugraf.exe" "{out_prt}"\n', encoding="utf-8")
    latest_file = repo_root / "latest_nx_result.txt"
    latest_file.write_text(str(out_prt), encoding="utf-8")
    print(f"[OK] Updated {cmd_file.name} and {latest_file.name}")


if __name__ == "__main__":
    main()
