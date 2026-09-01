r"""
build_impeller_disk3.py
=======================
NX CAD automation script and NX journal for generating `impeller_disk3` part.
"""

import json
import socket
import time
import sys
import os
import math
import subprocess
from pathlib import Path

OUTPUT_PRT = Path("C:/Users/HP/nx-mcp/impeller_disk3.prt").resolve()
OUTPUT_STEP = Path("C:/Users/HP/nx-mcp/impeller_disk3.stp").resolve()
OUTPUT_STL = Path("C:/Users/HP/nx-mcp/impeller_disk3.stl").resolve()


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
        ("DISK_DIA", 120.0),
        ("DISK_THICK", 8.0),
        ("HUB_DIA", 22.0),
        ("HUB_HEIGHT", 8.0),
        ("BORE_DIA", 10.0),
        ("BLADE_COUNT", 9.0),
        ("INNER_RADIUS", 16.0),
        ("OUTER_RADIUS", 55.0),
        ("BLADE_START_WIDTH", 5.0),
        ("BLADE_END_WIDTH", 7.0),
        ("BLADE_DEPTH", 4.0),
        ("BLADE_SWEEP", 52.0),
        ("POCKET_FILLET", 0.5),
        ("HUB_FILLET", 1.0),
        ("EDGE_FILLET", 1.0),
    ]
    for name, value in expressions:
        work_part.Expressions.CreateExpression("Number", f"{name} = {value}")

    # Evaluate variables dynamically
    disk_dia_val = work_part.Expressions.FindObject("DISK_DIA").Value
    disk_thick_val = work_part.Expressions.FindObject("DISK_THICK").Value
    hub_dia_val = work_part.Expressions.FindObject("HUB_DIA").Value
    hub_height_val = work_part.Expressions.FindObject("HUB_HEIGHT").Value
    bore_dia_val = work_part.Expressions.FindObject("BORE_DIA").Value
    blade_count_val = work_part.Expressions.FindObject("BLADE_COUNT").Value
    inner_radius_val = work_part.Expressions.FindObject("INNER_RADIUS").Value
    outer_radius_val = work_part.Expressions.FindObject("OUTER_RADIUS").Value
    blade_start_width_val = work_part.Expressions.FindObject("BLADE_START_WIDTH").Value
    blade_end_width_val = work_part.Expressions.FindObject("BLADE_END_WIDTH").Value
    blade_depth_val = work_part.Expressions.FindObject("BLADE_DEPTH").Value
    blade_sweep_val = work_part.Expressions.FindObject("BLADE_SWEEP").Value

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
    vec_z_pos = NXOpen.Vector3d(0.0, 0.0, 1.0)
    vec_z_neg = NXOpen.Vector3d(0.0, 0.0, -1.0)

    # 1. Base Disk (Cylinder Dia 120, height 8) named BASE
    origin_disk = NXOpen.Point3d(0.0, 0.0, 0.0)
    base_body = _create_cylinder(origin_disk, vec_z_pos, "DISK_DIA", "DISK_THICK")
    base_body.SetName("BASE")

    # 2. Hub (Cylinder Dia 22, height DISK_THICK + HUB_HEIGHT = 16)
    origin_hub = NXOpen.Point3d(0.0, 0.0, 0.0)
    hub_body = _create_cylinder(origin_hub, vec_z_pos, "HUB_DIA", "DISK_THICK + HUB_HEIGHT")
    _perform_unite(base_body, hub_body)

    # 3. Center Bore Hole (BORE_DIA, Through All along -Z)
    # Starts slightly above (DISK_THICK + HUB_HEIGHT + 0.1) and cuts deeper than total height (height + 0.2)
    origin_bore = NXOpen.Point3d(0.0, 0.0, disk_thick_val + hub_height_val + 0.1)
    bore_cyl = _create_cylinder(origin_bore, vec_z_neg, "BORE_DIA", "DISK_THICK + HUB_HEIGHT + 0.2")
    _perform_subtract(base_body, bore_cyl)

    # 4. Blade Pocket sketch & extrude-cut (Z = DISK_THICK)
    # Spline 1 control points in polar coordinates:
    # P1 (Radius = 16, Angle = 0°), P2 (24, -8°), P3 (34, -18°), P4 (45, -34°), P5 (55, -52°)
    polar_pts = [
        (inner_radius_val, 0.0),
        (24.0, -8.0),
        (34.0, -18.0),
        (45.0, -34.0),
        (outer_radius_val, -blade_sweep_val)
    ]
    
    cart_pts = []
    for r, theta in polar_pts:
        theta_rad = math.radians(theta)
        cart_pts.append((r * math.cos(theta_rad), r * math.sin(theta_rad)))
        
    offset_pts = []
    n_pts = len(cart_pts)
    for i in range(n_pts):
        if i == 0:
            tx = cart_pts[1][0] - cart_pts[0][0]
            ty = cart_pts[1][1] - cart_pts[0][1]
        elif i == n_pts - 1:
            tx = cart_pts[i][0] - cart_pts[i-1][0]
            ty = cart_pts[i][1] - cart_pts[i-1][1]
        else:
            tx = cart_pts[i+1][0] - cart_pts[i-1][0]
            ty = cart_pts[i+1][1] - cart_pts[i-1][1]
            
        length = math.sqrt(tx**2 + ty**2)
        nx = -ty / length
        ny = tx / length
        
        r_current = polar_pts[i][0]
        # Interpolate pocket offset width linearly from BLADE_START_WIDTH to BLADE_END_WIDTH
        frac = (r_current - inner_radius_val) / (outer_radius_val - inner_radius_val)
        w = blade_start_width_val + frac * (blade_end_width_val - blade_start_width_val)
        
        ox = cart_pts[i][0] + w * nx
        oy = cart_pts[i][1] + w * ny
        offset_pts.append((ox, oy))

    z_start = disk_thick_val # Top face of disk

    # Create Spline 1 (curving clockwise)
    builder1 = work_part.Features.CreateStudioSplineBuilderEx(NXOpen.Features.Feature.Null)
    builder1.Degree = 3
    builder1.IsPeriodic = False
    for ox, oy in cart_pts:
        pt = work_part.Points.CreatePoint(NXOpen.Point3d(ox, oy, z_start))
        gcd = builder1.ConstraintManager.CreateGeometricConstraintData()
        gcd.Point = pt
        builder1.ConstraintManager.Append(gcd)
    feat1 = builder1.CommitFeature()
    spline1 = feat1.GetEntities()[0]
    builder1.Destroy()

    # Create Spline 2 (variable-width offset spline)
    builder2 = work_part.Features.CreateStudioSplineBuilderEx(NXOpen.Features.Feature.Null)
    builder2.Degree = 3
    builder2.IsPeriodic = False
    for ox, oy in offset_pts:
        pt = work_part.Points.CreatePoint(NXOpen.Point3d(ox, oy, z_start))
        gcd = builder2.ConstraintManager.CreateGeometricConstraintData()
        gcd.Point = pt
        builder2.ConstraintManager.Append(gcd)
    feat2 = builder2.CommitFeature()
    spline2 = feat2.GetEntities()[0]
    builder2.Destroy()

    # Close both spline ends using straight tangent lines
    pt_s1 = work_part.Points.CreatePoint(NXOpen.Point3d(cart_pts[0][0], cart_pts[0][1], z_start))
    pt_s2 = work_part.Points.CreatePoint(NXOpen.Point3d(offset_pts[0][0], offset_pts[0][1], z_start))
    line_start = work_part.Curves.CreateLine(pt_s1, pt_s2)

    pt_e1 = work_part.Points.CreatePoint(NXOpen.Point3d(cart_pts[-1][0], cart_pts[-1][1], z_start))
    pt_e2 = work_part.Points.CreatePoint(NXOpen.Point3d(offset_pts[-1][0], offset_pts[-1][1], z_start))
    line_end = work_part.Curves.CreateLine(pt_e1, pt_e2)

    # Create closed Section
    section = work_part.Sections.CreateSection(0.001, 0.01, 0.5)
    help_point = NXOpen.Point3d(0.0, 0.0, 0.0)
    for curve in [spline1, line_end, spline2, line_start]:
        rule = work_part.ScRuleFactory.CreateRuleCurveDumb([curve])
        section.AddToSection([rule], curve, NXOpen.NXObject.Null, NXOpen.NXObject.Null, help_point, NXOpen.Section.Mode.Create)

    # Extrude cut the blade pocket (depth = BLADE_DEPTH, direction = -Z, Subtract)
    ext_builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        ext_builder.Section = section
        ext_builder.Direction = work_part.Directions.CreateDirection(
            pt_s1.Coordinates, vec_z_neg, NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        ext_builder.Limits.EndExtend.Value.RightHandSide = "BLADE_DEPTH"
        ext_builder.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
            base_body
        )
        pocket_feat = ext_builder.CommitFeature()
    finally:
        ext_builder.Destroy()

    # 5. Circular Pattern of blade pocket
    work_part.Expressions.CreateExpression("Number", "BLADE_PITCH_ANGLE = 360.0 / BLADE_COUNT")

    pattern_builder = work_part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        pattern_builder.FeatureList.Add([pocket_feat])
        try:
            pattern_builder.PatternMethod = NXOpen.Features.PatternFeatureBuilder.PatternMethodOptions.Simple
        except Exception:
            pass
        service = pattern_builder.PatternService
        service.PatternType = NXOpen.GeometricUtilities.PatternDefinition.PatternEnum.Circular
        circ = service.CircularDefinition
        circ.RotationAxis = work_part.Axes.CreateAxis(
            NXOpen.Point3d(0.0, 0.0, z_start),
            vec_z_pos,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        circ.RotationCenter = work_part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, z_start))
        circ.IncludeSeedToggle = True
        circ.AngularSpacing.NCopies.RightHandSide = "BLADE_COUNT"
        circ.AngularSpacing.PitchAngle.RightHandSide = "BLADE_PITCH_ANGLE"
        pattern_feat = pattern_builder.CommitFeature()
    finally:
        pattern_builder.Destroy()

    # 6. Fillets
    all_body_edges = list(base_body.GetEdges())
    pocket_edges = []
    hub_edges = []
    disk_edges = []

    hub_top_z = disk_thick_val + hub_height_val
    hub_r = hub_dia_val / 2.0
    disk_r = disk_dia_val / 2.0

    for e in all_body_edges:
        v1, v2 = e.GetVertices()[0], e.GetVertices()[1]
        z_min = min(v1.Z, v2.Z)
        z_max = max(v1.Z, v2.Z)
        dist_1 = math.sqrt(v1.X**2 + v1.Y**2)
        dist_2 = math.sqrt(v2.X**2 + v2.Y**2)

        # Hub top circular edge
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(z_max - hub_top_z) < 0.1:
            if abs(dist_1 - hub_r) < 1.0 and abs(dist_2 - hub_r) < 1.0:
                hub_edges.append(e)
                continue

        # Outer top circular edge of disk
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(z_max - disk_thick_val) < 0.1:
            if abs(dist_1 - disk_r) < 1.0 and abs(dist_2 - disk_r) < 1.0:
                disk_edges.append(e)
                continue

        # Upper pocket edges: Z = disk_thick_val, but NOT linear (do not fillet blade ends),
        # and not on disk perimeter, and not on hub perimeter
        if abs(z_max - disk_thick_val) < 0.1 and abs(z_min - disk_thick_val) < 0.1:
            if e.EdgeType != NXOpen.Edge.EdgeType.Linear:
                if dist_1 < (disk_r - 1.0) and dist_1 > (hub_r + 1.0) and dist_2 < (disk_r - 1.0) and dist_2 > (hub_r + 1.0):
                    pocket_edges.append(e)
                    continue

    # Fillet Pocket Edges (POCKET_FILLET = 0.5)
    if pocket_edges:
        blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = work_part.ScCollectors.CreateCollector()
            rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in pocket_edges]
            collector.ReplaceRules(rules, False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "POCKET_FILLET")
            blend_builder.CommitFeature()
        except Exception as exc:
            print(f"[WARN] Pocket fillets note: {exc}")
        finally:
            blend_builder.Destroy()

    # Fillet Hub (HUB_FILLET = 1.0)
    if hub_edges:
        blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = work_part.ScCollectors.CreateCollector()
            rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in hub_edges]
            collector.ReplaceRules(rules, False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "HUB_FILLET")
            blend_builder.CommitFeature()
        except Exception as exc:
            print(f"[WARN] Hub fillet note: {exc}")
        finally:
            blend_builder.Destroy()

    # Fillet Outer Disk (EDGE_FILLET = 1.0)
    if disk_edges:
        blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = work_part.ScCollectors.CreateCollector()
            rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in disk_edges]
            collector.ReplaceRules(rules, False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "EDGE_FILLET")
            blend_builder.CommitFeature()
        except Exception as exc:
            print(f"[WARN] Outer disk fillet note: {exc}")
        finally:
            blend_builder.Destroy()

    # 7. Finish Operations
    # Set view to ISO, Display Mode to Shaded with Edges
    try:
        work_view = work_part.ModelingViews.WorkView
        work_view.Orient(NXOpen.View.Canned.Isometric, NXOpen.View.ScaleAdjustment.Fit)
        work_view.RenderingStyle = NXOpen.View.RenderingStyleType.ShadedWithEdges
        print("[OK] View set to ISO and Shaded with Edges.")
    except Exception as e:
        print(f"[WARN] View settings error: {e}")

    # Regenerate the Model
    try:
        session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)
        print("[OK] Model regenerated successfully.")
    except Exception as e:
        print(f"[WARN] Model regeneration error: {e}")

    # Validate Geometry (Check if solid body and compute volume)
    try:
        bodies = list(work_part.Bodies)
        print(f"[INFO] Number of bodies: {len(bodies)}")
        
        solid_bodies = []
        for b in bodies:
            is_solid = b.IsSolidBody
            if callable(is_solid):
                is_solid = is_solid()
            if is_solid:
                solid_bodies.append(b)
                
        print(f"[INFO] Solid bodies: {len(solid_bodies)}")
        
        if len(solid_bodies) > 0:
            body = solid_bodies[0]
            print(f"[INFO] Validating solid body named '{body.Name}' (Tag: {body.Tag})")
            
            # Use AskMassProps3d to measure volume (units=3 gives cm3, multiply by 1000 for mm3)
            acc_value = [0.99] + [0.0] * 10
            mass_props, stats = uf_session.Modeling.AskMassProps3d([body.Tag], 1, 1, 3, 1.0, 1, acc_value)
            volume = mass_props[1] * 1000.0
            
            print(f"[OK] Geometry validation successful. Solid body volume: {volume:.4f} mm³")
            if volume <= 0:
                raise ValueError("Volume must be greater than zero.")
        else:
            raise ValueError("No solid bodies found in the part.")
    except Exception as e:
        print(f"[ERROR] Geometry validation failed: {e}")
        sys.exit(1)

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
            print("SUCCESS: impeller_disk3 CAD model complete!")
            print(f"  PRT:  {OUTPUT_PRT}")
            print(f"  STEP: {OUTPUT_STEP}")
            print(f"  STL:  {OUTPUT_STL}")
            print("=" * 60)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
