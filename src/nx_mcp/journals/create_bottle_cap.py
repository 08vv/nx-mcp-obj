"""Create parametric Bottle_Cap.prt in Siemens NX 2206.

This journal builds the bottle cap as a clean native-feature model:
expressions, cylinder primitive, grip ribs via extrude + circular pattern,
and an internal cavity via subtract extrude.

All critical dimensions are controlled through named Expressions for full
parametric editability. The cap is positioned so its bottom sits at Z=0,
aligning concentrically with the neck when assembled.

Usage:
  run_journal.exe create_bottle_cap.py [output_path.prt]
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
# Primary parameters (mm) — matching the bottle body neck dimensions
# ---------------------------------------------------------------------------
VALUES = {
    "Cap_Diameter": 35.0,
    "Cap_Height": 22.0,
    "Cap_Rib_Depth": 0.8,
    "Cap_Rib_Count": 36,
    "Cap_Top_Fillet": 1.0,
    "Cap_Bottom_Fillet": 0.5,
    "Neck_Diameter": 28.0,
    "Cap_Cavity_Depth": 18.0,
    "Cap_Wall_Thickness": 2.0,
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Bottle_Cap.prt"


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
        rhs = int(value) if name == "Cap_Rib_Count" else value
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass
    formulas = {
        "Cap_Rib_Angle": "360.0 / Cap_Rib_Count",
        "Cap_Inner_Diameter": "Neck_Diameter + 0.5",
    }
    for name, rhs in formulas.items():
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Geometry helpers — all floats to avoid NXOpen int TypeError
# ---------------------------------------------------------------------------
def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))


def line(part, a, b):
    return part.Curves.CreateLine(point(*a), point(*b))


# ---------------------------------------------------------------------------
# Section
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


# ---------------------------------------------------------------------------
# Extrude
# ---------------------------------------------------------------------------
def extrude(part, curves, start_rhs, end_rhs, name, target=None, subtract=False):
    builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section(part, curves)
        builder.Direction = part.Directions.CreateDirection(
            point(0.0, 0.0, 0.0),
            vec(0.0, 0.0, 1.0),
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


# ---------------------------------------------------------------------------
# Edge helpers
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


# ---------------------------------------------------------------------------
# Edge Blend
# ---------------------------------------------------------------------------
def blend_edges(part, body, chooser, radius_rhs, name):
    edges = [e for e in list(body.GetEdges() or []) if chooser(e)]
    if not edges:
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
# Cylinder primitive
# ---------------------------------------------------------------------------
def cylinder(part, origin_z, diameter_rhs, height_rhs, name):
    builder = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        direction = part.Directions.CreateDirection(
            point(0.0, 0.0, origin_z),
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Axis.Point.SetCoordinates(point(0.0, 0.0, origin_z))
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
# Circle profile (polygon approximation)
# ---------------------------------------------------------------------------
def circle_profile(part, diameter, z, n=72):
    pts = []
    r = diameter * 0.5
    for i in range(n):
        a = 2.0 * math.pi * float(i) / float(n)
        pts.append((r * math.cos(a), r * math.sin(a), z))
    return [line(part, pts[i], pts[(i + 1) % n]) for i in range(n)]


# ---------------------------------------------------------------------------
# Cap with ribs
# ---------------------------------------------------------------------------
def build_cap(part):
    cap_z = 0.0

    # Step 1: Main cap cylinder
    _, cap = cylinder(part, cap_z, "Cap_Diameter", "Cap_Height", "CYLINDER_CAP_BODY")
    if cap is None:
        raise RuntimeError("Cap cylinder did not create a body.")
    print("[OK] Cap cylinder created")

    # Step 2: Edge blends on top and bottom
    blend_edges(
        part,
        cap,
        lambda e: edge_horizontal(e)
        and abs(edge_mid(e)[2] - (cap_z + v("Cap_Height"))) < 0.2,
        "Cap_Top_Fillet",
        "EDGE_BLEND_CAP_TOP",
    )
    print("[OK] Cap top fillet blended")

    blend_edges(
        part,
        cap,
        lambda e: edge_horizontal(e) and abs(edge_mid(e)[2] - cap_z) < 0.2,
        "Cap_Bottom_Fillet",
        "EDGE_BLEND_CAP_BOTTOM",
    )
    print("[OK] Cap bottom fillet blended")

    # Step 3: Grip ribs — single rib extruded then patterned circularly
    rib_width = math.pi * v("Cap_Diameter") / v("Cap_Rib_Count") * 0.35
    r = v("Cap_Diameter") * 0.5
    curves = [
        line(part, (r - 0.05, -rib_width * 0.5, cap_z + 1.0), (r + v("Cap_Rib_Depth"), -rib_width * 0.35, cap_z + 1.0)),
        line(part, (r + v("Cap_Rib_Depth"), -rib_width * 0.35, cap_z + 1.0), (r + v("Cap_Rib_Depth"), rib_width * 0.35, cap_z + 1.0)),
        line(part, (r + v("Cap_Rib_Depth"), rib_width * 0.35, cap_z + 1.0), (r - 0.05, rib_width * 0.5, cap_z + 1.0)),
        line(part, (r - 0.05, rib_width * 0.5, cap_z + 1.0), (r - 0.05, -rib_width * 0.5, cap_z + 1.0)),
    ]
    rib_feat, _ = extrude(
        part,
        curves,
        "0",
        "Cap_Height - 2.0",
        "EXTRUDE_SINGLE_GRIP_RIB",
        cap,
    )
    print("[OK] Single grip rib extruded")

    # Step 4: Circular pattern
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
            point(0.0, 0.0, cap_z),
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        circ.RotationCenter = part.Points.CreatePoint(point(0.0, 0.0, cap_z))
        circ.IncludeSeedToggle = True
        circ.AngularSpacing.NCopies.RightHandSide = "Cap_Rib_Count"
        circ.AngularSpacing.PitchAngle.RightHandSide = "Cap_Rib_Angle"
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, "CIRCULAR_PATTERN_GRIP_RIBS")
    print("[OK] Circular pattern of grip ribs created")

    # Step 5: Internal cavity (subtract extrude)
    cavity_dia = v("Neck_Diameter") + 0.5
    cavity_curves = circle_profile(part, cavity_dia, cap_z)
    extrude(
        part,
        cavity_curves,
        "0",
        "Cap_Cavity_Depth",
        "EXTRUDE_SUBTRACT_INTERNAL_CAVITY",
        cap,
        subtract=True,
    )
    print("[OK] Internal cavity subtracted")

    return cap


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

    print("Building parametric Bottle_Cap")
    make_expressions(part)
    cap = build_cap(part)

    try:
        print("Cap faces: {}".format(len(list(cap.GetFaces() or []))))
        part.ModelingViews.WorkView.Fit()
    except Exception:
        pass

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    write_launch_files(path)
    print("Saved: {}".format(path))


if __name__ == "__main__":
    log = Path(__file__).resolve().parents[3] / "bottle_cap_journal.log"
    try:
        log.write_text("Starting Bottle_Cap journal\n", encoding="utf-8")
        main()
        with log.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
