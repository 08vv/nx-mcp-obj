"""Create parametric Persil_Detergent_Bottle.prt in Siemens NX 2206.

This journal builds the 5 segments of the Persil liquid detergent bottle
as separate, colored solid bodies in a single part file, matching the
reference and segmented images.
"""

from __future__ import annotations
import math
import os
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
    "Overall_Height": 310.0,
    "Overall_Width": 165.0,
    "Overall_Depth": 95.0,
    
    # Segment 1 (Brown)
    "S1_Height": 265.0,
    "S1_Width": 165.0,
    "S1_Depth": 95.0,
    "S1_Bottom_Width": 155.0,
    "S1_Top_Width": 70.0,
    "S1_Corner_Radius": 18.0,
    "S1_Bottom_Edge_Radius": 12.0,
    "S1_Wall_Thickness": 2.5,
    "S1_Side_Draft": 1.0,
    
    # Handle Opening
    "Handle_Height": 140.0,
    "Handle_Width": 60.0,
    "Handle_Thickness": 24.0,
    "Handle_Blend_Radius": 18.0,
    
    # Segment 2 (Light Blue)
    "S2_Height": 215.0,
    "S2_Width": 108.0,
    "S2_Depth": 70.0,
    "S2_Top_Width": 38.0,
    "S2_Bottom_Width": 92.0,
    
    # Segment 3 (Dark Blue)
    "S3_Height": 32.0,
    "S3_Width": 52.0,
    "S3_Depth": 42.0,
    "S3_Blend_Radius": 18.0,
    
    # Segment 4 (Orange)
    "S4_Height": 45.0,
    "S4_Width": 70.0,
    "S4_Depth": 42.0,
    "S4_Blend_Radius": 22.0,
    
    # Segment 5 (Pink) - Cap
    "Cap_Diameter": 52.0,
    "Cap_Height": 42.0,
    "Cap_Dome_Height": 10.0,
    "Cap_Rib_Count": 44,
    "Cap_Rib_Width": 1.4,
    "Cap_Rib_Depth": 0.8,
    "Cap_Rib_Height": 32.0,
    "Cap_Top_Radius": 3.0,
    "Cap_Bottom_Radius": 2.0,
    
    # Neck
    "Neck_Diameter": 38.0,
    "Neck_Height": 14.0,
    
    # Bottom
    "Base_Thickness": 4.0,
    "Recess_Depth": 2.0,
    
    # Split Gap
    "Cap_Split_Gap": 0.5,
}

# ---------------------------------------------------------------------------
# Output path helper
# ---------------------------------------------------------------------------
def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Persil_Detergent_Bottle.prt"

# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------
def make_expressions(part) -> None:
    for name, value in VALUES.items():
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))

def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))

def line(part, a, b):
    return part.Curves.CreateLine(point(*a), point(*b))

def set_name(obj, name: str) -> None:
    try:
        obj.SetName(name)
    except Exception:
        pass

def set_body_color(part, body, color_index: int):
    try:
        display_modification = NXOpen.Session.GetSession().DisplayManager.NewDisplayModification()
        display_modification.NewColor = color_index
        display_modification.Apply([body])
    except Exception as exc:
        print("  [WARN] Failed to set body color: {}".format(exc))

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
        
        if draft_angle_rhs is not None:
            draft = builder.Draft
            draft.DraftOption = NXOpen.GeometricUtilities.SimpleDraftSimpleDraftType.SimpleFromStart
            draft.FrontDraftAngle.RightHandSide = str(draft_angle_rhs)
            
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

def extrude_y(part, curves, start_rhs, end_rhs, name, target=None, subtract=False, draft_angle_rhs=None):
    return extrude(part, curves, vec(0.0, 1.0, 0.0), start_rhs, end_rhs, name, target, subtract, draft_angle_rhs)

def extrude_z(part, curves, start_rhs, end_rhs, name, target=None, subtract=False):
    return extrude(part, curves, vec(0.0, 0.0, 1.0), start_rhs, end_rhs, name, target, subtract)

