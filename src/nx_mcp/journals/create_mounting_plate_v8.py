"""
create_mounting_plate_v8.py
===========================
NX Journal: Parametric clevis mounting plate V8.

Based on proven V4/V7 codebase with updated expressions and geometry positioning.

21-step build order:
  1.  Sketch (base plate)
  2.  Extrude (base plate)
  3.  Edge Blend (outer plate corners)
  4.  Hole (4 corner mounting holes)
  5.  Sketch (rear D-shaped lug)
  6.  Extrude (rear lug)
  7.  Sketch (front D-shaped lug)
  8.  Extrude (front lug)
  9.  Hole (rear lug)
  10. Hole (front lug)
  11. Sketch (front relief slit)
  12. Extrude Remove (relief slit)
  13. Sketch (rectangular pocket)
  14. Extrude Remove (rectangular pocket)
  15. Sketch (left triangle)
  16. Extrude Remove (left triangle)
  17. Mirror Feature (right triangle)
  18. Edge Blend (remaining edges)
  19. Save Part
  20. Export STEP
  21. Export STL
"""

import sys
import os
import math
from pathlib import Path
import subprocess

import NXOpen
import NXOpen.UF

# ---------------------------------------------------------------------------
# Parametric Constants (mm)
# ---------------------------------------------------------------------------
PLATE_LENGTH         = 160.0
PLATE_WIDTH          = 100.0
PLATE_THICKNESS      = 10.0
PLATE_CORNER_RADIUS  = 8.0

CORNER_HOLE_DIAMETER = 8.0
CORNER_HOLE_OFFSET_X = 19.2   # 12% of PLATE_LENGTH
CORNER_HOLE_OFFSET_Y = 19.2   # symmetric

LUG_WIDTH            = 36.0   # Y extent (~1.8 x thickness)
LUG_THICKNESS        = 20.0   # X extent
LUG_HEIGHT           = 50.0   # Z height above plate top
LUG_SPACING          = 6.0    # X gap between inner faces (constant gap)

LUG_HOLE_DIAMETER    = 16.0

RELIEF_SLOT_WIDTH    = 7.2    # ~20% of LUG_WIDTH
RELIEF_SLOT_LENGTH   = 24.0   # derived: LUG_HEIGHT - LUG_WIDTH/2 - LUG_HOLE_DIAMETER/2

RECT_POCKET_WIDTH    = 36.0   # approx combined width of lugs (36.0)
RECT_POCKET_HEIGHT   = 27.0   # 0.75 times width
RECT_POCKET_OFFSET   = 5.0    # vertical clearance from bottom of front lug

TRIANGLE_BASE        = 36.0
TRIANGLE_HEIGHT      = 26.0
TRIANGLE_OFFSET_X    = 38.0
TRIANGLE_OFFSET_Y    = 32.0   # centers it vertically below upper-left hole

GENERAL_FILLET_RADIUS = 2.0

# Derived geometry constants
HALF_PL  = PLATE_LENGTH / 2.0
HALF_PW  = PLATE_WIDTH  / 2.0
HALF_LW  = LUG_WIDTH    / 2.0
ARC_CZ   = PLATE_THICKNESS + LUG_HEIGHT - HALF_LW
REAR_BACK_X  = -(LUG_SPACING / 2.0 + LUG_THICKNESS)
FRONT_BACK_X = LUG_SPACING / 2.0

# Pocket positioned DIRECTLY BELOW the lugs (+X direction)
POCKET_X_MIN = FRONT_BACK_X + LUG_THICKNESS + RECT_POCKET_OFFSET
POCKET_X_MAX = POCKET_X_MIN + RECT_POCKET_HEIGHT


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "mounting_plate_v8.prt"


# ---------------------------------------------------------------------------
# Boolean helpers
# ---------------------------------------------------------------------------
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
# Sketch helpers
# ---------------------------------------------------------------------------
def _con_geom(curve, point_type=None):
    geom = NXOpen.Sketch.ConstraintGeometry()
    geom.Geometry = curve
    geom.PointType = point_type or NXOpen.SketchConstraintPointType.NotSet
    return geom


