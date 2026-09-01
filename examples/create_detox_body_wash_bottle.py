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
from examples._common import set_name, unite, vec

UF = NXOpen.UF.UFSession.GetUFSession()

VALUES = {
    "Overall_Height": 230.0,
    "Overall_Width": 78.0,
    "Overall_Depth": 42.0,
    "Body_Height": 150.0,
    "Shoulder_Height": 38.0,
    "Neck_Diameter": 34.0,
    "Neck_Height": 12.0,
    "Cap_Diameter": 40.0,
    "Cap_Height": 30.0,
    "Corner_Radius": 9.0,
    "Bottom_Blend": 4.0,
    "Wall_Thickness": 2.2,
    "Draft_Angle": 0.8,
    "Rib_Count": 48,
    "Rib_Depth": 0.7,
    "Rib_Width": 1.2,
}

SECTION_SEGMENTS = (64, 80, 96, 120)


def out_path() -> Path:
    for arg in sys.argv:
        try:
            p = Path(arg)
            if p.suffix.lower() == ".prt":
                return p.resolve()
        except Exception:
            pass
    return Path("C:/Users/HP/nx-mcp/detox_body_wash_bottle.prt")


def v(name: str) -> float:
    return float(VALUES[name])




def make_expressions(part) -> None:
    for name, value in VALUES.items():
        rhs = int(value) if name == "Rib_Count" else value
        try:
            part.Expressions.CreateExpression("Number", f"{name} = {rhs}")
        except Exception:
            pass
    formulas = {
        "Cap_Rib_Angle": "360.0 / Rib_Count",
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
        point(0.0, 0.0, 0.0),
        vec(0.0, 0.0, 1.0),
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


def crowned_rect_curves(part, z: float, w: float, d: float, r: float, crown: float, sketch=None):
    hw = w * 0.5
    hd = d * 0.5
    r = min(r, hw - 0.1, hd - 0.1)
    
    # 4 corner centers
    # C1 (bottom-right): (hw - r, -hd + r)
    # C2 (top-right): (hw - r, hd - r)
    # C3 (top-left): (-hw + r, hd - r)
    # C4 (bottom-left): (-hw + r, -hd + r)
    
    x_axis = vec(1.0, 0.0, 0.0)
    y_axis = vec(0.0, 1.0, 0.0)
    
    curves = []
    
    # 1. Front face: from C4_front (-hw + r, -hd) to C1_front (hw - r, -hd)
    if crown > 0.001:
        chord = w - 2.0 * r
        R_crown = (chord**2) / (8.0 * crown) + (crown / 2.0)
        center_y = -hd - crown + R_crown
        theta = math.asin((chord / 2.0) / R_crown)
        curves.append(part.Curves.CreateArc(point(0.0, center_y, z), x_axis, y_axis, R_crown, -math.pi/2.0 - theta, -math.pi/2.0 + theta))
    else:
        curves.append(line(part, (-hw + r, -hd, z), (hw - r, -hd, z)))
        
    # 2. Corner C1
    curves.append(part.Curves.CreateArc(point(hw - r, -hd + r, z), x_axis, y_axis, r, -math.pi/2.0, 0.0))
    
    # 3. Right side line
    curves.append(line(part, (hw, -hd + r, z), (hw, hd - r, z)))
    
    # 4. Corner C2
    curves.append(part.Curves.CreateArc(point(hw - r, hd - r, z), x_axis, y_axis, r, 0.0, math.pi/2.0))
    
    # 5. Rear face: from C2_rear (hw - r, hd) to C3_rear (-hw + r, hd)
    if crown > 0.001:
        chord = w - 2.0 * r
        R_crown = (chord**2) / (8.0 * crown) + (crown / 2.0)
        center_y = hd + crown - R_crown
        theta = math.asin((chord / 2.0) / R_crown)
        curves.append(part.Curves.CreateArc(point(0.0, center_y, z), x_axis, y_axis, R_crown, math.pi/2.0 - theta, math.pi/2.0 + theta))
    else:
        curves.append(line(part, (hw - r, hd, z), (-hw + r, hd, z)))
        
    # 6. Corner C3
    curves.append(part.Curves.CreateArc(point(-hw + r, hd - r, z), x_axis, y_axis, r, math.pi/2.0, math.pi))
    
    # 7. Left side line
    curves.append(line(part, (-hw, hd - r, z), (-hw, -hd + r, z)))
    
    # 8. Corner C4
    curves.append(part.Curves.CreateArc(point(-hw + r, -hd + r, z), x_axis, y_axis, r, math.pi, 3.0 * math.pi/2.0))
    
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
        point(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create,
        False,
    )
    return sec


def extrude(part, curves, start_rhs: str, end_rhs: str, name: str, target=None):
    builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section(part, curves)
        builder.Direction = part.Directions.CreateDirection(
            point(0.0, 0.0, 0.0),
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Limits.StartExtend.Value.RightHandSide = start_rhs
        builder.Limits.EndExtend.Value.RightHandSide = end_rhs
        
        # Apply Draft if extruding the main body
        if name == "EXTRUDE_TALL_RECTANGULAR_BODY":
            try:
                draft_settings = builder.DraftSettings
                draft_settings.DraftOption = NXOpen.GeometricUtilities.FeatureDraft.Types.FromStartLimit
                draft_settings.Angle.RightHandSide = "-Draft_Angle" # inward draft
            except Exception:
                try:
                    draft = builder.Draft
                    draft.DraftOption = NXOpen.GeometricUtilities.SimpleDraftSimpleDraftType.SimpleFromStart
                    draft.FrontDraftAngle.RightHandSide = "Draft_Angle"
                except Exception:
                    pass
                    
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
    curves = crowned_rect_curves(
        part,
        0.0,
        v("Overall_Width"),
        v("Overall_Depth"),
        v("Corner_Radius"),
        1.0, # 1.0 mm crown
        sketch,
    )
    return extrude(part, curves, "0.0", "Body_Height", "EXTRUDE_TALL_RECTANGULAR_BODY")


def recess_bottom(part, body):
    rw = v("Overall_Width") - 12.0
    rd = v("Overall_Depth") - 12.0
    rc = v("Corner_Radius") - 4.0
    
    sketch = xy_sketch(part, "SKETCH_BOTTOM_RECESS_PROFILE")
    curves = crowned_rect_curves(
        part,
        0.0,
        rw,
        rd,
        rc,
        0.8, # slightly less crown for recessed face
        sketch,
    )
    
    builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section(part, curves)
        builder.Direction = part.Directions.CreateDirection(
            point(0.0, 0.0, 0.0),
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        builder.Limits.EndExtend.Value.RightHandSide = "1.5" # 1.5 mm recess
        builder.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
            body,
        )
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, "EXTRUDE_BOTTOM_RECESS_CUT")
    
    bodies = feat.GetBodies()
    return bodies[0] if bodies else body


def shoulder_sections(part, count: int):
    curves_per_section = []
    
    # Calculate bottom size of shoulder at Z = Body_Height due to side draft
    w_start = v("Overall_Width") - 2.0 * v("Body_Height") * math.tan(math.radians(v("Draft_Angle")))
    d_start = v("Overall_Depth") - 2.0 * v("Body_Height") * math.tan(math.radians(v("Draft_Angle")))
    r_start = v("Corner_Radius") - v("Body_Height") * math.tan(math.radians(v("Draft_Angle")))
    
    w_end = v("Neck_Diameter")
    d_end = v("Neck_Diameter")
    r_end = v("Neck_Diameter") * 0.5 - 0.01
    
    for i in range(9):
        t = i / 8.0
        s = t * t * (3.0 - 2.0 * t)
        
        w = w_start + (w_end - w_start) * s
        d = d_start + (d_end - d_start) * s
        r = r_start + (r_end - r_start) * s
        crown = 1.0 * (1.0 - s)
        z = v("Body_Height") + v("Shoulder_Height") * t
        
        curves_per_section.append(crowned_rect_curves(part, z, w, d, r, crown))
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
    raise RuntimeError(f"Through Curves shoulder did not succeed: {error_text}")




def circle_profile(part, diameter: float, z: float, n: int = 72):
    pts = []
    r = diameter * 0.5
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append((r * math.cos(a), r * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % n]) for i in range(n)]