# ---------------------------------------------------------------------------
# Revolve
# ---------------------------------------------------------------------------
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
# Cylinder primitive
# ---------------------------------------------------------------------------
def cylinder(part, origin, diameter_rhs, height_rhs, name):
    builder = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        direction = part.Directions.CreateDirection(
            origin,
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Axis.Point.SetCoordinates(origin)
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
# Edge Helpers
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

def face_z(face):
    try:
        face_type, origin, direction, bbox, radius, flag1, flag2 = UF.Modeling.AskFaceData(face.Tag)
        return float(origin[2])
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Shell uniform wall thickness
# ---------------------------------------------------------------------------
def shell_bottle(part, body, top_z, thickness_rhs):
    faces = []
    for face in list(body.GetFaces() or []):
        z = face_z(face)
        if z is not None and abs(z - top_z) < 0.5:
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
        builder.DefaultThickness.RightHandSide = str(thickness_rhs)
        builder.Tolerance = 0.01
        collector = part.ScCollectors.CreateCollector()
        collector.ReplaceRules([part.ScRuleFactory.CreateRuleFaceDumb(faces)], False)
        builder.RemovedFacesCollector = collector
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, "SHELL_BOTTLE_BODY")
    return feat.GetBodies()[0] if feat.GetBodies() else body

# ---------------------------------------------------------------------------
# Symmetrical Rounded Rectangle Curves
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

