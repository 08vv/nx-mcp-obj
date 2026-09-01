# Parametric Persil Detergent Bottle template for NXOpen
# Assumes pre-injected variables: NXOpen, SESSION, UF_SESSION, work_part, math, Point3d, Vector3d

# Helper functions
def v(name: str) -> float:
    return work_part.Expressions.FindObject(name).Value

def body_h() -> float:
    return v("Body_Height")

def shoulder_top() -> float:
    return body_h() + v("Shoulder_Height")

def neck_top() -> float:
    return shoulder_top() + v("Neck_Height")

def make_expressions() -> None:
    expressions = [
        ("Body_Height", "120.0"),
        ("Body_Width", "75.0"),
        ("Body_Depth", "45.0"),
        ("Corner_Radius", "15.0"),
        ("Shoulder_Height", "25.0"),
        ("Neck_Height", "15.0"),
        ("Neck_Diameter", "28.0"),
        ("Neck_Fillet", "3.0"),
        ("Handle_Offset_X", "15.0"),
        ("Handle_Center_Z", "70.0"),
        ("Handle_Hole_Width", "18.0"),
        ("Handle_Hole_Height", "35.0"),
        ("Handle_Fillet", "4.0"),
        ("Bottom_Fillet", "2.0"),
        ("Wall_Thickness", "1.5"),
        ("Cap_Diameter", "32.0"),
        ("Cap_Height", "20.0"),
        ("Cap_Rib_Count", "36.0"),
    ]
    for name, formula in expressions:
        try:
            work_part.Expressions.CreateExpression("Number", f"{name} = {formula}")
        except Exception:
            pass

def point(x: float, y: float, z: float) -> Point3d:
    return Point3d(x, y, z)

def line(a, b):
    return work_part.Curves.CreateLine(a, b)

def add_to_sketch(sketch, curve) -> None:
    infer = NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints
    sketch.AddGeometry(curve, infer)

