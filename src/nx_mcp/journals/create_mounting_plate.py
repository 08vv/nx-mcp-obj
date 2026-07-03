"""
create_mounting_plate.py
========================
NX Journal that creates a parametric mounting plate with:
  - Base rectangular plate (sketched and extruded)
  - Four symmetric corner holes
  - Upper semi-cylindrical boss (sketched and extruded, united)
  - Mirror feature to create lower boss
  - Center rectangular slot (sketched and extruded, subtracted)
  - Small circular through hole (midway between upper boss and slot)
  - Left triangular cut-out (sketched and extruded, subtracted)
  - Mirror feature to create right triangle
  - Edge blends on outer curved edges of the bosses
  - Save, STEP, and STL exports.

All dimensions are stored as named NX Expressions.
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
PLATE_LENGTH         = 120.0
PLATE_WIDTH          = 80.0
PLATE_THICKNESS      = 10.0
CORNER_HOLE_DIAMETER = 8.0
CORNER_HOLE_OFFSET_X = 12.0
CORNER_HOLE_OFFSET_Y = 12.0
BOSS_RADIUS          = 12.0
BOSS_WIDTH           = 24.0
BOSS_HEIGHT          = 15.0
BOSS_CENTER_OFFSET   = 19.0
CENTER_SLOT_WIDTH    = 12.0
CENTER_SLOT_HEIGHT   = 20.0
CENTER_HOLE_DIAMETER = 6.0
TRIANGLE_BASE        = 16.0
TRIANGLE_HEIGHT      = 12.0
EDGE_BLEND_RADIUS    = 2.0


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
def _output_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "mounting_plate.prt"


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
# Helpers for Sketch and Extrude
# ---------------------------------------------------------------------------
def _dim_geom(curve, assoc_type=None):
    geom = NXOpen.Sketch.DimensionGeometry()
    geom.Geometry = curve
    if assoc_type is None:
        assoc_type = NXOpen.SketchAssocType.NotSet
    geom.AssocType = assoc_type
    return geom


def _con_geom(curve, point_type=None):
    geom = NXOpen.Sketch.ConstraintGeometry()
    geom.Geometry = curve
    if point_type is None:
        point_type = NXOpen.SketchConstraintPointType.NotSet
    geom.PointType = point_type
    return geom


def _apply_dim(sketch, dim_type, geom1, geom2, origin, expr):
    if geom2 is None:
        geom2 = NXOpen.Sketch.DimensionGeometry()
    try:
        sketch.CreateDimension(
            dim_type, geom1, geom2,
            origin, expr,
            NXOpen.SketchDimensionOption.CreateAsDriving)
    except Exception as exc:
        print("[WARN] Dimension {}: {}".format(dim_type, exc))


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
                    setattr(builder, attr, plane_obj)
                    break
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


def _extrude_curves(work_part, curves, dir_vec, start_expr, end_expr, feature_name, boolean_type=None, target_body=None):
    if boolean_type is None:
        try:
            boolean_type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        except AttributeError:
            boolean_type = "Create"

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
            NXOpen.Point3d(0.0, 0.0, 0.0),
            dir_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Direction = nx_dir
        builder.Limits.StartExtend.Value.RightHandSide = start_expr
        builder.Limits.EndExtend.Value.RightHandSide = end_expr
        
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
def _fixed_datum_plane_type(plane):
    ref = str(plane or "XY").strip().upper()
    fixed_types = {
        "XY": NXOpen.Features.DatumPlaneBuilder.FixedType.Xy,
        "XZ": NXOpen.Features.DatumPlaneBuilder.FixedType.Zx,
        "ZX": NXOpen.Features.DatumPlaneBuilder.FixedType.Zx,
        "YZ": NXOpen.Features.DatumPlaneBuilder.FixedType.Yz,
    }
    return fixed_types[ref]


def _mirror_feature(work_part, source_feature, plane_name):
    # 1. Create datum plane
    datum_builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        datum_builder.SetFixedDatumPlane(_fixed_datum_plane_type(plane_name))
        datum_feat = datum_builder.CommitFeature()
        datum_plane = datum_feat.DatumPlane
    finally:
        datum_builder.Destroy()

    # 2. Create Mirror Feature
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
                datum_plane,
                work_part.ModelingViews.WorkView,
                NXOpen.Point3d(0.0, 0.0, 0.0),
            )
        elif hasattr(builder, "MirrorPlane"):
            builder.MirrorPlane = datum_plane
            
        feat = builder.CommitFeature()
        return feat
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Edge Blend (fillet) helper
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


# ---------------------------------------------------------------------------
# Helper: update result files
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
    print("  CREATING PARAMETRIC MOUNTING PLATE")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. NX Expressions
    # ------------------------------------------------------------------
    expressions = [
        ("PLATE_LENGTH",         PLATE_LENGTH),
        ("PLATE_WIDTH",          PLATE_WIDTH),
        ("PLATE_THICKNESS",      PLATE_THICKNESS),
        ("CORNER_HOLE_DIAMETER", CORNER_HOLE_DIAMETER),
        ("CORNER_HOLE_OFFSET_X", CORNER_HOLE_OFFSET_X),
        ("CORNER_HOLE_OFFSET_Y", CORNER_HOLE_OFFSET_Y),
        ("BOSS_RADIUS",          BOSS_RADIUS),
        ("BOSS_WIDTH",           BOSS_WIDTH),
        ("BOSS_HEIGHT",          BOSS_HEIGHT),
        ("BOSS_CENTER_OFFSET",   BOSS_CENTER_OFFSET),
        ("CENTER_SLOT_WIDTH",    CENTER_SLOT_WIDTH),
        ("CENTER_SLOT_HEIGHT",   CENTER_SLOT_HEIGHT),
        ("CENTER_HOLE_DIAMETER", CENTER_HOLE_DIAMETER),
        ("TRIANGLE_BASE",        TRIANGLE_BASE),
        ("TRIANGLE_HEIGHT",      TRIANGLE_HEIGHT),
        ("EDGE_BLEND_RADIUS",    EDGE_BLEND_RADIUS),

        # Derived helper expressions
        ("HALF_LENGTH",          "PLATE_LENGTH / 2.0"),
        ("HALF_WIDTH",           "PLATE_WIDTH / 2.0"),
        ("HOLE_DEPTH",           "PLATE_THICKNESS + 2.0"),
        ("BOSS_SLOT_SPACING",    "BOSS_CENTER_OFFSET - (CENTER_SLOT_HEIGHT / 2.0)"),
        ("TRIANGLE_X_BASE",      "- (CENTER_SLOT_WIDTH / 2.0) - BOSS_SLOT_SPACING"),
        ("CENTER_HOLE_Y",        "(BOSS_CENTER_OFFSET + (CENTER_SLOT_HEIGHT / 2.0)) / 2.0"),
    ]

    for name, value in expressions:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
    print("[OK] Expressions created.")

    # ------------------------------------------------------------------
    # 2. Base Plate Sketch and Extrude (Steps 1 & 2)
    # ------------------------------------------------------------------
    print("[...] Steps 1 & 2: Sketching and extruding base plate...")
    xy_plane = work_part.Planes.CreatePlane(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling)

    feat_s1, sk1 = _create_sketch_on_plane(work_part, xy_plane, "S1_Base_Plate")
    sk1.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    half_l = PLATE_LENGTH / 2.0
    half_w = PLATE_WIDTH / 2.0

    p1 = NXOpen.Point3d(-half_l, -half_w, 0.0)
    p2 = NXOpen.Point3d(half_l, -half_w, 0.0)
    p3 = NXOpen.Point3d(half_l, half_w, 0.0)
    p4 = NXOpen.Point3d(-half_l, half_w, 0.0)

    l1 = work_part.Curves.CreateLine(p1, p2)
    l2 = work_part.Curves.CreateLine(p2, p3)
    l3 = work_part.Curves.CreateLine(p3, p4)
    l4 = work_part.Curves.CreateLine(p4, p1)

    infer = NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints
    for curve in (l1, l2, l3, l4):
        sk1.AddGeometry(curve, infer)

    # Constraints
    sk1.CreateHorizontalConstraint(_con_geom(l1))
    sk1.CreateVerticalConstraint(_con_geom(l2))
    sk1.CreateHorizontalConstraint(_con_geom(l3))
    sk1.CreateVerticalConstraint(_con_geom(l4))

    # Center origin
    pt_origin = work_part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    sk1.AddGeometry(pt_origin, infer)
    sk1.CreateFixedConstraint(_con_geom(pt_origin))

    CT = NXOpen.SketchConstraintType
    _apply_dim(sk1, CT.HorizontalDim,
               _dim_geom(pt_origin),
               _dim_geom(l2, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(half_l / 2.0, -half_w - 5.0, 0.0),
               work_part.Expressions.FindObject("HALF_LENGTH"))

    _apply_dim(sk1, CT.VerticalDim,
               _dim_geom(pt_origin),
               _dim_geom(l3, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(-half_l - 5.0, half_w / 2.0, 0.0),
               work_part.Expressions.FindObject("HALF_WIDTH"))

    sk1.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    feat_ext1, base_body = _extrude_curves(
        work_part, [l1, l2, l3, l4],
        NXOpen.Vector3d(0.0, 0.0, 1.0), "0.0", "PLATE_THICKNESS",
        "F1_Base_Plate",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    )
    print("[OK] Base plate extruded.")

    # ------------------------------------------------------------------
    # 3. Corner Holes (Step 3)
    # ------------------------------------------------------------------
    print("[...] Step 3: Creating four symmetric corner holes...")
    for idx, x_formula, y_formula, cx, cy in [
        ("1", "-HALF_LENGTH + CORNER_HOLE_OFFSET_X", "-HALF_WIDTH + CORNER_HOLE_OFFSET_Y", -half_l + CORNER_HOLE_OFFSET_X, -half_w + CORNER_HOLE_OFFSET_Y),
        ("2", "HALF_LENGTH - CORNER_HOLE_OFFSET_X",  "-HALF_WIDTH + CORNER_HOLE_OFFSET_Y",  half_l - CORNER_HOLE_OFFSET_X, -half_w + CORNER_HOLE_OFFSET_Y),
        ("3", "-HALF_LENGTH + CORNER_HOLE_OFFSET_X", "HALF_WIDTH - CORNER_HOLE_OFFSET_Y",  -half_l + CORNER_HOLE_OFFSET_X,  half_w - CORNER_HOLE_OFFSET_Y),
        ("4", "HALF_LENGTH - CORNER_HOLE_OFFSET_X",  "HALF_WIDTH - CORNER_HOLE_OFFSET_Y",   half_l - CORNER_HOLE_OFFSET_X,  half_w - CORNER_HOLE_OFFSET_Y),
    ]:
        work_part.Expressions.CreateExpression("Number", "HOLE{}_X = {}".format(idx, x_formula))
        work_part.Expressions.CreateExpression("Number", "HOLE{}_Y = {}".format(idx, y_formula))

        # Extrude cylinder cut
        cyl_builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        try:
            origin = NXOpen.Point3d(cx, cy, -1.0)
            direction = work_part.Directions.CreateDirection(
                origin, NXOpen.Vector3d(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)

            cyl_builder.Diameter.RightHandSide = "CORNER_HOLE_DIAMETER"
            cyl_builder.Height.RightHandSide   = "HOLE_DEPTH"
            cyl_builder.Axis.Point.SetCoordinates(origin)
            cyl_builder.Axis.Direction = direction
            cyl_feat = cyl_builder.Commit()
            tool_body = cyl_feat.GetBodies()[0]
        finally:
            cyl_builder.Destroy()

        # Boolean subtract
        subtract_builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
        try:
            subtract_builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
            for attr in ("Target", "TargetBody"):
                if hasattr(subtract_builder, attr):
                    setattr(subtract_builder, attr, base_body); break
            for attr in ("Tool", "ToolBody"):
                if hasattr(subtract_builder, attr):
                    setattr(subtract_builder, attr, tool_body); break
            subtract_builder.CommitFeature()
        finally:
            subtract_builder.Destroy()

    print("[OK] Corner holes completed.")

    # ------------------------------------------------------------------
    # 4. Upper semi-cylindrical boss (Steps 4 & 5)
    # ------------------------------------------------------------------
    print("[...] Steps 4 & 5: Sketching and extruding upper boss...")
    feat_s2, sk2 = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, 0.0, PLATE_THICKNESS),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        "S2_Upper_Boss"
    )
    sk2.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    # Upper boss center is at X=0, Y=BOSS_CENTER_OFFSET
    # Flat horizontal line from -BOSS_WIDTH/2 to +BOSS_WIDTH/2
    bx_half = BOSS_WIDTH / 2.0
    
    bp_left  = NXOpen.Point3d(-bx_half, BOSS_CENTER_OFFSET, PLATE_THICKNESS)
    bp_right = NXOpen.Point3d(bx_half, BOSS_CENTER_OFFSET, PLATE_THICKNESS)
    b_center = NXOpen.Point3d(0.0, BOSS_CENTER_OFFSET, PLATE_THICKNESS)

    bline = work_part.Curves.CreateLine(bp_left, bp_right)
    barc  = work_part.Curves.CreateArc(
        b_center, NXOpen.Vector3d(1.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0),
        BOSS_RADIUS, 0.0, math.pi
    )

    for curve in (bline, barc):
        sk2.AddGeometry(curve, infer)

    sk2.CreateHorizontalConstraint(_con_geom(bline))
    sk2.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    feat_boss, base_body = _extrude_curves(
        work_part, [bline, barc],
        NXOpen.Vector3d(0.0, 0.0, 1.0), "0.0", "BOSS_HEIGHT",
        "F2_Upper_Boss",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        base_body
    )
    print("[OK] Upper boss created.")

    # ------------------------------------------------------------------
    # 5. Mirror upper boss to create lower boss (Step 6)
    # ------------------------------------------------------------------
    print("[...] Step 6: Mirroring upper boss to create lower boss...")
    _mirror_feature(work_part, feat_boss, "XZ")
    print("[OK] Lower boss mirrored.")

    # ------------------------------------------------------------------
    # 6. Center rectangular slot (Steps 7 & 8)
    # ------------------------------------------------------------------
    print("[...] Steps 7 & 8: Sketching and extruding center rectangular slot...")
    feat_s3, sk3 = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, 0.0, PLATE_THICKNESS),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        "S3_Center_Slot"
    )
    sk3.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    sw_half = CENTER_SLOT_WIDTH / 2.0
    sh_half = CENTER_SLOT_HEIGHT / 2.0

    sp1 = NXOpen.Point3d(-sw_half, -sh_half, PLATE_THICKNESS)
    sp2 = NXOpen.Point3d(sw_half, -sh_half, PLATE_THICKNESS)
    sp3 = NXOpen.Point3d(sw_half, sh_half, PLATE_THICKNESS)
    sp4 = NXOpen.Point3d(-sw_half, sh_half, PLATE_THICKNESS)

    sl1 = work_part.Curves.CreateLine(sp1, sp2)
    sl2 = work_part.Curves.CreateLine(sp2, sp3)
    sl3 = work_part.Curves.CreateLine(sp3, sp4)
    sl4 = work_part.Curves.CreateLine(sp4, sp1)

    for curve in (sl1, sl2, sl3, sl4):
        sk3.AddGeometry(curve, infer)

    sk3.CreateHorizontalConstraint(_con_geom(sl1))
    sk3.CreateVerticalConstraint(_con_geom(sl2))
    sk3.CreateHorizontalConstraint(_con_geom(sl3))
    sk3.CreateVerticalConstraint(_con_geom(sl4))

    sk3.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # Extrude Remove
    feat_slot, base_body = _extrude_curves(
        work_part, [sl1, sl2, sl3, sl4],
        NXOpen.Vector3d(0.0, 0.0, -1.0), "0.0", "PLATE_THICKNESS",
        "F3_Center_Slot",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
        base_body
    )
    print("[OK] Center slot subtracted.")

    # ------------------------------------------------------------------
    # 7. Small center through-hole (Step 9)
    # ------------------------------------------------------------------
    print("[...] Step 9: Creating small center through-hole...")
    ch_y = (BOSS_CENTER_OFFSET + sh_half) / 2.0
    ch_builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        origin = NXOpen.Point3d(0.0, ch_y, -1.0)
        direction = work_part.Directions.CreateDirection(
            origin, NXOpen.Vector3d(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)

        ch_builder.Diameter.RightHandSide = "CENTER_HOLE_DIAMETER"
        ch_builder.Height.RightHandSide   = "HOLE_DEPTH"
        ch_builder.Axis.Point.SetCoordinates(origin)
        ch_builder.Axis.Direction = direction
        ch_feat = ch_builder.Commit()
        ch_body = ch_feat.GetBodies()[0]
    finally:
        ch_builder.Destroy()

    # Subtract
    _perform_subtract(work_part, base_body, ch_body)

    print("[OK] Small center hole subtracted.")

    # ------------------------------------------------------------------
    # 8. Left triangular cut-out (Steps 10 & 11)
    # ------------------------------------------------------------------
    print("[...] Steps 10 & 11: Sketching and extruding left triangular cut-out...")
    feat_s4, sk4 = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, 0.0, PLATE_THICKNESS),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        "S4_Left_Triangle"
    )
    sk4.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    # Left triangle vertices:
    # Vertical edge at X = TRIANGLE_X_BASE
    # Vertex 1: (TRIANGLE_X_BASE, -TRIANGLE_BASE / 2)
    # Vertex 2: (TRIANGLE_X_BASE, TRIANGLE_BASE / 2)
    # Vertex 3 (points outward): (TRIANGLE_X_BASE - TRIANGLE_HEIGHT, 0)
    tx_base = -sw_half - (BOSS_CENTER_OFFSET - sh_half)
    
    tp1 = NXOpen.Point3d(tx_base, -TRIANGLE_BASE / 2.0, PLATE_THICKNESS)
    tp2 = NXOpen.Point3d(tx_base, TRIANGLE_BASE / 2.0, PLATE_THICKNESS)
    tp3 = NXOpen.Point3d(tx_base - TRIANGLE_HEIGHT, 0.0, PLATE_THICKNESS)

    tl1 = work_part.Curves.CreateLine(tp1, tp2)
    tl2 = work_part.Curves.CreateLine(tp2, tp3)
    tl3 = work_part.Curves.CreateLine(tp3, tp1)

    for curve in (tl1, tl2, tl3):
        sk4.AddGeometry(curve, infer)

    sk4.CreateVerticalConstraint(_con_geom(tl1))
    sk4.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # Extrude Remove
    feat_triangle, base_body = _extrude_curves(
        work_part, [tl1, tl2, tl3],
        NXOpen.Vector3d(0.0, 0.0, -1.0), "0.0", "PLATE_THICKNESS",
        "F4_Left_Triangle",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
        base_body
    )
    print("[OK] Left triangle subtracted.")

    # ------------------------------------------------------------------
    # 9. Mirror left triangle to create right triangle (Step 12)
    # ------------------------------------------------------------------
    print("[...] Step 12: Mirroring left triangle to create right triangle...")
    _mirror_feature(work_part, feat_triangle, "YZ")
    print("[OK] Right triangle mirrored.")

    # ------------------------------------------------------------------
    # 10. Edge Blend (Step 13)
    #     Apply to outer curved edges of the semi-cylindrical bosses
    #     These lie at Z = PLATE_THICKNESS + BOSS_HEIGHT
    # ------------------------------------------------------------------
    print("[...] Step 13: Applying edge blends to boss outer curved edges...")
    top_z = PLATE_THICKNESS + BOSS_HEIGHT
    uf_session = NXOpen.UF.UFSession.GetUFSession()

    boss_edges = []
    print("[DEBUG] Searching for boss edges at top_z = {}".format(top_z))
    for idx, edge in enumerate(base_body.GetEdges()):
        try:
            v1, v2 = edge.GetVertices()
            p1 = v1.GetCoordinates()
            p2 = v2.GetCoordinates()
            edge_type = uf_session.Modl.AskEdgeType(edge.Tag)
            if idx < 30: # Limit print output
                print("[DEBUG] Edge {}: type={}, p1.Z={:.3f}, p2.Z={:.3f}".format(idx, edge_type, p1.Z, p2.Z))
            if abs(p1.Z - top_z) < 0.05 and abs(p2.Z - top_z) < 0.05:
                if edge_type != 3:  # Not linear
                    boss_edges.append(edge)
        except Exception as e:
            if idx < 30:
                print("[DEBUG] Edge {} failed: {}".format(idx, e))

    if boss_edges:
        print("[...] Blending {} circular boss edges...".format(len(boss_edges)))
        for edge in boss_edges:
            try:
                _blend_single_edge(work_part, edge, "EDGE_BLEND_RADIUS")
            except Exception as exc:
                print("[WARN] Blend failed on edge: {}".format(exc))
        print("[OK] Blends completed.")
    else:
        print("[WARN] No curved boss edges found at Z = {}.".format(top_z))

    # ------------------------------------------------------------------
    # 11. View ISO
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
    # 12. Save part (Step 14)
    # ------------------------------------------------------------------
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("[OK] Part saved -> {}".format(output_path))

    # ------------------------------------------------------------------
    # 13. Export STEP (Step 15)
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
    # 14. Export STL (Step 16)
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
    # 15. Update watcher files
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
            subprocess.Popen([str(ugs_router), "-ug", "-use_file_dir", str(output_path.resolve())])
            print("[OK] NX GUI launched -> opening {}".format(output_path.name))
        else:
            print("[WARN] ugs_router.exe not found -- open part manually in NX.")
    except Exception as exc:
        print("[WARN] Could not auto-open in NX GUI: {}".format(exc))

    print("=" * 60)
    print("[DONE] Mounting plate complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
