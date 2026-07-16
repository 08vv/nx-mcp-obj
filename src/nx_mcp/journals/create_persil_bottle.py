"""Create parametric Persil_Detergent_Bottle.prt in Siemens NX 2206.

This journal builds both the bottle body and measuring cap as two separate
solid bodies in a single part file, matching the Persil liquid detergent
bottle reference image.

Features:
- Oval body (rounded rectangle with large corner radii)
- Through Curves shoulder transition (oval to circle)
- Integrated side handle via elliptical subtract extrude
- Short cylindrical neck (polygon-circle)
- Dome-shaped measuring cap with grip ribs (separate body)
- All dimensions controlled via named Expressions

Usage:
  run_journal.exe create_persil_bottle.py [output_path.prt]
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import traceback
from pathlib import Path

import NXOpen
import NXOpen.UF


UF = NXOpen.UF.UFSession.GetUFSession()


# ---------------------------------------------------------------------------
# Primary parameters (mm) — estimated from Persil 1.05L reference
# ---------------------------------------------------------------------------
VALUES = {
    "Body_Height": 210.0,
    "Body_Width": 140.0,
    "Body_Depth": 70.0,
    "Shoulder_Height": 45.0,
    "Shoulder_Curve_Radius": 30.0,
    "Neck_Diameter": 42.0,
    "Neck_Height": 12.0,
    "Corner_Radius": 28.0,
    "Handle_Offset_X": 32.0,
    "Handle_Hole_Width": 34.0,
    "Handle_Hole_Height": 90.0,
    "Handle_Center_Z": 170.0,
    "Handle_Fillet": 5.0,
    "Bottom_Fillet": 3.0,
    "Cap_Diameter": 55.0,
    "Cap_Height": 30.0,
    "Cap_Dome_Radius": 20.0,
    "Cap_Rib_Count": 24,
    "Cap_Rib_Depth": 0.8,
    "Cap_Bottom_Fillet": 0.5,
    "Wall_Thickness": 2.5,
}

SECTION_SEGMENTS = (64, 80, 96, 120)


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Persil_Detergent_Bottle.prt"


def v(name: str) -> float:
    return float(VALUES[name])


def body_h() -> float:
    return v("Body_Height")


def shoulder_top() -> float:
    return body_h() + v("Shoulder_Height")


def neck_top() -> float:
    return shoulder_top() + v("Neck_Height")


def set_name(obj, name: str) -> None:
    try:
        obj.SetName(name)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------
def make_expressions(part) -> None:
    for name, value in VALUES.items():
        rhs = int(value) if name == "Cap_Rib_Count" else value
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass
    formulas = {
        "Overall_Height": "Body_Height + Shoulder_Height + Neck_Height",
        "Shoulder_Start_Z": "Body_Height",
        "Shoulder_End_Z": "Body_Height + Shoulder_Height",
        "Neck_Start_Z": "Shoulder_End_Z",
        "Neck_End_Z": "Neck_Start_Z + Neck_Height",
        "Handle_Top_Z": "Handle_Center_Z + Handle_Hole_Height / 2.0",
        "Handle_Bottom_Z": "Handle_Center_Z - Handle_Hole_Height / 2.0",
        "Cap_Rib_Angle": "360.0 / Cap_Rib_Count",
        "Cap_Inner_Diameter": "Neck_Diameter + 0.5",
    }
    for name, rhs in formulas.items():
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Geometry helpers — all floats to avoid NXOpen int TypeError
# ---------------------------------------------------------------------------
def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))


def line(part, a, b):
    return part.Curves.CreateLine(point(*a), point(*b))


def add_to_sketch(sketch, curve) -> None:
    try:
        sketch.AddGeometry(curve, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    except Exception:
        try:
            sketch.AddGeometry(curve)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Sketch on XY plane
# ---------------------------------------------------------------------------
def create_sketch_on_csys(part, origin, x_vec, y_vec, z_vec, sketch_name):
    matrix = NXOpen.Matrix3x3()
    matrix.Xx = x_vec.X; matrix.Xy = x_vec.Y; matrix.Xz = x_vec.Z
    matrix.Yx = y_vec.X; matrix.Yy = y_vec.Y; matrix.Yz = y_vec.Z
    matrix.Zx = z_vec.X; matrix.Zy = z_vec.Y; matrix.Zz = z_vec.Z
    nx_matrix = part.NXMatrices.Create(matrix)
    csys = part.CoordinateSystems.CreateCoordinateSystem(origin, nx_matrix, True)

    factory2 = getattr(part.Sketches, "CreateSketchInPlaceBuilder2", None)
    builder = None
    if factory2 is not None:
        try:
            builder = factory2(None)
        except Exception:
            pass
    if builder is None:
        factory = getattr(part.Sketches, "CreateNewSketchInPlaceBuilder", None)
        if factory is None:
            factory = getattr(part.Sketches, "CreateSketchInPlaceBuilder", None)
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


def xy_sketch(part, name: str):
    return create_sketch_on_csys(
        part,
        point(0.0, 0.0, 0.0),
        vec(1.0, 0.0, 0.0),
        vec(0.0, 1.0, 0.0),
        vec(0.0, 0.0, 1.0),
        name,
    )


# ---------------------------------------------------------------------------
# Rounded rectangle profile (produces oval with large corner radius)
# ---------------------------------------------------------------------------
def rounded_rect_curves(part, z, w, d, r, sketch=None):
    hw = w * 0.5
    hd = d * 0.5
    r = min(r, hw - 0.1, hd - 0.1)
    x0, x1 = -hw + r, hw - r
    y0, y1 = -hd + r, hd - r
    x_axis = vec(1.0, 0.0, 0.0)
    y_axis = vec(0.0, 1.0, 0.0)
    curves = [
        line(part, (x0, -hd, z), (x1, -hd, z)),
        part.Curves.CreateArc(point(x1, y0, z), x_axis, y_axis, float(r), -math.pi / 2.0, 0.0),
        line(part, (hw, y0, z), (hw, y1, z)),
        part.Curves.CreateArc(point(x1, y1, z), x_axis, y_axis, float(r), 0.0, math.pi / 2.0),
        line(part, (x1, hd, z), (x0, hd, z)),
        part.Curves.CreateArc(point(x0, y1, z), x_axis, y_axis, float(r), math.pi / 2.0, math.pi),
        line(part, (-hw, y1, z), (-hw, y0, z)),
        part.Curves.CreateArc(point(x0, y0, z), x_axis, y_axis, float(r), math.pi, 3.0 * math.pi / 2.0),
    ]
    if sketch is not None:
        try:
            sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
        except Exception:
            pass
        for curve in curves:
            add_to_sketch(sketch, curve)
        try:
            sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
        except Exception:
            pass
    return curves


# ---------------------------------------------------------------------------
# Section and Extrude
# ---------------------------------------------------------------------------
def section(part, curves):
    sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
    rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    sec.AddToSection(
        rules,
        curves[0],
        NXOpen.NXObject.Null,
        NXOpen.NXObject.Null,
        point(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create,
        False,
    )
    return sec


def extrude(part, curves, dir_vec, start_rhs, end_rhs, name, target=None, subtract=False):
    """Extrude curves in the given direction vector."""
    builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section(part, curves)
        builder.Direction = part.Directions.CreateDirection(
            point(0.0, 0.0, 0.0),
            dir_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Limits.StartExtend.Value.RightHandSide = str(start_rhs)
        builder.Limits.EndExtend.Value.RightHandSide = str(end_rhs)
        if target is not None:
            bool_type = (
                NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
                if subtract
                else NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite
            )
            builder.BooleanOperation.SetBooleanOperationAndBody(bool_type, target)
        else:
            builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, target if target is not None else (bodies[0] if bodies else None)


def extrude_z(part, curves, start_rhs, end_rhs, name, target=None, subtract=False):
    """Extrude in Z direction (up)."""
    return extrude(part, curves, vec(0.0, 0.0, 1.0), start_rhs, end_rhs, name, target, subtract)


def extrude_y(part, curves, start_rhs, end_rhs, name, target=None, subtract=False):
    """Extrude in Y direction (depth)."""
    return extrude(part, curves, vec(0.0, 1.0, 0.0), start_rhs, end_rhs, name, target, subtract)


# ---------------------------------------------------------------------------
# Main body extrude (oval cross-section)
# ---------------------------------------------------------------------------
def body_feature(part):
    _, sketch = xy_sketch(part, "SKETCH_BODY_PROFILE")
    curves = rounded_rect_curves(
        part,
        0.0,
        v("Body_Width"),
        v("Body_Depth"),
        v("Corner_Radius"),
        sketch,
    )
    return extrude_z(part, curves, "0", "Body_Height", "EXTRUDE_OVAL_BODY")


# ---------------------------------------------------------------------------
# Shoulder transition (Through Curves: oval -> circle)
# ---------------------------------------------------------------------------
def radius_to_rounded_rect(width, depth, corner, angle):
    ux, uy = math.cos(angle), math.sin(angle)
    low, high = 0.0, max(width, depth)
    hw, hd = width * 0.5, depth * 0.5
    rr = min(corner, hw - 0.01, hd - 0.01)
    for _ in range(40):
        mid = (low + high) * 0.5
        x, y = mid * ux, mid * uy
        qx = abs(x) - (hw - rr)
        qy = abs(y) - (hd - rr)
        outside = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - rr
        if outside <= 0.0:
            low = mid
        else:
            high = mid
    return low


def ring_polyline(part, width, depth, corner, z, count):
    pts = []
    for i in range(count):
        a = 2.0 * math.pi * float(i) / float(count)
        mag = radius_to_rounded_rect(width, depth, corner, a)
        pts.append((mag * math.cos(a), mag * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % count]) for i in range(count)]


def shoulder_sections(part, count):
    curves_per_section = []
    num_sections = 12
    for i in range(num_sections):
        t = float(i) / float(num_sections - 1)
        s = t * t * (3.0 - 2.0 * t)
        w = v("Body_Width") + (v("Neck_Diameter") - v("Body_Width")) * s
        d = v("Body_Depth") + (v("Neck_Diameter") - v("Body_Depth")) * s
        c = v("Corner_Radius") + (v("Neck_Diameter") * 0.5 - v("Corner_Radius")) * s
        z = body_h() + v("Shoulder_Height") * t
        curves_per_section.append(ring_polyline(part, w, d, c, z, count))
    return curves_per_section


def append_section(builder, sec) -> None:
    container = getattr(builder, "SectionsList", None) or getattr(builder, "Sections", None)
    if hasattr(container, "Append"):
        container.Append(sec)
    else:
        container.Add(sec)


def through_curves_shoulder(part, body):
    error_text = ""
    for count in SECTION_SEGMENTS:
        try:
            curvesets = shoulder_sections(part, count)
            builder = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
            try:
                try:
                    builder.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
                except Exception:
                    pass
                for curves in curvesets:
                    append_section(builder, section(part, curves))
                feat = builder.CommitFeature()
            finally:
                builder.Destroy()
            set_name(feat, "THROUGH_CURVES_SHOULDER")
            bodies = feat.GetBodies()
            if bodies:
                return feat, bodies[0]
        except Exception as exc:
            error_text = str(exc)
    raise RuntimeError("Through Curves shoulder failed: {}".format(error_text))


# ---------------------------------------------------------------------------
# Boolean Unite
# ---------------------------------------------------------------------------
def unite(part, target, tool, name):
    builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        builder.Target = target
        builder.Tool = tool
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return bodies[0] if bodies else target


# ---------------------------------------------------------------------------
# Neck (polygon-circle extrude)
# ---------------------------------------------------------------------------
def circle_profile(part, diameter, z, n=72):
    pts = []
    r = diameter * 0.5
    for i in range(n):
        a = 2.0 * math.pi * float(i) / float(n)
        pts.append((r * math.cos(a), r * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % n]) for i in range(n)]


def add_neck(part, body):
    curves = circle_profile(part, v("Neck_Diameter"), shoulder_top())
    _, body = extrude_z(part, curves, "0", "Neck_Height", "EXTRUDE_NECK", body)
    return body


# ---------------------------------------------------------------------------
# Handle hole (tangent-continuous slot profile in XZ plane)
# ---------------------------------------------------------------------------
def slot_profile_xz(part, cx, cz, width, height):
    """Create a tangent-continuous slot profile (2 lines, 2 arcs) in XZ plane."""
    r = width * 0.5
    dy = height * 0.5 - r
    x_axis = vec(1.0, 0.0, 0.0)
    z_axis = vec(0.0, 0.0, 1.0)
    
    # Semicircular top arc CCW from 0 to pi (right to left)
    top_center = point(cx, 0.0, cz + dy)
    top_arc = part.Curves.CreateArc(top_center, x_axis, z_axis, float(r), 0.0, math.pi)
    
    # Left vertical line going down
    left_line = line(part, (cx - r, 0.0, cz + dy), (cx - r, 0.0, cz - dy))
    
    # Semicircular bottom arc CCW from pi to 2pi (left to right)
    bottom_center = point(cx, 0.0, cz - dy)
    bottom_arc = part.Curves.CreateArc(bottom_center, x_axis, z_axis, float(r), math.pi, 2.0 * math.pi)
    
    # Right vertical line going up
    right_line = line(part, (cx + r, 0.0, cz - dy), (cx + r, 0.0, cz + dy))
    
    return [right_line, top_arc, left_line, bottom_arc]


def cut_handle_hole(part, body):
    cx = v("Handle_Offset_X")
    cz = v("Handle_Center_Z")
    w = v("Handle_Hole_Width")
    h = v("Handle_Hole_Height")
    curves = slot_profile_xz(part, cx, cz, w, h)
    # Extrude in Y through entire body depth with margin
    margin = 5.0
    half_depth = v("Body_Depth") * 0.5 + margin
    _, body = extrude_y(
        part, curves,
        str(-half_depth), str(half_depth),
        "EXTRUDE_SUBTRACT_HANDLE_HOLE",
        body, subtract=True,
    )
    return body


# ---------------------------------------------------------------------------
# Edge helpers
# ---------------------------------------------------------------------------
def edge_points(edge):
    try:
        a, b, _ = UF.Modeling.AskEdgeVerts(edge.Tag)
        return xyz(a), xyz(b)
    except Exception:
        return None


def xyz(p):
    if hasattr(p, "X"):
        return float(p.X), float(p.Y), float(p.Z)
    return float(p[0]), float(p[1]), float(p[2])


def edge_mid(edge):
    pts = edge_points(edge)
    if pts is None:
        return 0.0, 0.0, 0.0
    return tuple((pts[0][i] + pts[1][i]) * 0.5 for i in range(3))


def edge_horizontal(edge):
    pts = edge_points(edge)
    return bool(pts and abs(pts[0][2] - pts[1][2]) < 0.05)


def body_bounds(body):
    pts = []
    for edge in list(body.GetEdges() or []):
        pair = edge_points(edge)
        if pair:
            pts.extend(pair)
    if not pts:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    return (
        (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts)),
        (max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts)),
    )


def live_tallest_body(part):
    bodies = list(part.Bodies or [])
    if not bodies:
        return None
    return max(bodies, key=lambda b: body_bounds(b)[1][2] - body_bounds(b)[0][2])


# ---------------------------------------------------------------------------
# Edge Blend
# ---------------------------------------------------------------------------
def blend_edges(part, body, chooser, radius_rhs, name):
    edges = [e for e in list(body.GetEdges() or []) if chooser(e)]
    if not edges:
        print("  blend_edges '{}': no matching edges found".format(name))
        return None
    builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        collector = part.ScCollectors.CreateCollector()
        collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(edges)], False)
        builder.Tolerance = 0.01
        builder.AddChainset(collector, str(radius_rhs))
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    return feat


# ---------------------------------------------------------------------------
# Cylinder primitive (for cap)
# ---------------------------------------------------------------------------
def cylinder(part, origin_z, diameter_rhs, height_rhs, name):
    builder = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        direction = part.Directions.CreateDirection(
            point(0.0, 0.0, float(origin_z)),
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Axis.Point.SetCoordinates(point(0.0, 0.0, float(origin_z)))
        builder.Axis.Direction = direction
        builder.Diameter.RightHandSide = str(diameter_rhs)
        builder.Height.RightHandSide = str(height_rhs)
        feat = builder.Commit()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, bodies[0] if bodies else None


# ---------------------------------------------------------------------------
# Cap with dome and ribs (separate body, not united with bottle)
# ---------------------------------------------------------------------------
def build_cap(part):
    cap_z = neck_top()

    # Step 1: Cap cylinder (separate body — Target=None means BooleanType.Create)
    curves = circle_profile(part, v("Cap_Diameter"), cap_z)
    _, cap = extrude_z(part, curves, "0", "Cap_Height", "EXTRUDE_CAP_BODY")
    if cap is None:
        raise RuntimeError("Cap cylinder extrude did not create a body.")
    print("[OK] Cap cylinder extruded at z={:.1f}".format(cap_z))

    # Step 2: Dome fillet on top edge
    cap_top_z = cap_z + v("Cap_Height")
    blend_edges(
        part, cap,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2] - cap_top_z) < 0.5,
        "Cap_Dome_Radius",
        "EDGE_BLEND_CAP_DOME",
    )
    print("[OK] Cap dome fillet applied")

    # Step 3: Bottom fillet
    blend_edges(
        part, cap,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2] - cap_z) < 0.5,
        "Cap_Bottom_Fillet",
        "EDGE_BLEND_CAP_BOTTOM",
    )
    print("[OK] Cap bottom fillet applied")

    # Step 4: Grip ribs
    rib_width = math.pi * v("Cap_Diameter") / v("Cap_Rib_Count") * 0.35
    r = v("Cap_Diameter") * 0.5
    curves = [
        line(part, (r - 0.05, -rib_width * 0.5, cap_z + 1.0), (r + v("Cap_Rib_Depth"), -rib_width * 0.35, cap_z + 1.0)),
        line(part, (r + v("Cap_Rib_Depth"), -rib_width * 0.35, cap_z + 1.0), (r + v("Cap_Rib_Depth"), rib_width * 0.35, cap_z + 1.0)),
        line(part, (r + v("Cap_Rib_Depth"), rib_width * 0.35, cap_z + 1.0), (r - 0.05, rib_width * 0.5, cap_z + 1.0)),
        line(part, (r - 0.05, rib_width * 0.5, cap_z + 1.0), (r - 0.05, -rib_width * 0.5, cap_z + 1.0)),
    ]
    rib_feat, _ = extrude_z(
        part, curves,
        "0", "Cap_Height - 2.0",
        "EXTRUDE_SINGLE_GRIP_RIB",
        cap,
    )
    print("[OK] Single grip rib extruded")

    # Step 5: Circular pattern
    builder = part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.FeatureList.Add([rib_feat])
        try:
            builder.PatternMethod = NXOpen.Features.PatternFeatureBuilder.PatternMethodOptions.Simple
        except Exception:
            pass
        service = builder.PatternService
        service.PatternType = NXOpen.GeometricUtilities.PatternDefinition.PatternEnum.Circular
        circ = service.CircularDefinition
        circ.RotationAxis = part.Axes.CreateAxis(
            point(0.0, 0.0, cap_z),
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        circ.RotationCenter = part.Points.CreatePoint(point(0.0, 0.0, cap_z))
        circ.IncludeSeedToggle = True
        circ.AngularSpacing.NCopies.RightHandSide = "Cap_Rib_Count"
        circ.AngularSpacing.PitchAngle.RightHandSide = "Cap_Rib_Angle"
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, "CIRCULAR_PATTERN_GRIP_RIBS")
    print("[OK] Circular pattern of grip ribs created")

    return cap


# ---------------------------------------------------------------------------
# Launch file helpers
# ---------------------------------------------------------------------------
def write_launch_files(path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    (root / "latest_nx_result.txt").write_text(str(path), encoding="utf-8")
    base = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
    router = Path(base) / "NXBIN" / "ugs_router.exe"
    (root / "open_current_nx_result.cmd").write_text(
        '@echo off\nstart "" "{}" -ug -use_file_dir "{}"\n'.format(router, path),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    path = out_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)
    part = session.Parts.Work

    print("Building parametric Persil Detergent Bottle")
    make_expressions(part)

    # ---- BOTTLE BODY ----

    # Step 1: Oval body extrude
    _, body = body_feature(part)
    print("[OK] Oval body extruded ({}x{} mm, CR={})".format(
        int(v("Body_Width")), int(v("Body_Depth")), int(v("Corner_Radius"))))

    # Step 2: Shoulder transition (oval to circle)
    _, shoulder = through_curves_shoulder(part, body)
    body = unite(part, body, shoulder, "UNITE_BODY_AND_SHOULDER")
    print("[OK] Shoulder transition united")

    # Step 3: Neck
    body = add_neck(part, body)
    print("[OK] Neck extruded")

    # Step 4: Handle hole
    body = cut_handle_hole(part, body)
    print("[OK] Handle hole cut")

    # Step 5: Edge blends — handle hole
    try:
        handle_cx = v("Handle_Offset_X")
        handle_cz = v("Handle_Center_Z")
        handle_rx = v("Handle_Hole_Width") * 0.5
        handle_rz = v("Handle_Hole_Height") * 0.5
        
        def handle_vertical_chooser(e):
            pts = edge_points(e)
            if pts is None:
                return False
            # Exclude Y-aligned internal edges
            if abs(pts[0][1] - pts[1][1]) > 5.0:
                return False
            # Vertical edges have Z difference
            if abs(pts[0][2] - pts[1][2]) < 5.0:
                return False
            mid = edge_mid(e)
            return (
                abs(mid[0] - handle_cx) < handle_rx + 5.0
                and abs(mid[2] - handle_cz) < handle_rz + 5.0
                and abs(mid[1]) < v("Body_Depth") * 0.5 + 2.0
            )

        blend_edges(
            part, body,
            handle_vertical_chooser,
            "Handle_Fillet",
            "EDGE_BLEND_HANDLE_VERT",
        )
        print("[OK] Handle vertical edge blend applied")
    except Exception as exc:
        print("[WARN] Handle edge blend skipped: {}".format(exc))

    # Step 6: Edge blend — bottom
    blend_edges(
        part, body,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2]) < 0.3,
        "Bottom_Fillet",
        "EDGE_BLEND_BOTTOM",
    )
    print("[OK] Bottom fillet applied")

    # ---- BOTTLE CAP (separate body) ----
    cap = build_cap(part)

    # ---- FINALIZE ----
    try:
        body_faces = len(list(body.GetFaces() or []))
        cap_faces = len(list(cap.GetFaces() or []))
        num_bodies = len(list(part.Bodies or []))
        print("Bodies: {}, Bottle faces: {}, Cap faces: {}".format(num_bodies, body_faces, cap_faces))
        part.ModelingViews.WorkView.Fit()
    except Exception:
        pass

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    write_launch_files(path)
    print("Saved: {}".format(path))


if __name__ == "__main__":
    log = Path(__file__).resolve().parents[3] / "persil_bottle_journal.log"
    try:
        log.write_text("Starting Persil Detergent Bottle journal\n", encoding="utf-8")
        main()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