def create_sketch_on_csys(origin, x_vec, y_vec, z_vec, sketch_name):
    plane = work_part.Planes.CreatePlane(origin, z_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
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
                    setattr(builder, attr, plane)
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

def xz_sketch(name: str):
    origin = point(0.0, 0.0, 0.0)
    x_vec = Vector3d(1.0, 0.0, 0.0)
    y_vec = Vector3d(0.0, 0.0, 1.0)
    z_vec = Vector3d(0.0, -1.0, 0.0)
    return create_sketch_on_csys(origin, x_vec, y_vec, z_vec, name)

def section(curves):
    sec = work_part.Sections.CreateSection(0.001, 0.01, 0.5)
    for c in curves:
        rule = work_part.ScRuleFactory.CreateRuleCurveDumb([c])
        sec.AddToSection([rule], c, NXOpen.NXObject.Null, NXOpen.NXObject.Null, Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create)
    return sec

def extrude(curves, dir_vec, start_rhs, end_rhs, name, target=None, subtract=False):
    builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section(curves)
        direction = work_part.Directions.CreateDirection(point(0.0, 0.0, 0.0), dir_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Direction = direction
        builder.Limits.StartExtend.Value.RightHandSide = start_rhs
        builder.Limits.EndExtend.Value.RightHandSide = end_rhs
        
        if subtract:
            builder.BooleanOperation.SetBooleanOperationAndBody(NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract, target)
        elif target is not None:
            builder.BooleanOperation.SetBooleanOperationAndBody(NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite, target)
        else:
            builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
            
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    try:
        feat.SetName(name)
    except Exception:
        pass
    return feat, feat.GetBodies()[0]

def extrude_y(curves, start_rhs, end_rhs, name, target=None, subtract=False):
    return extrude(curves, Vector3d(0.0, 1.0, 0.0), start_rhs, end_rhs, name, target, subtract)

def extrude_z(curves, start_rhs, end_rhs, name, target=None, subtract=False):
    return extrude(curves, Vector3d(0.0, 0.0, 1.0), start_rhs, end_rhs, name, target, subtract)

def body_feature():
    _, sk = xz_sketch("S1_Body_Profile")
    sk.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    
    bw = v("Body_Width")
    bh = body_h()
    st = shoulder_top()
    nd = v("Neck_Diameter")
    
    p1 = point(-bw*0.5, 0.0, 0.0)
    p2 = point(bw*0.5, 0.0, 0.0)
    p3 = point(bw*0.5, 0.0, bh)
    p4 = point(nd*0.5, 0.0, st)
    p5 = point(-nd*0.5, 0.0, st)
    p6 = point(-bw*0.5, 0.0, bh)
    
    l1 = line(p1, p2)
    l2 = line(p2, p3)
    l3 = line(p3, p4)
    l4 = line(p4, p5)
    l5 = line(p5, p6)
    l6 = line(p6, p1)
    
    for c in (l1, l2, l3, l4, l5, l6):
        add_to_sketch(sk, c)
        
    sk.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    return extrude_y([l1, l2, l3, l4, l5, l6], "-Body_Depth*0.5", "Body_Depth*0.5", "F1_Body_Extrude")

def cylinder(origin_z, diameter_rhs, height_rhs, name):
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        dir_vec = Vector3d(0.0, 0.0, 1.0)
        direction = work_part.Directions.CreateDirection(point(0.0, 0.0, origin_z), dir_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Diameter.RightHandSide = diameter_rhs
        builder.Height.RightHandSide = height_rhs
        builder.Axis.Point.SetCoordinates(point(0.0, 0.0, origin_z))
        builder.Axis.Direction = direction
        feat = builder.Commit()
    finally:
        builder.Destroy()
    try:
        feat.SetName(name)
    except Exception:
        pass
    return feat.GetBodies()[0]

def add_neck(body):
    neck_body = cylinder(shoulder_top(), "Neck_Diameter", "Neck_Height", "Neck_Cylinder")
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        builder.Target = body
        builder.ToolBody.Add(neck_body)
        builder.CommitFeature()
    finally:
        builder.Destroy()
    return body

def slot_profile_xz(cx, cz, width, height):
    p1 = point(cx - width*0.5, 0.0, cz - height*0.5)
    p2 = point(cx + width*0.5, 0.0, cz - height*0.5)
    p3 = point(cx + width*0.5, 0.0, cz + height*0.5)
    p4 = point(cx - width*0.5, 0.0, cz + height*0.5)
    
    l1 = line(p1, p2)
    l2 = line(p2, p3)
    l3 = line(p3, p4)
    l4 = line(p4, p1)
    
    return [l1, l2, l3, l4]

def cut_handle_hole(body):
    curves = slot_profile_xz(v("Handle_Offset_X"), v("Handle_Center_Z"), v("Handle_Hole_Width"), v("Handle_Hole_Height"))
    _, body = extrude_y(curves, "-Body_Depth", "Body_Depth", "F2_Handle_Cut", body, subtract=True)
    return body

def edge_points(edge):
    try:
        v1 = edge.GetVertices()[0]
        v2 = edge.GetVertices()[1]
        return (v1, v2)
    except Exception:
        return None

def xyz(p):
    return (p.X, p.Y, p.Z)

def edge_mid(edge):
    pts = edge_points(edge)
    if pts is None:
        return (0.0, 0.0, 0.0)
    p1, p2 = xyz(pts[0]), xyz(pts[1])
    return ((p1[0] + p2[0])*0.5, (p1[1] + p2[1])*0.5, (p1[2] + p2[2])*0.5)

def edge_horizontal(edge):
    pts = edge_points(edge)
    if pts is None:
        return False
    p1, p2 = xyz(pts[0]), xyz(pts[1])
    return abs(p1[2] - p2[2]) < 0.1

def body_bounds(body):
    return (0.0, shoulder_top(), 0.0, body_h())

def live_tallest_body():
    bodies = list(work_part.Bodies)
    if not bodies:
        return None
    tallest = None
    max_z = -1.0e9
    for b in bodies:
        for f in b.GetFaces():
            for loop in f.GetLoops():
                for edge in loop.GetEdges():
                    pts = edge_points(edge)
                    if pts:
                        z = max(pts[0].Z, pts[1].Z)
                        if z > max_z:
                            max_z = z
                            tallest = b
    return tallest

def face_z(face):
    box = face.GetBoundingBox()
    return (box.Min.Z + box.Max.Z) * 0.5

def edge_z_center(edge):
    pts = edge_points(edge)
    if pts is None:
        return 0.0
    return (pts[0].Z + pts[1].Z) * 0.5

def shell_bottle(body):
    builder = work_part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
    try:
        faces_to_remove = []
        target_z = neck_top()
        for f in body.GetFaces():
            if abs(face_z(f) - target_z) < 0.5:
                faces_to_remove.append(f)
                
        collector = work_part.ScCollectors.CreateCollector()
        rules = [work_part.ScRuleFactory.CreateRuleFaceBoundary(f) for f in faces_to_remove]
        collector.ReplaceRules(rules, False)
        
        builder.Thickness.RightHandSide = "Wall_Thickness"
        builder.RemoveFaces.Add(faces_to_remove)
        builder.CommitFeature()
    finally:
        builder.Destroy()
    return body

def blend_edges(body, chooser, radius_rhs, name):
    builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        edges_to_blend = [e for e in body.GetEdges() if chooser(e)]
        if not edges_to_blend:
            return
            
        collector = work_part.ScCollectors.CreateCollector()
        rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in edges_to_blend]
        collector.ReplaceRules(rules, False)
        
        builder.Tolerance = 0.01
        builder.AddChainset(collector, radius_rhs)
        builder.CommitFeature()
    finally:
        builder.Destroy()

def circle_profile(diameter, z, n=72):
    pts = []
    r = diameter * 0.5
    for i in range(n):
        theta = 2.0 * math.pi * i / n
        pts.append(point(r * math.cos(theta), r * math.sin(theta), z))
        
    curves = []
    for i in range(n):
        curves.append(line(pts[i], pts[(i + 1) % n]))
    return curves

def build_cap():
    cap_d = v("Cap_Diameter")
    cap_h = v("Cap_Height")
    
    # 1. Extrude Cap Cylinder
    curves = circle_profile(cap_d, neck_top() + 1.0)
    feat, cap_body = extrude_z(curves, "0.0", "Cap_Height", "F3_Cap_Base")
    
    # 2. Cap Dome Blend
    blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        top_edges = []
        target_z = neck_top() + 1.0 + cap_h
        for e in cap_body.GetEdges():
            pts = edge_points(e)
            if pts and abs(pts[0].Z - target_z) < 0.1 and abs(pts[1].Z - target_z) < 0.1:
                top_edges.append(e)
                
        if top_edges:
            collector = work_part.ScCollectors.CreateCollector()
            rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in top_edges]
            collector.ReplaceRules(rules, False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "Cap_Height * 0.2")
            blend_builder.CommitFeature()
    finally:
        blend_builder.Destroy()
        
    return cap_body

# Feature Creation Sequence
make_expressions()

# Step 1: Body profile extrude
_, body = body_feature()

# Step 2: Edge blend to round vertical corners
blend_edges(
    body,
    lambda e: (
        edge_points(e) is not None
        and not edge_horizontal(e)
        and edge_mid(e)[2] < body_h()
    ),
    "Corner_Radius",
    "EDGE_BLEND_BODY_OVAL"
)

# Step 3: Neck cylinder extrude & Boolean Unite
body = add_neck(body)

# Step 4: Edge blend on the shoulder slants
blend_edges(
    body,
    lambda e: (
        edge_points(e) is not None
        and edge_horizontal(e)
        and abs(edge_mid(e)[2] - body_h()) < 1.0
    ),
    "Shoulder_Height * 0.8",
    "EDGE_BLEND_SHOULDER"
)

# Step 4b: Edge blend at the neck base
def neck_base_chooser(e):
    mid = edge_mid(e)
    if abs(edge_z_center(e) - shoulder_top()) > 0.5:
        return False
    return math.hypot(mid[0], mid[1]) < 25.0

blend_edges(
    body,
    neck_base_chooser,
    "Neck_Fillet",
    "EDGE_BLEND_SHOULDER_NECK"
)

# Step 5: Handle hole slot subtract-cut
body = cut_handle_hole(body)

# Step 6: Handle vertical edges fillet
try:
    handle_cx = v("Handle_Offset_X")
    handle_cz = v("Handle_Center_Z")
    handle_rx = v("Handle_Hole_Width") * 0.5
    handle_rz = v("Handle_Hole_Height") * 0.5
    
    def handle_vertical_chooser(e):
        pts = edge_points(e)
        if pts is None:
            return False
        if abs(pts[0][1] - pts[1][1]) > 5.0:
            return False
        if abs(pts[0][2] - pts[1][2]) < 5.0:
            return False
        mid = edge_mid(e)
        return (
            abs(mid[0] - handle_cx) < handle_rx + 5.0
            and abs(mid[2] - handle_cz) < handle_rz + 5.0
            and abs(mid[1]) < v("Body_Depth") * 0.5 + 2.0
        )

    blend_edges(
        body,
        handle_vertical_chooser,
        "Handle_Fillet",
        "EDGE_BLEND_HANDLE_VERT"
    )
except Exception as exc:
    print("[WARN] Handle edge blend skipped: {}".format(exc))

# Step 7: Bottom edge fillet
try:
    blend_edges(
        body,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2]) < 0.3,
        "Bottom_Fillet",
        "EDGE_BLEND_BOTTOM"
    )
except Exception as exc:
    print("[WARN] Bottom base fillet skipped: {}".format(exc))

# Step 8: Shell bottle removing neck top face
body = shell_bottle(body)

# Step 9: Build Cap (separate solid body)
cap = build_cap()

# Fit View
try:
    work_part.ModelingViews.WorkView.Orient(NXOpen.View.Canned.Isometric, NXOpen.View.ScaleAdjustment.Fit)
except Exception:
    pass

print("[SUCCESS] Persil Detergent Bottle geometry generated successfully.")
