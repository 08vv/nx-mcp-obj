"""Create a clean, production-ready, parametric Sunlight_Detergent_Bottle.prt in Siemens NX 2206.

This journal builds the bottle body and cap as two separate solid bodies
matching the reference image proportions and using the requested feature tree:
Sketch -> Extrude -> Draft -> Through Curves -> Shell -> Handle Cut -> Edge Blends -> Neck Extrude -> Cap Revolve -> Circular Pattern (Grip Ribs).

Usage:
  run_journal.exe create_bottle_parts.py [output_path.prt]
"""

from __future__ import annotations

import math
import os
import sys
import traceback
from pathlib import Path

import NXOpen
import NXOpen.UF
from examples._common import set_name, unite, vec

UF = NXOpen.UF.UFSession.GetUFSession()

# ---------------------------------------------------------------------------
# Default parameter values (mm)
# ---------------------------------------------------------------------------
VALUES = {
    "Body_Height": 150.0,
    "Body_Width": 140.0,
    "Body_Depth": 70.0,
    "Shoulder_Height": 70.0,
    "Shoulder_Blend_Radius": 2.0,
    "Neck_Diameter": 42.0,
    "Neck_Height": 15.0,
    "Handle_Outer_Height": 120.0,
    "Handle_Outer_Width": 50.0,
    "Handle_Inner_Height": 80.0,
    "Handle_Inner_Width": 30.0,
    "Handle_Depth": 35.0,
    "Cap_Diameter": 48.0,
    "Cap_Height": 25.0,
    "Grip_Rib_Count": 30,
    "Grip_Rib_Depth": 0.6,
    "Grip_Rib_Width": 1.2,
    "Corner_Radius": 25.0,
    "Bottom_Blend_Radius": 2.0,
    "Wall_Thickness": 2.5,
    "Draft_Angle": 2.0,
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Sunlight_Detergent_Bottle.prt"


def v(name: str) -> float:
    return float(VALUES[name])


def body_h() -> float:
    return v("Body_Height")




# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------
def make_expressions(part) -> None:
    for name, value in VALUES.items():
        rhs = int(value) if name == "Grip_Rib_Count" else value
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass
    formulas = {
        "Overall_Height": "Body_Height + Shoulder_Height + Neck_Height",
        "Overall_Width": "Body_Width",
        "Overall_Depth": "Body_Depth",
    }
    for name, rhs in formulas.items():
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))




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
# Coordinate System Sketches
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


def xy_sketch(part, name: str, z=0.0):
    """Create sketch on the XY plane at a specific Z height."""
    return create_sketch_on_csys(
        part,
        point(0.0, 0.0, z),
        vec(1.0, 0.0, 0.0),
        vec(0.0, 1.0, 0.0),
        vec(0.0, 0.0, 1.0),
        name,
    )


def xz_sketch(part, name: str):
    """Create sketch on the XZ plane (Y=0)."""
    return create_sketch_on_csys(
        part,
        point(0.0, 0.0, 0.0),
        vec(1.0, 0.0, 0.0),
        vec(0.0, 0.0, 1.0),
        vec(0.0, -1.0, 0.0),
        name,
    )


# ---------------------------------------------------------------------------
# Section and Extrude/Revolve Helpers
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


def extrude(part, curves, dir_vec, start_rhs, end_rhs, name, target=None, subtract=False, draft_angle_rhs=None):
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

        # Apply Draft if requested
        if draft_angle_rhs is not None:
            try:
                draft_settings = builder.DraftSettings
                draft_settings.DraftOption = NXOpen.GeometricUtilities.FeatureDraft.Types.FromStartLimit
                draft_settings.Angle.RightHandSide = str(draft_angle_rhs)
            except Exception:
                try:
                    draft = builder.Draft
                    draft.DraftOption = NXOpen.GeometricUtilities.SimpleDraftSimpleDraftType.SimpleFromStart
                    draft.FrontDraftAngle.RightHandSide = str(draft_angle_rhs)
                except Exception:
                    pass

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


def extrude_y(part, curves, start_rhs, end_rhs, name, target=None, subtract=False):
    return extrude(part, curves, vec(0.0, 1.0, 0.0), start_rhs, end_rhs, name, target, subtract)


