"""
create_clevis_mount.py
=======================
NX Journal that creates a parametric clevis mount bracket.
All dimensions are stored as named NX Expressions.

Geometry (origin at center of bottom face of base, i.e. (0,0,0)):
  - Base rectangular block: 60 x 20 x 12 mm
  - Left arm  : 12 x 20 x 48 mm block at left end of base, united
  - Right arm : 12 x 20 x 48 mm block at right end of base, united
  - Left  cylindrical boss: D24, L12, on outer -Y face of left arm, united
  - Right cylindrical boss: D24, L12, on outer +Y face of right arm, united
  - Left  pin hole: D10, depth 24, -Y through left arm+boss, subtracted
  - Right pin hole: D10, depth 24, +Y through right arm+boss, subtracted
  - Edge fillet R2.0 on outer edges

Usage:
  run_journal.exe create_clevis_mount.py [output_path.prt]
"""

import sys
import os
from pathlib import Path
import subprocess

import NXOpen
import NXOpen.UF

# ---------------------------------------------------------------------------
# Parametric Constants (mm)
# ---------------------------------------------------------------------------
BASE_LENGTH       = 60.0
BASE_WIDTH        = 20.0
BASE_HEIGHT       = 12.0
ARM_THICKNESS     = 12.0
ARM_HEIGHT        = 48.0
GAP_WIDTH         = 24.0
BOSS_DIAMETER     = 24.0
BOSS_LENGTH       = 12.0
PIN_HOLE_DIAMETER = 10.0
EDGE_FILLET       = 2.0

# Derived
HALF_BL  = BASE_LENGTH / 2.0   # 30.0
HALF_BW  = BASE_WIDTH  / 2.0   # 10.0
ARM_CX_L = -HALF_BL + ARM_THICKNESS / 2.0   # -24.0  (left arm centre X)
ARM_CX_R =  HALF_BL - ARM_THICKNESS / 2.0   #  24.0  (right arm centre X)
ARM_CZ   = BASE_HEIGHT + ARM_HEIGHT / 2.0   #  36.0  (arm centre Z)


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
def _output_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "clevis_mount.prt"


# ---------------------------------------------------------------------------
# Helper: boolean unite
# ---------------------------------------------------------------------------
def _perform_unite(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body)
                    break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body)
                    break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Helper: boolean subtract
# ---------------------------------------------------------------------------
def _perform_subtract(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body)
                    break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body)
                    break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Helper: create cylinder feature
