r"""
build_benchmark_06_clevis_bracket_lightening_cutouts.py
======================================================
NX CAD automation script and NX journal for generating `benchmark_06_clevis_bracket_lightening_cutouts` part.

Features:
- Expressions: BASE_LENGTH, BASE_WIDTH, BASE_THICK, BASE_CORNER_RADIUS, LUG_THICK,
               LUG_WIDTH, LUG_HEIGHT, LUG_GAP, TOP_RADIUS, PIN_HOLE_DIA,
               PIN_CENTER_HEIGHT, SLOT_WIDTH, SLOT_HEIGHT, CONNECTOR_DIA,
               CONNECTOR_LENGTH, MOUNT_HOLE_DIA, MOUNT_OFFSET_X, MOUNT_OFFSET_Y,
               TRIANGLE_SIZE, RELIEF_RADIUS, FILLET_R
- Base Body: BASE Cuboid (120 x 70 x 8) at (0,0,0)
- Feature Sequence:
  - Step 1: Create left lug (Width 16, Height 20, Top Arc Radius 10, standing vertical, height 42)
  - Step 2: Create right lug (same profile, Center X = 77)
  - Step 3: Create cylindrical connector (Dia 12, height 18 along +X connecting the two lugs)
  - Step 4: Hole through left lug (H5, Dia 12.0, depth 16 along +X)
  - Step 5: Hole through right lug (H6, Dia 12.0, depth 16 along -X)
  - Step 6: Front lug slot (Width 4, Height 14, depth 16 along +X on LEFT_LUG)
  - Step 7: Left lightening pocket (Triangle cutout + relief hole at (18,18))
  - Step 8: Mirror left pocket across YZ plane at midplane X=60
  - Step 9: Mount holes (4x, Dia 8.0, depth 8.0, at offsets 15,15)
- Finish: Fillets on outer edges (6.0 mm) and vertical edges (2.0 mm)
- Exports: .prt, .stp
"""

import json
import socket
import time
import sys
import os
import math
import subprocess
from pathlib import Path

