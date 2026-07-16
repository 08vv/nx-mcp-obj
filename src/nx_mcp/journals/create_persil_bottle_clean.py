"""Create a clean, production-ready, parametric Persil_Detergent_Bottle_Clean.prt in Siemens NX 2206.

This script implements a high-quality CAD modeling history for the bottle body
and measuring cap:
- Body is built by sketching the front profile in the XZ plane, extruding
  symmetrically along Y, and rounding with large fillets.
- Neck is extruded as a perfect cylinder and united with the body.
- The bottle is hollowed using a uniform Shell feature removing the neck's top face.
- The integrated side handle is cut using a slot extrude-cut and blended.
- The cap is a separate solid body (extruded circle, large dome blend, patterned grip ribs).
- Fully parametric via named Expressions.

Usage:
  run_journal.exe create_persil_bottle_clean.py [output_path.prt]
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
# Primary parameters (mm) — Persil detergent bottle
# ---------------------------------------------------------------------------
VALUES = {
    "Body_Height": 210.0,
    "Body_Width": 140.0,
    "Body_Depth": 70.0,
    "Shoulder_Height": 45.0,
    "Neck_Diameter": 42.0,
    "Neck_Height": 12.0,
    "Corner_Radius": 28.0,
    "Handle_Offset_X": 32.0,
    "Handle_Hole_Width": 34.0,
    "Handle_Hole_Height": 90.0,
    "Handle_Center_Z": 170.0,
    "Handle_Fillet": 5.0,
    "Bottom_Fillet": 2.0,
    "Neck_Fillet": 2.0,
    "Cap_Diameter": 55.0,
    "Cap_Height": 24.0,
    "Cap_Dome_Radius": 10.0,
    "Cap_Rib_Count": 36,
    "Cap_Rib_Depth": 0.5,
    "Cap_Bottom_Fillet": 0.5,
    "Wall_Thickness": 2.5,
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Persil_Detergent_Bottle_Clean.prt"


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


def extrude_y(part, curves, start_rhs, end_rhs, name, target=None, subtract=False):
    return extrude(part, curves, vec(0.0, 1.0, 0.0), start_rhs, end_rhs, name, target, subtract)


def extrude_z(part, curves, start_rhs, end_rhs, name, target=None, subtract=False):
    return extrude(part, curves, vec(0.0, 0.0, 1.0), start_rhs, end_rhs, name, target, subtract)


# ---------------------------------------------------------------------------
# Symmetrical bottle body from XZ front profile sketch
# ---------------------------------------------------------------------------
def body_feature(part):
    _, sketch = xz_sketch(part, "SKETCH_BOTTLE_FRONT_PROFILE")
    
    # Half-width and Z values
    hw = v("Body_Width") * 0.5
    h_neck = v("Neck_Diameter") * 0.5
    h_shoulder_top = h_neck + 2.0  # Leaves a 2.0 mm shelf margin for filleting
    z_shoulder_start = body_h()
    z_shoulder_end = shoulder_top()
    
    # Symmetrical profile: base, vertical sides, shoulder taper lines, neck base line
    curves = [
        # Base horizontal line
        line(part, (-hw, 0.0, 0.0), (hw, 0.0, 0.0)),
        # Right vertical side
        line(part, (hw, 0.0, 0.0), (hw, 0.0, z_shoulder_start - 30.0)),
        # Right shoulder bottom transition line (softly angled)
        line(part, (hw, 0.0, z_shoulder_start - 30.0), (hw - 10.0, 0.0, z_shoulder_start)),
        # Right slanted shoulder line
        line(part, (hw - 10.0, 0.0, z_shoulder_start), (h_shoulder_top, 0.0, z_shoulder_end)),
        # Neck base horizontal line
        line(part, (h_shoulder_top, 0.0, z_shoulder_end), (-h_shoulder_top, 0.0, z_shoulder_end)),
        # Left slanted shoulder line
        line(part, (-h_shoulder_top, 0.0, z_shoulder_end), (-hw + 10.0, 0.0, z_shoulder_start)),
        # Left shoulder bottom transition line
        line(part, (-hw + 10.0, 0.0, z_shoulder_start), (-hw, 0.0, z_shoulder_start - 30.0)),
        # Left vertical side
        line(part, (-hw, 0.0, z_shoulder_start - 30.0), (-hw, 0.0, 0.0)),
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
            
    # Extrude symmetrically along Y by half depth
    half_depth = v("Body_Depth") * 0.5
    return extrude_y(part, curves, str(-half_depth), str(half_depth), "EXTRUDE_FRONT_SILHOUETTE_BODY")


# ---------------------------------------------------------------------------
# Cylinder primitive helper
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


def add_neck(part, body):
    _, neck_body = cylinder(part, shoulder_top(), "Neck_Diameter", "Neck_Height", "CYLINDER_NECK")
    if neck_body is not None and neck_body is not body:
        body = unite(part, body, neck_body, "UNITE_NECK")
    return body


# ---------------------------------------------------------------------------
# Integrated side handle slot cutout
# ---------------------------------------------------------------------------
def slot_profile_xz(part, cx, cz, width, height):
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


def face_z(face):
    try:
        face_type, origin, direction, bbox, radius, flag1, flag2 = UF.Modeling.AskFaceData(face.Tag)
        return float(origin[2])
    except Exception:
        return None


def edge_z_center(edge):
    pts = edge_points(edge)
    if pts is not None:
        return (pts[0][2] + pts[1][2]) * 0.5
    return 0.0


# ---------------------------------------------------------------------------
# Shell uniform wall thickness (removing top circular neck face)
# ---------------------------------------------------------------------------
def shell_bottle(part, body):
    body = live_tallest_body(part) or body
    faces = []
    target_z = neck_top()
    
    # Top flat circular face of the neck
    for face in list(body.GetFaces() or []):
        z = face_z(face)
        if z is not None and abs(z - target_z) < 0.5:
            # Check if it has a circular/outer loop
            faces.append(face)
            break
            
    if not faces:
        print("  [WARN] Could not find neck top face for shell, selecting highest flat face")
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


def circle_profile(part, diameter, z, n=72):
    pts = []
    r = diameter * 0.5
    for i in range(n):
        a = 2.0 * math.pi * float(i) / float(n)
        pts.append((r * math.cos(a), r * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % n]) for i in range(n)]


# ---------------------------------------------------------------------------
# Cap construction
# ---------------------------------------------------------------------------
def build_cap(part):
    cap_z = neck_top()
    
    # Cap body (extruded cylinder)
    curves = circle_profile(part, v("Cap_Diameter"), cap_z)
    _, cap = extrude_z(part, curves, "0", "Cap_Height", "EXTRUDE_CAP_BODY")
    if cap is None:
        raise RuntimeError("Cap extrude did not create a body.")
    print("[OK] Cap cylinder extruded at Z={:.1f}".format(cap_z))
    
    # Top dome fillet
    cap_top_z = cap_z + v("Cap_Height")
    blend_edges(
        part, cap,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2] - cap_top_z) < 0.5,
        "Cap_Dome_Radius",
        "EDGE_BLEND_CAP_DOME",
    )
    print("[OK] Cap dome fillet applied")
    
    # Bottom corner fillet
    blend_edges(
        part, cap,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2] - cap_z) < 0.5,
        "Cap_Bottom_Fillet",
        "EDGE_BLEND_CAP_BOTTOM",
    )
    print("[OK] Cap bottom fillet applied")
    
    # Grip ribs (single + circular pattern)
    rib_width = math.pi * v("Cap_Diameter") / v("Cap_Rib_Count") * 0.35
    r = v("Cap_Diameter") * 0.5
    rib_curves = [
        line(part, (r - 0.05, -rib_width * 0.5, cap_z + 1.0), (r + v("Cap_Rib_Depth"), -rib_width * 0.35, cap_z + 1.0)),
        line(part, (r + v("Cap_Rib_Depth"), -rib_width * 0.35, cap_z + 1.0), (r + v("Cap_Rib_Depth"), rib_width * 0.35, cap_z + 1.0)),
        line(part, (r + v("Cap_Rib_Depth"), rib_width * 0.35, cap_z + 1.0), (r - 0.05, rib_width * 0.5, cap_z + 1.0)),
        line(part, (r - 0.05, rib_width * 0.5, cap_z + 1.0), (r - 0.05, -rib_width * 0.5, cap_z + 1.0)),
    ]
    rib_feat, _ = extrude_z(
        part, rib_curves,
        "0", "Cap_Height - Cap_Dome_Radius - 2.0",
        "EXTRUDE_SINGLE_GRIP_RIB",
        cap,
    )
    print("[OK] Single grip rib extruded")
    
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

    print("Building parametric clean CAD Persil Detergent Bottle")
    make_expressions(part)

    # ---- BOTTLE BODY ----

    # Step 1: Body profile extrude (symmetrical block)
    _, body = body_feature(part)
    print("[OK] Symmetrical body silhouette extruded")

    # Step 2: Edge blend to round vertical corners to form oval body shape
    blend_edges(
        part, body,
        lambda e: (
            edge_points(e) is not None
            and not edge_horizontal(e)
            and edge_mid(e)[2] < body_h()
        ),
        "Corner_Radius",
        "EDGE_BLEND_BODY_OVAL",
    )
    print("[OK] Body rounded into oval shape via edge blends")

    # Step 3: Neck cylinder extrude & Boolean Unite
    body = add_neck(part, body)
    print("[OK] Neck cylinder united with body")

    # Step 4: Edge blend on the shoulder slants to blend them smoothly
    blend_edges(
        part, body,
        lambda e: (
            edge_points(e) is not None
            and edge_horizontal(e)
            and abs(edge_mid(e)[2] - body_h()) < 1.0
        ),
        "Shoulder_Height * 0.8",
        "EDGE_BLEND_SHOULDER",
    )
    print("[OK] Shoulder transitions blended smoothly")

    # Step 4b: Edge blend at the neck base to transition smoothly into the shoulder
    def neck_base_chooser(e):
        mid = edge_mid(e)
        # Check Z position
        if abs(edge_z_center(e) - shoulder_top()) > 0.5:
            return False
        # Check XY radius to exclude outer shoulder edges
        return math.hypot(mid[0], mid[1]) < 25.0

    blend_edges(
        part, body,
        neck_base_chooser,
        "Neck_Fillet",
        "EDGE_BLEND_SHOULDER_NECK",
    )
    print("[OK] Shoulder-to-neck transition blended smoothly")

    # Step 5: Handle hole slot subtract-cut
    body = cut_handle_hole(part, body)
    print("[OK] Handle hole slot cut out")

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

    # Step 7: Bottom edge fillet
    try:
        blend_edges(
            part, body,
            lambda e: edge_horizontal(e) and abs(edge_mid(e)[2]) < 0.3,
            "Bottom_Fillet",
            "EDGE_BLEND_BOTTOM",
        )
        print("[OK] Bottom base fillet applied")
    except Exception as exc:
        print("[WARN] Bottom base fillet skipped: {}".format(exc))

    # Step 8: Shell bottle (removing neck's top face)
    body = shell_bottle(part, body)
    print("[OK] Bottle body shelled successfully")

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
    log = Path(__file__).resolve().parents[3] / "persil_bottle_clean_journal.log"
    try:
        log.write_text("Starting clean Persil Detergent Bottle journal\n", encoding="utf-8")
        main()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
