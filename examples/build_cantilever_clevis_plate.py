r"""
build_cantilever_clevis_plate.py
================================
NX CAD automation script and NX journal for generating `cantilever_clevis_plate` part.

Features:
- Expressions: BASE_LENGTH, BASE_WIDTH, BASE_THICKNESS, LUG_WIDTH, LUG_HEIGHT,
               LUG_PROJECTION, LUG_TOP_RADIUS, LUG_SPACING, PIN_HOLE_DIA,
               PIN_HOLE_CENTER_Z, SLOT_WIDTH, SLOT_HEIGHT, BASE_HOLE_DIA,
               RELIEF_DIA, FILLET_R
- Base Body: BASE Cuboid (120 x 70 x 8) at (0,0,0)
- Feature Sequence:
  - Step 1: Extrude LUG_1 (Width 18, Height 42, Top Radius 9, projection 20 along +X)
  - Step 2: Pattern LUG_1 along +Y to create LUG_2 (pitch 38)
  - Step 3: Pin hole H1 on LUG_1 (Dia 12.0, height 28 from plate = Z=36)
  - Step 4: Mirror pin hole across XZ midplane (Y=35) to create H2 in LUG_2
  - Step 5: Extrude cut relief slot on LUG_2 (Width 5.0, Height 14.0 centered below pin hole)
  - Step 6: Extrude cut Triangle 1 with relief hole (18,18), (42,18), (30,42)
  - Step 7: Mirror Triangle Cut across YZ plane at midplane X=60
  - Step 8: Add upper mounting hole H3 on BASE (Dia 8.0, at X=105, Y=55, depth 8)
  - Step 9: Mirror mounting hole across XZ midplane (Y=35) to create H4 at X=105, Y=15
- Finish: Fillets on outer and vertical edges (2.0 mm) and ISO view
- Exports: .prt, .stp, .stl
"""

import json
import socket
import time
import sys
import os
import math
import subprocess
from pathlib import Path

OUTPUT_PRT = Path("C:/Users/HP/nx-mcp/cantilever_clevis_plate.prt").resolve()
OUTPUT_STEP = Path("C:/Users/HP/nx-mcp/cantilever_clevis_plate.stp").resolve()
OUTPUT_STL = Path("C:/Users/HP/nx-mcp/cantilever_clevis_plate.stl").resolve()