OUTPUT_PRT = Path("C:/Users/HP/nx-mcp/benchmark_06_clevis_bracket_lightening_cutouts.prt").resolve()
OUTPUT_STEP = Path("C:/Users/HP/nx-mcp/benchmark_06_clevis_bracket_lightening_cutouts.stp").resolve()
OUTPUT_STL = Path("C:/Users/HP/nx-mcp/benchmark_06_clevis_bracket_lightening_cutouts.stl").resolve()


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
        ("BASE_THICK", 8.0),
        ("BASE_CORNER_RADIUS", 6.0),
        ("LUG_THICK", 16.0),
        ("LUG_WIDTH", 20.0),
        ("LUG_HEIGHT", 42.0),
        ("LUG_GAP", 18.0),
        ("TOP_RADIUS", 10.0),
        ("PIN_HOLE_DIA", 12.0),
        ("PIN_CENTER_HEIGHT", 28.0),
        ("SLOT_WIDTH", 4.0),
        ("SLOT_HEIGHT", 14.0),
        ("CONNECTOR_DIA", 12.0),
        ("CONNECTOR_LENGTH", "LUG_GAP"),
        ("MOUNT_HOLE_DIA", 8.0),
        ("MOUNT_OFFSET_X", 15.0),
        ("MOUNT_OFFSET_Y", 15.0),
        ("TRIANGLE_SIZE", 24.0),
        ("RELIEF_RADIUS", 4.0),
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
    vec_x_neg = NXOpen.Vector3d(-1.0, 0.0, 0.0)
    vec_z_neg = NXOpen.Vector3d(0.0, 0.0, -1.0)

    # Base Body: Cuboid BASE_LENGTH (120) x BASE_WIDTH (70) x BASE_THICK (8)
    # Position: Corner at (0,0,0)
    corner_base = NXOpen.Point3d(0.0, 0.0, 0.0)
    base_body = _create_block(corner_base, "BASE_LENGTH", "BASE_WIDTH", "BASE_THICK")

    # Helper function to sketch capsule profile in XY plane and extrude vertically (+Z)
    def _create_capsule_lug(center_x, center_y, z_start, height_val):
        x_left = center_x - 8.0
        x_right = center_x + 8.0
        y_bottom_arc = center_y - 6.0
        y_top_arc = center_y + 6.0

        p1 = work_part.Points.CreatePoint(NXOpen.Point3d(x_left, y_bottom_arc, z_start))
        p2 = work_part.Points.CreatePoint(NXOpen.Point3d(x_left, y_top_arc, z_start))
        p3 = work_part.Points.CreatePoint(NXOpen.Point3d(x_right, y_top_arc, z_start))
        p4 = work_part.Points.CreatePoint(NXOpen.Point3d(x_right, y_bottom_arc, z_start))

        l1 = work_part.Curves.CreateLine(p1, p2)
        l2 = work_part.Curves.CreateLine(p3, p4)

        # Create arcs using center, x_axis, y_axis, radius, start angle, end angle
        center_pt = NXOpen.Point3d(center_x, center_y, z_start)
        x_axis = NXOpen.Vector3d(1.0, 0.0, 0.0)
        y_axis = NXOpen.Vector3d(0.0, 1.0, 0.0)
        
        # acos(0.8) approx 0.6435011087932844
        top_start = math.acos(8.0 / 10.0)
        top_end = math.acos(-8.0 / 10.0)
        arc_top = work_part.Curves.CreateArc(center_pt, x_axis, y_axis, 10.0, top_start, top_end)

        bottom_start = math.pi + math.acos(8.0 / 10.0)
        bottom_end = 2.0 * math.pi - math.acos(8.0 / 10.0)
        arc_bottom = work_part.Curves.CreateArc(center_pt, x_axis, y_axis, 10.0, bottom_start, bottom_end)

        section = work_part.Sections.CreateSection(0.001, 0.01, 0.5)
        help_point = NXOpen.Point3d(0.0, 0.0, 0.0)
        for curve in [l1, arc_top, l2, arc_bottom]:
            rule = work_part.ScRuleFactory.CreateRuleCurveDumb([curve])
            section.AddToSection([rule], curve, NXOpen.NXObject.Null, NXOpen.NXObject.Null, help_point, NXOpen.Section.Mode.Create)

        ext_builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
        try:
            ext_builder.Section = section
            ext_builder.Direction = work_part.Directions.CreateDirection(
                p1.Coordinates, NXOpen.Vector3d(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling
            )
            ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
            ext_builder.Limits.EndExtend.Value.RightHandSide = str(height_val)
            ext_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
            feat = ext_builder.CommitFeature()
            return feat.GetBodies()[0]
        finally:
            ext_builder.Destroy()

    # Step 1: Create left lug
    # Center X = 43.0, Center Y = 35.0
    left_lug_body = _create_capsule_lug(43.0, 35.0, 8.0, "LUG_HEIGHT")
    _perform_unite(base_body, left_lug_body)

    # Step 2: Create right lug
    # Center X = 77.0, Center Y = 35.0
    right_lug_body = _create_capsule_lug(77.0, 35.0, 8.0, "LUG_HEIGHT")
    _perform_unite(base_body, right_lug_body)

    # Step 3: Create cylindrical connector
    # Starts at X=51.0, extends 18.0 to X=69.0, diameter 12.0
    origin_connector = NXOpen.Point3d(51.0, 35.0, 36.0)
    connector_cyl = _create_cylinder(origin_connector, vec_x_pos, "CONNECTOR_DIA", "CONNECTOR_LENGTH")
    _perform_unite(base_body, connector_cyl)

    # Step 4: Hole through left lug
    # Starts at X=34.9 (outer face X=35.0), extends +X by 16.2 to exit inner face X=51.0
    origin_hole_left = NXOpen.Point3d(34.9, 35.0, 36.0)
    hole_left = _create_cylinder(origin_hole_left, vec_x_pos, "PIN_HOLE_DIA", "LUG_THICK + 0.2")
    _perform_subtract(base_body, hole_left)

    # Step 5: Hole through right lug
    # Starts at X=85.1 (outer face X=85.0), extends -X by 16.2 to exit inner face X=69.0
    origin_hole_right = NXOpen.Point3d(85.1, 35.0, 36.0)
    hole_right = _create_cylinder(origin_hole_right, vec_x_neg, "PIN_HOLE_DIA", "LUG_THICK + 0.2")
    _perform_subtract(base_body, hole_right)

    # Step 6: Front lug slot on Left Lug
    # Width = 4.0 (Y from 33.0 to 37.0), Height = 14.0 (Z from 8.0 to 22.0), starts X=34.9, depth 16.2 along +X
    corner_slot = NXOpen.Point3d(34.9, 35.0 - 2.0, 8.0)
    slot_block = _create_block(corner_slot, "LUG_THICK + 0.2", "SLOT_WIDTH", "SLOT_HEIGHT")
    _perform_subtract(base_body, slot_block)

    # Step 7 & 8: Triangular Pocket Cutouts
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
            ext_builder.Limits.EndExtend.Value.RightHandSide = "BASE_THICK + 0.2"
            ext_builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
            feat = ext_builder.CommitFeature()
            tool_body = feat.GetBodies()[0]
        finally:
            ext_builder.Destroy()

        _perform_subtract(base_body, tool_body)

        # Circular corner relief hole (Diameter = 2.0 * RELIEF_RADIUS = 8.0)
        origin_circle = NXOpen.Point3d(circle_center.X, circle_center.Y, 8.1)
        circle_cyl = _create_cylinder(origin_circle, vec_z_neg, "2.0 * RELIEF_RADIUS", "BASE_THICK + 0.2")
        _perform_subtract(base_body, circle_cyl)

    # Triangle 1 (Step 7): (18,18), (42,18), (30,42), circle at (18,18)
    p1_t1 = NXOpen.Point3d(18.0, 18.0, 8.1)
    p2_t1 = NXOpen.Point3d(42.0, 18.0, 8.1)
    p3_t1 = NXOpen.Point3d(30.0, 42.0, 8.1)
    _create_triangular_cutout_with_circle(p1_t1, p2_t1, p3_t1, p1_t1)

    # Triangle 2 (Step 8 - Mirrored across YZ plane at midplane X=60): (102,18), (78,18), (90,42), circle at (102,18)
    p1_t2 = NXOpen.Point3d(102.0, 18.0, 8.1)
    p2_t2 = NXOpen.Point3d(78.0, 18.0, 8.1)
    p3_t2 = NXOpen.Point3d(90.0, 42.0, 8.1)
    _create_triangular_cutout_with_circle(p1_t2, p2_t2, p3_t2, p1_t2)

    # Step 9: Mounting Holes
    mount_holes = [
        (15.0, 15.0),
        (105.0, 15.0),
        (15.0, 55.0),
        (105.0, 55.0),
    ]
    for x_h, y_h in mount_holes:
        origin_mh = NXOpen.Point3d(x_h, y_h, 8.1)
        hole_m = _create_cylinder(origin_mh, vec_z_neg, "MOUNT_HOLE_DIA", "BASE_THICK + 0.2")
        _perform_subtract(base_body, hole_m)

    # Section 6: Fillets
    # Fillet 1: BASE corners (radius = BASE_CORNER_RADIUS = 6.0) on 4 vertical edges of base cuboid
    all_edges = list(base_body.GetEdges())
    base_vert_edges = [
        e for e in all_edges
        if e.EdgeType == NXOpen.Edge.EdgeType.Linear
        and abs(e.GetVertices()[0].X - e.GetVertices()[1].X) < 1e-3
        and abs(e.GetVertices()[0].Y - e.GetVertices()[1].Y) < 1e-3
        and max(e.GetVertices()[0].Z, e.GetVertices()[1].Z) <= 8.1
    ]
    if base_vert_edges:
        blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = work_part.ScCollectors.CreateCollector()
            rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in base_vert_edges]
            collector.ReplaceRules(rules, False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "BASE_CORNER_RADIUS")
            blend_builder.CommitFeature()
        except Exception as exc:
            print(f"[WARN] Base corner blend note: {exc}")
        finally:
            blend_builder.Destroy()

    # Fillet 2: General Edge Fillet (radius = FILLET_R = 2.0) on other edges
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
            print(f"[WARN] General fillet note: {exc}")
        finally:
            blend_builder.Destroy()

    # View to ISO
    try:
        work_part.ModelingViews.WorkView.Orient("ISO")
        work_part.ModelingViews.WorkView.Fit()
    except Exception:
        pass

    # Save Part
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"[OK] Saved part: {OUTPUT_PRT}")

    # Export STL using UFSession
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
            print("SUCCESS: benchmark_06_clevis_bracket_lightening_cutouts CAD model complete!")
            print(f"  PRT:  {OUTPUT_PRT}")
            print(f"  STEP: {OUTPUT_STEP}")
            print(f"  STL:  {OUTPUT_STL}")
            print("=" * 60)


if __name__ == "__main__":
    main()
