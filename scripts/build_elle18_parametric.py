"""
build_elle18_parametric.py
==========================
NOTE: This script is for the "Elle18 Enamel Jar Container" (obj/elle18-enamel-jar_reduced.obj).
It does NOT build the Ellie 18 Cosmetic Eyeliner.
For the Ellie 18 Eyeliner, use scripts/build_ellie_18_parametric.py.
"""
- Tall cylindrical main body with slightly tapered sides and oblate cross-section
- Rounded bottom transition
- Distinct lower body curved ring features (Y ~ -78 to -68 mm)
- Upper body horizontal transition ring (Y ~ 36 to 42 mm)
- Wide rounded shoulder near the top (Y ~ 42 to 49 mm)
- Narrow neck transition below cap (Y ~ 49.5 to 52.5 mm, dia ~ 53.8 mm)
- Large cylindrical cap with rounded top dome edges
- Synchronized native coordinate system: X=Width, Y=Height, Z=Depth

Operates via NX Journal execution:
  run_journal.exe scripts/build_elle18_parametric.py
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

# Configure license servers
if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.5" not in os.environ.get("SPLM_LICENSE_SERVER", ""):
    curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.5;28000@SunFibo19;28000@192.168.1.29;28000@192.168.1.3;{curr}"

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
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
    n = len(pts_3d)
    return [make_line(part, pts_3d[k], pts_3d[(k + 1) % n]) for k in range(n)]


def apply_edge_blend_to_edges(part, edges: List[Any], radius_val: float, radius_expr_name: str, name: str) -> Optional[Any]:
    if not edges:
        return None

    radii_to_try = [radius_val]
    if radius_val > 2.0:
        radii_to_try.extend([radius_val * 0.75, radius_val * 0.5, 2.0, 1.5, 1.0])
    elif radius_val > 1.0:
        radii_to_try.extend([1.0, 0.8, 0.5])

    for r in radii_to_try:
        bb = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            coll = part.ScCollectors.CreateCollector()
            coll.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(edges)], False)
            bb.Tolerance = 0.01
            r_str = radius_expr_name if r == radius_val else f"{r:.2f}"
            bb.AddChainset(coll, r_str)
            feat = bb.CommitFeature()
            set_name(feat, name)
            print(f"  [OK] {name} applied with radius {r_str} mm on {len(edges)} edge(s).")
            return feat
        except Exception:
            continue
        finally:
            bb.Destroy()

    print(f"  [WARN] {name} failed with attempted radii.")
    return None


def export_stl(session, part, main_body, out_stl_path: Path):
    print(f"\nExporting STL: {out_stl_path}")
    if out_stl_path.exists():
        try:
            out_stl_path.unlink()
        except Exception:
            pass

    stl_exp = session.DexManager.CreateStlCreator()
    try:
        stl_exp.OutputFile = str(out_stl_path)
        stl_exp.ExportSelectionBlock.Add(main_body)
        stl_exp.Commit()
        print(f"  [OK] STL exported successfully: {out_stl_path} ({out_stl_path.stat().st_size:,} bytes)")
    except Exception as e:
        print(f"  [ERROR] STL export failed: {e}")
    finally:
        stl_exp.Destroy()


