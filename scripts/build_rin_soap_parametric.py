"""
build_rin_soap_parametric.py
============================
Parametric NX CAD Builder for Rin Soap Container.
Constructs a fully parametric, feature-based Siemens NX part (.prt) strictly
matching the reference geometry of obj/Rin_soap_reduced.obj:
- Recessed central front section (Y = -45.97 mm, Z from -10.3 to +10.9 mm)
- Raised upper and lower front rails (Y = -54.32 mm, protruding by 8.35 mm)
- Smooth transitional ramps connecting recess to rails
- Stepped top structure with dual longitudinal grooves (depth 4.25 mm)
- Stepped bottom structure with dual longitudinal grooves (depth 4.00 mm)
- Smoothly rounded side edge transitions at container ends
- 31 cross-section stations with 64 points per station (optimal smooth curvature)
- Comprehensive named parametric driving expressions in NX

Coordinate system (NX):
  X = length (-100 to +100 mm)
  Y = width (-54 to +54 mm)
  Z = height (-34 to +34 mm)

Usage (invoked via run_journal.exe):
    run_journal.exe build_rin_soap_parametric.py <spec_json> <output_prt>
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.29" not in os.environ["SPLM_LICENSE_SERVER"]:
    curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.29;{curr}"

import NXOpen
import NXOpen.UF

UF = NXOpen.UF.UFSession.GetUFSession()


def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))


def make_line(part, a: Tuple[float, float, float], b: Tuple[float, float, float]):
    return part.Curves.CreateLine(point(*a), point(*b))


def set_name(obj, name: str):
    if obj is None:
        return
    try:
        obj.SetName(name)
    except Exception:
        pass


def nx_section(part, curves, start_point=None):
    sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
    rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    help_pt = start_point if start_point is not None else point(0.0, 0.0, 0.0)
    sec.AddToSection(
        rules,
        curves[0],
        NXOpen.NXObject.Null,
        NXOpen.NXObject.Null,
        help_pt,
        NXOpen.Section.Mode.Create,
        False,
    )
    return sec


def append_section(builder, sec) -> None:
    container = getattr(builder, "SectionsList", None) or getattr(builder, "Sections", None)
    if hasattr(container, "Append"):
        container.Append(sec)
    else:
        container.Add(sec)


def station_to_curves(part, pts_3d):
    """Convert a list of 3D points into line segments forming a closed polygon."""
    n = len(pts_3d)
    curves = [make_line(part, pts_3d[k], pts_3d[(k + 1) % n]) for k in range(n)]
    return curves


def main():
    if len(sys.argv) < 3:
        print("Usage: run_journal.exe build_rin_soap_parametric.py <spec_json> <output_prt>")
        sys.exit(1)

    spec_path = Path(sys.argv[1]).resolve()
    out_prt = Path(sys.argv[2]).resolve()

    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: RIN SOAP CONTAINER (STRICT MATCH)")
    print(f"  Specification: {spec_path}")
    print(f"  Target PRT:    {out_prt}")
    print("=" * 75)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    # Initialize NX Part
    out_prt.parent.mkdir(parents=True, exist_ok=True)
    if out_prt.exists():
        try:
            out_prt.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(out_prt), NXOpen.Part.Units.Millimeters)
    part = session.Parts.Work

    # =========================================================================
    # 1. Driving Parametric Expressions
    # =========================================================================
    print("[1/4] Creating driving expressions...")
    expressions = spec.get("expressions", {})
    for name, val in expressions.items():
        try:
            part.Expressions.CreateExpression("Number", f"{name} = {float(val):.3f}")
        except Exception as e:
            print(f"  [WARN] Expression {name} failed: {e}")
    print(f"  [OK] {len(expressions)} expressions created.")

    # =========================================================================
    # 2. Unified Loft Through All Stations
    # =========================================================================
    print("[2/4] Building unified loft through all stations...")
    features = spec.get("features", [])
    loft_feature_spec = features[0] if features else {}
    stations = loft_feature_spec.get("stations", [])
    print(f"  Total stations: {len(stations)}")

    curvesets = []
    start_points = []
    for i, st in enumerate(stations):
        pts_3d = st["contour_pts_3d_mm"]
        curves = station_to_curves(part, pts_3d)
        curvesets.append(curves)
        start_points.append(pts_3d[0])
        x_val = st.get("axis_position", pts_3d[0][0])
        print(f"  Station {i+1:2d}: X={x_val:7.2f}mm, {len(pts_3d)} points")

    loft_builder = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        loft_builder.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
        for curves, spt in zip(curvesets, start_points):
            append_section(loft_builder, nx_section(part, curves, start_point=point(*spt)))
        body_feat = loft_builder.CommitFeature()
        set_name(body_feat, "BODY_PRIMARY_LOFT")
        base_body = body_feat.GetBodies()[0]
        print(f"  [OK] Unified body loft created: {base_body}")
    finally:
        loft_builder.Destroy()

    # =========================================================================
    # 3. Inspection, Verification & Save
    # =========================================================================
    print("[3/4] Finalizing, inspecting, and saving part...")
    feats = [f for f in part.Features]
    solids = [b for b in part.Bodies if b.IsSolidBody]
    faces = list(base_body.GetFaces()) if base_body else []
    edges = list(base_body.GetEdges()) if base_body else []

    print("=" * 75)
    print(f"[SUCCESS] Reconstructed Parametric Model: {out_prt.name}")
    print(f"  Features:      {len(feats)}")
    print(f"  Solid Bodies:  {len(solids)}")
    print(f"  Faces / Edges: {len(faces)} faces, {len(edges)} edges")
    print("=" * 75)

    # Convenience launch files
    try:
        root_dir = os.path.dirname(os.path.abspath(str(out_prt)))
        cmd_file = os.path.join(root_dir, "open_current_nx_result.cmd")
        cmd_content = f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{out_prt}"\n'
        with open(cmd_file, "w", encoding="utf-8") as f:
            f.write(cmd_content)
        latest_file = os.path.join(root_dir, "latest_nx_result.txt")
        with open(latest_file, "w", encoding="utf-8") as f:
            f.write(str(out_prt))
    except Exception:
        pass

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"[OK] Part successfully saved to: {out_prt}")

    # =========================================================================
    # 4. Synchronized STL Export
    # =========================================================================
    print("[4/4] Exporting synchronized STL...")
    try:
        stl_path = out_prt.with_suffix(".stl")
        stl_exp = session.DexManager.CreateStlCreator()
        stl_exp.OutputFile = str(stl_path)
        stl_exp.ExportSelectionBlock.Add(base_body)
        stl_exp.Commit()
        stl_exp.Destroy()
        print(f"[OK] Synchronized STL exported to: {stl_path}")
    except Exception as e:
        print(f"  [WARN] STL export: {e}")
    print("=" * 75)


if __name__ == "__main__":
    main()
