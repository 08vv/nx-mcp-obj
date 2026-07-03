"""
create_threaded_clevis_block.py
================================
NX Journal that creates a parametric threaded clevis block.
All dimensions are stored as named NX Expressions.

Geometry (origin at center of bottom face of block, i.e. (0,0,0)):
  - Base rectangular block: 50 x 24 x 24 mm, centered in X and Y, from Z=0 to Z=24
  - Left/Right side cylindrical bosses: D22, L10, projecting outward in -X / +X
  - Left/Right shoulders: D16, L6, beyond the bosses
  - Left/Right threaded shafts: D12, L18, beyond the shoulders
  - Center through hole: D14, through full block height
  - Edge fillet R2.5 on outer edges of the rectangular block

Usage:
  run_journal.exe create_threaded_clevis_block.py [output_path.prt]

Named Expressions:
  BLOCK_LENGTH=50, BLOCK_WIDTH=24, BLOCK_HEIGHT=24,
  SIDE_BOSS_DIA=22, SIDE_BOSS_LEN=10,
  CENTER_HOLE_DIA=14,
  THREAD_MAJOR_DIA=12, THREAD_LENGTH=18,
  THREAD_SHOULDER_DIA=16, THREAD_SHOULDER_LEN=6,
  EDGE_FILLET=2.5
"""

import math
import sys
import os
from pathlib import Path
import subprocess

import NXOpen
import NXOpen.UF

# ---------------------------------------------------------------------------
# Parametric Constants (mm)
# ---------------------------------------------------------------------------
BLOCK_LENGTH         = 50.0
BLOCK_WIDTH          = 24.0
BLOCK_HEIGHT         = 24.0
SIDE_BOSS_DIA        = 22.0
SIDE_BOSS_LEN        = 10.0
CENTER_HOLE_DIA      = 14.0
THREAD_MAJOR_DIA     = 12.0
THREAD_LENGTH        = 18.0
THREAD_SHOULDER_DIA  = 16.0
THREAD_SHOULDER_LEN  = 6.0
EDGE_FILLET          = 2.5

# Derived
HALF_L = BLOCK_LENGTH / 2.0    # 25.0
HALF_W = BLOCK_WIDTH  / 2.0    # 12.0
HALF_H = BLOCK_HEIGHT / 2.0    # 12.0  (cylinder/boss axis height)


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
def _output_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "threaded_clevis_block.prt"