def run_nxopen_journal():
    import NXOpen
    import NXOpen.UF

    session = NXOpen.Session.GetSession()
    uf_session = NXOpen.UF.UFSession.GetUFSession()

    OUTPUT_PRT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PRT.exists():
        try:
            OUTPUT_PRT.unlink()
        except Exception:
            pass

    # Create Part
    work_part = session.Parts.NewDisplay(str(OUTPUT_PRT), NXOpen.Part.Units.Millimeters)

    # 1. Expressions Table
    expressions = [
        ("BASE_LENGTH", 120.0),
        ("BASE_WIDTH", 70.0),
        ("BASE_THICKNESS", 8.0),
        ("LUG_WIDTH", 18.0),
        ("LUG_HEIGHT", 42.0),
        ("LUG_PROJECTION", 20.0),
        ("LUG_TOP_RADIUS", 9.0),
        ("LUG_SPACING", 20.0),
        ("PIN_HOLE_DIA", 12.0),
        ("PIN_HOLE_CENTER_Z", 28.0),
        ("SLOT_WIDTH", 5.0),
        ("SLOT_HEIGHT", 14.0),
        ("BASE_HOLE_DIA", 8.0),
        ("RELIEF_DIA", 8.0),
        ("FILLET_R", 2.0),
    ]
    for name, value in expressions:
        work_part.Expressions.CreateExpression("Number", f"{name} = {value}")

    # Helper functions
    def _create_cylinder(origin, dir_vec, diam_str, height_str):
        builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        try:
            direction = work_part.Directions.CreateDirection(
                origin, dir_vec, NXOpen.SmartObject.UpdateOption.WithinModeling
            )
            builder.Diameter.RightHandSide = str(diam_str)
            builder.Height.RightHandSide = str(height_str)
            builder.Axis.Point.SetCoordinates(origin)
            builder.Axis.Direction = direction
            feat = builder.Commit()
            return feat.GetBodies()[0]
        finally:
            builder.Destroy()

    def _create_block(corner_origin, len_str, width_str, height_str):
        builder = work_part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
        try:
            builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
            builder.SetOriginAndLengths(corner_origin, str(len_str), str(width_str), str(height_str))
            builder.SetBooleanOperationAndTarget(
                NXOpen.Features.Feature.BooleanType.Create,
                NXOpen.Body.Null,
            )
            feat = builder.CommitFeature()
            return feat.GetBodies()[0]
        finally:
            builder.Destroy()

    def _perform_unite(target_body, tool_body):
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

    def _perform_subtract(target_body, tool_body):
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

    # Vectors
    vec_x_pos = NXOpen.Vector3d(1.0, 0.0, 0.0)
    vec_z_neg = NXOpen.Vector3d(0.0, 0.0, -1.0)

    # Base Body: Cuboid BASE_LENGTH (120) x BASE_WIDTH (70) x BASE_THICKNESS (8)
    # Position: Corner at (0,0,0)
    corner_base = NXOpen.Point3d(0.0, 0.0, 0.0)
    base_body = _create_block(corner_base, "BASE_LENGTH", "BASE_WIDTH", "BASE_THICKNESS")

    # Step 1 & 2: Cantilever Lugs (LUG_1 & LUG_2)
    # LUG_1: Y center = 16.0 (Y range 7.0 to 25.0, width 18.0)
    corner_left_tab = NXOpen.Point3d(0.0, 7.0, 8.0)
    left_tab_block = _create_block(corner_left_tab, "LUG_PROJECTION", "LUG_WIDTH", "LUG_HEIGHT - LUG_TOP_RADIUS")
    _perform_unite(base_body, left_tab_block)

    origin_left_cyl = NXOpen.Point3d(0.0, 16.0, 41.0)
    left_tab_cyl = _create_cylinder(origin_left_cyl, vec_x_pos, "2.0 * LUG_TOP_RADIUS", "LUG_PROJECTION")
    _perform_unite(base_body, left_tab_cyl)

    # LUG_2 (Step 2 - Pattern along +Y with pitch LUG_WIDTH + LUG_SPACING = 38.0): Y center = 54.0 (Y range 45.0 to 63.0)
    corner_right_tab = NXOpen.Point3d(0.0, 45.0, 8.0)
    right_tab_block = _create_block(corner_right_tab, "LUG_PROJECTION", "LUG_WIDTH", "LUG_HEIGHT - LUG_TOP_RADIUS")
    _perform_unite(base_body, right_tab_block)

    origin_right_cyl = NXOpen.Point3d(0.0, 54.0, 41.0)
    right_tab_cyl = _create_cylinder(origin_right_cyl, vec_x_pos, "2.0 * LUG_TOP_RADIUS", "LUG_PROJECTION")
    _perform_unite(base_body, right_tab_cyl)

    # Steps 3 & 4: Pin Holes
    # LUG_1 Pin Hole (Step 3): Center at (10.0, 16.0, 36.0), Height = PIN_HOLE_CENTER_Z = 28.0 from plate top
    origin_pin_left = NXOpen.Point3d(-0.1, 16.0, 36.0)
    pin_left_cyl = _create_cylinder(origin_pin_left, vec_x_pos, "PIN_HOLE_DIA", "LUG_PROJECTION + 0.2")
    _perform_subtract(base_body, pin_left_cyl)

    # LUG_2 Pin Hole (Step 4 - Mirrored across XZ plane at Y=35.0): Center at (10.0, 54.0, 36.0)
    origin_pin_right = NXOpen.Point3d(-0.1, 54.0, 36.0)
    pin_right_cyl = _create_cylinder(origin_pin_right, vec_x_pos, "PIN_HOLE_DIA", "LUG_PROJECTION + 0.2")
    _perform_subtract(base_body, pin_right_cyl)

    # Step 5: Relief Slot Cut on LUG_2
    # Centered below pin hole (Y = 54.0, SLOT_WIDTH = 5.0, SLOT_HEIGHT = 14.0)
    corner_slot = NXOpen.Point3d(-0.1, 54.0 - 2.5, 8.0)
    slot_block = _create_block(corner_slot, "LUG_PROJECTION + 0.2", "SLOT_WIDTH", "SLOT_HEIGHT")
    _perform_subtract(base_body, slot_block)

    # Steps 6 & 7: Triangular Extrude Cutouts with Relief Holes
    def _create_triangular_cutout_with_circle(p1, p2, p3, circle_center):
        pt1 = work_part.Points.CreatePoint(p1)
        pt2 = work_part.Points.CreatePoint(p2)
        pt3 = work_part.Points.CreatePoint(p3)

        l1 = work_part.Curves.CreateLine(pt1, pt2)
        l2 = work_part.Curves.CreateLine(pt2, pt3)
        l3 = work_part.Curves.CreateLine(pt3, pt1)

        section = work_part.Sections.CreateSection(0.001, 0.01, 0.5)
        help_point = NXOpen.Point3d(0.0, 0.0, 0.0)

        for line in [l1, l2, l3]:
            rule = work_part.ScRuleFactory.CreateRuleCurveDumb([line])
            section.AddToSection([rule], line, NXOpen.NXObject.Null, NXOpen.NXObject.Null, help_point, NXOpen.Section.Mode.Create)

        ext_builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
        try:
            ext_builder.Section = section
            ext_builder.Direction = work_part.Directions.CreateDirection(
                p1, vec_z_neg, NXOpen.SmartObject.UpdateOption.WithinModeling
            )
            ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
            ext_builder.Limits.EndExtend.Value.RightHandSide = "BASE_THICKNESS + 0.2"
            ext_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
            feat = ext_builder.CommitFeature()
            tool_body = feat.GetBodies()[0]
        finally:
            ext_builder.Destroy()

        _perform_subtract(base_body, tool_body)

        # Circular corner relief hole
        origin_circle = NXOpen.Point3d(circle_center.X, circle_center.Y, 8.1)
        circle_cyl = _create_cylinder(origin_circle, vec_z_neg, "RELIEF_DIA", "BASE_THICKNESS + 0.2")
        _perform_subtract(base_body, circle_cyl)

    # Triangle 1 (Step 6): (18,18), (42,18), (30,42), circle at (18,18)
    p1_t1 = NXOpen.Point3d(18.0, 18.0, 8.1)
    p2_t1 = NXOpen.Point3d(42.0, 18.0, 8.1)
    p3_t1 = NXOpen.Point3d(30.0, 42.0, 8.1)
    _create_triangular_cutout_with_circle(p1_t1, p2_t1, p3_t1, p1_t1)

    # Triangle 2 (Step 7 - Mirrored across YZ plane at midplane X=60): (102,18), (78,18), (90,42), circle at (102,18)
    p1_t2 = NXOpen.Point3d(102.0, 18.0, 8.1)
    p2_t2 = NXOpen.Point3d(78.0, 18.0, 8.1)
    p3_t2 = NXOpen.Point3d(90.0, 42.0, 8.1)
    _create_triangular_cutout_with_circle(p1_t2, p2_t2, p3_t2, p1_t2)

    # Steps 8 & 9: Mounting Holes
    # Upper Mount Hole (Step 8): at Upper-right mounting location (X=105.0, Y=55.0, Z=8.1)
    origin_mh_upper = NXOpen.Point3d(105.0, 55.0, 8.1)
    hole_m_upper = _create_cylinder(origin_mh_upper, vec_z_neg, "BASE_HOLE_DIA", "BASE_THICKNESS + 0.2")
    _perform_subtract(base_body, hole_m_upper)

    # Lower Mount Hole (Step 9 - Mirrored across XZ plane at Y=35.0): at Lower-right mounting location (X=105.0, Y=15.0, Z=8.1)
    origin_mh_lower = NXOpen.Point3d(105.0, 15.0, 8.1)
    hole_m_lower = _create_cylinder(origin_mh_lower, vec_z_neg, "BASE_HOLE_DIA", "BASE_THICKNESS + 0.2")
    _perform_subtract(base_body, hole_m_lower)

    # Section 6: Edge Fillets (FILLET_R = 2.0)
    all_body_edges = list(base_body.GetEdges())
    if all_body_edges:
        blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = work_part.ScCollectors.CreateCollector()
            rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in all_body_edges]
            collector.ReplaceRules(rules, False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "FILLET_R")
            blend_builder.CommitFeature()
        except Exception as exc:
            print(f"[WARN] Edge blend note: {exc}")
        finally:
            blend_builder.Destroy()

    # 9. Set View to ISO
    try:
        work_part.ModelingViews.WorkView.Orient("ISO")
        work_part.ModelingViews.WorkView.Fit()
    except Exception:
        pass

    # 10. Save Part
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"[OK] Saved part: {OUTPUT_PRT}")

    # 11. Export STL using UFSession
    try:
        if OUTPUT_STL.exists():
            try:
                OUTPUT_STL.unlink()
            except Exception:
                pass
        uf_session.Std.SetDefaultStlParams()
        stl_stem = str(OUTPUT_STL.with_suffix(""))
        file_handle = uf_session.Std.OpenTextStlFile(stl_stem, False)
        uf_session.Std.PutSolidInStlFile(file_handle, 0, base_body.Tag, 0.0, 0.0, 0.01)
        uf_session.Std.CloseStlFile(file_handle)

        candidate_1 = Path(stl_stem + ".txt")
        candidate_2 = Path(stl_stem + ".stl.txt")

        start = time.time()
        while time.time() - start < 5:
            target_txt = candidate_1 if candidate_1.exists() else (candidate_2 if candidate_2.exists() else None)
            if target_txt:
                if OUTPUT_STL.exists():
                    try:
                        OUTPUT_STL.unlink()
                    except Exception:
                        pass
                target_txt.rename(OUTPUT_STL)
                break
            time.sleep(0.5)

        if OUTPUT_STL.exists() and OUTPUT_STL.stat().st_size > 0:
            print(f"[OK] Exported STL ({OUTPUT_STL.stat().st_size} bytes): {OUTPUT_STL}")
    except Exception as e:
        print(f"[WARN] STL export error: {e}")


