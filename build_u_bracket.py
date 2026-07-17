"""
build_u_bracket.py
===================
NX Journal that creates a parametric U-bracket with side bosses.
All dimensions and coordinates are stored as named NX Expressions.
Uses Sketch and Extrude features matching the exact build order.
"""

import sys
import os
import math
from pathlib import Path

# Support running in mock mode for local testing
if os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1":
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root / "src"))
    import nx_mcp.testing.mock_nxopen as NXOpen
    from unittest.mock import MagicMock
    class MockExpression:
        def __init__(self, name, formula):
            self.Name = name
            self.RightHandSide = formula
            self.Value = 1.0  # mock numeric value
            try:
                self.Value = float(formula)
            except Exception:
                pass
    class MockExpressionsCollection:
        def __init__(self):
            self._exprs = {}
        def CreateExpression(self, type_str, expr_str):
            name, formula = expr_str.split("=", 1)
            name = name.strip()
            formula = formula.strip()
            self._exprs[name] = MockExpression(name, formula)
        def FindObject(self, name):
            if name in self._exprs:
                return self._exprs[name]
            mock_expr = MagicMock()
            mock_expr.Value = 1.0
            return mock_expr
        def __iter__(self):
            return iter(self._exprs.values())
    
    orig_init = NXOpen._WorkPart.__init__
    def patched_init(self):
        orig_init(self)
        self.Expressions = MockExpressionsCollection()
        self.Planes = MagicMock()
        self.Points = MagicMock()
        self.Sections = MagicMock()
        self.ScRuleFactory = MagicMock()
        self.ScCollectors = MagicMock()
        self.Directions = MagicMock()
        self.CoordinateSystems = MagicMock()
        self.NXMatrices = MagicMock()
        self.Scalars = MagicMock()
        self.WCS = MagicMock()
        self.ModelingViews = MagicMock()
        self.Save = MagicMock()
    NXOpen._WorkPart.__init__ = patched_init

    NXOpen.SmartObject = MagicMock()
    NXOpen.SketchDimensionOption = MagicMock()
    NXOpen.Sketch = MagicMock()
    NXOpen.BasePart = MagicMock()
    NXOpen.SketchConstraintPointType = MagicMock()
    NXOpen.SketchAssocType = MagicMock()
    NXOpen.SketchConstraintType = MagicMock()
    NXOpen.GeometricUtilities = MagicMock()
    NXOpen.NXObject = MagicMock()
    NXOpen.Section = MagicMock()
    NXOpen.Features = MagicMock()
    NXOpen.Matrix3x3 = MagicMock
    NXOpen.Scalar = MagicMock()

    class MockUFSession:
        @staticmethod
        def GetUFSession():
            mock_uf = MagicMock()
            # Return coordinates consistent with default values
            mock_uf.Modeling.AskFaceData = MagicMock(return_value=(1, [-28.0, 0.0, 33.0], [-1.0, 0.0, 0.0], [0,0,0,0,0,0], 0.0, False, False))
            mock_uf.Modeling.AskEdgeVerts = MagicMock(return_value=([0.0, 0.0, 58.0], [10.0, 0.0, 58.0], 2))
            return mock_uf
    class MockUF:
        UFSession = MockUFSession
    NXOpen.UF = MockUF
else:
    import NXOpen
    import NXOpen.UF


def _output_path() -> Path:
    return Path("C:/Users/HP/nx-mcp/u_bracket_with_side_bosses.prt").resolve()


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
        except Exception as e:
            print("[INFO] CreateSketchInPlaceBuilder2 failed: {}. Falling back to CreateNewSketchInPlaceBuilder.".format(e))
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
        except Exception as e:
            print("[INFO] CreateSketchInPlaceBuilder2 failed: {}. Falling back to CreateNewSketchInPlaceBuilder.".format(e))
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
    body = feat.GetBodies()[0]
    if os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1":
        from unittest.mock import MagicMock
        body.GetFaces = MagicMock(return_value=[MagicMock(Tag=1), MagicMock(Tag=2)])
        body.GetEdges = MagicMock(return_value=[MagicMock(Tag=1), MagicMock(Tag=2)])
    return feat, body


