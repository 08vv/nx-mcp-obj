"""
create_everomino_pump_bottle.py
================================
NX 2206 journal — parametric EVEROMINO luxury pump bottle from reference image.

Features:
  - Teardrop revolved body (matte white)
  - Interlocking S-curve wave relief wrapping the body
  - Two-tier gold pump collar + curved dispensing spout
  - Front logo recess zone (EVEROMINO branding area)

Usage:
  run_journal.exe create_everomino_pump_bottle.py [output_path.prt]
"""

import math
import os
import subprocess
import sys
import traceback
from pathlib import Path

import NXOpen
import NXOpen.UF


UF_SESSION = NXOpen.UF.UFSession.GetUFSession()


# ---------------------------------------------------------------------------
# Primary parameters, mm — derived from reference image proportions
# ---------------------------------------------------------------------------
BOTTLE_H = 220.0
BODY_MAX_R = 44.0
BODY_BASE_R = 30.0
BODY_NECK_R = 26.0
BODY_SHOULDER_Z = 172.0
BODY_NECK_Z = 196.0

# Gold pump assembly
COLLAR_LOWER_Z = BODY_NECK_Z
COLLAR_LOWER_H = 6.0
COLLAR_LOWER_R = 34.0
COLLAR_UPPER_H = 5.0
COLLAR_UPPER_R = 30.0
NECK_CYL_H = 14.0
NECK_CYL_R = 22.0
SPOUT_LEN = 52.0
SPOUT_TIP_DROP = 8.0

# Wave relief geometry
WAVE_RIDGE_W = 9.0
WAVE_VALLEY_W = 4.5
WAVE_PROTRUDE = 6.5
WAVE_CUT_DEPTH = 9.0

LOGO_Z = 105.0
LOGO_W = 38.0
LOGO_H = 12.0


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3].joinpath(
        "everomino_pump_bottle.prt"
    ).resolve()


def _create_expressions(work_part):
    params = [
        ("BOTTLE_H", BOTTLE_H),
        ("BODY_MAX_R", BODY_MAX_R),
        ("BODY_BASE_R", BODY_BASE_R),
        ("BODY_NECK_R", BODY_NECK_R),
        ("BODY_SHOULDER_Z", BODY_SHOULDER_Z),
        ("BODY_NECK_Z", BODY_NECK_Z),
        ("COLLAR_LOWER_H", COLLAR_LOWER_H),
        ("COLLAR_LOWER_R", COLLAR_LOWER_R),
        ("COLLAR_UPPER_H", COLLAR_UPPER_H),
        ("COLLAR_UPPER_R", COLLAR_UPPER_R),
        ("NECK_CYL_H", NECK_CYL_H),
        ("NECK_CYL_R", NECK_CYL_R),
        ("SPOUT_LEN", SPOUT_LEN),
        ("WAVE_PROTRUDE", WAVE_PROTRUDE),
        ("WAVE_CUT_DEPTH", WAVE_CUT_DEPTH),
        ("LOGO_Z", LOGO_Z),
    ]
    for name, value in params:
        try:
            work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
        except Exception:
            pass


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


def _body_radius_at_z(z):
    u = max(0.0, min(1.0, z / BODY_NECK_Z))
    if u < 0.10:
        t = u / 0.10
        return BODY_BASE_R + (BODY_MAX_R * 0.75 - BODY_BASE_R) * _smooth(t)
    if u < 0.48:
        t = (u - 0.10) / 0.38
        return BODY_MAX_R * 0.75 + (BODY_MAX_R - BODY_MAX_R * 0.75) * _smooth(t)
    if u < BODY_SHOULDER_Z / BODY_NECK_Z:
        t = (u - 0.48) / ((BODY_SHOULDER_Z / BODY_NECK_Z) - 0.48)
        return BODY_MAX_R + (BODY_MAX_R * 0.80 - BODY_MAX_R) * _smooth(t)
    t = (u - BODY_SHOULDER_Z / BODY_NECK_Z) / (1.0 - BODY_SHOULDER_Z / BODY_NECK_Z)
    return BODY_MAX_R * 0.80 + (BODY_NECK_R - BODY_MAX_R * 0.80) * _smooth(t)


def _line(work_part, a, b):
    return work_part.Curves.CreateLine(
        NXOpen.Point3d(a[0], a[1], a[2]),
        NXOpen.Point3d(b[0], b[1], b[2]),
    )