# ---------------------------------------------------------------------------
# Helper: boolean unite
# ---------------------------------------------------------------------------
def _perform_unite(work_part, target_body, tool_body):
    """Unite tool_body into target_body."""
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
    """Subtract tool_body from target_body."""
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
# Helper: create a cylinder feature
# ---------------------------------------------------------------------------
def _create_cylinder(work_part, origin, direction_vec, diameter_expr, height_expr):
    """
    Create a cylinder feature.
    origin        : NXOpen.Point3d  -- base-centre of the cylinder
    direction_vec : NXOpen.Vector3d -- axis direction
    diameter_expr : str  expression for diameter
    height_expr   : str  expression for height
    Returns body of the new cylinder.
    """
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
# Helper: create a block (cuboid) feature
# ---------------------------------------------------------------------------
def _create_block(work_part, corner_origin, length_str, width_str, height_str):
    """
    Create a solid block feature from corner_origin extending by
    length_str(X) x width_str(Y) x height_str(Z).
    Returns the body.
    """
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
    """Apply an edge blend (fillet) to a list of edges as a single feature."""
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
# Helper: update result files (latest_nx_result.txt, cmd, vbs)
# ---------------------------------------------------------------------------
def _update_result_files(output_path):
    try:
        abs_path_str = str(output_path.resolve())

        latest_file = output_path.parent / "latest_nx_result.txt"
        latest_file.write_text(abs_path_str, encoding="utf-8")

        project_root = Path(__file__).parent.parent.parent.parent.resolve()
        root_latest = project_root / "latest_nx_result.txt"
        root_latest.write_text(abs_path_str, encoding="utf-8")

        # Resolve ugs_router path
        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        ugs_router = None
        for cand in [base_path / "NXBIN" / "ugs_router.exe", base_path / "UGII" / "ugs_router.exe"]:
            if cand.exists():
                ugs_router = cand
                break
        if ugs_router is None:
            ugs_router = Path(r"C:\Program Files\Siemens\NX2206\NXBIN\ugs_router.exe")

        cmd_path = project_root / "open_current_nx_result.cmd"
        cmd_path.write_text(
            '@echo off\nstart "" "{}" -ug -use_file_dir "{}"\n'.format(ugs_router, abs_path_str),
            encoding="utf-8"
        )
        vbs_path = project_root / "open_latest_nx_result.vbs"
        vbs_path.write_text(
            'Set shell = CreateObject("WScript.Shell")\nshell.Run """{}""  -ug -use_file_dir ""{}""\", 0, False\n'.format(ugs_router, abs_path_str),
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

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    print("=" * 60)
    print("  CREATING PARAMETRIC THREADED CLEVIS BLOCK")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Register named NX Expressions
    # ------------------------------------------------------------------
    named_expressions = [
        ("BLOCK_LENGTH",        BLOCK_LENGTH),
        ("BLOCK_WIDTH",         BLOCK_WIDTH),
        ("BLOCK_HEIGHT",        BLOCK_HEIGHT),
        ("SIDE_BOSS_DIA",       SIDE_BOSS_DIA),
        ("SIDE_BOSS_LEN",       SIDE_BOSS_LEN),
        ("CENTER_HOLE_DIA",     CENTER_HOLE_DIA),
        ("THREAD_MAJOR_DIA",    THREAD_MAJOR_DIA),
        ("THREAD_LENGTH",       THREAD_LENGTH),
        ("THREAD_SHOULDER_DIA", THREAD_SHOULDER_DIA),
        ("THREAD_SHOULDER_LEN", THREAD_SHOULDER_LEN),
        ("EDGE_FILLET",         EDGE_FILLET),
        # Derived helpers
        ("HALF_BLOCK_L",        HALF_L),
        ("HALF_BLOCK_W",        HALF_W),
        ("HALF_BLOCK_H",        HALF_H),
    ]
    for name, value in named_expressions:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
    print("[OK] Named expressions created.")

    # ------------------------------------------------------------------
    # 2. Base rectangular block
    #    Corner at (-HALF_L, -HALF_W, 0) extends BLOCK_LENGTH x BLOCK_WIDTH x BLOCK_HEIGHT
    #    This places the center of the bottom face at (0,0,0).
    # ------------------------------------------------------------------
    print("[...] Creating base rectangular block {}x{}x{}mm...".format(
        BLOCK_LENGTH, BLOCK_WIDTH, BLOCK_HEIGHT))
    block_corner = NXOpen.Point3d(-HALF_L, -HALF_W, 0.0)
    main_body = _create_block(
        work_part, block_corner,
        "BLOCK_LENGTH", "BLOCK_WIDTH", "BLOCK_HEIGHT"
    )
    print("[OK] Base block created.")

    # ------------------------------------------------------------------
    # 3. Left cylindrical boss
    #    Origin at left face center: (-HALF_L, 0, HALF_H)
    #    Direction: -X, height = SIDE_BOSS_LEN
    # ------------------------------------------------------------------
    print("[...] Creating left side boss D{} L{}mm...".format(SIDE_BOSS_DIA, SIDE_BOSS_LEN))
    left_boss_origin = NXOpen.Point3d(-HALF_L, 0.0, HALF_H)
    left_boss_dir    = NXOpen.Vector3d(-1.0, 0.0, 0.0)
    left_boss_body = _create_cylinder(
        work_part, left_boss_origin, left_boss_dir,
        "SIDE_BOSS_DIA", "SIDE_BOSS_LEN"
    )
    _perform_unite(work_part, main_body, left_boss_body)
    print("[OK] Left boss united.")

    # ------------------------------------------------------------------
    # 4. Right cylindrical boss
    #    Origin at right face center: (HALF_L, 0, HALF_H), Direction: +X
    # ------------------------------------------------------------------
    print("[...] Creating right side boss D{} L{}mm...".format(SIDE_BOSS_DIA, SIDE_BOSS_LEN))
    right_boss_origin = NXOpen.Point3d(HALF_L, 0.0, HALF_H)
    right_boss_dir    = NXOpen.Vector3d(1.0, 0.0, 0.0)
    right_boss_body = _create_cylinder(
        work_part, right_boss_origin, right_boss_dir,
        "SIDE_BOSS_DIA", "SIDE_BOSS_LEN"
    )
    _perform_unite(work_part, main_body, right_boss_body)
    print("[OK] Right boss united.")

    # ------------------------------------------------------------------
    # 5. Left shoulder
    #    Origin at (-HALF_L - SIDE_BOSS_LEN, 0, HALF_H), Direction: -X
    # ------------------------------------------------------------------
    left_shoulder_x = -(HALF_L + SIDE_BOSS_LEN)  # -35
    print("[...] Creating left shoulder D{} L{}mm...".format(THREAD_SHOULDER_DIA, THREAD_SHOULDER_LEN))
    left_shoulder_origin = NXOpen.Point3d(left_shoulder_x, 0.0, HALF_H)
    left_shoulder_body = _create_cylinder(
        work_part, left_shoulder_origin, NXOpen.Vector3d(-1.0, 0.0, 0.0),
        "THREAD_SHOULDER_DIA", "THREAD_SHOULDER_LEN"
    )
    _perform_unite(work_part, main_body, left_shoulder_body)
    print("[OK] Left shoulder united.")

    # ------------------------------------------------------------------
    # 6. Right shoulder
    #    Origin at (HALF_L + SIDE_BOSS_LEN, 0, HALF_H), Direction: +X
    # ------------------------------------------------------------------
    right_shoulder_x = HALF_L + SIDE_BOSS_LEN  # 35
    print("[...] Creating right shoulder D{} L{}mm...".format(THREAD_SHOULDER_DIA, THREAD_SHOULDER_LEN))
    right_shoulder_origin = NXOpen.Point3d(right_shoulder_x, 0.0, HALF_H)
    right_shoulder_body = _create_cylinder(
        work_part, right_shoulder_origin, NXOpen.Vector3d(1.0, 0.0, 0.0),
        "THREAD_SHOULDER_DIA", "THREAD_SHOULDER_LEN"
    )
    _perform_unite(work_part, main_body, right_shoulder_body)
    print("[OK] Right shoulder united.")

    # ------------------------------------------------------------------
    # 7. Left threaded shaft
    #    Origin at (-HALF_L - SIDE_BOSS_LEN - THREAD_SHOULDER_LEN, 0, HALF_H)
    #    Direction: -X
    # ------------------------------------------------------------------
    left_thread_x = -(HALF_L + SIDE_BOSS_LEN + THREAD_SHOULDER_LEN)  # -41
    print("[...] Creating left threaded shaft D{} L{}mm...".format(THREAD_MAJOR_DIA, THREAD_LENGTH))
    left_thread_origin = NXOpen.Point3d(left_thread_x, 0.0, HALF_H)
    left_thread_body = _create_cylinder(
        work_part, left_thread_origin, NXOpen.Vector3d(-1.0, 0.0, 0.0),
        "THREAD_MAJOR_DIA", "THREAD_LENGTH"
    )
    _perform_unite(work_part, main_body, left_thread_body)
    print("[OK] Left threaded shaft united.")

    # ------------------------------------------------------------------
    # 8. Right threaded shaft
    #    Origin at (HALF_L + SIDE_BOSS_LEN + THREAD_SHOULDER_LEN, 0, HALF_H)
    #    Direction: +X
    # ------------------------------------------------------------------
    right_thread_x = HALF_L + SIDE_BOSS_LEN + THREAD_SHOULDER_LEN  # 41
    print("[...] Creating right threaded shaft D{} L{}mm...".format(THREAD_MAJOR_DIA, THREAD_LENGTH))
    right_thread_origin = NXOpen.Point3d(right_thread_x, 0.0, HALF_H)
    right_thread_body = _create_cylinder(
        work_part, right_thread_origin, NXOpen.Vector3d(1.0, 0.0, 0.0),
        "THREAD_MAJOR_DIA", "THREAD_LENGTH"
    )
    _perform_unite(work_part, main_body, right_thread_body)
    print("[OK] Right threaded shaft united.")

    # ------------------------------------------------------------------
    # 9. Center through hole (subtract cylinder)
    #    A cylinder D=CENTER_HOLE_DIA, slightly taller than BLOCK_HEIGHT,
    #    centered at (0,0,-1) in +Z direction cuts through from z=-1 to z=25
    # ------------------------------------------------------------------
    print("[...] Creating center through hole D{}mm...".format(CENTER_HOLE_DIA))
    hole_origin = NXOpen.Point3d(0.0, 0.0, -1.0)
    hole_dir    = NXOpen.Vector3d(0.0, 0.0, 1.0)
    hole_body = _create_cylinder(
        work_part, hole_origin, hole_dir,
        "CENTER_HOLE_DIA", str(BLOCK_HEIGHT + 2.0)
    )
    _perform_subtract(work_part, main_body, hole_body)
    print("[OK] Center through hole subtracted.")

    # ------------------------------------------------------------------
    # 10. Edge fillet on outer edges of rectangular block
    # ------------------------------------------------------------------
    print("[...] Applying edge fillet R{}mm to outer edges...".format(EDGE_FILLET))
    all_edges = _get_body_edges(main_body)
    if all_edges:
        _add_edge_blend(work_part, all_edges, "EDGE_FILLET")
    else:
        print("[WARN] No edges found for fillet.")

    # ------------------------------------------------------------------
    # 11. Set view to ISO
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
    # 12. Save part
    # ------------------------------------------------------------------
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("[OK] Part saved -> {}".format(output_path))

    # ------------------------------------------------------------------
    # 13. Export STEP
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
    # 14. Export STL
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
        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
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
    print("[DONE] Threaded clevis block complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
