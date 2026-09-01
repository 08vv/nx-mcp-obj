"""
build_clevis_mount.py
======================
NX Journal that creates a parametric clevis mount.
All dimensions are stored as named NX Expressions.
Uses Sketch and Extrude features matching the exact build order:
  1. Sketch (Base Profile)
  2. Extrude (Base)
  3. Extrude Remove (Centered U-slot)
  4. Sketch (Boss Profile)
  5. Extrude (Stepped Boss)
  6. Hole (Through Boss and Arm)
  7. Mirror Feature (Boss and Hole)
  8. Edge Blend
  9. Save Part
  10. Export STEP
  11. Export STL
"""

import sys
import os
import math
import time
import subprocess
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
        self.Datums = MagicMock()
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
            mock_uf.Modeling.AskEdgeVerts = MagicMock(return_value=([0.0, 0.0, 58.0], [10.0, 0.0, 58.0], 2))
            mock_uf.Modl.AskEdgeType = MagicMock(return_value=3)  # Linear
            return mock_uf
    class MockUF:
        UFSession = MockUFSession
    NXOpen.UF = MockUF
else:
    try:
        import NXOpen
        import NXOpen.UF
    except ImportError:
        class Dummy:
            pass
        NXOpen = Dummy()
        NXOpen.UF = Dummy()


OUTPUT_PRT = Path("C:/Users/HP/nx-mcp/clevis_mount.prt").resolve()
OUTPUT_STEP = Path("C:/Users/HP/nx-mcp/clevis_mount.stp").resolve()
OUTPUT_STL = Path("C:/Users/HP/nx-mcp/clevis_mount.stl").resolve()


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
                        point.Coordinates, dir_vec,
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


def _mirror_features(work_part, features_to_mirror, datum_plane):
    builder = work_part.Features.CreateMirrorFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        feature_list = [f for f in features_to_mirror if f is not None]
        if hasattr(builder, "FeatureSet"):
            builder.FeatureSet.Add(feature_list)
        elif hasattr(builder, "Features"):
            builder.Features.Add(feature_list)
            
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
    print("[OK] Fillet: {} blended, {} skipped.".format(applied, failed))


def _select_clevis_edges(work_part, uf_session, body):
    edges = list(body.GetEdges() or [])
    
    base_length = work_part.Expressions.FindObject("BASE_LENGTH").Value
    base_width = work_part.Expressions.FindObject("BASE_WIDTH").Value
    base_thickness = work_part.Expressions.FindObject("BASE_THICKNESS").Value
    arm_height = work_part.Expressions.FindObject("ARM_HEIGHT").Value
    total_height = base_thickness + arm_height
    boss_cz = base_thickness + arm_height / 2.0
    boss_ext_len = work_part.Expressions.FindObject("BOSS_EXTRUSION_LENGTH").Value
    boss_flange_len = boss_ext_len / 2.0
    
    half_bl = base_length / 2.0
    half_bw = base_width / 2.0
    
    outside_vertical_edges = []
    upper_edges = []
    outside_lower_edges = []
    boss_to_arm_junctions = []
    outer_circular_edges = []
    
    for edge in edges:
        try:
            edge_type = uf_session.Modl.AskEdgeType(edge.Tag)
            
            # Linear edges
            if edge_type == 3:
                pt1, pt2, _ = uf_session.Modeling.AskEdgeVerts(edge.Tag)
                p1 = (pt1[0], pt1[1], pt1[2])
                p2 = (pt2[0], pt2[1], pt2[2])
                
                # Vertical outside corners
                if abs(p1[0] - p2[0]) < 0.1 and abs(p1[1] - p2[1]) < 0.1:
                    if abs(abs(p1[0]) - half_bw) < 0.5 and abs(abs(p1[1]) - half_bl) < 0.5:
                        outside_vertical_edges.append(edge)
                        
                # Upper edges of arms
                if abs(p1[2] - total_height) < 0.1 and abs(p2[2] - total_height) < 0.1:
                    upper_edges.append(edge)
                    
                # Lower edges of base
                if abs(p1[2] - 0.0) < 0.1 and abs(p2[2] - 0.0) < 0.1:
                    outside_lower_edges.append(edge)
                    
            # Curved edges
            else:
                pt1, pt2, _ = uf_session.Modeling.AskEdgeVerts(edge.Tag)
                p1 = (pt1[0], pt1[1], pt1[2])
                p2 = (pt2[0], pt2[1], pt2[2])
                
                mid_x = (p1[0] + p2[0]) / 2.0
                mid_y = (p1[1] + p2[1]) / 2.0
                mid_z = (p1[2] + p2[2]) / 2.0
                
                if abs(mid_y) < 0.5 and abs(mid_z - boss_cz) < 0.5:
                    if abs(abs(mid_x) - half_bw) < 0.5:
                        boss_to_arm_junctions.append(edge)
                    elif abs(abs(mid_x) - (half_bw + boss_flange_len)) < 0.5:
                        outer_circular_edges.append(edge)
                    elif abs(abs(mid_x) - (half_bw + boss_ext_len)) < 0.5:
                        outer_circular_edges.append(edge)
        except Exception:
            continue
            
    print(f"Selected: {len(outside_vertical_edges)} vertical, {len(upper_edges)} upper, "
          f"{len(outside_lower_edges)} lower, {len(boss_to_arm_junctions)} junction, "
          f"{len(outer_circular_edges)} outer circular edges.")
          
    return (outside_vertical_edges + upper_edges + outside_lower_edges +
            boss_to_arm_junctions + outer_circular_edges)