def add_neck(part, body):
    z_start = v("Body_Height") + v("Shoulder_Height")
    w_end = v("Neck_Diameter")
    d_end = v("Neck_Diameter")
    r_end = v("Neck_Diameter") * 0.5 - 0.01
    curves = crowned_rect_curves(part, z_start, w_end, d_end, r_end, 0.0)
    _, body = extrude(part, curves, "0.0", "Neck_Height", "EXTRUDE_SHORT_CENTERED_NECK", body)
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
    neck_top_z = v("Body_Height") + v("Shoulder_Height") + v("Neck_Height")
    for face in list(body.GetFaces() or []):
        z = face_z(face)
        if z is not None and abs(z - neck_top_z) < 0.8:
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
            point(0.0, 0.0, origin_z),
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Axis.Point.SetCoordinates(point(0.0, 0.0, origin_z))
        builder.Axis.Direction = direction
        builder.Diameter.RightHandSide = diameter_rhs
        builder.Height.RightHandSide = height_rhs
        feat = builder.Commit()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, bodies[0] if bodies else None


def create_cap_revolve(part):
    cap_z_start = v("Body_Height") + v("Shoulder_Height") + v("Neck_Height")
    r = v("Cap_Diameter") * 0.5
    h = v("Cap_Height")
    
    # Profile in XZ plane
    pts = [
        (0.0, 0.0, cap_z_start),
        (r, 0.0, cap_z_start),
        (r, 0.0, cap_z_start + h),
        (0.0, 0.0, cap_z_start + h),
    ]
    curves = [
        line(part, pts[0], pts[1]),
        line(part, pts[1], pts[2]),
        line(part, pts[2], pts[3]),
        line(part, pts[3], pts[0]),
    ]
    
    tags = [curve.Tag for curve in curves]
    features, number_of_features = UF.Modl.CreateRevolution(
        tags,
        len(tags),
        None,
        ["0.0", "360.0"],
        ["0", "0"],
        [0.0, 0.0, 0.0],
        False,
        True,
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        NXOpen.UF.Modl.FeatureSigns.NULLSIGN,
    )
    if not features or number_of_features < 1:
        raise RuntimeError("Cap Revolve did not create a feature")
    feature = NXOpen.TaggedObjectManager().GetTaggedObject(features[0])
    set_name(feature, "REVOLVE_BOTTLE_CAP")
    bodies = feature.GetBodies()
    cap_body = bodies[0] if bodies else None
    if cap_body:
        cap_body.SetName("Bottle_Cap")
    return feature, cap_body