def _create_parametric_point(work_part, x_name, y_name, z_name):
    expr_x = work_part.Expressions.FindObject(x_name)
    expr_y = work_part.Expressions.FindObject(y_name)
    expr_z = work_part.Expressions.FindObject(z_name)
    
    x_scalar = work_part.Scalars.CreateScalarExpression(
        expr_x, NXOpen.Scalar.DimensionalityType.NotSet,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    y_scalar = work_part.Scalars.CreateScalarExpression(
        expr_y, NXOpen.Scalar.DimensionalityType.NotSet,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    z_scalar = work_part.Scalars.CreateScalarExpression(
        expr_z, NXOpen.Scalar.DimensionalityType.NotSet,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    
    csys = work_part.WCS.CoordinateSystem
    return work_part.Points.CreatePoint(
        csys, x_scalar, y_scalar, z_scalar,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )


def _add_hole_feature(work_part, target_body, x_expr, y_expr, z_expr, dir_vec, dia_expr_name, depth_expr_name, feature_name):
    point = _create_parametric_point(work_part, x_expr, y_expr, z_expr)
    
    # Try using HoleBuilder
    builder_factory = getattr(work_part.Features, "CreateHoleBuilder", None)
    if callable(builder_factory):
        builder = builder_factory(NXOpen.Features.Feature.Null)
        try:
            for attr in ("Type", "HoleType"):
                if hasattr(builder, attr):
                    try:
                        type_enum = getattr(builder, attr + "s", None) or getattr(builder, attr)
                        simple = getattr(type_enum, "Simple", getattr(type_enum, "GeneralHole", None))
                        if simple is not None:
                            setattr(builder, attr, simple)
                        break
                    except Exception:
                        pass
            
            builder.Diameter.RightHandSide = dia_expr_name
            for depth_attr in ("Depth", "HoleDepth", "TipDepth"):
                if hasattr(builder, depth_attr):
                    try:
                        getattr(builder, depth_attr).RightHandSide = depth_expr_name
                        break
                    except Exception:
                        pass
            
            if hasattr(builder, "Position"):
                try:
                    builder.Position = point
                except Exception:
                    pass
            if hasattr(builder, "Direction"):
                try:
                    nx_dir = work_part.Directions.CreateDirection(
                        point, dir_vec,
                        NXOpen.SmartObject.UpdateOption.WithinModeling)
                    builder.Direction = nx_dir
                except Exception:
                    pass
            for attr in ("Target", "TargetBody", "BooleanOperation"):
                if hasattr(builder, attr):
                    try:
                        setattr(builder, attr, target_body)
                        break
                    except Exception:
                        pass
            feat = builder.CommitFeature()
            try:
                feat.SetName(feature_name)
            except Exception:
                pass
            return feat, target_body
        except Exception as e:
            print("[WARN] HoleBuilder failed, falling back to cylinder-subtract: {}".format(e))
        finally:
            builder.Destroy()
            
    # Fallback to cylinder subtract
    cyl_builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        nx_dir = work_part.Directions.CreateDirection(
            point.Coordinates, dir_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        cyl_builder.Diameter.RightHandSide = dia_expr_name
        cyl_builder.Height.RightHandSide = depth_expr_name
        cyl_builder.Axis.Point = point
        cyl_builder.Axis.Direction = nx_dir
        feat = cyl_builder.Commit()
        tool_body = feat.GetBodies()[0]
    finally:
        cyl_builder.Destroy()
        
    _perform_subtract(work_part, target_body, tool_body)
    return feat, target_body


def _point_tuple(point):
    if hasattr(point, "X"):
        return (float(point.X), float(point.Y), float(point.Z))
    return (float(point[0]), float(point[1]), float(point[2]))


def _body_bounds(uf_session, body):
    try:
        bbox = uf_session.Modl.AskBoundingBox(body.Tag)
        return (
            (float(bbox[0]), float(bbox[1]), float(bbox[2])),
            (float(bbox[3]), float(bbox[4]), float(bbox[5])),
        )
    except Exception:
        pass

    points = []
    for edge in list(body.GetEdges() or []):
        try:
            pt1, pt2, _vertex_count = uf_session.Modeling.AskEdgeVerts(edge.Tag)
            points.extend([_point_tuple(pt1), _point_tuple(pt2)])
        except Exception:
            continue
    if not points:
        raise RuntimeError("Could not determine body bounds")

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _resolve_edges(uf_session, body, edge_reference="outer_edges"):
    edges = list(body.GetEdges() or [])
    if not edges:
        raise RuntimeError("No edges found on body")

    ref = str(edge_reference or "all").strip().lower().replace("-", "_")
    if ref in {"all", "all_edges", "outer", "outer_edges"}:
        return edges

    try:
        (min_x, min_y, min_z), (max_x, max_y, max_z) = _body_bounds(uf_session, body)
    except Exception:
        min_x = min_y = min_z = -999999.0
        max_x = max_y = max_z = 999999.0

    def get_edge_endpoints(edge):
        try:
            pt1, pt2, _ = uf_session.Modeling.AskEdgeVerts(edge.Tag)
            p1 = _point_tuple(pt1)
            p2 = _point_tuple(pt2)
            return p1, p2
        except Exception:
            return None, None

    if ref in {"top", "top_edges", "max_z", "max_z_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[2] - max_z) < 0.001 and abs(p2[2] - max_z) < 0.001:
                selected.append(edge)
        return selected

    return edges


def _set_collector_rules(work_part, collector, rules):
    try:
        collector.SetRules(rules)
    except Exception:
        for attr in ("SetRules", "ReplaceRules", "AddRules"):
            if hasattr(collector, attr):
                try:
                    getattr(collector, attr)(rules)
                    break
                except Exception:
                    pass


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
    uf_session = NXOpen.UF.UFSession.GetUFSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    # 1. Register Expressions and Derived Formulas
    expressions = [
        ("BASE_LENGTH", "70.0"),
        ("INNER_GAP", "40.0"),
        ("SIDE_THICK", "8.0"),
        ("BASE_WIDTH", "INNER_GAP + 2.0 * SIDE_THICK"), # Evaluates to 56.0
        ("BASE_THICK", "8.0"),
        ("SIDE_HEIGHT", "50.0"),
        ("BOSS_DIA", "24.0"),
        ("BOSS_LENGTH", "15.0"),
        ("HOLE_DIA", "12.0"),
        ("BLEND_RADIUS", "2.0"),
        ("CHAMFER_OFFSET", "1.0"),
        
        # Derived expressions for sketch and feature positioning
        ("BASE_L_HALF", "BASE_LENGTH / 2.0"),
        ("BASE_W_HALF", "BASE_WIDTH / 2.0"),
        ("SIDE_T_HALF", "SIDE_THICK / 2.0"),
        ("SIDE_T_HALF_NEG", "-SIDE_THICK / 2.0"),
        ("ZERO_EXP", "0.0"),
        
        ("LEFT_ORIGIN_X", "-BASE_WIDTH / 2.0 + SIDE_THICK / 2.0"),
        ("RIGHT_ORIGIN_X", "BASE_WIDTH / 2.0 - SIDE_THICK / 2.0"),
        
        ("BOSS_CENTER_X_L", "-BASE_WIDTH / 2.0"),
        ("BOSS_CENTER_X_R", "BASE_WIDTH / 2.0"),
        ("BOSS_CENTER_Y", "BASE_LENGTH / 2.0"),
        ("BOSS_CENTER_Z", "BASE_THICK + SIDE_HEIGHT / 2.0"),
        
        ("LEFT_HOLE_X", "-BASE_WIDTH / 2.0 - BOSS_LENGTH"),
        ("LEFT_HOLE_Y", "BASE_LENGTH / 2.0"),
        ("LEFT_HOLE_Z", "BASE_THICK + SIDE_HEIGHT / 2.0"),
        
        ("RIGHT_HOLE_X", "BASE_WIDTH / 2.0 + BOSS_LENGTH"),
        ("RIGHT_HOLE_Y", "BASE_LENGTH / 2.0"),
        ("RIGHT_HOLE_Z", "BASE_THICK + SIDE_HEIGHT / 2.0"),
        
        ("HOLE_DEPTH_EXP", "BOSS_LENGTH + SIDE_THICK + 5.0"),
    ]

    for name, formula in expressions:
        work_part.Expressions.CreateExpression("Number", f"{name} = {formula}")

    # 2. Base Sketch S1 on XY plane
    xy_plane = work_part.Planes.CreatePlane(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling)

    feat_s1, sk1 = _create_sketch_on_plane(work_part, xy_plane, "S1_Base")
    sk1.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    base_l_half_val = work_part.Expressions.FindObject("BASE_L_HALF").Value
    base_w_half_val = work_part.Expressions.FindObject("BASE_W_HALF").Value
    
    p1 = NXOpen.Point3d(-base_l_half_val, -base_w_half_val, 0.0)
    p2 = NXOpen.Point3d(base_l_half_val, -base_w_half_val, 0.0)
    p3 = NXOpen.Point3d(base_l_half_val, base_w_half_val, 0.0)
    p4 = NXOpen.Point3d(-base_l_half_val, base_w_half_val, 0.0)

    l1 = work_part.Curves.CreateLine(p1, p2)
    l2 = work_part.Curves.CreateLine(p2, p3)
    l3 = work_part.Curves.CreateLine(p3, p4)
    l4 = work_part.Curves.CreateLine(p4, p1)

    infer = NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints
    for curve in (l1, l2, l3, l4):
        sk1.AddGeometry(curve, infer)

    # Geometric constraints
    sk1.CreateHorizontalConstraint(_con_geom(l1))
    sk1.CreateVerticalConstraint(_con_geom(l2))
    sk1.CreateHorizontalConstraint(_con_geom(l3))
    sk1.CreateVerticalConstraint(_con_geom(l4))

    # Center coincident with origin
    pt_origin = work_part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    sk1.AddGeometry(pt_origin, infer)
    sk1.CreateFixedConstraint(_con_geom(pt_origin))

    CT = NXOpen.SketchConstraintType
    
    # Horizontal dimension: origin to l4 -> BASE_L_HALF
    _apply_dim(sk1, CT.HorizontalDim,
               _dim_geom(pt_origin),
               _dim_geom(l4, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(-base_l_half_val/2.0, -base_w_half_val - 5.0, 0.0),
               work_part.Expressions.FindObject("BASE_L_HALF"))

    # Horizontal dimension: origin to l2 -> BASE_L_HALF
    _apply_dim(sk1, CT.HorizontalDim,
               _dim_geom(pt_origin),
               _dim_geom(l2, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(base_l_half_val/2.0, -base_w_half_val - 5.0, 0.0),
               work_part.Expressions.FindObject("BASE_L_HALF"))

    # Vertical dimension: origin to l3 -> BASE_W_HALF
    _apply_dim(sk1, CT.VerticalDim,
               _dim_geom(pt_origin),
               _dim_geom(l3, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(-base_l_half_val - 5.0, base_w_half_val/2.0, 0.0),
               work_part.Expressions.FindObject("BASE_W_HALF"))

    # Vertical dimension: origin to l1 -> BASE_W_HALF
    _apply_dim(sk1, CT.VerticalDim,
               _dim_geom(pt_origin),
               _dim_geom(l1, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(-base_l_half_val - 5.0, -base_w_half_val/2.0, 0.0),
               work_part.Expressions.FindObject("BASE_W_HALF"))

    sk1.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # 3. Base plate extrusion F4
    feat_f4, base_body = _extrude_curves(
        work_part, [l1, l2, l3, l4],
        NXOpen.Vector3d(0.0, 0.0, 1.0), "0.0", "BASE_THICK",
        "F4_Base_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    )

    # 4. Left Side Plate — free curves in XZ plane (Y=0), extruded along +Y
    side_height_val = work_part.Expressions.FindObject("SIDE_HEIGHT").Value
    side_thick_val  = work_part.Expressions.FindObject("SIDE_THICK").Value
    base_thick_val  = work_part.Expressions.FindObject("BASE_THICK").Value
    base_w_half_val = work_part.Expressions.FindObject("BASE_W_HALF").Value

    lw_x_out = -base_w_half_val                        # outer face X  (-28)
    lw_x_in  = -base_w_half_val + side_thick_val       # inner face X  (-20)
    lw_z_bot = base_thick_val                           # bottom Z       (8)
    lw_z_top = base_thick_val + side_height_val         # top Z         (58)

    lw_p1 = NXOpen.Point3d(lw_x_out, 0.0, lw_z_bot)
    lw_p2 = NXOpen.Point3d(lw_x_in,  0.0, lw_z_bot)
    lw_p3 = NXOpen.Point3d(lw_x_in,  0.0, lw_z_top)
    lw_p4 = NXOpen.Point3d(lw_x_out, 0.0, lw_z_top)

    lw_l1 = work_part.Curves.CreateLine(lw_p1, lw_p2)
    lw_l2 = work_part.Curves.CreateLine(lw_p2, lw_p3)
    lw_l3 = work_part.Curves.CreateLine(lw_p3, lw_p4)
    lw_l4 = work_part.Curves.CreateLine(lw_p4, lw_p1)

    # 5. Extrude Left Wall F7 along +Y by BASE_LENGTH (Unite with base body)
    feat_f7, main_body = _extrude_curves(
        work_part, [lw_l1, lw_l2, lw_l3, lw_l4],
        NXOpen.Vector3d(0.0, 1.0, 0.0), "0.0", "BASE_LENGTH",
        "F7_Left_Wall_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        base_body
    )

    # 6. Right Side Plate — free curves in XZ plane (Y=0), extruded along +Y
    rw_x_in  = base_w_half_val - side_thick_val        # inner face X  (+20)
    rw_x_out = base_w_half_val                         # outer face X  (+28)

    rw_p1 = NXOpen.Point3d(rw_x_in,  0.0, lw_z_bot)
    rw_p2 = NXOpen.Point3d(rw_x_out, 0.0, lw_z_bot)
    rw_p3 = NXOpen.Point3d(rw_x_out, 0.0, lw_z_top)
    rw_p4 = NXOpen.Point3d(rw_x_in,  0.0, lw_z_top)

    rw_l1 = work_part.Curves.CreateLine(rw_p1, rw_p2)
    rw_l2 = work_part.Curves.CreateLine(rw_p2, rw_p3)
    rw_l3 = work_part.Curves.CreateLine(rw_p3, rw_p4)
    rw_l4 = work_part.Curves.CreateLine(rw_p4, rw_p1)

    # 7. Extrude Right Wall F10 along +Y by BASE_LENGTH (Unite)
    feat_f10, main_body = _extrude_curves(
        work_part, [rw_l1, rw_l2, rw_l3, rw_l4],
        NXOpen.Vector3d(0.0, 1.0, 0.0), "0.0", "BASE_LENGTH",
        "F10_Right_Wall_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        main_body
    )

    # 8. Left Boss — free circle arc at outer left face, extruded along -X
    boss_dia_val = work_part.Expressions.FindObject("BOSS_DIA").Value
    boss_l_val   = work_part.Expressions.FindObject("BASE_LENGTH").Value
    boss_c_y     = boss_l_val / 2.0
    boss_c_z     = base_thick_val + side_height_val / 2.0

    # Arc orientation: local X=(0,1,0), local Y=(0,0,1), local Z=(-1,0,0)
    # → arc lies in the YZ plane (X = lw_x_out)
    mat_l = NXOpen.Matrix3x3()
    mat_l.Xx = 0.0; mat_l.Xy = 1.0; mat_l.Xz = 0.0
    mat_l.Yx = 0.0; mat_l.Yy = 0.0; mat_l.Yz = 1.0
    mat_l.Zx = -1.0; mat_l.Zy = 0.0; mat_l.Zz = 0.0
    nx_mat_l = work_part.NXMatrices.Create(mat_l)

    circle_left = work_part.Curves.CreateArc(
        NXOpen.Point3d(lw_x_out, boss_c_y, boss_c_z),
        nx_mat_l, boss_dia_val / 2.0, 0.0, 2.0 * math.pi
    )

    # 9. Extrude Left Boss F13 along -X by BOSS_LENGTH (Unite)
    feat_f13, main_body = _extrude_curves(
        work_part, [circle_left],
        NXOpen.Vector3d(-1.0, 0.0, 0.0), "0.0", "BOSS_LENGTH",
        "F13_Left_Boss_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        main_body
    )

    # 10. Right Boss — free circle arc at outer right face, extruded along +X
    # Arc orientation: local X=(0,1,0), local Y=(0,0,1), local Z=(+1,0,0)
    mat_r = NXOpen.Matrix3x3()
    mat_r.Xx = 0.0; mat_r.Xy = 1.0; mat_r.Xz = 0.0
    mat_r.Yx = 0.0; mat_r.Yy = 0.0; mat_r.Yz = 1.0
    mat_r.Zx = 1.0; mat_r.Zy = 0.0; mat_r.Zz = 0.0
    nx_mat_r = work_part.NXMatrices.Create(mat_r)

    circle_right = work_part.Curves.CreateArc(
        NXOpen.Point3d(rw_x_out, boss_c_y, boss_c_z),
        nx_mat_r, boss_dia_val / 2.0, 0.0, 2.0 * math.pi
    )

    # 11. Extrude Right Boss F16 along +X by BOSS_LENGTH (Unite)
    feat_f16, main_body = _extrude_curves(
        work_part, [circle_right],
        NXOpen.Vector3d(1.0, 0.0, 0.0), "0.0", "BOSS_LENGTH",
        "F16_Right_Boss_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        main_body
    )

    # 13. Create Left Hole F17
    feat_f17, main_body = _add_hole_feature(
        work_part, main_body,
        "LEFT_HOLE_X", "LEFT_HOLE_Y", "LEFT_HOLE_Z",
        NXOpen.Vector3d(1.0, 0.0, 0.0), "HOLE_DIA", "HOLE_DEPTH_EXP",
        "F17_Left_Hole"
    )

    # 14. Create Right Hole F18
    feat_f18, main_body = _add_hole_feature(
        work_part, main_body,
        "RIGHT_HOLE_X", "RIGHT_HOLE_Y", "RIGHT_HOLE_Z",
        NXOpen.Vector3d(-1.0, 0.0, 0.0), "HOLE_DIA", "HOLE_DEPTH_EXP",
        "F18_Right_Hole"
    )

    # 15. Apply Edge Blend F19
    blend_r = work_part.Expressions.FindObject("BLEND_RADIUS").Value
    if blend_r > 0.0:
        blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            edges_to_blend = _resolve_edges(uf_session, main_body, "outer_edges")
            collector = work_part.ScCollectors.CreateCollector()
            rule = work_part.ScRuleFactory.CreateRuleEdgeMultipleSeedTangent(edges_to_blend, 0.5, True)
            _set_collector_rules(work_part, collector, [rule])
            
            blend_builder.Tolerance = 0.01
            blend_builder.AllInstancesOption = False
            blend_builder.RemoveSelfIntersection = True
            blend_builder.ConvexConcaveY = False
            blend_builder.RollOverSmoothEdge = True
            blend_builder.RollOntoEdge = True
            blend_builder.MoveSharpEdge = True
            blend_builder.OverlapOption = NXOpen.Features.EdgeBlendBuilder.Overlap.AnyConvexityRollOver
            blend_builder.BlendOrder = NXOpen.Features.EdgeBlendBuilder.OrderOfBlending.ConvexFirst
            blend_builder.SetbackOption = NXOpen.Features.EdgeBlendBuilder.Setback.SeparateFromCorner
            blend_builder.AddChainset(collector, "BLEND_RADIUS")
            feat_blend = blend_builder.CommitFeature()
        finally:
            blend_builder.Destroy()

    # 16. Apply Chamfer F20
    chamfer_o = work_part.Expressions.FindObject("CHAMFER_OFFSET").Value
    if chamfer_o > 0.0:
        chamfer_builder = work_part.Features.CreateChamferBuilder(NXOpen.Features.Feature.Null)
        try:
            edges_to_chamfer = _resolve_edges(uf_session, main_body, "top_edges")
            chamfer_builder.Option = NXOpen.Features.ChamferBuilder.ChamferOption.OffsetAndAngle
            chamfer_builder.Method = NXOpen.Features.ChamferBuilder.OffsetMethod.EdgesAlongFaces
            chamfer_builder.FirstOffset = "CHAMFER_OFFSET"
            chamfer_builder.SecondOffset = "CHAMFER_OFFSET"
            chamfer_builder.Angle = "45"
            chamfer_builder.Tolerance = 0.01

            rules = [
                work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False)
                for e in edges_to_chamfer
            ]
            collector_chamfer = work_part.ScCollectors.CreateCollector()
            _set_collector_rules(work_part, collector_chamfer, rules)
            chamfer_builder.SmartCollector = collector_chamfer
            feat_chamfer = chamfer_builder.CommitFeature()
        finally:
            chamfer_builder.Destroy()

    # 17. Save Part F21
    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    
    # Update latest result files
    try:
        abs_path_str = str(output_path.resolve())

        latest_file = output_path.parent / "latest_nx_result.txt"
        latest_file.write_text(abs_path_str, encoding="utf-8")

        project_root = Path(__file__).parent.resolve()
        root_latest = project_root / "latest_nx_result.txt"
        root_latest.write_text(abs_path_str, encoding="utf-8")

        cmd_path = project_root / "open_current_nx_result.cmd"
        cmd_content = '@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{}"\n'.format(abs_path_str)
        cmd_path.write_text(cmd_content, encoding="utf-8")
        print("[OK] Result files updated.")
    except Exception as exc:
        print("[WARN] Could not update result files: {}".format(exc))

    print("[DONE] Parametric U-Bracket with side bosses complete -> {}".format(output_path))

    # Automatically open the generated .prt file in NX
    try:
        import os
        print("Opening {} in NX...".format(output.name))
        os.startfile(str(output))
    except Exception as e:
        print("[WARN] Could not open file automatically: {}".format(e))


if __name__ == "__main__":
    main()
