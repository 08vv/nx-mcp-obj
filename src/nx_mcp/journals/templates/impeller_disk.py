# Parametric Impeller Disk template for NXOpen
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

# 1. Expressions Table
expressions = [
    ("DISK_DIA", 120.0),
    ("DISK_THICK", 8.0),
    ("HUB_DIA", 22.0),
    ("HUB_HEIGHT", 8.0),
    ("BORE_DIA", 10.0),
    ("BLADE_COUNT", 9.0),
    ("INNER_RADIUS", 16.0),
    ("OUTER_RADIUS", 55.0),
    ("BLADE_START_WIDTH", 5.0),
    ("BLADE_END_WIDTH", 7.0),
    ("BLADE_DEPTH", 4.0),
    ("BLADE_SWEEP", 52.0),
    ("POCKET_FILLET", 0.5),
    ("HUB_FILLET", 1.0),
    ("EDGE_FILLET", 1.0),
]
for name, value in expressions:
    work_part.Expressions.CreateExpression("Number", f"{name} = {value}")

# Evaluate variables dynamically
disk_dia_val = work_part.Expressions.FindObject("DISK_DIA").Value
disk_thick_val = work_part.Expressions.FindObject("DISK_THICK").Value
hub_dia_val = work_part.Expressions.FindObject("HUB_DIA").Value
hub_height_val = work_part.Expressions.FindObject("HUB_HEIGHT").Value
bore_dia_val = work_part.Expressions.FindObject("BORE_DIA").Value
blade_count_val = work_part.Expressions.FindObject("BLADE_COUNT").Value
inner_radius_val = work_part.Expressions.FindObject("INNER_RADIUS").Value
outer_radius_val = work_part.Expressions.FindObject("OUTER_RADIUS").Value
blade_start_width_val = work_part.Expressions.FindObject("BLADE_START_WIDTH").Value
blade_end_width_val = work_part.Expressions.FindObject("BLADE_END_WIDTH").Value
blade_depth_val = work_part.Expressions.FindObject("BLADE_DEPTH").Value
blade_sweep_val = work_part.Expressions.FindObject("BLADE_SWEEP").Value

# Vectors
vec_z_pos = Vector3d(0.0, 0.0, 1.0)
vec_z_neg = Vector3d(0.0, 0.0, -1.0)

# 1. Base Disk (Cylinder Dia 120, height 8) named BASE
origin_disk = Point3d(0.0, 0.0, 0.0)
base_body = _create_cylinder(origin_disk, vec_z_pos, "DISK_DIA", "DISK_THICK")
try:
    base_body.SetName("BASE")
except Exception:
    pass

# 2. Hub (Cylinder Dia 22, height DISK_THICK + HUB_HEIGHT = 16)
origin_hub = Point3d(0.0, 0.0, 0.0)
hub_body = _create_cylinder(origin_hub, vec_z_pos, "HUB_DIA", "DISK_THICK + HUB_HEIGHT")
_perform_unite(base_body, hub_body)

# 3. Center Bore Hole (BORE_DIA, Through All along -Z)
origin_bore = Point3d(0.0, 0.0, disk_thick_val + hub_height_val + 0.1)
bore_cyl = _create_cylinder(origin_bore, vec_z_neg, "BORE_DIA", "DISK_THICK + HUB_HEIGHT + 0.2")
_perform_subtract(base_body, bore_cyl)

# 4. Blade Pocket sketch & extrude-cut (Z = DISK_THICK)
polar_pts = [
    (inner_radius_val, 0.0),
    (24.0, -8.0),
    (34.0, -18.0),
    (45.0, -34.0),
    (outer_radius_val, -blade_sweep_val)
]

cart_pts = []
for r, theta in polar_pts:
    theta_rad = math.radians(theta)
    cart_pts.append((r * math.cos(theta_rad), r * math.sin(theta_rad)))
    