def name_bodies(part):
    bodies = list(part.Bodies or [])
    for b in bodies:
        min_pt, max_pt = body_bounds(b)
        if min_pt[2] > 190.0:
            b.SetName("Bottle_Cap")
            set_name(b, "Bottle_Cap")
        else:
            b.SetName("Bottle_Body")
            set_name(b, "Bottle_Body")


def main() -> None:
    path = out_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)
    part = session.Parts.Work

    print("Building premium body-wash bottle model")
    make_expressions(part)
    
    # 1. Main Bottle Body
    _, body = body_feature(part)
    
    # 2. Bottom Edge Blend
    blend_edges(part, body, lambda e: edge_horizontal(e) and abs(edge_mid(e)[2]) < 0.2, "Bottom_Blend", "EDGE_BLEND_BODY_BOTTOM")
    
    # 3. Shoulder Transition
    _, shoulder = through_curves_shoulder(part, body)
    body = unite(part, body, shoulder, "UNITE_BODY_AND_SHOULDER")
    
    # 4. Neck Extrude
    body = add_neck(part, body)
    
    # 5. Shell Bottle
    body = shell_bottle(part, body)
    
    # 6. Bottom Recess
    body = recess_bottom(part, body)
    
    # 7. Cap Revolve
    _, cap_body = create_cap_revolve(part)
    if cap_body is None:
        raise RuntimeError("Cap revolve failed to build body.")
        
    # Cap Blends
    cap_z_start = v("Body_Height") + v("Shoulder_Height") + v("Neck_Height")
    cap_h = v("Cap_Height")
    
    blend_edges(
        part,
        cap_body,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2] - (cap_z_start + cap_h)) < 0.2,
        "2.0", # Top Edge Radius = 2 mm
        "EDGE_BLEND_CAP_TOP"
    )
    blend_edges(
        part,
        cap_body,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2] - cap_z_start) < 0.2,
        "1.5", # Bottom Edge Radius = 1.5 mm
        "EDGE_BLEND_CAP_BOTTOM"
    )
    
    # 8. Grip Ribs & Circular Pattern
    r = v("Cap_Diameter") * 0.5
    rw = v("Rib_Width")
    rd = v("Rib_Depth")
    z_start = cap_z_start + 3.0 # center 24mm ribs on the 30mm cap height
    
    curves = [
        line(part, (r - 0.05, -rw * 0.5, z_start), (r + rd, -rw * 0.5, z_start)),
        line(part, (r + rd, -rw * 0.5, z_start), (r + rd, rw * 0.5, z_start)),
        line(part, (r + rd, rw * 0.5, z_start), (r - 0.05, rw * 0.5, z_start)),
        line(part, (r - 0.05, rw * 0.5, z_start), (r - 0.05, -rw * 0.5, z_start)),
    ]
    
    rib_feat, _ = extrude(
        part,
        curves,
        "0.0",
        "24.0", # Rib_Height = 24 mm
        "EXTRUDE_SINGLE_CAP_RIB",
        cap_body
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
        circ.RotationAxis = part.Axes.CreateAxis(point(0.0, 0.0, cap_z_start), vec(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        circ.RotationCenter = part.Points.CreatePoint(point(0.0, 0.0, cap_z_start))
        circ.IncludeSeedToggle = True
        circ.AngularSpacing.NCopies.RightHandSide = "Rib_Count"
        circ.AngularSpacing.PitchAngle.RightHandSide = "Cap_Rib_Angle"
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, "CIRCULAR_PATTERN_CAP_RIBS")
    
    # 9. Set solid body names
    name_bodies(part)
    
    try:
        part.ModelingViews.WorkView.Fit()
    except Exception:
        pass
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    
    # Write launcher files
    root = Path(__file__).resolve().parents[3]
    (root / "latest_nx_result.txt").write_text(str(path), encoding="utf-8")
    base = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
    router = Path(base) / "NXBIN" / "ugs_router.exe"
    (root / "open_current_nx_result.cmd").write_text(
        f'@echo off\nstart "" "{router}" -ug -use_file_dir "{path}"\n',
        encoding="utf-8",
    )
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
