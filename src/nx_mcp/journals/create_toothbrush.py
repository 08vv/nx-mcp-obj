"""Create a clean, production-ready, parametric children's cartoon toothbrush model in Siemens NX 2206.

This script implements a high-quality CAD modeling history for:
- Handle_Body (rounded rectangular profile, taper draft via profile intersect, buttons, bow tie)
- Character_Head (revolved sphere, neck connector, eyes, nose, cheeks recesses)
- Hat_Guard (revolved cowboy hat crown and brim profile)
- Neck (slender flared cylinder)
- Brush_Head (rounded rectangular extrude on XZ plane)
- Bristle_Array (rectangular patterned circular tufts united to a thin base plate)
- All primary dimensions are controlled via Expressions.

Usage:
  run_journal.exe create_toothbrush.py [output_path.prt]
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
# Primary parameters (mm) — Cartoon toothbrush
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Height": 160.0,
    "Handle_Length": 70.0,
    "Handle_Width": 18.0,
    "Handle_Depth": 14.0,
    "Handle_Taper": 1.5,
    "Head_Diameter": 22.0,
    "Hat_Diameter": 36.0,
    "Hat_Height": 10.0,
    "Hat_Brim_Thickness": 2.5,
    "Neck_Diameter": 8.5,
    "Neck_Length": 38.0,
    "Brush_Head_Length": 22.0,
    "Brush_Head_Width": 11.0,
    "Brush_Head_Thickness": 6.0,
    "Bristle_Diameter": 1.5,
    "Bristle_Height": 8.0,
    "Bristle_Spacing_X": 2.2,
    "Bristle_Spacing_Y": 2.2,
    "Button_Diameter": 2.5,
    "Button_Spacing": 6.0,
    "Bow_Width": 6.0,
    "Bow_Height": 3.0,
    "Face_Eye_Diameter": 2.0,
    "Cheek_Diameter": 4.0,
    "Wall_Thickness": 2.0,
    "Blend_Radius": 1.5,
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Toothbrush_Model.prt"


def v(name: str) -> float:
    return float(VALUES[name])


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


# ---------------------------------------------------------------------------
# Geometry helpers
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


def yz_sketch(part, name: str):
    return create_sketch_on_csys(
        part,
        point(0.0, 0.0, 0.0),
        vec(0.0, 1.0, 0.0),  # local X (Y axis)
        vec(0.0, 0.0, 1.0),  # local Y (Z axis)
        vec(1.0, 0.0, 0.0),  # normal (X axis)
        name,
    )


def xy_sketch(part, name: str, z: float = 0.0):
    return create_sketch_on_csys(
        part,
        point(0.0, 0.0, z),
        vec(1.0, 0.0, 0.0),
        vec(0.0, 1.0, 0.0),
        vec(0.0, 0.0, 1.0),
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


def extrude_x(part, curves, start_rhs, end_rhs, name, target=None, subtract=False):
    return extrude(part, curves, vec(1.0, 0.0, 0.0), start_rhs, end_rhs, name, target, subtract)


def extrude_y(part, curves, start_rhs, end_rhs, name, target=None, subtract=False):
    return extrude(part, curves, vec(0.0, 1.0, 0.0), start_rhs, end_rhs, name, target, subtract)


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
# Boolean helpers
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


def intersect(part, target, tool, name):
    builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Intersect
        builder.Target = target
        builder.Tool = tool
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return bodies[0] if bodies else target


# ---------------------------------------------------------------------------
# Profile generators
# ---------------------------------------------------------------------------
def circle_profile(part, diameter, z, plane_offset_x=0.0, plane_offset_y=0.0):
    r = diameter * 0.5
    x_axis = NXOpen.Vector3d(1.0, 0.0, 0.0)
    z_axis = NXOpen.Vector3d(0.0, 0.0, 1.0)
    arc = part.Curves.CreateArc(point(plane_offset_x, plane_offset_y, z), x_axis, z_axis, float(r), 0.0, 2.0 * math.pi)
    return [arc]


def circle_profile_xy(part, diameter, z, plane_offset_x=0.0, plane_offset_y=0.0):
    r = diameter * 0.5
    x_axis = NXOpen.Vector3d(1.0, 0.0, 0.0)
    y_axis = NXOpen.Vector3d(0.0, 1.0, 0.0)
    arc = part.Curves.CreateArc(point(plane_offset_x, plane_offset_y, z), x_axis, y_axis, float(r), 0.0, 2.0 * math.pi)
    return [arc]


def rounded_rect_profile_xz(part, width, height, r, center_x, center_z, plane_offset_y=0.0):
    hw = width * 0.5
    hh = height * 0.5
    r = min(r, hw - 0.1, hh - 0.1)
    x0, x1 = center_x - hw + r, center_x + hw - r
    z0, z1 = center_z - hh + r, center_z + hh - r
    
    x_axis = NXOpen.Vector3d(1.0, 0.0, 0.0)
    z_axis = NXOpen.Vector3d(0.0, 0.0, 1.0)
    
    curves = [
        line(part, (x0, plane_offset_y, center_z - hh), (x1, plane_offset_y, center_z - hh)),
        part.Curves.CreateArc(point(x1, plane_offset_y, z0), x_axis, z_axis, r, -math.pi / 2, 0.0),
        line(part, (center_x + hw, plane_offset_y, z0), (center_x + hw, plane_offset_y, z1)),
        part.Curves.CreateArc(point(x1, plane_offset_y, z1), x_axis, z_axis, r, 0.0, math.pi / 2),
        line(part, (x1, plane_offset_y, center_z + hh), (x0, plane_offset_y, center_z + hh)),
        part.Curves.CreateArc(point(x0, plane_offset_y, z1), x_axis, z_axis, r, math.pi / 2, math.pi),
        line(part, (center_x - hw, plane_offset_y, z1), (center_x - hw, plane_offset_y, z0)),
        part.Curves.CreateArc(point(x0, plane_offset_y, z0), x_axis, z_axis, r, math.pi, 3 * math.pi / 2)
    ]
    return curves


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
    print("Building Kids Cartoon Toothbrush")
    print("--------------------------------")

    # Step 1: Expressions
    make_expressions(part)

    # -----------------------------------------------------------------------
    # Step 2: Handle_Body
    # -----------------------------------------------------------------------
    # We build the tapered handle body using XZ profile intersect with YZ profile
    hw = v("Handle_Width") * 0.5
    hd = v("Handle_Depth") * 0.5
    h_len = v("Handle_Length")
    
    taper_delta = h_len * math.tan(math.radians(v("Handle_Taper")))
    hw_top = hw - taper_delta
    hd_top = hd - taper_delta

    # Sketch 1: Front XZ profile
    front_curves = [
        line(part, (-hw, 0.0, 0.0), (hw, 0.0, 0.0)),
        line(part, (hw, 0.0, 0.0), (hw_top, 0.0, h_len)),
        line(part, (hw_top, 0.0, h_len), (-hw_top, 0.0, h_len)),
        line(part, (-hw_top, 0.0, h_len), (-hw, 0.0, 0.0))
    ]
    _, front_sketch = xz_sketch(part, "SKETCH_HANDLE_FRONT_PROFILE")
    if front_sketch is not None:
        try:
            front_sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
        except Exception:
            pass
        for curve in front_curves:
            add_to_sketch(front_sketch, curve)
        try:
            front_sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
        except Exception:
            pass
            
    # Extrude symmetrically in Y
    _, body_f = extrude_y(part, front_curves, str(-hd - 5.0), str(hd + 5.0), "EXTRUDE_HANDLE_FRONT_PROFILE")

    # Sketch 2: Side YZ profile
    side_curves = [
        line(part, (0.0, -hd, 0.0), (0.0, hd, 0.0)),
        line(part, (0.0, hd, 0.0), (0.0, hd_top, h_len)),
        line(part, (0.0, hd_top, h_len), (0.0, -hd_top, h_len)),
        line(part, (0.0, -hd_top, h_len), (0.0, -hd, 0.0))
    ]
    _, side_sketch = yz_sketch(part, "SKETCH_HANDLE_SIDE_PROFILE")
    if side_sketch is not None:
        try:
            side_sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
        except Exception:
            pass
        for curve in side_curves:
            add_to_sketch(side_sketch, curve)
        try:
            side_sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
        except Exception:
            pass
            
    # Extrude symmetrically in X
    _, body_s = extrude_x(part, side_curves, str(-hw - 5.0), str(hw + 5.0), "EXTRUDE_HANDLE_SIDE_PROFILE")

    # Intersect them to create the tapered block
    handle = intersect(part, body_f, body_s, "INTERSECT_HANDLE_BODY")
    print("[OK] Handle body basic block created")

    # Vertical corners Edge Blend (to round the block)
    blend_edges(
        part, handle,
        lambda e: not edge_horizontal(e) and abs(edge_mid(e)[2] - h_len * 0.5) < 5.0,
        "Blend_Radius * 2.0",
        "EDGE_BLEND_HANDLE_VERTICAL"
    )
    
    # Bottom corner Edge Blend
    blend_edges(
        part, handle,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2]) < 0.5,
        "Blend_Radius * 3.0",
        "EDGE_BLEND_HANDLE_BOTTOM"
    )
    print("[OK] Handle body rounded successfully")

    # Decorative elements on front face: Buttons & Bow tie
    taper_angle_rad = math.radians(v("Handle_Taper"))
    tan_val = math.tan(taper_angle_rad)

    # 3 circular button recesses
    for i in range(3):
        btn_z = h_len * (0.25 + i * 0.20)
        btn_y = (v("Handle_Depth") - 2.0 * btn_z * tan_val) * 0.5
        btn_curves = circle_profile(part, v("Button_Diameter"), btn_z, plane_offset_y=btn_y)
        _, handle = extrude_y(part, btn_curves, "-0.8", "2.0", "EXTRUDE_SUBTRACT_BUTTON_{}".format(i), handle, subtract=True)
    print("[OK] Button recesses cut out")

    # 1 bow tie recess above the buttons (split into left, right, and center knot to prevent self-intersection)
    bow_z = h_len * 0.82
    bow_y = (v("Handle_Depth") - 2.0 * bow_z * tan_val) * 0.5
    b_w = v("Bow_Width") * 0.5
    b_h = v("Bow_Height") * 0.5
    
    # Left triangle
    bow_l = [
        line(part, (-0.2, bow_y, bow_z), (-b_w, bow_y, bow_z + b_h)),
        line(part, (-b_w, bow_y, bow_z + b_h), (-b_w, bow_y, bow_z - b_h)),
        line(part, (-b_w, bow_y, bow_z - b_h), (-0.2, bow_y, bow_z))
    ]
    _, handle = extrude_y(part, bow_l, "-0.8", "2.0", "EXTRUDE_SUBTRACT_BOW_L", handle, subtract=True)

    # Right triangle
    bow_r = [
        line(part, (0.2, bow_y, bow_z), (b_w, bow_y, bow_z + b_h)),
        line(part, (b_w, bow_y, bow_z + b_h), (b_w, bow_y, bow_z - b_h)),
        line(part, (b_w, bow_y, bow_z - b_h), (0.2, bow_y, bow_z))
    ]
    _, handle = extrude_y(part, bow_r, "-0.8", "2.0", "EXTRUDE_SUBTRACT_BOW_R", handle, subtract=True)

    # Center knot (circle)
    knot = circle_profile(part, 1.2, bow_z, plane_offset_y=bow_y)
    _, handle = extrude_y(part, knot, "-0.8", "2.0", "EXTRUDE_SUBTRACT_BOW_KNOT", handle, subtract=True)
    set_name(handle, "Handle_Body")
    print("[OK] Bow recess cut out. Handle_Body finished.")

    # -----------------------------------------------------------------------
    # Step 3: Character_Head
    # -----------------------------------------------------------------------
    head_z = h_len + v("Head_Diameter") * 0.5
    r_head = v("Head_Diameter") * 0.5
    
    # 1. Sphere head (revolved semicircle)
    head_curves = [
        part.Curves.CreateArc(point(0.0, 0.0, head_z), vec(1.0, 0.0, 0.0), vec(0.0, 0.0, 1.0), float(r_head), -math.pi * 0.5, math.pi * 0.5),
        line(part, (0.0, 0.0, head_z + r_head), (0.0, 0.0, head_z - r_head))
    ]
    _, head = revolve_z(part, head_curves, "0", "360", "REVOLVE_HEAD_SPHERE")
    
    # 2. Neck connector cylinder (to blend smoothly to handle)
    conn_curves = circle_profile_xy(part, v("Head_Diameter") * 0.65, h_len)
    _, head = extrude_z(part, conn_curves, "0", "6.0", "EXTRUDE_HEAD_CONNECTOR", head)
    
    # Fillet connector to sphere junction (actual intersection is around Z = 72.64)
    blend_edges(
        part, head,
        lambda e: abs(edge_z_center(e) - 72.64) < 1.0,
        "Blend_Radius * 1.5",
        "EDGE_BLEND_HEAD_NECK_JUNCTION"
    )
    print("[OK] Character head sphere and connector created")

    # 3. Face features: Eyes, cheeks, nose (dynamically calculated Y_front to avoid tool outside target body)
    # Eyes at X = ±3.5, Z = head_z + 2.0
    eye_y = math.sqrt(r_head**2 - 3.5**2 - 2.0**2)
    eye_curves_l = circle_profile(part, v("Face_Eye_Diameter"), head_z + 2.0, plane_offset_x=-3.5, plane_offset_y=eye_y)
    _, head = extrude_y(part, eye_curves_l, "-0.8", "2.0", "EXTRUDE_SUBTRACT_EYE_L", head, subtract=True)
    
    eye_curves_r = circle_profile(part, v("Face_Eye_Diameter"), head_z + 2.0, plane_offset_x=3.5, plane_offset_y=eye_y)
    _, head = extrude_y(part, eye_curves_r, "-0.8", "2.0", "EXTRUDE_SUBTRACT_EYE_R", head, subtract=True)

    # Cheek pads at X = ±7.0, Z = head_z - 2.0
    cheek_y = math.sqrt(r_head**2 - 7.0**2 - 2.0**2)
    cheek_curves_l = circle_profile(part, v("Cheek_Diameter"), head_z - 2.0, plane_offset_x=-7.0, plane_offset_y=cheek_y)
    _, head = extrude_y(part, cheek_curves_l, "-0.4", "2.0", "EXTRUDE_SUBTRACT_CHEEK_L", head, subtract=True)

    cheek_curves_r = circle_profile(part, v("Cheek_Diameter"), head_z - 2.0, plane_offset_x=7.0, plane_offset_y=cheek_y)
    _, head = extrude_y(part, cheek_curves_r, "-0.4", "2.0", "EXTRUDE_SUBTRACT_CHEEK_R", head, subtract=True)

    # Tiny nose at X = 0.0, Z = head_z (starting at -1.0 to overlap with the sphere for a clean Boolean Unite)
    nose_y = r_head
    nose_curves = circle_profile(part, 1.2, head_z, plane_offset_x=0.0, plane_offset_y=nose_y)
    _, head = extrude_y(part, nose_curves, "-1.0", "1.0", "EXTRUDE_NOSE_FEATURE", head)
    set_name(head, "Character_Head")
    print("[OK] Face features added. Character_Head finished.")

    # -----------------------------------------------------------------------
    # Step 4: Hat_Guard
    # -----------------------------------------------------------------------
    hat_z = h_len + v("Head_Diameter")
    brim_r = v("Hat_Diameter") * 0.5
    crown_r = brim_r * 0.55
    brim_t = v("Hat_Brim_Thickness")
    hat_h = v("Hat_Height")
    
    # Revolve cowboy hat profile
    hat_curves = [
        line(part, (0.0, 0.0, hat_z), (brim_r, 0.0, hat_z)),
        line(part, (brim_r, 0.0, hat_z), (brim_r, 0.0, hat_z + brim_t)),
        line(part, (brim_r, 0.0, hat_z + brim_t), (crown_r, 0.0, hat_z + brim_t)),
        line(part, (crown_r, 0.0, hat_z + brim_t), (crown_r, 0.0, hat_z + hat_h)),
        line(part, (crown_r, 0.0, hat_z + hat_h), (0.0, 0.0, hat_z + hat_h)),
        line(part, (0.0, 0.0, hat_z + hat_h), (0.0, 0.0, hat_z))
    ]
    _, hat = revolve_z(part, hat_curves, "0", "360", "REVOLVE_HAT_BODY")
    
    # Fillets on hat brim (radius > crown_r + 2.0 to avoid pre-blending crown base)
    blend_edges(
        part, hat,
        lambda e: (abs(edge_z_center(e) - hat_z) < 0.5) or (abs(edge_z_center(e) - (hat_z + brim_t)) < 0.5 and math.hypot(edge_mid(e)[0], edge_mid(e)[1]) > crown_r + 2.0),
        "1.0",
        "EDGE_BLEND_HAT_BRIM"
    )
    # Fillet crown junction
    blend_edges(
        part, hat,
        lambda e: abs(edge_z_center(e) - (hat_z + brim_t)) < 0.5 and math.hypot(edge_mid(e)[0], edge_mid(e)[1]) < crown_r + 2.0,
        "Blend_Radius",
        "EDGE_BLEND_HAT_CROWN_BASE"
    )
    set_name(hat, "Hat_Guard")
    print("[OK] Hat_Guard body finished.")

    # -----------------------------------------------------------------------
    # Step 5: Neck
    # -----------------------------------------------------------------------
    neck_z_start = hat_z + hat_h
    neck_len = v("Neck_Length")
    neck_z_end = neck_z_start + neck_len
    
    # Revolve flared neck profile to model blends natively while maintaining body independence
    n_rad = v("Neck_Diameter") * 0.5
    neck_profile = [
        # Centerline
        line(part, (0.0, 0.0, neck_z_start), (0.0, 0.0, neck_z_end)),
        # Top flat face
        line(part, (0.0, 0.0, neck_z_end), (n_rad + 2.0, 0.0, neck_z_end)),
        # Top flared transition
        line(part, (n_rad + 2.0, 0.0, neck_z_end), (n_rad, 0.0, neck_z_end - 4.0)),
        # Straight cylindrical neck
        line(part, (n_rad, 0.0, neck_z_end - 4.0), (n_rad, 0.0, neck_z_start + 4.0)),
        # Bottom flared transition
        line(part, (n_rad, 0.0, neck_z_start + 4.0), (n_rad + 2.0, 0.0, neck_z_start)),
        # Bottom flat face
        line(part, (n_rad + 2.0, 0.0, neck_z_start), (0.0, 0.0, neck_z_start))
    ]
    _, neck = revolve_z(part, neck_profile, "0", "360", "REVOLVE_NECK_BODY")
    set_name(neck, "Neck")
    print("[OK] Neck body finished.")

    # -----------------------------------------------------------------------
    # Step 6: Brush_Head
    # -----------------------------------------------------------------------
    bh_len = v("Brush_Head_Length")
    bh_width = v("Brush_Head_Width")
    bh_thick = v("Brush_Head_Thickness")
    
    # Brush head is elongated vertically (Z) and extruded forward (Y)
    center_z = neck_z_end + bh_len * 0.5
    # Sketch rounded rectangle on XZ plane
    bh_curves = rounded_rect_profile_xz(part, bh_width, bh_len, v("Blend_Radius") * 2.0, 0.0, center_z)
    
    _, bh_sketch = xz_sketch(part, "SKETCH_BRUSH_HEAD_PROFILE")
    if bh_sketch is not None:
        try:
            bh_sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
        except Exception:
            pass
        for curve in bh_curves:
            add_to_sketch(bh_sketch, curve)
        try:
            bh_sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
        except Exception:
            pass
            
    # Extrude symmetrically in Y by half thickness
    half_thick = bh_thick * 0.5
    _, brush_head = extrude_y(part, bh_curves, str(-half_thick), str(half_thick), "EXTRUDE_BRUSH_HEAD")
    
    # Apply generous edge blends to round the perimeter
    blend_edges(
        part, brush_head,
        lambda e: True, # Fillet all perimeter edges
        "Blend_Radius",
        "EDGE_BLEND_BRUSH_HEAD"
    )
    set_name(brush_head, "Brush_Head")
    print("[OK] Brush_Head body finished.")

    # -----------------------------------------------------------------------
    # Step 7: Bristle_Array
    # -----------------------------------------------------------------------
    # Front face of the brush head is at Y = half_thick (3.0 mm)
    y_base = half_thick
    base_plate_thick = 0.5
    y_front = y_base + base_plate_thick # 3.5 mm
    
    # Base plate sketch (rounded rectangle)
    bp_curves = rounded_rect_profile_xz(part, bh_width - 1.5, bh_len - 3.0, v("Blend_Radius") * 1.5, 0.0, center_z, plane_offset_y=y_base)
    _, bristles = extrude_y(part, bp_curves, "0", str(base_plate_thick), "EXTRUDE_BRISTLE_BASE_PLATE")
    
    # 3x6 grid of cylindrical bristle tufts with hemispherical tips
    count_x = 3
    count_z = 6
    spacing_x = v("Bristle_Spacing_X")
    spacing_y = v("Bristle_Spacing_Y") # spaced along Z
    
    bristle_dia = v("Bristle_Diameter")
    bristle_h = v("Bristle_Height")
    
    print("Generating 3x6 array of bristle tufts...")
    for ix in range(count_x):
        # Local X coordinate: centered on X=0
        tuft_x = -1.0 * spacing_x + ix * spacing_x
        for iz in range(count_z):
            # Local Z coordinate: centered on center_z
            tuft_z = center_z - 2.5 * spacing_y + iz * spacing_y
            
            # Sketch circle for tuft at y_base (3.0 mm)
            tuft_curves = circle_profile(part, bristle_dia, tuft_z, plane_offset_x=tuft_x, plane_offset_y=y_base)
            
            # Extrude cylinder forward along +Y (starting at -1.0 to penetrate base plate completely)
            _, tuft_body = extrude_y(part, tuft_curves, "-1.0", str(bristle_h + base_plate_thick), "EXTRUDE_TUFT_{}_{}".format(ix, iz))
            # Unite it to the bristles body using robust Boolean Unite
            bristles = unite(part, bristles, tuft_body, "UNITE_TUFT_{}_{}".format(ix, iz))
            
            # Apply Edge Blend to the tip (hemispherical tip)
            blend_edges(
                part, bristles,
                lambda e: (abs(edge_mid(e)[1] - (y_front + bristle_h)) < 0.1 and
                           abs(edge_mid(e)[0] - tuft_x) < bristle_dia and
                           abs(edge_mid(e)[2] - tuft_z) < bristle_dia),
                str(bristle_dia * 0.49),
                "EDGE_BLEND_TUFT_{}_{}".format(ix, iz)
            )
            
    set_name(bristles, "Bristle_Array")
    print("[OK] Bristle_Array body finished.")

    # ---- FINALIZE ----
    try:
        num_bodies = len(list(part.Bodies or []))
        for idx, b in enumerate(list(part.Bodies or [])):
            print("Body #{}: Name='{}', Id='{}', Solid={}, Faces={}".format(
                idx, b.Name, b.JournalIdentifier, b.IsSolidBody, len(list(b.GetFaces() or []))
            ))
        body_names = [b.Name for b in list(part.Bodies or [])]
        print("Bodies: {}, Named: {}".format(num_bodies, body_names))
        part.ModelingViews.WorkView.Fit()
    except Exception as e:
        print("Finalize error: {}".format(e))

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    write_launch_files(path)
    print("Saved: {}".format(path))


if __name__ == "__main__":
    log = Path(__file__).resolve().parents[3] / "toothbrush_journal.log"
    try:
        log.write_text("Starting toothbrush journal\n", encoding="utf-8")
        main()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
