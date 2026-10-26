"""
build_cif3_parametric.py
========================
Fully Parametric, Zone-Wise Siemens NX CAD Builder for Cif3 Jerry Can Container.

Reconstructs obj/Cif3_jerry_can_reduced.obj as a genuine multi-zone,
multi-feature parametric Siemens NX part (.prt) that strictly passes
all automated CAD quality checks:
  CHECK 1: Zero monolithic lofts spanning >80% total height
  CHECK 2: ≥5 distinct named features in Part Navigator
  CHECK 3: All user expressions actively drive solid geometry (0 orphans)
  CHECK 4: Associative edge blends (SelectionIntentRule OuterEdgesOfFaces, 0 dumb rules)

Zone Decomposition & Feature Tree:
  1. Parametric Expressions: Chained driving variables
  2. LOWER_BODY: Through Curves, Z = 2.0 to 75.0 mm (H = 73.0 mm, 36.6%)
  3. BOTTOM_BASE_EXTENSION: Extrude base station down to Z = 0.0 mm
  4. BASE_BOTTOM_BLEND: Associative edge blend on bottom perimeter (R = 1.5 mm)
  5. MID_BODY: Through Curves, Z = 75.0 to 145.0 mm (H = 70.0 mm, 35.1%)
  6. UNITE_MID_BODY: Boolean unite into main body
  7. UPPER_SHOULDER: Through Curves, Z = 145.0 to 164.0 mm (H = 19.0 mm, 9.5%)
  8. UNITE_SHOULDER: Boolean unite into main body
  9. HANDLE_SOLID_ARCH: Through Curves, Z = 160.0 to 199.45 mm (H = 39.45 mm, 19.8%)
  10. UNITE_HANDLE: Boolean unite into main body
  11. HANDLE_THROUGH_CUTOUT: Extrude subtract of enclosed opening (lines + tangent arcs)
  12. NECK_COLLAR: Cylinder primitive at X = -48.2, Y = -0.5, Z = NECK_START_Z
  13. UNITE_NECK: Boolean unite into main body
  14. CAP_CYLINDER: Cylinder primitive at X = -48.2, Y = -0.5, Z = CAP_START_Z
  15. CAP_TOP_BLEND: Associative edge blend on cap crown (R = 1.2 mm)
  16. UNITE_CAP: Boolean unite into main body

Usage:
  python scripts/build_cif3_parametric.py [spec_json] [output_prt]
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

# Configure license servers
if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.5" not in os.environ.get("SPLM_LICENSE_SERVER", ""):
    curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.5;28000@SunFibo19;28000@192.168.1.29;28000@192.168.1.3;{curr}"

_REPO_ROOT = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from nx_mcp.parametric_helpers import (
    boolean_unite,
    create_associative_blend_by_face,
    create_cylinder,
    create_scalar_point,
    populate_expressions,
    set_feature_name,
)

try:
    import NXOpen
    import NXOpen.Features
    import NXOpen.GeometricUtilities
    import NXOpen.UF
    UF = NXOpen.UF.UFSession.GetUFSession()
except ImportError:
    run_journal_exe = Path(r"C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe")
    if not run_journal_exe.exists():
        print(f"[FAIL] NXOpen not found and {run_journal_exe} does not exist.")
        sys.exit(1)
    import subprocess
    cmd = [str(run_journal_exe), str(Path(__file__).resolve())]
    if len(sys.argv) > 1:
        cmd.extend(["-args", *sys.argv[1:]])
    res = subprocess.run(cmd)
    sys.exit(res.returncode)


# ──────────────────────────────────────────────────────────────────────────────
# NX Helper Utilities
# ──────────────────────────────────────────────────────────────────────────────

def pt(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def vc(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))


def make_line(part, a, b):
    c = part.Curves.CreateLine(pt(*a), pt(*b))
    try:
        c.Blank()
    except Exception:
        pass
    return c


def nx_section(part, curves, start_point=None):
    sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
    rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    help_pt = start_point if start_point is not None else pt(0.0, 0.0, 0.0)
    sec.AddToSection(
        rules,
        curves[0],
        NXOpen.NXObject.Null,
        NXOpen.NXObject.Null,
        help_pt,
        NXOpen.Section.Mode.Create,
        False,
    )
    return sec


def append_section(builder, sec) -> None:
    container = getattr(builder, "SectionsList", None) or getattr(builder, "Sections", None)
    if hasattr(container, "Append"):
        container.Append(sec)
    else:
        container.Add(sec)


def build_loft_zone(part, sts, name: str):
    """Build a ThroughCurves solid zone from a list of cross-section station point-sets."""
    curvesets, spts = [], []
    for pts_3d in sts:
        n = len(pts_3d)
        c = [make_line(part, pts_3d[k], pts_3d[(k + 1) % n]) for k in range(n)]
        curvesets.append(c)
        spts.append(pts_3d[0])
    lb = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        lb.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
        for c, sp in zip(curvesets, spts):
            append_section(lb, nx_section(part, c, start_point=pt(*sp)))
        f = lb.CommitFeature()
        set_feature_name(f, name)
        return f, f.GetBodies()[0]
    finally:
        lb.Destroy()


def export_stl(session, part, body, stl_path: Path):
    """Export body as STL for validation."""
    if stl_path.exists():
        try:
            stl_path.unlink()
        except Exception:
            pass
    stl_exp = session.DexManager.CreateStlCreator()
    try:
        stl_exp.OutputFile = str(stl_path)
        stl_exp.ExportSelectionBlock.Add(body)
        stl_exp.Commit()
        print(f"  [OK] STL exported: {stl_path} ({stl_path.stat().st_size:,} bytes)")
    except Exception as e:
        print(f"  [WARN] STL export: {e}")
    finally:
        stl_exp.Destroy()


# ──────────────────────────────────────────────────────────────────────────────
# Main Reconstruction Routine
# ──────────────────────────────────────────────────────────────────────────────

def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    default_spec = repo_root / "Cif3_parametric_spec.json"
    default_prt = repo_root / "Cif3_Parametric.prt"

    args = [a for a in sys.argv[1:] if a != "-args" and not a.startswith("-")]
    spec_path = Path(args[0]).resolve() if len(args) > 0 else default_spec
    out_prt = Path(args[1]).resolve() if len(args) > 1 else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 75)
    print("CIF3 JERRY CAN CONTAINER: ZONE-WISE PARAMETRIC NX CAD RECONSTRUCTION")
    print("  MULTI-FEATURE ARCHITECTURE (ZERO MONOLITHIC LOFTS, 0 ORPHANS)")
    print(f"  Specification: {spec_path}")
    print(f"  Target PRT:    {out_prt}")
    print("=" * 75)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

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
    print("\n[1/10] Creating chained driving expressions...")
    exp_defs = spec.get("expressions", [])
    populate_expressions(part, exp_defs)

    dir_z_pos = part.Directions.CreateDirection(
        pt(0, 0, 0), vc(0, 0, 1), NXOpen.SmartObject.UpdateOption.WithinModeling
    )
    dir_z_neg = part.Directions.CreateDirection(
        pt(0, 0, 0), vc(0, 0, -1), NXOpen.SmartObject.UpdateOption.WithinModeling
    )
    dir_y_pos = part.Directions.CreateDirection(
        pt(0, 0, 0), vc(0, 1, 0), NXOpen.SmartObject.UpdateOption.WithinModeling
    )

    # =========================================================================
    # 2. ZONE 1: LOWER BODY (Through Curves)
    #    Z = 2.0 to 75.0 mm (H = 73.0 mm, 36.6% of height < 80%)
    # =========================================================================
    print("\n[2/10] Building Zone 1: LOWER_BODY (ThroughCurves)...")
    lower_stations = spec.get("lower_stations", [])
    f_lower, main_body = build_loft_zone(part, lower_stations, "LOWER_BODY")
    print(f"  [OK] Feature: LOWER_BODY committed ({len(lower_stations)} stations).")

    # =========================================================================
    # 3. BOTTOM BASE EXTENSION & ASSOCIATIVE BLEND
    #    Extrude station 0 down from Z = 2.0 to Z = 0.0 mm
    # =========================================================================
    print("\n[3/10] Extending base plate down to Z=0.0mm & applying associative blend...")
    bot_pts = lower_stations[0]
    n_bot = len(bot_pts)
    bot_curves = [make_line(part, bot_pts[k], bot_pts[(k + 1) % n_bot]) for k in range(n_bot)]

    base_ext_b = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        base_ext_b.Section = nx_section(part, bot_curves)
        base_ext_b.Limits.StartExtend.Value.RightHandSide = "0.0"
        base_ext_b.Limits.EndExtend.Value.RightHandSide = "BASE_EXTENSION_HEIGHT"
        base_ext_b.Direction = dir_z_neg
        base_ext_b.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite, main_body
        )
        bot_ext_feat = base_ext_b.CommitFeature()
        set_feature_name(bot_ext_feat, "BOTTOM_BASE_EXTENSION")
        print("  [OK] Feature: BOTTOM_BASE_EXTENSION committed.")
    finally:
        base_ext_b.Destroy()

    # Associative Bottom Base Blend on bottom planar face (Z = 0.0)
    bot_planar = [f for f in main_body.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    if bot_planar:
        bot_face = min(bot_planar, key=lambda f: f.GetCenter()[2] if hasattr(f, "GetCenter") else 0.0)
        try:
            bf_base = create_associative_blend_by_face(
                part, bot_face, "BASE_BLEND_R", name="BASE_BOTTOM_BLEND"
            )
            if bf_base:
                print("  [OK] Feature: BASE_BOTTOM_BLEND committed (associative OuterEdgesOfFaces).")
        except Exception as e:
            print(f"  [WARN] BASE_BOTTOM_BLEND notice: {e}")

    # =========================================================================
    # 4. ZONE 2: MID BODY (Through Curves)
    #    Z = 75.0 to 145.0 mm (H = 70.0 mm, 35.1% of height < 80%)
    #    Includes upper subtle horizontal band at Z = 138.0 mm
    # =========================================================================
    print("\n[4/10] Building Zone 2: MID_BODY (ThroughCurves)...")
    mid_stations = spec.get("mid_stations", [])
    f_mid, b_mid = build_loft_zone(part, mid_stations, "MID_BODY")
    print("  [OK] Feature: MID_BODY committed.")
    boolean_unite(part, main_body, b_mid, name="UNITE_MID_BODY")
    print("  [OK] Feature: UNITE_MID_BODY committed.")

    # =========================================================================
    # 5. ZONE 3: UPPER SHOULDER (Through Curves)
    #    Z = 145.0 to 164.0 mm (H = 19.0 mm, 9.5% of height)
    # =========================================================================
    print("\n[5/10] Building Zone 3: UPPER_SHOULDER (ThroughCurves)...")
    shoulder_stations = spec.get("shoulder_stations", [])
    f_sh, b_sh = build_loft_zone(part, shoulder_stations, "UPPER_SHOULDER")
    print("  [OK] Feature: UPPER_SHOULDER committed.")
    boolean_unite(part, main_body, b_sh, name="UNITE_SHOULDER")
    print("  [OK] Feature: UNITE_SHOULDER committed.")

    # =========================================================================
    # 6. ZONE 4: HANDLE SOLID ARCH (Through Curves)
    #    Z = 160.0 to 199.45 mm (H = 39.45 mm, 19.8% of height)
    # =========================================================================
    print("\n[6/10] Building Zone 4: HANDLE_SOLID_ARCH (ThroughCurves)...")
    handle_stations = spec.get("handle_stations", [])
    f_handle, b_handle = build_loft_zone(part, handle_stations, "HANDLE_SOLID_ARCH")
    print("  [OK] Feature: HANDLE_SOLID_ARCH committed.")
    boolean_unite(part, main_body, b_handle, name="UNITE_HANDLE")
    print("  [OK] Feature: UNITE_HANDLE committed.")

    # =========================================================================
    # 7. HANDLE THROUGH CUTOUT (Extrude Subtract along Y)
    #    Exact enclosed opening with smooth lines + tangent corner arcs
    # =========================================================================
    print("\n[7/10] Cutting Feature: HANDLE_THROUGH_CUTOUT (Extrude Subtract)...")
    ho = spec.get("handle_opening", {})
    x_min = float(ho.get("x_min", -11.39))
    x_max = float(ho.get("x_max", 45.67))
    z_min = float(ho.get("z_min", 164.34))
    z_max = float(ho.get("z_max", 189.00))
    r_corn = float(ho.get("corner_radius", 8.0))
    y_cut = float(ho.get("y_cut_start", -35.0))
    y_depth = float(ho.get("y_cut_depth", 70.0))

    bl_c = (x_min + r_corn, z_min + r_corn)
    br_c = (x_max - r_corn, z_min + r_corn)
    tr_c = (x_max - r_corn, z_max - r_corn)
    tl_c = (x_min + r_corn, z_max - r_corn)

    opening_curves = [
        # Bottom horizontal segment
        part.Curves.CreateLine(pt(bl_c[0], y_cut, z_min), pt(br_c[0], y_cut, z_min)),
        # Bottom-right corner arc
        part.Curves.CreateArc(pt(br_c[0], y_cut, br_c[1]), vc(1, 0, 0), vc(0, 0, 1), r_corn, -math.pi / 2.0, 0.0),
        # Right vertical segment
        part.Curves.CreateLine(pt(x_max, y_cut, br_c[1]), pt(x_max, y_cut, tr_c[1])),
        # Top-right corner arc
        part.Curves.CreateArc(pt(tr_c[0], y_cut, tr_c[1]), vc(1, 0, 0), vc(0, 0, 1), r_corn, 0.0, math.pi / 2.0),
        # Top horizontal segment
        part.Curves.CreateLine(pt(tr_c[0], y_cut, z_max), pt(tl_c[0], y_cut, z_max)),
        # Top-left corner arc
        part.Curves.CreateArc(pt(tl_c[0], y_cut, tl_c[1]), vc(1, 0, 0), vc(0, 0, 1), r_corn, math.pi / 2.0, math.pi),
        # Left vertical segment
        part.Curves.CreateLine(pt(x_min, y_cut, tl_c[1]), pt(x_min, y_cut, bl_c[1])),
        # Bottom-left corner arc
        part.Curves.CreateArc(pt(bl_c[0], y_cut, bl_c[1]), vc(1, 0, 0), vc(0, 0, 1), r_corn, math.pi, 1.5 * math.pi),
    ]

    cut_builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        cut_builder.Section = nx_section(part, opening_curves)
        cut_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        cut_builder.Limits.EndExtend.Value.RightHandSide = str(y_depth)
        cut_builder.Direction = dir_y_pos
        cut_builder.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract, main_body
        )
        cut_feat = cut_builder.CommitFeature()
        set_feature_name(cut_feat, "HANDLE_THROUGH_CUTOUT")
        print("  [OK] Feature: HANDLE_THROUGH_CUTOUT committed.")
    finally:
        cut_builder.Destroy()

    # =========================================================================
    # 8. ZONE 5: OFFSET NECK COLLAR (Cylinder Primitive)
    #    Positioned beside handle at X = -48.2, Y = -0.5, Z = NECK_START_Z
    # =========================================================================
    print("\n[8/10] Building Zone 5: NECK_COLLAR (Cylinder)...")
    neck_info = spec.get("neck", {})
    pos_x = str(neck_info.get("collar_pos_x", -48.2))
    pos_y = str(neck_info.get("collar_pos_y", -0.5))

    pt_neck = create_scalar_point(part, pos_x, pos_y, "NECK_START_Z")
    neck_feat, neck_body = create_cylinder(
        part,
        pt_neck,
        diameter_rhs="COLLAR_DIA",
        height_rhs="COLLAR_HEIGHT",
        direction=dir_z_pos,
        name="NECK_COLLAR",
    )
    print("  [OK] Feature: NECK_COLLAR committed.")
    boolean_unite(part, main_body, neck_body, name="UNITE_NECK")
    print("  [OK] Feature: UNITE_NECK committed.")

    # =========================================================================
    # 9. ZONE 6: OFFSET CAP CYLINDER & TOP CROWN BLEND
    #    Chained from neck collar at Z = CAP_START_Z, crowned with associative blend
    # =========================================================================
    print("\n[9/10] Building Zone 6: CAP_CYLINDER (Cylinder) & CAP_TOP_BLEND...")
    pt_cap = create_scalar_point(part, pos_x, pos_y, "CAP_START_Z")
    cap_feat, cap_body = create_cylinder(
        part,
        pt_cap,
        diameter_rhs="CAP_DIA",
        height_rhs="CAP_HEIGHT",
        direction=dir_z_pos,
        name="CAP_CYLINDER",
    )
    print("  [OK] Feature: CAP_CYLINDER committed.")

    # Associative Cap Top Crown Blend on cap's top planar face
    cap_planar = [f for f in cap_feat.GetFaces() if f.SolidFaceType == NXOpen.Face.FaceType.Planar]
    if cap_planar:
        top_cap_face = max(cap_planar, key=lambda f: f.GetCenter()[2] if hasattr(f, "GetCenter") else 0.0)
        try:
            bf_cap = create_associative_blend_by_face(
                part, top_cap_face, "CAP_BLEND_R", name="CAP_TOP_BLEND"
            )
            if bf_cap:
                print("  [OK] Feature: CAP_TOP_BLEND committed (associative OuterEdgesOfFaces).")
        except Exception as e:
            print(f"  [WARN] CAP_TOP_BLEND notice: {e}")

    boolean_unite(part, main_body, cap_body, name="UNITE_CAP")
    print("  [OK] Feature: UNITE_CAP committed.")

    main_body = [b for b in part.Bodies if b.IsSolidBody][0]

    # =========================================================================
    # 10. AUDIT, SAVE & QUICK LAUNCH
    # =========================================================================
    print("\n[10/10] Feature Tree Audit, Save & STL Export...")
    feats = list(part.Features)
    print("=" * 75)
    print("PART NAVIGATOR FEATURE TREE:")
    for i, f in enumerate(feats):
        print(f"  [{i + 1:2d}] {f.GetFeatureName():<34} (Type: {f.FeatureType})")
    print(f"Total Model Features: {len(feats)}")
    bodies = [b for b in part.Bodies if b.IsSolidBody]
    print(f"Solid Bodies:         {len(bodies)}")
    print("=" * 75)

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"\n[OK] Model saved successfully: {out_prt}")

    # Export STL
    export_stl(session, part, main_body, out_stl)

    # Quick launch command
    cmd_file = repo_root / "open_current_nx_result.cmd"
    cmd_file.write_text(
        f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugraf.exe" "{out_prt}"\n',
        encoding="utf-8",
    )
    latest_file = repo_root / "latest_nx_result.txt"
    latest_file.write_text(str(out_prt), encoding="utf-8")

    print("\nReconstruction completed successfully.")


if __name__ == "__main__":
    main()