def run_nxopen_journal():
    session = NXOpen.Session.GetSession()
    uf_session = NXOpen.UF.UFSession.GetUFSession()

    OUTPUT_PRT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PRT.exists():
        try:
            OUTPUT_PRT.unlink()
        except Exception:
            pass

    # Create Display Part
    session.Parts.NewDisplay(str(OUTPUT_PRT), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    # 1. Expressions Table
    expressions = [
        ("BASE_LENGTH", "80.0"),
        ("INNER_OPENING_WIDTH", "40.0"),
        ("ARM_THICKNESS", "10.0"),
        ("BASE_WIDTH", "INNER_OPENING_WIDTH + 2.0 * ARM_THICKNESS"),
        ("BASE_THICKNESS", "12.0"),
        ("ARM_HEIGHT", "50.0"),
        ("BOSS_OUTER_DIAMETER", "30.0"),
        ("BOSS_INNER_DIAMETER", "20.0"),
        ("BOSS_EXTRUSION_LENGTH", "12.0"),
        ("THROUGH_HOLE_DIAMETER", "10.0"),
        ("EDGE_BLEND_RADIUS", "2.0"),
        # Derived expressions
        ("TOTAL_HEIGHT", "BASE_THICKNESS + ARM_HEIGHT"),
        ("HALF_BL", "BASE_LENGTH / 2.0"),
        ("HALF_BW", "BASE_WIDTH / 2.0"),
        ("HALF_IOW", "INNER_OPENING_WIDTH / 2.0"),
        ("BOSS_CZ", "BASE_THICKNESS + ARM_HEIGHT / 2.0"),
        ("BOSS_FLANGE_LEN", "BOSS_EXTRUSION_LENGTH / 2.0"),
        ("HOLE_DEPTH", "BOSS_EXTRUSION_LENGTH + ARM_THICKNESS"),
        ("HOLE_X", "-HALF_BW - BOSS_EXTRUSION_LENGTH"),
        ("HOLE_Y", "0.0"),
        ("HOLE_Z", "BOSS_CZ"),
        ("ZERO_EXP", "0.0"),
        ("BOSS_X", "-HALF_BW"),
    ]

    for name, formula in expressions:
        work_part.Expressions.CreateExpression("Number", f"{name} = {formula}")

    # Query required initial float values
    base_l_half_val = work_part.Expressions.FindObject("HALF_BL").Value
    base_w_half_val = work_part.Expressions.FindObject("HALF_BW").Value
    total_h_val = work_part.Expressions.FindObject("TOTAL_HEIGHT").Value
    base_thick_val = work_part.Expressions.FindObject("BASE_THICKNESS").Value
    inner_opening_half_val = work_part.Expressions.FindObject("HALF_IOW").Value
    boss_cz_val = work_part.Expressions.FindObject("BOSS_CZ").Value
    boss_outer_dia_val = work_part.Expressions.FindObject("BOSS_OUTER_DIAMETER").Value
    boss_inner_dia_val = work_part.Expressions.FindObject("BOSS_INNER_DIAMETER").Value
    boss_ext_len_val = work_part.Expressions.FindObject("BOSS_EXTRUSION_LENGTH").Value

    # 1. Sketch (Base Profile) on XY plane
    xy_plane = work_part.Planes.CreatePlane(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling)

    feat_s1, sk1 = _create_sketch_on_plane(work_part, xy_plane, "S1_Base")
    sk1.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    p1 = NXOpen.Point3d(-base_w_half_val, -base_l_half_val, 0.0)
    p2 = NXOpen.Point3d(base_w_half_val, -base_l_half_val, 0.0)
    p3 = NXOpen.Point3d(base_w_half_val, base_l_half_val, 0.0)
    p4 = NXOpen.Point3d(-base_w_half_val, base_l_half_val, 0.0)

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

    # Center coincident with origin
    pt_origin = work_part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    sk1.AddGeometry(pt_origin, infer)
    sk1.CreateFixedConstraint(_con_geom(pt_origin))

    CT = NXOpen.SketchConstraintType
    _apply_dim(sk1, CT.HorizontalDim, _dim_geom(pt_origin), _dim_geom(l4),
               NXOpen.Point3d(-base_w_half_val/2.0, -base_l_half_val - 5.0, 0.0),
               work_part.Expressions.FindObject("HALF_BW"))
    _apply_dim(sk1, CT.HorizontalDim, _dim_geom(pt_origin), _dim_geom(l2),
               NXOpen.Point3d(base_w_half_val/2.0, -base_l_half_val - 5.0, 0.0),
               work_part.Expressions.FindObject("HALF_BW"))
    _apply_dim(sk1, CT.VerticalDim, _dim_geom(pt_origin), _dim_geom(l3),
               NXOpen.Point3d(-base_w_half_val - 5.0, base_l_half_val/2.0, 0.0),
               work_part.Expressions.FindObject("HALF_BL"))
    _apply_dim(sk1, CT.VerticalDim, _dim_geom(pt_origin), _dim_geom(l1),
               NXOpen.Point3d(-base_w_half_val - 5.0, -base_l_half_val/2.0, 0.0),
               work_part.Expressions.FindObject("HALF_BL"))

    sk1.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # 2. Extrude (Base)
    feat_f2, base_body = _extrude_curves(
        work_part, [l1, l2, l3, l4],
        NXOpen.Vector3d(0.0, 0.0, 1.0), "0.0", "TOTAL_HEIGHT",
        "F2_Base_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    )

    # 3. Extrude Remove (Centered U-slot)
    feat_s2, sk2 = _create_sketch_on_plane(work_part, xy_plane, "S2_Slot")
    sk2.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    s1 = NXOpen.Point3d(-inner_opening_half_val, -base_l_half_val, 0.0)
    s2 = NXOpen.Point3d(inner_opening_half_val, -base_l_half_val, 0.0)
    s3 = NXOpen.Point3d(inner_opening_half_val, base_l_half_val, 0.0)
    s4 = NXOpen.Point3d(-inner_opening_half_val, base_l_half_val, 0.0)

    sl1 = work_part.Curves.CreateLine(s1, s2)
    sl2 = work_part.Curves.CreateLine(s2, s3)
    sl3 = work_part.Curves.CreateLine(s3, s4)
    sl4 = work_part.Curves.CreateLine(s4, s1)

    for curve in (sl1, sl2, sl3, sl4):
        sk2.AddGeometry(curve, infer)

    sk2.CreateHorizontalConstraint(_con_geom(sl1))
    sk2.CreateVerticalConstraint(_con_geom(sl2))
    sk2.CreateHorizontalConstraint(_con_geom(sl3))
    sk2.CreateVerticalConstraint(_con_geom(sl4))

    # Re-add pt_origin to this sketch for dimension references
    pt_origin_s2 = work_part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    sk2.AddGeometry(pt_origin_s2, infer)
    sk2.CreateFixedConstraint(_con_geom(pt_origin_s2))

    _apply_dim(sk2, CT.HorizontalDim, _dim_geom(pt_origin_s2), _dim_geom(sl4),
               NXOpen.Point3d(-inner_opening_half_val/2.0, -base_l_half_val - 5.0, 0.0),
               work_part.Expressions.FindObject("HALF_IOW"))
    _apply_dim(sk2, CT.HorizontalDim, _dim_geom(pt_origin_s2), _dim_geom(sl2),
               NXOpen.Point3d(inner_opening_half_val/2.0, -base_l_half_val - 5.0, 0.0),
               work_part.Expressions.FindObject("HALF_IOW"))
    _apply_dim(sk2, CT.VerticalDim, _dim_geom(pt_origin_s2), _dim_geom(sl3),
               NXOpen.Point3d(-inner_opening_half_val - 5.0, base_l_half_val/2.0, 0.0),
               work_part.Expressions.FindObject("HALF_BL"))
    _apply_dim(sk2, CT.VerticalDim, _dim_geom(pt_origin_s2), _dim_geom(sl1),
               NXOpen.Point3d(-inner_opening_half_val - 5.0, -base_l_half_val/2.0, 0.0),
               work_part.Expressions.FindObject("HALF_BL"))

    sk2.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    feat_f3, base_body = _extrude_curves(
        work_part, [sl1, sl2, sl3, sl4],
        NXOpen.Vector3d(0.0, 0.0, 1.0), "BASE_THICKNESS", "TOTAL_HEIGHT + 5.0",
        "F3_U_Slot_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
        base_body
    )

    # 4. Sketch (Boss Profile)
    # We create a datum plane at X = -BASE_WIDTH / 2.0 (outside face of the left arm)
    pt_boss_plane = _create_parametric_point(work_part, "BOSS_X", "ZERO_EXP", "ZERO_EXP")
    dir_vector = NXOpen.Vector3d(1.0, 0.0, 0.0)
    nx_dir = work_part.Directions.CreateDirection(NXOpen.Point3d(0.0, 0.0, 0.0), dir_vector, NXOpen.SmartObject.UpdateOption.WithinModeling)

    datum_builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        plane_obj = datum_builder.GetPlane()
        plane_obj.SetMethod(NXOpen.PlaneTypes.MethodType.PointDir)
        plane_obj.SetGeometry([pt_boss_plane, nx_dir])
        datum_feat = datum_builder.CommitFeature()
        boss_datum_plane = datum_feat.DatumPlane
    finally:
        datum_builder.Destroy()

    # Create local matrix for concentric circles in the YZ plane at X = -HALF_BW
    # Z_local = (-1,0,0) [along -X axis], X_local = (0,1,0) [along +Y], Y_local = (0,0,1) [along +Z]
    mat = NXOpen.Matrix3x3()
    mat.Xx = 0.0; mat.Xy = 1.0; mat.Xz = 0.0
    mat.Yx = 0.0; mat.Yy = 0.0; mat.Yz = 1.0
    mat.Zx = -1.0; mat.Zy = 0.0; mat.Zz = 0.0
    nx_mat = work_part.NXMatrices.Create(mat)

    # The circles are concentric, centered at (X=-base_w_half_val, Y=0.0, Z=boss_cz_val)
    center = NXOpen.Point3d(-base_w_half_val, 0.0, boss_cz_val)
    arc1 = work_part.Curves.CreateArc(center, nx_mat, boss_outer_dia_val / 2.0, 0.0, 2.0 * math.pi)
    arc2 = work_part.Curves.CreateArc(center, nx_mat, boss_inner_dia_val / 2.0, 0.0, 2.0 * math.pi)

    feat_s3, sk3 = _create_sketch_on_plane(work_part, boss_datum_plane, "S3_Boss_Profile")
    sk3.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    sk3.AddGeometry(arc1, infer)
    sk3.AddGeometry(arc2, infer)

    # Coincident constraints to the sketch center point
    pt_center = work_part.Points.CreatePoint(center)
    sk3.AddGeometry(pt_center, infer)
    sk3.CreateFixedConstraint(_con_geom(pt_center))
    
    sk3.CreateCoincidentConstraint(_con_geom(arc1, NXOpen.SketchConstraintPointType.ArcCenter), _con_geom(pt_center))
    sk3.CreateCoincidentConstraint(_con_geom(arc2, NXOpen.SketchConstraintPointType.ArcCenter), _con_geom(pt_center))

    # Driving dimensions for circle diameters
    _apply_dim(sk3, CT.DiameterDim, _dim_geom(arc1), None,
               NXOpen.Point3d(-base_w_half_val, boss_outer_dia_val/2.0, boss_cz_val + boss_outer_dia_val/2.0),
               work_part.Expressions.FindObject("BOSS_OUTER_DIAMETER"))
    _apply_dim(sk3, CT.DiameterDim, _dim_geom(arc2), None,
               NXOpen.Point3d(-base_w_half_val, boss_inner_dia_val/2.0, boss_cz_val + boss_inner_dia_val/2.0),
               work_part.Expressions.FindObject("BOSS_INNER_DIAMETER"))

    sk3.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # 5. Extrude (Stepped Boss)
    # Extrude 1: Flange (outer circle) along -X by BOSS_FLANGE_LEN, united
    feat_f5_flange, base_body = _extrude_curves(
        work_part, [arc1],
        NXOpen.Vector3d(-1.0, 0.0, 0.0), "0.0", "BOSS_FLANGE_LEN",
        "F5_Boss_Flange",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        base_body
    )
    # Extrude 2: Hub (inner circle) along -X by BOSS_EXTRUSION_LENGTH, united
    feat_f5_hub, base_body = _extrude_curves(
        work_part, [arc2],
        NXOpen.Vector3d(-1.0, 0.0, 0.0), "0.0", "BOSS_EXTRUSION_LENGTH",
        "F5_Boss_Hub",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        base_body
    )

    # 6. Hole (Through Boss and Arm)
    feat_f6_hole, base_body = _add_hole_feature(
        work_part, base_body,
        "HOLE_X", "HOLE_Y", "HOLE_Z",
        NXOpen.Vector3d(1.0, 0.0, 0.0), "THROUGH_HOLE_DIAMETER", "HOLE_DEPTH",
        "F6_Coaxial_Hole"
    )

    # 7. Mirror Feature (Boss and Hole)
    # Get fixed YZ plane for mirror
    mirror_plane_builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        mirror_plane_builder.SetFixedDatumPlane(NXOpen.Features.DatumPlaneBuilder.FixedType.Yz)
        mirror_plane_feat = mirror_plane_builder.CommitFeature()
        yz_mirror_plane = mirror_plane_feat.DatumPlane
    finally:
        mirror_plane_builder.Destroy()

    # Mirror flange, hub, and hole features across YZ plane
    feat_f7_mirror = _mirror_features(
        work_part,
        [feat_f5_flange, feat_f5_hub, feat_f6_hole],
        yz_mirror_plane
    )

    # 8. Edge Blend
    blend_r = work_part.Expressions.FindObject("EDGE_BLEND_RADIUS").Value
    if blend_r > 0.0:
        edges_to_blend = _select_clevis_edges(work_part, uf_session, base_body)
        if edges_to_blend:
            _add_edge_blend(work_part, edges_to_blend, "EDGE_BLEND_RADIUS")
        else:
            print("[WARN] No edges selected for blend.")

    # Orient to ISO and fit view
    try:
        work_part.ModelingViews.WorkView.Orient("ISO")
        work_part.ModelingViews.WorkView.Fit()
    except Exception:
        pass

    # 9. Save Part
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"[OK] Saved part: {OUTPUT_PRT}")

    # 10. Export STEP using DexManager
    try:
        if OUTPUT_STEP.exists():
            try:
                OUTPUT_STEP.unlink()
            except Exception:
                pass
        step_creator = session.DexManager.CreateStepCreator()
        step_creator.ObjectTypes.Solids = True
        step_creator.OutputFile = str(OUTPUT_STEP)
        step_creator.Commit()
        step_creator.Destroy()
        print(f"[OK] Exported STEP: {OUTPUT_STEP}")
    except Exception as e:
        print(f"[WARN] STEP export error: {e}")

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
        
        start_time = time.time()
        while time.time() - start_time < 5:
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
    if OUTPUT_STEP.exists() and OUTPUT_STEP.stat().st_size > 0:
        return
        
    print("[INFO] Falling back to STEP CLI converter...")
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
            print(f"[OK] STEP exported via STEP214 CLI ({OUTPUT_STEP.stat().st_size} bytes): {OUTPUT_STEP}")
            return
        time.sleep(0.5)
    print(f"[WARN] STEP CLI output: {res.stdout}")


def launch_and_connect():
    os.system("taskkill /F /IM ugraf.exe 2>nul")
    time.sleep(1)

    nx_base = r"C:\Program Files\Siemens\NX2206"
    nxbin = r"C:\Program Files\Siemens\NX2206\NXBIN"
    run_journal = os.path.join(nxbin, "run_journal.exe")
    script_path = str(Path(__file__).resolve())

    env = os.environ.copy()
    env["UGII_BASE_DIR"] = nx_base
    env["UGII_ROOT_DIR"] = nxbin
    env["PATH"] = f"{nxbin};{nx_base}\\UGII;{env.get('PATH', '')}"

    print(f"[INFO] Executing script via run_journal.exe: {run_journal}")
    res = subprocess.run([run_journal, script_path], env=env, capture_output=True, text=True)
    print("STDOUT:\n", res.stdout)
    if res.stderr:
        print("STDERR:\n", res.stderr)

    export_step_cli()

    return res.returncode == 0


def main():
    is_nx_env = False
    if os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1":
        is_nx_env = True
    else:
        try:
            import NXOpen
            if hasattr(NXOpen, "Session"):
                is_nx_env = True
        except ImportError:
            pass

    if is_nx_env:
        run_nxopen_journal()
    else:
        print("[INFO] Running launcher...")
        success = launch_and_connect()
        if success:
            print("\n" + "="*60)
            print("SUCCESS: Clevis Mount CAD model complete!")
            print(f"  PRT:  {OUTPUT_PRT}")
            print(f"  STEP: {OUTPUT_STEP}")
            print(f"  STL:  {OUTPUT_STL}")
            print("="*60)


if __name__ == "__main__":
    main()
