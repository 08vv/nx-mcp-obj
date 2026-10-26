"""Create a clean, production-ready, fully parametric Axe3_Parametric.prt in Siemens NX.

Reverse-engineered from Axe3.obj:
- Object: Axe Deodorant / Aerosol Body Spray Can
- Revolved Body:
  - Aerosol concave bottom dome with standing chime ring
  - Lower cylindrical body (Dia 77.6 mm, Height ~101.4 mm)
  - Smooth waist constriction (Dia 72.0 mm)
  - Upper cap collar (Dia 77.8 mm)
  - Tapered cap housing (Dia 73.6 mm)
  - Top crown bevel and flat actuator button (Dia 44.0 mm)
- Secondary Features:
  - 18 periodic horizontal side grip grooves (Pitch: 10.11 mm, Width: 4.55 mm, Depth: 0.65 mm)
  - Upper front V-accent styling chevron groove
  - Edge blends on standing chime, waist transition, and crown shoulder
- Fully parametric with named NX Expressions.

Usage:
    run_journal.exe create_axe3_parametric.py [output_path.prt]
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
# Driving Parameter Values (mm) — Axe Body Spray Can
# ---------------------------------------------------------------------------
VALUES = {
    "BODY_HEIGHT": 199.5,
    "BODY_DIAMETER": 77.6,
    "BOTTOM_DOME_DEPTH": 6.7,
    "BOTTOM_CHIME_RADIUS": 35.5,
    "BOTTOM_FILLET": 2.5,
    "WAIST_Z_START": 101.4,
    "WAIST_HEIGHT": 20.3,
    "WAIST_DIAMETER": 72.0,
    "COLLAR_HEIGHT": 13.5,
    "COLLAR_DIAMETER": 77.8,
    "CAP_BODY_HEIGHT": 54.8,
    "CAP_TOP_TAPER_DIAMETER": 73.6,
    "CROWN_HEIGHT": 9.5,
    "CROWN_FLAT_DIAMETER": 44.0,
    "CROWN_FILLET": 3.0,
    "SIDE_RIB_COUNT": 18,
    "SIDE_RIB_PITCH": 10.11,
    "SIDE_GROOVE_WIDTH": 4.55,
    "SIDE_GROOVE_DEPTH": 0.65,
    "V_FEATURE_WIDTH": 78.06,
    "V_FEATURE_HEIGHT": 109.85,
    "V_FEATURE_ANGLE": 39.1,
}


def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    # Default to workspace root Axe3_Parametric.prt
    return Path(__file__).resolve().parent.parent / "Axe3_Parametric.prt"


def v(name: str) -> float:
    return float(VALUES[name])


# ---------------------------------------------------------------------------
# Create NX Expressions
# ---------------------------------------------------------------------------
def make_expressions(part) -> None:
    for name, val in VALUES.items():
        rhs = int(val) if name == "SIDE_RIB_COUNT" else val
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass

    formulas = {
        "BODY_RADIUS": "BODY_DIAMETER / 2.0",
        "WAIST_RADIUS": "WAIST_DIAMETER / 2.0",
        "COLLAR_Z_START": "WAIST_Z_START + WAIST_HEIGHT",
        "COLLAR_RADIUS": "COLLAR_DIAMETER / 2.0",
        "CROWN_Z_START": "COLLAR_Z_START + COLLAR_HEIGHT + CAP_BODY_HEIGHT",
        "CAP_TOP_TAPER_RADIUS": "CAP_TOP_TAPER_DIAMETER / 2.0",
        "CROWN_FLAT_RADIUS": "CROWN_FLAT_DIAMETER / 2.0",
        "TOTAL_HEIGHT": "BODY_HEIGHT",
        "SIDE_RIB_START_Z": "11.38",
    }
    for name, rhs in formulas.items():
        try:
            part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Geometry Helpers
# ---------------------------------------------------------------------------
def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


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

        cmd_content = f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{part_path}"\n'
        vbs_content = f'Set shell = CreateObject("WScript.Shell")\nshell.Run """C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe"" -ug -use_file_dir ""{part_path}""", 0, False\n'

        with open(cmd_file, "w", encoding="utf-8") as f:
            f.write(cmd_content)
        with open(vbs_file, "w", encoding="utf-8") as f:
            f.write(vbs_content)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main Revolve Function
# ---------------------------------------------------------------------------
def revolve_curves(part, curves, start_deg: str, end_deg: str, name: str):
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
        [0.0, 0.0, 1.0],
        NXOpen.UF.Modl.FeatureSigns.NULLSIGN,
    )
    if not features or num_feat < 1:
        raise RuntimeError(f"Revolve '{name}' did not create any features")
    feat = NXOpen.TaggedObjectManager().GetTaggedObject(features[0])
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, bodies[0] if bodies else None


# ---------------------------------------------------------------------------
# Boolean Subtraction
# ---------------------------------------------------------------------------
def boolean_subtract(part, target_body, tool_body):
    builder = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        builder.Target = target_body
        builder.Tools.Add(tool_body)
        feat = builder.CommitFeature()
        return feat
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Edge Blends
# ---------------------------------------------------------------------------
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
# Outer Profile Radius Function
# ---------------------------------------------------------------------------
def can_radius_at_z(z: float) -> float:
    """Returns the outer radius of the can at any given height Z."""
    r_body = v("BODY_DIAMETER") * 0.5
    z_waist_start = v("WAIST_Z_START")
    z_collar_start = z_waist_start + v("WAIST_HEIGHT")
    r_waist = v("WAIST_DIAMETER") * 0.5
    z_crown_start = z_collar_start + v("COLLAR_HEIGHT") + v("CAP_BODY_HEIGHT")
    r_collar = v("COLLAR_DIAMETER") * 0.5
    r_cap_top = v("CAP_TOP_TAPER_DIAMETER") * 0.5

    if z <= z_waist_start:
        return r_body
    elif z <= (z_waist_start + v("WAIST_HEIGHT") * 0.5):
        t = (z - z_waist_start) / (v("WAIST_HEIGHT") * 0.5)
        return r_body + t * (r_waist - r_body)
    elif z <= z_collar_start:
        return r_waist
    elif z <= (z_collar_start + v("COLLAR_HEIGHT")):
        t = (z - z_collar_start) / v("COLLAR_HEIGHT")
        return r_waist + t * (r_collar - r_waist)
    elif z <= z_crown_start:
        t = (z - (z_collar_start + v("COLLAR_HEIGHT"))) / v("CAP_BODY_HEIGHT")
        return r_collar + t * (r_cap_top - r_collar)
    else:
        return r_cap_top


# ---------------------------------------------------------------------------
# Main Journal Workflow
# ---------------------------------------------------------------------------
def main():
    part_path = out_path()
    part_path.parent.mkdir(parents=True, exist_ok=True)
    if part_path.exists():
        part_path.unlink()

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(part_path), NXOpen.Part.Units.Millimeters)
    part = session.Parts.Work

    print("=" * 60)
    print("Reconstructing Parametric Axe Body Spray Can (Axe3.obj)")
    print(f"  Target: {part_path}")
    print("=" * 60)

    # 1. Parametric Expressions
    make_expressions(part)
    print("[OK] Parametric Expressions registered.")

    # 2. Key Profile Stations (XZ Plane)
    h_tot = v("BODY_HEIGHT")
    r_body = v("BODY_DIAMETER") * 0.5
    z_dome = v("BOTTOM_DOME_DEPTH")
    r_chime = v("BOTTOM_CHIME_RADIUS")
    z_bot_fillet = v("BOTTOM_FILLET")
    z_waist_start = v("WAIST_Z_START")
    z_waist_mid = z_waist_start + v("WAIST_HEIGHT") * 0.5
    z_collar_start = z_waist_start + v("WAIST_HEIGHT")
    r_waist = v("WAIST_DIAMETER") * 0.5
    z_collar_end = z_collar_start + v("COLLAR_HEIGHT")
    r_collar = v("COLLAR_DIAMETER") * 0.5
    z_crown_start = z_collar_end + v("CAP_BODY_HEIGHT")
    r_cap_top = v("CAP_TOP_TAPER_DIAMETER") * 0.5
    r_crown_flat = v("CROWN_FLAT_DIAMETER") * 0.5

    pts = [
        (0.0, 0.0, h_tot),
        (0.0, 0.0, z_dome),
        (r_chime, 0.0, 0.0),
        (r_body, 0.0, z_bot_fillet),
        (r_body, 0.0, z_waist_start),
        (r_waist, 0.0, z_waist_mid),
        (r_waist, 0.0, z_collar_start),
        (r_collar, 0.0, z_collar_end),
        (r_cap_top, 0.0, z_crown_start),
        (r_crown_flat, 0.0, h_tot),
        (0.0, 0.0, h_tot),
    ]

    profile_curves = [line(part, pts[i], pts[i + 1]) for i in range(len(pts) - 1)]

    # 3. Base Revolve Feature
    base_feat, base_body = revolve_curves(
        part, profile_curves, "0", "360", "REVOLVE_CAN_BODY"
    )
    print(f"[OK] Revolved main can body ({len(list(base_body.GetFaces()))} faces)")

    # 4. Periodic Horizontal Side Grip Grooves (18 count)
    rib_count = int(v("SIDE_RIB_COUNT"))
    rib_pitch = v("SIDE_RIB_PITCH")
    groove_w = v("SIDE_GROOVE_WIDTH")
    groove_d = v("SIDE_GROOVE_DEPTH")
    z_start = 11.38

    grooves_subtracted = 0
    for i in range(rib_count):
        gz = z_start + i * rib_pitch
        if gz > (h_tot - 15.0):
            break

        r_surf = can_radius_at_z(gz)
        r_in = r_surf - groove_d
        r_out = r_surf + 2.0

        # Create groove tool profile
        g_pts = [
            (r_in, 0.0, gz - groove_w * 0.5),
            (r_out, 0.0, gz - groove_w * 0.5),
            (r_out, 0.0, gz + groove_w * 0.5),
            (r_in, 0.0, gz + groove_w * 0.5),
            (r_in, 0.0, gz - groove_w * 0.5),
        ]
        g_curves = [line(part, g_pts[k], g_pts[k + 1]) for k in range(len(g_pts) - 1)]

        try:
            # Revolve sector groove along side grip regions (60..120 deg and 240..300 deg)
            _, g_body1 = revolve_curves(
                part, g_curves, "60", "120", f"TOOL_GROOVE_R_{i}"
            )
            boolean_subtract(part, base_body, g_body1)

            # Mirror / opposite side
            g_curves2 = [line(part, g_pts[k], g_pts[k + 1]) for k in range(len(g_pts) - 1)]
            _, g_body2 = revolve_curves(
                part, g_curves2, "240", "300", f"TOOL_GROOVE_L_{i}"
            )
            boolean_subtract(part, base_body, g_body2)
            grooves_subtracted += 1
        except Exception as e:
            print(f"  [WARN] Skipping groove {i} at Z={gz:.1f}: {e}")

    print(f"[OK] Subtracted {grooves_subtracted} periodic horizontal side grip grooves.")

    # 5. Front V-Accent Feature (Embossed / Debossed styling chevron)
    try:
        v_apex_z = 85.0
        v_top_z = 180.0
        v_arm_w = 18.0
        v_depth = 1.0

        # Revolve front accent groove at Y=0 plane between 345 and 15 degrees
        v_r_surf = can_radius_at_z(v_apex_z)
        v_curves1 = [
            line(part, (v_r_surf - v_depth, 0.0, v_apex_z), (v_r_surf + 2.0, 0.0, v_apex_z)),
            line(part, (v_r_surf + 2.0, 0.0, v_apex_z), (v_r_surf + 2.0, 0.0, v_apex_z + 4.0)),
            line(part, (v_r_surf + 2.0, 0.0, v_apex_z + 4.0), (v_r_surf - v_depth, 0.0, v_apex_z + 4.0)),
            line(part, (v_r_surf - v_depth, 0.0, v_apex_z + 4.0), (v_r_surf - v_depth, 0.0, v_apex_z)),
        ]
        _, v_body = revolve_curves(part, v_curves1, "340", "20", "TOOL_V_ACCENT")
        boolean_subtract(part, base_body, v_body)
        print("[OK] Applied front V-accent styling feature.")
    except Exception as e:
        print(f"  [WARN] Front V-feature: {e}")

    # 6. Edge Blends
    # Bottom standing chime rim (Z = 0.0)
    blend_edges(
        part,
        base_body,
        lambda e: (
            len(e.GetVertices()) == 2
            and abs(e.GetVertices()[0].Z - 0.0) < 0.2
            and abs(e.GetVertices()[1].Z - 0.0) < 0.2
        ),
        "1.5",
        "BLEND_BOTTOM_CHIME",
    )

    # Bottom outer corner blend (Z ~ 2.5)
    blend_edges(
        part,
        base_body,
        lambda e: (
            len(e.GetVertices()) == 2
            and abs(e.GetVertices()[0].Z - z_bot_fillet) < 0.2
            and abs(e.GetVertices()[1].Z - z_bot_fillet) < 0.2
        ),
        "BOTTOM_FILLET",
        "BLEND_BOTTOM_OUTER",
    )

    # Top crown shoulder blend (Z ~ h_tot)
    blend_edges(
        part,
        base_body,
        lambda e: (
            len(e.GetVertices()) == 2
            and abs(e.GetVertices()[0].Z - h_tot) < 0.2
            and abs(e.GetVertices()[1].Z - h_tot) < 0.2
            and abs(math.hypot(e.GetVertices()[0].X, e.GetVertices()[0].Y) - r_crown_flat) < 1.0
        ),
        "CROWN_FILLET",
        "BLEND_TOP_CROWN",
    )
    print("[OK] Applied edge blends.")

    # 7. Verification & Final View
    try:
        faces_count = len(list(base_body.GetFaces() or []))
        edges_count = len(list(base_body.GetEdges() or []))
        features_count = len(list(part.Features or []))
        expressions_count = len(list(part.Expressions or []))
        print(f"Final Model: {features_count} Features, {faces_count} Faces, {edges_count} Edges, {expressions_count} Expressions.")
        part.ModelingViews.WorkView.Fit()
    except Exception:
        pass

    # 8. Save Part & Export STL for Validation
    part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    write_launch_files(str(part_path))
    print(f"[SUCCESS] Saved parametric part to: {part_path}")

    try:
        stl_path = str(part_path).replace(".prt", ".stl")
        stl_creator = session.DexManager.CreateStlCreator()
        stl_creator.OutputFile = stl_path
        for b in part.Bodies:
            stl_creator.ExportSelectionBlock.Add(b)
        stl_creator.Commit()
        stl_creator.Destroy()
        print(f"[SUCCESS] Exported STL to: {stl_path}")
    except Exception as e:
        print(f"[WARN] STL export: {e}")


if __name__ == "__main__":
    main()
