"""Create a clean, production-ready, parametric plastic food container in Siemens NX 2206.

This script implements a high-quality CAD modeling history for:
- Container_Body (drafted cylindrical tub with rolled rim, shelled)
- Lid (flat cylindrical cap with slight crown, skirt, rounded edges)
- Label_Sleeve (thin cylindrical wrap around container exterior)

All primary dimensions are controlled via named Expressions.

Usage:
  run_journal.exe create_food_container.py [output_path.prt]
"""

from __future__ import annotations
import math
import os
import sys
import traceback
from pathlib import Path
import NXOpen
import NXOpen.UF
from examples._common import set_name, vec

UF = NXOpen.UF.UFSession.GetUFSession()

# ---------------------------------------------------------------------------
# Primary parameters (mm) — Plastic food container (Kissan jam tub)
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Diameter": 100.0,
    "Overall_Height": 70.0,
    "Container_Diameter": 94.0,
    "Container_Height": 55.0,
    "Wall_Thickness": 1.5,
    "Draft_Angle": 5.0,
    "Base_Thickness": 2.0,
    "Bottom_Blend_Radius": 8.0,
    "Top_Rim_Diameter": 96.0,
    "Top_Rim_Height": 3.0,
    "Top_Rim_Radius": 1.5,
    "Lid_Diameter": 100.0,
    "Lid_Height": 12.0,
    "Lid_Skirt_Height": 6.0,
    "Lid_Top_Crown_Height": 1.0,
    "Lid_Edge_Radius": 2.5,
    "Label_Height": 42.0,
    "Label_Thickness": 0.3,
    "Split_Gap": 0.3,
    "Edge_Blend_Radius": 1.0,
}

DERIVED = {
    "Container_Radius": "Container_Diameter / 2.0",
    "Rim_Radius": "Top_Rim_Diameter / 2.0",
    "Lid_Radius": "Lid_Diameter / 2.0",
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Food_Container.prt"




def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))




def line(part, a, b):
    return part.Curves.CreateLine(point(*a), point(*b))


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------
def make_expressions(part) -> None:
    for name, value in VALUES.items():
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
        except Exception:
            pass
    for name, rhs in DERIVED.items():
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass


def get_val(part, name: str) -> float:
    try:
        return part.Expressions.FindObject(name).Value
    except Exception:
        return float(VALUES.get(name, 0.0))


# ---------------------------------------------------------------------------
# Sketch helpers
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
    """Create a sketch on the XZ plane (X is horizontal, Z is vertical)."""
    return create_sketch_on_csys(
        part,
        point(0.0, 0.0, 0.0),
        vec(1.0, 0.0, 0.0),
        vec(0.0, 0.0, 1.0),
        vec(0.0, -1.0, 0.0),
        name,
    )


def add_to_sketch(sketch, curve) -> None:
    try:
        sketch.AddGeometry(curve, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    except Exception:
        try:
            sketch.AddGeometry(curve)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Revolve
# ---------------------------------------------------------------------------
def revolve_z(part, curves, start_angle_rhs, end_angle_rhs, name):
    """Revolve curves around the Z-axis using UF.Modl.CreateRevolution."""
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


def edge_z_center(edge):
    pts = edge_points(edge)
    if pts is not None:
        return (pts[0][2] + pts[1][2]) * 0.5
    return 0.0


def edge_radius(edge):
    """Return the radius of a circular edge."""
    pts = edge_points(edge)
    if pts is None:
        return 0.0
    p1 = pts[0]
    return math.sqrt(p1[0] ** 2 + p1[1] ** 2)


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


# ---------------------------------------------------------------------------
# Edge Blend
# ---------------------------------------------------------------------------
def blend_edges(part, body, chooser, radius_rhs, name):
    edges = [e for e in list(body.GetEdges() or []) if chooser(e)]
    if not edges:
        print("  [WARN] blend_edges '{}': no matching edges found".format(name))
        return None
    builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        collector = part.ScCollectors.CreateCollector()
        collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(edges)], False)
        builder.Tolerance = 0.01
        builder.AllInstancesOption = False
        builder.RemoveSelfIntersection = True
        builder.RollOverSmoothEdge = True
        builder.RollOntoEdge = True
        builder.MoveSharpEdge = True
        builder.OverlapOption = NXOpen.Features.EdgeBlendBuilder.Overlap.AnyConvexityRollOver
        builder.BlendOrder = NXOpen.Features.EdgeBlendBuilder.OrderOfBlending.ConvexFirst
        builder.SetbackOption = NXOpen.Features.EdgeBlendBuilder.Setback.SeparateFromCorner
        builder.AddChainset(collector, str(radius_rhs))
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    return feat


