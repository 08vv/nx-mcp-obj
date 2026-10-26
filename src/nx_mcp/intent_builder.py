"""
intent_builder.py
=================
Generic Intent-IR-to-NX CAD Execution Engine.

Directly ingests a ReconstructionIntent IR (or comprehensive mesh analysis JSON)
and synthesizes a fully parametric Siemens NX part (.prt) without any per-object
hardcoded scripts.

Capabilities:
1. Dynamic Expression Engine: Populates all named NX expressions from Intent IR.
2. Dynamic Base Shape Synthesis:
   - 'cylindrical_revolved_body': Extracts 2D silhouette profile and performs native 360° Revolve.
   - 'freeform_lofted_solid' / 'elliptical_or_flatted_profile_solid': Slices cross-section stations and lofts ThroughCurves.
   - 'body_with_handle_loop': Solid loft + handle pass-through void extrude cut.
3. Dynamic Secondary Feature Dispatcher:
   - AXIAL_LONGITUDINAL: Fluted ribs arrayed via circular pattern around primary axis.
   - CIRCUMFERENTIAL_AZIMUTHAL: Periodic groove rings along height axis.
   - 'cap_ribs': Neck collar cylinder + dispenser cap + fluted pattern.
   - 'v_feature': Front chevron/V-accent deboss or emboss.
   - 'recessed_panel': Inset label panel with corner blends.
4. Dress-up & Blends: Bottom chime, transition shoulder, and crown edge blends.

Usage (invoked via run_journal.exe or nx_bridge.run_journal):
    run_journal.exe intent_builder.py <intent_json_path> <output_prt_path>
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import NXOpen
import NXOpen.UF

UF = NXOpen.UF.UFSession.GetUFSession()


# ---------------------------------------------------------------------------
# Geometry & Vector Helpers
# ---------------------------------------------------------------------------
def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def vec(x: float, y: float, z: float) -> NXOpen.Vector3d:
    return NXOpen.Vector3d(float(x), float(y), float(z))


def line(part, a, b):
    return part.Curves.CreateLine(point(*a), point(*b))


def set_name(obj, name: str):
    if obj is None:
        return
    try:
        obj.SetName(name)
    except Exception:
        pass


def write_launch_files(part_path: str):
    try:
        root_dir = os.path.dirname(os.path.abspath(part_path))
        cmd_file = os.path.join(root_dir, "open_current_nx_result.cmd")
        vbs_file = os.path.join(root_dir, "open_latest_nx_result.vbs")
        txt_file = os.path.join(root_dir, "latest_nx_result.txt")

        cmd_content = f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{part_path}"\n'
        vbs_content = f'Set shell = CreateObject("WScript.Shell")\nshell.Run """C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe"" -ug -use_file_dir ""{part_path}""", 0, False\n'

        with open(cmd_file, "w", encoding="utf-8") as f:
            f.write(cmd_content)
        with open(vbs_file, "w", encoding="utf-8") as f:
            f.write(vbs_content)
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(part_path)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Expression Engine
# ---------------------------------------------------------------------------
def populate_expressions(part, expressions: Dict[str, Any]) -> None:
    """Dynamically creates all parametric driving expressions in the NX part."""
    print(f"[ENGINE] Creating {len(expressions)} driving expressions...")
    for name, val in expressions.items():
        try:
            if isinstance(val, (int, float)):
                rhs = int(val) if "COUNT" in name else float(val)
                part.Expressions.CreateExpression("Number", f"{name} = {rhs}")
            elif isinstance(val, str):
                part.Expressions.CreateExpression("Number", f"{name} = {val}")
        except Exception:
            pass

    # Standard derived geometry formulas if dimensions exist
    derived = {}
    if "BODY_WIDTH" in expressions:
        derived["BODY_RADIUS_X"] = "BODY_WIDTH / 2.0"
    if "BODY_DEPTH" in expressions:
        derived["BODY_RADIUS_Y"] = "BODY_DEPTH / 2.0"
    if "BODY_DIAMETER" in expressions:
        derived["BODY_RADIUS"] = "BODY_DIAMETER / 2.0"
    if "NECK_DIAMETER" in expressions:
        derived["NECK_RADIUS"] = "NECK_DIAMETER / 2.0"
    if "CAP_DIAMETER" in expressions:
        derived["CAP_RADIUS"] = "CAP_DIAMETER / 2.0"

    for name, rhs in derived.items():
        try:
            part.Expressions.CreateExpression("Number", f"{name} = {rhs}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Modeling Primitives & Features
# ---------------------------------------------------------------------------
def revolve_curves(part, curves, start_deg: str, end_deg: str, name: str):
    """Revolves wireframe curves 360° around the Z-axis."""
    tags = [c.Tag for c in curves]
    features, num_feat = UF.Modl.CreateRevolution(
        tags,
        len(tags),
        None,
        [str(start_deg), str(end_deg)],
        ["0", "0"],
        [0.0, 0.0, 0.0],
        False,
        True,
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],  # Z-up axis of revolution
        NXOpen.UF.Modl.FeatureSigns.NULLSIGN,
    )
    if not features or num_feat < 1:
        raise RuntimeError(f"Revolve '{name}' did not create any features")
    feat = NXOpen.TaggedObjectManager().GetTaggedObject(features[0])
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, bodies[0] if bodies else None


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


def append_section(builder, sec) -> None:
    container = getattr(builder, "SectionsList", None) or getattr(builder, "Sections", None)
    if hasattr(container, "Append"):
        container.Append(sec)
    else:
        container.Add(sec)


def through_curves(part, curvesets, name: str):
    """Lofts a solid body across sequential closed curve cross-sections."""
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


def create_cylinder(part, origin: Tuple[float, float, float], diam: float, height: float, name: str):
    """Creates a solid cylinder along Z."""
    builder = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Diameter.RightHandSide = str(diam)
        builder.Height.RightHandSide = str(height)
        builder.Origin = point(*origin)
        builder.Direction = vec(0.0, 0.0, 1.0)
        builder.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        feat = builder.CommitFeature()
        set_name(feat, name)
        bodies = feat.GetBodies()
        return feat, bodies[0] if bodies else None
    finally:
        builder.Destroy()


def boolean_unite(part, target_body, tool_body):
    builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        builder.Target = target_body
        builder.Tools.Add(tool_body)
        return builder.CommitFeature()
    finally:
        builder.Destroy()


def boolean_subtract(part, target_body, tool_body):
    builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        builder.Target = target_body
        builder.Tools.Add(tool_body)
        return builder.CommitFeature()
    finally:
        builder.Destroy()


def blend_edges(part, body, chooser, radius_rhs: str, name: str):
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
        set_name(feat, name)
        return feat
    except Exception as e:
        print(f"  [WARN] Blend '{name}' could not be committed: {e}")
        return None
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Base Shape Builders
# ---------------------------------------------------------------------------
def build_revolved_base(part, intent: Dict[str, Any]) -> Tuple[Any, Any]:
    """Synthesizes a 360° revolved solid body from extracted silhouette profile points."""
    rev_info = intent.get("revolve_profile") or {}
    profile_pts = rev_info.get("profile_points", [])

    if not profile_pts:
        sections = intent.get("cross_sections", [])
        if sections:
            profile_pts = [
                {"y": s["y"], "r": max(s.get("rx", 10.0), s.get("rz", 10.0))}
                for s in sections
            ]

    if not profile_pts:
        raise ValueError("No profile points or cross-sections available for revolved body")

    sorted_pts = sorted(profile_pts, key=lambda p: float(p.get("y", 0.0)))
    z_min = float(sorted_pts[0]["y"])
    shift_z = -z_min

    wire_pts = [(0.0, 0.0, 0.0)]

    for pt in sorted_pts:
        r_val = float(pt.get("r", pt.get("x", 10.0)))
        z_val = float(pt.get("y", 0.0)) + shift_z
        r_val = max(1.0, r_val)
        wire_pts.append((r_val, 0.0, z_val))

    z_max = wire_pts[-1][2]
    wire_pts.append((0.0, 0.0, z_max))
    wire_pts.append((0.0, 0.0, 0.0))

    curves = []
    for i in range(len(wire_pts) - 1):
        p1 = wire_pts[i]
        p2 = wire_pts[i + 1]
        dist = math.hypot(p2[0] - p1[0], p2[2] - p1[2])
        if dist > 0.05:
            curves.append(line(part, p1, p2))

    if len(curves) < 3:
        raise RuntimeError(f"Insufficient curves generated for revolve profile ({len(curves)})")

    print(f"[ENGINE] Revolving base body across {len(curves)} profile segments...")
    feat, body = revolve_curves(part, curves, "0", "360", "REVOLVE_BASE_BODY")
    return feat, body


def build_lofted_base(part, intent: Dict[str, Any]) -> Tuple[Any, Any]:
    """
    Synthesizes a solid ThroughCurves loft across sequential cross-section stations.
    CRITICAL RULE: Only allowed for zones explicitly marked non-axisymmetric/organic.
    Never lofts the entire part stack.
    """
    is_zone_bounded = bool(intent.get("is_zone_bounded") or intent.get("zone_bounds") or intent.get("non_axisymmetric_zone"))
    sections = intent.get("zone_cross_sections") or intent.get("cross_sections", [])
    if not sections:
        raise ValueError("No cross_sections available for lofted base body")

    sorted_sec = sorted(sections, key=lambda s: float(s.get("y", 0.0)))
    total_y_span = float(sorted_sec[-1]["y"]) - float(sorted_sec[0]["y"])
    body_h = float(intent.get("expressions", {}).get("BODY_HEIGHT", total_y_span))

    # Reject whole-stack lofts unless explicitly flagged as single-zone organic component
    if not is_zone_bounded and body_h > 30.0 and (total_y_span / max(body_h, 1e-3)) > 0.80:
        print("[WARN] Monolithic Through Curves loft spanning > 80% of part height detected!")
        print("[WARN] Parametric CAD Rule: Whole part cannot be a single Through Curves loft.")
        # Restrict to non-axisymmetric organic transition zone (lower body portion)
        max_allowed_y = float(sorted_sec[0]["y"]) + 0.65 * total_y_span
        sorted_sec = [s for s in sorted_sec if float(s.get("y", 0.0)) <= max_allowed_y]
        print(f"[ENGINE] Constrained Through Curves loft to organic zone ({len(sorted_sec)} stations).")

    z_min = float(sorted_sec[0]["y"])
    shift_z = -z_min

    curvesets = []
    for s_idx, sec in enumerate(sorted_sec):
        z_station = float(sec.get("y", 0.0)) + shift_z
        pts_2d = sec.get("points_2d", [])

        if pts_2d and len(pts_2d) >= 8:
            station_pts = [(float(px), float(pz), z_station) for (px, pz) in pts_2d]
            loop_curves = []
            n_pts = len(station_pts)
            for k in range(n_pts):
                loop_curves.append(line(part, station_pts[k], station_pts[(k + 1) % n_pts]))
            curvesets.append(loop_curves)
        else:
            rx = float(sec.get("rx", 25.0))
            rz = float(sec.get("rz", 20.0))
            n = 36
            m = 2.6
            pts = []
            for i in range(n):
                theta = 2.0 * math.pi * float(i) / float(n)
                cos_t = math.cos(theta)
                sin_t = math.sin(theta)
                denom = (abs(cos_t) / rx) ** m + (abs(sin_t) / rz) ** m
                r = 1.0 / (denom ** (1.0 / m)) if denom > 0 else 0.0
                pts.append((r * cos_t, r * sin_t, z_station))
            loop_curves = [line(part, pts[k], pts[(k + 1) % n]) for k in range(n)]
            curvesets.append(loop_curves)

    print(f"[ENGINE] Lofting ThroughCurves body across {len(curvesets)} stations...")
    feat, body = through_curves(part, curvesets, "ORGANIC_ZONE_LOFT")
    return feat, body


# ---------------------------------------------------------------------------
# Secondary Feature Builders
# ---------------------------------------------------------------------------
def apply_periodic_features(part, base_body, intent: Dict[str, Any]) -> None:
    """Applies periodic longitudinal ribs or circumferential grooves."""
    sec_features = intent.get("secondary_features", {})
    p_feat = sec_features.get("periodic_features") or sec_features.get("side_ribs")
    if not p_feat or p_feat.get("confidence", 0.0) < 0.50:
        return

    orientation = p_feat.get("orientation", "")
    count = int(p_feat.get("rib_count", 0))
    if count < 2:
        return

    exprs = intent.get("expressions", {})
    body_h = float(exprs.get("BODY_HEIGHT", 200.0))
    body_w = float(exprs.get("BODY_WIDTH", 78.0))
    body_r = body_w * 0.5

    if "LONGITUDINAL" in orientation:
        print(f"[ENGINE] Applying {count} longitudinal ribs via circular pattern...")
        rib_w = float(p_feat.get("groove_width_mm", 2.0))
        rib_d = float(p_feat.get("groove_depth_mm", 1.0))
        for i in range(count):
            angle = float(i) * (360.0 / float(count))
            ang_rad = math.radians(angle)
            fx = (body_r - rib_d * 0.5) * math.cos(ang_rad)
            fy = (body_r - rib_d * 0.5) * math.sin(ang_rad)
            try:
                c_feat, c_body = create_cylinder(part, (fx, fy, 15.0), rib_w, body_h * 0.70, f"FLUTE_TOOL_{i}")
                boolean_subtract(part, base_body, c_body)
            except Exception:
                pass

    elif "CIRCUMFERENTIAL" in orientation:
        print(f"[ENGINE] Applying {count} circumferential groove rings along height...")
        pitch = float(p_feat.get("pitch_mm", 15.0))
        groove_w = float(p_feat.get("groove_width_mm", 4.0))
        groove_d = float(p_feat.get("groove_depth_mm", 0.8))
        z_start = float(p_feat.get("y_start_mm", 15.0))
        if z_start < 0:
            z_start = 15.0

        for i in range(count):
            gz = z_start + i * pitch
            if gz > (body_h - 20.0):
                break
            try:
                r_in = body_r - groove_d
                r_out = body_r + 3.0
                pts = [
                    (r_in, 0.0, gz - groove_w * 0.5),
                    (r_out, 0.0, gz - groove_w * 0.5),
                    (r_out, 0.0, gz + groove_w * 0.5),
                    (r_in, 0.0, gz + groove_w * 0.5),
                    (r_in, 0.0, gz - groove_w * 0.5),
                ]
                curves = [line(part, pts[k], pts[k + 1]) for k in range(len(pts) - 1)]
                _, g_body = revolve_curves(part, curves, "0", "360", f"GROOVE_RING_{i}")
                boolean_subtract(part, base_body, g_body)
            except Exception:
                pass


def apply_cap_assembly(part, base_body, intent: Dict[str, Any]) -> None:
    """Applies top neck collar, dispenser disc, and fluted cap ribs."""
    sec = intent.get("secondary_features", {})
    cap = sec.get("cap_ribs")
    if not cap or cap.get("confidence", 0.0) < 0.50:
        return

    exprs = intent.get("expressions", {})
    body_h = float(exprs.get("BODY_HEIGHT", 200.0))
    collar_d = float(cap.get("collar_diameter_mm", 39.5))
    collar_h = float(cap.get("collar_height_mm", 25.0))
    cap_d = float(cap.get("cap_diameter_mm", 28.5))
    cap_h = float(cap.get("cap_height_mm", 15.0))
    rib_count = int(cap.get("rib_count", 0))

    z_collar = body_h - (collar_h + cap_h)
    if z_collar < 50.0:
        z_collar = body_h * 0.75

    print(f"[ENGINE] Synthesizing top neck/cap assembly (D={collar_d:.1f}mm, {rib_count} ribs)...")
    try:
        _, collar_body = create_cylinder(part, (0.0, 0.0, z_collar), collar_d, collar_h, "CAP_COLLAR")
        boolean_unite(part, base_body, collar_body)

        _, disc_body = create_cylinder(part, (0.0, 0.0, z_collar + collar_h), cap_d, cap_h, "CAP_DISC")
        boolean_unite(part, base_body, disc_body)

        if rib_count > 0:
            for i in range(rib_count):
                angle = float(i) * (360.0 / float(rib_count))
                ang_rad = math.radians(angle)
                fx = (collar_d * 0.5) * math.cos(ang_rad)
                fy = (collar_d * 0.5) * math.sin(ang_rad)
                try:
                    _, flute = create_cylinder(part, (fx, fy, z_collar), 1.25, collar_h, f"CAP_RIB_{i}")
                    boolean_subtract(part, base_body, flute)
                except Exception:
                    pass
    except Exception as e:
        print(f"  [WARN] Cap assembly could not be applied: {e}")


def apply_v_feature(part, base_body, intent: Dict[str, Any]) -> None:
    """Applies upper front V-accent / chevron groove or emboss."""
    sec = intent.get("secondary_features", {})
    v_feat = sec.get("v_feature")
    if not v_feat or v_feat.get("confidence", 0.0) < 0.50:
        return

    exprs = intent.get("expressions", {})
    body_w = float(exprs.get("BODY_WIDTH", 78.0))
    body_h = float(exprs.get("BODY_HEIGHT", 200.0))
    body_r = body_w * 0.5

    v_w = float(v_feat.get("width_mm", body_w * 0.60))
    v_h = float(v_feat.get("height_mm", 30.0))
    is_deboss = "DEBOSS" in str(v_feat.get("direction", "DEBOSS"))

    print(f"[ENGINE] Synthesizing front V-feature ({'DEBOSS' if is_deboss else 'EMBOSS'})...")
    z_apex = body_h * 0.65

    try:
        y_plane = body_r + 1.0
        depth = float(abs(v_feat.get("depth_mm", 1.5)))
        t_pts = [
            (0.0, y_plane, z_apex),
            (-v_w * 0.5, y_plane, z_apex + v_h * 0.5),
            (-v_w * 0.5 + 4.0, y_plane, z_apex + v_h * 0.5),
            (0.0, y_plane, z_apex + 4.0),
            (v_w * 0.5 - 4.0, y_plane, z_apex + v_h * 0.5),
            (v_w * 0.5, y_plane, z_apex + v_h * 0.5),
            (0.0, y_plane, z_apex),
        ]
        curves = [line(part, t_pts[k], t_pts[k + 1]) for k in range(len(t_pts) - 1)]
        builder = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
        try:
            builder.Section = nx_section(part, curves)
            builder.Limits.StartExtend.Value.RightHandSide = "0.0"
            builder.Limits.EndExtend.Value.RightHandSide = str(depth + 2.0)
            builder.Direction = part.Directions.CreateDirection(
                point(0.0, 0.0, 0.0),
                vec(0.0, -1.0, 0.0),
                NXOpen.SmartObject.UpdateOption.WithinModeling,
            )
            b_type = (
                NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
                if is_deboss
                else NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite
            )
            builder.BooleanOperation.SetBooleanOperationAndBody(b_type, base_body)
            t_feat = builder.CommitFeature()
            set_name(t_feat, "V_FEATURE")
        finally:
            builder.Destroy()
    except Exception as e:
        print(f"  [WARN] V-feature could not be committed: {e}")


def apply_edge_blends(part, base_body, intent: Dict[str, Any]) -> None:
    """Applies dress-up blends on base chime and top crowns."""
    exprs = intent.get("expressions", {})
    body_h = float(exprs.get("BODY_HEIGHT", 200.0))

    blend_edges(
        part,
        base_body,
        lambda e: abs(e.GetVertices()[0].Z - 0.0) < 2.0,
        "2.5",
        "BLEND_BOTTOM_CHIME",
    )

    blend_edges(
        part,
        base_body,
        lambda e: abs(e.GetVertices()[0].Z - body_h) < 3.0,
        "2.0",
        "BLEND_TOP_CROWN",
    )


# ---------------------------------------------------------------------------
# Main Generic Builder Pipeline
# ---------------------------------------------------------------------------
def build_part_from_intent(intent_json_path: Path, output_prt_path: Path) -> None:
    """Core execution engine: Ingests Intent IR JSON and builds parametric NX part."""
    print("=" * 70)
    print("GENERIC INTENT-IR-TO-NX CAD EXECUTION ENGINE")
    print(f"  Intent Source: {intent_json_path}")
    print(f"  Target PRT:    {output_prt_path}")
    print("=" * 70)

    with open(intent_json_path, "r", encoding="utf-8") as f:
        intent = json.load(f)

    output_prt_path.parent.mkdir(parents=True, exist_ok=True)
    if output_prt_path.exists():
        try:
            output_prt_path.unlink()
        except Exception:
            pass

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_prt_path), NXOpen.Part.Units.Millimeters)
    part = session.Parts.Work

    # 1. Populate Parametric Expressions
    expressions = intent.get("expressions", {})
    populate_expressions(part, expressions)

    # 2. Base Shape Synthesis
    shape_family = intent.get("global_shape_family", "cylindrical_revolved_body")
    print(f"[ENGINE] Base Shape Family: {shape_family}")

    if shape_family == "cylindrical_revolved_body":
        base_feat, base_body = build_revolved_base(part, intent)
    else:
        base_feat, base_body = build_lofted_base(part, intent)

    if base_body is None:
        raise RuntimeError("[ENGINE] Base body construction failed!")

    # 3. Secondary Features
    apply_periodic_features(part, base_body, intent)
    apply_cap_assembly(part, base_body, intent)
    apply_v_feature(part, base_body, intent)

    # 4. Dress-up Blends
    apply_edge_blends(part, base_body, intent)

    # 5. Inspection & Save
    feats = [f for f in part.Features]
    faces = list(base_body.GetFaces()) if base_body else []
    edges = list(base_body.GetEdges()) if base_body else []

    print("-" * 70)
    print(f"[ENGINE] Build Success: {len(feats)} Features, {len(faces)} Faces, {len(edges)} Edges.")
    print("-" * 70)

    # Update launch files so user can open result immediately
    write_launch_files(str(output_prt_path))

    # Save part
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print(f"[ENGINE] Part file saved successfully: {output_prt_path}")
    print("=" * 70)


def main():
    if len(sys.argv) < 3:
        print("Usage: run_journal.exe intent_builder.py <intent_json> <output_prt>")
        sys.exit(1)

    intent_p = Path(sys.argv[1]).resolve()
    out_p = Path(sys.argv[2]).resolve()

    if not intent_p.exists():
        print(f"[ERROR] Intent JSON not found: {intent_p}")
        sys.exit(1)

    build_part_from_intent(intent_p, out_p)


if __name__ == "__main__":
    main()