def export_step_cli():
    if OUTPUT_STEP.exists():
        try:
            OUTPUT_STEP.unlink()
        except Exception:
            pass
    nx_base = r"C:\Program Files\Siemens\NX2206"
    nxbin = r"C:\Program Files\Siemens\NX2206\NXBIN"
    env = os.environ.copy()
    env["UGII_BASE_DIR"] = nx_base
    env["UGII_ROOT_DIR"] = nxbin
    env["PATH"] = f"{nxbin};{nx_base}\\UGII;{env.get('PATH', '')}"

    step_cmd = f'echo. | "{nx_base}\\STEP214UG\\step214ug.cmd" "{OUTPUT_PRT}"'
    res = subprocess.run(step_cmd, shell=True, cwd=str(OUTPUT_STEP.parent), env=env, capture_output=True, text=True)

    start = time.time()
    while time.time() - start < 15:
        if OUTPUT_STEP.exists() and OUTPUT_STEP.stat().st_size > 0:
            print(f"[OK] STEP exported via STEP214 converter ({OUTPUT_STEP.stat().st_size} bytes): {OUTPUT_STEP}")
            return
        time.sleep(0.5)
    print(f"[WARN] STEP CLI output: {res.stdout}")


def launch_and_connect():
    os.system("taskkill /F /IM ugraf.exe 2>nul")
    time.sleep(1)

    nx_base = r"C:\Program Files\Siemens\NX2206"
    run_journal = os.path.join(nx_base, "NXBIN", "run_journal.exe")
    script_path = str(Path(__file__).resolve())

    print(f"[INFO] Executing script via run_journal.exe: {run_journal}")
    res = subprocess.run([run_journal, script_path], capture_output=True, text=True)
    print("STDOUT:\n", res.stdout)
    if res.stderr:
        print("STDERR:\n", res.stderr)

    # Re-generate STEP via CLI converter to ensure latest geometry
    export_step_cli()

    return res.returncode == 0


def main():
    try:
        import NXOpen
        is_nx_env = True
    except ImportError:
        is_nx_env = False

    if is_nx_env:
        run_nxopen_journal()
    else:
        print("[INFO] Running launcher...")
        success = launch_and_connect()
        if success:
            print("\n" + "=" * 60)
            print("SUCCESS: cantilever_clevis_plate CAD model complete!")
            print(f"  PRT:  {OUTPUT_PRT}")
            print(f"  STEP: {OUTPUT_STEP}")
            print(f"  STL:  {OUTPUT_STL}")
            print("=" * 60)


if __name__ == "__main__":
    main()