def _create_sketch_on_csys(work_part, origin, x_vec, y_vec, z_vec, sketch_name):
    """Create a sketch on a coordinate system defined by origin and 3 orthogonal vectors."""
    matrix = NXOpen.Matrix3x3()
    matrix.Xx = x_vec.X; matrix.Xy = x_vec.Y; matrix.Xz = x_vec.Z
    matrix.Yx = y_vec.X; matrix.Yy = y_vec.Y; matrix.Yz = y_vec.Z
    matrix.Zx = z_vec.X; matrix.Zy = z_vec.Y; matrix.Zz = z_vec.Z
    nx_matrix = work_part.NXMatrices.Create(matrix)
    csys = work_part.CoordinateSystems.CreateCoordinateSystem(origin, nx_matrix, True)

    factory2 = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder2", None)
    builder = None
    if factory2 is not None:
        try:
            builder = factory2(None)
        except Exception:
            pass
    if builder is None:
        factory = getattr(work_part.Sketches, "CreateNewSketchInPlaceBuilder", None)
        if factory is None:
            factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder", None)
        builder = factory(None)
    try:
        builder.Csystem = csys
        commit = getattr(builder, "CommitFeature", None) or getattr(builder, "Commit", None)
        feat = commit()
    finally:
        builder.Destroy()
    try:
        feat.SetName(sketch_name)
    except Exception:
        pass
    sketch = feat.Sketch if hasattr(feat, "Sketch") else feat
    return feat, sketch


# ---------------------------------------------------------------------------
# Extrude helper
# ---------------------------------------------------------------------------
def _extrude_curves(work_part, curves, dir_vec, start_expr, end_expr,
                    feature_name, boolean_type=None, target_body=None):
    """Extrude a set of curves as a section."""
    if boolean_type is None:
        boolean_type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create

    section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
    rules = [work_part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    section.AddToSection(
        rules, curves[0],
        NXOpen.NXObject.Null, NXOpen.NXObject.Null,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create, False)

    builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section
        nx_dir = work_part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), dir_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Direction = nx_dir
        builder.Limits.StartExtend.Value.RightHandSide = start_expr
        builder.Limits.EndExtend.Value.RightHandSide   = end_expr
        if target_body is not None:
            builder.BooleanOperation.SetBooleanOperationAndBody(boolean_type, target_body)
        else:
            builder.BooleanOperation.Type = boolean_type
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    try:
        feat.SetName(feature_name)
    except Exception:
        pass
    return feat, feat.GetBodies()[0]


# ---------------------------------------------------------------------------
# Mirror Feature helper
# ---------------------------------------------------------------------------
def _mirror_feature(work_part, source_feature, plane_name):
    """Mirror source_feature about a fixed datum plane (XY, XZ, or YZ)."""
    fixed_types = {
        "XY": NXOpen.Features.DatumPlaneBuilder.FixedType.Xy,
        "XZ": NXOpen.Features.DatumPlaneBuilder.FixedType.Zx,
        "ZX": NXOpen.Features.DatumPlaneBuilder.FixedType.Zx,
        "YZ": NXOpen.Features.DatumPlaneBuilder.FixedType.Yz,
    }
    datum_builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        datum_builder.SetFixedDatumPlane(fixed_types[plane_name.upper()])
        datum_feat = datum_builder.CommitFeature()
        datum_plane = datum_feat.DatumPlane
    finally:
        datum_builder.Destroy()

    builder = work_part.Features.CreateMirrorFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        if hasattr(builder, "FeatureSet"):
            builder.FeatureSet.Add([source_feature])
        elif hasattr(builder, "Features"):
            builder.Features.Add([source_feature])
        if hasattr(builder, "PlaneOption"):
            builder.PlaneOption = NXOpen.Features.MirrorFeatureBuilder.PlaneOptions.Existing
        if hasattr(builder, "Plane"):
            builder.Plane.SetValue(
                datum_plane, work_part.ModelingViews.WorkView,
                NXOpen.Point3d(0.0, 0.0, 0.0))
        elif hasattr(builder, "MirrorPlane"):
            builder.MirrorPlane = datum_plane
        feat = builder.CommitFeature()
        return feat
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Edge Blend helpers
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


