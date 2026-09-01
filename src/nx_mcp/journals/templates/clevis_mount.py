# Parametric Clevis Mount template for NXOpen
# Assumes pre-injected variables: NXOpen, SESSION, UF_SESSION, work_part, math, Point3d, Vector3d

# Helper functions
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

def _create_sketch_on_plane(plane_obj, sketch_name):
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

def _extrude_curves(curves, dir_vec, start_expr, end_expr, feature_name, boolean_type=None, target_body=None):
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
        Point3d(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create, False)

    builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section
        nx_dir = work_part.Directions.CreateDirection(
            Point3d(0.0, 0.0, 0.0),
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
    return feat, body

def _create_parametric_point(x_name, y_name, z_name):
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

def _add_hole_feature(target_body, x_expr, y_expr, z_expr, dir_vec, dia_expr_name, depth_expr_name, feature_name):
    point = _create_parametric_point(x_expr, y_expr, z_expr)
    
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
        
    _perform_subtract(target_body, tool_body)
    return feat, target_body

def _mirror_features(features_to_mirror, datum_plane):
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
                Point3d(0.0, 0.0, 0.0),
            )
        elif hasattr(builder, "MirrorPlane"):
            builder.MirrorPlane = datum_plane
            
        feat = builder.CommitFeature()
        return feat
    finally:
        builder.Destroy()

def _blend_single_edge(edge, radius_expr):
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

def _add_edge_blend(edges, radius_expr):
    applied = failed = 0
    for edge in edges:
        try:
            _blend_single_edge(edge, radius_expr)
            applied += 1
        except Exception:
            failed += 1
    print("[OK] Fillet: {} blended, {} skipped.".format(applied, failed))

def _select_clevis_edges(body):
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
            edge_type = UF_SESSION.Modl.AskEdgeType(edge.Tag)
            
            if edge_type == 3:  # Linear
                pt1, pt2, _ = UF_SESSION.Modeling.AskEdgeVerts(edge.Tag)
                p1 = (pt1[0], pt1[1], pt1[2])
                p2 = (pt2[0], pt2[1], pt2[2])
                
                if abs(p1[0] - p2[0]) < 0.1 and abs(p1[1] - p2[1]) < 0.1:
                    if abs(abs(p1[0]) - half_bw) < 0.5 and abs(abs(p1[1]) - half_bl) < 0.5:
                        outside_vertical_edges.append(edge)
                        
                if abs(p1[2] - total_height) < 0.1 and abs(p2[2] - total_height) < 0.1:
                    upper_edges.append(edge)
                    
                if abs(p1[2] - 0.0) < 0.1 and abs(p2[2] - 0.0) < 0.1:
                    outside_lower_edges.append(edge)
            else:
                pt1, pt2, _ = UF_SESSION.Modeling.AskEdgeVerts(edge.Tag)
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
            
    return (outside_vertical_edges + upper_edges + outside_lower_edges +
            boss_to_arm_junctions + outer_circular_edges)

# Core Feature Building Logic
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

# Query required initial values
base_l_half_val = work_part.Expressions.FindObject("HALF_BL").Value
base_w_half_val = work_part.Expressions.FindObject("HALF_BW").Value
inner_opening_half_val = work_part.Expressions.FindObject("HALF_IOW").Value
boss_cz_val = work_part.Expressions.FindObject("BOSS_CZ").Value
boss_outer_dia_val = work_part.Expressions.FindObject("BOSS_OUTER_DIAMETER").Value
boss_inner_dia_val = work_part.Expressions.FindObject("BOSS_INNER_DIAMETER").Value

# XY Plane Reference
xy_plane = work_part.Planes.CreatePlane(
    Point3d(0.0, 0.0, 0.0),
    Vector3d(0.0, 0.0, 1.0),
    NXOpen.SmartObject.UpdateOption.WithinModeling)

# 2. Sketch Base Profile
feat_s1, sk1 = _create_sketch_on_plane(xy_plane, "S1_Base")
sk1.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

p1 = Point3d(-base_w_half_val, -base_l_half_val, 0.0)
p2 = Point3d(base_w_half_val, -base_l_half_val, 0.0)
p3 = Point3d(base_w_half_val, base_l_half_val, 0.0)
p4 = Point3d(-base_w_half_val, base_l_half_val, 0.0)

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

