"""
create_clevis_mount_v2.py
==========================
NX Journal: fully parametric clevis mount with stepped bosses.

Feature order:
  1.  Base rectangular block (full height)
  2.  U-slot subtract (creates U-bracket with two arms)
  3.  Left boss flange  cylinder (extrude from arm outer face)
  4.  Left boss hub     cylinder (stepped, on top of flange)
  5.  Left pin through-hole (through hub + flange + arm)
  6.  Right boss flange cylinder (mirrored via symmetric placement)
  7.  Right boss hub    cylinder
  8.  Right pin through-hole
  9.  Edge blends (per-edge, skipping conflicts)
  10. ISO view
  11. Save .prt
  12. Export STEP / STL

Geometry (origin at centre of bottom face of base, (0,0,0)):

  BASE_LENGTH x BASE_WIDTH x TOTAL_HEIGHT   full envelope
  Slot cuts out centre from Z=BASE_HEIGHT to top, leaving two vertical arms.

  Left arm  outer X face : X = -HALF_BL
  Right arm outer X face : X = +HALF_BL
  Boss axis is centred at (±HALF_BL, 0, BOSS_CZ) pointing outward in ±X.

All dimensions are registered as NX Expressions.
"""

import sys
import os
from pathlib import Path
import subprocess

import NXOpen
import NXOpen.UF

# ---------------------------------------------------------------------------
# Parametric Constants  (mm)
# ---------------------------------------------------------------------------
BASE_LENGTH     = 76.0    # X extent of full bracket
BASE_WIDTH      = 28.0    # Y extent
BASE_HEIGHT     = 12.0    # Z: base bridge / bottom thickness
ARM_THICKNESS   = 14.0    # X: arm wall thickness
ARM_HEIGHT      = 48.0    # Z: arm height above base top face
SLOT_WIDTH      = BASE_LENGTH - 2.0 * ARM_THICKNESS   # 48.0 — inner X gap
BOSS_FLANGE_DIA = 30.0    # outer flange diameter
BOSS_HUB_DIA    = 22.0    # hub cylinder diameter
BOSS_FLANGE_LEN = 6.0     # flange extrusion length from arm outer face
BOSS_HUB_LEN    = 9.0     # hub additional extrusion beyond flange face
PIN_HOLE_DIA    = 10.0    # co-axial through-hole diameter
EDGE_FILLET     = 2.5     # edge blend radius

# Derived
HALF_BL  = BASE_LENGTH / 2.0           # 38.0
HALF_BW  = BASE_WIDTH  / 2.0           # 14.0
TOTAL_H  = BASE_HEIGHT + ARM_HEIGHT    # 60.0
BOSS_CZ  = BASE_HEIGHT + ARM_HEIGHT / 2.0   # 36.0  (arm mid-height)
# Through-hole total depth = arm wall + flange + hub
PIN_DEPTH = ARM_THICKNESS + BOSS_FLANGE_LEN + BOSS_HUB_LEN   # 29.0


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
def _output_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "clevis_mount_v2.prt"


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def _create_block(work_part, corner_origin, length_str, width_str, height_str):
    builder = work_part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(corner_origin, length_str, width_str, height_str)
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create, NXOpen.Body.Null)
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


def _create_cylinder(work_part, origin, direction_vec, diameter_expr, height_expr):
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        direction = work_part.Directions.CreateDirection(
            origin, direction_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Diameter.RightHandSide = diameter_expr
        builder.Height.RightHandSide   = height_expr
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = direction
        feat = builder.Commit()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


def _perform_unite(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body); break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body); break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()


def _perform_subtract(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body); break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body); break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Edge blend helpers
# ---------------------------------------------------------------------------
def _blend_single_edge(work_part, edge, radius_expr):
    builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        collector = work_part.ScCollectors.CreateCollector()
        rule = work_part.ScRuleFactory.CreateRuleEdgeMultipleSeedTangent([edge], 0.5, True)
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
    """Apply blend one edge at a time; silently skip overlap conflicts."""
    applied = failed = 0
    for edge in edges:
        try:
            _blend_single_edge(work_part, edge, radius_expr)
            applied += 1
        except Exception:
            failed += 1
    print("[OK] Fillet: {} blended, {} skipped (overlap/conflict).".format(applied, failed))


