r"""
build_radial_engine_cylinder3.py
================================
NX CAD automation script and NX journal for generating `radial_engine_cylinder3` part.
"""

import json
import socket
import time
import sys
import os
import math
import subprocess
from pathlib import Path

# Add shared helpers from examples._common
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from examples._common import vec, set_name, unite, write_launch_files

OUTPUT_PRT = Path("C:/Users/HP/nx-mcp/radial_engine_cylinder3.prt").resolve()
OUTPUT_STEP = Path("C:/Users/HP/nx-mcp/radial_engine_cylinder3.stp").resolve()
OUTPUT_STL = Path("C:/Users/HP/nx-mcp/radial_engine_cylinder3.stl").resolve()


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
        ("BASE_DIA", 80.0),
        ("BASE_HEIGHT", 10.0),
        ("BODY_DIA", 52.0),
        ("BODY_HEIGHT", 70.0),
        ("HEAD_DIA", 56.0),
        ("HEAD_HEIGHT", 15.0),
        ("FIN_COUNT", 11.0),
        ("FIN_HEIGHT", 3.0),
        ("FIN_SPACING", 6.0),
        ("FIN_DEPTH", 2.0),
        ("PIPE_DIA", 12.0),
        ("PIPE_LENGTH", 22.0),
        ("PIPE_HOLE_DIA", 5.0),
        ("PIPE_CENTER_HEIGHT", 8.0),
        ("BOLT_HOLE_DIA", 5.0),
        ("BOLT_CIRCLE_DIA", 60.0),
        ("BOLT_COUNT", 4.0),
        ("EDGE_FILLET", 1.0),
    ]
    for name, value in expressions:
        work_part.Expressions.CreateExpression("Number", f"{name} = {value}")

    # Evaluate dynamic variables from expressions
    base_dia_val = work_part.Expressions.FindObject("BASE_DIA").Value
    base_height_val = work_part.Expressions.FindObject("BASE_HEIGHT").Value
    body_dia_val = work_part.Expressions.FindObject("BODY_DIA").Value
    body_height_val = work_part.Expressions.FindObject("BODY_HEIGHT").Value
    head_dia_val = work_part.Expressions.FindObject("HEAD_DIA").Value
    head_height_val = work_part.Expressions.FindObject("HEAD_HEIGHT").Value
    fin_height_val = work_part.Expressions.FindObject("FIN_HEIGHT").Value
    fin_depth_val = work_part.Expressions.FindObject("FIN_DEPTH").Value
    pipe_dia_val = work_part.Expressions.FindObject("PIPE_DIA").Value
    pipe_length_val = work_part.Expressions.FindObject("PIPE_LENGTH").Value
    pipe_center_height_val = work_part.Expressions.FindObject("PIPE_CENTER_HEIGHT").Value
    bolt_circle_dia_val = work_part.Expressions.FindObject("BOLT_CIRCLE_DIA").Value

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
    vec_x_pos = vec(1.0, 0.0, 0.0)
    vec_z_pos = vec(0.0, 0.0, 1.0)
    vec_z_neg = vec(0.0, 0.0, -1.0)

    # 1. Base Cylinder (Dia 80, height 10), named BASE
    origin_base = NXOpen.Point3d(0.0, 0.0, 0.0)
    base_body = _create_cylinder(origin_base, vec_z_pos, "BASE_DIA", "BASE_HEIGHT")
    set_name(base_body, "BASE")

    # 2. Main Cylinder (Dia 52, height 70) starting at Z = BASE_HEIGHT
    origin_body = NXOpen.Point3d(0.0, 0.0, base_height_val)
    body_cylinder = _create_cylinder(origin_body, vec_z_pos, "BODY_DIA", "BODY_HEIGHT")
    unite(base_body, [body_cylinder])

    # 3. Top Head Cylinder (Dia 56, height 15) starting at Z = BASE_HEIGHT + BODY_HEIGHT
    origin_head = NXOpen.Point3d(0.0, 0.0, base_height_val + body_height_val)
    head_cylinder = _create_cylinder(origin_head, vec_z_pos, "HEAD_DIA", "HEAD_HEIGHT")
    unite(base_body, [head_cylinder])

    # 4. Cooling Groove (Revolve Cut)
    # Rectangle on XZ plane:
    # X from BODY_DIA/2 - FIN_DEPTH to BODY_DIA/2
    # Z from BASE_HEIGHT + 3.0 to BASE_HEIGHT + 3.0 + FIN_HEIGHT
    x_inner = body_dia_val / 2.0 - fin_depth_val
    x_outer = body_dia_val / 2.0
    z_bottom = base_height_val + 3.0
    z_top = base_height_val + 3.0 + fin_height_val

    p1 = work_part.Points.CreatePoint(NXOpen.Point3d(x_inner, 0.0, z_bottom))
    p2 = work_part.Points.CreatePoint(NXOpen.Point3d(x_outer, 0.0, z_bottom))
    p3 = work_part.Points.CreatePoint(NXOpen.Point3d(x_outer, 0.0, z_top))
    p4 = work_part.Points.CreatePoint(NXOpen.Point3d(x_inner, 0.0, z_top))

    l1 = work_part.Curves.CreateLine(p1, p2)
    l2 = work_part.Curves.CreateLine(p2, p3)
    l3 = work_part.Curves.CreateLine(p3, p4)
    l4 = work_part.Curves.CreateLine(p4, p1)

    section = work_part.Sections.CreateSection(0.001, 0.01, 0.5)
    help_point = NXOpen.Point3d(0.0, 0.0, 0.0)
    for curve in [l1, l2, l3, l4]:
        rule = work_part.ScRuleFactory.CreateRuleCurveDumb([curve])
        section.AddToSection([rule], curve, NXOpen.NXObject.Null, NXOpen.NXObject.Null, help_point, NXOpen.Section.Mode.Create)

    features, number_of_features = uf_session.Modl.CreateRevolution(
        [l1.Tag, l2.Tag, l3.Tag, l4.Tag],
        4,
        None,
        ["0", "360"],
        ["0", "0"],
        [0.0, 0.0, 0.0],
        False,
        True,
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        NXOpen.UF.Modl.FeatureSigns.NEGATIVE,
    )
    groove_feat = NXOpen.TaggedObjectManager().GetTaggedObject(features[0])

    # 5. Linear Pattern of Cooling Groove in +Z direction
    pattern_builder = work_part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        pattern_builder.FeatureList.Add([groove_feat])
        try:
            pattern_builder.PatternMethod = NXOpen.Features.PatternFeatureBuilder.PatternMethodOptions.Simple
        except Exception:
            pass
        service = pattern_builder.PatternService
        service.PatternType = NXOpen.GeometricUtilities.PatternDefinition.PatternEnum.Linear
        rect = service.RectangularDefinition
        
        # Direction 1 along +Z
        dir_z = work_part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), vec_z_pos, NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        rect.XDirection = dir_z
        rect.XSpacing.NCopies.RightHandSide = "FIN_COUNT"
        rect.XSpacing.PitchDistance.RightHandSide = "FIN_SPACING"
        rect.UseYDirectionToggle = False
        
        lin_feat = pattern_builder.CommitFeature()
    finally:
        pattern_builder.Destroy()

    # 6. Side Pipe Cylinder
    # Diameter: PIPE_DIA, height: PIPE_LENGTH, axis +X, centered at X = BODY_DIA / 2
    # Start at X = BODY_DIA / 2 - 1.0 (to overlap with main body) with length PIPE_LENGTH + 1.0
    # Z = BODY_HEIGHT + PIPE_CENTER_HEIGHT
    origin_pipe = NXOpen.Point3d(body_dia_val / 2.0 - 1.0, 0.0, body_height_val + pipe_center_height_val)
    pipe_body = _create_cylinder(origin_pipe, vec_x_pos, "PIPE_DIA", "PIPE_LENGTH + 1.0")
    unite(base_body, [pipe_body])

    # 7. Pipe Hole along the axis of side pipe (Through All, direction +X)
    # Start at X = BODY_DIA / 2 - 6.0 (to cut through the cylinder wall) with length PIPE_LENGTH + 10.0
    origin_pipe_hole = NXOpen.Point3d(body_dia_val / 2.0 - 6.0, 0.0, body_height_val + pipe_center_height_val)
    pipe_hole = _create_cylinder(origin_pipe_hole, vec_x_pos, "PIPE_HOLE_DIA", "PIPE_LENGTH + 10.0")
    _perform_subtract(base_body, pipe_hole)

    # 8. Base Mounting Hole
    # Diameter: BOLT_HOLE_DIA, depth: BASE_HEIGHT, direction -Z, positioned at X = BOLT_CIRCLE_DIA / 2, Y=0, Z = BASE_HEIGHT
    # Start slightly above (Z = BASE_HEIGHT + 0.1) and cut deeper (height = BASE_HEIGHT + 0.2) to cleanly cut through base
    origin_bolt = NXOpen.Point3d(bolt_circle_dia_val / 2.0, 0.0, base_height_val + 0.1)
    bolt_hole = _create_cylinder(origin_bolt, vec_z_neg, "BOLT_HOLE_DIA", "BASE_HEIGHT + 0.2")
    _perform_subtract(base_body, bolt_hole)

    # Find the feature corresponding to the bolt hole cylinder subtraction
    all_feats = list(work_part.Features)
    bolt_hole_feat = all_feats[-1]

    # Circular Pattern of Bolt Hole (BOLT_COUNT count around Z axis, 360°)
    circ_builder = work_part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        circ_builder.FeatureList.Add([bolt_hole_feat])
        try:
            circ_builder.PatternMethod = NXOpen.Features.PatternFeatureBuilder.PatternMethodOptions.Simple
        except Exception:
            pass
        service = circ_builder.PatternService
        service.PatternType = NXOpen.GeometricUtilities.PatternDefinition.PatternEnum.Circular
        circ = service.CircularDefinition
        circ.RotationAxis = work_part.Axes.CreateAxis(
            NXOpen.Point3d(0.0, 0.0, 0.0),
            vec_z_pos,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        circ.RotationCenter = work_part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
        circ.IncludeSeedToggle = True
        circ.AngularSpacing.NCopies.RightHandSide = "BOLT_COUNT"
        circ.AngularSpacing.PitchAngle.RightHandSide = "360.0 / BOLT_COUNT"
        circ_feat = circ_builder.CommitFeature()
    finally:
        circ_builder.Destroy()

    # 9. Edge Fillets (EDGE_FILLET = 1.0) applied to the 4 outer circular edges
    all_body_edges = list(base_body.GetEdges())
    fillet_edges = []
    base_r = base_dia_val / 2.0
    head_r = head_dia_val / 2.0
    pipe_r = pipe_dia_val / 2.0
    pipe_end_x = body_dia_val / 2.0 + pipe_length_val
    total_z = base_height_val + body_height_val + head_height_val

    for e in all_body_edges:
        v1, v2 = e.GetVertices()[0], e.GetVertices()[1]
        z_min = min(v1.Z, v2.Z)
        z_max = max(v1.Z, v2.Z)
        x_min = min(v1.X, v2.X)
        x_max = max(v1.X, v2.X)
        dist_1 = math.sqrt(v1.X**2 + v1.Y**2)
        dist_2 = math.sqrt(v2.X**2 + v2.Y**2)

        # A. Base bottom (Z=0, radius base_r)
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(z_max) < 0.1:
            if abs(dist_1 - base_r) < 1.0 and abs(dist_2 - base_r) < 1.0:
                fillet_edges.append(e)
                continue

        # B. Base top (Z=base_height_val, radius base_r)
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(z_max - base_height_val) < 0.1:
            if abs(dist_1 - base_r) < 1.0 and abs(dist_2 - base_r) < 1.0:
                fillet_edges.append(e)
                continue

        # C. Head top (Z=total_z, radius head_r)
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(z_max - total_z) < 0.1:
            if abs(dist_1 - head_r) < 1.0 and abs(dist_2 - head_r) < 1.0:
                fillet_edges.append(e)
                continue

        # D. Pipe end (X=pipe_end_x, circular edge with radius pipe_r)
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(x_max - pipe_end_x) < 0.1:
            fillet_edges.append(e)
            continue

    if fillet_edges:
        blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = work_part.ScCollectors.CreateCollector()
            rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in fillet_edges]
            collector.ReplaceRules(rules, False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "EDGE_FILLET")
            blend_builder.CommitFeature()
        except Exception as exc:
            print(f"[WARN] Fillets note: {exc}")
        finally:
            blend_builder.Destroy()

    # 10. Finish Operations
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
            
            # Use uf_session.Modeling.AskMassProps3d to measure volume (units=3 gives cm3, multiply by 1000 for mm3)
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
            print("SUCCESS: radial_engine_cylinder3 CAD model complete!")
            print(f"  PRT:  {OUTPUT_PRT}")
            print(f"  STEP: {OUTPUT_STEP}")
            print(f"  STL:  {OUTPUT_STL}")
            print("=" * 60)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
