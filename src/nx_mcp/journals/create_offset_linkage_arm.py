"""
NX Journal: create_offset_linkage_arm.py
=========================================
Creates a fully parametric offset linkage arm in Siemens NX.

Part Description
----------------
Two identical rounded-end arms connected by a vertical cylindrical spacer.
The upper arm is rotated 180° relative to the lower arm.

Geometry Layout
---------------
Coordinate origin = center of the bottom linkage arm cylinder axis at Z=0.

Lower Arm:
  - Profile on XY plane (Z=0)
  - Left arc center at (-HOLE_OFFSET, 0, 0) = (-12, 0, 0)
  - Right arc center at (ARM_SPAN - HOLE_OFFSET, 0, 0) = (54, 0, 0)
    where ARM_SPAN = ARM_LENGTH - 2*END_RADIUS = 90 - 24 = 66
  - Left hole center at (0, 0, ARM_THICK) = origin at top face
  - Right hole center at (ARM_SPAN - 2*HOLE_OFFSET, 0, ARM_THICK) = (42, 0, 8)
  - Extruded ARM_THICK = 8mm in +Z

Spacer Cylinder:
  - Axis at (0, 0) — concentric with lower arm left hole
  - Diameter = CYLINDER_DIA = 22mm
  - Spans from Z=ARM_THICK to Z=ARM_THICK+CYLINDER_HEIGHT = 8 to 63
  - United with lower arm

Upper Arm:
  - Rotated 180° — right end at origin, extends in -X direction
  - Right arc center at (HOLE_OFFSET, 0, Z_CYL_TOP) = (12, 0, 63)
  - Left arc center at (HOLE_OFFSET - ARM_SPAN, 0, Z_CYL_TOP) = (-54, 0, 63)
  - Right hole center at (0, 0, Z_UPPER_TOP) = origin at upper top face
  - Left hole center at (-(ARM_SPAN - 2*HOLE_OFFSET), 0, Z_UPPER_TOP) = (-42, 0, 71)
  - Extruded ARM_THICK = 8mm in +Z

Named Parameters:
  ARM_LENGTH=90, ARM_WIDTH=24, ARM_THICK=8, END_RADIUS=12,
  HOLE_DIA=10, HOLE_OFFSET=12, CYLINDER_DIA=22, CYLINDER_HEIGHT=55,
  BLEND_RADIUS=2, CHAMFER_OFFSET=0.5
"""

import sys
import os
import math

