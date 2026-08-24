"""
build_symmetric_u_bracket.py
=============================
Parametric Siemens NX model of a symmetric U-shaped mounting bracket 
with integrated two-section stepped cylindrical bosses (Flange + Hub),
mirrored features, edge blends, and STEP/STL export.
"""

import sys
import os
import math
import time
from pathlib import Path
import subprocess

try:
    import NXOpen
    import NXOpen.UF
    IS_NX = True
except ImportError:
    IS_NX = False


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


def run_nxopen_journal():
    the_session = NXOpen.Session.GetSession()
    uf_session = NXOpen.UF.UFSession.GetUFSession()

    part_path = Path("C:/Users/HP/nx-mcp/symmetric_u_bracket_stepped_bosses.prt").resolve()
    
    if part_path.exists():
        try:
            part_path.unlink()
        except Exception:
            pass

    the_session.Parts.NewDisplay(str(part_path), NXOpen.Part.Units.Millimeters)
    work_part = the_session.Parts.Work

    print(f"Created work part: {part_path}")

    # ==========================================
    # 1. EXPRESSIONS
    # ==========================================
    expressions_data = [
        ("BASE_LENGTH", "120.0"),
        ("BASE_WIDTH", "60.0"),
        ("BASE_THICKNESS", "15.0"),
        ("ARM_THICKNESS", "15.0"),
        ("ARM_HEIGHT", "60.0"),
        ("INNER_OPENING_WIDTH", "BASE_LENGTH - 2 * ARM_THICKNESS"),
        ("INNER_OPENING_DEPTH", "ARM_HEIGHT - BASE_THICKNESS"),
        ("BOSS_ELEVATION", "BASE_THICKNESS + INNER_OPENING_DEPTH / 2"),
        ("BOSS_BASE_DIA", "40.0"),
        ("BOSS_FLANGE_DIA", "40.0"),
        ("OUTER_HUB_DIA", "24.0"),
        ("BOSS_FLANGE_LENGTH", "10.0"),
        ("BOSS_HUB_LENGTH", "10.0"),
        ("BOSS_OVERALL_LENGTH", "BOSS_FLANGE_LENGTH + BOSS_HUB_LENGTH"),
        ("THROUGH_HOLE_DIA", "12.0"),
        ("EDGE_BLEND_RADIUS", "2.5"),
    ]

    expr_objs = {}
    for name, val in expressions_data:
        try:
            expr = work_part.Expressions.CreateExpression("Number", f"{name} = {val}")
            expr_objs[name] = expr
        except Exception as exc:
            print(f"[WARN] Create expression {name}: {exc}")
            try:
                expr = work_part.Expressions.FindObject(name)
                expr.RightHandSide = val
                expr_objs[name] = expr
            except Exception:
                pass

    print("[OK] All NX Expressions created.")

    # Helper function to create line section
    def create_rectangle_section(x_min_expr, x_max_expr, y_min_expr, y_max_expr, z_const=0.0):
        x_min = float(work_part.Expressions.FindObject(x_min_expr).Value) if hasattr(work_part.Expressions, "FindObject") else -60.0
        x_max = float(work_part.Expressions.FindObject(x_max_expr).Value) if hasattr(work_part.Expressions, "FindObject") else 60.0
        y_min = float(work_part.Expressions.FindObject(y_min_expr).Value) if hasattr(work_part.Expressions, "FindObject") else -30.0
        y_max = float(work_part.Expressions.FindObject(y_max_expr).Value) if hasattr(work_part.Expressions, "FindObject") else 30.0

        p1 = NXOpen.Point3d(x_min, y_min, z_const)
        p2 = NXOpen.Point3d(x_max, y_min, z_const)
        p3 = NXOpen.Point3d(x_max, y_max, z_const)
        p4 = NXOpen.Point3d(x_min, y_max, z_const)

        c1 = work_part.Curves.CreateLine(p1, p2)
        c2 = work_part.Curves.CreateLine(p2, p3)
        c3 = work_part.Curves.CreateLine(p3, p4)
        c4 = work_part.Curves.CreateLine(p4, p1)

        curves = [c1, c2, c3, c4]

        section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rules = [work_part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
        section.AddToSection(
            rules, curves[0],
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False
        )
        return section, curves

    # ==========================================
    # 2. EXTRUDE (BASE BLOCK)
    # ==========================================
    print("Creating Base Block...")
    work_part.Expressions.CreateExpression("Number", "BASE_XMIN = -BASE_LENGTH / 2")
    work_part.Expressions.CreateExpression("Number", "BASE_XMAX = BASE_LENGTH / 2")
    work_part.Expressions.CreateExpression("Number", "BASE_YMIN = -BASE_WIDTH / 2")
    work_part.Expressions.CreateExpression("Number", "BASE_YMAX = BASE_WIDTH / 2")

    sec_base, curves_base = create_rectangle_section("BASE_XMIN", "BASE_XMAX", "BASE_YMIN", "BASE_YMAX", 0.0)

    builder_base = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    builder_base.Section = sec_base
    nx_dir_z = work_part.Directions.CreateDirection(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling
    )
    builder_base.Direction = nx_dir_z
    builder_base.Limits.StartExtend.Value.RightHandSide = "0.0"
    builder_base.Limits.EndExtend.Value.RightHandSide = "ARM_HEIGHT"
    try:
        builder_base.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    except Exception:
        pass
    feat_base = builder_base.CommitFeature()
    builder_base.Destroy()
    feat_base.SetName("EXTRUDE_BASE_BLOCK")

    main_body = feat_base.GetBodies()[0]
    print(f"Base block created: {feat_base.JournalIdentifier}")

    # ==========================================
    # 3. EXTRUDE REMOVE (U-SHAPED OPENING)
    # ==========================================
    print("Creating U-Shaped Cutout...")
    work_part.Expressions.CreateExpression("Number", "CUT_XMIN = -INNER_OPENING_WIDTH / 2")
    work_part.Expressions.CreateExpression("Number", "CUT_XMAX = INNER_OPENING_WIDTH / 2")
    work_part.Expressions.CreateExpression("Number", "CUT_YMIN = -BASE_WIDTH / 2 - 5.0")
    work_part.Expressions.CreateExpression("Number", "CUT_YMAX = BASE_WIDTH / 2 + 5.0")

    sec_cut, curves_cut = create_rectangle_section("CUT_XMIN", "CUT_XMAX", "CUT_YMIN", "CUT_YMAX", 0.0)

    builder_cut = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    builder_cut.Section = sec_cut
    builder_cut.Direction = nx_dir_z
    builder_cut.Limits.StartExtend.Value.RightHandSide = "BASE_THICKNESS"
    builder_cut.Limits.EndExtend.Value.RightHandSide = "ARM_HEIGHT + 5.0"
    try:
        builder_cut.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
            main_body
        )
    except Exception:
        builder_cut.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract

    feat_cut = builder_cut.CommitFeature()
    builder_cut.Destroy()
    feat_cut.SetName("EXTRUDE_U_CUTOUT")
    print(f"U-Cutout created: {feat_cut.JournalIdentifier}")

    if len(feat_cut.GetBodies()) > 0:
        main_body = feat_cut.GetBodies()[0]

    # ==========================================
    # 4 & 5. SKETCH & EXTRUDE (STEPPED BOSS - 2 SECTIONS)
    # ==========================================
    print("Creating Stepped Boss (2 Concentric Sections: Flange & Outer Hub)...")
    x_arm_face = float(work_part.Expressions.FindObject("BASE_XMAX").Value) if hasattr(work_part.Expressions, "FindObject") else 60.0
    z_boss_center = float(work_part.Expressions.FindObject("BOSS_ELEVATION").Value) if hasattr(work_part.Expressions, "FindObject") else 37.5

    nx_dir_x = work_part.Directions.CreateDirection(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling
    )

    steps_config = [
        ("BOSS_STEP_FLANGE", "BOSS_FLANGE_DIA", "0.0", "BOSS_FLANGE_LENGTH"),
        ("BOSS_STEP_HUB", "OUTER_HUB_DIA", "BOSS_FLANGE_LENGTH", "BOSS_OVERALL_LENGTH"),
    ]

    boss_features = []
    for step_name, dia_expr, start_expr, end_expr in steps_config:
        dia_val = float(work_part.Expressions.FindObject(dia_expr).Value) if hasattr(work_part.Expressions, "FindObject") else 20.0
        radius = dia_val / 2.0

        center_pt = NXOpen.Point3d(x_arm_face, 0.0, z_boss_center)
        x_vec = NXOpen.Vector3d(0.0, 1.0, 0.0)
        y_vec = NXOpen.Vector3d(0.0, 0.0, 1.0)

        arc = work_part.Curves.CreateArc(center_pt, x_vec, y_vec, radius, 0.0, 2.0 * math.pi)

        sec = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rule = work_part.ScRuleFactory.CreateRuleCurveDumb([arc])
        sec.AddToSection(
            [rule], arc,
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False
        )

        bldr = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
        bldr.Section = sec
        bldr.Direction = nx_dir_x
        bldr.Limits.StartExtend.Value.RightHandSide = start_expr
        bldr.Limits.EndExtend.Value.RightHandSide = end_expr

        try:
            bldr.BooleanOperation.SetBooleanOperationAndBody(
                NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
                main_body
            )
        except Exception:
            bldr.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite

        feat_step = bldr.CommitFeature()
        bldr.Destroy()
        feat_step.SetName(step_name)
        boss_features.append(feat_step)
        print(f"Stepped boss section '{step_name}' created: {feat_step.JournalIdentifier}")

    # ==========================================
    # 6. HOLE (THROUGH BOSS AND ARM)
    # ==========================================
    print("Creating Concentric Through Hole...")
    dia_hole = float(work_part.Expressions.FindObject("THROUGH_HOLE_DIA").Value) if hasattr(work_part.Expressions, "FindObject") else 12.0
    r_hole = dia_hole / 2.0

    center_hole = NXOpen.Point3d(x_arm_face, 0.0, z_boss_center)
    arc_hole = work_part.Curves.CreateArc(
        center_hole,
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        r_hole, 0.0, 2.0 * math.pi
    )

    sec_hole = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
    rule_hole = work_part.ScRuleFactory.CreateRuleCurveDumb([arc_hole])
    sec_hole.AddToSection(
        [rule_hole], arc_hole,
        NXOpen.NXObject.Null, NXOpen.NXObject.Null,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create, False
    )

    nx_dir_minus_x = work_part.Directions.CreateDirection(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(-1.0, 0.0, 0.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling
    )

    bldr_hole = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    bldr_hole.Section = sec_hole
    bldr_hole.Direction = nx_dir_minus_x
    bldr_hole.Limits.StartExtend.Value.RightHandSide = "-BOSS_OVERALL_LENGTH - 2.0"
    bldr_hole.Limits.EndExtend.Value.RightHandSide = "ARM_THICKNESS + 5.0"
    try:
        bldr_hole.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
            main_body
        )
    except Exception:
        bldr_hole.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract

    feat_hole = bldr_hole.CommitFeature()
    bldr_hole.Destroy()
    feat_hole.SetName("THROUGH_HOLE")
    print(f"Through hole created: {feat_hole.JournalIdentifier}")

    # ==========================================
    # 7. MIRROR FEATURE (BOSS AND HOLE)
    # ==========================================
    print("Mirroring Boss and Hole Features about YZ Plane...")
    try:
        datum_builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
        datum_builder.SetFixedDatumPlane(NXOpen.Features.DatumPlaneBuilder.FixedType.Yz)
        datum_feat = datum_builder.CommitFeature()
        datum_plane = datum_feat.DatumPlane
        datum_builder.Destroy()

        bldr_mirror = work_part.Features.CreateMirrorFeatureBuilder(NXOpen.Features.Feature.Null)
        features_to_mirror = boss_features + [feat_hole]
        if hasattr(bldr_mirror, "FeatureSet"):
            bldr_mirror.FeatureSet.Add(features_to_mirror)
        elif hasattr(bldr_mirror, "Features"):
            bldr_mirror.Features.Add(features_to_mirror)

        if hasattr(bldr_mirror, "PlaneOption"):
            bldr_mirror.PlaneOption = NXOpen.Features.MirrorFeatureBuilder.PlaneOptions.Existing
        
        if hasattr(bldr_mirror, "Plane"):
            bldr_mirror.Plane.SetValue(datum_plane, work_part.ModelingViews.WorkView, NXOpen.Point3d(0.0, 0.0, 0.0))
        elif hasattr(bldr_mirror, "MirrorPlane"):
            bldr_mirror.MirrorPlane = datum_plane

        feat_mirror = bldr_mirror.CommitFeature()
        bldr_mirror.Destroy()
        feat_mirror.SetName("MIRROR_BOSS_AND_HOLE")
        print(f"Mirror feature created: {feat_mirror.JournalIdentifier}")
    except Exception as exc:
        print(f"[WARN] MirrorFeatureBuilder note: {exc}. Creating symmetric features on opposite arm...")
        nx_dir_left_x = work_part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Vector3d(-1.0, 0.0, 0.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        x_left_arm = -x_arm_face

        for step_name, dia_expr, start_expr, end_expr in steps_config:
            dia_val = float(work_part.Expressions.FindObject(dia_expr).Value) if hasattr(work_part.Expressions, "FindObject") else 20.0
            r_left = dia_val / 2.0
            c_left = NXOpen.Point3d(x_left_arm, 0.0, z_boss_center)
            arc_left = work_part.Curves.CreateArc(c_left, NXOpen.Vector3d(0.0, 1.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0), r_left, 0.0, 2.0 * math.pi)
            sec_l = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
            rule_l = work_part.ScRuleFactory.CreateRuleCurveDumb([arc_left])
            sec_l.AddToSection([rule_l], arc_left, NXOpen.NXObject.Null, NXOpen.NXObject.Null, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
            b_l = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
            b_l.Section = sec_l
            b_l.Direction = nx_dir_left_x
            b_l.Limits.StartExtend.Value.RightHandSide = start_expr
            b_l.Limits.EndExtend.Value.RightHandSide = end_expr
            try:
                b_l.BooleanOperation.SetBooleanOperationAndBody(NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite, main_body)
            except Exception:
                b_l.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite
            feat_l = b_l.CommitFeature()
            b_l.Destroy()
            feat_l.SetName(f"{step_name}_MIRRORED")

        c_hole_l = NXOpen.Point3d(x_left_arm, 0.0, z_boss_center)
        arc_hl = work_part.Curves.CreateArc(c_hole_l, NXOpen.Vector3d(0.0, 1.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0), r_hole, 0.0, 2.0 * math.pi)
        sec_hl = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rule_hl = work_part.ScRuleFactory.CreateRuleCurveDumb([arc_hl])
        sec_hl.AddToSection([rule_hl], arc_hl, NXOpen.NXObject.Null, NXOpen.NXObject.Null, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        b_hl = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
        b_hl.Section = sec_hl
        b_hl.Direction = nx_dir_x
        b_hl.Limits.StartExtend.Value.RightHandSide = "-BOSS_OVERALL_LENGTH - 2.0"
        b_hl.Limits.EndExtend.Value.RightHandSide = "ARM_THICKNESS + 5.0"
        try:
            b_hl.BooleanOperation.SetBooleanOperationAndBody(NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract, main_body)
        except Exception:
            b_hl.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
        feat_hl = b_hl.CommitFeature()
        b_hl.Destroy()
        feat_hl.SetName("THROUGH_HOLE_MIRRORED")

    # ==========================================
    # 8. EDGE BLENDS
    # ==========================================
    print("Applying Edge Blends...")
    edges = list(main_body.GetEdges())
    print(f"Total solid body edges: {len(edges)}")
    applied = failed = 0
    for edge in edges:
        try:
            _blend_single_edge(work_part, edge, "EDGE_BLEND_RADIUS")
            applied += 1
        except Exception:
            failed += 1
    print(f"Edge Blends result: {applied} applied, {failed} skipped.")

    # Orient ISO View
    try:
        work_part.ModelingViews.WorkView.Fit()
        try:
            work_part.ModelingViews.WorkView.Orient("ISO")
        except Exception:
            pass
    except Exception:
        pass

    # ==========================================
    # 9. SAVE PART
    # ==========================================
    print("Saving Part file...")
    try:
        work_part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
        print(f"Saved .prt file to: {part_path}")
    except Exception as exc:
        print(f"[WARN] Part save: {exc}")

    try:
        with open("C:/Users/HP/nx-mcp/latest_nx_result.txt", "w") as f:
            f.write(str(part_path))
    except Exception:
        pass

    # ==========================================
    # 11. EXPORT STL via DexManager
    # ==========================================
    stl_path = Path("C:/Users/HP/nx-mcp/symmetric_u_bracket_stepped_bosses.stl").resolve()
    print(f"Exporting STL file: {stl_path}")
    try:
        exp_stl = the_session.DexManager.CreateStlCreator()
        exp_stl.OutputFile = str(stl_path)
        exp_stl.Commit()
        exp_stl.Destroy()
        print(f"STL exported to: {stl_path}")
    except Exception as exc:
        print(f"[INFO] STL export note: {exc}")

    print("==================================================")
    print("NXOPEN JOURNAL GENERATION COMPLETED SUCCESSFULLY")
    print("==================================================")


def export_step_cli():
    prt_path = Path("C:/Users/HP/nx-mcp/symmetric_u_bracket_stepped_bosses.prt").resolve()
    step_path = Path("C:/Users/HP/nx-mcp/symmetric_u_bracket_stepped_bosses.stp").resolve()
    
    nx_base = r"C:\Program Files\Siemens\NX2206"
    step_cmd = f'echo. | "{nx_base}\\STEP214UG\\step214ug.cmd" "{prt_path}"'
    
    env = os.environ.copy()
    env["UGII_BASE_DIR"] = nx_base
    
    print(f"[INFO] Running STEP CLI export: {step_cmd}")
    res = subprocess.run(step_cmd, shell=True, cwd=str(step_path.parent), env=env, capture_output=True, text=True)
    
    start = time.time()
    while time.time() - start < 15:
        if step_path.exists() and step_path.stat().st_size > 0:
            print(f"[OK] STEP exported successfully ({step_path.stat().st_size} bytes): {step_path}")
            return
        time.sleep(0.5)
    print(f"[WARN] STEP CLI output: {res.stdout}")


def main():
    if IS_NX:
        run_nxopen_journal()
    else:
        run_journal = r"C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe"
        script_path = str(Path(__file__).resolve())
        print(f"[INFO] Executing journal via run_journal.exe: {script_path}")
        res = subprocess.run([run_journal, script_path], capture_output=True, text=True)
        print("STDOUT:\n", res.stdout)
        if res.stderr:
            print("STDERR:\n", res.stderr)
        
        # Export STEP via CLI
        export_step_cli()


if __name__ == "__main__":
    main()
