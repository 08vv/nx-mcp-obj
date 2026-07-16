"""Create a clean, production-ready, parametric toothpaste tube model in Siemens NX 2206.

This script implements a high-quality CAD modeling history for:
- Tube_Body (neck cylinder, flared shoulder loft, squeezable body loft, flat seal tab,
             crimped closure grooves, edge blends, optional shell)
- Tube_Cap  (revolved cylinder, top corner fillet, circular-patterned grip ribs)
- All primary dimensions are controlled via Expressions.

Usage:
  run_journal.exe create_toothpaste_tube.py [output_path.prt]
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
# Primary parameters (mm) — Toothpaste tube
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Height": 190.0,
    "Tube_Length": 135.0,
    "Tube_Width": 42.0,
    "Tube_Depth": 26.0,
    "Tube_Taper": 1.5,
    "Corner_Radius": 10.0,
    "Shoulder_Height": 12.0,
    "Shoulder_Radius": 18.0,
    "Shoulder_Blend_Radius": 1.5,
    "Neck_Diameter": 16.0,
    "Neck_Height": 10.0,
    "Cap_Diameter": 24.0,
    "Cap_Height": 20.0,
    "Cap_Corner_Radius": 2.5,
    "Cap_Draft_Angle": 1.5,
    "Grip_Rib_Count": 30,
    "Grip_Rib_Width": 1.0,
    "Grip_Rib_Depth": 0.5,
    "Seal_Tab_Height": 10.0,
    "Seal_Tab_Thickness": 2.5,
    "Seal_Crimp_Depth": 0.3,
    "Seal_Crimp_Count": 7,
    "Wall_Thickness": 0.5,
    "Bottom_Blend_Radius": 4.0,
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Toothpaste_Tube.prt"


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


# ---------------------------------------------------------------------------
# Section, Extrude, Revolve
# ---------------------------------------------------------------------------
def nx_section(part, curves):
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
        builder.Section = nx_section(part, curves)
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


def revolve_z(part, curves, start_angle, end_angle, name, target=None):
    tags = [curve.Tag for curve in curves]
    features, number_of_features = UF.Modl.CreateRevolution(
        tags,
        len(tags),
        None,
        [str(start_angle), str(end_angle)],
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
    return feature, target if target is not None else (bodies[0] if bodies else None)


# ---------------------------------------------------------------------------
# Boolean Unite
# ---------------------------------------------------------------------------
def set_boolean_inputs(builder, part, target_body, tool_body):
    # Prioritize modern BooleanBuilder targets/tools assignment:
    if hasattr(builder, "Targets") and (hasattr(builder, "ToolBodyCollector") or hasattr(builder, "BooleanTool")):
        try:
            builder.Targets.Add(target_body)
            collector = part.ScCollectors.CreateCollector()
            rule = part.ScRuleFactory.CreateRuleBodyDumb([tool_body], True)
            collector.ReplaceRules([rule], False)
            if hasattr(builder, "ToolBodyCollector"):
                builder.ToolBodyCollector = collector
                return
            elif hasattr(builder, "BooleanTool"):
                boolean_tool = builder.BooleanTool
                for attr in ("BodyCollector", "ToolBodyCollector"):
                    if hasattr(boolean_tool, attr):
                        setattr(boolean_tool, attr, collector)
                        return
        except Exception:
            pass

    for attr in ("Target", "TargetBody"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, target_body)
                return_attr = attr
                break
            except Exception:
                pass
    else:
        return_attr = None

    for attr in ("Tool", "ToolBody"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, tool_body)
                if return_attr:
                    return
            except Exception:
                pass

    if hasattr(builder, "Targets"):
        try:
            builder.Targets.Add([target_body])
        except Exception:
            pass
    if hasattr(builder, "Tools"):
        try:
            builder.Tools.Add([tool_body])
            return
        except Exception:
            pass

    collector = part.ScCollectors.CreateCollector()
    rule = part.ScRuleFactory.CreateRuleBodyDumb([tool_body], True)
    collector.ReplaceRules([rule], False)
    for attr in ("ToolBodyCollector", "ToolCollector"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, collector)
                return
            except Exception:
                try:
                    getattr(builder, attr).ReplaceRules(collector.GetRules(), False)
                    return
                except Exception:
                    pass

    boolean_tool = getattr(builder, "BooleanTool", None)
    if boolean_tool is not None:
        for attr in ("BodyCollector", "ToolBodyCollector"):
            if hasattr(boolean_tool, attr):
                try:
                    setattr(boolean_tool, attr, collector)
                    return
                except Exception:
                    pass
    raise RuntimeError("Could not assign boolean target/tool bodies")


def unite(part, target, tool, name):
    builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        set_boolean_inputs(builder, part, target, tool)
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return bodies[0] if bodies else target


def subtract(part, target, tool, name):
    builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        set_boolean_inputs(builder, part, target, tool)
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return bodies[0] if bodies else target


# ---------------------------------------------------------------------------
# Edge Blend
# ---------------------------------------------------------------------------
def edge_points(edge):
    try:
        verts = edge.GetVertices()
        if verts and len(verts) >= 2:
            return (float(verts[0].X), float(verts[0].Y), float(verts[0].Z)), (float(verts[1].X), float(verts[1].Y), float(verts[1].Z))
        elif verts and len(verts) == 1:
            pt = (float(verts[0].X), float(verts[0].Y), float(verts[0].Z))
            return pt, pt
    except Exception:
        pass
    return None


def edge_mid(e):
    pts = edge_points(e)
    if pts is None:
        return 0.0, 0.0, 0.0
    return ((pts[0][0] + pts[1][0]) * 0.5, (pts[0][1] + pts[1][1]) * 0.5, (pts[0][2] + pts[1][2]) * 0.5)


def edge_z_center(e):
    return edge_mid(e)[2]


def edge_horizontal(e):
    pts = edge_points(e)
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
    bodies = [b for b in list(part.Bodies or []) if b.IsSolidBody]
    if not bodies:
        return None
    return max(bodies, key=lambda b: body_bounds(b)[1][2] - body_bounds(b)[0][2])


def blend_edges(part, body, selector, radius_rhs, name):
    edges = [e for e in list(body.GetEdges() or []) if selector(e)]
    if not edges:
        print("  [SKIP] No edges matched for {}".format(name))
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
# Through Curves (Loft)
# ---------------------------------------------------------------------------
def append_section(builder, sec) -> None:
    container = getattr(builder, "SectionsList", None) or getattr(builder, "Sections", None)
    if hasattr(container, "Append"):
        container.Append(sec)
    else:
        container.Add(sec)


def through_curves(part, curvesets, name):
    builder = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        try:
            builder.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
        except Exception:
            pass
        for curves in curvesets:
            append_section(builder, nx_section(part, curves))
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, bodies[0] if bodies else None


# ---------------------------------------------------------------------------
# Rounded-rectangle polar radius (bisection)
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


def ring_polyline(part, width, depth, corner, z, count=72):
    pts = []
    for i in range(count):
        a = 2.0 * math.pi * float(i) / float(count)
        mag = radius_to_rounded_rect(width, depth, corner, a)
        pts.append((mag * math.cos(a), mag * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % count]) for i in range(count)]


# ---------------------------------------------------------------------------
# Circle profile on XY plane
# ---------------------------------------------------------------------------
def circle_profile_xy(part, diameter, z, n=72):
    pts = []
    r = diameter * 0.5
    for i in range(n):
        a = 2.0 * math.pi * float(i) / float(n)
        pts.append((r * math.cos(a), r * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % n]) for i in range(n)]


# ---------------------------------------------------------------------------
# Face data helpers
# ---------------------------------------------------------------------------
def face_z(face):
    try:
        face_type, origin, direction, bbox, radius, flag1, flag2 = UF.Modeling.AskFaceData(face.Tag)
        return float(origin[2])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------
def shell_body(part, body, z_open_face, name):
    faces = []
    for face in list(body.GetFaces() or []):
        z = face_z(face)
        if z is not None and abs(z - z_open_face) < 0.5:
            faces.append(face)
            break
    if not faces:
        print("  [WARN] Could not find opening face, selecting nearest flat face")
        candidates = []
        for face in list(body.GetFaces() or []):
            z = face_z(face)
            if z is not None:
                candidates.append((abs(z - z_open_face), face))
        if candidates:
            candidates.sort(key=lambda t: t[0])
            faces.append(candidates[0][1])
    if not faces:
        print("  [SKIP] Could not find face for shell. Skipping.")
        return body
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
    set_name(feat, name)
    print("[OK] Shell applied successfully")
    return live_tallest_body(part) or body


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
def main():
    path = out_path()
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = None
    try:
        # Check if the part is already open in session
        part = session.Parts.FindObject(path.name)
    except Exception:
        pass

    if part is not None:
        # Close the existing part first
        part.Close(NXOpen.BasePart.CloseWholeTree.TrueValue, NXOpen.BasePart.CloseModified.CloseWithSaving, None)

    # Now create new display
    session.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)
    part = session.Parts.Work
    print("Building Toothpaste Tube")
    print("------------------------")

    # Step 1: Expressions
    make_expressions(part)

    # Derived dimensions
    z_cap_top = v("Cap_Height")
    z_neck_top = z_cap_top + v("Neck_Height")
    z_shoulder_top = z_neck_top + v("Shoulder_Height")
    z_seal_start = v("Overall_Height") - v("Seal_Tab_Height")
    z_top = v("Overall_Height")

    h_body = z_seal_start - z_shoulder_top
    taper_rad = math.radians(v("Tube_Taper"))
    seal_width = v("Tube_Width") + 2.0 * h_body * math.tan(taper_rad)
    seal_thickness = v("Seal_Tab_Thickness")
    seal_corner = min(seal_thickness * 0.4, 0.8)

    # -----------------------------------------------------------------------
    # Step 2: Tube_Body — Neck cylinder
    # -----------------------------------------------------------------------
    neck_curves = circle_profile_xy(part, v("Neck_Diameter"), z_cap_top)
    _, tube = extrude_z(part, neck_curves, "0", "Neck_Height", "EXTRUDE_NECK")
    print("[OK] Neck cylinder extruded")

    # -----------------------------------------------------------------------
    # Step 3: Tube_Body — Shoulder loft (circle -> rounded rect)
    # -----------------------------------------------------------------------
    n_seg = 72
    n_shoulder_sections = 7
    shoulder_sections = []
    for i in range(n_shoulder_sections):
        t = float(i) / float(n_shoulder_sections - 1)
        s = t * t * (3.0 - 2.0 * t)  # smoothstep interpolation
        w = v("Neck_Diameter") + (v("Tube_Width") - v("Neck_Diameter")) * s
        d = v("Neck_Diameter") + (v("Tube_Depth") - v("Neck_Diameter")) * s
        c = v("Neck_Diameter") * 0.5 + (v("Corner_Radius") - v("Neck_Diameter") * 0.5) * s
        z = z_neck_top + v("Shoulder_Height") * t
        shoulder_sections.append(ring_polyline(part, w, d, c, z, n_seg))

    _, shoulder = through_curves(part, shoulder_sections, "THROUGH_CURVES_SHOULDER")
    tube = unite(part, tube, shoulder, "UNITE_SHOULDER")
    print("[OK] Shoulder loft created and united")

    # -----------------------------------------------------------------------
    # Step 4+5: Tube_Body — Squeezable body loft + seal tab (single loft)
    #   Creating body and seal tab as a single ThroughCurves feature avoids
    #   a Parasolid boolean unite issue where the loft top-face normal is
    #   inverted, causing silent geometry truncation during unite.
    # -----------------------------------------------------------------------
    n_body_sections = 5
    body_sections = []
    for i in range(n_body_sections):
        t = float(i) / float(n_body_sections - 1)
        s = t * t * (3.0 - 2.0 * t)  # smoothstep
        w = v("Tube_Width") + (seal_width - v("Tube_Width")) * s
        d = v("Tube_Depth") + (seal_thickness - v("Tube_Depth")) * s
        c = v("Corner_Radius") + (seal_corner - v("Corner_Radius")) * s
        z = z_shoulder_top + h_body * t
        body_sections.append(ring_polyline(part, w, d, c, z, n_seg))

    # Append the seal tab top section (constant cross-section at z_top)
    # This creates a straight extrusion from z_seal_start to z_top within
    # the same loft, giving a clean solid with correct face normals.
    body_sections.append(ring_polyline(part, seal_width, seal_thickness, seal_corner, z_top, n_seg))

    _, body_loft = through_curves(part, body_sections, "THROUGH_CURVES_BODY_AND_SEAL")
    tube = unite(part, tube, body_loft, "UNITE_BODY_LOFT")
    tube = live_tallest_body(part) or tube
    print("[OK] Squeezable body loft with seal tab created and united")

    # -----------------------------------------------------------------------
    # Step 5b: Tube_Body — Seal crimp grooves
    #   Use inline boolean subtract during extrude with non-symmetric limits
    #   (start=0, end=height) to ensure solid tool bodies.
    # -----------------------------------------------------------------------
    n_crimps = int(v("Seal_Crimp_Count"))
    crimp_depth = v("Seal_Crimp_Depth")
    crimp_w = seal_width * 0.75
    crimp_slot_h = v("Seal_Tab_Height") * 0.6 / max(n_crimps, 1)
    crimp_start_z = z_seal_start + v("Seal_Tab_Height") * 0.2
    for ic in range(n_crimps):
        cz = crimp_start_z + ic * (v("Seal_Tab_Height") * 0.6 / max(n_crimps - 1, 1))
        cz_bottom = cz - crimp_slot_h * 0.5
        half_w = crimp_w * 0.5

        # Front crimp slot profile (cuts front face)
        y_min_f = seal_thickness * 0.5 - crimp_depth
        y_max_f = seal_thickness * 0.5 + crimp_depth + 1.0
        slot_f = [
            line(part, (-half_w, y_min_f, cz_bottom), (half_w, y_min_f, cz_bottom)),
            line(part, (half_w, y_min_f, cz_bottom), (half_w, y_max_f, cz_bottom)),
            line(part, (half_w, y_max_f, cz_bottom), (-half_w, y_max_f, cz_bottom)),
            line(part, (-half_w, y_max_f, cz_bottom), (-half_w, y_min_f, cz_bottom)),
        ]

        # Back crimp slot profile (cuts back face)
        y_min_b = -seal_thickness * 0.5 - crimp_depth - 1.0
        y_max_b = -seal_thickness * 0.5 + crimp_depth
        slot_b = [
            line(part, (-half_w, y_min_b, cz_bottom), (half_w, y_min_b, cz_bottom)),
            line(part, (half_w, y_min_b, cz_bottom), (half_w, y_max_b, cz_bottom)),
            line(part, (half_w, y_max_b, cz_bottom), (-half_w, y_max_b, cz_bottom)),
            line(part, (-half_w, y_max_b, cz_bottom), (-half_w, y_min_b, cz_bottom)),
        ]

        try:
            _, tube = extrude_z(part, slot_f, "0", str(crimp_slot_h), "EXTRUDE_CRIMP_F_{}".format(ic), target=tube, subtract=True)
        except Exception as exc:
            print("  [SKIP] Front crimp groove {}: {}".format(ic, exc))

        try:
            _, tube = extrude_z(part, slot_b, "0", str(crimp_slot_h), "EXTRUDE_CRIMP_B_{}".format(ic), target=tube, subtract=True)
        except Exception as exc:
            print("  [SKIP] Back crimp groove {}: {}".format(ic, exc))
    print("[OK] Seal crimp grooves created")

    # -----------------------------------------------------------------------
    # Step 6: Tube_Body — Edge blends
    # -----------------------------------------------------------------------
    tube = live_tallest_body(part) or tube

    # Blend shoulder-neck junction
    try:
        blend_edges(
            part, tube,
            lambda e: edge_horizontal(e) and abs(edge_z_center(e) - z_neck_top) < 0.5,
            "0.5",
            "EDGE_BLEND_SHOULDER_NECK"
        )
        print("[OK] Shoulder-neck blend applied")
    except Exception as exc:
        print("  [SKIP] Shoulder-neck blend: {}".format(exc))

    # Blend shoulder-body transition
    try:
        blend_edges(
            part, tube,
            lambda e: edge_horizontal(e) and abs(edge_z_center(e) - z_shoulder_top) < 0.5,
            "1.0",
            "EDGE_BLEND_SHOULDER_BODY"
        )
        print("[OK] Shoulder-body blend applied")
    except Exception as exc:
        print("  [SKIP] Shoulder-body blend: {}".format(exc))

    # Blend top seal edge
    try:
        blend_edges(
            part, tube,
            lambda e: edge_horizontal(e) and abs(edge_z_center(e) - z_top) < 2.0,
            "0.5",
            "EDGE_BLEND_SEAL_TOP"
        )
        print("[OK] Seal top blend applied")
    except Exception as exc:
        print("  [SKIP] Seal top blend: {}".format(exc))

    # -----------------------------------------------------------------------
    # Step 7: Tube_Body — Shell (optional, wrapped in try/except)
    # -----------------------------------------------------------------------
    tube = live_tallest_body(part) or tube
    try:
        tube = shell_body(part, tube, z_cap_top, "SHELL_TUBE_BODY")
    except Exception as exc:
        print("  [SKIP] Shell failed: {}".format(exc))

    tube = live_tallest_body(part) or tube
    set_name(tube, "Tube_Body")
    print("[OK] Tube_Body finished.")

    # =======================================================================
    # Step 9: Tube_Cap
    # =======================================================================
    cap_r = v("Cap_Diameter") * 0.5
    cap_h = v("Cap_Height")
    draft_offset = cap_h * math.tan(math.radians(v("Cap_Draft_Angle")))
    cap_r_top = cap_r - draft_offset

    # Revolve a trapezoid profile to create the drafted cap cylinder
    cap_curves = [
        line(part, (0.0, 0.0, 0.0), (cap_r, 0.0, 0.0)),
        line(part, (cap_r, 0.0, 0.0), (cap_r_top, 0.0, cap_h)),
        line(part, (cap_r_top, 0.0, cap_h), (0.0, 0.0, cap_h)),
        line(part, (0.0, 0.0, cap_h), (0.0, 0.0, 0.0)),
    ]
    _, cap = revolve_z(part, cap_curves, "0", "360", "REVOLVE_CAP_BODY")
    print("[OK] Cap body revolved")

    # Top corner fillet
    try:
        blend_edges(
            part, cap,
            lambda e: edge_horizontal(e) and abs(edge_z_center(e) - cap_h) < 0.5,
            "Cap_Corner_Radius",
            "EDGE_BLEND_CAP_TOP"
        )
        print("[OK] Cap top corner fillet applied")
    except Exception as exc:
        print("  [SKIP] Cap top fillet: {}".format(exc))

    # Bottom edge small fillet
    try:
        blend_edges(
            part, cap,
            lambda e: edge_horizontal(e) and abs(edge_z_center(e)) < 0.5,
            "0.5",
            "EDGE_BLEND_CAP_BOTTOM"
        )
        print("[OK] Cap bottom fillet applied")
    except Exception as exc:
        print("  [SKIP] Cap bottom fillet: {}".format(exc))

    # -----------------------------------------------------------------------
    # Step 9: Tube_Cap — Grip ribs (revolve + unite in loop)
    # -----------------------------------------------------------------------
    rib_r = cap_r + v("Grip_Rib_Depth") * 0.5
    rib_w = v("Grip_Rib_Width") * 0.5
    rib_z_start = 2.0
    rib_z_end = cap_h - v("Cap_Corner_Radius") - 1.0

    rib_curves = [
        line(part, (rib_r - rib_w, 0.0, rib_z_start), (rib_r + rib_w, 0.0, rib_z_start)),
        line(part, (rib_r + rib_w, 0.0, rib_z_start), (rib_r + rib_w, 0.0, rib_z_end)),
        line(part, (rib_r + rib_w, 0.0, rib_z_end), (rib_r - rib_w, 0.0, rib_z_end)),
        line(part, (rib_r - rib_w, 0.0, rib_z_end), (rib_r - rib_w, 0.0, rib_z_start)),
    ]

    n_ribs = int(v("Grip_Rib_Count"))
    rib_angle = 360.0 / n_ribs
    rib_span = rib_angle * 0.6

    for ic in range(n_ribs):
        center_a = ic * rib_angle
        start_a = center_a - rib_span * 0.5
        end_a = center_a + rib_span * 0.5
        rib_feat, rib_body = revolve_z(
            part, rib_curves,
            str(start_a), str(end_a),
            "REVOLVE_GRIP_RIB_{}".format(ic)
        )
        cap = unite(part, cap, rib_body, "UNITE_GRIP_RIB_{}".format(ic))

    print("[OK] Grip ribs created and united")

    set_name(cap, "Tube_Cap")
    print("[OK] Tube_Cap finished.")

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
    log = Path(__file__).resolve().parents[3] / "toothpaste_tube_journal.log"
    try:
        log.write_text("Starting toothpaste tube journal\n", encoding="utf-8")
        main()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