pt_origin = work_part.Points.CreatePoint(Point3d(0.0, 0.0, 0.0))
sk1.AddGeometry(pt_origin, infer)
sk1.CreateFixedConstraint(_con_geom(pt_origin))

CT = NXOpen.SketchConstraintType
_apply_dim(sk1, CT.HorizontalDim, _dim_geom(pt_origin), _dim_geom(l4),
           Point3d(-base_w_half_val/2.0, -base_l_half_val - 5.0, 0.0),
           work_part.Expressions.FindObject("HALF_BW"))
_apply_dim(sk1, CT.HorizontalDim, _dim_geom(pt_origin), _dim_geom(l2),
           Point3d(base_w_half_val/2.0, -base_l_half_val - 5.0, 0.0),
           work_part.Expressions.FindObject("HALF_BW"))
_apply_dim(sk1, CT.VerticalDim, _dim_geom(pt_origin), _dim_geom(l3),
           Point3d(-base_w_half_val - 5.0, base_l_half_val/2.0, 0.0),
           work_part.Expressions.FindObject("HALF_BL"))
_apply_dim(sk1, CT.VerticalDim, _dim_geom(pt_origin), _dim_geom(l1),
           Point3d(-base_w_half_val - 5.0, -base_l_half_val/2.0, 0.0),
           work_part.Expressions.FindObject("HALF_BL"))

sk1.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

# Extrude Base
feat_f2, base_body = _extrude_curves(
    [l1, l2, l3, l4],
    Vector3d(0.0, 0.0, 1.0), "0.0", "TOTAL_HEIGHT",
    "F2_Base_Extrude",
    NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
)

# 3. Extrude Remove Centered U-slot
feat_s2, sk2 = _create_sketch_on_plane(xy_plane, "S2_Slot")
sk2.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

s1 = Point3d(-inner_opening_half_val, -base_l_half_val, 0.0)
s2 = Point3d(inner_opening_half_val, -base_l_half_val, 0.0)
s3 = Point3d(inner_opening_half_val, base_l_half_val, 0.0)
s4 = Point3d(-inner_opening_half_val, base_l_half_val, 0.0)

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

pt_origin_s2 = work_part.Points.CreatePoint(Point3d(0.0, 0.0, 0.0))
sk2.AddGeometry(pt_origin_s2, infer)
sk2.CreateFixedConstraint(_con_geom(pt_origin_s2))

_apply_dim(sk2, CT.HorizontalDim, _dim_geom(pt_origin_s2), _dim_geom(sl4),
           Point3d(-inner_opening_half_val/2.0, -base_l_half_val - 5.0, 0.0),
           work_part.Expressions.FindObject("HALF_IOW"))
_apply_dim(sk2, CT.HorizontalDim, _dim_geom(pt_origin_s2), _dim_geom(sl2),
           Point3d(inner_opening_half_val/2.0, -base_l_half_val - 5.0, 0.0),
           work_part.Expressions.FindObject("HALF_IOW"))
_apply_dim(sk2, CT.VerticalDim, _dim_geom(pt_origin_s2), _dim_geom(sl3),
           Point3d(-inner_opening_half_val - 5.0, base_l_half_val/2.0, 0.0),
           work_part.Expressions.FindObject("HALF_BL"))
_apply_dim(sk2, CT.VerticalDim, _dim_geom(pt_origin_s2), _dim_geom(sl1),
           Point3d(-inner_opening_half_val - 5.0, -base_l_half_val/2.0, 0.0),
           work_part.Expressions.FindObject("HALF_BL"))

sk2.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

feat_f3, base_body = _extrude_curves(
    [sl1, sl2, sl3, sl4],
    Vector3d(0.0, 0.0, 1.0), "BASE_THICKNESS", "TOTAL_HEIGHT + 5.0",
    "F3_U_Slot_Extrude",
    NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
    base_body
)

# 4. Sketch Boss Profile
pt_boss_plane = _create_parametric_point("BOSS_X", "ZERO_EXP", "ZERO_EXP")
dir_vector = Vector3d(1.0, 0.0, 0.0)
nx_dir = work_part.Directions.CreateDirection(Point3d(0.0, 0.0, 0.0), dir_vector, NXOpen.SmartObject.UpdateOption.WithinModeling)

datum_builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
try:
    plane_obj = datum_builder.GetPlane()
    plane_obj.SetMethod(NXOpen.PlaneTypes.MethodType.PointDir)
    plane_obj.SetGeometry([pt_boss_plane, nx_dir])
    datum_feat = datum_builder.CommitFeature()
    boss_datum_plane = datum_feat.DatumPlane