offset_pts = []
n_pts = len(cart_pts)
for i in range(n_pts):
    if i == 0:
        tx = cart_pts[1][0] - cart_pts[0][0]
        ty = cart_pts[1][1] - cart_pts[0][1]
    elif i == n_pts - 1:
        tx = cart_pts[i][0] - cart_pts[i-1][0]
        ty = cart_pts[i][1] - cart_pts[i-1][1]
    else:
        tx = cart_pts[i+1][0] - cart_pts[i-1][0]
        ty = cart_pts[i+1][1] - cart_pts[i-1][1]
        
    length = math.sqrt(tx**2 + ty**2)
    nx = -ty / length
    ny = tx / length
    
    r_current = polar_pts[i][0]
    frac = (r_current - inner_radius_val) / (outer_radius_val - inner_radius_val)
    w = blade_start_width_val + frac * (blade_end_width_val - blade_start_width_val)
    
    ox = cart_pts[i][0] + w * nx
    oy = cart_pts[i][1] + w * ny
    offset_pts.append((ox, oy))

z_start = disk_thick_val

# Create Spline 1
builder1 = work_part.Features.CreateStudioSplineBuilderEx(NXOpen.Features.Feature.Null)
builder1.Degree = 3
builder1.IsPeriodic = False
for ox, oy in cart_pts:
    pt = work_part.Points.CreatePoint(Point3d(ox, oy, z_start))
    gcd = builder1.ConstraintManager.CreateGeometricConstraintData()
    gcd.Point = pt
    builder1.ConstraintManager.Append(gcd)
feat1 = builder1.CommitFeature()
spline1 = feat1.GetEntities()[0]
builder1.Destroy()

# Create Spline 2
builder2 = work_part.Features.CreateStudioSplineBuilderEx(NXOpen.Features.Feature.Null)
builder2.Degree = 3
builder2.IsPeriodic = False
for ox, oy in offset_pts:
    pt = work_part.Points.CreatePoint(Point3d(ox, oy, z_start))
    gcd = builder2.ConstraintManager.CreateGeometricConstraintData()
    gcd.Point = pt
    builder2.ConstraintManager.Append(gcd)
feat2 = builder2.CommitFeature()
spline2 = feat2.GetEntities()[0]
builder2.Destroy()

# Close spline ends
pt_s1 = work_part.Points.CreatePoint(Point3d(cart_pts[0][0], cart_pts[0][1], z_start))
pt_s2 = work_part.Points.CreatePoint(Point3d(offset_pts[0][0], offset_pts[0][1], z_start))
line_start = work_part.Curves.CreateLine(pt_s1, pt_s2)

pt_e1 = work_part.Points.CreatePoint(Point3d(cart_pts[-1][0], cart_pts[-1][1], z_start))
pt_e2 = work_part.Points.CreatePoint(Point3d(offset_pts[-1][0], offset_pts[-1][1], z_start))
line_end = work_part.Curves.CreateLine(pt_e1, pt_e2)

# Create Section
section = work_part.Sections.CreateSection(0.001, 0.01, 0.5)
help_point = Point3d(0.0, 0.0, 0.0)
for curve in [spline1, line_end, spline2, line_start]:
    rule = work_part.ScRuleFactory.CreateRuleCurveDumb([curve])
    section.AddToSection([rule], curve, NXOpen.NXObject.Null, NXOpen.NXObject.Null, help_point, NXOpen.Section.Mode.Create)

# Extrude cut the blade pocket
ext_builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
try:
    ext_builder.Section = section
    ext_builder.Direction = work_part.Directions.CreateDirection(
        pt_s1.Coordinates, vec_z_neg, NXOpen.SmartObject.UpdateOption.WithinModeling
    )
    ext_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
    ext_builder.Limits.EndExtend.Value.RightHandSide = "BLADE_DEPTH"
    ext_builder.BooleanOperation.SetBooleanOperationAndBody(
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
        base_body
    )
    pocket_feat = ext_builder.CommitFeature()
finally:
    ext_builder.Destroy()

# 5. Circular Pattern of blade pocket
work_part.Expressions.CreateExpression("Number", "BLADE_PITCH_ANGLE = 360.0 / BLADE_COUNT")

