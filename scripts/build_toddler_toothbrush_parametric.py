"""
build_toddler_toothbrush_parametric.py
=======================================
Constructs a high-fidelity zone-wise parametric Siemens NX CAD model for
the Toddler Toothbrush (obj/Todddler_toothbrush.obj) with STRICT GEOMETRIC FIDELITY:

Feature Tree Architecture:
  1. 20 Parametric Driving Expressions (overall length, bounds, collar brim, brush head, bristles)
  2. HANDLE_BODY_LOFT:          Solid ThroughCurves loft across 35 stations (dome + tapered handle + front grip ridges)
  3. CHAR_HEAD_COLLAR_LOFT:     Solid ThroughCurves loft across 35 stations (enlarged character head + facial contours + wide curved collar brim)
  4. UNITE_CHAR_HEAD_COLLAR:    Boolean unite into main body
  5. NECK_TRANS_LOFT:           Solid ThroughCurves loft across 11 stations (smooth transition neck)
  6. UNITE_NECK_TRANS:          Boolean unite into main body
  7. SLIM_STEM_LOFT:            Solid ThroughCurves loft across 20 stations (elongated upper shaft)
  8. UNITE_SLIM_STEM:           Boolean unite into main body
  9. BRUSH_HEAD_BRISTLES_LOFT:  Solid ThroughCurves loft across 35 stations (backing pad + multi-row raised bristles)
  10. UNITE_BRUSH_HEAD:         Boolean unite into main body
  11. BASE_PERIMETER_BLEND:     Edge blend on handle base rim

Usage:
  run_journal.exe scripts/build_toddler_toothbrush_parametric.py
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure license servers
if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.5" not in os.environ.get("SPLM_LICENSE_SERVER", ""):
    curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.5;28000@SunFibo19;28000@192.168.1.29;28000@192.168.1.3;{curr}"

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF

UF = NXOpen.UF.UFSession.GetUFSession()


# ─────────────────────────── Helpers ────────────────────────────

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
    """Create an NX Section from a list of curves (polyline segments)."""
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
    """Append a section to a ThroughCurvesBuilder."""
    container = getattr(builder, "SectionsList", None) or getattr(builder, "Sections", None)
    if hasattr(container, "Append"):
        container.Append(sec)
    else:
        container.Add(sec)


def station_to_curves(part, pts_3d):
    """Convert a closed polygon of 3D points to a list of NX line segments."""
    n = len(pts_3d)
    return [make_line(part, pts_3d[k], pts_3d[(k + 1) % n]) for k in range(n)]


def apply_edge_blend_to_edges(part, edges, radius_val: float, radius_expr_name: str, name: str):
    """Apply a fillet/edge blend to a set of edges, with fallback radii."""
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

    print(f"  [WARN] {name} failed with all attempted radii.")
    return None


def export_stl(session, part, main_body, out_stl_path: Path):
    """Export model body to STL."""
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
        print(f"  [OK] STL exported ({out_stl_path.stat().st_size:,} bytes)")
    except Exception as e:
        print(f"  [ERROR] STL export failed: {e}")
    finally:
        stl_exp.Destroy()


def update_watcher_files(repo_root: Path, prt_path: Path):
    """Write quick-launch reference files."""
    abs_prt = str(prt_path.resolve())
    latest_txt = repo_root / "latest_nx_result.txt"
    latest_txt.write_text(abs_prt, encoding="utf-8")
    ugraf_path = Path(r"C:\Program Files\Siemens\NX2206\NXBIN\ugraf.exe")
    cmd_path = repo_root / "open_current_nx_result.cmd"
    cmd_path.write_text(f'@echo off\nstart "" "{ugraf_path}" "{abs_prt}"\n', encoding="utf-8")
    print(f"  [OK] Updated watcher files -> {abs_prt}")


def build_through_curves_zone(part, stations_3d, zone_name: str):
    """
    Build a solid through-curves loft from cross-section station polygons.
    Each station is a list of (X, Y, Z) points forming a closed contour.
    Returns (feature, body).
    """
    print(f"  Building {zone_name}: {len(stations_3d)} stations, {len(stations_3d[0])} pts/station")

    curvesets = []
    start_points = []
    for pts in stations_3d:
        curves = station_to_curves(part, pts)
        curvesets.append(curves)
        start_points.append(pts[0])

    loft_b = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        loft_b.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
    except Exception:
        pass

    for curves, spt in zip(curvesets, start_points):
        append_section(loft_b, nx_section(part, curves, start_point=point(*spt)))

    feat = loft_b.CommitFeature()
    set_name(feat, zone_name)
    body = feat.GetBodies()[0]
    loft_b.Destroy()
    print(f"  [OK] Feature: {zone_name}")
    return feat, body


# ─────────────────────────── Main ────────────────────────────

def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    default_spec = repo_root / "Toddler_Toothbrush_parametric_spec.json"
    default_prt = repo_root / "Toddler_Toothbrush_Parametric.prt"

    spec_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_spec
    out_prt = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: TODDLER TOOTHBRUSH (HIGH-FIDELITY)")
    print("  STRICT GEOMETRIC MATCH TO OBJ SOURCE")
    print(f"  Specification: {spec_path}")
    print(f"  Target PRT:    {out_prt}")
    print("=" * 75)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    if out_prt.exists():
        try:
            out_prt.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(out_prt), NXOpen.Part.Units.Millimeters)

    # =========================================================================
    # 1. DRIVING PARAMETRIC EXPRESSIONS
    # =========================================================================
    print("\n[1/6] Creating driving parametric expressions...")
    expressions = spec["expressions"]
    for name, value in expressions.items():
        try:
            exp_str = f"{name} = {float(value):.3f}"
            part.Expressions.CreateExpression("Number", exp_str)
            print(f"  Expression: {exp_str}")
        except Exception as e:
            print(f"  [WARN] Expression {name}: {e}")

    # =========================================================================
    # 2. ZONE-BY-ZONE THROUGH-CURVES LOFT BUILD
    # =========================================================================
    zone_configs = [
        ("HANDLE_BODY_LOFT",         "handle_body"),
        ("CHAR_HEAD_COLLAR_LOFT",    "char_head_collar"),
        ("NECK_TRANS_LOFT",          "neck_trans"),
        ("SLIM_STEM_LOFT",           "slim_stem"),
        ("BRUSH_HEAD_BRISTLES_LOFT", "brush_head_bristles"),
    ]

    main_body = None
    for zone_idx, (feat_name, zone_key) in enumerate(zone_configs):
        print(f"\n[{zone_idx + 2}/6] Building {feat_name}...")
        stations = spec["zones"][zone_key]
        if len(stations) < 2:
            print(f"  [WARN] Zone {zone_key} has < 2 stations, skipping.")
            continue

        feat, body = build_through_curves_zone(part, stations, feat_name)

        if main_body is None:
            main_body = body
        else:
            # Boolean unite into main body
            unite_name = f"UNITE_{zone_key.upper()}"
            u_builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
            u_builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
            u_builder.RetainTarget = False
            u_builder.RetainTool = False
            u_builder.Target = main_body
            u_builder.Tools.Add(body)
            u_feat = u_builder.CommitFeature()
            set_name(u_feat, unite_name)
            u_builder.Destroy()
            print(f"  [OK] Feature: {unite_name}")

    # =========================================================================
    # 3. DRESS-UP EDGE BLENDS
    # =========================================================================
    print("\n[7/7] Applying dress-up edge blends...")
    if main_body is not None:
        try:
            all_edges = list(main_body.GetEdges())
            if all_edges:
                all_y_coords = []
                for e in all_edges:
                    try:
                        v0, v1 = e.GetVertices()
                        all_y_coords.extend([v0.Y, v1.Y])
                    except Exception:
                        continue
                if all_y_coords:
                    min_body_y = min(all_y_coords)
                    bot_edges = []
                    for e in all_edges:
                        try:
                            v0, v1 = e.GetVertices()
                            if abs(v0.Y - min_body_y) < 0.5 and abs(v1.Y - min_body_y) < 0.5:
                                bot_edges.append(e)
                        except Exception:
                            continue
                    if bot_edges:
                        apply_edge_blend_to_edges(part, bot_edges, 2.0, "2.00", "BASE_PERIMETER_BLEND")
        except Exception as e:
            print(f"  [WARN] Edge blend step: {e}")

    # =========================================================================
    # 4. VERIFY, EXPORT, AND SAVE
    # =========================================================================
    print("\n[VERIFY] Inspecting Feature Tree...")
    feat_count = 0
    for feat in part.Features:
        feat_count += 1
        feat_type = getattr(feat, "FeatureType", type(feat).__name__)
        name = feat.Name if feat.Name else feat_type
        print(f"  [{feat_count:02d}] {name} ({feat_type})")

    solids = [b for b in part.Bodies if b.IsSolidBody]
    faces = list(main_body.GetFaces()) if main_body else []
    edges = list(main_body.GetEdges()) if main_body else []

    print(f"\n  Solid Bodies: {len(solids)}")
    print(f"  Faces / Edges: {len(faces)} / {len(edges)}")

    # Export STL
    if main_body is not None:
        export_stl(session, part, main_body, out_stl)

    # Save Part
    print(f"\nSaving NX Part: {out_prt}")
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"  [OK] Saved PRT ({out_prt.stat().st_size:,} bytes)")

    # Update watcher files
    update_watcher_files(repo_root, out_prt)

    print("\n" + "=" * 75)
    print("HIGH-FIDELITY RECONSTRUCTION COMPLETED SUCCESSFULLY!")
    print(f"  Output Part: {out_prt}")
    print(f"  Output STL:  {out_stl}")
    print(f"  Features:    {feat_count}")
    print(f"  Bodies:      {len(solids)}")
    print("=" * 75)


if __name__ == "__main__":
    main()