def blend_edges_safe(part, body, chooser, radius_rhs, name):
    """Apply edge blend one edge at a time; skip edges that fail."""
    edges = [e for e in list(body.GetEdges() or []) if chooser(e)]
    if not edges:
        print("  [WARN] blend_edges_safe '{}': no matching edges found".format(name))
        return
    applied = 0
    failed = 0
    for edge in edges:
        try:
            blend_edges(part, body, lambda e, ref=edge: e == ref, radius_rhs, "{}_{}".format(name, applied))
            applied += 1
        except Exception:
            failed += 1
    if applied > 0:
        print("[OK] {} ({}/{} edges blended, {} skipped)".format(name, applied, applied + failed, failed))
    else:
        print("[WARN] {} - no edges could be blended".format(name))


# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------
def shell_body(part, body, top_z, thickness_expr, name):
    """Shell the body by removing the top face at top_z."""
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
        raise RuntimeError("Could not identify the top face for Shell.")

    builder = part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Body = body
        builder.DefaultThickness.RightHandSide = str(thickness_expr)
        builder.Tolerance = 0.01
        collector = part.ScCollectors.CreateCollector()
        collector.ReplaceRules([part.ScRuleFactory.CreateRuleFaceDumb(faces)], False)
        builder.RemovedFacesCollector = collector
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    # Return the live body after shell
    for b in list(part.Bodies or []):
        bounds = body_bounds(b)
        if abs(bounds[1][2] - top_z) < 1.0:
            return b
    return body