def extrude_z(part, curves, start_rhs, end_rhs, name, target=None, subtract=False, draft_angle_rhs=None):
    return extrude(part, curves, vec(0.0, 0.0, 1.0), start_rhs, end_rhs, name, target, subtract, draft_angle_rhs)


def revolve_axis(part, curves, start_angle, end_angle, axis_point, axis_dir, name):
    tags = [curve.Tag for curve in curves]
    features, number_of_features = UF.Modl.CreateRevolution(
        tags,
        len(tags),
        None,
        [str(start_angle), str(end_angle)],
        ["0", "0"],
        axis_point,
        False,
        True,
        axis_point,
        axis_dir,
        NXOpen.UF.Modl.FeatureSigns.NULLSIGN,
    )
    if not features or number_of_features < 1:
        raise RuntimeError("Revolve did not create a feature")
    feature = NXOpen.TaggedObjectManager().GetTaggedObject(features[0])
    set_name(feature, name)
    bodies = feature.GetBodies()
    return feature, bodies[0] if bodies else None


# ---------------------------------------------------------------------------
# Symmetrical/Asymmetrical Profiles
# ---------------------------------------------------------------------------
def rounded_rect_curves(part, z, w, d, r, cx=0.0):
    hw = w * 0.5
    hd = d * 0.5
    r = min(r, hw - 0.1, hd - 0.1)
    x0, x1 = -hw + r + cx, hw - r + cx
    y0, y1 = -hd + r, hd - r
    x_axis = vec(1.0, 0.0, 0.0)
    y_axis = vec(0.0, 1.0, 0.0)
    return [
        line(part, (x0, -hd, z), (x1, -hd, z)),
        part.Curves.CreateArc(point(x1, y0, z), x_axis, y_axis, float(r), -math.pi / 2.0, 0.0),
        line(part, (hw + cx, y0, z), (hw + cx, y1, z)),
        part.Curves.CreateArc(point(x1, y1, z), x_axis, y_axis, float(r), 0.0, math.pi / 2.0),
        line(part, (x1, hd, z), (x0, hd, z)),
        part.Curves.CreateArc(point(x0, y1, z), x_axis, y_axis, float(r), math.pi / 2.0, math.pi),
        line(part, (-hw + cx, y1, z), (-hw + cx, y0, z)),
        part.Curves.CreateArc(point(x0, y0, z), x_axis, y_axis, float(r), math.pi, 3.0 * math.pi / 2.0),
    ]


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


def ring_polyline(part, wl, wr, depth, corner, z, count=64):
    w = wl + wr
    cx = (wr - wl) * 0.5
    pts = []
    for i in range(count):
        a = 2.0 * math.pi * float(i) / float(count)
        mag = radius_to_rounded_rect(w, depth, corner, a)
        pts.append((mag * math.cos(a) + cx, mag * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % count]) for i in range(count)]


def slot_profile_xz(part, cx, cz, width, height):
    r = width * 0.5
    dy = height * 0.5 - r
    x_axis = vec(1.0, 0.0, 0.0)
    z_axis = vec(0.0, 0.0, 1.0)
    return [
        line(part, (cx + r, 0.0, cz - dy), (cx + r, 0.0, cz + dy)),
        part.Curves.CreateArc(point(cx, 0.0, cz + dy), x_axis, z_axis, float(r), 0.0, math.pi),
        line(part, (cx - r, 0.0, cz + dy), (cx - r, 0.0, cz - dy)),
        part.Curves.CreateArc(point(cx, 0.0, cz - dy), x_axis, z_axis, float(r), math.pi, 2.0 * math.pi),
    ]


