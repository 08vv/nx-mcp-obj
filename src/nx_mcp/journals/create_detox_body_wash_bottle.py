"""Create a parametric premium body-wash bottle in Siemens NX 2206.

This journal builds a clean native-feature model:
expressions, one rounded-rectangle sketch/profile extrude, one Through Curves
shoulder, neck/ring primitives, one native shell, one rib seed, one circular
feature pattern, and final edge blends.
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


VALUES = {
    "Bottle_Height": 180.0,
    "Bottle_Width": 70.0,
    "Bottle_Depth": 45.0,
    "Wall_Thickness": 2.5,
    "Corner_Radius": 9.0,
    "Shoulder_Height": 30.0,
    "Neck_Diameter": 27.0,
    "Neck_Height": 17.0,
    "Retaining_Ring_Diameter": 31.0,
    "Retaining_Ring_Height": 3.0,
    "Cap_Diameter": 35.0,
    "Cap_Height": 24.0,
    "Cap_Rib_Count": 36,
    "Cap_Rib_Depth": 0.8,
    "Bottom_Fillet": 1.8,
    "Top_Fillet": 0.6,
}

BODY_HEIGHT_FACTOR = 0.73
SECTION_SEGMENTS = (64, 80, 96, 120)


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "detox_body_wash_bottle.prt"


def v(name: str) -> float:
    return float(VALUES[name])


def body_h() -> float:
    return v("Bottle_Height") * BODY_HEIGHT_FACTOR


def shoulder_top() -> float:
    return body_h() + v("Shoulder_Height")


def neck_top() -> float:
    return shoulder_top() + v("Retaining_Ring_Height") + v("Neck_Height")


def set_name(obj, name: str) -> None:
    try:
        obj.SetName(name)
    except Exception:
        pass


def make_expressions(part) -> None:
    for name, value in VALUES.items():
        rhs = int(value) if name == "Cap_Rib_Count" else value
        try:
            part.Expressions.CreateExpression("Number", f"{name} = {rhs}")
        except Exception:
            pass
    formulas = {
        "Body_Height": "Bottle_Height * 0.73",
        "Shoulder_Start_Z": "Body_Height",
        "Shoulder_End_Z": "Body_Height + Shoulder_Height",
        "Neck_Start_Z": "Shoulder_End_Z + Retaining_Ring_Height",
        "Neck_End_Z": "Neck_Start_Z + Neck_Height",
        "Cap_Start_Z": "Neck_End_Z",
        "Cap_Rib_Angle": "360.0 / Cap_Rib_Count",
    }
    for name, rhs in formulas.items():
        try:
            part.Expressions.CreateExpression("Number", f"{name} = {rhs}")
        except Exception:
            pass


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


def xy_sketch(part, name: str):
    plane = part.Planes.CreatePlane(
        point(0, 0, 0),
        NXOpen.Vector3d(0, 0, 1),
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    factory = (
        getattr(part.Sketches, "CreateSketchInPlaceBuilder2", None)
        or getattr(part.Sketches, "CreateSketchInPlaceBuilder", None)
    )
    builder = factory(None)
    try:
        for attr in ("PlaneOrFace", "PlaneReference", "PlacementFace"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, plane)
                    break
                except Exception:
                    pass
        feature = builder.Commit()
    finally:
        builder.Destroy()
    sketch = feature.Sketch if hasattr(feature, "Sketch") else feature
    set_name(feature, name)
    return sketch


def rounded_rect_curves(part, z: float, w: float, d: float, r: float, sketch=None):
    hw = w * 0.5
    hd = d * 0.5
    r = min(r, hw - 0.1, hd - 0.1)
    x0, x1 = -hw + r, hw - r
    y0, y1 = -hd + r, hd - r
    x_axis = NXOpen.Vector3d(1, 0, 0)
    y_axis = NXOpen.Vector3d(0, 1, 0)
    curves = [
        line(part, (x0, -hd, z), (x1, -hd, z)),
        part.Curves.CreateArc(point(x1, y0, z), x_axis, y_axis, r, -math.pi / 2, 0),
        line(part, (hw, y0, z), (hw, y1, z)),
        part.Curves.CreateArc(point(x1, y1, z), x_axis, y_axis, r, 0, math.pi / 2),
        line(part, (x1, hd, z), (x0, hd, z)),
        part.Curves.CreateArc(point(x0, y1, z), x_axis, y_axis, r, math.pi / 2, math.pi),
        line(part, (-hw, y1, z), (-hw, y0, z)),
        part.Curves.CreateArc(point(x0, y0, z), x_axis, y_axis, r, math.pi, 3 * math.pi / 2),
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


def section(part, curves):
    sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
    rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    sec.AddToSection(
        rules,
        curves[0],
        NXOpen.NXObject.Null,
        NXOpen.NXObject.Null,
        point(0, 0, 0),
        NXOpen.Section.Mode.Create,
        False,
    )
    return sec


def extrude(part, curves, start_rhs: str, end_rhs: str, name: str, target=None):
    builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section(part, curves)
        builder.Direction = part.Directions.CreateDirection(
            point(0, 0, 0),
            NXOpen.Vector3d(0, 0, 1),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Limits.StartExtend.Value.RightHandSide = start_rhs
        builder.Limits.EndExtend.Value.RightHandSide = end_rhs
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


def body_feature(part):
    sketch = xy_sketch(part, "SKETCH_ROUNDED_RECTANGLE_BODY_PROFILE")
    curves = rounded_rect_curves(
        part,
        0,
        v("Bottle_Width"),
        v("Bottle_Depth"),
        v("Corner_Radius"),
        sketch,
    )
    return extrude(part, curves, "0", "Body_Height", "EXTRUDE_TALL_RECTANGULAR_BODY")


def radius_to_rounded_rect(width: float, depth: float, corner: float, angle: float) -> float:
    ux, uy = math.cos(angle), math.sin(angle)
    low, high = 0.0, max(width, depth)
    hw, hd = width * 0.5, depth * 0.5
    rr = min(corner, hw - 0.01, hd - 0.01)
    for _ in range(40):
        mid = (low + high) * 0.5
        x, y = mid * ux, mid * uy
        qx = abs(x) - (hw - rr)
        qy = abs(y) - (hd - rr)
        outside = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - rr
        if outside <= 0:
            low = mid
        else:
            high = mid
    return low


def ring_polyline(part, width: float, depth: float, corner: float, z: float, count: int):
    pts = []
    for i in range(count):
        a = 2 * math.pi * i / count
        mag = radius_to_rounded_rect(width, depth, corner, a)
        pts.append((mag * math.cos(a), mag * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % count]) for i in range(count)]


def shoulder_sections(part, count: int):
    curves_per_section = []
    for i in range(9):
        t = i / 8.0
        s = t * t * (3 - 2 * t)
        w = v("Bottle_Width") + (v("Neck_Diameter") - v("Bottle_Width")) * s
        d = v("Bottle_Depth") + (v("Neck_Diameter") - v("Bottle_Depth")) * s
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
            set_name(feat, "THROUGH_CURVES_CONTINUOUS_RECTANGLE_TO_ROUND_SHOULDER")
            bodies = feat.GetBodies()
            if bodies:
                return feat, bodies[0]
        except Exception as exc:
            error_text = str(exc)
    raise RuntimeError(f"Through Curves shoulder did not succeed after regenerating compatible sections: {error_text}")


def unite(part, target, tool, name: str):
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


def circle_profile(part, diameter: float, z: float, n: int = 72):
    pts = []
    r = diameter * 0.5
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append((r * math.cos(a), r * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % n]) for i in range(n)]


def add_neck(part, body):
    curves = circle_profile(part, v("Neck_Diameter"), shoulder_top() + v("Retaining_Ring_Height"))
    _, body = extrude(part, curves, "0", "Neck_Height", "EXTRUDE_SHORT_CENTERED_NECK", body)
    return body


def add_retaining_ring(part, body):
    z0 = shoulder_top()
    z1 = shoulder_top() + v("Retaining_Ring_Height")
    r0 = v("Neck_Diameter") * 0.5
    r1 = v("Retaining_Ring_Diameter") * 0.5
    profile = [
        (r0, 0, z0),
        (r1, 0, z0),
        (r1, 0, z1),
        (r0, 0, z1),
    ]
    curves = [line(part, profile[i], profile[(i + 1) % len(profile)]) for i in range(len(profile))]
    builder = part.Features.CreateRevolveBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section(part, curves)
        axis = NXOpen.Axis(point(0, 0, 0), NXOpen.Vector3d(0, 0, 1))
        try:
            axis = part.Axes.CreateAxis(point(0, 0, 0), NXOpen.Vector3d(0, 0, 1), NXOpen.SmartObject.UpdateOption.WithinModeling)
        except Exception:
            pass
        builder.Axis = axis
        builder.Limits.StartExtend.Value.RightHandSide = "0"
        builder.Limits.EndExtend.Value.RightHandSide = "360"
        try:
            builder.BooleanOperation.SetBooleanOperationAndBody(
                NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
                body,
            )
        except Exception:
            pass
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, "REVOLVE_LOW_RETAINING_RING")
    bodies = feat.GetBodies()
    if bodies and bodies[0] is not body:
        body = unite(part, body, bodies[0], "UNITE_RETAINING_RING")
    return body


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
        return 0, 0, 0
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
        return (0, 0, 0), (0, 0, 0)
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


def shell_bottle(part, body):
    body = live_tallest_body(part) or body
    faces = []
    for face in list(body.GetFaces() or []):
        z = face_z(face)
        if z is not None and abs(z - neck_top()) < 0.8:
            faces.append(face)
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
    set_name(feat, "SHELL_UNIFORM_OPEN_NECK")
    return live_tallest_body(part) or body


def blend_edges(part, body, chooser, radius_rhs: str, name: str):
    edges = [e for e in list(body.GetEdges() or []) if chooser(e)]
    if not edges:
        return None
    builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        collector = part.ScCollectors.CreateCollector()
        collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(edges)], False)
        builder.Tolerance = 0.01
        builder.AddChainset(collector, radius_rhs)
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    return feat


def cylinder(part, origin_z: float, diameter_rhs: str, height_rhs: str, name: str):
    builder = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        direction = part.Directions.CreateDirection(
            point(0, 0, origin_z),
            NXOpen.Vector3d(0, 0, 1),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Axis.Point.SetCoordinates(point(0, 0, origin_z))
        builder.Axis.Direction = direction
        builder.Diameter.RightHandSide = diameter_rhs
        builder.Height.RightHandSide = height_rhs
        feat = builder.Commit()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, bodies[0] if bodies else None


def cap_with_ribs(part):
    cap_z = neck_top()
    _, cap = cylinder(part, cap_z, "Cap_Diameter", "Cap_Height", "CYLINDER_COMPACT_RIBBED_CAP")
    if cap is None:
        raise RuntimeError("Cap cylinder did not create a body.")
    blend_edges(
        part,
        cap,
        lambda e: edge_horizontal(e)
        and (abs(edge_mid(e)[2] - cap_z) < 0.2 or abs(edge_mid(e)[2] - (cap_z + v("Cap_Height"))) < 0.2),
        "0.5",
        "EDGE_BLEND_CAP_ENDS",
    )
    rib_width = math.pi * v("Cap_Diameter") / v("Cap_Rib_Count") * 0.35
    r = v("Cap_Diameter") * 0.5
    curves = [
        line(part, (r - 0.05, -rib_width * 0.5, cap_z + 1.0), (r + v("Cap_Rib_Depth"), -rib_width * 0.35, cap_z + 1.0)),
        line(part, (r + v("Cap_Rib_Depth"), -rib_width * 0.35, cap_z + 1.0), (r + v("Cap_Rib_Depth"), rib_width * 0.35, cap_z + 1.0)),
        line(part, (r + v("Cap_Rib_Depth"), rib_width * 0.35, cap_z + 1.0), (r - 0.05, rib_width * 0.5, cap_z + 1.0)),
        line(part, (r - 0.05, rib_width * 0.5, cap_z + 1.0), (r - 0.05, -rib_width * 0.5, cap_z + 1.0)),
    ]
    rib_feat, _ = extrude(
        part,
        curves,
        "0",
        "Cap_Height - 2.0",
        "EXTRUDE_SINGLE_CAP_GRIP_RIB",
        cap,
    )
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
        circ.RotationAxis = part.Axes.CreateAxis(point(0, 0, cap_z), NXOpen.Vector3d(0, 0, 1), NXOpen.SmartObject.UpdateOption.WithinModeling)
        circ.RotationCenter = part.Points.CreatePoint(point(0, 0, cap_z))
        circ.IncludeSeedToggle = True
        circ.AngularSpacing.NCopies.RightHandSide = "Cap_Rib_Count"
        circ.AngularSpacing.PitchAngle.RightHandSide = "Cap_Rib_Angle"
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, "CIRCULAR_FEATURE_ARRAY_CAP_RIBS")
    return cap


def write_launch_files(path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    (root / "latest_nx_result.txt").write_text(str(path), encoding="utf-8")
    base = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
    router = Path(base) / "NXBIN" / "ugs_router.exe"
    (root / "open_current_nx_result.cmd").write_text(
        f'@echo off\nstart "" "{router}" -ug -use_file_dir "{path}"\n',
        encoding="utf-8",
    )


def main() -> None:
    path = out_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)
    part = session.Parts.Work

    print("Building premium parametric body wash bottle")
    make_expressions(part)
    _, body = body_feature(part)
    _, shoulder = through_curves_shoulder(part, body)
    body = unite(part, body, shoulder, "UNITE_BODY_AND_SINGLE_SHOULDER")
    body = add_retaining_ring(part, body)
    body = add_neck(part, body)
    body = shell_bottle(part, body)
    blend_edges(part, body, lambda e: edge_horizontal(e) and abs(edge_mid(e)[2]) < 0.3, "Bottom_Fillet", "EDGE_BLEND_BODY_BOTTOM")
    blend_edges(part, body, lambda e: edge_horizontal(e) and abs(edge_mid(e)[2] - shoulder_top()) < 0.3, "Top_Fillet", "EDGE_BLEND_SHOULDER_NECK")
    cap = cap_with_ribs(part)

    try:
        print(f"Bottle faces: {len(list(body.GetFaces() or []))}; cap faces: {len(list(cap.GetFaces() or []))}")
        part.ModelingViews.WorkView.Fit()
    except Exception:
        pass
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    write_launch_files(path)
    router = Path(os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206") / "NXBIN" / "ugs_router.exe"
    if router.exists():
        try:
            subprocess.Popen([str(router), "-ug", "-use_file_dir", str(path)])
        except Exception:
            pass
    print(f"Saved: {path}")


if __name__ == "__main__":
    log = Path(__file__).resolve().parents[3] / "detox_body_wash_bottle_journal.log"
    try:
        log.write_text("Starting new body wash bottle journal\n", encoding="utf-8")
        main()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