# ---------------------------------------------------------------------------
def _create_cylinder(work_part, origin, direction_vec, diameter_expr, height_expr):
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        direction = work_part.Directions.CreateDirection(
            origin, direction_vec, NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        builder.Diameter.RightHandSide = diameter_expr
        builder.Height.RightHandSide   = height_expr
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = direction
        feat = builder.Commit()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


# ---------------------------------------------------------------------------
# Helper: create block (cuboid) feature
# ---------------------------------------------------------------------------
def _create_block(work_part, corner_origin, length_str, width_str, height_str):
    builder = work_part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(corner_origin, length_str, width_str, height_str)
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


# ---------------------------------------------------------------------------
# Helper: edge blend (fillet) — single group
# ---------------------------------------------------------------------------
def _add_edge_blend_group(work_part, edges, radius_expr):
    if not edges:
        return
    builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        collector = work_part.ScCollectors.CreateCollector()
        rule = work_part.ScRuleFactory.CreateRuleEdgeMultipleSeedTangent(
            edges, 0.5, True
        )
        collector.ReplaceRules([rule], False)
        builder.Tolerance = 0.01
        builder.AllInstancesOption = False
        builder.RemoveSelfIntersection = True
        builder.ConvexConcaveY = False
        builder.RollOverSmoothEdge = True
        builder.RollOntoEdge = True
        builder.MoveSharpEdge = True
        builder.OverlapOption = NXOpen.Features.EdgeBlendBuilder.Overlap.AnyConvexityRollOver
        builder.BlendOrder = NXOpen.Features.EdgeBlendBuilder.OrderOfBlending.ConvexFirst
        builder.SetbackOption = NXOpen.Features.EdgeBlendBuilder.Setback.SeparateFromCorner
        builder.AddChainset(collector, radius_expr)
        builder.CommitFeature()
    finally:
        builder.Destroy()


def _add_edge_blend(work_part, edges, radius_expr):
    """Apply edge blend one edge at a time; silently skip edges that cause overlap conflicts."""
    if not edges:
        print("[WARN] No edges provided for fillet, skipping.")
        return
    applied = 0
    failed  = 0
    for edge in edges:
        try:
            _add_edge_blend_group(work_part, [edge], radius_expr)
            applied += 1
        except Exception:
            failed += 1
    print("[OK] Fillet: {} edges blended, {} skipped (overlap/conflict).".format(applied, failed))


# ---------------------------------------------------------------------------
# Helper: get all edges of a body
# ---------------------------------------------------------------------------
def _get_body_edges(body):
    try:
        return list(body.GetEdges() or [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Helper: update result watcher files
# ---------------------------------------------------------------------------
def _update_result_files(output_path):
    try:
        abs_path_str = str(output_path.resolve())
        (output_path.parent / "latest_nx_result.txt").write_text(abs_path_str, encoding="utf-8")

        project_root = Path(__file__).parent.parent.parent.parent.resolve()
        (project_root / "latest_nx_result.txt").write_text(abs_path_str, encoding="utf-8")

        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        ugs_router = None
        for cand in [base_path / "NXBIN" / "ugs_router.exe", base_path / "UGII" / "ugs_router.exe"]:
            if cand.exists():
                ugs_router = cand
                break
        if ugs_router is None:
            ugs_router = Path(r"C:\Program Files\Siemens\NX2206\NXBIN\ugs_router.exe")

        (project_root / "open_current_nx_result.cmd").write_text(
            '@echo off\nstart "" "{}" -ug -use_file_dir "{}"\n'.format(ugs_router, abs_path_str),
            encoding="utf-8"
        )
        (project_root / "open_latest_nx_result.vbs").write_text(
            'Set shell = CreateObject("WScript.Shell")\n'
            'shell.Run """{}""  -ug -use_file_dir ""{}""\", 0, False\n'.format(ugs_router, abs_path_str),
            encoding="utf-8"
        )
        print("[OK] Result files updated.")
    except Exception as exc:
        print("[WARN] Could not update result files: {}".format(exc))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            output_path.unlink()
            print("[OK] Removed existing part: {}".format(output_path))
        except Exception as exc:
            print("[WARN] Could not remove existing file: {}".format(exc))

    session   = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    print("=" * 60)
    print("  CREATING PARAMETRIC CLEVIS MOUNT")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Named NX Expressions
    # ------------------------------------------------------------------
    for name, val in [
        ("BASE_LENGTH",       BASE_LENGTH),
        ("BASE_WIDTH",        BASE_WIDTH),
        ("BASE_HEIGHT",       BASE_HEIGHT),
        ("ARM_THICKNESS",     ARM_THICKNESS),
        ("ARM_HEIGHT",        ARM_HEIGHT),
        ("GAP_WIDTH",         GAP_WIDTH),
        ("BOSS_DIAMETER",     BOSS_DIAMETER),
        ("BOSS_LENGTH",       BOSS_LENGTH),
        ("PIN_HOLE_DIAMETER", PIN_HOLE_DIAMETER),
        ("EDGE_FILLET",       EDGE_FILLET),
        ("HALF_BL",           HALF_BL),
        ("HALF_BW",           HALF_BW),
        ("ARM_CX_L",          ARM_CX_L),
        ("ARM_CX_R",          ARM_CX_R),
        ("ARM_CZ",            ARM_CZ),
    ]:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, val))
    print("[OK] Named expressions created.")

    # ------------------------------------------------------------------
    # 2. Base rectangular block
    #    Corner at (-HALF_BL, -HALF_BW, 0)
    # ------------------------------------------------------------------
    print("[...] Creating base block {}x{}x{}mm...".format(BASE_LENGTH, BASE_WIDTH, BASE_HEIGHT))
    base_corner = NXOpen.Point3d(-HALF_BL, -HALF_BW, 0.0)
    main_body = _create_block(work_part, base_corner,
                              "BASE_LENGTH", "BASE_WIDTH", "BASE_HEIGHT")
    print("[OK] Base block created.")

    # ------------------------------------------------------------------
    # 3. Left arm
    #    Corner: (-BASE_LENGTH/2, -BASE_WIDTH/2, BASE_HEIGHT) = (-30,-10,12)
    #    Size: ARM_THICKNESS x BASE_WIDTH x ARM_HEIGHT = 12 x 20 x 48
    # ------------------------------------------------------------------
    print("[...] Creating left arm {}x{}x{}mm...".format(ARM_THICKNESS, BASE_WIDTH, ARM_HEIGHT))
    left_arm_corner = NXOpen.Point3d(-HALF_BL, -HALF_BW, BASE_HEIGHT)
    left_arm_body = _create_block(work_part, left_arm_corner,
                                  "ARM_THICKNESS", "BASE_WIDTH", "ARM_HEIGHT")
    _perform_unite(work_part, main_body, left_arm_body)
    print("[OK] Left arm united.")

    # ------------------------------------------------------------------
    # 4. Right arm
    #    Corner: (BASE_LENGTH/2-ARM_THICKNESS, -BASE_WIDTH/2, BASE_HEIGHT) = (18,-10,12)
    #    Size: ARM_THICKNESS x BASE_WIDTH x ARM_HEIGHT = 12 x 20 x 48
    # ------------------------------------------------------------------
    print("[...] Creating right arm {}x{}x{}mm...".format(ARM_THICKNESS, BASE_WIDTH, ARM_HEIGHT))
    right_arm_corner = NXOpen.Point3d(HALF_BL - ARM_THICKNESS, -HALF_BW, BASE_HEIGHT)
    right_arm_body = _create_block(work_part, right_arm_corner,
                                   "ARM_THICKNESS", "BASE_WIDTH", "ARM_HEIGHT")
    _perform_unite(work_part, main_body, right_arm_body)
    print("[OK] Right arm united.")

    # ------------------------------------------------------------------
    # 5. Left cylindrical boss
    #    Center: (ARM_CX_L, -HALF_BW, ARM_CZ) = (-24, -10, 36)
    #    Direction: -Y, D=BOSS_DIAMETER, H=BOSS_LENGTH
    # ------------------------------------------------------------------
    print("[...] Creating left boss D{} L{}mm...".format(BOSS_DIAMETER, BOSS_LENGTH))
    left_boss_origin = NXOpen.Point3d(ARM_CX_L, -HALF_BW, ARM_CZ)
    left_boss_body = _create_cylinder(
        work_part, left_boss_origin, NXOpen.Vector3d(0.0, -1.0, 0.0),
        "BOSS_DIAMETER", "BOSS_LENGTH"
    )
    _perform_unite(work_part, main_body, left_boss_body)
    print("[OK] Left boss united.")

    # ------------------------------------------------------------------
    # 6. Right cylindrical boss
    #    Center: (ARM_CX_R, HALF_BW, ARM_CZ) = (24, 10, 36)
    #    Direction: +Y, D=BOSS_DIAMETER, H=BOSS_LENGTH
    # ------------------------------------------------------------------
    print("[...] Creating right boss D{} L{}mm...".format(BOSS_DIAMETER, BOSS_LENGTH))
    right_boss_origin = NXOpen.Point3d(ARM_CX_R, HALF_BW, ARM_CZ)
    right_boss_body = _create_cylinder(
        work_part, right_boss_origin, NXOpen.Vector3d(0.0, 1.0, 0.0),
        "BOSS_DIAMETER", "BOSS_LENGTH"
    )
    _perform_unite(work_part, main_body, right_boss_body)
    print("[OK] Right boss united.")

    # ------------------------------------------------------------------
    # 7. Left pin hole
    #    H1: center at (ARM_CX_L, 0, ARM_CZ) = (-24, 0, 36)
    #    Direction: -Y, D=PIN_HOLE_DIAMETER, depth=ARM_THICKNESS+BOSS_LENGTH=24
    #    Cylinder origin at Y=0, going -Y for 24mm (through arm half + boss)
    # ------------------------------------------------------------------
    pin_depth = ARM_THICKNESS + BOSS_LENGTH  # 24.0
    print("[...] Creating left pin hole D{} depth{}mm at (-24,0,36)...".format(
        PIN_HOLE_DIAMETER, pin_depth))
    left_hole_origin = NXOpen.Point3d(ARM_CX_L, 0.0, ARM_CZ)
    left_hole_body = _create_cylinder(
        work_part, left_hole_origin, NXOpen.Vector3d(0.0, -1.0, 0.0),
        "PIN_HOLE_DIAMETER", str(pin_depth)
    )
    _perform_subtract(work_part, main_body, left_hole_body)
    print("[OK] Left pin hole subtracted.")

    # ------------------------------------------------------------------
    # 8. Right pin hole
    #    H2: center at (ARM_CX_R, 0, ARM_CZ) = (24, 0, 36)
    #    Direction: +Y, D=PIN_HOLE_DIAMETER, depth=ARM_THICKNESS+BOSS_LENGTH=24
    # ------------------------------------------------------------------
    print("[...] Creating right pin hole D{} depth{}mm at (24,0,36)...".format(
        PIN_HOLE_DIAMETER, pin_depth))
    right_hole_origin = NXOpen.Point3d(ARM_CX_R, 0.0, ARM_CZ)
    right_hole_body = _create_cylinder(
        work_part, right_hole_origin, NXOpen.Vector3d(0.0, 1.0, 0.0),
        "PIN_HOLE_DIAMETER", str(pin_depth)
    )
    _perform_subtract(work_part, main_body, right_hole_body)
    print("[OK] Right pin hole subtracted.")

    # ------------------------------------------------------------------
    # 9. Edge fillet R2.0
    # ------------------------------------------------------------------
    print("[...] Applying edge fillet R{}mm...".format(EDGE_FILLET))
    all_edges = _get_body_edges(main_body)
    if all_edges:
        _add_edge_blend(work_part, all_edges, "EDGE_FILLET")
    else:
        print("[WARN] No edges found for fillet.")

    # ------------------------------------------------------------------
    # 10. ISO view
    # ------------------------------------------------------------------
    try:
        work_part.ModelingViews.WorkView.Fit()
        try:
            work_part.ModelingViews.WorkView.Orient("ISO")
        except Exception:
            pass
        print("[OK] View set to ISO.")
    except Exception as exc:
        print("[WARN] Could not set view: {}".format(exc))

    # ------------------------------------------------------------------
    # 11. Save part
    # ------------------------------------------------------------------
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("[OK] Part saved -> {}".format(output_path))

    # ------------------------------------------------------------------
    # 12. Export STEP
    # ------------------------------------------------------------------
    step_path = output_path.with_suffix(".stp")
    print("[...] Exporting STEP -> {}".format(step_path))
    try:
        step_exp = session.DexManager.CreateStepCreator()
        step_exp.ObjectTypes.Solids = True
        step_exp.OutputFile = str(step_path)
        step_exp.Commit()
        step_exp.Destroy()
        print("[OK] STEP exported -> {}".format(step_path))
    except Exception as exc:
        print("[WARN] STEP export failed: {}".format(exc))

    # ------------------------------------------------------------------
    # 13. Export STL
    # ------------------------------------------------------------------
    stl_path = output_path.with_suffix(".stl")
    print("[...] Exporting STL -> {}".format(stl_path))
    try:
        stl_exp = session.DexManager.CreateStlCreator()
        stl_exp.OutputFile = str(stl_path)
        stl_exp.Commit()
        stl_exp.Destroy()
        print("[OK] STL exported -> {}".format(stl_path))
    except Exception as exc:
        print("[WARN] STL export failed: {}".format(exc))

    # ------------------------------------------------------------------
    # 14. Update result watcher files
    # ------------------------------------------------------------------
    _update_result_files(output_path)

    # ------------------------------------------------------------------
    # 15. Auto-open in NX GUI
    # ------------------------------------------------------------------
    try:
        base_dir  = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        ugs_router = None
        for cand in [base_path / "NXBIN" / "ugs_router.exe", base_path / "UGII" / "ugs_router.exe"]:
            if cand.exists():
                ugs_router = cand
                break
        if ugs_router:
            subprocess.Popen([str(ugs_router), "-ug", "-use_file_dir", str(output_path.resolve())])
            print("[OK] NX GUI launched -> opening {}".format(output_path.name))
        else:
            print("[WARN] ugs_router.exe not found -- open the part manually in NX.")
    except Exception as exc:
        print("[WARN] Could not auto-open in NX GUI: {}".format(exc))

    print("=" * 60)
    print("[DONE] Clevis mount complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