# ---------------------------------------------------------------------------
# Shoulder transition (Through Curves: asymmetric rectangle -> circle)
# ---------------------------------------------------------------------------
def shoulder_sections(part, w_start, d_start, r_start):
    curves_per_section = []
    w_end = v("Neck_Diameter")
    d_end = v("Neck_Diameter")
    r_end = v("Neck_Diameter") * 0.5 - 0.01

    for i in range(10):
        t = i / 9.0
        # Left side tapers quickly (shorter, rounded shoulder)
        wl = w_end * 0.5 + (w_start * 0.5 - w_end * 0.5) * ((1.0 - t) ** 1.5)
        # Right side stays wider (extends naturally to handle)
        wr = w_end * 0.5 + (w_start * 0.5 - w_end * 0.5) * math.sqrt(1.0 - t)
        
        d = d_end + (d_start - d_end) * (1.0 - t)
        r = r_end + (r_start - r_end) * (1.0 - t)
        z = body_h() + v("Shoulder_Height") * t
        curves_per_section.append(ring_polyline(part, wl, wr, d, r, z, count=64))
    return curves_per_section


def append_section(builder, sec) -> None:
    container = getattr(builder, "SectionsList", None) or getattr(builder, "Sections", None)
    if hasattr(container, "Append"):
        container.Append(sec)
    else:
        container.Add(sec)


def through_curves_shoulder(part, w_start, d_start, r_start):
    curvesets = shoulder_sections(part, w_start, d_start, r_start)
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
    return feat, bodies[0] if bodies else None




# ---------------------------------------------------------------------------
# Edge and Face Utilities for Selection
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


def face_z(face):
    try:
        face_type, origin, direction, bbox, radius, flag1, flag2 = UF.Modeling.AskFaceData(face.Tag)
        return float(origin[2])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Shell uniform wall hollowing