finally:
    datum_builder.Destroy()

mat = NXOpen.Matrix3x3()
mat.Xx = 0.0; mat.Xy = 1.0; mat.Xz = 0.0
mat.Yx = 0.0; mat.Yy = 0.0; mat.Yz = 1.0
mat.Zx = -1.0; mat.Zy = 0.0; mat.Zz = 0.0
nx_mat = work_part.NXMatrices.Create(mat)

center = Point3d(-base_w_half_val, 0.0, boss_cz_val)
arc1 = work_part.Curves.CreateArc(center, nx_mat, boss_outer_dia_val / 2.0, 0.0, 2.0 * math.pi)
arc2 = work_part.Curves.CreateArc(center, nx_mat, boss_inner_dia_val / 2.0, 0.0, 2.0 * math.pi)

feat_s3, sk3 = _create_sketch_on_plane(boss_datum_plane, "S3_Boss_Profile")
sk3.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

sk3.AddGeometry(arc1, infer)
sk3.AddGeometry(arc2, infer)

pt_center = work_part.Points.CreatePoint(center)
sk3.AddGeometry(pt_center, infer)
sk3.CreateFixedConstraint(_con_geom(pt_center))

sk3.CreateCoincidentConstraint(_con_geom(arc1, NXOpen.SketchConstraintPointType.ArcCenter), _con_geom(pt_center))
sk3.CreateCoincidentConstraint(_con_geom(arc2, NXOpen.SketchConstraintPointType.ArcCenter), _con_geom(pt_center))

_apply_dim(sk3, CT.DiameterDim, _dim_geom(arc1), None,
           Point3d(-base_w_half_val, boss_outer_dia_val/2.0, boss_cz_val + boss_outer_dia_val/2.0),
           work_part.Expressions.FindObject("BOSS_OUTER_DIAMETER"))
_apply_dim(sk3, CT.DiameterDim, _dim_geom(arc2), None,
           Point3d(-base_w_half_val, boss_inner_dia_val/2.0, boss_cz_val + boss_inner_dia_val/2.0),
           work_part.Expressions.FindObject("BOSS_INNER_DIAMETER"))

sk3.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

# 5. Extrude Stepped Boss
feat_f5_flange, base_body = _extrude_curves(
    [arc1],
    Vector3d(-1.0, 0.0, 0.0), "0.0", "BOSS_FLANGE_LEN",
    "F5_Boss_Flange",
    NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
    base_body
)

feat_f5_hub, base_body = _extrude_curves(
    [arc2],
    Vector3d(-1.0, 0.0, 0.0), "0.0", "BOSS_EXTRUSION_LENGTH",
    "F5_Boss_Hub",
    NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
    base_body
)

# 6. Coaxial Through Hole
feat_f6_hole, base_body = _add_hole_feature(
    base_body,
    "HOLE_X", "HOLE_Y", "HOLE_Z",
    Vector3d(1.0, 0.0, 0.0), "THROUGH_HOLE_DIAMETER", "HOLE_DEPTH",
    "F6_Coaxial_Hole"
)

# 7. Mirror Features across YZ plane
mirror_plane_builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
try:
    mirror_plane_builder.SetFixedDatumPlane(NXOpen.Features.DatumPlaneBuilder.FixedType.Yz)
    mirror_plane_feat = mirror_plane_builder.CommitFeature()
    yz_mirror_plane = mirror_plane_feat.DatumPlane
finally:
    mirror_plane_builder.Destroy()

feat_f7_mirror = _mirror_features(
    [feat_f5_flange, feat_f5_hub, feat_f6_hole],
    yz_mirror_plane
)

# 8. Edge Blend Fillets
blend_r = work_part.Expressions.FindObject("EDGE_BLEND_RADIUS").Value
if blend_r > 0.0:
    edges_to_blend = _select_clevis_edges(base_body)
    if edges_to_blend:
        _add_edge_blend(edges_to_blend, "EDGE_BLEND_RADIUS")

# Fit work view
try:
    work_part.ModelingViews.WorkView.Orient(NXOpen.View.Canned.Isometric, NXOpen.View.ScaleAdjustment.Fit)
except Exception:
    pass

print("[SUCCESS] Clevis Mount geometry generated successfully.")