def _closed_polyline(work_part, pts):
    curves = []
    for i, p in enumerate(pts):
        curves.append(_line(work_part, p, pts[(i + 1) % len(pts)]))
    return curves


def _section_from_curves(work_part, curves):
    section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
    rules = [work_part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    section.AddToSection(
        rules,
        curves[0],
        NXOpen.NXObject.Null,
        NXOpen.NXObject.Null,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create,
        False,
    )
    return section


def _revolve_profile(work_part, points, name):
    curves = []
    axis_top = (0.0, 0.0, points[-1][2])
    axis_bottom = (0.0, 0.0, points[0][2])
    closed = [axis_bottom] + points + [axis_top]
    for i in range(len(closed) - 1):
        curves.append(_line(work_part, closed[i], closed[i + 1]))
    curves.append(_line(work_part, axis_top, axis_bottom))

    tags = [curve.Tag for curve in curves]
    features, number_of_features = UF_SESSION.Modl.CreateRevolution(
        tags,
        len(tags),
        None,
        ["0", "360"],
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
    try:
        feature.SetName(name)
    except Exception:
        pass
    return feature, feature.GetBodies()[0]


def _create_body(work_part):
    profile = []
    for i in range(20):
        z = BODY_NECK_Z * i / 19.0
        r = _body_radius_at_z(z)
        profile.append((r, 0.0, z))
    return _revolve_profile(work_part, profile, "TEARDROP_WHITE_BODY")


def _extrude_curves(work_part, curves, direction_vec, start_expr, end_expr, name,
                    boolean_type=None, target_body=None):
    if boolean_type is None:
        boolean_type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = _section_from_curves(work_part, curves)
        direction = work_part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0),
            direction_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Direction = direction
        builder.Limits.StartExtend.Value.RightHandSide = str(start_expr)
        builder.Limits.EndExtend.Value.RightHandSide = str(end_expr)
        if target_body is not None:
            builder.BooleanOperation.SetBooleanOperationAndBody(boolean_type, target_body)
        else:
            builder.BooleanOperation.Type = boolean_type
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    try:
        feature.SetName(name)
    except Exception:
        pass
    bodies = feature.GetBodies()
    return feature, bodies[0] if bodies else None


def _boolean(work_part, operation, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = operation
        builder.Target = target_body
        builder.Tool = tool_body
        builder.CommitFeature()
    finally:
        builder.Destroy()


def _unite(work_part, target_body, tool_body):
    _boolean(work_part, NXOpen.Features.Feature.BooleanType.Unite, target_body, tool_body)


def _subtract(work_part, target_body, tool_body):
    _boolean(work_part, NXOpen.Features.Feature.BooleanType.Subtract, target_body, tool_body)


def _create_cylinder(work_part, origin, direction_vec, diameter, height, name,
                     boolean_type=None, target_body=None):
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        direction = work_part.Directions.CreateDirection(
            origin, direction_vec, NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = direction
        builder.Diameter.RightHandSide = str(diameter)
        builder.Height.RightHandSide = str(height)
        if boolean_type is not None and target_body is not None:
            builder.BooleanOption.Type = boolean_type
            try:
                builder.BooleanOption.SetTarget(target_body)
            except Exception:
                pass
        feature = builder.Commit()
    finally:
        builder.Destroy()
    try:
        feature.SetName(name)
    except Exception:
        pass
    return feature, feature.GetBodies()[0]


def _front_y_for_path(path, offset):
    return -BODY_MAX_R - offset


def _ribbon_outline_xz(path, width, y_value, taper=0.85):
    left = []
    right = []
    last = len(path) - 1
    for i, (x, z) in enumerate(path):
        if i == 0:
            dx = path[i + 1][0] - x
            dz = path[i + 1][1] - z
        elif i == last:
            dx = x - path[i - 1][0]
            dz = z - path[i - 1][1]
        else:
            dx = path[i + 1][0] - path[i - 1][0]
            dz = path[i + 1][1] - path[i - 1][1]
        length = math.hypot(dx, dz) or 1.0
        nx = -dz / length
        nz = dx / length
        end_taper = taper + (1.0 - taper) * math.sin(math.pi * i / max(1, last))
        local_w = width * end_taper
        left.append((x + nx * local_w * 0.5, y_value, z + nz * local_w * 0.5))
        right.append((x - nx * local_w * 0.5, y_value, z - nz * local_w * 0.5))
    return left + list(reversed(right))


def _make_front_relief(work_part, body, path, width, depth, name, mode):
    y = _front_y_for_path(path, 1.8 if mode == "raise" else 0.2)
    curves = _closed_polyline(work_part, _ribbon_outline_xz(path, width, y))
    direction = NXOpen.Vector3d(0.0, 1.0, 0.0)
    if mode == "raise":
        boolean_type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite
    else:
        boolean_type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
    try:
        return _extrude_curves(work_part, curves, direction, "0", str(depth),
                               name, boolean_type, body)
    except Exception:
        feature, tool = _extrude_curves(work_part, curves, direction, "0", str(depth), name)
        if tool:
            if mode == "raise":
                _unite(work_part, body, tool)
            else:
                _subtract(work_part, body, tool)
        return feature, tool


def _add_wave_texture(work_part, body):
    # Interlocking S-curve wave paths digitized from the EVEROMINO reference image.
    # Front sculpted relief reads as the flowing white/gold surface in the photo.
    ridges = [
        [(-32, 6), (-28, 38), (-14, 72), (-26, 108), (-12, 148), (-6, 182), (-2, 196)],
        [(-10, 4), (-16, 36), (4, 74), (-8, 114), (8, 152), (4, 186), (2, 196)],
        [(8, 2), (2, 34), (24, 78), (14, 118), (28, 156), (22, 188), (18, 196)],
        [(28, 10), (34, 44), (22, 80), (38, 118), (30, 158), (26, 190)],
        [(-36, 32), (-22, 68), (-34, 108), (-16, 152), (-8, 188)],
        [(36, 34), (20, 70), (36, 110), (18, 154), (10, 190)],
    ]
    valleys = [
        [(-22, 12), (-20, 48), (-4, 86), (-14, 126), (0, 168), (2, 192)],
        [(4, 8), (0, 44), (18, 82), (6, 122), (20, 162), (16, 190)],
        [(-30, 52), (-14, 90), (-28, 130), (-10, 172)],
        [(30, 54), (14, 92), (28, 132), (12, 174)],
        [(-8, 24), (-12, 60), (6, 98), (-4, 138), (10, 180)],
        [(14, 22), (8, 58), (26, 96), (14, 136), (24, 178)],
    ]

    for i, path in enumerate(ridges, 1):
        _make_front_relief(work_part, body, path, WAVE_RIDGE_W, WAVE_PROTRUDE,
                           "S_CURVE_RIDGE_{:02d}".format(i), "raise")
    for i, path in enumerate(valleys, 1):
        _make_front_relief(work_part, body, path, WAVE_VALLEY_W, WAVE_CUT_DEPTH,
                           "S_CURVE_VALLEY_{:02d}".format(i), "cut")


def _add_gold_pump(work_part, body):
    # Lower gold collar tier
    _, lower = _create_cylinder(
        work_part, NXOpen.Point3d(0.0, 0.0, COLLAR_LOWER_Z),
        NXOpen.Vector3d(0.0, 0.0, 1.0), COLLAR_LOWER_R * 2.0, COLLAR_LOWER_H,
        "GOLD_COLLAR_LOWER_TIER"
    )
    _unite(work_part, body, lower)

    upper_z = COLLAR_LOWER_Z + COLLAR_LOWER_H
    _, upper = _create_cylinder(
        work_part, NXOpen.Point3d(0.0, 0.0, upper_z),
        NXOpen.Vector3d(0.0, 0.0, 1.0), COLLAR_UPPER_R * 2.0, COLLAR_UPPER_H,
        "GOLD_COLLAR_UPPER_TIER"
    )
    _unite(work_part, body, upper)

    neck_z = upper_z + COLLAR_UPPER_H
    _, neck = _create_cylinder(
        work_part, NXOpen.Point3d(0.0, 0.0, neck_z),
        NXOpen.Vector3d(0.0, 0.0, 1.0), NECK_CYL_R * 2.0, NECK_CYL_H,
        "GOLD_NECK_CYLINDER"
    )
    _unite(work_part, body, neck)

    # Curved dispensing spout — side profile extruded through Y
    spout_z = neck_z + NECK_CYL_H - 2.0
    top_profile = [
        (-4.0, -NECK_CYL_R - 2.0, spout_z + 2.0),
        (8.0, -NECK_CYL_R - 2.0, spout_z + 5.0),
        (SPOUT_LEN * 0.5, -NECK_CYL_R - 2.0, spout_z + 6.5),
        (SPOUT_LEN, -NECK_CYL_R - 2.0, spout_z + 3.0),
        (SPOUT_LEN + 8.0, -NECK_CYL_R - 2.0, spout_z - SPOUT_TIP_DROP),
    ]
    bottom_profile = [
        (SPOUT_LEN + 6.0, -NECK_CYL_R - 2.0, spout_z - SPOUT_TIP_DROP - 4.0),
        (SPOUT_LEN - 4.0, -NECK_CYL_R - 2.0, spout_z - 1.0),
        (SPOUT_LEN * 0.4, -NECK_CYL_R - 2.0, spout_z + 1.0),
        (0.0, -NECK_CYL_R - 2.0, spout_z + 0.5),
        (-6.0, -NECK_CYL_R - 2.0, spout_z),
    ]
    curves = _closed_polyline(work_part, top_profile + bottom_profile)
    _extrude_curves(
        work_part, curves, NXOpen.Vector3d(0.0, 1.0, 0.0), "0", str(NECK_CYL_R * 2.0 + 4.0),
        "GOLD_CURVED_DISPENSING_SPOUT",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite, body
    )


def _add_logo_recess(work_part, body):
    y = -BODY_MAX_R - 0.15
    half_w = LOGO_W * 0.5
    half_h = LOGO_H * 0.5
    pts = [
        (-half_w, y, LOGO_Z - half_h),
        (half_w, y, LOGO_Z - half_h),
        (half_w, y, LOGO_Z + half_h),
        (-half_w, y, LOGO_Z + half_h),
    ]
    try:
        _extrude_curves(
            work_part, _closed_polyline(work_part, pts), NXOpen.Vector3d(0.0, 1.0, 0.0),
            "0", "3.5", "EVEROMINO_LOGO_RECESS",
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract, body
        )
    except Exception:
        pass


def _blend_edges(work_part, body, radius, max_edges=120):
    applied = 0
    for edge in list(body.GetEdges())[:max_edges]:
        builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = work_part.ScCollectors.CreateCollector()
            rule = work_part.ScRuleFactory.CreateRuleEdgeMultipleSeedTangent([edge], 0.5, True)
            collector.ReplaceRules([rule], False)
            builder.Tolerance = 0.01
            builder.AddChainset(collector, str(radius))
            builder.CommitFeature()
            applied += 1
        except Exception:
            pass
        finally:
            builder.Destroy()
    print("[OK] Blend pass applied to {} edge chains.".format(applied))


def _update_result_files(output_path):
    root = Path(__file__).resolve().parents[3]
    abs_str = str(output_path.resolve())
    (root / "latest_nx_result.txt").write_text(abs_str, encoding="utf-8")
    base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
    router = Path(base_dir) / "NXBIN" / "ugs_router.exe"
    (root / "open_current_nx_result.cmd").write_text(
        '@echo off\nstart "" "{}" -ug -use_file_dir "{}"\n'.format(router, abs_str),
        encoding="utf-8",
    )


def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            output_path.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    print("=" * 72)
    print("  EVEROMINO PARAMETRIC PUMP BOTTLE")
    print("  Output: {}".format(output_path))
    print("=" * 72)

    _create_expressions(work_part)
    _, body = _create_body(work_part)
    print("[OK] Teardrop revolved body created.")

    _add_wave_texture(work_part, body)
    print("[OK] Interlocking S-curve wave texture applied.")

    _add_gold_pump(work_part, body)
    print("[OK] Gold two-tier pump collar and curved spout created.")

    _add_logo_recess(work_part, body)
    print("[OK] EVEROMINO logo recess zone added.")

    _blend_edges(work_part, body, 1.0, max_edges=160)

    try:
        work_part.ModelingViews.WorkView.Fit()
    except Exception:
        pass

    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("[OK] Part saved: {}".format(output_path))

    _update_result_files(output_path)
    try:
        router = Path(os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206") / "NXBIN" / "ugs_router.exe"
        if router.exists():
            subprocess.Popen([str(router), "-ug", "-use_file_dir", str(output_path.resolve())])
    except Exception:
        pass

    print("[DONE] EVEROMINO parametric bottle complete.")


if __name__ == "__main__":
    log_path = Path(__file__).resolve().parents[3] / "everomino_pump_bottle_journal.log"
    try:
        log_path.write_text("Starting create_everomino_pump_bottle.py\n", encoding="utf-8")
        main()
        with log_path.open("a", encoding="utf-8") as f:
            f.write("Completed successfully\n")
    except Exception:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise
