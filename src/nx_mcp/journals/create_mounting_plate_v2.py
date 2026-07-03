"""
create_mounting_plate_v2.py
===========================
NX Journal that creates a parametric mounting plate with:
  - Base rectangular plate (sketched and extruded)
  - Perimeter edge blend
  - Four corner holes
  - Upright clevis lug with rounded top (sketched and extruded)
  - Mirror feature to create the second lug
  - Lug through hole
  - Mirror feature to create the second lug hole
  - Vertical relief slot on the first lug
  - Centered rectangular pocket behind the lugs
  - Left triangular cut-out near front-left
  - Mirror feature to create the right triangle
  - Edge blends on lug edges, transitions, pocket, and triangles
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
PLATE_LENGTH         = 150.0
PLATE_WIDTH          = 100.0
PLATE_THICKNESS      = 12.0
CORNER_HOLE_DIAMETER = 8.0
CORNER_HOLE_OFFSET   = 12.0
LUG_WIDTH            = 30.0
LUG_THICKNESS        = 8.0
LUG_HEIGHT           = 45.0
LUG_SPACING          = 20.0
LUG_HOLE_DIAMETER    = 15.0
RELIEF_SLOT_WIDTH    = 3.0
RELIEF_SLOT_LENGTH   = 20.0
CENTER_POCKET_LENGTH = 40.0
CENTER_POCKET_WIDTH  = 12.0
TRIANGLE_BASE        = 20.0
TRIANGLE_HEIGHT      = 15.0
OUTER_FILLET_RADIUS  = 8.0
LUG_FILLET_RADIUS    = 2.0


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
def _output_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "mounting_plate_v2.prt"


# ---------------------------------------------------------------------------
# Helpers for Boolean Operations
# ---------------------------------------------------------------------------
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
# Edge Blend (fillet) helpers
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
    applied = failed = 0
    for edge in edges:
        try:
            _blend_single_edge(work_part, edge, radius_expr)
            applied += 1
        except Exception:
            failed += 1
    print("[OK] Blend: {} applied, {} skipped.".format(applied, failed))


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
        print("[OK] Result watcher files updated.")
    except Exception as exc:
        print("[WARN] Could not update result files: {}".format(exc))


# ---------------------------------------------------------------------------
# Main Feature Sequence
# ---------------------------------------------------------------------------
def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            output_path.unlink()
            print("[OK] Removed existing part file: {}".format(output_path))
        except Exception as exc:
            print("[WARN] Could not remove existing file: {}".format(exc))

    session   = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    print("=" * 60)
    print("  CREATING PARAMETRIC MOUNTING PLATE WITH CLEVIS LUGS (V2)")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. NX Expressions Setup
    # ------------------------------------------------------------------
    expressions = [
        ("PLATE_LENGTH",         PLATE_LENGTH),
        ("PLATE_WIDTH",          PLATE_WIDTH),
        ("PLATE_THICKNESS",      PLATE_THICKNESS),
        ("CORNER_HOLE_DIAMETER", CORNER_HOLE_DIAMETER),
        ("CORNER_HOLE_OFFSET",   CORNER_HOLE_OFFSET),
        ("LUG_WIDTH",            LUG_WIDTH),
        ("LUG_THICKNESS",        LUG_THICKNESS),
        ("LUG_HEIGHT",           LUG_HEIGHT),
        ("LUG_SPACING",          LUG_SPACING),
        ("LUG_HOLE_DIAMETER",    LUG_HOLE_DIAMETER),
        ("RELIEF_SLOT_WIDTH",    RELIEF_SLOT_WIDTH),
        ("RELIEF_SLOT_LENGTH",   RELIEF_SLOT_LENGTH),
        ("CENTER_POCKET_LENGTH", CENTER_POCKET_LENGTH),
        ("CENTER_POCKET_WIDTH",  CENTER_POCKET_WIDTH),
        ("TRIANGLE_BASE",        TRIANGLE_BASE),
        ("TRIANGLE_HEIGHT",      TRIANGLE_HEIGHT),
        ("OUTER_FILLET_RADIUS",  OUTER_FILLET_RADIUS),
        ("LUG_FILLET_RADIUS",    LUG_FILLET_RADIUS),

        # Derived expressions
        ("HALF_LENGTH",          "PLATE_LENGTH / 2.0"),
        ("HALF_WIDTH",           "PLATE_WIDTH / 2.0"),
        ("HOLE_DEPTH",           "PLATE_THICKNESS + 2.0"),
        ("LUG_Y_START",          "LUG_SPACING / 2.0"),
        ("LUG_HOLE_Z",           "PLATE_THICKNESS + LUG_HEIGHT - LUG_WIDTH / 2.0"),
        ("LUG_HOLE_Y",           "LUG_Y_START + LUG_THICKNESS / 2.0"),
        ("LUG_HOLE_DEPTH",       "LUG_THICKNESS + 2.0"),
        ("RELIEF_SLOT_Z_MAX",    "LUG_HOLE_Z - LUG_HOLE_DIAMETER / 2.0"),
        ("RELIEF_SLOT_DEPTH",    "LUG_THICKNESS + 2.0"),
        ("POCKET_X_MIN",         "-LUG_WIDTH / 2.0 - 2.0 - CENTER_POCKET_LENGTH"),
        ("POCKET_X_MAX",         "-LUG_WIDTH / 2.0 - 2.0"),
        ("TRIANGLE_X_BASE",      "PLATE_LENGTH / 2.0 - 20.0"),
        ("TRIANGLE_Y_CENTER",    "PLATE_WIDTH / 2.0 - 20.0"),
    ]

    for name, value in expressions:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
    print("[OK] Expressions created.")

    # ------------------------------------------------------------------
    # Step 1 & 2: Sketch and Extrude Base Plate
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
    # Step 3: Edge Blend (outer plate perimeter)
    # ------------------------------------------------------------------
    print("[...] Step 3: Blending base plate perimeter vertical edges...")
    base_verticals = []
    for edge in base_body.GetEdges():
        try:
            v1, v2 = edge.GetVertices()
            p1 = v1.GetCoordinates()
            p2 = v2.GetCoordinates()
            # Vertical edges are parallel to Z-axis
            if abs(p1.Z - p2.Z) > 0.1:
                if abs(p1.X - p2.X) < 0.1 and abs(p1.Y - p2.Y) < 0.1:
                    # Outer perimeter corners (X is near ±half_l, Y is near ±half_w)
                    if abs(p1.X) > (half_l - 2.0) and abs(p1.Y) > (half_w - 2.0):
                        base_verticals.append(edge)
        except Exception:
            pass

    if base_verticals:
        _add_edge_blend(work_part, base_verticals, "OUTER_FILLET_RADIUS")
    else:
        print("[WARN] No base plate corner vertical edges found.")

    # ------------------------------------------------------------------
    # Step 4: Hole (four corner holes)
    # ------------------------------------------------------------------
    print("[...] Step 4: Creating four symmetric corner holes...")
    for idx, x_formula, y_formula in [
        ("1", "-HALF_LENGTH + CORNER_HOLE_OFFSET", "-HALF_WIDTH + CORNER_HOLE_OFFSET"),
        ("2", "HALF_LENGTH - CORNER_HOLE_OFFSET",  "-HALF_WIDTH + CORNER_HOLE_OFFSET"),
        ("3", "-HALF_LENGTH + CORNER_HOLE_OFFSET", "HALF_WIDTH - CORNER_HOLE_OFFSET"),
        ("4", "HALF_LENGTH - CORNER_HOLE_OFFSET",  "HALF_WIDTH - CORNER_HOLE_OFFSET"),
    ]:
        work_part.Expressions.CreateExpression("Number", "HOLE{}_X = {}".format(idx, x_formula))
        work_part.Expressions.CreateExpression("Number", "HOLE{}_Y = {}".format(idx, y_formula))

        hx = work_part.Expressions.FindObject("HOLE{}_X".format(idx)).Value
        hy = work_part.Expressions.FindObject("HOLE{}_Y".format(idx)).Value

        cyl_builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        try:
            origin = NXOpen.Point3d(hx, hy, -1.0)
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

        _perform_subtract(work_part, base_body, tool_body)
    print("[OK] Corner holes completed.")

    # ------------------------------------------------------------------
    # Step 5 & 6: Sketch and Extrude first lug
    # ------------------------------------------------------------------
    print("[...] Steps 5 & 6: Sketching and extruding first lug...")
    # Plane at Y = LUG_SPACING / 2.0 (inner face plane of first lug)
    lug_y = LUG_SPACING / 2.0
    feat_s2, sk2 = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, lug_y, 0.0),
        NXOpen.Vector3d(1.0, 0.0, 0.0),  # local X
        NXOpen.Vector3d(0.0, 0.0, 1.0),  # local Y
        NXOpen.Vector3d(0.0, -1.0, 0.0), # local Z (normal)
        "S2_First_Lug"
    )
    sk2.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    # Rounded top profile coordinates
    # Center of arc: (0, lug_y, PLATE_THICKNESS + LUG_HEIGHT - LUG_WIDTH/2)
    arc_cz = PLATE_THICKNESS + LUG_HEIGHT - LUG_WIDTH / 2.0
    half_lw = LUG_WIDTH / 2.0

    lp1 = NXOpen.Point3d(-half_lw, lug_y, PLATE_THICKNESS)
    lp2 = NXOpen.Point3d(half_lw, lug_y, PLATE_THICKNESS)
    lp3 = NXOpen.Point3d(half_lw, lug_y, arc_cz)
    lp4 = NXOpen.Point3d(-half_lw, lug_y, arc_cz)
    lp_center = NXOpen.Point3d(0.0, lug_y, arc_cz)

    l_bottom = work_part.Curves.CreateLine(lp1, lp2)
    l_right  = work_part.Curves.CreateLine(lp2, lp3)
    l_left   = work_part.Curves.CreateLine(lp4, lp1)
    
    # Semicircular arc on XZ plane
    l_arc = work_part.Curves.CreateArc(
        lp_center, NXOpen.Vector3d(1.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0),
        half_lw, 0.0, math.pi
    )

    for curve in (l_bottom, l_right, l_arc, l_left):
        sk2.AddGeometry(curve, infer)

    sk2.CreateHorizontalConstraint(_con_geom(l_bottom))
    sk2.CreateVerticalConstraint(_con_geom(l_right))
    sk2.CreateVerticalConstraint(_con_geom(l_left))
    sk2.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # Extrude along Y-axis (+Y) by LUG_THICKNESS
    feat_lug, base_body = _extrude_curves(
        work_part, [l_bottom, l_right, l_arc, l_left],
        NXOpen.Vector3d(0.0, 1.0, 0.0), "0.0", "LUG_THICKNESS",
        "F2_First_Lug",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        base_body
    )
    print("[OK] First lug extruded and united.")

    # ------------------------------------------------------------------
    # Step 7: Mirror Feature (second lug)
    # ------------------------------------------------------------------
    print("[...] Step 7: Mirroring first lug about XZ plane to create second lug...")
    _mirror_feature(work_part, feat_lug, "XZ")
    print("[OK] Second lug mirrored.")

    # ------------------------------------------------------------------
    # Step 8: Hole (first lug)
    # ------------------------------------------------------------------
    print("[...] Step 8: Creating through-hole in first lug...")
    hole_y = lug_y - 1.0  # start slightly outside the lug for a clean cut
    
    cyl_builder2 = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        origin = NXOpen.Point3d(0.0, hole_y, arc_cz)
        direction = work_part.Directions.CreateDirection(
            origin, NXOpen.Vector3d(0.0, 1.0, 0.0), NXOpen.SmartObject.UpdateOption.WithinModeling)

        cyl_builder2.Diameter.RightHandSide = "LUG_HOLE_DIAMETER"
        cyl_builder2.Height.RightHandSide   = "LUG_HOLE_DEPTH"
        cyl_builder2.Axis.Point.SetCoordinates(origin)
        cyl_builder2.Axis.Direction = direction
        cyl_feat2 = cyl_builder2.Commit()
        tool_body2 = cyl_feat2.GetBodies()[0]
    finally:
        cyl_builder2.Destroy()

    _perform_subtract(work_part, base_body, tool_body2)
    print("[OK] First lug hole completed.")

    # ------------------------------------------------------------------
    # Step 9: Mirror Feature (second lug hole)
    # ------------------------------------------------------------------
    print("[...] Step 9: Mirroring first hole about XZ plane to create second hole...")
    mirrored_cyl_feat = _mirror_feature(work_part, cyl_feat2, "XZ")
    mirrored_cyl_body = mirrored_cyl_feat.GetBodies()[0]
    _perform_subtract(work_part, base_body, mirrored_cyl_body)
    print("[OK] Second lug hole completed.")

    # ------------------------------------------------------------------
    # Step 10 & 11: Sketch and Extrude Remove vertical relief slot
    # ------------------------------------------------------------------
    print("[...] Steps 10 & 11: Sketching and extruding vertical relief slot...")
    feat_s3, sk3 = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, lug_y, 0.0),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        NXOpen.Vector3d(0.0, -1.0, 0.0),
        "S3_Relief_Slot"
    )
    sk3.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    slot_w_half = RELIEF_SLOT_WIDTH / 2.0
    # Extend the slot slightly into the circular hole by 2.0mm to avoid touch condition / zero thickness wall error
    slot_z_max  = arc_cz - LUG_HOLE_DIAMETER / 2.0 + 2.0

    sp1 = NXOpen.Point3d(-slot_w_half, lug_y, PLATE_THICKNESS)
    sp2 = NXOpen.Point3d(slot_w_half, lug_y, PLATE_THICKNESS)
    sp3 = NXOpen.Point3d(slot_w_half, lug_y, slot_z_max)
    sp4 = NXOpen.Point3d(-slot_w_half, lug_y, slot_z_max)

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

    # Extrude along Y-axis to cut through first lug
    feat_slot, base_body = _extrude_curves(
        work_part, [sl1, sl2, sl3, sl4],
        NXOpen.Vector3d(0.0, 1.0, 0.0), "-1.0", "LUG_HOLE_DEPTH",
        "F3_Relief_Slot",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
        base_body
    )
    print("[OK] Vertical relief slot cut through first lug.")

    # ------------------------------------------------------------------
    # Step 12 & 13: Sketch and Extrude Remove center rectangular pocket
    # ------------------------------------------------------------------
    print("[...] Steps 12 & 13: Sketching and extruding center rectangular pocket...")
    feat_s4, sk4 = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, 0.0, PLATE_THICKNESS),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        "S4_Center_Pocket"
    )
    sk4.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    # Pocket centered on Y=0, positioned behind the lugs (at X < 0)
    # Lugs lie between X = -LUG_WIDTH/2 and +LUG_WIDTH/2
    # Pocket extends from X = -LUG_WIDTH/2 - 2.0 - CENTER_POCKET_LENGTH to -LUG_WIDTH/2 - 2.0
    px_min = -half_lw - 2.0 - CENTER_POCKET_LENGTH
    px_max = -half_lw - 2.0
    py_half = CENTER_POCKET_WIDTH / 2.0

    pp1 = NXOpen.Point3d(px_min, -py_half, PLATE_THICKNESS)
    pp2 = NXOpen.Point3d(px_max, -py_half, PLATE_THICKNESS)
    pp3 = NXOpen.Point3d(px_max, py_half, PLATE_THICKNESS)
    pp4 = NXOpen.Point3d(px_min, py_half, PLATE_THICKNESS)

    pl1 = work_part.Curves.CreateLine(pp1, pp2)
    pl2 = work_part.Curves.CreateLine(pp2, pp3)
    pl3 = work_part.Curves.CreateLine(pp3, pp4)
    pl4 = work_part.Curves.CreateLine(pp4, pp1)

    for curve in (pl1, pl2, pl3, pl4):
        sk4.AddGeometry(curve, infer)

    sk4.CreateHorizontalConstraint(_con_geom(pl1))
    sk4.CreateVerticalConstraint(_con_geom(pl2))
    sk4.CreateHorizontalConstraint(_con_geom(pl3))
    sk4.CreateVerticalConstraint(_con_geom(pl4))
    sk4.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # Extrude down along Z to subtract from plate
    feat_pocket, base_body = _extrude_curves(
        work_part, [pl1, pl2, pl3, pl4],
        NXOpen.Vector3d(0.0, 0.0, -1.0), "-1.0", "HOLE_DEPTH",
        "F4_Center_Pocket",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
        base_body
    )
    print("[OK] Center pocket subtracted.")

    # ------------------------------------------------------------------
    # Step 14 & 15: Sketch and Extrude Remove left triangular cut-out
    # ------------------------------------------------------------------
    print("[...] Steps 14 & 15: Sketching and extruding left triangular cut-out...")
    feat_s5, sk5 = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, 0.0, PLATE_THICKNESS),
        NXOpen.Vector3d(1.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        "S5_Left_Triangle"
    )
    sk5.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    # Triangle centered at front-left area (X > 0, Y > 0)
    # Pointing inward (-X) toward the plate center
    tx_base = half_l - 20.0
    ty_center = half_w - 20.0

    tp1 = NXOpen.Point3d(tx_base, ty_center - TRIANGLE_BASE / 2.0, PLATE_THICKNESS)
    tp2 = NXOpen.Point3d(tx_base, ty_center + TRIANGLE_BASE / 2.0, PLATE_THICKNESS)
    tp3 = NXOpen.Point3d(tx_base - TRIANGLE_HEIGHT, ty_center, PLATE_THICKNESS)

    tl1 = work_part.Curves.CreateLine(tp1, tp2)
    tl2 = work_part.Curves.CreateLine(tp2, tp3)
    tl3 = work_part.Curves.CreateLine(tp3, tp1)

    for curve in (tl1, tl2, tl3):
        sk5.AddGeometry(curve, infer)

    sk5.CreateVerticalConstraint(_con_geom(tl1))
    sk5.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # Extrude down along Z to subtract from plate
    feat_triangle, base_body = _extrude_curves(
        work_part, [tl1, tl2, tl3],
        NXOpen.Vector3d(0.0, 0.0, -1.0), "-1.0", "HOLE_DEPTH",
        "F5_Left_Triangle",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
        base_body
    )
    print("[OK] Left triangle subtracted.")

    # ------------------------------------------------------------------
    # Step 16: Mirror Feature (right triangle)
    # ------------------------------------------------------------------
    print("[...] Step 16: Mirroring left triangle about XZ plane to create right triangle...")
    _mirror_feature(work_part, feat_triangle, "XZ")
    print("[OK] Right triangle mirrored.")

    # ------------------------------------------------------------------
    # Step 17: Edge Blend (lug edges)
    #          - Vertical outside edges of both lugs
    #          - Top outside curved edges of both lugs
    # ------------------------------------------------------------------
    print("[...] Step 17: Applying edge blends to lug edges...")
    uf_session = NXOpen.UF.UFSession.GetUFSession()
    lug_edges = []
    
    # Outer top arc Z max is PLATE_THICKNESS + LUG_HEIGHT
    lug_top_z = PLATE_THICKNESS + LUG_HEIGHT
    
    for edge in base_body.GetEdges():
        try:
            v1, v2 = edge.GetVertices()
            p1 = v1.GetCoordinates()
            p2 = v2.GetCoordinates()
            edge_type = uf_session.Modl.AskEdgeType(edge.Tag)
            
            # Filter 1: Vertical outside edges of the lugs (parallel to Z, above plate, at X = ±LUG_WIDTH/2)
            if abs(p1.Z - p2.Z) > 0.1 and abs(p1.X - p2.X) < 0.1 and abs(p1.Y - p2.Y) < 0.1:
                mid_z = (p1.Z + p2.Z) / 2.0
                if mid_z > PLATE_THICKNESS:
                    # Check X coordinate corresponds to lug outer boundaries
                    if abs(abs(p1.X) - half_lw) < 0.2:
                        # Check Y coordinate corresponds to lug faces
                        if abs(abs(p1.Y) - lug_y) < 0.2 or abs(abs(p1.Y) - (lug_y + LUG_THICKNESS)) < 0.2:
                            lug_edges.append(edge)
            
            # Filter 2: Top outside curved edges of both lugs (arcs, Z near lug_top_z, radius LUG_WIDTH/2)
            if edge_type != 3:  # Not linear
                # Find maximum Z coordinate on this curved edge
                # Check if it corresponds to the top semicircular cap of the lugs
                if abs(p1.Z - arc_cz) < 0.2 and abs(p2.Z - arc_cz) < 0.2:
                    # Ensure it is not the lug hole edge (which is circular but has a different radius)
                    # Semicircular cap radius is LUG_WIDTH / 2
                    # We can check its Y coordinate is not the center of the lug thickness (which hole edges occupy)
                    # Top outside caps are on the lug outer/inner planes: Y = ±lug_y or Y = ±(lug_y + LUG_THICKNESS)
                    if abs(abs(p1.Y) - lug_y) < 0.2 or abs(abs(p1.Y) - (lug_y + LUG_THICKNESS)) < 0.2:
                        lug_edges.append(edge)
        except Exception:
            pass

    if lug_edges:
        _add_edge_blend(work_part, lug_edges, "LUG_FILLET_RADIUS")
    else:
        print("[WARN] No lug edges found for filleting.")

    # ------------------------------------------------------------------
    # Step 18: Edge Blend (lug-to-base transitions)
    #          - Horizontal contact lines where lugs meet the base plate at Z = PLATE_THICKNESS
    # ------------------------------------------------------------------
    print("[...] Step 18: Applying transitions blends where lugs join base plate...")
    transition_edges = []
    for edge in base_body.GetEdges():
        try:
            v1, v2 = edge.GetVertices()
            p1 = v1.GetCoordinates()
            p2 = v2.GetCoordinates()
            edge_type = uf_session.Modl.AskEdgeType(edge.Tag)
            
            # Horizontal lines parallel to X-axis at Z = PLATE_THICKNESS
            if abs(p1.Z - PLATE_THICKNESS) < 0.1 and abs(p2.Z - PLATE_THICKNESS) < 0.1:
                if abs(p1.X - p2.X) > 1.0 and abs(p1.Y - p2.Y) < 0.1:
                    # Check Y coordinate corresponds to lug outer/inner faces
                    if abs(abs(p1.Y) - lug_y) < 0.2 or abs(abs(p1.Y) - (lug_y + LUG_THICKNESS)) < 0.2:
                        transition_edges.append(edge)
        except Exception:
            pass

    if transition_edges:
        _add_edge_blend(work_part, transition_edges, "LUG_FILLET_RADIUS")
    else:
        print("[WARN] No lug-to-base transition edges found.")

    # ------------------------------------------------------------------
    # Step 19: Edge Blend (pocket corners)
    #          - Vertical corners of the pocket inside base plate (Z range 0 to PLATE_THICKNESS)
    # ------------------------------------------------------------------
    print("[...] Step 19: Applying blends to center pocket vertical corners...")
    pocket_corners = []
    for edge in base_body.GetEdges():
        try:
            v1, v2 = edge.GetVertices()
            p1 = v1.GetCoordinates()
            p2 = v2.GetCoordinates()
            # Vertical edges parallel to Z-axis
            if abs(p1.Z - p2.Z) > 0.1 and abs(p1.X - p2.X) < 0.1 and abs(p1.Y - p2.Y) < 0.1:
                mid_z = (p1.Z + p2.Z) / 2.0
                if mid_z < PLATE_THICKNESS:
                    # Check X/Y ranges correspond to pocket boundaries
                    if px_min - 0.2 <= p1.X <= px_max + 0.2:
                        if abs(abs(p1.Y) - py_half) < 0.2:
                            pocket_corners.append(edge)
        except Exception:
            pass

    if pocket_corners:
        _add_edge_blend(work_part, pocket_corners, "LUG_FILLET_RADIUS")
    else:
        print("[WARN] No pocket corners found.")

    # ------------------------------------------------------------------
    # Step 20: Edge Blend (triangle corners)
    #          - Vertical corners of both triangular cut-outs inside base plate
    # ------------------------------------------------------------------
    print("[...] Step 20: Applying blends to triangle corners...")
    triangle_corners = []
    for edge in base_body.GetEdges():
        try:
            v1, v2 = edge.GetVertices()
            p1 = v1.GetCoordinates()
            p2 = v2.GetCoordinates()
            edge_type = uf_session.Modl.AskEdgeType(edge.Tag)
            
            # Vertical edges parallel to Z-axis
            if abs(p1.Z - p2.Z) > 0.1 and abs(p1.X - p2.X) < 0.1 and abs(p1.Y - p2.Y) < 0.1:
                mid_z = (p1.Z + p2.Z) / 2.0
                if mid_z < PLATE_THICKNESS:
                    # Triangle is in X > 0, and not at the outer base corners or lugs
                    if p1.X > 0.0 and abs(p1.X - half_l) > 1.0:
                        # Exclude any other pockets/features
                        triangle_corners.append(edge)
        except Exception:
            pass

    if triangle_corners:
        _add_edge_blend(work_part, triangle_corners, "LUG_FILLET_RADIUS")
    else:
        print("[WARN] No triangle corners found.")

    # ------------------------------------------------------------------
    # Orient ISO View
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
    # Step 21: Save Part
    # ------------------------------------------------------------------
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("[OK] Part saved -> {}".format(output_path))

    # ------------------------------------------------------------------
    # Step 22: Export STEP
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
    # Step 23: Export STL
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
    # Update watcher files & Auto-open in NX GUI
    # ------------------------------------------------------------------
    _update_result_files(output_path)

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
    print("[DONE] Mounting plate V2 complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