# ---------------------------------------------------------------------------
def shell_bottle(part, body):
    body = live_tallest_body(part) or body
    faces = []
    target_z = body_h() + v("Shoulder_Height")

    for face in list(body.GetFaces() or []):
        z = face_z(face)
        if z is not None and abs(z - target_z) < 0.5:
            faces.append(face)
            break

    if not faces:
        candidates = []
        for face in list(body.GetFaces() or []):
            z = face_z(face)
            if z is not None:
                candidates.append((z, face))
        if candidates:
            candidates.sort(key=lambda t: t[0], reverse=True)
            faces.append(candidates[0][1])

    if not faces:
        raise RuntimeError("Could not identify the neck opening face for Shell.")

    builder = part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Body = body
        builder.DefaultThickness.RightHandSide = "Wall_Thickness"
        builder.Tolerance = 0.01
        collector = part.ScCollectors.CreateCollector()
        collector.ReplaceRules([part.ScRuleFactory.CreateRuleFaceDumb(faces)], False)
        builder.RemovedFacesCollector = collector
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, "SHELL_BOTTLE_BODY")
    return live_tallest_body(part) or body


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

    print("Building parametric Sunlight Detergent Bottle model")
    make_expressions(part)

    # 1. Base footprint sketch & extrude with draft
    _, sketch_body = xy_sketch(part, "SKETCH_BODY_FOOTPRINT", 0.0)
    curves_body = rounded_rect_curves(
        part, 0.0, v("Body_Width"), v("Body_Depth"), v("Corner_Radius")
    )
    for c in curves_body:
        add_to_sketch(sketch_body, c)

    # Extrude base profile with inward draft
    _, body = extrude_z(
        part, curves_body, "0.0", "Body_Height", "EXTRUDE_BODY",
        draft_angle_rhs="-Draft_Angle"
    )
    print("[OK] Base rectangular body extruded with inward draft")

    # Calculate actual body bounds at Z = Body_Height after draft
    draft_rad = math.radians(v("Draft_Angle"))
    w_start = v("Body_Width") - 2.0 * v("Body_Height") * math.tan(draft_rad)
    d_start = v("Body_Depth") - 2.0 * v("Body_Height") * math.tan(draft_rad)
    r_start = v("Corner_Radius") - v("Body_Height") * math.tan(draft_rad)

    # 2. Shoulder transition (Through Curves: asymmetric rectangle to circle)
    _, shoulder = through_curves_shoulder(part, w_start, d_start, r_start)
    body = unite(part, body, shoulder, "UNITE_BODY_AND_SHOULDER")
    print("[OK] Asymmetric shoulder Through Curves united")

    # 3. Base Recess (recessed bottom cut of 2mm)
    rw = w_start - 12.0
    rd = d_start - 12.0
    rc = r_start - 4.0
    curves_recess = rounded_rect_curves(part, 0.0, rw, rd, rc)
    _, body = extrude(
        part, curves_recess, vec(0.0, 0.0, 1.0), "-1.0", "2.0",
        "EXTRUDE_BASE_RECESS", target=body, subtract=True
    )
    print("[OK] Recessed bottom subtracted")

    # 4. Shell hollowing (removing top neck opening face)
    body = shell_bottle(part, body)
    print("[OK] Bottle body shelled successfully")

    # 5. Handle Opening Cutout
    # Formula for handle opening X position:
    handle_cx = (v("Body_Width") * 0.5) - (v("Handle_Outer_Width") - v("Handle_Inner_Width") * 0.5)
    handle_cz = v("Body_Height") + v("Shoulder_Height") * 0.4
    
    handle_curves = slot_profile_xz(part, handle_cx, handle_cz, v("Handle_Inner_Width"), v("Handle_Inner_Height"))
    _, body = extrude_y(
        part, handle_curves,
        str(-(v("Body_Depth") * 0.5 + 5.0)), str(v("Body_Depth") * 0.5 + 5.0),
        "EXTRUDE_SUBTRACT_HANDLE_HOLE",
        body, subtract=True,
    )
    print("[OK] Handle opening slot cut out")

    # 6. Edge Blends
    # Bottom base fillet
    try:
        blend_edges(
            part, body,
            lambda e: edge_horizontal(e) and abs(edge_mid(e)[2]) < 0.5,
            "Bottom_Blend_Radius",
            "EDGE_BLEND_BOTTOM",
        )
        print("[OK] Bottom base fillet applied")
    except Exception as exc:
        print("[WARN] Bottom base fillet skipped: {}".format(exc))
    
    # Handle cutout loop fillet for comfort
    try:
        def handle_edge_chooser(e):
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
                abs(mid[0] - handle_cx) < v("Handle_Inner_Width") * 0.5 + 5.0
                and abs(mid[2] - handle_cz) < v("Handle_Inner_Height") * 0.5 + 5.0
            )

        blend_edges(
            part, body,
            handle_edge_chooser,
            "Wall_Thickness * 0.8",
            "EDGE_BLEND_HANDLE",
        )
        print("[OK] Handle vertical edge blend applied")
    except Exception as exc:
        print("[WARN] Handle edge blend skipped: {}".format(exc))
    
    # Left shoulder soft blending
    try:
        blend_edges(
            part, body,
            lambda e: edge_horizontal(e) and abs(edge_mid(e)[2] - body_h()) < 1.0 and edge_mid(e)[0] < 0,
            "Shoulder_Blend_Radius",
            "EDGE_BLEND_LEFT_SHOULDER",
        )
        print("[OK] Left shoulder blend applied")
    except Exception as exc:
        print("[WARN] Left shoulder blend skipped: {}".format(exc))
    print("[OK] Body edge blends completed")

    # 7. Neck Extrude (Hollow tube)
    # Circle profile for neck
    neck_z = body_h() + v("Shoulder_Height")
    neck_outer = rounded_rect_curves(part, neck_z, v("Neck_Diameter"), v("Neck_Diameter"), v("Neck_Diameter") * 0.5 - 0.01)
    
    # We extrude neck with thickness by subtract or double circle profile
    _, neck_solid = extrude_z(
        part, neck_outer, "0.0", "Neck_Height", "EXTRUDE_NECK_OUTER",
        target=body
    )
    
    # Subtract internal opening to complete hollow neck
    neck_inner_dia = v("Neck_Diameter") - 2.0 * v("Wall_Thickness")
    neck_inner = rounded_rect_curves(part, neck_z - 1.0, neck_inner_dia, neck_inner_dia, neck_inner_dia * 0.5 - 0.01)
    _, body = extrude_z(
        part, neck_inner, "0.0", "Neck_Height + 2.0", "EXTRUDE_NECK_HOLLOW",
        target=body, subtract=True
    )
    
    # Rename body to Bottle_Body
    body.SetName("Bottle_Body")
    print("[OK] Hollow Neck extruded and united to Bottle_Body")

    # 8. Cap Revolve (Separate Body)
    cap_z = neck_z
    # Cap profile in XZ: a closed rectangle from X=0 to X=Cap_Diameter/2
    cap_r = v("Cap_Diameter") * 0.5
    cap_w = cap_r
    cap_h = v("Cap_Height")
    
    cap_profile = [
        line(part, (0.0, 0.0, cap_z), (cap_w, 0.0, cap_z)),
        line(part, (cap_w, 0.0, cap_z), (cap_w, 0.0, cap_z + cap_h)),
        line(part, (cap_w, 0.0, cap_z + cap_h), (0.0, 0.0, cap_z + cap_h)),
        line(part, (0.0, 0.0, cap_z + cap_h), (0.0, 0.0, cap_z)),
    ]
    
    _, cap = revolve_axis(
        part, cap_profile, "0", "360",
        [0.0, 0.0, 0.0], [0.0, 0.0, 1.0],
        "REVOLVE_CAP"
    )
    cap.SetName("Bottle_Cap")
    print("[OK] Cap body revolved concentrically")

    # Soft round the top upper edges of the cap
    cap_top_z = cap_z + cap_h
    cap_top_edges = []
    try:
        for face in list(cap.GetFaces() or []):
            z = face_z(face)
            if z is not None and abs(z - cap_top_z) < 0.5:
                cap_top_edges = list(face.GetEdges() or [])
                break
    except Exception:
        pass

    try:
        blend_edges(
            part, cap,
            lambda e: e in cap_top_edges,
            "Bottom_Blend_Radius * 0.5",
            "EDGE_BLEND_CAP_TOP",
        )
        print("[OK] Cap top fillet applied")
    except Exception as exc:
        print("[WARN] Cap top fillet skipped: {}".format(exc))

    # 9. Grip Ribs (circular pattern around Cap)
    # Protrusion curve of a single rib on the outer wall
    rib_z_start = cap_z + 1.0
    rib_z_height = cap_h - 4.0  # terminates below the top surface leaving it smooth
    
    rib_w = v("Grip_Rib_Width")
    rib_d = v("Grip_Rib_Depth")
    
    # Draw rib profile: small rectangle at X = cap_r to X = cap_r + rib_d
    rib_curves = [
        line(part, (cap_r - 0.1, -rib_w * 0.5, rib_z_start), (cap_r + rib_d, -rib_w * 0.5, rib_z_start)),
        line(part, (cap_r + rib_d, -rib_w * 0.5, rib_z_start), (cap_r + rib_d, rib_w * 0.5, rib_z_start)),
        line(part, (cap_r + rib_d, rib_w * 0.5, rib_z_start), (cap_r - 0.1, rib_w * 0.5, rib_z_start)),
        line(part, (cap_r - 0.1, rib_w * 0.5, rib_z_start), (cap_r - 0.1, -rib_w * 0.5, rib_z_start)),
    ]
    
    rib_feat, _ = extrude_z(
        part, rib_curves, "0.0", str(rib_z_height), "EXTRUDE_SINGLE_GRIP_RIB",
        target=cap
    )
    print("[OK] Single cap rib extruded")

    # Circular pattern of ribs
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
        circ.AngularSpacing.NCopies.RightHandSide = "Grip_Rib_Count"
        circ.AngularSpacing.PitchAngle.RightHandSide = "360.0 / Grip_Rib_Count"
        feat_pattern = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat_pattern, "CIRCULAR_PATTERN_GRIP_RIBS")
    print("[OK] Grip ribs patterned around Cap side wall")

    # Save and fit view
    try:
        part.ModelingViews.WorkView.Fit()
    except Exception:
        pass
    
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    
    # Write output to launcher/watcher files
    root = Path(__file__).resolve().parents[3]
    (root / "latest_nx_result.txt").write_text(str(path), encoding="utf-8")
    base = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
    router = Path(base) / "NXBIN" / "ugs_router.exe"
    (root / "open_current_nx_result.cmd").write_text(
        '@echo off\nstart "" "{}" -ug -use_file_dir "{}"\n'.format(router, path),
        encoding="utf-8",
    )
    print("Saved: {}".format(path))


if __name__ == "__main__":
    log = Path(__file__).resolve().parents[3] / "bottle_parts_journal.log"
    try:
        log.write_text("Starting Bottle_Parts journal\n", encoding="utf-8")
        main()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
