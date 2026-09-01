# Parametric Radial Engine Cylinder template for NXOpen
# Assumes pre-injected variables: NXOpen, SESSION, UF_SESSION, work_part, math, Point3d, Vector3d

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

# Vectors
vec_x_pos = Vector3d(1.0, 0.0, 0.0)
vec_z_pos = Vector3d(0.0, 0.0, 1.0)
vec_z_neg = Vector3d(0.0, 0.0, -1.0)

# 1. Base Cylinder (Dia 80, height 10), named BASE
origin_base = Point3d(0.0, 0.0, 0.0)
base_body = _create_cylinder(origin_base, vec_z_pos, "BASE_DIA", "BASE_HEIGHT")
try:
    base_body.SetName("BASE")
except Exception:
    pass

# 2. Main Cylinder (Dia 52, height 70) starting at Z = BASE_HEIGHT
origin_body = Point3d(0.0, 0.0, base_height_val)
body_cylinder = _create_cylinder(origin_body, vec_z_pos, "BODY_DIA", "BODY_HEIGHT")
_perform_unite(base_body, body_cylinder)

# 3. Top Head Cylinder (Dia 56, height 15) starting at Z = BASE_HEIGHT + BODY_HEIGHT
origin_head = Point3d(0.0, 0.0, base_height_val + body_height_val)
head_cylinder = _create_cylinder(origin_head, vec_z_pos, "HEAD_DIA", "HEAD_HEIGHT")
_perform_unite(base_body, head_cylinder)

# 4. Cooling Groove (Revolve Cut)
x_inner = body_dia_val / 2.0 - fin_depth_val
x_outer = body_dia_val / 2.0
z_bottom = base_height_val + 3.0
z_top = base_height_val + 3.0 + fin_height_val

p1 = work_part.Points.CreatePoint(Point3d(x_inner, 0.0, z_bottom))
p2 = work_part.Points.CreatePoint(Point3d(x_outer, 0.0, z_bottom))
p3 = work_part.Points.CreatePoint(Point3d(x_outer, 0.0, z_top))
p4 = work_part.Points.CreatePoint(Point3d(x_inner, 0.0, z_top))

l1 = work_part.Curves.CreateLine(p1, p2)
l2 = work_part.Curves.CreateLine(p2, p3)
l3 = work_part.Curves.CreateLine(p3, p4)
l4 = work_part.Curves.CreateLine(p4, p1)

section = work_part.Sections.CreateSection(0.001, 0.01, 0.5)
help_point = Point3d(0.0, 0.0, 0.0)
for curve in [l1, l2, l3, l4]:
    rule = work_part.ScRuleFactory.CreateRuleCurveDumb([curve])
    section.AddToSection([rule], curve, NXOpen.NXObject.Null, NXOpen.NXObject.Null, help_point, NXOpen.Section.Mode.Create)

features, number_of_features = UF_SESSION.Modl.CreateRevolution(
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
    
    dir_z = work_part.Directions.CreateDirection(
        Point3d(0.0, 0.0, 0.0), vec_z_pos, NXOpen.SmartObject.UpdateOption.WithinModeling
    )
    rect.XDirection = dir_z
    rect.XSpacing.NCopies.RightHandSide = "FIN_COUNT"
    rect.XSpacing.PitchDistance.RightHandSide = "FIN_SPACING"
    rect.UseYDirectionToggle = False
    
    lin_feat = pattern_builder.CommitFeature()
finally:
    pattern_builder.Destroy()

# 6. Side Pipe Cylinder
origin_pipe = Point3d(body_dia_val / 2.0 - 1.0, 0.0, body_height_val + pipe_center_height_val)
pipe_body = _create_cylinder(origin_pipe, vec_x_pos, "PIPE_DIA", "PIPE_LENGTH + 1.0")
_perform_unite(base_body, pipe_body)

# 7. Pipe Hole along the axis of side pipe
origin_pipe_hole = Point3d(body_dia_val / 2.0 - 6.0, 0.0, body_height_val + pipe_center_height_val)
pipe_hole = _create_cylinder(origin_pipe_hole, vec_x_pos, "PIPE_HOLE_DIA", "PIPE_LENGTH + 10.0")
_perform_subtract(base_body, pipe_hole)

# 8. Base Mounting Hole
origin_bolt = Point3d(bolt_circle_dia_val / 2.0, 0.0, base_height_val + 0.1)
bolt_hole = _create_cylinder(origin_bolt, vec_z_neg, "BOLT_HOLE_DIA", "BASE_HEIGHT + 0.2")
_perform_subtract(base_body, bolt_hole)

all_feats = list(work_part.Features)
bolt_hole_feat = all_feats[-1]

# Circular Pattern of Bolt Hole
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
        Point3d(0.0, 0.0, 0.0),
        vec_z_pos,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    circ.RotationCenter = work_part.Points.CreatePoint(Point3d(0.0, 0.0, 0.0))
    circ.IncludeSeedToggle = True
    circ.AngularSpacing.NCopies.RightHandSide = "BOLT_COUNT"
    circ.AngularSpacing.PitchAngle.RightHandSide = "360.0 / BOLT_COUNT"
    circ_feat = circ_builder.CommitFeature()
finally:
    circ_builder.Destroy()

# 9. Edge Fillets
all_body_edges = list(base_body.GetEdges())
fillet_edges = []
base_r = base_dia_val / 2.0
head_r = head_dia_val / 2.0
pipe_r = pipe_dia_val / 2.0
pipe_end_x = body_dia_val / 2.0 + pipe_length_val
total_z = base_height_val + body_height_val + head_height_val

for e in all_body_edges:
    try:
        v1, v2 = e.GetVertices()[0], e.GetVertices()[1]
        z_min = min(v1.Z, v2.Z)
        z_max = max(v1.Z, v2.Z)
        x_min = min(v1.X, v2.X)
        x_max = max(v1.X, v2.X)
        dist_1 = math.sqrt(v1.X**2 + v1.Y**2)
        dist_2 = math.sqrt(v2.X**2 + v2.Y**2)

        # Base bottom
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(z_max) < 0.1:
            if abs(dist_1 - base_r) < 1.0 and abs(dist_2 - base_r) < 1.0:
                fillet_edges.append(e)
                continue

        # Base top
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(z_max - base_height_val) < 0.1:
            if abs(dist_1 - base_r) < 1.0 and abs(dist_2 - base_r) < 1.0:
                fillet_edges.append(e)
                continue

        # Head top
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(z_max - total_z) < 0.1:
            if abs(dist_1 - head_r) < 1.0 and abs(dist_2 - head_r) < 1.0:
                fillet_edges.append(e)
                continue

        # Pipe end
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(x_max - pipe_end_x) < 0.1:
            fillet_edges.append(e)
            continue
    except Exception:
        pass

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

# Fit work view
try:
    work_part.ModelingViews.WorkView.Orient(NXOpen.View.Canned.Isometric, NXOpen.View.ScaleAdjustment.Fit)
except Exception:
    pass

print("[SUCCESS] Radial Engine Cylinder geometry generated successfully.")