# ---------------------------------------------------------------------------
# Slot Curves in XZ plane
# ---------------------------------------------------------------------------
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
# Revolve cap body with dome
# ---------------------------------------------------------------------------
def cap_revolve_curves(part, cx, cz_start):
    r_cap = 26.0
    h_cyl = 32.0
    h_cap = 42.0
    r_dome = 38.8
    z_dome_center = cz_start + 3.2
    
    start_angle = math.atan2(28.8, 26.0)
    end_angle = math.pi / 2.0
    
    return [
        line(part, (cx, 0.0, cz_start), (cx + r_cap, 0.0, cz_start)),
        line(part, (cx + r_cap, 0.0, cz_start), (cx + r_cap, 0.0, cz_start + h_cyl)),
        part.Curves.CreateArc(
            point(cx, 0.0, z_dome_center),
            vec(1.0, 0.0, 0.0),
            vec(0.0, 0.0, 1.0),
            r_dome,
            start_angle,
            end_angle
        ),
        line(part, (cx, 0.0, cz_start + h_cap), (cx, 0.0, cz_start)),
    ]

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

    print("Building detergent bottle CAD model with 5 segments")
    make_expressions(part)

    # Offset neck to the left of the handle opening
    X_neck = -28.5

    # ---------------------------------------------------------------------------
    # SEGMENT 1 (Brown) — Outer Bottle Shell with Integrated Handle
    # ---------------------------------------------------------------------------
    hw_bottom = 155.0 * 0.5
    hw_max = 165.0 * 0.5
    hw_top = 70.0 * 0.5
    
    # 1. Extrude the main body profile (symmetrically along Y by 95mm)
    s1_body_curves = [
        line(part, (-hw_bottom, 0.0, 0.0), (hw_bottom, 0.0, 0.0)),
        line(part, (hw_bottom, 0.0, 0.0), (hw_max, 0.0, 120.0)),
        line(part, (hw_max, 0.0, 120.0), (75.0, 0.0, 220.0)),
        line(part, (75.0, 0.0, 220.0), (X_neck + hw_top, 0.0, 265.0)),
        line(part, (X_neck + hw_top, 0.0, 265.0), (X_neck - hw_top, 0.0, 265.0)),
        line(part, (X_neck - hw_top, 0.0, 265.0), (-70.0, 0.0, 220.0)),
        line(part, (-70.0, 0.0, 220.0), (-hw_max, 0.0, 100.0)),
        line(part, (-hw_max, 0.0, 100.0), (-hw_bottom, 0.0, 0.0)),
    ]
    _, body = extrude_y(part, s1_body_curves, "-47.5", "47.5", "EXTRUDE_S1_MAIN")
    print("[OK] S1 main body extruded")

    # 2. Apply Edge Blends to vertical corners BEFORE adding other features
    # Both left and right corners are blended with 11.5mm to avoid overlap with the neck cylinder and handle opening
    blend_edges(
        part, body,
        lambda e: not edge_horizontal(e) and edge_mid(e)[2] < 265.0,
        "11.5",
        "EDGE_BLEND_S1_OVAL_LOOPS",
    )
    print("[OK] S1 vertical corners rounded")

    # 2b. Bottom base edge (filleted while solid to prevent thin ring collision)
    blend_edges(
        part, body,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2]) < 0.5,
        "S1_Bottom_Edge_Radius",
        "EDGE_BLEND_S1_BOTTOM",
    )
    print("[OK] S1 bottom corners rounded")

    # 3. Add Neck cylinder and Unite
    _, neck_cylinder = cylinder(part, point(X_neck, 0.0, 265.0), "Neck_Diameter", "Neck_Height", "CYLINDER_NECK")
    builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        builder.Target = body
        builder.Tool = neck_cylinder
        feat = builder.CommitFeature()
        set_name(feat, "UNITE_NECK")
        bodies = feat.GetBodies()
        if bodies:
            body = bodies[0]
    finally:
        builder.Destroy()
    print("[OK] Neck cylinder united with S1")

    # 3b. Shell outer body (removing top neck face at Z=279)
    # Shell is done early on the simple solid to guarantee success
    body = shell_bottle(part, body, 279.0, "S1_Wall_Thickness")
    print("[OK] S1 shelled successfully")

    # 4. Bottom Recess subtraction (offset 6mm to allow 2.5mm shell wall thickness, depth 2mm)
    recess_curves = rounded_rect_curves(part, 0.0, 143.0, 83.0, 14.0, cx=0.0)
    _, body = extrude_z(part, recess_curves, "-1.0", "Recess_Depth", "EXTRUDE_RECESS", target=body, subtract=True)
    print("[OK] Bottom recess subtracted")

    # 5. Handle Opening cutout slot
    handle_slot_curves = slot_profile_xz(part, 28.5, 120.0, 60.0, 140.0)
    _, body = extrude_y(part, handle_slot_curves, "-60.0", "60.0", "EXTRUDE_HANDLE_SLOT", target=body, subtract=True)
    print("[OK] Handle opening slot cut out")

    # 6. Apply remaining edge blends
    
    # Handle opening loop blend (rounds inside slot with 2.0mm to fit within 2.5mm wall thickness)
    blend_edges(
        part, body,
        lambda e: (
            edge_points(e) is not None
            and abs(edge_mid(e)[0] - 28.5) < 35.0
            and abs(edge_mid(e)[2] - 120.0) < 75.0
            and abs(edge_mid(e)[1]) > 46.0
        ),
        "2.0",
        "EDGE_BLEND_HANDLE_OPENING",
    )
    
    # Neck fillet
    blend_edges(
        part, body,
        lambda e: (
            abs(edge_mid(e)[2] - 265.0) < 0.5
            and math.hypot(edge_mid(e)[0] - X_neck, edge_mid(e)[1]) < 20.0
        ),
        "Recess_Depth",
        "EDGE_BLEND_NECK_BASE",
    )
    print("[OK] S1 edge blends applied")

    set_body_color(part, body, 104) # Brown
    print("[OK] S1 completed and colored Brown")

    # ---------------------------------------------------------------------------
    # SEGMENT 2 (Light Blue) — Main Internal Bottle Volume
    # ---------------------------------------------------------------------------
    s2_profile = [
        line(part, (X_neck - 46.0, 0.0, 49.0), (X_neck + 46.0, 0.0, 49.0)),
        line(part, (X_neck + 46.0, 0.0, 49.0), (X_neck + 54.0, 0.0, 150.0)),
        line(part, (X_neck + 54.0, 0.0, 150.0), (X_neck + 19.0, 0.0, 264.0)),
        line(part, (X_neck + 19.0, 0.0, 264.0), (X_neck - 19.0, 0.0, 264.0)),
        line(part, (X_neck - 19.0, 0.0, 264.0), (X_neck - 54.0, 0.0, 150.0)),
        line(part, (X_neck - 54.0, 0.0, 150.0), (X_neck - 46.0, 0.0, 49.0)),
    ]
    _, s2_body = extrude_y(part, s2_profile, "-35.0", "35.0", "EXTRUDE_S2")
    blend_edges(
        part, s2_body,
        lambda e: not edge_horizontal(e) and edge_mid(e)[2] < 265.0,
        "15.0",
        "EDGE_BLEND_S2",
    )
    set_body_color(part, s2_body, 153) # Light Blue
    print("[OK] S2 body created and colored Light Blue")

    # ---------------------------------------------------------------------------
    # SEGMENT 3 (Dark Blue) — Upper Shoulder Transition
    # ---------------------------------------------------------------------------
    s3_profile = [
        line(part, (X_neck - 26.0, 0.0, 232.0), (X_neck + 26.0, 0.0, 232.0)),
        line(part, (X_neck + 26.0, 0.0, 232.0), (X_neck + 26.0, 0.0, 264.0)),
        line(part, (X_neck + 26.0, 0.0, 264.0), (X_neck - 26.0, 0.0, 264.0)),
        line(part, (X_neck - 26.0, 0.0, 264.0), (X_neck - 26.0, 0.0, 232.0)),
    ]
    _, s3_body = extrude_y(part, s3_profile, "-21.0", "21.0", "EXTRUDE_S3")
    blend_edges(
        part, s3_body,
        lambda e: not edge_horizontal(e),
        "S3_Blend_Radius",
        "EDGE_BLEND_S3",
    )
    set_body_color(part, s3_body, 211) # Dark Blue
    print("[OK] S3 body created and colored Dark Blue")

    # ---------------------------------------------------------------------------
    # SEGMENT 4 (Orange) — Bottom Volume Transition
    # ---------------------------------------------------------------------------
    s4_profile = [
        line(part, (X_neck - 35.0, 0.0, 4.0), (X_neck + 35.0, 0.0, 4.0)),
        line(part, (X_neck + 35.0, 0.0, 4.0), (X_neck + 35.0, 0.0, 49.0)),
        line(part, (X_neck + 35.0, 0.0, 49.0), (X_neck - 35.0, 0.0, 49.0)),
        line(part, (X_neck - 35.0, 0.0, 49.0), (X_neck - 35.0, 0.0, 4.0)),
    ]
    _, s4_body = extrude_y(part, s4_profile, "-21.0", "21.0", "EXTRUDE_S4")
    blend_edges(
        part, s4_body,
        lambda e: not edge_horizontal(e),
        "20.0",
        "EDGE_BLEND_S4",
    )
    set_body_color(part, s4_body, 36) # Orange
    print("[OK] S4 body created and colored Orange")

    # ---------------------------------------------------------------------------
    # SEGMENT 5 (Pink) — Cap
    # ---------------------------------------------------------------------------
    cap_z = 268.0
    cap_curves = cap_revolve_curves(part, X_neck, cap_z)
    _, cap = revolve_axis(part, cap_curves, "0", "360", [X_neck, 0.0, 0.0], [0.0, 0.0, 1.0], "REVOLVE_CAP")
    
    # Bottom fillet (2 mm)
    blend_edges(
        part, cap,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2] - cap_z) < 0.5,
        "Cap_Bottom_Radius",
        "EDGE_BLEND_CAP_BOTTOM",
    )
    
    # Grip ribs
    # Count: 44, Width: 1.4, Depth: 0.8, Height: 32 (Z=268 to 300)
    rib_curves = [
        line(part, (X_neck + 25.95, -0.7, 268.0), (X_neck + 26.8, -0.7, 268.0)),
        line(part, (X_neck + 26.8, -0.7, 268.0), (X_neck + 26.8, 0.7, 268.0)),
        line(part, (X_neck + 26.8, 0.7, 268.0), (X_neck + 25.95, 0.7, 268.0)),
        line(part, (X_neck + 25.95, 0.7, 268.0), (X_neck + 25.95, -0.7, 268.0)),
    ]
    rib_feat, _ = extrude_z(part, rib_curves, "0", "Cap_Rib_Height", "EXTRUDE_RIB", target=cap)
    
    # Pattern features circular
    builder = part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.FeatureList.Add([rib_feat])
        service = builder.PatternService
        service.PatternType = NXOpen.GeometricUtilities.PatternDefinition.PatternEnum.Circular
        circ = service.CircularDefinition
        circ.RotationAxis = part.Axes.CreateAxis(
            point(X_neck, 0.0, cap_z),
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        circ.RotationCenter = part.Points.CreatePoint(point(X_neck, 0.0, cap_z))
        circ.IncludeSeedToggle = True
        circ.AngularSpacing.NCopies.RightHandSide = "Cap_Rib_Count"
        circ.AngularSpacing.PitchAngle.RightHandSide = "360.0 / Cap_Rib_Count"
        builder.CommitFeature()
    finally:
        builder.Destroy()
        
    set_body_color(part, cap, 181) # Pink
    print("[OK] Cap body created, ribs patterned, and colored Pink")

    # ---- SAVE AND FIT ----
    try:
        part.ModelingViews.WorkView.Fit()
    except Exception:
        pass
    
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    
    # Write output to log and launch files
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
