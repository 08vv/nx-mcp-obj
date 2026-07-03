"""
create_mounting_plate_v5.py
===========================
NX Journal: Parametric clevis mounting plate with D-shaped lugs and absolute positioning.

18-step build order:
  1.  Sketch (base plate)
  2.  Extrude Base Plate
  3.  Edge Blend Plate (corners only)
  4.  Four Corner Holes
  5.  Sketch Rear Lug
  6.  Extrude Rear Lug
  7.  Sketch Front Lug
  8.  Extrude Front Lug
  9.  Rear Lug Hole
  10. Front Lug Hole
  11. Relief Slot
  12. Rectangular Pocket
  13. Left Triangle
  14. Mirror Triangle
  15. Remaining Edge Blends
  16. Save Part
  17. Export STEP
  18. Export STL
"""

import sys
import os
import math
from pathlib import Path
import subprocess

import NXOpen

# ---------------------------------------------------------------------------
# Parametric Constants (mm)
# ---------------------------------------------------------------------------
PLATE_LENGTH         = 160.0
PLATE_WIDTH          = 100.0
PLATE_THICKNESS      = 10.0
PLATE_CORNER_RADIUS  = 8.0

CORNER_HOLE_DIAMETER = 8.0
CORNER_OFFSET_X      = 19.2  # 12% of PLATE_LENGTH
CORNER_OFFSET_Y      = 12.0

LUG_WIDTH            = 20.0  # narrower to avoid pocket overlap in Y
LUG_THICKNESS        = 11.0  # width ~ 1.8 * thickness (20.0 / 11.0 = 1.81)
LUG_HEIGHT           = 40.0
LUG_SPACING          = 6.0

LUG_HOLE_DIAMETER    = 10.0

RELIEF_SLOT_WIDTH    = 4.0   # 20% of LUG_WIDTH
RELIEF_SLOT_LENGTH   = 22.0  # derived: LUG_HEIGHT - LUG_WIDTH/2 - LUG_HOLE_DIAMETER/2

RECT_POCKET_WIDTH    = 20.0  # equal to LUG_WIDTH
RECT_POCKET_HEIGHT   = 26.0  # 1.3 * RECT_POCKET_WIDTH
RECT_POCKET_CENTER_Y = 72.0  # 0.72 * PLATE_WIDTH

TRIANGLE_BASE        = 20.0
TRIANGLE_HEIGHT      = 16.0
TRIANGLE_CENTER_X    = 36.8  # 0.23 * PLATE_LENGTH
TRIANGLE_CENTER_Y    = 72.0  # 0.72 * PLATE_WIDTH

GENERAL_FILLET_RADIUS = 2.0

# Derived coordinates
HALF_LW  = LUG_WIDTH / 2.0
ARC_CZ   = PLATE_THICKNESS + LUG_HEIGHT - HALF_LW
REAR_X   = PLATE_LENGTH / 2.0 - LUG_THICKNESS - LUG_SPACING / 2.0  # 80 - 11 - 3 = 66
FRONT_X  = PLATE_LENGTH / 2.0 + LUG_SPACING / 2.0                 # 80 + 3 = 83


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "mounting_plate_v5.prt"


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
# Sketch & Plane helpers
# ---------------------------------------------------------------------------
def _con_geom(curve, point_type=None):
    geom = NXOpen.Sketch.ConstraintGeometry()
    geom.Geometry = curve
    geom.PointType = point_type or NXOpen.SketchConstraintPointType.NotSet
    return geom


def _create_datum_plane_at_x(work_part, x_val):
    pt = work_part.Points.CreatePoint(NXOpen.Point3d(x_val, 0.0, 0.0))
    pt3d = NXOpen.Point3d(x_val, 0.0, 0.0)
    dir_vector = NXOpen.Vector3d(1.0, 0.0, 0.0)
    nx_dir = work_part.Directions.CreateDirection(pt3d, dir_vector, NXOpen.SmartObject.UpdateOption.WithinModeling)
    
    datum_builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        plane = datum_builder.GetPlane()
        plane.SetMethod(NXOpen.PlaneTypes.MethodType.PointDir)
        plane.SetGeometry([pt, nx_dir])
        datum_feat = datum_builder.CommitFeature()
        return datum_feat, datum_feat.DatumPlane
    finally:
        datum_builder.Destroy()