def _get_body_edges(body):
    try:
        return list(body.GetEdges() or [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Result-watcher helpers
# ---------------------------------------------------------------------------
def _update_result_files(output_path):
    try:
        abs_str = str(output_path.resolve())
        (output_path.parent / "latest_nx_result.txt").write_text(abs_str, encoding="utf-8")
        project_root = Path(__file__).parent.parent.parent.parent.resolve()
        (project_root / "latest_nx_result.txt").write_text(abs_str, encoding="utf-8")

        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        ugs_router = None
        for cand in [base_path / "NXBIN" / "ugs_router.exe",
                     base_path / "UGII"  / "ugs_router.exe"]:
            if cand.exists():
                ugs_router = cand
                break
        if ugs_router is None:
            ugs_router = Path(r"C:\Program Files\Siemens\NX2206\NXBIN\ugs_router.exe")

        (project_root / "open_current_nx_result.cmd").write_text(
            '@echo off\nstart "" "{}" -ug -use_file_dir "{}"\n'.format(ugs_router, abs_str),
            encoding="utf-8")
        (project_root / "open_latest_nx_result.vbs").write_text(
            'Set shell = CreateObject("WScript.Shell")\n'
            'shell.Run """{}""  -ug -use_file_dir ""{}""\", 0, False\n'.format(ugs_router, abs_str),
            encoding="utf-8")
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
            print("[WARN] Could not remove: {}".format(exc))

    session   = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    print("=" * 60)
    print("  CREATING PARAMETRIC CLEVIS MOUNT V2 (stepped boss)")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Named NX Expressions
    # ------------------------------------------------------------------
    for name, val in [
        ("BASE_LENGTH",     BASE_LENGTH),
        ("BASE_WIDTH",      BASE_WIDTH),
        ("BASE_HEIGHT",     BASE_HEIGHT),
        ("ARM_THICKNESS",   ARM_THICKNESS),
        ("ARM_HEIGHT",      ARM_HEIGHT),
        ("SLOT_WIDTH",      SLOT_WIDTH),
        ("BOSS_FLANGE_DIA", BOSS_FLANGE_DIA),
        ("BOSS_HUB_DIA",    BOSS_HUB_DIA),
        ("BOSS_FLANGE_LEN", BOSS_FLANGE_LEN),
        ("BOSS_HUB_LEN",    BOSS_HUB_LEN),
        ("PIN_HOLE_DIA",    PIN_HOLE_DIA),
        ("PIN_DEPTH",       PIN_DEPTH),
        ("EDGE_FILLET",     EDGE_FILLET),
        ("TOTAL_H",         TOTAL_H),
        ("BOSS_CZ",         BOSS_CZ),
    ]:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, val))
    print("[OK] Named expressions created.")

    # ------------------------------------------------------------------
    # 2. Full rectangular block (Step 1 — base body)
    #    Corner: (-HALF_BL, -HALF_BW, 0)
    #    Dimensions: BASE_LENGTH x BASE_WIDTH x TOTAL_H
    # ------------------------------------------------------------------
    print("[...] Step 1: Creating full envelope block {}x{}x{}mm...".format(
        BASE_LENGTH, BASE_WIDTH, TOTAL_H))
    full_corner = NXOpen.Point3d(-HALF_BL, -HALF_BW, 0.0)
    main_body = _create_block(work_part, full_corner,
                              "BASE_LENGTH", "BASE_WIDTH", "TOTAL_H")
    print("[OK] Full block created.")

    # ------------------------------------------------------------------
    # 3. U-slot subtract (Step 2 — Extrude Remove)
    #    Removes centre material from Z=BASE_HEIGHT to top,
    #    leaving left arm (X: -38→-24) and right arm (X: +24→+38).
    #    Slot: SLOT_WIDTH x BASE_WIDTH x ARM_HEIGHT
    #    Corner: (-SLOT_WIDTH/2, -HALF_BW, BASE_HEIGHT)
    # ------------------------------------------------------------------
    slot_half = SLOT_WIDTH / 2.0    # 24.0
    print("[...] Step 2: Cutting U-slot {}x{}x{}mm to create two arms...".format(
        SLOT_WIDTH, BASE_WIDTH, ARM_HEIGHT))
    slot_corner = NXOpen.Point3d(-slot_half, -HALF_BW, BASE_HEIGHT)
    slot_body = _create_block(work_part, slot_corner,
                              "SLOT_WIDTH", "BASE_WIDTH", "ARM_HEIGHT")
    _perform_subtract(work_part, main_body, slot_body)
    print("[OK] U-bracket formed — left arm X:[{},{}], right arm X:[{},{}].".format(
        -HALF_BL, -slot_half, slot_half, HALF_BL))

    # ------------------------------------------------------------------
    # 4. Left boss flange (Step 3)
    #    Outer X face of left arm is at X=-HALF_BL=-38.
    #    Flange origin: (-38, 0, BOSS_CZ), direction: -X
    #    D=BOSS_FLANGE_DIA, H=BOSS_FLANGE_LEN
    # ------------------------------------------------------------------
    print("[...] Step 3: Creating left boss flange D{} L{}mm...".format(
        BOSS_FLANGE_DIA, BOSS_FLANGE_LEN))
    lf_origin = NXOpen.Point3d(-HALF_BL, 0.0, BOSS_CZ)
    left_flange_body = _create_cylinder(
        work_part, lf_origin, NXOpen.Vector3d(-1.0, 0.0, 0.0),
        "BOSS_FLANGE_DIA", "BOSS_FLANGE_LEN")
    _perform_unite(work_part, main_body, left_flange_body)
    print("[OK] Left flange united.")

    # ------------------------------------------------------------------
    # 5. Left boss hub (Step 4 — stepped, extends beyond flange)
    #    Hub origin: (-HALF_BL - BOSS_FLANGE_LEN, 0, BOSS_CZ) = (-44, 0, 36)
    #    Direction: -X, D=BOSS_HUB_DIA, H=BOSS_HUB_LEN
    # ------------------------------------------------------------------
    print("[...] Step 4: Creating left boss hub D{} L{}mm...".format(
        BOSS_HUB_DIA, BOSS_HUB_LEN))
    lh_origin = NXOpen.Point3d(-HALF_BL - BOSS_FLANGE_LEN, 0.0, BOSS_CZ)
    left_hub_body = _create_cylinder(
        work_part, lh_origin, NXOpen.Vector3d(-1.0, 0.0, 0.0),
        "BOSS_HUB_DIA", "BOSS_HUB_LEN")
    _perform_unite(work_part, main_body, left_hub_body)
    print("[OK] Left hub united.")

    # ------------------------------------------------------------------
    # 6. Left through-hole (Step 5)
    #    Starts at outer hub face X = -(HALF_BL + BOSS_FLANGE_LEN + BOSS_HUB_LEN)
    #                              = -(38+6+9) = -53
    #    Direction: +X, D=PIN_HOLE_DIA, H=PIN_DEPTH=29
    #    Cuts through: hub (9) + flange (6) + arm wall (14) = 29mm total
    # ------------------------------------------------------------------
    pin_x_l = -(HALF_BL + BOSS_FLANGE_LEN + BOSS_HUB_LEN)   # -53
    print("[...] Step 5: Creating left through-hole D{} depth{}mm...".format(
        PIN_HOLE_DIA, PIN_DEPTH))
    lhole_origin = NXOpen.Point3d(pin_x_l, 0.0, BOSS_CZ)
    lhole_body = _create_cylinder(
        work_part, lhole_origin, NXOpen.Vector3d(1.0, 0.0, 0.0),
        "PIN_HOLE_DIA", "PIN_DEPTH")
    _perform_subtract(work_part, main_body, lhole_body)
    print("[OK] Left through-hole subtracted.")

    # ------------------------------------------------------------------
    # 7. Right boss flange (Step 6 — mirror of Step 3)
    #    Outer X face of right arm at X=+HALF_BL=+38
    #    Direction: +X, D=BOSS_FLANGE_DIA, H=BOSS_FLANGE_LEN
    # ------------------------------------------------------------------
    print("[...] Step 6: Creating right boss flange D{} L{}mm (mirror)...".format(
        BOSS_FLANGE_DIA, BOSS_FLANGE_LEN))
    rf_origin = NXOpen.Point3d(HALF_BL, 0.0, BOSS_CZ)
    right_flange_body = _create_cylinder(
        work_part, rf_origin, NXOpen.Vector3d(1.0, 0.0, 0.0),
        "BOSS_FLANGE_DIA", "BOSS_FLANGE_LEN")
    _perform_unite(work_part, main_body, right_flange_body)
    print("[OK] Right flange united.")

    # ------------------------------------------------------------------
    # 8. Right boss hub (Step 7 — mirror of Step 4)
    #    Hub origin: (+HALF_BL + BOSS_FLANGE_LEN, 0, BOSS_CZ) = (+44, 0, 36)
    #    Direction: +X
    # ------------------------------------------------------------------
    print("[...] Step 7: Creating right boss hub D{} L{}mm (mirror)...".format(
        BOSS_HUB_DIA, BOSS_HUB_LEN))
    rh_origin = NXOpen.Point3d(HALF_BL + BOSS_FLANGE_LEN, 0.0, BOSS_CZ)
    right_hub_body = _create_cylinder(
        work_part, rh_origin, NXOpen.Vector3d(1.0, 0.0, 0.0),
        "BOSS_HUB_DIA", "BOSS_HUB_LEN")
    _perform_unite(work_part, main_body, right_hub_body)
    print("[OK] Right hub united.")

    # ------------------------------------------------------------------
    # 9. Right through-hole (Step 8 — mirror of Step 5)
    #    Starts at outer hub face X=+(HALF_BL+BOSS_FLANGE_LEN+BOSS_HUB_LEN)=+53
    #    Direction: -X, D=PIN_HOLE_DIA, H=PIN_DEPTH=29
    # ------------------------------------------------------------------
    pin_x_r = HALF_BL + BOSS_FLANGE_LEN + BOSS_HUB_LEN   # +53
    print("[...] Step 8: Creating right through-hole D{} depth{}mm (mirror)...".format(
        PIN_HOLE_DIA, PIN_DEPTH))
    rhole_origin = NXOpen.Point3d(pin_x_r, 0.0, BOSS_CZ)
    rhole_body = _create_cylinder(
        work_part, rhole_origin, NXOpen.Vector3d(-1.0, 0.0, 0.0),
        "PIN_HOLE_DIA", "PIN_DEPTH")
    _perform_subtract(work_part, main_body, rhole_body)
    print("[OK] Right through-hole subtracted.")

    # ------------------------------------------------------------------
    # 10. Edge Blend (Step 9)
    #     Applied per-edge; overlap conflicts silently skipped.
    # ------------------------------------------------------------------
    print("[...] Step 9: Applying edge blends R{}mm...".format(EDGE_FILLET))
    all_edges = _get_body_edges(main_body)
    if all_edges:
        _add_edge_blend(work_part, all_edges, "EDGE_FILLET")
    else:
        print("[WARN] No edges found for fillet.")

    # ------------------------------------------------------------------
    # 11. ISO view
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
    # 12. Save part (Step 9)
    # ------------------------------------------------------------------
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("[OK] Part saved -> {}".format(output_path))

    # ------------------------------------------------------------------
    # 13. Export STEP (Step 10)
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
    # 14. Export STL (Step 11)
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
    # 15. Update result watcher files
    # ------------------------------------------------------------------
    _update_result_files(output_path)

    # ------------------------------------------------------------------
    # 16. Auto-open in NX GUI
    # ------------------------------------------------------------------
    try:
        base_dir  = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        ugs_router = None
        for cand in [base_path / "NXBIN" / "ugs_router.exe",
                     base_path / "UGII"  / "ugs_router.exe"]:
            if cand.exists():
                ugs_router = cand
                break
        if ugs_router:
            subprocess.Popen([str(ugs_router), "-ug", "-use_file_dir",
                              str(output_path.resolve())])
            print("[OK] NX GUI launched -> opening {}".format(output_path.name))
        else:
            print("[WARN] ugs_router.exe not found -- open part manually in NX.")
    except Exception as exc:
        print("[WARN] Could not auto-open in NX GUI: {}".format(exc))

    print("=" * 60)
    print("[DONE] Clevis mount v2 complete.")
    print("  Envelope:  {}L x {}W x {}H mm".format(BASE_LENGTH, BASE_WIDTH, TOTAL_H))
    print("  Arms:      {}mm thick, {}mm tall, {}mm gap".format(
        ARM_THICKNESS, ARM_HEIGHT, SLOT_WIDTH))
    print("  Bosses:    flange D{}/L{}, hub D{}/L{}".format(
        BOSS_FLANGE_DIA, BOSS_FLANGE_LEN, BOSS_HUB_DIA, BOSS_HUB_LEN))
    print("  Pin holes: D{} coaxial through hub+flange+arm".format(PIN_HOLE_DIA))
    print("=" * 60)


if __name__ == "__main__":
    main()