import NXOpen
import NXOpen.UF

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
PARAMS = {
    "ARM_LENGTH":      90.0,
    "ARM_WIDTH":       24.0,
    "ARM_THICK":       8.0,
    "END_RADIUS":      12.0,
    "HOLE_DIA":        10.0,
    "HOLE_OFFSET":     12.0,
    "CYLINDER_DIA":    22.0,
    "CYLINDER_HEIGHT": 55.0,
    "BLEND_RADIUS":    2.0,
    "CHAMFER_OFFSET":  0.5,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def warn(msg):
    sys.stderr.write("[WARN] " + msg + "\n")
    sys.stderr.flush()


def create_nx_expression(work_part, name, value):
    """Create or update a named NX Expression. Returns the expression name."""
    try:
        try:
            expr = work_part.Expressions.FindObject(name)
            expr.RightHandSide = str(float(value))
            return name
        except Exception:
            pass
        work_part.Expressions.CreateExpression("Number", f"{name} = {float(value)}")
        return name
    except Exception as e:
        warn(f"Expression '{name}' creation failed: {e}. Using literal value.")
        return str(float(value))


def get_expr_value(work_part, name):
    """Get the numeric value of a named expression."""
    try:
        expr = work_part.Expressions.FindObject(name)
        return float(expr.Value)
    except Exception:
        return float(name)


def get_last_body(work_part):
    """Return the most recently created solid body."""
    bodies = [b for b in work_part.Bodies]
    if not bodies:
        raise RuntimeError("No bodies found in work part")
    return bodies[-1]


def create_direction(work_part, vec):
    """Create a Direction smart object from a Vector3d."""
    return work_part.Directions.CreateDirection(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        vec,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )


# ---------------------------------------------------------------------------
# Profile Drawing
# ---------------------------------------------------------------------------

def draw_rounded_arm_profile(work_part, left_arc_cx, cy, z, arm_length, arm_width, end_radius):
    """
    Draw a closed rounded-rectangle profile on plane Z.

    Profile:
      Left arc:   center=(left_arc_cx, cy), R=end_radius, 90°→270°
      Bottom:     (left_arc_cx, cy-half_w) → (right_arc_cx, cy-half_w)
      Right arc:  center=(right_arc_cx, cy), R=end_radius, 270°→90°
      Top:        (right_arc_cx, cy+half_w) → (left_arc_cx, cy+half_w)

    Returns list of NXOpen curve objects.
    """
    right_arc_cx = left_arc_cx + (arm_length - 2.0 * end_radius)
    half_w = arm_width / 2.0
    normal = NXOpen.Vector3d(0.0, 0.0, 1.0)

    curves = []

    # Left arc: 90° → 270° (counter-clockwise, so left-facing)
    x_dir = NXOpen.Vector3d(1.0, 0.0, 0.0)
    y_dir = NXOpen.Vector3d(0.0, 1.0, 0.0)
    curves.append(work_part.Curves.CreateArc(
        NXOpen.Point3d(left_arc_cx, cy, z), x_dir, y_dir, end_radius,
        math.radians(90.0), math.radians(270.0)
    ))

    # Bottom line
    curves.append(work_part.Curves.CreateLine(
        NXOpen.Point3d(left_arc_cx, cy - half_w, z),
        NXOpen.Point3d(right_arc_cx, cy - half_w, z)
    ))

    # Right arc: 270° → 90° (counter-clockwise, so right-facing)
    x_dir = NXOpen.Vector3d(1.0, 0.0, 0.0)
    y_dir = NXOpen.Vector3d(0.0, 1.0, 0.0)
    curves.append(work_part.Curves.CreateArc(
        NXOpen.Point3d(right_arc_cx, cy, z), x_dir, y_dir, end_radius,
        math.radians(270.0), math.radians(90.0)
    ))

    # Top line
    curves.append(work_part.Curves.CreateLine(
        NXOpen.Point3d(right_arc_cx, cy + half_w, z),
        NXOpen.Point3d(left_arc_cx, cy + half_w, z)
    ))

    return curves


def draw_upper_arm_profile(work_part, right_arc_cx, cy, z, arm_length, arm_width, end_radius):
    """
    Draw upper arm profile (180° rotated from lower arm) on plane Z.

    The right arc center is at (right_arc_cx, cy).
    The arm extends to the LEFT (toward negative X).

    Profile:
      Right arc:  center=(right_arc_cx, cy), R=end_radius, 270°→90°
      Top:        (right_arc_cx, cy+half_w) → (left_arc_cx, cy+half_w)
      Left arc:   center=(left_arc_cx, cy), R=end_radius, 90°→270°
      Bottom:     (left_arc_cx, cy-half_w) → (right_arc_cx, cy-half_w)
    """
    left_arc_cx = right_arc_cx - (arm_length - 2.0 * end_radius)
    half_w = arm_width / 2.0
    normal = NXOpen.Vector3d(0.0, 0.0, 1.0)

    curves = []

    # Right arc: 270° → 90°
    x_dir = NXOpen.Vector3d(1.0, 0.0, 0.0)
    y_dir = NXOpen.Vector3d(0.0, 1.0, 0.0)
    curves.append(work_part.Curves.CreateArc(
        NXOpen.Point3d(right_arc_cx, cy, z), x_dir, y_dir, end_radius,
        math.radians(270.0), math.radians(90.0)
    ))

    # Top line: right to left
    curves.append(work_part.Curves.CreateLine(
        NXOpen.Point3d(right_arc_cx, cy + half_w, z),
        NXOpen.Point3d(left_arc_cx, cy + half_w, z)
    ))

    # Left arc: 90° → 270°
    x_dir = NXOpen.Vector3d(1.0, 0.0, 0.0)
    y_dir = NXOpen.Vector3d(0.0, 1.0, 0.0)
    curves.append(work_part.Curves.CreateArc(
        NXOpen.Point3d(left_arc_cx, cy, z), x_dir, y_dir, end_radius,
        math.radians(90.0), math.radians(270.0)
    ))

    # Bottom line: left to right
    curves.append(work_part.Curves.CreateLine(
        NXOpen.Point3d(left_arc_cx, cy - half_w, z),
        NXOpen.Point3d(right_arc_cx, cy - half_w, z)
    ))

    return curves


# ---------------------------------------------------------------------------
# Extrude
# ---------------------------------------------------------------------------

def extrude_profile(work_part, curves, start_str, end_str,
                    boolean_type=None, boolean_target=None):
    """
    Extrude a set of curves in +Z from start_str to end_str (expression strings).
    Returns the committed feature.
    """
    builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rules = [work_part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
        section.AddToSection(
            rules, curves[0],
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False,
        )
        builder.Section = section
        builder.Direction = create_direction(work_part, NXOpen.Vector3d(0.0, 0.0, 1.0))
        builder.Limits.StartExtend.Value.RightHandSide = str(start_str)
        builder.Limits.EndExtend.Value.RightHandSide = str(end_str)

        if boolean_type is not None:
            target = boolean_target if boolean_target is not None else NXOpen.Body.Null
            builder.BooleanOperation.SetBooleanOperationAndBody(boolean_type, target)
        else:
            builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create

        return builder.CommitFeature()
    finally:
        builder.Destroy()


def extrude_circle_z(work_part, cx, cy, radius, start_str, end_str,
                     boolean_type=None, boolean_target=None):
    """
    Extrude a circle (at Z=0 in XY plane) from start_str to end_str in +Z.
    Returns the committed feature.
    """
    center = NXOpen.Point3d(cx, cy, 0.0)
    x_dir = NXOpen.Vector3d(1.0, 0.0, 0.0)
    y_dir = NXOpen.Vector3d(0.0, 1.0, 0.0)
    circle = work_part.Curves.CreateArc(center, x_dir, y_dir, radius, 0.0, 2.0 * math.pi)

    builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rule = work_part.ScRuleFactory.CreateRuleCurveDumb([circle])
        section.AddToSection(
            [rule], circle,
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False,
        )
        builder.Section = section
        builder.Direction = create_direction(work_part, NXOpen.Vector3d(0.0, 0.0, 1.0))
        builder.Limits.StartExtend.Value.RightHandSide = str(start_str)
        builder.Limits.EndExtend.Value.RightHandSide = str(end_str)

        if boolean_type is not None:
            target = boolean_target if boolean_target is not None else NXOpen.Body.Null
            builder.BooleanOperation.SetBooleanOperationAndBody(boolean_type, target)
        else:
            builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create

        return builder.CommitFeature()
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Hole (cylinder subtract)
# ---------------------------------------------------------------------------

def subtract_hole(work_part, target_body, cx, cy, z_top, diameter, depth):
    """
    Create a through-hole by drawing a circle at (cx, cy, z_top) and extruding
    ARM_THICK in -Z, then boolean subtracting from target_body.

    diameter, depth: float values
    Returns the feature or None on failure.
    """
    radius = diameter / 2.0
    center = NXOpen.Point3d(cx, cy, z_top)
    x_dir = NXOpen.Vector3d(1.0, 0.0, 0.0)
    y_dir = NXOpen.Vector3d(0.0, 1.0, 0.0)
    circle = work_part.Curves.CreateArc(center, x_dir, y_dir, radius, 0.0, 2.0 * math.pi)

    builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rule = work_part.ScRuleFactory.CreateRuleCurveDumb([circle])
        section.AddToSection(
            [rule], circle,
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False,
        )
        builder.Section = section
        builder.Direction = create_direction(work_part, NXOpen.Vector3d(0.0, 0.0, -1.0))
        builder.Limits.StartExtend.Value.RightHandSide = "0"
        builder.Limits.EndExtend.Value.RightHandSide = str(float(depth))

        builder.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract,
            target_body
        )

        return builder.CommitFeature()
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Finishing operations
# ---------------------------------------------------------------------------

def apply_edge_blend(work_part, body, radius, uf_session, max_z):
    """Fillet all edges of the body with the given radius, except the top edges."""
    try:
        all_edges = list(body.GetEdges() or [])
        edges = []
        for edge in all_edges:
            try:
                pt1, pt2, _ = uf_session.Modeling.AskEdgeVerts(edge.Tag)
                z1 = float(pt1[2]) if hasattr(pt1, '__getitem__') else float(pt1.Z)
                z2 = float(pt2[2]) if hasattr(pt2, '__getitem__') else float(pt2.Z)
                if abs(z1 - max_z) < 0.05 and abs(z2 - max_z) < 0.05:
                    continue
                edges.append(edge)
            except Exception:
                edges.append(edge)

        if not edges:
            return None

        builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = work_part.ScCollectors.CreateCollector()
            rule = work_part.ScRuleFactory.CreateRuleEdgeMultipleSeedTangent(edges, 0.5, True)
            collector.ReplaceRules([rule], False)

            builder.Tolerance = 0.01
            builder.RemoveSelfIntersection = True
            builder.RollOverSmoothEdge = True
            builder.RollOntoEdge = True
            builder.MoveSharpEdge = True
            builder.OverlapOption = NXOpen.Features.EdgeBlendBuilder.Overlap.AnyConvexityRollOver
            builder.BlendOrder = NXOpen.Features.EdgeBlendBuilder.OrderOfBlending.ConvexFirst
            builder.SetbackOption = NXOpen.Features.EdgeBlendBuilder.Setback.SeparateFromCorner
            builder.AddChainset(collector, str(float(radius)))
            return builder.CommitFeature()
        finally:
            builder.Destroy()
    except Exception as e:
        warn(f"Edge blend failed: {e}")
        return None


def _get_top_edges(body, uf_session, max_z):
    """Return edges at the maximum Z of the body."""
    top_edges = []
    for edge in list(body.GetEdges() or []):
        try:
            pt1, pt2, _ = uf_session.Modeling.AskEdgeVerts(edge.Tag)
            z1 = float(pt1[2]) if hasattr(pt1, '__getitem__') else float(pt1.Z)
            z2 = float(pt2[2]) if hasattr(pt2, '__getitem__') else float(pt2.Z)
            if abs(z1 - max_z) < 0.05 and abs(z2 - max_z) < 0.05:
                top_edges.append(edge)
        except Exception:
            continue
    return top_edges


def apply_chamfer(work_part, body, offset, uf_session, max_z):
    """Chamfer the top edges of the body."""
    try:
        top_edges = _get_top_edges(body, uf_session, max_z)
        if not top_edges:
            warn("No top edges found for chamfer")
            return None

        builder = work_part.Features.CreateChamferBuilder(NXOpen.Features.Feature.Null)
        try:
            builder.Option = NXOpen.Features.ChamferBuilder.ChamferOption.OffsetAndAngle
            builder.Method = NXOpen.Features.ChamferBuilder.OffsetMethod.EdgesAlongFaces
            builder.FirstOffset = str(float(offset))
            builder.SecondOffset = str(float(offset))
            builder.Angle = "45"
            builder.Tolerance = 0.01

            rules = [
                work_part.ScRuleFactory.CreateRuleEdgeTangent(
                    e, NXOpen.Edge.Null, False, 0.5, False
                )
                for e in top_edges
            ]
            collector = work_part.ScCollectors.CreateCollector()
            collector.ReplaceRules(rules, False)
            builder.SmartCollector = collector
            return builder.CommitFeature()
        finally:
            builder.Destroy()
    except Exception as e:
        warn(f"Chamfer failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def get_output_path():
    """Parse output path from command-line args passed via run_journal.exe."""
    default = "C:/Users/HP/nx-mcp/offset_linkage_arm.prt"
    for arg in sys.argv[1:]:
        for prefix in ("output_path=", "--output_path=", "-o="):
            if arg.startswith(prefix):
                return arg.split("=", 1)[1].strip()
    return default


def main():
    output_path = get_output_path()
    output_path = output_path.replace("\\", "/")
    if not output_path.endswith(".prt"):
        output_path += ".prt"

    # ---- Shortcuts to parameters ----
    p = PARAMS
    ARM_L = p["ARM_LENGTH"]        # 90.0
    ARM_W = p["ARM_WIDTH"]         # 24.0
    ARM_T = p["ARM_THICK"]         # 8.0
    END_R = p["END_RADIUS"]        # 12.0
    HOLE_D = p["HOLE_DIA"]         # 10.0
    HOLE_O = p["HOLE_OFFSET"]      # 12.0
    CYL_D = p["CYLINDER_DIA"]      # 22.0
    CYL_H = p["CYLINDER_HEIGHT"]   # 55.0
    BLEND_R = p["BLEND_RADIUS"]    # 2.0
    CHAM_O = p["CHAMFER_OFFSET"]   # 0.5

    ARM_SPAN = ARM_L - 2.0 * END_R    # 66.0 (center-to-center of arc centers)
    CYL_R = CYL_D / 2.0               # 11.0

    # Geometry layout (all coordinates in mm):
    #
    # Lower arm arc centers:
    #   LEFT  at (-HOLE_O, 0)         = (-12, 0)   → left hole at (0,0) = origin ✓
    #   RIGHT at (-HOLE_O + ARM_SPAN, 0) = (54, 0) → right hole at (42, 0)
    #
    # Lower arm holes (drilled from Z=ARM_T, direction -Z):
    #   LEFT  (0, 0, ARM_T)
    #   RIGHT (ARM_SPAN - 2*HOLE_O, 0, ARM_T) = (42, 0, ARM_T)
    #
    # Cylinder: center (0,0), radius CYL_R, from Z=ARM_T to Z=ARM_T+CYL_H
    #
    # Upper arm arc centers (at Z = ARM_T + CYL_H):
    #   RIGHT at (HOLE_O, 0)          = (12, 0)    → right hole at (0,0) = origin ✓
    #   LEFT  at (HOLE_O - ARM_SPAN, 0) = (-54, 0) → left hole at (-42, 0)
    #
    # Upper arm holes (drilled from Z=ARM_T+CYL_H+ARM_T, direction -Z):
    #   RIGHT (0, 0, Z_UPPER_TOP)
    #   LEFT  (-(ARM_SPAN - 2*HOLE_O), 0, Z_UPPER_TOP) = (-42, 0, Z_UPPER_TOP)

    LOWER_LEFT_ARC_X  = -HOLE_O                      # -12.0
    LOWER_LEFT_HOLE_X = 0.0                            # at origin
    LOWER_RIGHT_HOLE_X = ARM_SPAN - 2.0 * HOLE_O      # 42.0

    UPPER_RIGHT_ARC_X  = HOLE_O                       # 12.0
    UPPER_RIGHT_HOLE_X = 0.0                           # at origin
    UPPER_LEFT_HOLE_X  = -(ARM_SPAN - 2.0 * HOLE_O)   # -42.0

    Z_LOWER_TOP = ARM_T                               # 8.0
    Z_CYL_TOP   = ARM_T + CYL_H                      # 63.0
    Z_UPPER_TOP = ARM_T + CYL_H + ARM_T              # 71.0

    # ---- NX Session ----
    session = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()

    # Create new part
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
            log("Deleted existing file: " + output_path)
        except Exception as e:
            warn(f"Failed to delete existing file {output_path}: {e}")
    session.Parts.NewDisplay(output_path, NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    if work_part is None:
        raise RuntimeError("Failed to create work part")

    log("Part created: " + output_path)

    # ---- Create NX Expressions ----
    exprs = {}
    for name, val in PARAMS.items():
        exprs[name] = create_nx_expression(work_part, name, val)
    log("Expressions created.")

    # ========== F3: Lower Arm Profile ==========
    log("Drawing lower arm profile...")
    lower_curves = draw_rounded_arm_profile(
        work_part,
        left_arc_cx=LOWER_LEFT_ARC_X,  # -12.0
        cy=0.0,
        z=0.0,
        arm_length=ARM_L,
        arm_width=ARM_W,
        end_radius=END_R,
    )

    # ========== F4: Extrude Lower Arm ==========
    log("Extruding lower arm...")
    lower_feature = extrude_profile(
        work_part, lower_curves,
        start_str="0",
        end_str=exprs["ARM_THICK"],  # "ARM_THICK"
        boolean_type=None,
    )
    log(f"Lower arm extruded.")
    main_body = get_last_body(work_part)

    # ========== F7+F8: Cylinder circle + extrude (UNITE) ==========
    log("Creating cylinder spacer...")
    cyl_feature = extrude_circle_z(
        work_part,
        cx=0.0, cy=0.0,
        radius=CYL_R,
        start_str=exprs["ARM_THICK"],               # "ARM_THICK" = 8
        end_str=str(ARM_T + CYL_H),                 # 63.0
        boolean_type=NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        boolean_target=main_body,
    )
    log("Cylinder created and united.")
    main_body = get_last_body(work_part)

    # ========== F10+F12: Upper Arm Profile + Extrude (UNITE) ==========
    log("Drawing upper arm profile (180° rotated)...")
    upper_curves = draw_upper_arm_profile(
        work_part,
        right_arc_cx=UPPER_RIGHT_ARC_X,  # 12.0
        cy=0.0,
        z=Z_CYL_TOP,                     # 63.0
        arm_length=ARM_L,
        arm_width=ARM_W,
        end_radius=END_R,
    )

    log("Extruding upper arm...")
    upper_feature = extrude_profile(
        work_part, upper_curves,
        start_str="0",
        end_str=exprs["ARM_THICK"],
        boolean_type=NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        boolean_target=main_body,
    )
    log("Upper arm extruded and united.")
    main_body = get_last_body(work_part)

    # ========== F5: Lower Arm Left Hole ==========
    log("Adding lower arm left hole...")
    subtract_hole(
        work_part, main_body,
        cx=LOWER_LEFT_HOLE_X,   # 0.0
        cy=0.0,
        z_top=Z_LOWER_TOP,      # 8.0
        diameter=HOLE_D,
        depth=ARM_T,
    )
    log("Lower arm left hole done.")
    main_body = get_last_body(work_part)

    # ========== Lower Arm Right Hole ==========
    log("Adding lower arm right hole...")
    subtract_hole(
        work_part, main_body,
        cx=LOWER_RIGHT_HOLE_X,  # 42.0
        cy=0.0,
        z_top=Z_LOWER_TOP,
        diameter=HOLE_D,
        depth=ARM_T,
    )
    log("Lower arm right hole done.")
    main_body = get_last_body(work_part)

    # ========== F13: Upper Arm Right Hole (at cylinder axis) ==========
    log("Adding upper arm right hole...")
    subtract_hole(
        work_part, main_body,
        cx=UPPER_RIGHT_HOLE_X,  # 0.0
        cy=0.0,
        z_top=Z_UPPER_TOP,      # 71.0
        diameter=HOLE_D,
        depth=ARM_T,
    )
    log("Upper arm right hole done.")
    main_body = get_last_body(work_part)

    # ========== Upper Arm Left Hole ==========
    log("Adding upper arm left hole...")
    subtract_hole(
        work_part, main_body,
        cx=UPPER_LEFT_HOLE_X,   # -42.0
        cy=0.0,
        z_top=Z_UPPER_TOP,
        diameter=HOLE_D,
        depth=ARM_T,
    )
    log("Upper arm left hole done.")
    main_body = get_last_body(work_part)

    # ========== F14: Edge Blend ==========
    log("Applying edge blend...")
    max_z = 2.0 * ARM_T + CYL_H
    apply_edge_blend(work_part, main_body, BLEND_R, uf, max_z)
    log("Edge blend done.")
    main_body = get_last_body(work_part)

    # ========== F15: Chamfer ==========
    log("Applying chamfer to top edges...")
    apply_chamfer(work_part, main_body, CHAM_O, uf, max_z)
    log("Chamfer done.")

    # ========== F16: Fit view + Save ==========
    try:
        work_part.ModelingViews.WorkView.Fit()
    except Exception:
        pass

    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )

    # Update tracking files for auto-open
    try:
        root = "C:\\Users\\HP\\nx-mcp"
        abs_path = os.path.abspath(output_path.replace("/", "\\"))
        with open(os.path.join(root, "latest_nx_result.txt"), "w", encoding="utf-8") as f:
            f.write(abs_path)
        with open(os.path.join(root, "open_current_nx_result.cmd"), "w", encoding="utf-8") as f:
            f.write(
                f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe"'
                f' -ug -use_file_dir "{abs_path}"\n'
            )
        vbs_path = os.path.join(root, "open_latest_nx_result.vbs")
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(
                f'Set shell = CreateObject("WScript.Shell")\n'
                f'shell.Run """C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe"" -ug'
                f' -use_file_dir ""{abs_path}""\", 0, False\n'
            )
    except Exception:
        pass

    log("")
    log("=" * 60)
    log("SUCCESS: offset_linkage_arm.prt created")
    log(f"  Output:          {output_path}")
    log(f"  ARM_LENGTH:      {ARM_L} mm")
    log(f"  ARM_WIDTH:       {ARM_W} mm")
    log(f"  ARM_THICK:       {ARM_T} mm")
    log(f"  END_RADIUS:      {END_R} mm")
    log(f"  HOLE_DIA:        {HOLE_D} mm")
    log(f"  HOLE_OFFSET:     {HOLE_O} mm")
    log(f"  CYLINDER_DIA:    {CYL_D} mm")
    log(f"  CYLINDER_HEIGHT: {CYL_H} mm")
    log(f"  BLEND_RADIUS:    {BLEND_R} mm")
    log(f"  CHAMFER_OFFSET:  {CHAM_O} mm")
    log(f"  Lower arm:       left arc=({LOWER_LEFT_ARC_X},0), holes at ({LOWER_LEFT_HOLE_X},0) & ({LOWER_RIGHT_HOLE_X},0)")
    log(f"  Cylinder:        at (0,0), Z={ARM_T}..{ARM_T+CYL_H}")
    log(f"  Upper arm:       right arc=({UPPER_RIGHT_ARC_X},0), holes at ({UPPER_RIGHT_HOLE_X},0) & ({UPPER_LEFT_HOLE_X},0)")
    log(f"  Total height:    {Z_UPPER_TOP} mm")
    log("=" * 60)


if __name__ == "__main__":
    main()