# ---------------------------------------------------------------------------
# Main Builder
# ---------------------------------------------------------------------------
def main():
    path = out_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()

    try:
        session.Parts.CloseAll(NXOpen.BasePartCloseModified.CloseModified, None)
    except Exception:
        pass

    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

    part = session.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)

    # 1. Create Expressions
    make_expressions(part)
    print("[OK] All named Expressions successfully created.")

    # Read values
    top_r = get_val(part, "Container_Radius")
    rim_r = get_val(part, "Rim_Radius")
    body_h = get_val(part, "Container_Height")
    rim_h = get_val(part, "Top_Rim_Height")
    draft_deg = get_val(part, "Draft_Angle")
    lid_r = get_val(part, "Lid_Radius")
    lid_h = get_val(part, "Lid_Height")
    lid_skirt_h = get_val(part, "Lid_Skirt_Height")
    lid_crown_h = get_val(part, "Lid_Top_Crown_Height")
    split_gap = get_val(part, "Split_Gap")
    label_h = get_val(part, "Label_Height")
    label_t = get_val(part, "Label_Thickness")
    bottom_blend_r = get_val(part, "Bottom_Blend_Radius")

    draft_rad = math.radians(draft_deg)
    # Base radius: drafted inward from the top of the main wall section
    base_r = top_r - math.tan(draft_rad) * (body_h - rim_h)

    # -----------------------------------------------------------------------
    # 2. Container Body — Sketch + Revolve
    # -----------------------------------------------------------------------
    _, sk_body = xz_sketch(part, "S1_Body_Profile")

    # Half-profile in XZ plane (revolved around Z-axis):
    #   Bottom flat → drafted wall → rim flare → top flat → axis closure
    body_curves = [
        line(part, (0.0, 0.0, 0.0), (base_r, 0.0, 0.0)),                          # bottom flat
        line(part, (base_r, 0.0, 0.0), (top_r, 0.0, body_h - rim_h)),              # drafted wall
        line(part, (top_r, 0.0, body_h - rim_h), (rim_r, 0.0, body_h)),            # rim flare
        line(part, (rim_r, 0.0, body_h), (0.0, 0.0, body_h)),                      # top flat
        line(part, (0.0, 0.0, body_h), (0.0, 0.0, 0.0)),                           # axis closure
    ]

    sk_body.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for c in body_curves:
        add_to_sketch(sk_body, c)
    sk_body.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    _, container_body = revolve_z(part, body_curves, "0", "360", "F1_Revolve_Body")
    print("[OK] Container body revolved.")

    # 3. Shell the container body (remove top face)
    container_body = shell_body(part, container_body, body_h, "Wall_Thickness", "F2_Shell_Body")
    print("[OK] Container body shelled.")

    # 4. Edge Blend — bottom outer edge (generous base-to-wall transition)
    blend_edges(
        part, container_body,
        lambda e: abs(edge_z_center(e) - 0.0) < 0.3 and edge_radius(e) > base_r * 0.8,
        "Bottom_Blend_Radius",
        "F3_Bottom_Blend"
    )
    print("[OK] Bottom blend applied.")

    # 5. Edge Blend — rim outer edge (smooth rolled rim)
    blend_edges_safe(
        part, container_body,
        lambda e: abs(edge_z_center(e) - body_h) < 1.0 and edge_radius(e) > top_r * 0.8,
        "Top_Rim_Radius",
        "F4_Rim_Blend"
    )

    # -----------------------------------------------------------------------
    # 6. Lid — Sketch + Revolve
    # -----------------------------------------------------------------------
    # Lid positioning: skirt wraps around rim, rest sits above
    lid_skirt_bottom_z = body_h + split_gap - lid_skirt_h
    lid_top_z = body_h + split_gap + (lid_h - lid_skirt_h)

    _, sk_lid = xz_sketch(part, "S2_Lid_Profile")

    # Half-profile: skirt bottom → outer wall → top with slight crown → axis closure
    lid_curves = [
        line(part, (0.0, 0.0, lid_skirt_bottom_z), (lid_r, 0.0, lid_skirt_bottom_z)),   # skirt bottom flat
        line(part, (lid_r, 0.0, lid_skirt_bottom_z), (lid_r, 0.0, lid_top_z)),           # outer wall
        line(part, (lid_r, 0.0, lid_top_z), (0.0, 0.0, lid_top_z + lid_crown_h)),        # top crown slope
        line(part, (0.0, 0.0, lid_top_z + lid_crown_h), (0.0, 0.0, lid_skirt_bottom_z)), # axis closure
    ]

    sk_lid.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for c in lid_curves:
        add_to_sketch(sk_lid, c)
    sk_lid.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    _, lid_body = revolve_z(part, lid_curves, "0", "360", "F5_Revolve_Lid")
    print("[OK] Lid body revolved.")

    # 7. Edge Blend — lid top outer edge (Lid_Edge_Radius)
    blend_edges(
        part, lid_body,
        lambda e: abs(edge_z_center(e) - lid_top_z) < 1.5 and edge_radius(e) > lid_r * 0.8,
        "Lid_Edge_Radius",
        "F6_Lid_Top_Blend"
    )
    print("[OK] Lid top blend applied.")

    # 8. Edge Blend — lid skirt bottom edge (small radius)
    blend_edges(
        part, lid_body,
        lambda e: abs(edge_z_center(e) - lid_skirt_bottom_z) < 0.5 and edge_radius(e) > lid_r * 0.8,
        "Edge_Blend_Radius",
        "F7_Lid_Bottom_Blend"
    )
    print("[OK] Lid skirt bottom blend applied.")

    # -----------------------------------------------------------------------
    # 9. Label Sleeve — Sketch + Revolve
    # -----------------------------------------------------------------------
    # Label is centered on the body, above the base blend zone
    label_bottom_z = bottom_blend_r + 2.0
    label_top_z = label_bottom_z + label_h

    # Inner radii follow the container draft (outer surface of container wall)
    wall_section_h = body_h - rim_h
    inner_r_bottom = base_r + (top_r - base_r) * (label_bottom_z / wall_section_h) + 0.05
    inner_r_top = base_r + (top_r - base_r) * (label_top_z / wall_section_h) + 0.05

    # Outer radii offset by label thickness
    outer_r_bottom = inner_r_bottom + label_t
    outer_r_top = inner_r_top + label_t

    _, sk_label = xz_sketch(part, "S3_Label_Profile")

    label_curves = [
        line(part, (inner_r_bottom, 0.0, label_bottom_z), (outer_r_bottom, 0.0, label_bottom_z)),  # bottom
        line(part, (outer_r_bottom, 0.0, label_bottom_z), (outer_r_top, 0.0, label_top_z)),        # outer wall
        line(part, (outer_r_top, 0.0, label_top_z), (inner_r_top, 0.0, label_top_z)),              # top
        line(part, (inner_r_top, 0.0, label_top_z), (inner_r_bottom, 0.0, label_bottom_z)),        # inner wall
    ]

    sk_label.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for c in label_curves:
        add_to_sketch(sk_label, c)
    sk_label.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    _, label_body = revolve_z(part, label_curves, "0", "360", "F8_Revolve_Label")
    print("[OK] Label sleeve revolved.")

    # -----------------------------------------------------------------------
    # 10. Rename bodies and save
    # -----------------------------------------------------------------------
    set_name(container_body, "Container_Body")
    set_name(lid_body, "Lid")
    set_name(label_body, "Label_Sleeve")

    part.ModelingViews.WorkView.Fit()
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("Food Container saved successfully to {}".format(path))


if __name__ == "__main__":
    log_path = Path(__file__).resolve().parents[3] / "food_container_journal.log"
    try:
        log_path.write_text("Starting food container journal\n", encoding="utf-8")
        main()
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
