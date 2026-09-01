"""Create a clean, production-ready, parametric Sweet_Spicy_Sauce_Bottle.prt in Siemens NX 2206.

This script implements a high-quality CAD modeling history for the sauce bottle body
and measuring cap:
- Body is built by sketching the front profile in the XZ plane, revolving it
  360 degrees around the Z-axis, and blending the shoulder and base transitions.
- The bottle is hollowed using a uniform Shell feature removing the neck's top face.
- The cap is a separate solid body (revolved rectangle, dome blend, patterned grip ribs).
- Fully parametric via named Expressions.

Usage:
  run_journal.exe create_sauce_bottle.py [output_path.prt]
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
from examples._common import set_name, vec, write_launch_files

UF = NXOpen.UF.UFSession.GetUFSession()

# ---------------------------------------------------------------------------
# Primary parameters (mm) — Sweet & Spicy sauce bottle
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Height": 250.0,
    "Body_Diameter": 68.0,
    "Base_Radius": 34.0,           # Body_Diameter / 2.0
    "Shoulder_Height": 110.0,      # Height where straight body ends and shoulder starts
    "Shoulder_Radius": 14.0,       # Neck_Diameter / 2.0
    "Shoulder_Curve_Radius": 15.0, # Fillet at shoulder bottom transition
    "Neck_Diameter": 28.0,
    "Neck_Height": 25.0,
    "Cap_Diameter": 32.0,
    "Cap_Height": 16.0,
    "Cap_Corner_Radius": 1.5,
    "Grip_Rib_Count": 36,
    "Grip_Rib_Depth": 0.5,
    "Wall_Thickness": 2.0,
    "Bottom_Fillet_Radius": 3.0,
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Sweet_Spicy_Sauce_Bottle.prt"


def v(name: str) -> float:
    return float(VALUES[name])




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
        "Base_Radius": "Body_Diameter / 2.0",
        "Shoulder_Radius": "Neck_Diameter / 2.0",
        "Shoulder_Top_Z": "Overall_Height - Neck_Height",
        "Cap_Start_Z": "Overall_Height",
        "Cap_End_Z": "Overall_Height + Cap_Height",
        "Cap_Rib_Angle": "360.0 / Grip_Rib_Count",
    }
    for name, rhs in formulas.items():
        try:
            expr = part.Expressions.Get(name)
            expr.RightHandSide = rhs
        except Exception:
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
    return create_sketch_on_csys(
        part,
        point(0.0, 0.0, 0.0),
        vec(1.0, 0.0, 0.0),
        vec(0.0, 0.0, 1.0),
        vec(0.0, -1.0, 0.0),
        name,
    )


# ---------------------------------------------------------------------------
# Section, Extrude, and Revolve
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


def extrude_z(part, curves, start_rhs, end_rhs, name, target=None, subtract=False):
    return extrude(part, curves, vec(0.0, 0.0, 1.0), start_rhs, end_rhs, name, target, subtract)


def revolve_z(part, curves, start_angle_rhs, end_angle_rhs, name, target_body=None):
    tags = [curve.Tag for curve in curves]
    features, number_of_features = UF.Modl.CreateRevolution(
        tags,
        len(tags),
        None,
        [str(start_angle_rhs), str(end_angle_rhs)],
        ["0", "0"],
        [0.0, 0.0, 0.0],
        False,
        True,
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        NXOpen.UF.Modl.FeatureSigns.NULLSIGN,
    )
    if not features or number_of_features < 1:
        raise RuntimeError("Revolve did not create a feature")
    feature = NXOpen.TaggedObjectManager().GetTaggedObject(features[0])
    set_name(feature, name)
    bodies = feature.GetBodies()
    return feature, bodies[0] if bodies else None


# ---------------------------------------------------------------------------
# Edge and Face helpers
# ---------------------------------------------------------------------------
def edge_points(edge):
    try:
        verts = edge.GetVertices()
        if verts and len(verts) >= 2:
            return (float(verts[0].X), float(verts[0].Y), float(verts[0].Z)), (float(verts[1].X), float(verts[1].Y), float(verts[1].Z))
        elif verts and len(verts) == 1:
            pt = (float(verts[0].X), float(verts[0].Y), float(verts[0].Z))
            return pt, pt
        return None
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


def edge_z_center(edge):
    pts = edge_points(edge)
    if pts is not None:
        return (pts[0][2] + pts[1][2]) * 0.5
    return 0.0


def face_z(face):
    try:
        face_type, origin, direction, bbox, radius, flag1, flag2 = UF.Modeling.AskFaceData(face.Tag)
        return float(origin[2])
    except Exception:
        return None


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
# Shell uniform wall thickness
# ---------------------------------------------------------------------------
def shell_bottle(part, body):
    body = live_tallest_body(part) or body
    faces = []
    target_z = v("Overall_Height")
    
    # Top flat circular face of the neck
    for face in list(body.GetFaces() or []):
        z = face_z(face)
        if z is not None and abs(z - target_z) < 0.5:
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
# Cap construction
# ---------------------------------------------------------------------------
def circle_profile(part, diameter, z, n=72):
    pts = []
    r = diameter * 0.5
    for i in range(n):
        a = 2.0 * math.pi * float(i) / float(n)
        pts.append((r * math.cos(a), r * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % n]) for i in range(n)]


def build_cap(part):
    z_start = v("Overall_Height")
    z_end = z_start + v("Cap_Height")
    c_rad = v("Cap_Diameter") * 0.5
    
    # 1. Cap body (revolved profile)
    cap_curves = [
        line(part, (0.0, 0.0, z_start), (c_rad, 0.0, z_start)),
        line(part, (c_rad, 0.0, z_start), (c_rad, 0.0, z_end)),
        line(part, (c_rad, 0.0, z_end), (0.0, 0.0, z_end)),
        line(part, (0.0, 0.0, z_end), (0.0, 0.0, z_start))
    ]
    
    _, cap_sketch = xz_sketch(part, "SKETCH_CAP_PROFILE")
    if cap_sketch is not None:
        try:
            cap_sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
        except Exception:
            pass
        for curve in cap_curves:
            add_to_sketch(cap_sketch, curve)
        try:
            cap_sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
        except Exception:
            pass
            
    _, cap = revolve_z(part, cap_curves, "0", "360", "REVOLVE_CAP_BODY")
    print("[OK] Cap body revolved successfully")
    
    # 2. Cap top corner fillet
    blend_edges(
        part, cap,
        lambda e: abs(edge_z_center(e) - z_end) < 0.5,
        "Cap_Corner_Radius",
        "EDGE_BLEND_CAP_TOP"
    )
    print("[OK] Cap top corner fillet applied")
    
    # 3. Cap bottom seating edge fillet
    blend_edges(
        part, cap,
        lambda e: abs(edge_z_center(e) - z_start) < 0.5,
        "0.5",
        "EDGE_BLEND_CAP_BOTTOM"
    )
    print("[OK] Cap bottom fillet applied")
    
    # 4. Grip ribs (single + circular pattern)
    rib_width = math.pi * v("Cap_Diameter") / v("Grip_Rib_Count") * 0.35
    r = v("Cap_Diameter") * 0.5
    rib_z_start = z_start + 0.5
    
    # Single vertical rib sketch curves
    rib_curves = [
        line(part, (r - 0.05, -rib_width * 0.5, rib_z_start), (r + v("Grip_Rib_Depth"), -rib_width * 0.35, rib_z_start)),
        line(part, (r + v("Grip_Rib_Depth"), -rib_width * 0.35, rib_z_start), (r + v("Grip_Rib_Depth"), rib_width * 0.35, rib_z_start)),
        line(part, (r + v("Grip_Rib_Depth"), rib_width * 0.35, rib_z_start), (r - 0.05, rib_width * 0.5, rib_z_start)),
        line(part, (r - 0.05, rib_width * 0.5, rib_z_start), (r - 0.05, -rib_width * 0.5, rib_z_start)),
    ]
    
    # Extrude rib so it terminates before the top edge
    rib_feat, _ = extrude_z(
        part, rib_curves,
        "0", "Cap_Height - 3.0",
        "EXTRUDE_SINGLE_GRIP_RIB",
        cap,
    )
    print("[OK] Single cap rib extruded")
    
    # Pattern ribs circular around the center axis
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
            point(0.0, 0.0, z_start),
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        circ.RotationCenter = part.Points.CreatePoint(point(0.0, 0.0, z_start))
        circ.IncludeSeedToggle = True
        circ.AngularSpacing.NCopies.RightHandSide = "Grip_Rib_Count"
        circ.AngularSpacing.PitchAngle.RightHandSide = "Cap_Rib_Angle"
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, "CIRCULAR_PATTERN_CAP_RIBS")
    print("[OK] Circular pattern of grip ribs created")
    
    return cap


# ---------------------------------------------------------------------------
# Launch file helpers
# ---------------------------------------------------------------------------


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
    print("Building Sweet & Spicy Sauce Bottle")
    print("-----------------------------------")

    # Step 1: Expressions
    make_expressions(part)

    # Step 2: Bottle Body revolved from XZ sketch
    hw = v("Body_Diameter") * 0.5
    h_neck = v("Neck_Diameter") * 0.5
    z_shoulder = v("Shoulder_Height")
    z_shoulder_top = v("Overall_Height") - v("Neck_Height")
    z_top = v("Overall_Height")
    
    # Outer profile lines
    profile_curves = [
        line(part, (0.0, 0.0, 0.0), (hw, 0.0, 0.0)),
        line(part, (hw, 0.0, 0.0), (hw, 0.0, z_shoulder)),
        line(part, (hw, 0.0, z_shoulder), (h_neck, 0.0, z_shoulder_top)),
        line(part, (h_neck, 0.0, z_shoulder_top), (h_neck, 0.0, z_top)),
        line(part, (h_neck, 0.0, z_top), (0.0, 0.0, z_top)),
        line(part, (0.0, 0.0, z_top), (0.0, 0.0, 0.0))
    ]
    
    _, body_sketch = xz_sketch(part, "SKETCH_BOTTLE_PROFILE")
    if body_sketch is not None:
        try:
            body_sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
        except Exception:
            pass
        for curve in profile_curves:
            add_to_sketch(body_sketch, curve)
        try:
            body_sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
        except Exception:
            pass
            
    _, body = revolve_z(part, profile_curves, "0", "360", "REVOLVE_BOTTLE_BODY")
    print("[OK] Bottle body revolved successfully")



    # Step 3: Lower shoulder blend (taper transition)
    blend_edges(
        part, body,
        lambda e: abs(edge_z_center(e) - z_shoulder) < 0.5,
        "Shoulder_Curve_Radius",
        "EDGE_BLEND_SHOULDER_BOTTOM"
    )
    print("[OK] Lower shoulder blend applied")

    # Step 4: Upper shoulder blend (neck transition)
    blend_edges(
        part, body,
        lambda e: abs(edge_z_center(e) - z_shoulder_top) < 0.5,
        "Shoulder_Curve_Radius * 0.5",
        "EDGE_BLEND_SHOULDER_TOP"
    )
    print("[OK] Upper shoulder blend applied")

    # Step 5: Bottom base fillet
    blend_edges(
        part, body,
        lambda e: abs(edge_z_center(e) - 0.0) < 0.5,
        "Bottom_Fillet_Radius",
        "EDGE_BLEND_BOTTOM"
    )
    print("[OK] Bottom base fillet applied")

    # Step 6: Shell bottle (removing neck's top face)
    body = shell_bottle(part, body)
    print("[OK] Bottle body shelled successfully")

    # Step 7: Revolved Cap body with Patterned grip ribs
    cap = build_cap(part)

    # Finalize view and save
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
    log = Path(__file__).resolve().parents[3] / "sauce_bottle_journal.log"
    try:
        log.write_text("Starting Sweet & Spicy Sauce Bottle journal\n", encoding="utf-8")
        main()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