def _add_edge_blend(work_part, body, radius_expr, label=""):
    """Apply blend per-edge with try-except for robustness."""
    edges = list(body.GetEdges())
    applied = failed = 0
    for edge in edges:
        try:
            _blend_single_edge(work_part, edge, radius_expr)
            applied += 1
        except Exception:
            failed += 1
    print("[OK] Blend {}: {} applied, {} skipped.".format(label, applied, failed))


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
                ugs_router = cand; break
        if ugs_router is None:
            ugs_router = Path(r"C:\Program Files\Siemens\NX2206\NXBIN\ugs_router.exe")
        (project_root / "open_current_nx_result.cmd").write_text(
            '@echo off\nstart "" "{}" -ug -use_file_dir "{}"\n'.format(ugs_router, abs_str),
            encoding="utf-8")
        print("[OK] Result files updated.")
    except Exception as exc:
        print("[WARN] Could not update result files: {}".format(exc))


# ---------------------------------------------------------------------------
# Main — 21 step build
# ---------------------------------------------------------------------------
def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            output_path.unlink()
        except Exception:
            pass

    session   = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    print("=" * 60)
    print("  PARAMETRIC CLEVIS MOUNTING PLATE V8")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # NX Expressions
    # ------------------------------------------------------------------
    for name, val in [
        ("PLATE_LENGTH",         PLATE_LENGTH),
        ("PLATE_WIDTH",          PLATE_WIDTH),
        ("PLATE_THICKNESS",      PLATE_THICKNESS),
        ("PLATE_CORNER_RADIUS",  PLATE_CORNER_RADIUS),
        ("CORNER_HOLE_DIAMETER", CORNER_HOLE_DIAMETER),
        ("CORNER_HOLE_OFFSET_X", CORNER_HOLE_OFFSET_X),
        ("CORNER_HOLE_OFFSET_Y", CORNER_HOLE_OFFSET_Y),
        ("LUG_WIDTH",            LUG_WIDTH),
        ("LUG_THICKNESS",        LUG_THICKNESS),
        ("LUG_HEIGHT",           LUG_HEIGHT),
        ("LUG_SPACING",          LUG_SPACING),
        ("LUG_HOLE_DIAMETER",    LUG_HOLE_DIAMETER),
        ("RELIEF_SLOT_WIDTH",    RELIEF_SLOT_WIDTH),
        ("RELIEF_SLOT_LENGTH",   RELIEF_SLOT_LENGTH),
        ("RECT_POCKET_WIDTH",    RECT_POCKET_WIDTH),
        ("RECT_POCKET_HEIGHT",   RECT_POCKET_HEIGHT),
        ("RECT_POCKET_OFFSET",   RECT_POCKET_OFFSET),
        ("TRIANGLE_BASE",        TRIANGLE_BASE),
        ("TRIANGLE_HEIGHT",      TRIANGLE_HEIGHT),
        ("TRIANGLE_OFFSET_X",    TRIANGLE_OFFSET_X),
        ("TRIANGLE_OFFSET_Y",    TRIANGLE_OFFSET_Y),
        ("GENERAL_FILLET_RADIUS", GENERAL_FILLET_RADIUS),
    ]:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, val))
    print("[OK] NX Expressions created.")

    infer = NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints

    # ==================================================================
    # Step 1: Sketch (base plate rectangle on XY plane)
    # ==================================================================
    print("[...] Step 1: Sketching base plate rectangle...")
    feat_s1, sk1 = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        "S01_Base_Plate")
    sk1.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    bp1 = NXOpen.Point3d(-HALF_PL, -HALF_PW, 0.0)
    bp2 = NXOpen.Point3d( HALF_PL, -HALF_PW, 0.0)
    bp3 = NXOpen.Point3d( HALF_PL,  HALF_PW, 0.0)
    bp4 = NXOpen.Point3d(-HALF_PL,  HALF_PW, 0.0)

    bl1 = work_part.Curves.CreateLine(bp1, bp2)
    bl2 = work_part.Curves.CreateLine(bp2, bp3)
    bl3 = work_part.Curves.CreateLine(bp3, bp4)
    bl4 = work_part.Curves.CreateLine(bp4, bp1)

    for c in (bl1, bl2, bl3, bl4):
        sk1.AddGeometry(c, infer)
    sk1.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print("[OK] Step 1 complete.")

    # ==================================================================
    # Step 2: Extrude (base plate +Z)
    # ==================================================================
    print("[...] Step 2: Extruding base plate...")
    feat_plate, base_body = _extrude_curves(
        work_part, [bl1, bl2, bl3, bl4],
        NXOpen.Vector3d(0.0, 0.0, 1.0), "0.0", "PLATE_THICKNESS",
        "F01_Base_Plate")
    print("[OK] Step 2 complete. Base plate extruded.")

    # ==================================================================
    # Step 3: Edge Blend (outer plate corners — before other features)
    # ==================================================================
    print("[...] Step 3: Blending base plate perimeter edges...")
    _add_edge_blend(work_part, base_body, "PLATE_CORNER_RADIUS", "perimeter")
    print("[OK] Step 3 complete.")

    # ==================================================================
    # Step 4: Hole (4 corner mounting holes via cylinder-subtract)
    # ==================================================================
    print("[...] Step 4: Creating 4 corner holes...")
    hole_positions = [
        (-HALF_PL + CORNER_HOLE_OFFSET_X, -HALF_PW + CORNER_HOLE_OFFSET_Y),
        ( HALF_PL - CORNER_HOLE_OFFSET_X, -HALF_PW + CORNER_HOLE_OFFSET_Y),
        (-HALF_PL + CORNER_HOLE_OFFSET_X,  HALF_PW - CORNER_HOLE_OFFSET_Y),
        ( HALF_PL - CORNER_HOLE_OFFSET_X,  HALF_PW - CORNER_HOLE_OFFSET_Y),
    ]
    for hx, hy in hole_positions:
        cb = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        try:
            origin = NXOpen.Point3d(hx, hy, -1.0)
            direction = work_part.Directions.CreateDirection(
                origin, NXOpen.Vector3d(0.0, 0.0, 1.0),
                NXOpen.SmartObject.UpdateOption.WithinModeling)
            cb.Diameter.RightHandSide = "CORNER_HOLE_DIAMETER"
            cb.Height.RightHandSide   = str(PLATE_THICKNESS + 2.0)
            cb.Axis.Point.SetCoordinates(origin)
            cb.Axis.Direction = direction
            cf = cb.Commit()
            _perform_subtract(work_part, base_body, cf.GetBodies()[0])
        finally:
            cb.Destroy()
    print("[OK] Step 4 complete. 4 corner holes created.")

    # ==================================================================
    # Helper: create D-shaped lug profile sketch + extrude
    # ==================================================================
    def _create_lug(back_x, sketch_name, feature_name):
        """Sketch a D-shaped profile on YZ plane at X=back_x, extrude +X."""
        feat_sk, sk = _create_sketch_on_csys(
            work_part,
            NXOpen.Point3d(back_x, 0.0, 0.0),
            NXOpen.Vector3d(0.0, 1.0, 0.0),   # local X = world Y
            NXOpen.Vector3d(0.0, 0.0, 1.0),   # local Y = world Z
            NXOpen.Vector3d(1.0, 0.0, 0.0),   # normal  = world X
            sketch_name)
        sk.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

        # Profile points (in world coords at X = back_x)
        lp1 = NXOpen.Point3d(back_x, -HALF_LW, PLATE_THICKNESS)
        lp2 = NXOpen.Point3d(back_x,  HALF_LW, PLATE_THICKNESS)
        lp3 = NXOpen.Point3d(back_x,  HALF_LW, ARC_CZ)
        lp4 = NXOpen.Point3d(back_x, -HALF_LW, ARC_CZ)

        bottom = work_part.Curves.CreateLine(lp1, lp2)
        right  = work_part.Curves.CreateLine(lp2, lp3)
        left   = work_part.Curves.CreateLine(lp4, lp1)

        # Semicircular arc from p3 (angle 0) to p4 (angle pi) over the top
        arc_centre = NXOpen.Point3d(back_x, 0.0, ARC_CZ)
        arc = work_part.Curves.CreateArc(
            arc_centre,
            NXOpen.Vector3d(0.0, 1.0, 0.0),   # x-dir in arc plane
            NXOpen.Vector3d(0.0, 0.0, 1.0),   # y-dir in arc plane
            HALF_LW, 0.0, math.pi)

        for c in (bottom, right, arc, left):
            sk.AddGeometry(c, infer)
        sk.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

        feat_ext, body = _extrude_curves(
            work_part, [bottom, right, arc, left],
            NXOpen.Vector3d(1.0, 0.0, 0.0), "0.0", "LUG_THICKNESS",
            feature_name,
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
            base_body)
        return feat_ext

    # ==================================================================
    # Steps 5–6: Sketch + Extrude rear lug
    # ==================================================================
    print("[...] Steps 5-6: Creating rear D-shaped lug...")
    feat_rear_lug = _create_lug(REAR_BACK_X, "S02_Rear_Lug", "F02_Rear_Lug")
    print("[OK] Steps 5-6 complete. Rear lug created.")

    # ==================================================================
    # Steps 7–8: Sketch + Extrude front lug
    # ==================================================================
    print("[...] Steps 7-8: Creating front D-shaped lug...")
    feat_front_lug = _create_lug(FRONT_BACK_X, "S03_Front_Lug", "F03_Front_Lug")
    print("[OK] Steps 7-8 complete. Front lug created.")

    # ==================================================================
    # Helper: create through-hole in a lug via cylinder-subtract
    # ==================================================================
    def _create_lug_hole(back_x):
        """Through-hole at arc centre, aligned with +X through lug thickness."""
        cb = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        try:
            origin = NXOpen.Point3d(back_x - 1.0, 0.0, ARC_CZ)
            direction = work_part.Directions.CreateDirection(
                origin, NXOpen.Vector3d(1.0, 0.0, 0.0),
                NXOpen.SmartObject.UpdateOption.WithinModeling)
            cb.Diameter.RightHandSide = "LUG_HOLE_DIAMETER"
            cb.Height.RightHandSide   = str(LUG_THICKNESS + 2.0)
            cb.Axis.Point.SetCoordinates(origin)
            cb.Axis.Direction = direction
            cf = cb.Commit()
            _perform_subtract(work_part, base_body, cf.GetBodies()[0])
        finally:
            cb.Destroy()

    # ==================================================================
    # Step 9: Hole (rear lug)
    # ==================================================================
    print("[...] Step 9: Creating rear lug through-hole...")
    _create_lug_hole(REAR_BACK_X)
    print("[OK] Step 9 complete.")

    # ==================================================================
    # Step 10: Hole (front lug)
    # ==================================================================
    print("[...] Step 10: Creating front lug through-hole...")
    _create_lug_hole(FRONT_BACK_X)
    print("[OK] Step 10 complete.")

    # ==================================================================
    # Steps 11–12: Sketch + Extrude Remove (relief slit on FRONT lug)
    # ==================================================================
    print("[...] Steps 11-12: Creating relief slit on front lug...")
    feat_s_slit, sk_slit = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(FRONT_BACK_X, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        "S04_Relief_Slit")
    sk_slit.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    slit_half_w = RELIEF_SLOT_WIDTH / 2.0
    # Overlap 2mm into the hole to avoid zero-thickness wall error
    slit_z_max  = ARC_CZ - LUG_HOLE_DIAMETER / 2.0 + 2.0
    slit_z_min  = PLATE_THICKNESS

    sp1 = NXOpen.Point3d(FRONT_BACK_X, -slit_half_w, slit_z_min)
    sp2 = NXOpen.Point3d(FRONT_BACK_X,  slit_half_w, slit_z_min)
    sp3 = NXOpen.Point3d(FRONT_BACK_X,  slit_half_w, slit_z_max)
    sp4 = NXOpen.Point3d(FRONT_BACK_X, -slit_half_w, slit_z_max)

    sl1 = work_part.Curves.CreateLine(sp1, sp2)
    sl2 = work_part.Curves.CreateLine(sp2, sp3)
    sl3 = work_part.Curves.CreateLine(sp3, sp4)
    sl4 = work_part.Curves.CreateLine(sp4, sp1)

    for c in (sl1, sl2, sl3, sl4):
        sk_slit.AddGeometry(c, infer)
    sk_slit.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    _extrude_curves(
        work_part, [sl1, sl2, sl3, sl4],
        NXOpen.Vector3d(1.0, 0.0, 0.0), "0.0", str(LUG_THICKNESS + 2.0),
        "F04_Relief_Slit",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
        base_body)
    print("[OK] Steps 11-12 complete. Relief slit subtracted.")

    # ==================================================================
    # Steps 13–14: Sketch + Extrude Remove (rectangular pocket BELOW lugs)
    # ==================================================================
    print("[...] Steps 13-14: Creating rectangular pocket...")
    feat_s_pkt, sk_pkt = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, 0.0, PLATE_THICKNESS),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        "S05_Rect_Pocket")
    sk_pkt.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    pkt_hw = RECT_POCKET_WIDTH / 2.0
    pp1 = NXOpen.Point3d(POCKET_X_MIN, -pkt_hw, PLATE_THICKNESS)
    pp2 = NXOpen.Point3d(POCKET_X_MAX, -pkt_hw, PLATE_THICKNESS)
    pp3 = NXOpen.Point3d(POCKET_X_MAX,  pkt_hw, PLATE_THICKNESS)
    pp4 = NXOpen.Point3d(POCKET_X_MIN,  pkt_hw, PLATE_THICKNESS)

    pl1 = work_part.Curves.CreateLine(pp1, pp2)
    pl2 = work_part.Curves.CreateLine(pp2, pp3)
    pl3 = work_part.Curves.CreateLine(pp3, pp4)
    pl4 = work_part.Curves.CreateLine(pp4, pp1)

    for c in (pl1, pl2, pl3, pl4):
        sk_pkt.AddGeometry(c, infer)
    sk_pkt.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    _extrude_curves(
        work_part, [pl1, pl2, pl3, pl4],
        NXOpen.Vector3d(0.0, 0.0, -1.0), "0.0", str(PLATE_THICKNESS + 2.0),
        "F05_Rect_Pocket",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
        base_body)
    print("[OK] Steps 13-14 complete. Rectangular pocket subtracted.")

    # ==================================================================
    # Steps 15–16: Sketch + Extrude Remove (left triangle)
    # ==================================================================
    print("[...] Steps 15-16: Creating left triangular cut-out...")
    feat_s_tri, sk_tri = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, 0.0, PLATE_THICKNESS),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        "S06_Left_Triangle")
    sk_tri.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    # Center of left triangle
    tri_cx = -TRIANGLE_OFFSET_X
    tri_cy = -TRIANGLE_OFFSET_Y
    tri_half_b = TRIANGLE_BASE / 2.0
    tri_half_h = TRIANGLE_HEIGHT / 2.0

    # Base is approximately vertical (parallel to X-axis), apex points left (toward -Y)
    tp1 = NXOpen.Point3d(tri_cx - tri_half_b, tri_cy + tri_half_h, PLATE_THICKNESS)  # top-left of base
    tp2 = NXOpen.Point3d(tri_cx + tri_half_b, tri_cy + tri_half_h, PLATE_THICKNESS)  # top-right of base
    tp3 = NXOpen.Point3d(tri_cx,              tri_cy - tri_half_h, PLATE_THICKNESS)  # apex pointing left (-Y)

    tl1 = work_part.Curves.CreateLine(tp1, tp2)  # base line (parallel to X)
    tl2 = work_part.Curves.CreateLine(tp2, tp3)  # right leg
    tl3 = work_part.Curves.CreateLine(tp3, tp1)  # left leg

    for c in (tl1, tl2, tl3):
        sk_tri.AddGeometry(c, infer)
    sk_tri.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    feat_tri, _ = _extrude_curves(
        work_part, [tl1, tl2, tl3],
        NXOpen.Vector3d(0.0, 0.0, -1.0), "0.0", str(PLATE_THICKNESS + 2.0),
        "F06_Left_Triangle",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
        base_body)
    print("[OK] Steps 15-16 complete. Left triangle subtracted.")

    # ==================================================================
    # Step 17: Mirror Feature (right triangle about XZ plane / Y=0)
    # ==================================================================
    print("[...] Step 17: Mirroring triangle about XZ plane...")
    _mirror_feature(work_part, feat_tri, "XZ")
    print("[OK] Step 17 complete. Right triangle mirrored.")

    # ==================================================================
    # Step 18: Edge Blend (remaining edges with GENERAL_FILLET_RADIUS)
    # ==================================================================
    print("[...] Step 18: Applying general edge blends...")
    _add_edge_blend(work_part, base_body, "GENERAL_FILLET_RADIUS", "general")
    print("[OK] Step 18 complete.")

    # ==================================================================
    # Orient ISO View
    # ==================================================================
    try:
        work_part.ModelingViews.WorkView.Fit()
        try:
            work_part.ModelingViews.WorkView.Orient("ISO")
        except Exception:
            pass
        print("[OK] View set to ISO.")
    except Exception:
        pass

    # ==================================================================
    # Step 19: Save Part
    # ==================================================================
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("[OK] Step 19 complete. Part saved -> {}".format(output_path))

    # ==================================================================
    # Step 20: Export STEP
    # ==================================================================
    step_path = output_path.with_suffix(".stp")
    print("[...] Step 20: Exporting STEP...")
    try:
        exp = session.DexManager.CreateStepCreator()
        exp.ObjectTypes.Solids = True
        exp.OutputFile = str(step_path)
        exp.Commit()
        exp.Destroy()
        print("[OK] STEP exported -> {}".format(step_path))
    except Exception as exc:
        print("[WARN] STEP export failed: {}".format(exc))

    # ==================================================================
    # Step 21: Export STL
    # ==================================================================
    stl_path = output_path.with_suffix(".stl")
    print("[...] Step 21: Exporting STL...")
    try:
        exp = session.DexManager.CreateStlCreator()
        exp.OutputFile = str(stl_path)
        exp.Commit()
        exp.Destroy()
        print("[OK] STL exported -> {}".format(stl_path))
    except Exception as exc:
        print("[WARN] STL export failed: {}".format(exc))

    # ==================================================================
    # Result watcher + auto-open
    # ==================================================================
    _update_result_files(output_path)

    try:
        base_dir  = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        ugs_router = None
        for cand in [base_path / "NXBIN" / "ugs_router.exe",
                     base_path / "UGII"  / "ugs_router.exe"]:
            if cand.exists():
                ugs_router = cand; break
        if ugs_router:
            subprocess.Popen([str(ugs_router), "-ug", "-use_file_dir",
                              str(output_path.resolve())])
            print("[OK] NX GUI launched.")
    except Exception:
        pass

    print("=" * 60)
    print("[DONE] Mounting plate V8 complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