def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    default_spec = repo_root / "Elle18_parametric_spec.json"
    default_prt = repo_root / "Elle18_Parametric.prt"

    spec_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_spec
    out_prt = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: ELLE18 ENAMEL JAR (STRICT GEOMETRY)")
    print(f"  Specification: {spec_path}")
    print(f"  Target PRT:    {out_prt}")
    print("=" * 75)

    if not spec_path.exists():
        print(f"ERROR: Specification file not found: {spec_path}")
        sys.exit(1)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    if out_prt.exists():
        try:
            out_prt.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(out_prt), NXOpen.Part.Units.Millimeters)

    # 1. Driving Parametric Expressions
    print("\n[1/4] Creating parametric driving expressions...")
    expressions = spec.get("expressions", {})
    for name, val in expressions.items():
        try:
            exp_str = f"{name} = {float(val):.3f}"
            part.Expressions.CreateExpression("Number", exp_str)
            print(f"  Expression: {exp_str}")
        except Exception as e:
            print(f"  [WARN] Expression {name}: {e}")

    # 2. Main Solid Loft through all stations
    stations = spec.get("stations", [])
    print(f"\n[2/4] Lofting Solid Model through {len(stations)} stations...")
    curvesets = []
    start_points = []
    for pts in stations:
        curves = station_to_curves(part, pts)
        curvesets.append(curves)
        start_points.append(pts[0])

    loft_b = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        loft_b.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
        for curves, spt in zip(curvesets, start_points):
            append_section(loft_b, nx_section(part, curves, start_point=point(*spt)))
        body_feat = loft_b.CommitFeature()
        set_name(body_feat, "ELLE18_BODY_CAP_SOLID_LOFT")
        main_body = body_feat.GetBodies()[0]
        print(f"  [OK] Solid Body created successfully: {main_body}")
    finally:
        loft_b.Destroy()

    # 3. Dress-up Blends
    print("\n[3/4] Applying dress-up edge blends...")
    all_edges = list(main_body.GetEdges())
    if all_edges:
        all_y_coords = [e.GetVertices()[0].Y for e in all_edges] + [e.GetVertices()[1].Y for e in all_edges]
        min_body_y = min(all_y_coords)
        max_body_y = max(all_y_coords)

        # Base perimeter blend (lowest Y edges)
        r_base_blend = float(expressions.get("BASE_BLEND_RADIUS", 2.00))
        bot_edges = []
        for e in all_edges:
            v0, v1 = e.GetVertices()
            if abs(v0.Y - min_body_y) < 0.2 and abs(v1.Y - min_body_y) < 0.2:
                bot_edges.append(e)
        if bot_edges:
            apply_edge_blend_to_edges(part, bot_edges, r_base_blend, "BASE_BLEND_RADIUS", "BASE_PERIMETER_BLEND")
        else:
            print(f"  [INFO] Base perimeter edges not found near Y={min_body_y:.1f}; base already smooth.")

        # Cap top rim blend (highest Y edges)
        r_cap_blend = float(expressions.get("CAP_TOP_BLEND_RADIUS", 2.00))
        top_edges = []
        for e in all_edges:
            v0, v1 = e.GetVertices()
            if abs(v0.Y - max_body_y) < 0.2 and abs(v1.Y - max_body_y) < 0.2:
                top_edges.append(e)
        if top_edges:
            apply_edge_blend_to_edges(part, top_edges, r_cap_blend, "CAP_TOP_BLEND_RADIUS", "CAP_TOP_RIM_BLEND")
        else:
            print(f"  [INFO] Cap top edges not found near Y={max_body_y:.1f}; top dome already smooth.")

    # 4. Save Part & Export STL
    print("\n[4/4] Finalizing, inspecting, and saving part...")
    feats = [f for f in part.Features]
    solids = [b for b in part.Bodies if b.IsSolidBody]
    faces = list(main_body.GetFaces()) if main_body else []
    edges = list(main_body.GetEdges()) if main_body else []

    print("=" * 75)
    print(f"[SUCCESS] Reconstructed Parametric Model: {out_prt.name}")
    print(f"  Features:      {len(feats)}")
    print(f"  Solid Bodies:  {len(solids)}")
    print(f"  Faces / Edges: {len(faces)} faces, {len(edges)} edges")
    print("=" * 75)

    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"[OK] Part successfully saved to: {out_prt}")

    export_stl(session, part, main_body, out_stl)

    # Update quick-launch files
    cmd_file = repo_root / "open_current_nx_result.cmd"
    cmd_file.write_text(f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugraf.exe" "{out_prt}"\n', encoding="utf-8")
    latest_file = repo_root / "latest_nx_result.txt"
    latest_file.write_text(str(out_prt), encoding="utf-8")

    print(f"[OK] Updated {cmd_file.name} and {latest_file.name}")
    print("\nReconstruction completed successfully.")


if __name__ == "__main__":
    main()
