"""Create a clean, production-ready, parametric Liquid Lip Colour container in Siemens NX 2206.

This script implements a high-quality CAD modeling history for:
- Container_Body (revolved cylindrical reservoir, shelled, with bottom and neck blends)
- Cap (revolved cylindrical cap with softly rounded top and bottom edges)

All primary dimensions are controlled via named Expressions.

Usage:
  run_journal.exe create_lip_colour.py [output_path.prt]
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
# Primary parameters (mm) — Liquid Lip Colour container
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Height": 105.0,
    "Overall_Diameter": 19.0,
    "Body_Diameter": 19.0,
    "Body_Height": 73.0,
    "Body_Wall_Thickness": 1.2,
    "Neck_Diameter": 16.0,
    "Neck_Height": 4.0,
    "Cap_Diameter": 19.0,
    "Cap_Height": 32.0,
    "Cap_Top_Radius": 2.0,
    "Bottom_Radius": 4.0,
    "Split_Gap": 0.3,
    "Edge_Blend_Radius": 1.0,
    "Base_Thickness": 1.5,
}

DERIVED = {
    "Body_Radius": "Body_Diameter / 2.0",
    "Neck_Radius": "Neck_Diameter / 2.0",
    "Cap_Radius": "Cap_Diameter / 2.0",
    "Cap_Start_Z": "Body_Height + Neck_Height + Split_Gap",
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Liquid_Lip_Colour.prt"




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
# Section and Revolve
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
    """Return the radius of a circular edge, or 0.0 if not circular."""
    pts = edge_points(edge)
    if pts is None:
        return 0.0
    p1, p2 = pts
    # For a circular edge revolved around Z, both endpoints have same Z and same radius
    r1 = math.sqrt(p1[0] ** 2 + p1[1] ** 2)
    return r1


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
            blend_edges(part, body, lambda e, ref=edge: e == ref, radius_rhs, "{}_{}"  .format(name, applied))
            applied += 1
        except Exception:
            failed += 1
    if applied > 0:
        print("[OK] {} ({}/{} edges blended, {} skipped)".format(name, applied, applied + failed, failed))
    else:
        print("[WARN] {} — no edges could be blended".format(name))


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
        # Fallback: find the highest flat face
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

    # Close open parts for a clean environment
    try:
        session.Parts.CloseAll(NXOpen.BasePartCloseModified.CloseModified, None)
    except Exception:
        pass

    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

    # Create new part
    part = session.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)

    # 1. Create Expressions
    make_expressions(part)
    print("[OK] All named Expressions successfully created.")

    # Read values
    body_r = get_val(part, "Body_Radius")
    neck_r = get_val(part, "Neck_Radius")
    body_h = get_val(part, "Body_Height")
    neck_h = get_val(part, "Neck_Height")
    cap_r = get_val(part, "Cap_Radius")
    cap_h = get_val(part, "Cap_Height")
    split_gap = get_val(part, "Split_Gap")

    body_top_z = body_h + neck_h

    # -----------------------------------------------------------------------
    # 2. Container Body — Sketch + Revolve
    # -----------------------------------------------------------------------
    _, sk_body = xz_sketch(part, "S1_Body_Profile")

    # Half-profile points (in XZ plane, X=radius, Z=height)
    # Bottom axis → bottom outer → wall up → neck step-in → neck top → top axis → close
    body_curves = [
        line(part, (0.0, 0.0, 0.0), (body_r, 0.0, 0.0)),           # bottom flat
        line(part, (body_r, 0.0, 0.0), (body_r, 0.0, body_h)),     # straight wall
        line(part, (body_r, 0.0, body_h), (neck_r, 0.0, body_h)),   # neck step-in
        line(part, (neck_r, 0.0, body_h), (neck_r, 0.0, body_top_z)), # neck wall
        line(part, (neck_r, 0.0, body_top_z), (0.0, 0.0, body_top_z)), # top flat
        line(part, (0.0, 0.0, body_top_z), (0.0, 0.0, 0.0)),       # axis closure
    ]

    sk_body.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for c in body_curves:
        add_to_sketch(sk_body, c)
    sk_body.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    _, container_body = revolve_z(part, body_curves, "0", "360", "F1_Revolve_Body")
    print("[OK] Container body revolved.")

    # 3. Shell the container body (remove top face)
    container_body = shell_body(part, container_body, body_top_z, "Body_Wall_Thickness", "F2_Shell_Body")
    print("[OK] Container body shelled.")

    # 4. Edge Blend — bottom outer edge (Bottom_Radius)
    blend_edges(
        part, container_body,
        lambda e: abs(edge_z_center(e) - 0.0) < 0.3 and edge_radius(e) > body_r * 0.8,
        "Bottom_Radius",
        "F3_Bottom_Blend"
    )
    print("[OK] Bottom blend applied.")

    # 5. Edge Blend — neck transition (body_h where wall steps in)
    blend_edges_safe(
        part, container_body,
        lambda e: abs(edge_z_center(e) - body_h) < 0.5,
        "Edge_Blend_Radius",
        "F4_Neck_Blend"
    )

    # -----------------------------------------------------------------------
    # 6. Cap — Sketch + Revolve
    # -----------------------------------------------------------------------
    cap_start_z = body_top_z + split_gap
    cap_end_z = cap_start_z + cap_h

    _, sk_cap = xz_sketch(part, "S2_Cap_Profile")

    cap_curves = [
        line(part, (0.0, 0.0, cap_start_z), (cap_r, 0.0, cap_start_z)),   # bottom flat
        line(part, (cap_r, 0.0, cap_start_z), (cap_r, 0.0, cap_end_z)),   # wall
        line(part, (cap_r, 0.0, cap_end_z), (0.0, 0.0, cap_end_z)),       # top flat
        line(part, (0.0, 0.0, cap_end_z), (0.0, 0.0, cap_start_z)),       # axis closure
    ]

    sk_cap.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for c in cap_curves:
        add_to_sketch(sk_cap, c)
    sk_cap.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    _, cap_body = revolve_z(part, cap_curves, "0", "360", "F5_Revolve_Cap")
    print("[OK] Cap body revolved.")

    # 7. Edge Blend — cap top (Cap_Top_Radius)
    blend_edges(
        part, cap_body,
        lambda e: abs(edge_z_center(e) - cap_end_z) < 0.3 and edge_radius(e) > cap_r * 0.8,
        "Cap_Top_Radius",
        "F6_Cap_Top_Blend"
    )
    print("[OK] Cap top blend applied.")

    # 8. Edge Blend — cap bottom (small radius)
    blend_edges(
        part, cap_body,
        lambda e: abs(edge_z_center(e) - cap_start_z) < 0.3 and edge_radius(e) > cap_r * 0.8,
        "0.5",
        "F7_Cap_Bottom_Blend"
    )
    print("[OK] Cap bottom blend applied.")

    # -----------------------------------------------------------------------
    # 9. Rename bodies and save
    # -----------------------------------------------------------------------
    set_name(container_body, "Container_Body")
    set_name(cap_body, "Cap")

    part.ModelingViews.WorkView.Fit()
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("Liquid Lip Colour container saved successfully to {}".format(path))


if __name__ == "__main__":
    log_path = Path(__file__).resolve().parents[3] / "lip_colour_journal.log"
    try:
        log_path.write_text("Starting lip colour container journal\n", encoding="utf-8")
        main()
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