pattern_builder = work_part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
try:
    pattern_builder.FeatureList.Add([pocket_feat])
    try:
        pattern_builder.PatternMethod = NXOpen.Features.PatternFeatureBuilder.PatternMethodOptions.Simple
    except Exception:
        pass
    service = pattern_builder.PatternService
    service.PatternType = NXOpen.GeometricUtilities.PatternDefinition.PatternEnum.Circular
    circ = service.CircularDefinition
    circ.RotationAxis = work_part.Axes.CreateAxis(
        Point3d(0.0, 0.0, z_start),
        vec_z_pos,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    circ.RotationCenter = work_part.Points.CreatePoint(Point3d(0.0, 0.0, z_start))
    circ.IncludeSeedToggle = True
    circ.AngularSpacing.NCopies.RightHandSide = "BLADE_COUNT"
    circ.AngularSpacing.PitchAngle.RightHandSide = "BLADE_PITCH_ANGLE"
    pattern_feat = pattern_builder.CommitFeature()
finally:
    pattern_builder.Destroy()

# 6. Fillets
all_body_edges = list(base_body.GetEdges())
pocket_edges = []
hub_edges = []
disk_edges = []

hub_top_z = disk_thick_val + hub_height_val
hub_r = hub_dia_val / 2.0
disk_r = disk_dia_val / 2.0

for e in all_body_edges:
    try:
        v1, v2 = e.GetVertices()[0], e.GetVertices()[1]
        z_min = min(v1.Z, v2.Z)
        z_max = max(v1.Z, v2.Z)
        dist_1 = math.sqrt(v1.X**2 + v1.Y**2)
        dist_2 = math.sqrt(v2.X**2 + v2.Y**2)

        # Hub top circular edge
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(z_max - hub_top_z) < 0.1:
            if abs(dist_1 - hub_r) < 1.0 and abs(dist_2 - hub_r) < 1.0:
                hub_edges.append(e)
                continue

        # Outer top circular edge of disk
        if e.EdgeType == NXOpen.Edge.EdgeType.Circular and abs(z_max - disk_thick_val) < 0.1:
            if abs(dist_1 - disk_r) < 1.0 and abs(dist_2 - disk_r) < 1.0:
                disk_edges.append(e)
                continue

        # Upper pocket edges
        if abs(z_max - disk_thick_val) < 0.1 and abs(z_min - disk_thick_val) < 0.1:
            if e.EdgeType != NXOpen.Edge.EdgeType.Linear:
                if dist_1 < (disk_r - 1.0) and dist_1 > (hub_r + 1.0) and dist_2 < (disk_r - 1.0) and dist_2 > (hub_r + 1.0):
                    pocket_edges.append(e)
                    continue
    except Exception:
        pass

# Fillet Pocket Edges
if pocket_edges:
    blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        collector = work_part.ScCollectors.CreateCollector()
        rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in pocket_edges]
        collector.ReplaceRules(rules, False)
        blend_builder.Tolerance = 0.01
        blend_builder.AddChainset(collector, "POCKET_FILLET")
        blend_builder.CommitFeature()
    except Exception as exc:
        print(f"[WARN] Pocket fillets note: {exc}")
    finally:
        blend_builder.Destroy()

# Fillet Hub
if hub_edges:
    blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        collector = work_part.ScCollectors.CreateCollector()
        rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in hub_edges]
        collector.ReplaceRules(rules, False)
        blend_builder.Tolerance = 0.01
        blend_builder.AddChainset(collector, "HUB_FILLET")
        blend_builder.CommitFeature()
    except Exception as exc:
        print(f"[WARN] Hub fillet note: {exc}")
    finally:
        blend_builder.Destroy()

# Fillet Outer Disk
if disk_edges:
    blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        collector = work_part.ScCollectors.CreateCollector()
        rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in disk_edges]
        collector.ReplaceRules(rules, False)
        blend_builder.Tolerance = 0.01
        blend_builder.AddChainset(collector, "EDGE_FILLET")
        blend_builder.CommitFeature()
    except Exception as exc:
        print(f"[WARN] Outer disk fillet note: {exc}")
    finally:
        blend_builder.Destroy()

# Fit work view
try:
    work_part.ModelingViews.WorkView.Orient(NXOpen.View.Canned.Isometric, NXOpen.View.ScaleAdjustment.Fit)
except Exception:
    pass

print("[SUCCESS] Impeller Disk geometry generated successfully.")
