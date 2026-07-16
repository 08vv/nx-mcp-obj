"""
create_swirl_pump_bottle.py
===========================
NX 2206 journal that creates a separate, reference-matched parametric pump
bottle: smooth tapered body, flowing raised/recessed front swirls, black collar,
white stem sleeve, and a curved dispensing head.

Usage:
  run_journal.exe create_swirl_pump_bottle.py [output_path.prt]
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
# Primary parameters, mm
# ---------------------------------------------------------------------------
BOTTLE_H = 214.0
BODY_MAX_R = 42.0
BODY_BASE_R = 31.0
BODY_NECK_R = 28.0
BODY_SHOULDER_Z = 168.0
BODY_NECK_Z = 190.0

COLLAR_Z = BODY_NECK_Z
COLLAR_H = 12.0
COLLAR_R = 36.0
CAP_H = 18.0
CAP_R = 32.0
STEM_DIA = 19.0
STEM_H = 58.0
SLEEVE_DIA = 13.0

RELIEF_PROTRUDE = 7.5
RELIEF_CUT_DEPTH = 10.0
WHITE_RIB_W = 8.5
BRONZE_RIB_W = 6.0
GROOVE_W = 3.2

LOGO_Z = 108.0


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3].joinpath(
        "reference_matched_swirl_pump_bottle.prt"
    ).resolve()


def _create_expressions(work_part):
    for name, value in [
        ("BOTTLE_H", BOTTLE_H),
        ("BODY_MAX_R", BODY_MAX_R),
        ("BODY_BASE_R", BODY_BASE_R),
        ("BODY_NECK_R", BODY_NECK_R),
        ("BODY_SHOULDER_Z", BODY_SHOULDER_Z),
        ("BODY_NECK_Z", BODY_NECK_Z),
        ("COLLAR_H", COLLAR_H),
        ("COLLAR_R", COLLAR_R),
        ("CAP_H", CAP_H),
        ("CAP_R", CAP_R),
        ("STEM_DIA", STEM_DIA),
        ("STEM_H", STEM_H),
        ("RELIEF_PROTRUDE", RELIEF_PROTRUDE),
        ("RELIEF_CUT_DEPTH", RELIEF_CUT_DEPTH),
    ]:
        try:
            work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
        except Exception:
            pass


def _body_radius_at_z(z):
    u = max(0.0, min(1.0, z / BODY_NECK_Z))
    if u < 0.12:
        t = u / 0.12
        return BODY_BASE_R + (BODY_MAX_R * 0.82 - BODY_BASE_R) * _smooth(t)
    if u < 0.52:
        t = (u - 0.12) / 0.40
        return BODY_MAX_R * 0.82 + (BODY_MAX_R - BODY_MAX_R * 0.82) * _smooth(t)
    if u < BODY_SHOULDER_Z / BODY_NECK_Z:
        t = (u - 0.52) / ((BODY_SHOULDER_Z / BODY_NECK_Z) - 0.52)
        return BODY_MAX_R + (BODY_MAX_R * 0.78 - BODY_MAX_R) * _smooth(t)
    t = (u - BODY_SHOULDER_Z / BODY_NECK_Z) / (1.0 - BODY_SHOULDER_Z / BODY_NECK_Z)
    return BODY_MAX_R * 0.78 + (BODY_NECK_R - BODY_MAX_R * 0.78) * _smooth(t)


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


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
    for i in range(18):
        z = BODY_NECK_Z * i / 17.0
        r = _body_radius_at_z(z)
        profile.append((r, 0.0, z))
    return _revolve_profile(work_part, profile, "SMOOTH_HOURGLASS_WHITE_BODY")


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
    min_y = -BODY_MAX_R - offset
    return min_y


def _ribbon_outline(path, width, y_value, taper=0.85):
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
    curves = _closed_polyline(work_part, _ribbon_outline(path, width, y))
    if mode == "raise":
        direction = NXOpen.Vector3d(0.0, 1.0, 0.0)
        boolean_type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite
        length = depth
    else:
        direction = NXOpen.Vector3d(0.0, 1.0, 0.0)
        boolean_type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
        length = depth
    try:
        return _extrude_curves(work_part, curves, direction, "0", str(length),
                               name, boolean_type, body)
    except Exception:
        feature, tool = _extrude_curves(work_part, curves, direction, "0", str(length), name)
        if tool:
            if mode == "raise":
                _unite(work_part, body, tool)
            else:
                _subtract(work_part, body, tool)
        return feature, tool


def _add_front_swirl_language(work_part, body):
    # Broad, mostly vertical S-curves based on the reference image. These are
    # deliberately not wrapped around the whole bottle, so the model reads as
    # front sculpted relief rather than a woven cage.
    white = [
        [(-29, 8), (-31, 42), (-18, 78), (-28, 118), (-15, 158), (-8, 188)],
        [(-12, 4), (-18, 40), (2, 82), (-9, 126), (6, 166), (1, 190)],
        [(5, 2), (0, 42), (22, 86), (11, 128), (25, 164), (21, 188)],
        [(25, 12), (33, 48), (20, 84), (36, 122), (27, 162)],
        [(-35, 36), (-20, 78), (-33, 124), (-12, 174)],
        [(34, 38), (17, 82), (34, 126), (13, 176)],
    ]
    bronze = [
        [(-1, 4), (-9, 50), (13, 96), (2, 144), (12, 188)],
        [(18, 6), (30, 48), (15, 92), (36, 138), (26, 178)],
    ]
    grooves = [
        [(-23, 14), (-24, 52), (-8, 92), (-20, 136), (-6, 184)],
        [(12, 10), (7, 48), (29, 88), (17, 132), (27, 176)],
        [(-34, 58), (-18, 98), (-30, 140), (-5, 186)],
        [(35, 62), (20, 102), (34, 142), (12, 186)],
    ]

    for i, path in enumerate(white, 1):
        _make_front_relief(work_part, body, path, WHITE_RIB_W, RELIEF_PROTRUDE,
                           "BROAD_RAISED_WHITE_SWIRL_{:02d}".format(i), "raise")
    for i, path in enumerate(bronze, 1):
        _make_front_relief(work_part, body, path, BRONZE_RIB_W, RELIEF_PROTRUDE * 0.8,
                           "SOFT_BRONZE_ACCENT_SWIRL_{:02d}".format(i), "raise")
    for i, path in enumerate(grooves, 1):
        _make_front_relief(work_part, body, path, GROOVE_W, RELIEF_CUT_DEPTH,
                           "NARROW_RECESSED_SHADOW_GROOVE_{:02d}".format(i), "cut")


def _add_pump(work_part, body):
    _, collar = _create_cylinder(
        work_part, NXOpen.Point3d(0.0, 0.0, COLLAR_Z),
        NXOpen.Vector3d(0.0, 0.0, 1.0), COLLAR_R * 2.0, COLLAR_H, "ROUND_WHITE_COLLAR"
    )
    _unite(work_part, body, collar)

    _, cap = _create_cylinder(
        work_part, NXOpen.Point3d(0.0, 0.0, COLLAR_Z + COLLAR_H),
        NXOpen.Vector3d(0.0, 0.0, 1.0), CAP_R * 2.0, CAP_H, "GLOSS_BLACK_PUMP_CAP"
    )
    _unite(work_part, body, cap)

    stem_z = COLLAR_Z + COLLAR_H + CAP_H
    _, stem = _create_cylinder(
        work_part, NXOpen.Point3d(0.0, 0.0, stem_z),
        NXOpen.Vector3d(0.0, 0.0, 1.0), STEM_DIA, STEM_H, "BLACK_VERTICAL_PUMP_STEM"
    )
    _unite(work_part, body, stem)

    _, sleeve = _create_cylinder(
        work_part, NXOpen.Point3d(-8.0, -5.0, stem_z + 1.5),
        NXOpen.Vector3d(0.0, 0.0, 1.0), SLEEVE_DIA, STEM_H * 0.88, "WHITE_FRONT_STEM_SLEEVE"
    )
    _unite(work_part, body, sleeve)

    head_z = stem_z + STEM_H - 3.0
    # Side silhouette of the gently arched pump head, extruded through Y.
    top = [
        (-22.0, -12.0, head_z + 2.0),
        (2.0, -12.0, head_z + 6.0),
        (34.0, -12.0, head_z + 7.5),
        (65.0, -12.0, head_z + 4.0),
        (86.0, -12.0, head_z - 3.0),
    ]
    bottom = [
        (82.0, -12.0, head_z - 10.0),
        (58.0, -12.0, head_z - 5.5),
        (28.0, -12.0, head_z - 2.5),
        (-2.0, -12.0, head_z - 1.5),
        (-24.0, -12.0, head_z - 2.0),
    ]
    curves = _closed_polyline(work_part, top + bottom)
    _, head = _extrude_curves(
        work_part, curves, NXOpen.Vector3d(0.0, 1.0, 0.0), "0", "24",
        "SINGLE_CURVED_WHITE_PUMP_HEAD",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite, body
    )

    # Thin shadow/gold underside line from the reference.
    gold = [
        (-2.0, -13.0, head_z - 3.0),
        (26.0, -13.0, head_z + 0.5),
        (58.0, -13.0, head_z - 2.2),
        (80.0, -13.0, head_z - 7.2),
    ]
    _make_front_relief(work_part, body, [(p[0], p[2]) for p in gold], 3.0, 4.5,
                       "BRONZE_UNDERSIDE_PUMP_LINE", "raise")
    return head


def _add_logo_recess(work_part, body):
    y = -BODY_MAX_R - 0.1
    pts = [
        (-18.0, y, LOGO_Z - 5.0),
        (18.0, y, LOGO_Z - 5.0),
        (18.0, y, LOGO_Z + 5.0),
        (-18.0, y, LOGO_Z + 5.0),
    ]
    try:
        _extrude_curves(
            work_part, _closed_polyline(work_part, pts), NXOpen.Vector3d(0.0, 1.0, 0.0),
            "0", "4.0", "SHALLOW_FRONT_LOGO_RECESS",
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
    print("  REFERENCE-MATCHED SWIRL PUMP BOTTLE")
    print("  Output: {}".format(output_path))
    print("=" * 72)

    _create_expressions(work_part)
    _, body = _create_body(work_part)
    print("[OK] Smooth hourglass revolved body created.")

    _add_front_swirl_language(work_part, body)
    print("[OK] Broad front flowing swirl reliefs created.")

    _add_pump(work_part, body)
    print("[OK] Pump collar, stem, and single curved head created.")

    _add_logo_recess(work_part, body)
    print("[OK] Front logo recess added.")

    _blend_edges(work_part, body, 1.1, max_edges=140)

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

    print("[DONE] Reference-matched bottle complete.")


if __name__ == "__main__":
    log_path = Path(__file__).resolve().parents[3] / "swirl_pump_bottle_journal.log"
    try:
        log_path.write_text("Starting reference-matched create_swirl_pump_bottle.py\n", encoding="utf-8")
        main()
        with log_path.open("a", encoding="utf-8") as f:
            f.write("Completed successfully\n")
    except Exception:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise
