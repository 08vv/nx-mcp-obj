"""
build_rin_soap_v2_parametric.py
================================
Parametric NX CAD Builder for Rin Soap Bar — STRICT GEOMETRY MATCH.

Constructs a fully parametric, feature-based Siemens NX part (.prt) that
faithfully reconstructs the reference OBJ mesh (obj/Rin_soap_reduced.obj):

Feature tree:
  1. EXPRESSIONS      – Named parametric driving dimensions
  2. BODY_PRIMARY_LOFT – Solid Through-Curves loft through 45 organic stations
                         (96 pts/station) capturing:
                         • Elongated organic rounded-rectangular overall shape
                         • Strongly curved concave front face (8.4 mm indent)
                         • Broad smooth central body surface
                         • Inward-curved transitions at short ends
                         • Thick rounded outer perimeter
  3. END_BLEND         – Edge blend on end-cap edges for smooth organic feel
  4. STL_EXPORT        – Synchronized STL for validation

Coordinate system (NX):
  X = length (-100 to +100 mm, elongated direction)
  Y = width (-54 to +54 mm, front face at -Y with concave recess)
  Z = height (-34 to +34 mm)

Usage:
    run_journal.exe scripts/build_rin_soap_v2_parametric.py [spec_json] [output_prt]
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── NX License Setup ──
curr = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.3;28000@192.168.1.5;{curr}"

import NXOpen
import NXOpen.Features
import NXOpen.UF

UF = NXOpen.UF.UFSession.GetUFSession()


# ────────────────────────────────────────────────────────────────────
# NX helper utilities
# ────────────────────────────────────────────────────────────────────

def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))


def make_line(part, a: Tuple[float, ...], b: Tuple[float, ...]):
    return part.Curves.CreateLine(point(*a), point(*b))


def set_name(obj, name: str):
    if obj is None:
        return
    try:
        obj.SetName(name)
    except Exception:
        pass


def nx_section(part, curves, start_point=None):
    """Create an NX Section from a list of curves."""
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


def station_to_curves(part, pts_3d: List[List[float]]):
    """Convert a list of 3D point triplets into line segments forming a closed polygon."""
    n = len(pts_3d)
    return [make_line(part, pts_3d[k], pts_3d[(k + 1) % n]) for k in range(n)]


def apply_edge_blend(
    part,
    body,
    radius: float,
    name: str,
    edge_filter=None,
) -> Optional[Any]:
    """Try to apply an edge blend with fallback radii."""
    edges = list(body.GetEdges())
    if edge_filter:
        edges = [e for e in edges if edge_filter(e)]

    if not edges:
        print(f"  [SKIP] {name}: no qualifying edges found")
        return None

    radii_to_try = [radius]
    if radius > 2.0:
        radii_to_try.extend([radius * 0.75, radius * 0.5, 2.0, 1.5, 1.0])
    elif radius > 1.0:
        radii_to_try.extend([1.0, 0.8, 0.5])
    else:
        radii_to_try.extend([radius * 0.5, 0.3])

    for r in radii_to_try:
        bb = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            coll = part.ScCollectors.CreateCollector()
            coll.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(edges)], False)
            bb.Tolerance = 0.01
            bb.AddChainset(coll, f"{r:.2f}")
            feat = bb.CommitFeature()
            set_name(feat, name)
            print(f"  [OK] {name}: radius={r:.2f} mm on {len(edges)} edge(s)")
            return feat
        except Exception as e:
            print(f"  [TRY] {name}: radius={r:.2f} failed ({e})")
            continue
        finally:
            bb.Destroy()

    print(f"  [WARN] {name}: all radii failed")
    return None


def export_stl(session, part, body, out_stl: Path):
    """Export STL for validation."""
    print(f"\nExporting STL: {out_stl}")
    if out_stl.exists():
        try:
            out_stl.unlink()
        except Exception:
            pass

    stl_exp = session.DexManager.CreateStlCreator()
    try:
        stl_exp.OutputFile = str(out_stl)
        stl_exp.ExportSelectionBlock.Add(body)
        stl_exp.Commit()
        print(f"  [OK] STL exported: {out_stl} ({out_stl.stat().st_size:,} bytes)")
    except Exception as e:
        print(f"  [WARN] STL export: {e}")
    finally:
        stl_exp.Destroy()


# ────────────────────────────────────────────────────────────────────
# Main build
# ────────────────────────────────────────────────────────────────────

def main():
    repo_root = Path(__file__).resolve().parent.parent
    default_spec = repo_root / "Rin_soap_v2_spec.json"
    default_prt = repo_root / "Rin_soap_v2_Parametric.prt"

    spec_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_spec
    out_prt = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else default_prt
    out_stl = out_prt.with_suffix(".stl")

    print("=" * 75)
    print("PARAMETRIC NX RECONSTRUCTION: RIN SOAP BAR (V2 — STRICT GEOMETRY MATCH)")
    print(f"  Specification: {spec_path}")
    print(f"  Target PRT:    {out_prt}")
    print("=" * 75)

    if not spec_path.exists():
        print(f"[ERROR] Specification not found: {spec_path}")
        sys.exit(1)

    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    # ── Initialize NX Part ──────────────────────────────────────
    if out_prt.exists():
        try:
            out_prt.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(out_prt), NXOpen.Part.Units.Millimeters)

    # =====================================================================
    # STEP 1: Driving Parametric Expressions
    # =====================================================================
    print("\n[1/4] Creating parametric driving expressions...")
    expressions = spec.get("expressions", {})
    expr_count = 0
    for name, val in expressions.items():
        try:
            expr_str = f"{name} = {float(val):.4f}"
            part.Expressions.CreateExpression("Number", expr_str)
            print(f"  {expr_str}")
            expr_count += 1
        except Exception as e:
            print(f"  [WARN] {name}: {e}")
    print(f"  [OK] {expr_count} expressions created.\n")

    # =====================================================================
    # STEP 2: Body Primary Loft (Through Curves)
    # =====================================================================
    print("[2/4] Building body loft through organic cross-section stations...")
    loft_spec = spec["features"][0]
    stations = loft_spec["stations"]
    print(f"  Total stations: {len(stations)}")

    curvesets = []
    start_points = []
    for i, st in enumerate(stations):
        pts_3d = st["contour_pts_3d_mm"]
        curves = station_to_curves(part, pts_3d)
        curvesets.append(curves)
        start_points.append(pts_3d[0])
        x_val = st.get("axis_position", pts_3d[0][0])
        area = st.get("area_mm2", 0)
        print(f"  Station {i:2d}: X={x_val:8.2f}mm  area={area:8.1f}mm²  {len(pts_3d)} pts")

    loft_builder = part.Features.CreateThroughCurvesBuilder(NXOpen.Features.Feature.Null)
    try:
        loft_builder.BodyPreference = NXOpen.Features.ThroughCurvesBuilder.BodyPreferenceTypes.Solid
        for curves, spt in zip(curvesets, start_points):
            append_section(loft_builder, nx_section(part, curves, start_point=point(*spt)))
        body_feat = loft_builder.CommitFeature()
        set_name(body_feat, "BODY_PRIMARY_LOFT")
        main_body = body_feat.GetBodies()[0]
        print(f"  [OK] Primary body loft created successfully: {main_body}")
    except Exception as e:
        print(f"  [ERROR] Body loft failed: {e}")
        sys.exit(1)
    finally:
        loft_builder.Destroy()

    # =====================================================================
    # STEP 3: Dress-up Edge Blend (end caps)
    # =====================================================================
    print("\n[3/4] Applying dress-up edge blends...")
    blend_spec = spec["features"][1] if len(spec["features"]) > 1 else None

    if blend_spec:
        blend_radius = blend_spec.get("radius_mm", 3.0)

        # Identify end-cap edges (at extreme X positions)
        min_x_body = min(st["axis_position"] for st in stations)
        max_x_body = max(st["axis_position"] for st in stations)

        def is_end_edge(edge):
            try:
                v0, v1 = edge.GetVertices()
                x0, x1 = v0.X, v1.X
                return (abs(x0 - min_x_body) < 2.0 and abs(x1 - min_x_body) < 2.0) or \
                       (abs(x0 - max_x_body) < 2.0 and abs(x1 - max_x_body) < 2.0)
            except Exception:
                return False

        apply_edge_blend(part, main_body, blend_radius, "END_CAP_BLEND", is_end_edge)

    # =====================================================================
    # STEP 4: Inspection, Save & Export
    # =====================================================================
    print("\n[4/4] Inspecting and saving part...")
    feats = list(part.Features)
    solids = [b for b in part.Bodies if b.IsSolidBody]
    faces = list(main_body.GetFaces()) if main_body else []
    edges = list(main_body.GetEdges()) if main_body else []

    print("=" * 75)
    print(f"[SUCCESS] Reconstructed Parametric Model: {out_prt.name}")
    print(f"  Features:      {len(feats)}")
    print(f"  Solid Bodies:  {len(solids)}")
    print(f"  Faces / Edges: {len(faces)} faces, {len(edges)} edges")
    print(f"  Expressions:   {expr_count}")
    print("=" * 75)

    # Save part
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"\n[OK] Part saved: {out_prt}")

    # Export STL
    export_stl(session, part, main_body, out_stl)

    # Update quick-launch files
    try:
        cmd_file = repo_root / "open_current_nx_result.cmd"
        cmd_file.write_text(
            f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugraf.exe" "{out_prt}"\n',
            encoding="utf-8",
        )
        latest_file = repo_root / "latest_nx_result.txt"
        latest_file.write_text(str(out_prt), encoding="utf-8")
    except Exception:
        pass

    print("\n[DONE] Reconstruction complete.")


if __name__ == "__main__":
    main()
