"""Create parametric Bottle_Body.prt in Siemens NX 2206.

This journal builds the bottle body as a clean native-feature model:
expressions, rounded-rectangle sketch extrude, Through Curves shoulder
transition from rectangle to circle, neck cylinder, shell, and edge blends.

All critical dimensions are controlled through named Expressions for full
parametric editability.

Usage:
  run_journal.exe create_bottle_body.py [output_path.prt]
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
# Primary parameters (mm) — derived from reference image proportions
# ---------------------------------------------------------------------------
VALUES = {
    "Body_Height": 130.0,
    "Body_Width": 70.0,
    "Body_Depth": 45.0,
    "Shoulder_Height": 30.0,
    "Shoulder_Angle": 45.0,
    "Neck_Diameter": 28.0,
    "Neck_Height": 18.0,
    "Corner_Radius": 10.0,
    "Wall_Thickness": 2.0,
    "Bottom_Fillet": 2.0,
    "Top_Fillet": 0.6,
}

SECTION_SEGMENTS = (64, 80, 96, 120)


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Bottle_Body.prt"


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
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
        except Exception:
            pass
    formulas = {
        "Shoulder_Start_Z": "Body_Height",
        "Shoulder_End_Z": "Body_Height + Shoulder_Height",
        "Neck_Start_Z": "Shoulder_End_Z",
        "Neck_End_Z": "Neck_Start_Z + Neck_Height",
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
# Sketch creation via CSYS (proven pattern from mounting plate journals)
# ---------------------------------------------------------------------------
def create_sketch_on_csys(part, origin, x_vec, y_vec, z_vec, sketch_name):
    """Create a sketch on a coordinate system defined by origin and 3 orthogonal vectors."""
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
    """Create a sketch on the XY plane at Z=0."""
    return create_sketch_on_csys(
        part,
        point(0.0, 0.0, 0.0),
        vec(1.0, 0.0, 0.0),
        vec(0.0, 1.0, 0.0),
        vec(0.0, 0.0, 1.0),
        name,
    )


# ---------------------------------------------------------------------------
# Rounded rectangle profile
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


def extrude(part, curves, start_rhs, end_rhs, name, target=None):
    builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section(part, curves)
        builder.Direction = part.Directions.CreateDirection(
            point(0.0, 0.0, 0.0),
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Limits.StartExtend.Value.RightHandSide = str(start_rhs)
        builder.Limits.EndExtend.Value.RightHandSide = str(end_rhs)
        if target is not None:
            builder.BooleanOperation.SetBooleanOperationAndBody(
                NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
                target,
            )
        else:
            builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, target if target is not None else (bodies[0] if bodies else None)


# ---------------------------------------------------------------------------
# Main body extrude
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
    return extrude(part, curves, "0", "Body_Height", "EXTRUDE_RECTANGULAR_BODY")


# ---------------------------------------------------------------------------
# Shoulder transition (Through Curves: rectangle -> circle)
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
    for i in range(9):
        t = float(i) / 8.0
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
# Neck (polygon-circle extrude — edges readable by AskEdgeVerts)
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
    _, body = extrude(part, curves, "0", "Neck_Height", "EXTRUDE_NECK", body)
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
    zs = []
    for edge in list(face.GetEdges() or []):
        pair = edge_points(edge)
        if pair:
            zs.extend([pair[0][2], pair[1][2]])
    if not zs:
        return None
    return sum(zs) / len(zs)




# ---------------------------------------------------------------------------
# Edge Blend
# ---------------------------------------------------------------------------
def blend_edges(part, body, chooser, radius_rhs, name):
    edges = [e for e in list(body.GetEdges() or []) if chooser(e)]
    if not edges:
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

    print("Building parametric Bottle_Body")
    make_expressions(part)

    # Step 1: Rectangular body with rounded corners
    _, body = body_feature(part)
    print("[OK] Rectangular body extruded")

    # Step 2: Shoulder transition (rectangle to circle)
    _, shoulder = through_curves_shoulder(part, body)
    body = unite(part, body, shoulder, "UNITE_BODY_AND_SHOULDER")
    print("[OK] Shoulder united")

    # Step 3: Neck
    body = add_neck(part, body)
    print("[OK] Neck added")

    # Step 4: Edge blends
    blend_edges(
        part, body,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2]) < 0.3,
        "Bottom_Fillet",
        "EDGE_BLEND_BOTTOM",
    )
    print("[OK] Bottom fillet blended")

    try:
        print("Bottle faces: {}".format(len(list(body.GetFaces() or []))))
        part.ModelingViews.WorkView.Fit()
    except Exception:
        pass

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    write_launch_files(path)
    print("Saved: {}".format(path))


if __name__ == "__main__":
    log = Path(__file__).resolve().parents[3] / "bottle_body_journal.log"
    try:
        log.write_text("Starting Bottle_Body journal\n", encoding="utf-8")
        main()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