def _create_sketch_on_plane(work_part, plane_obj, sketch_name):
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
        for attr in ("PlaneOrFace", "PlaneReference", "PlacementFace"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, plane_obj); break
                except Exception:
                    pass
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


def _create_sketch_on_csys(work_part, origin, x_vec, y_vec, z_vec, sketch_name):
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
def _mirror_feature(work_part, source_feature, plane_obj):
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
                plane_obj, work_part.ModelingViews.WorkView,
                NXOpen.Point3d(0.0, 0.0, 0.0))
        elif hasattr(builder, "MirrorPlane"):
            builder.MirrorPlane = plane_obj
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


def _add_edge_blend(work_part, edges, radius_expr, label=""):
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
# Main — 18 step build
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
    print("  PARAMETRIC CLEVIS MOUNTING PLATE V5")
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
        ("CORNER_OFFSET_X",      CORNER_OFFSET_X),
        ("CORNER_OFFSET_Y",      CORNER_OFFSET_Y),
        ("LUG_WIDTH",            LUG_WIDTH),
        ("LUG_THICKNESS",        LUG_THICKNESS),
        ("LUG_HEIGHT",           LUG_HEIGHT),
        ("LUG_SPACING",          LUG_SPACING),
        ("LUG_HOLE_DIAMETER",    LUG_HOLE_DIAMETER),
        ("RELIEF_SLOT_WIDTH",    RELIEF_SLOT_WIDTH),
        ("RELIEF_SLOT_LENGTH",   RELIEF_SLOT_LENGTH),
        ("RECT_POCKET_WIDTH",    RECT_POCKET_WIDTH),
        ("RECT_POCKET_HEIGHT",   RECT_POCKET_HEIGHT),
        ("RECT_POCKET_CENTER_Y", RECT_POCKET_CENTER_Y),
        ("TRIANGLE_BASE",        TRIANGLE_BASE),
        ("TRIANGLE_HEIGHT",      TRIANGLE_HEIGHT),
        ("TRIANGLE_CENTER_X",    TRIANGLE_CENTER_X),
        ("TRIANGLE_CENTER_Y",    TRIANGLE_CENTER_Y),
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

    bp1 = NXOpen.Point3d(0.0, 0.0, 0.0)
    bp2 = NXOpen.Point3d(PLATE_LENGTH, 0.0, 0.0)
    bp3 = NXOpen.Point3d(PLATE_LENGTH, PLATE_WIDTH, 0.0)
    bp4 = NXOpen.Point3d(0.0, PLATE_WIDTH, 0.0)

    bl1 = work_part.Curves.CreateLine(bp1, bp2)
    bl2 = work_part.Curves.CreateLine(bp2, bp3)
    bl3 = work_part.Curves.CreateLine(bp3, bp4)
    bl4 = work_part.Curves.CreateLine(bp4, bp1)

    for c in (bl1, bl2, bl3, bl4):
        sk1.AddGeometry(c, infer)
    sk1.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print("[OK] Step 1 complete.")

    # ==================================================================
    # Step 2: Extrude Base Plate
    # ==================================================================
    print("[...] Step 2: Extruding base plate...")
    feat_plate, base_body = _extrude_curves(
        work_part, [bl1, bl2, bl3, bl4],
        NXOpen.Vector3d(0.0, 0.0, 1.0), "0.0", "PLATE_THICKNESS",
        "F01_Base_Plate")
    print("[OK] Step 2 complete. Base plate extruded.")

    # ==================================================================
    # Step 3: Edge Blend Plate (corners only)
    # ==================================================================
    print("[...] Step 3: Blending base plate perimeter vertical corners...")
    base_verticals = []
    for edge in base_body.GetEdges():
        try:
            v1, v2 = edge.GetVertices()
            p1 = v1.GetCoordinates()
            p2 = v2.GetCoordinates()
            # Vertical edges are parallel to Z-axis
            if abs(p1.Z - p2.Z) > 0.1:
                if abs(p1.X - p2.X) < 0.1 and abs(p1.Y - p2.Y) < 0.1:
                    # Must be at the outer perimeter corners (X is near 0 or PLATE_LENGTH, Y is near 0 or PLATE_WIDTH)
                    if (abs(p1.X) < 2.0 or abs(p1.X - PLATE_LENGTH) < 2.0) and \
                       (abs(p1.Y) < 2.0 or abs(p1.Y - PLATE_WIDTH) < 2.0):
                        base_verticals.append(edge)
        except Exception:
            pass

    if base_verticals:
        _add_edge_blend(work_part, base_verticals, "PLATE_CORNER_RADIUS", "perimeter")
    else:
        print("[WARN] No perimeter vertical corners found.")
    print("[OK] Step 3 complete.")

    # ==================================================================
    # Step 4: Four Corner Holes
    # ==================================================================
    print("[...] Step 4: Creating 4 corner holes...")
    hole_positions = [
        (CORNER_OFFSET_X, PLATE_WIDTH - CORNER_OFFSET_Y),                  # Top Left
        (PLATE_LENGTH - CORNER_OFFSET_X, PLATE_WIDTH - CORNER_OFFSET_Y),    # Top Right
        (CORNER_OFFSET_X, CORNER_OFFSET_Y),                                # Bottom Left
        (PLATE_LENGTH - CORNER_OFFSET_X, CORNER_OFFSET_Y),                  # Bottom Right
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
        """Sketch D-shaped profile on YZ plane at X=back_x, extrude +X."""
        # Use csys-based sketch to guarantee coplanarity of all geometry
        feat_sk, sk = _create_sketch_on_csys(
            work_part,
            NXOpen.Point3d(back_x, 0.0, 0.0),
            NXOpen.Vector3d(0.0, 1.0, 0.0),   # sketch local X = world Y
            NXOpen.Vector3d(0.0, 0.0, 1.0),   # sketch local Y = world Z
            NXOpen.Vector3d(1.0, 0.0, 0.0),   # sketch normal  = world X
            sketch_name)
        sk.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

        # Profile points in global coordinates on plane X = back_x
        # Lug is centered on Y = PLATE_WIDTH / 2.0 (50.0)
        y_center = PLATE_WIDTH / 2.0
        lp1 = NXOpen.Point3d(back_x, y_center - HALF_LW, PLATE_THICKNESS)
        lp2 = NXOpen.Point3d(back_x, y_center + HALF_LW, PLATE_THICKNESS)
        lp3 = NXOpen.Point3d(back_x, y_center + HALF_LW, ARC_CZ)
        lp4 = NXOpen.Point3d(back_x, y_center - HALF_LW, ARC_CZ)

        bottom = work_part.Curves.CreateLine(lp1, lp2)
        right  = work_part.Curves.CreateLine(lp2, lp3)
        left   = work_part.Curves.CreateLine(lp4, lp1)

        # Semicircular arc over the top (on YZ plane at X = back_x)
        arc_centre = NXOpen.Point3d(back_x, y_center, ARC_CZ)
        arc = work_part.Curves.CreateArc(
            arc_centre,
            NXOpen.Vector3d(0.0, 1.0, 0.0),   # local x-dir (world Y)
            NXOpen.Vector3d(0.0, 0.0, 1.0),   # local y-dir (world Z)
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
    # Steps 5–6: Sketch + Extrude Rear Lug
    # ==================================================================
    print("[...] Steps 5-6: Creating rear D-shaped lug...")
    feat_rear_lug = _create_lug(REAR_X, "S02_Rear_Lug", "F02_Rear_Lug")
    print("[OK] Steps 5-6 complete. Rear lug created.")

    # ==================================================================
    # Steps 7–8: Sketch + Extrude Front Lug
    # ==================================================================
    print("[...] Steps 7-8: Creating front D-shaped lug...")
    feat_front_lug = _create_lug(FRONT_X, "S03_Front_Lug", "F03_Front_Lug")
    print("[OK] Steps 7-8 complete. Front lug created.")

    # ==================================================================
    # Helper: create through-hole in a lug via cylinder-subtract
    # ==================================================================
    def _create_lug_hole(back_x):
        """Through-hole at arc center, aligned with +X through lug thickness."""
        cb = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        try:
            origin = NXOpen.Point3d(back_x - 1.0, PLATE_WIDTH / 2.0, ARC_CZ)
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
    # Step 9: Rear Lug Hole
    # ==================================================================
    print("[...] Step 9: Creating rear lug through-hole...")
    _create_lug_hole(REAR_X)
    print("[OK] Step 9 complete.")

    # ==================================================================
    # Step 10: Front Lug Hole
    # ==================================================================
    print("[...] Step 10: Creating front lug through-hole...")
    _create_lug_hole(FRONT_X)
    print("[OK] Step 10 complete.")

    # ==================================================================
    # Step 11: Relief Slot
    # ==================================================================
    print("[...] Step 11: Creating relief slot on front lug...")
    feat_s_slit, sk_slit = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(FRONT_X, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),   # sketch local X = world Y
        NXOpen.Vector3d(0.0, 0.0, 1.0),   # sketch local Y = world Z
        NXOpen.Vector3d(1.0, 0.0, 0.0),   # sketch normal  = world X
        "S04_Relief_Slit")
    sk_slit.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    slit_half_w = RELIEF_SLOT_WIDTH / 2.0
    # Overlap 2mm into the hole to avoid zero-thickness wall error
    slit_z_max  = ARC_CZ - LUG_HOLE_DIAMETER / 2.0 + 2.0
    slit_z_min  = PLATE_THICKNESS
    y_center = PLATE_WIDTH / 2.0

    sp1 = NXOpen.Point3d(FRONT_X, y_center - slit_half_w, slit_z_min)
    sp2 = NXOpen.Point3d(FRONT_X, y_center + slit_half_w, slit_z_min)
    sp3 = NXOpen.Point3d(FRONT_X, y_center + slit_half_w, slit_z_max)
    sp4 = NXOpen.Point3d(FRONT_X, y_center - slit_half_w, slit_z_max)

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
    print("[OK] Step 11 complete. Relief slot subtracted.")

    # ==================================================================
    # Step 12: Rectangular Pocket
    # ==================================================================
    print("[...] Step 12: Creating rectangular pocket...")
    feat_s_pkt, sk_pkt = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, 0.0, PLATE_THICKNESS),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        "S05_Rect_Pocket")
    sk_pkt.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    pkt_cx = PLATE_LENGTH / 2.0
    pkt_cy = RECT_POCKET_CENTER_Y
    pkt_hw = RECT_POCKET_WIDTH / 2.0
    pkt_hh = RECT_POCKET_HEIGHT / 2.0

    pp1 = NXOpen.Point3d(pkt_cx - pkt_hh, pkt_cy - pkt_hw, PLATE_THICKNESS)
    pp2 = NXOpen.Point3d(pkt_cx + pkt_hh, pkt_cy - pkt_hw, PLATE_THICKNESS)
    pp3 = NXOpen.Point3d(pkt_cx + pkt_hh, pkt_cy + pkt_hw, PLATE_THICKNESS)
    pp4 = NXOpen.Point3d(pkt_cx - pkt_hh, pkt_cy + pkt_hw, PLATE_THICKNESS)

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
    print("[OK] Step 12 complete. Rectangular pocket subtracted.")

    # ==================================================================
    # Step 13: Left Triangle (near X = 0.23 * PLATE_LENGTH, Y = 0.72 * PLATE_WIDTH)
    # ==================================================================
    print("[...] Step 13: Creating left triangular cutout...")
    feat_s_tri, sk_tri = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, 0.0, PLATE_THICKNESS),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        "S06_Left_Triangle")
    sk_tri.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    # Isosceles triangle.
    # Vertical edge (base) is on the left facing outward: X = TRIANGLE_CENTER_X - TRIANGLE_HEIGHT/2
    # Sharp apex points toward the plate center (to the right, +X direction): X = TRIANGLE_CENTER_X + TRIANGLE_HEIGHT/2
    tri_cx = TRIANGLE_CENTER_X
    tri_cy = TRIANGLE_CENTER_Y
    tri_half_b = TRIANGLE_BASE / 2.0
    tri_half_h = TRIANGLE_HEIGHT / 2.0

    tp1 = NXOpen.Point3d(tri_cx - tri_half_h, tri_cy - tri_half_b, PLATE_THICKNESS)  # base bottom
    tp2 = NXOpen.Point3d(tri_cx - tri_half_h, tri_cy + tri_half_b, PLATE_THICKNESS)  # base top
    tp3 = NXOpen.Point3d(tri_cx + tri_half_h, tri_cy,              PLATE_THICKNESS)  # apex pointing right (+X)

    tl1 = work_part.Curves.CreateLine(tp1, tp2)  # base (vertical)
    tl2 = work_part.Curves.CreateLine(tp2, tp3)  # top leg
    tl3 = work_part.Curves.CreateLine(tp3, tp1)  # bottom leg

    for c in (tl1, tl2, tl3):
        sk_tri.AddGeometry(c, infer)
    sk_tri.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    feat_tri, _ = _extrude_curves(
        work_part, [tl1, tl2, tl3],
        NXOpen.Vector3d(0.0, 0.0, -1.0), "0.0", str(PLATE_THICKNESS + 2.0),
        "F06_Left_Triangle",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
        base_body)
    print("[OK] Step 13 complete. Left triangle subtracted.")

    # ==================================================================
    # Step 14: Mirror Triangle (about vertical center plane X = 80.0)
    # ==================================================================
    print("[...] Step 14: Mirroring triangle about vertical center plane X = 80.0...")
    _, datum_plane_center = _create_datum_plane_at_x(work_part, PLATE_LENGTH / 2.0)
    _mirror_feature(work_part, feat_tri, datum_plane_center)
    print("[OK] Step 14 complete. Mirrored triangle created.")

    # ==================================================================
    # Step 15: Remaining Edge Blends
    # ==================================================================
    print("[...] Step 15: Applying remaining edge blends...")
    lug_verticals = []
    lug_tops = []
    lug_junctions = []
    pocket_triangle_corners = []

    # Filter and sort edges for precision blending
    for edge in base_body.GetEdges():
        try:
            v1, v2 = edge.GetVertices()
            p1 = v1.GetCoordinates()
            p2 = v2.GetCoordinates()
            
            # Linear edges (type code or checking if start-end matches midpoint)
            is_linear = (abs(p1.X - p2.X) > 0.05 or abs(p1.Y - p2.Y) > 0.05 or abs(p1.Z - p2.Z) > 0.05) # simple check
            
            # Check if edge is vertical (parallel to Z-axis)
            if abs(p1.X - p2.X) < 0.05 and abs(p1.Y - p2.Y) < 0.05 and abs(p1.Z - p2.Z) > 0.1:
                mid_z = (p1.Z + p2.Z) / 2.0
                if mid_z > PLATE_THICKNESS:
                    # Lug outside vertical edges
                    lug_verticals.append(edge)
                else:
                    # Pocket or triangle vertical corners
                    # Exclude base plate corner edges (which are already blended)
                    if abs(p1.X) > 2.0 and abs(p1.X - PLATE_LENGTH) > 2.0 and \
                       abs(p1.Y) > 2.0 and abs(p1.Y - PLATE_WIDTH) > 2.0:
                        pocket_triangle_corners.append(edge)
            
            # Check if edge is horizontal at the lug-to-base junction (parallel to Y, at Z=PLATE_THICKNESS)
            elif abs(p1.Z - PLATE_THICKNESS) < 0.05 and abs(p2.Z - PLATE_THICKNESS) < 0.05:
                if abs(p1.X - p2.X) < 0.05 and abs(p1.Y - p2.Y) > 0.1:
                    # Lug-to-base junction
                    lug_junctions.append(edge)
                    
            # Check if edge is a curved top cap (maximum Z is ARC_CZ + HALF_LW = PLATE_THICKNESS + LUG_HEIGHT)
            else:
                # Semicircular top curves of the lugs
                max_z = max(p1.Z, p2.Z)
                if abs(max_z - (PLATE_THICKNESS + LUG_HEIGHT)) < 0.5:
                    lug_tops.append(edge)
        except Exception:
            pass

    # Apply general fillets
    if lug_verticals:
        _add_edge_blend(work_part, lug_verticals, "GENERAL_FILLET_RADIUS", "lug_verticals")
    if lug_tops:
        _add_edge_blend(work_part, lug_tops, "GENERAL_FILLET_RADIUS", "lug_tops")
    if lug_junctions:
        _add_edge_blend(work_part, lug_junctions, "GENERAL_FILLET_RADIUS", "lug_junctions")
    if pocket_triangle_corners:
        _add_edge_blend(work_part, pocket_triangle_corners, "GENERAL_FILLET_RADIUS", "pocket_triangle_corners")
    print("[OK] Step 15 complete.")

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
    # Step 16: Save Part
    # ==================================================================
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("[OK] Step 16 complete. Part saved -> {}".format(output_path))

    # ==================================================================
    # Step 17: Export STEP
    # ==================================================================
    step_path = output_path.with_suffix(".stp")
    print("[...] Step 17: Exporting STEP...")
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
    # Step 18: Export STL
    # ==================================================================
    stl_path = output_path.with_suffix(".stl")
    print("[...] Step 18: Exporting STL...")
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
    print("[DONE] Mounting plate V5 complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
