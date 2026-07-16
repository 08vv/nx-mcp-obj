"""Create a clean, production-ready, parametric decorative floral soap bar in Siemens NX 2206.

This script implements a high-quality CAD modeling history for:
- Soap_Body (rounded-rect base, pillow-shaped top/bottom, generous perimeter blends,
             embossed floral petals, spiral swirls, vine segments, berry dots,
             recessed flower-center ovals, final relief blends)
- All primary dimensions are controlled via Expressions.

Usage:
  run_journal.exe create_floral_soap.py [output_path.prt]
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
# Primary parameters (mm) — Decorative floral soap bar
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Length": 80.0,
    "Overall_Width": 80.0,
    "Overall_Thickness": 28.0,
    "Corner_Radius": 10.0,
    "Edge_Blend_Radius": 5.0,
    "Face_Crown_Height": 1.5,
    "Side_Draft_Angle": 3.0,
    "Relief_Depth": 0.8,
    "Flower_Length": 28.0,
    "Flower_Width": 16.0,
    "Flower_Groove_Depth": 0.4,
    "Swirl_Radius": 10.0,
    "Swirl_Width": 2.5,
    "Vine_Width": 2.0,
    "Vine_Depth": 0.6,
    "Berry_Diameter": 4.0,
    "Berry_Height": 0.8,
    "Border_Width": 5.0,
    "Blend_Radius": 1.0,
    "Pattern_Scale": 1.0,
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Floral_Soap.prt"


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
# Section, Extrude
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


# ---------------------------------------------------------------------------
# Boolean helpers
# ---------------------------------------------------------------------------
def set_boolean_inputs(builder, part, target_body, tool_body):
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
                break
            except Exception:
                pass

    for attr in ("Tool", "ToolBody"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, tool_body)
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
# Edge helpers
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


def live_body(part):
    bodies = [b for b in list(part.Bodies or []) if b.IsSolidBody]
    if not bodies:
        return None
    return max(bodies, key=lambda b: len(list(b.GetFaces() or [])))


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
# Rounded-rectangle polar radius (bisection) — for soap base profile
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
# Ellipse polyline
# ---------------------------------------------------------------------------
def ellipse_polyline(part, cx, cy, z, rx, ry, angle_offset=0.0, n=48):
    """Closed ellipse polyline at (cx, cy, z) with semi-axes rx, ry, rotated by angle_offset radians."""
    cos_a = math.cos(angle_offset)
    sin_a = math.sin(angle_offset)
    pts = []
    for i in range(n):
        t = 2.0 * math.pi * float(i) / float(n)
        lx = rx * math.cos(t)
        ly = ry * math.sin(t)
        px = cx + lx * cos_a - ly * sin_a
        py = cy + lx * sin_a + ly * cos_a
        pts.append((px, py, z))
    return [line(part, pts[i], pts[(i + 1) % n]) for i in range(n)]


def teardrop_polyline(part, cx, cy, z, length, width, angle_offset=0.0, n=48):
    """Closed teardrop / petal profile — egg-shaped with one pointed end.

    The shape uses a superellipse with exponent modulation: the 'top' half
    (along the long axis) is narrower than the 'bottom' half, producing a
    tapered petal silhouette.  ``length`` is the full extent along the long
    axis, ``width`` along the short axis.
    """
    cos_a = math.cos(angle_offset)
    sin_a = math.sin(angle_offset)
    hl = length * 0.5
    hw = width * 0.5
    pts = []
    for i in range(n):
        t = 2.0 * math.pi * float(i) / float(n)
        # local y along long axis, local x along short axis
        ly = hl * math.sin(t)
        # modulate width: narrower toward positive y (tip)
        frac = (math.sin(t) + 1.0) * 0.5  # 0 at bottom, 1 at tip
        w_mod = hw * (1.0 - 0.55 * frac)  # narrows to 45% at tip
        lx = w_mod * math.cos(t)
        px = cx + lx * cos_a - ly * sin_a
        py = cy + lx * sin_a + ly * cos_a
        pts.append((px, py, z))
    return [line(part, pts[i], pts[(i + 1) % n]) for i in range(n)]


def circle_polyline(part, cx, cy, z, diameter, n=36):
    """Closed circle polyline at (cx, cy, z) with given diameter."""
    r = diameter * 0.5
    pts = []
    for i in range(n):
        t = 2.0 * math.pi * float(i) / float(n)
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t), z))
    return [line(part, pts[i], pts[(i + 1) % n]) for i in range(n)]


# ---------------------------------------------------------------------------
# Spiral polyline (Archimedean)
# ---------------------------------------------------------------------------
def spiral_ribbon_profiles(part, cx, cy, z, max_radius, ribbon_width, turns, angle_offset=0.0, n_per_turn=36):
    """Generate a closed ribbon outline of an Archimedean spiral.

    Returns a list of line segments forming a closed polygon that traces one
    side of the spiral outward and the other side inward.
    Starts from a minimum radius of ribbon_width * 1.5 to avoid self-intersection.
    """
    cos_a = math.cos(angle_offset)
    sin_a = math.sin(angle_offset)
    hw = ribbon_width * 0.5
    min_radius = ribbon_width * 1.5  # avoid self-intersection near center
    total = int(turns * n_per_turn)
    outer = []
    inner = []
    for i in range(total + 1):
        frac = float(i) / float(total)
        t = frac * turns * 2.0 * math.pi
        r = min_radius + (max_radius - min_radius) * frac
        ct, st = math.cos(t), math.sin(t)
        for sign, store in ((1.0, outer), (-1.0, inner)):
            lx = (r + sign * hw) * ct
            ly = (r + sign * hw) * st
            px = cx + lx * cos_a - ly * sin_a
            py = cy + lx * sin_a + ly * cos_a
            store.append((px, py, z))

    # Combine: outer forward, inner reversed, close the loop
    pts = outer + list(reversed(inner))
    return [line(part, pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]


# ---------------------------------------------------------------------------
# Vine curve ribbon
# ---------------------------------------------------------------------------
def vine_ribbon(part, control_points, width, z):
    """Build a ribbon outline from a polyline path defined by control_points.

    Each control point is (x, y).  The ribbon is offset by +/-width/2
    perpendicular to the local tangent.
    """
    hw = width * 0.5
    n = len(control_points)
    if n < 2:
        return []

    left = []
    right = []
    for i in range(n):
        # Tangent direction
        if i == 0:
            dx = control_points[1][0] - control_points[0][0]
            dy = control_points[1][1] - control_points[0][1]
        elif i == n - 1:
            dx = control_points[n - 1][0] - control_points[n - 2][0]
            dy = control_points[n - 1][1] - control_points[n - 2][1]
        else:
            dx = control_points[i + 1][0] - control_points[i - 1][0]
            dy = control_points[i + 1][1] - control_points[i - 1][1]
        mag = math.hypot(dx, dy)
        if mag < 1.0e-9:
            nx_dir, ny_dir = 0.0, 1.0
        else:
            nx_dir = -dy / mag
            ny_dir = dx / mag
        cx, cy = control_points[i]
        left.append((cx + hw * nx_dir, cy + hw * ny_dir, z))
        right.append((cx - hw * nx_dir, cy - hw * ny_dir, z))

    pts = left + list(reversed(right))
    return [line(part, pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]


# ---------------------------------------------------------------------------
# Catmull-Rom subdivision for smooth vine paths
# ---------------------------------------------------------------------------
def catmull_rom_chain(control_pts, subdivisions=8):
    """Subdivide a polyline using Catmull-Rom interpolation.

    ``control_pts`` is a list of (x, y) tuples.  Returns a denser list.
    """
    if len(control_pts) < 2:
        return list(control_pts)
    result = [control_pts[0]]
    for i in range(len(control_pts) - 1):
        p0 = control_pts[max(i - 1, 0)]
        p1 = control_pts[i]
        p2 = control_pts[i + 1]
        p3 = control_pts[min(i + 2, len(control_pts) - 1)]
        for j in range(1, subdivisions + 1):
            t = float(j) / float(subdivisions)
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * ((2.0 * p1[0]) +
                        (-p0[0] + p2[0]) * t +
                        (2.0 * p0[0] - 5.0 * p1[0] + 4.0 * p2[0] - p3[0]) * t2 +
                        (-p0[0] + 3.0 * p1[0] - 3.0 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2.0 * p1[1]) +
                        (-p0[1] + p2[1]) * t +
                        (2.0 * p0[1] - 5.0 * p1[1] + 4.0 * p2[1] - p3[1]) * t2 +
                        (-p0[1] + 3.0 * p1[1] - 3.0 * p2[1] + p3[1]) * t3)
            result.append((x, y))
    return result


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
        part = session.Parts.FindObject(path.name)
    except Exception:
        pass

    if part is not None:
        part.Close(NXOpen.BasePart.CloseWholeTree.TrueValue, NXOpen.BasePart.CloseModified.CloseWithSaving, None)

    session.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)
    part = session.Parts.Work
    print("Building Decorative Floral Soap Bar")
    print("------------------------------------")

    # Step 1: Expressions
    make_expressions(part)

    # Derived dimensions
    s = v("Pattern_Scale")
    length = v("Overall_Length")
    width = v("Overall_Width")
    thickness = v("Overall_Thickness")
    corner_r = v("Corner_Radius")
    z_top = thickness
    z_mid = thickness * 0.5

    # -----------------------------------------------------------------------
    # Step 2: Base soap body — through-curves loft for pillow shape
    # -----------------------------------------------------------------------
    n_seg = 72
    crown = v("Face_Crown_Height")
    draft_rad = math.radians(v("Side_Draft_Angle"))

    draft_expand = z_mid * math.tan(draft_rad)
    sections = []
    z_levels = [0.0, thickness * 0.2, z_mid, thickness * 0.8, z_top]
    for iz, zz in enumerate(z_levels):
        # Draft: widest at center, tapering toward top and bottom
        dist_from_mid = abs(zz - z_mid)
        draft_factor = 1.0 - (dist_from_mid / z_mid)  # 1.0 at center, 0.0 at faces
        w = length + 2.0 * draft_expand * draft_factor
        d = width + 2.0 * draft_expand * draft_factor
        c = corner_r
        sections.append(ring_polyline(part, w, d, c, zz, n_seg))

    _, soap = through_curves(part, sections, "THROUGH_CURVES_SOAP_BASE")
    print("[OK] Base soap body created via through-curves loft")

    # -----------------------------------------------------------------------
    # Step 3: Edge blends — pillow shape on top and bottom perimeter
    # -----------------------------------------------------------------------
    soap = live_body(part) or soap

    # Bottom horizontal edges
    try:
        blend_edges(
            part, soap,
            lambda e: edge_horizontal(e) and abs(edge_z_center(e)) < 1.0,
            "Edge_Blend_Radius",
            "EDGE_BLEND_BOTTOM"
        )
        print("[OK] Bottom edge blend applied")
    except Exception as exc:
        print("  [SKIP] Bottom edge blend: {}".format(exc))

    # Top horizontal edges
    soap = live_body(part) or soap
    try:
        blend_edges(
            part, soap,
            lambda e: edge_horizontal(e) and abs(edge_z_center(e) - z_top) < 1.0,
            "Edge_Blend_Radius",
            "EDGE_BLEND_TOP"
        )
        print("[OK] Top edge blend applied")
    except Exception as exc:
        print("  [SKIP] Top edge blend: {}".format(exc))

    soap = live_body(part) or soap
    print("[OK] Pillow-shape edge blends completed")

    # -----------------------------------------------------------------------
    # Step 4: Flower petals — 4 large teardrop-shaped embossed petals
    # -----------------------------------------------------------------------
    fl = v("Flower_Length") * s
    fw = v("Flower_Width") * s
    relief_d = v("Relief_Depth")
    groove_d = v("Flower_Groove_Depth")

    # Petal center offsets from soap center (0,0)
    petal_offset = 16.0 * s  # distance from center to petal center

    petal_configs = [
        # (center_x, center_y, rotation_angle_rad)
        (petal_offset, petal_offset, math.radians(45.0)),      # top-right
        (-petal_offset, petal_offset, math.radians(135.0)),    # top-left
        (-petal_offset, -petal_offset, math.radians(225.0)),   # bottom-left
        (petal_offset, -petal_offset, math.radians(315.0)),    # bottom-right
    ]

    for ip, (pcx, pcy, pangle) in enumerate(petal_configs):
        # Outer petal profile (teardrop)
        petal_curves = teardrop_polyline(part, pcx, pcy, z_top, fl, fw, pangle, 48)
        try:
            _, soap = extrude_z(
                part, petal_curves, "-3.0", str(relief_d),
                "EXTRUDE_PETAL_{}".format(ip), target=soap, subtract=False
            )
            print("[OK] Petal {} embossed".format(ip))
        except Exception as exc:
            print("  [SKIP] Petal {} emboss: {}".format(ip, exc))

        # Center groove (smaller elongated ellipse, subtracted into the petal top)
        groove_curves = ellipse_polyline(
            part, pcx, pcy, z_top, fl * 0.45, fw * 0.2, pangle, 36
        )
        soap = live_body(part) or soap
        try:
            _, soap = extrude_z(
                part, groove_curves, str(-groove_d), str(relief_d + 0.1),
                "EXTRUDE_PETAL_GROOVE_{}".format(ip), target=soap, subtract=True
            )
            print("[OK] Petal {} groove engraved".format(ip))
        except Exception as exc:
            print("  [SKIP] Petal {} groove: {}".format(ip, exc))

    soap = live_body(part) or soap
    print("[OK] All four flower petals completed")

    # -----------------------------------------------------------------------
    # Step 5: Central spiral swirls — two mirrored Archimedean spirals
    # -----------------------------------------------------------------------
    swirl_r = v("Swirl_Radius") * s
    swirl_w = v("Swirl_Width") * s

    # Right spiral (clockwise from center)
    spiral_r_curves = spiral_ribbon_profiles(
        part, 2.0 * s, 0.0, z_top,
        swirl_r, swirl_w, 1.5, math.radians(0.0), 36
    )
    try:
        _, soap = extrude_z(
            part, spiral_r_curves, "-3.0", str(relief_d),
            "EXTRUDE_SWIRL_R", target=soap, subtract=False
        )
        print("[OK] Right spiral swirl embossed")
    except Exception as exc:
        print("  [SKIP] Right spiral: {}".format(exc))

    # Left spiral (mirrored — rotated 180 degrees)
    soap = live_body(part) or soap
    spiral_l_curves = spiral_ribbon_profiles(
        part, -2.0 * s, 0.0, z_top,
        swirl_r, swirl_w, 1.5, math.radians(180.0), 36
    )
    try:
        _, soap = extrude_z(
            part, spiral_l_curves, "-3.0", str(relief_d),
            "EXTRUDE_SWIRL_L", target=soap, subtract=False
        )
        print("[OK] Left spiral swirl embossed")
    except Exception as exc:
        print("  [SKIP] Left spiral: {}".format(exc))

    soap = live_body(part) or soap
    print("[OK] Central spiral swirls completed")

    # -----------------------------------------------------------------------
    # Step 6: Vine segments — curved ribbons between flowers
    # -----------------------------------------------------------------------
    vine_w = v("Vine_Width") * s
    vine_d = v("Vine_Depth")

    # Define vine paths as polyline control points (x, y) in soap coordinates
    # Smoothed with Catmull-Rom subdivision
    vine_paths = [
        # Vine 1: top-right petal toward upper edge, curving right
        [(12.0, 12.0), (18.0, 22.0), (26.0, 28.0), (30.0, 32.0)],
        # Vine 2: top-left petal toward upper-left corner
        [(-12.0, 12.0), (-20.0, 20.0), (-28.0, 26.0), (-32.0, 30.0)],
        # Vine 3: bottom-right petal toward lower edge
        [(12.0, -12.0), (20.0, -20.0), (28.0, -28.0), (32.0, -30.0)],
        # Vine 4: bottom-left toward lower-left
        [(-12.0, -12.0), (-18.0, -22.0), (-26.0, -28.0), (-30.0, -32.0)],
        # Vine 5: connecting swirl to top-right area
        [(6.0, 4.0), (14.0, 8.0), (22.0, 6.0), (28.0, 10.0)],
        # Vine 6: connecting swirl to bottom-left area
        [(-6.0, -4.0), (-14.0, -8.0), (-22.0, -6.0), (-28.0, -10.0)],
        # Vine 7: short connector from top swirl end to upper flower
        [(4.0, 8.0), (6.0, 14.0), (10.0, 18.0)],
        # Vine 8: short connector from bottom swirl end to lower flower
        [(-4.0, -8.0), (-6.0, -14.0), (-10.0, -18.0)],
    ]

    for iv, raw_pts in enumerate(vine_paths):
        # Scale control points
        scaled_pts = [(px * s, py * s) for px, py in raw_pts]
        smooth_pts = catmull_rom_chain(scaled_pts, 6)
        ribbon_curves = vine_ribbon(part, smooth_pts, vine_w, z_top)
        if not ribbon_curves:
            print("  [SKIP] Vine {} — no ribbon curves".format(iv))
            continue
        soap = live_body(part) or soap
        try:
            _, soap = extrude_z(
                part, ribbon_curves, "-3.0", str(vine_d),
                "EXTRUDE_VINE_{}".format(iv), target=soap, subtract=False
            )
            print("[OK] Vine {} embossed".format(iv))
        except Exception as exc:
            print("  [SKIP] Vine {}: {}".format(iv, exc))

    soap = live_body(part) or soap
    print("[OK] Vine segments completed")

    # -----------------------------------------------------------------------
    # Step 7: Berry dots — small raised hemispheres at vine endpoints
    # -----------------------------------------------------------------------
    berry_d = v("Berry_Diameter") * s
    berry_h = v("Berry_Height")

    # Berry positions (x, y) — at the ends of vine branches and scattered
    berry_positions = [
        # Tips of vines
        (30.0, 32.0),
        (-32.0, 30.0),
        (32.0, -30.0),
        (-30.0, -32.0),
        (28.0, 10.0),
        (-28.0, -10.0),
        # Additional berries near flowers (reference shows clusters)
        (24.0, 30.0),
        (-26.0, 28.0),
        (26.0, -26.0),
        (-24.0, -30.0),
        # Berry pair near top-right vine
        (32.0, 26.0),
        (-30.0, 26.0),
        # Berry pair near bottom
        (-32.0, -26.0),
        # Small cluster near center-right
        (22.0, 14.0),
        (-22.0, -14.0),
    ]

    for ib, (bx, by) in enumerate(berry_positions):
        bx_s = bx * s
        by_s = by * s
        berry_curves = circle_polyline(part, bx_s, by_s, z_top, berry_d, 24)
        soap = live_body(part) or soap
        try:
            _, soap = extrude_z(
                part, berry_curves, "-5.0", str(berry_h),
                "EXTRUDE_BERRY_{}".format(ib), target=soap, subtract=False
            )
        except Exception as exc:
            print("  [SKIP] Berry {}: {}".format(ib, exc))

    # Apply rounded blend to berry tops (radius must be smaller than berry height)
    soap = live_body(part) or soap
    berry_blend_r = 0.20
    for ib, (bx, by) in enumerate(berry_positions):
        bx_s = bx * s
        by_s = by * s
        soap = live_body(part) or soap
        try:
            blend_edges(
                part, soap,
                lambda e, _bx=bx_s, _by=by_s: (
                    abs(edge_z_center(e) - (z_top + berry_h)) < 0.5
                    and abs(edge_mid(e)[0] - _bx) < berry_d
                    and abs(edge_mid(e)[1] - _by) < berry_d
                ),
                str(berry_blend_r),
                "EDGE_BLEND_BERRY_{}".format(ib)
            )
        except Exception as exc:
            print("  [SKIP] Berry {} blend: {}".format(ib, exc))

    soap = live_body(part) or soap
    print("[OK] Berry dots completed ({} berries)".format(len(berry_positions)))

    # -----------------------------------------------------------------------
    # Step 8: Small recessed ovals near flower centers
    # -----------------------------------------------------------------------
    oval_configs = [
        # Near each petal center — small ovals on the embossed petal surface
        (petal_offset, petal_offset, math.radians(45.0)),
        (-petal_offset, petal_offset, math.radians(135.0)),
        (-petal_offset, -petal_offset, math.radians(225.0)),
        (petal_offset, -petal_offset, math.radians(315.0)),
    ]

    oval_rx = 3.0 * s
    oval_ry = 1.8 * s
    oval_depth = groove_d

    for io, (ox, oy, oa) in enumerate(oval_configs):
        oval_curves = ellipse_polyline(part, ox, oy, z_top, oval_rx, oval_ry, oa, 30)
        soap = live_body(part) or soap
        try:
            _, soap = extrude_z(
                part, oval_curves, str(-oval_depth), str(relief_d + 1.0),
                "EXTRUDE_OVAL_{}".format(io), target=soap, subtract=True
            )
            print("[OK] Recessed oval {} engraved".format(io))
        except Exception as exc:
            print("  [SKIP] Oval {}: {}".format(io, exc))

    soap = live_body(part) or soap
    print("[OK] Recessed ovals completed")

    # -----------------------------------------------------------------------
    # Step 9: Final relief edge blends — soft transitions on all relief edges
    # -----------------------------------------------------------------------
    blend_r = v("Blend_Radius")
    try:
        blend_edges(
            part, soap,
            lambda e: (
                abs(edge_z_center(e) - z_top) < relief_d + 0.5
                and not edge_horizontal(e)
            ),
            str(blend_r * 0.25),
            "EDGE_BLEND_RELIEF_WALLS"
        )
        print("[OK] Relief wall blends applied")
    except Exception as exc:
        print("  [SKIP] Relief wall blends: {}".format(exc))

    # Name the final body
    soap = live_body(part) or soap
    set_name(soap, "Soap_Body")
    print("[OK] Soap_Body finished.")

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
    log = Path(__file__).resolve().parents[3] / "floral_soap_journal.log"
    try:
        log.write_text("Starting floral soap journal\n", encoding="utf-8")
        main()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
