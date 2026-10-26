"""
parametric_helpers.py
=====================
Shared Siemens NX CAD helper library for zone-wise, fully parametric reconstructions.

Provides standardized, reusable utilities for:
- Chained expression population (preserving dependency order)
- Fixed datum planes (XZ and XY) for sketch-based modeling
- Sketch-in-place creation and driving dimensional constraints (HorizontalDim, VerticalDim)
- Associative Sketch Revolve and Sketch Extrude features
- Native parametric primitive builders (Cylinder, Cone, Block)
- Associative edge blending via topological face boundaries
- Robust boolean unite & subtract with feature naming
- Bounding box and geometric verification
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

def setup_nx_license() -> None:
    os.environ.setdefault("UGII_BASE_DIR", r"C:\Program Files\Siemens\NX2206")
    os.environ.setdefault("UGII_ROOT_DIR", r"C:\Program Files\Siemens\NX2206\NXBIN")
    curr_lic = os.environ.get("SPLM_LICENSE_SERVER", "")
    if "192.168.1.5" not in curr_lic:
        lic = None
        cfg_path = Path(__file__).resolve().parent.parent.parent / "config.json"
        if cfg_path.exists():
            try:
                import json
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    lic = cfg.get("license_server")
            except Exception:
                pass
        fallback = "28000@192.168.1.5;28000@SunFibo19;28000@192.168.1.29;28000@192.168.1.3;28000@SUN004"
        server_str = lic or fallback
        os.environ["SPLM_LICENSE_SERVER"] = server_str
        os.environ["SALT_LICENSE_SERVER"] = server_str
    path = os.environ.get("PATH", "")
    nxbin = r"C:\Program Files\Siemens\NX2206\NXBIN"
    ugii = r"C:\Program Files\Siemens\NX2206\UGII"
    if nxbin not in path:
        os.environ["PATH"] = f"{nxbin};{ugii};{path}"




def normalize_parametric_prt_path(output_prt_path: Union[Path, str]) -> Path:
    """Enforces exact PascalCase naming: <mesh>_Parametric.prt with no lowercase duplicates."""
    p = Path(output_prt_path)
    out_stem = p.stem
    for sfx in ["_parametric", "_Parametric"]:
        if out_stem.endswith(sfx):
            out_stem = out_stem[:-len(sfx)]
            break
    return p.with_name(f"{out_stem}_Parametric.prt")


def set_feature_name(feat, name: str) -> None:
    if feat is None:
        return
    try:
        feat.SetName(name)
    except Exception:
        pass


def populate_expressions(part, expressions: Union[List[Tuple[str, str]], Dict[str, Any]]) -> int:
    """
    Populates parametric expressions in the NX part.
    If a list of (name, formula) is given, creates them strictly in order
    to support chained formulas (e.g. ZONE2_START = ZONE1_START + ZONE1_HEIGHT).
    """
    created = 0
    items = expressions if isinstance(expressions, list) else list(expressions.items())
    for name, rhs in items:
        try:
            val_str = str(rhs).strip()
            # If already exists, update formula; otherwise create
            try:
                exp = part.Expressions.FindObject(name)
                exp.RightHandSide = val_str
            except Exception:
                part.Expressions.CreateExpression("Number", f"{name} = {val_str}")
            created += 1
        except Exception as e:
            print(f"  [WARN] Expression {name} = {rhs}: {e}")
    return created


def get_scalar_expression(part, name_or_val: str):
    """Returns an NXOpen Scalar from an expression name or numerical string."""
    import NXOpen
    name_str = str(name_or_val).strip()
    if name_str in ("0", "0.0", "0.000"):
        return part.Scalars.CreateScalar(0.0, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)
    try:
        exp = part.Expressions.FindObject(name_str)
        return part.Scalars.CreateScalarExpression(exp, NXOpen.Scalar.DimensionalityType.Length, NXOpen.SmartObject.UpdateOption.WithinModeling)
    except Exception:
        val = float(name_str)
        return part.Scalars.CreateScalar(val, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)


def create_scalar_point(part, x_expr: str, y_expr: str, z_expr: str = "0"):
    """Creates an associative NXOpen Point driven by scalar expressions."""
    import NXOpen
    sx = get_scalar_expression(part, x_expr)
    sy = get_scalar_expression(part, y_expr)
    sz = get_scalar_expression(part, z_expr)
    return part.Points.CreatePoint(sx, sy, sz, NXOpen.SmartObject.UpdateOption.WithinModeling)


def create_direction(part, base_pt, dir_vec: Tuple[float, float, float]):
    """Creates an associative NXOpen Direction."""
    import NXOpen
    pt = base_pt if hasattr(base_pt, "Coordinates") else NXOpen.Point3d(*base_pt)
    v = NXOpen.Vector3d(*dir_vec)
    return part.Directions.CreateDirection(pt, v, NXOpen.SmartObject.UpdateOption.WithinModeling)


# ---------------------------------------------------------------------------
# Native Sketch-Based Helpers (Approach 1: Expression-Driven Sketch Features)
# ---------------------------------------------------------------------------

def create_fixed_datum_plane_xz(part, origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)):
    """
    Creates a Fixed Datum Plane on XZ plane oriented such that:
    - Sketch +X is World +X (Radius axis)
    - Sketch +Y is World +Z (Height / Axial axis)
    - Sketch Normal is World -Y
    """
    import NXOpen
    mat = NXOpen.Matrix3x3()
    mat.Xx, mat.Xy, mat.Xz = 1.0, 0.0, 0.0
    mat.Yx, mat.Yy, mat.Yz = 0.0, 0.0, 1.0
    mat.Zx, mat.Zy, mat.Zz = 0.0, -1.0, 0.0
    pt = NXOpen.Point3d(float(origin[0]), float(origin[1]), float(origin[2]))
    return part.Datums.CreateFixedDatumPlane(pt, mat)


def create_fixed_datum_plane_xy(part, origin: Tuple[float, float, float] = (0.0, 0.0, 0.0)):
    """
    Creates a Fixed Datum Plane on XY plane oriented such that:
    - Sketch +X is World +X
    - Sketch +Y is World +Y
    - Sketch Normal is World +Z
    """
    import NXOpen
    mat = NXOpen.Matrix3x3()
    mat.Xx, mat.Xy, mat.Xz = 1.0, 0.0, 0.0
    mat.Yx, mat.Yy, mat.Yz = 0.0, 1.0, 0.0
    mat.Zx, mat.Zy, mat.Zz = 0.0, 0.0, 1.0
    pt = NXOpen.Point3d(float(origin[0]), float(origin[1]), float(origin[2]))
    return part.Datums.CreateFixedDatumPlane(pt, mat)


def create_offset_datum_plane(part, base_plane, offset_expr: str, name: str = ""):
    """Creates an associative Datum Plane offset from base_plane by offset_expr."""
    import NXOpen
    dpb = part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        c = dpb.CreateConstraint()
        c.Geometry = base_plane
        c.ConstraintType = NXOpen.DatumConstraint.Type.Distance
        dpb.GetPlane().SetExpression(str(offset_expr))
        feat = dpb.CommitFeature()
        if name:
            set_feature_name(feat, name)
        datum_plane = dpb.GetDatum()
        return datum_plane
    finally:
        dpb.Destroy()


def create_sketch_in_place(part, plane_or_face, name: str = "SKETCH"):
    """Creates a SketchInPlace on the given plane or planar face."""
    import NXOpen
    b = part.Sketches.CreateSketchInPlaceBuilder2(NXOpen.Sketch.Null)
    try:
        b.PlaneOrFace.Value = plane_or_face
        sk = b.Commit()
        if name:
            sk.SetName(name)
        return sk
    finally:
        b.Destroy()


def add_sketch_driving_dim_radius(sketch, part, l_axis, l_target, exp_name: str, u: float, v: float):
    """Adds a driving HorizontalDim constraint between the central axis line and a profile line."""
    import NXOpen
    dg1 = NXOpen.Sketch.DimensionGeometry()
    dg1.Geometry = l_axis
    dg1.AssocType = NXOpen.Sketch.AssocType.StartPoint

    dg2 = NXOpen.Sketch.DimensionGeometry()
    dg2.Geometry = l_target
    dg2.AssocType = NXOpen.Sketch.AssocType.StartPoint

    exp = part.Expressions.FindObject(exp_name)
    return sketch.CreateDimension(
        NXOpen.Sketch.ConstraintType.HorizontalDim,
        dg1,
        dg2,
        NXOpen.Point3d(float(u), float(v), 0.0),
        exp,
        NXOpen.Sketch.DimensionOption.CreateAsDriving
    )


def add_sketch_driving_dim_height(sketch, part, line, exp_name: str, u: float, v: float):
    """Adds a driving VerticalDim constraint on a single line segment from StartPoint to EndPoint."""
    import NXOpen
    dg1 = NXOpen.Sketch.DimensionGeometry()
    dg1.Geometry = line
    dg1.AssocType = NXOpen.Sketch.AssocType.StartPoint

    dg2 = NXOpen.Sketch.DimensionGeometry()
    dg2.Geometry = line
    dg2.AssocType = NXOpen.Sketch.AssocType.EndPoint

    exp = part.Expressions.FindObject(exp_name)
    return sketch.CreateDimension(
        NXOpen.Sketch.ConstraintType.VerticalDim,
        dg1,
        dg2,
        NXOpen.Point3d(float(u), float(v), 0.0),
        exp,
        NXOpen.Sketch.DimensionOption.CreateAsDriving
    )


def add_sketch_driving_dim_length(sketch, part, line, exp_name: str, u: float, v: float):
    """Adds a driving HorizontalDim constraint for the length of a horizontal line."""
    import NXOpen
    dg1 = NXOpen.Sketch.DimensionGeometry()
    dg1.Geometry = line
    dg1.AssocType = NXOpen.Sketch.AssocType.StartPoint

    dg2 = NXOpen.Sketch.DimensionGeometry()
    dg2.Geometry = line
    dg2.AssocType = NXOpen.Sketch.AssocType.EndPoint

    exp = part.Expressions.FindObject(exp_name)
    return sketch.CreateDimension(
        NXOpen.Sketch.ConstraintType.HorizontalDim,
        dg1,
        dg2,
        NXOpen.Point3d(float(u), float(v), 0.0),
        exp,
        NXOpen.Sketch.DimensionOption.CreateAsDriving
    )


def add_sketch_driving_dim_elevation(sketch, part, origin_point, target_curve_or_pt, exp_name: str, u: float, v: float):
    """Adds a driving VerticalDim constraint linking zone start elevation from sketch origin point."""
    import NXOpen
    dg1 = NXOpen.Sketch.DimensionGeometry()
    dg1.Geometry = origin_point
    dg1.AssocType = NXOpen.Sketch.AssocType.StartPoint

    dg2 = NXOpen.Sketch.DimensionGeometry()
    dg2.Geometry = target_curve_or_pt
    dg2.AssocType = NXOpen.Sketch.AssocType.StartPoint

    exp = part.Expressions.FindObject(exp_name)
    return sketch.CreateDimension(
        NXOpen.Sketch.ConstraintType.VerticalDim,
        dg1,
        dg2,
        NXOpen.Point3d(float(u), float(v), 0.0),
        exp,
        NXOpen.Sketch.DimensionOption.CreateAsDriving
    )


def create_sketch_revolve(part, sketch, axis_curve, start_deg_rhs: str = "0", end_deg_rhs: str = "360", name: str = "REVOLVE") -> Tuple[Any, Any]:
    """Creates a 360 degree Revolve feature from an associative sketch."""
    import NXOpen
    import NXOpen.GeometricUtilities
    rev_b = part.Features.CreateRevolveBuilder(NXOpen.Features.Feature.Null)
    try:
        rev_b.Tolerance = 0.01
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rule = part.ScRuleFactory.CreateRuleCurveFeature([sketch.Feature])
        sec.AddToSection([rule], axis_curve, NXOpen.NXObject.Null, NXOpen.NXObject.Null, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        rev_b.Section = sec

        axis_dir = part.Directions.CreateDirection(NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0), NXOpen.SmartObject.UpdateOption.WithinModeling)
        axis_pt = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
        rev_b.Axis = part.Axes.CreateAxis(axis_pt, axis_dir, NXOpen.SmartObject.UpdateOption.WithinModeling)
        rev_b.Limits.StartExtend.Value.RightHandSide = str(start_deg_rhs)
        rev_b.Limits.EndExtend.Value.RightHandSide = str(end_deg_rhs)
        try:
            rev_b.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        except Exception:
            pass
        feat = rev_b.CommitFeature()
        if name:
            set_feature_name(feat, name)
        body = feat.GetBodies()[0]
        return feat, body
    finally:
        rev_b.Destroy()


def create_sketch_extrude(part, sketch, start_expr: str = "0.0", end_expr: str = "10.0",
                          direction_vec: Tuple[float, float, float] = (0.0, 0.0, 1.0),
                          name: str = "EXTRUDE") -> Tuple[Any, Any]:
    """Creates an associative Extrude feature from a planar sketch."""
    import NXOpen
    import NXOpen.GeometricUtilities
    eb = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        eb.Tolerance = 0.01
        sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
        rule = part.ScRuleFactory.CreateRuleCurveFeature([sketch.Feature])
        geoms = list(sketch.GetAllGeometry())
        ref_curve = geoms[0] if geoms else NXOpen.NXObject.Null
        sec.AddToSection([rule], ref_curve, NXOpen.NXObject.Null, NXOpen.NXObject.Null, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        eb.Section = sec

        dir_obj = part.Directions.CreateDirection(NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(*direction_vec), NXOpen.SmartObject.UpdateOption.WithinModeling)
        eb.Direction = dir_obj
        eb.Limits.StartExtend.Value.RightHandSide = str(start_expr)
        eb.Limits.EndExtend.Value.RightHandSide   = str(end_expr)
        try:
            eb.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        except Exception:
            pass
        feat = eb.CommitFeature()
        if name:
            set_feature_name(feat, name)
        body = feat.GetBodies()[0]
        return feat, body
    finally:
        eb.Destroy()


# ---------------------------------------------------------------------------
# Direct Primitive Builders (Legacy / Standalone)
# ---------------------------------------------------------------------------

def create_cylinder(part, origin_point, diameter_rhs: str, height_rhs: str, direction, name: str = "CYLINDER") -> Tuple[Any, Any]:
    """Creates an associative Cylinder feature driven by expression RHS names."""
    import NXOpen
    import NXOpen.GeometricUtilities
    b = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        b.Diameter.RightHandSide = str(diameter_rhs)
        b.Height.RightHandSide   = str(height_rhs)
        b.Axis.Point = origin_point
        b.Axis.Direction = direction
        b.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        feat = b.CommitFeature()
        set_feature_name(feat, name)
        body = feat.GetBodies()[0]
        return feat, body
    finally:
        b.Destroy()


def create_cone(part, origin_point, base_dia_rhs: str, top_dia_rhs: str, height_rhs: str, direction, name: str = "CONE") -> Tuple[Any, Any]:
    """Creates an associative Cone feature driven by expression RHS names."""
    import NXOpen
    import NXOpen.GeometricUtilities
    cb = part.Features.CreateConeBuilder(NXOpen.Features.Cone.Null)
    try:
        cb.Type = NXOpen.Features.ConeBuilder.Types.DiametersAndHeight
        cb.BaseDiameter.RightHandSide = str(base_dia_rhs)
        cb.TopDiameter.RightHandSide  = str(top_dia_rhs)
        cb.Height.RightHandSide       = str(height_rhs)
        cb.Axis.Point = origin_point
        cb.Axis.Direction = direction
        cb.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        feat = cb.CommitFeature()
        set_feature_name(feat, name)
        body = feat.GetBodies()[0]
        return feat, body
    finally:
        cb.Destroy()


def create_block(part, origin_point, length_rhs: str, width_rhs: str, height_rhs: str, name: str = "BLOCK") -> Tuple[Any, Any]:
    """Creates an associative Block feature driven by expression RHS names."""
    import NXOpen
    import NXOpen.GeometricUtilities
    bb = part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Block.Null)
    try:
        bb.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        bb.SetOriginAndLengths(origin_point, str(length_rhs), str(width_rhs), str(height_rhs))
        bb.BooleanOption.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        feat = bb.CommitFeature()
        set_feature_name(feat, name)
        body = feat.GetBodies()[0]
        return feat, body
    finally:
        bb.Destroy()


def boolean_unite(part, target_body, tool_body, name: str = "UNITE") -> Any:
    """Unites tool_body into target_body."""
    import NXOpen
    u = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        u.Operation = NXOpen.Features.Feature.BooleanType.Unite
        u.RetainTarget = False
        u.RetainTool = False
        u.Target = target_body
        u.Tools.Add(tool_body)
        feat = u.CommitFeature()
        if name:
            set_feature_name(feat, name)
        return feat
    finally:
        u.Destroy()


def boolean_subtract(part, target_body, tool_body, name: str = "SUBTRACT") -> Any:
    """Subtracts tool_body from target_body."""
    import NXOpen
    s = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        s.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        s.RetainTarget = False
        s.RetainTool = False
        s.Target = target_body
        s.Tools.Add(tool_body)
        feat = s.CommitFeature()
        if name:
            set_feature_name(feat, name)
        return feat
    finally:
        s.Destroy()


def create_associative_blend_by_face(part, face, radius_rhs: str, name: str = "EDGE_BLEND") -> Optional[Any]:
    """
    Creates an associative edge blend by collecting outer edges of the given face.
    Uses SelectionIntentRule OuterEdgesOfFaces (NEVER CreateRuleEdgeDumb).
    Cleans up undo marks if commit fails to prevent dirty session state.
    """
    import NXOpen
    session = NXOpen.Session.GetSession()
    candidates = [str(radius_rhs), "1.0", "0.8", "0.5"]

    for r_str in candidates:
        mark_id = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "BlendAttempt")
        bb = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = part.ScCollectors.CreateCollector()
            rule = part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([face])
            collector.ReplaceRules([rule], False)
            bb.AddChainset(collector, r_str)
            feat = bb.CommitFeature()
            if name:
                set_feature_name(feat, name)
            session.DeleteUndoMark(mark_id, "BlendAttempt")
            return feat
        except Exception:
            try:
                session.UndoToMark(mark_id, "BlendAttempt")
                session.DeleteUndoMark(mark_id, "BlendAttempt")
            except Exception:
                pass
        finally:
            try:
                bb.Destroy()
            except Exception:
                pass
    return None


def compute_body_bounds(body) -> Optional[Tuple[float, float, float, float, float, float]]:
    """
    Computes (min_x, min_y, min_z, max_x, max_y, max_z) of a solid body.
    Uses exact CAD geometry bounding box (AskBoundingBoxExact) when available,
    with robust fallback to edge vertices.
    """
    try:
        import NXOpen
        import NXOpen.UF
        uf = NXOpen.UF.UFSession.GetUFSession()
        mod = getattr(uf, "ModlGeneral", None) or getattr(uf, "Modl", None)
        if mod and hasattr(mod, "AskBoundingBoxExact"):
            min_pt, _, box_sizes = mod.AskBoundingBoxExact(body.Tag, 0)
            return (
                float(min_pt[0]), float(min_pt[1]), float(min_pt[2]),
                float(min_pt[0] + box_sizes[0]), float(min_pt[1] + box_sizes[1]), float(min_pt[2] + box_sizes[2])
            )
        elif mod and hasattr(mod, "AskBoundingBox"):
            box = mod.AskBoundingBox(body.Tag)
            if box and len(box) >= 6:
                return (float(box[0]), float(box[1]), float(box[2]), float(box[3]), float(box[4]), float(box[5]))
    except Exception:
        pass

    edges = body.GetEdges()
    xs, ys, zs = [], [], []
    for e in edges:
        try:
            v1, v2 = e.GetVertices()
            xs.extend([v1.X, v2.X])
            ys.extend([v1.Y, v2.Y])
            zs.extend([v1.Z, v2.Z])
        except Exception:
            pass
    if not xs:
        return None
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


# Relative radius difference below which a revolve zone is treated as a straight
# cylinder and driven by ONE radius expression (no redundant TOP_R orphan).
CYLINDER_ZONE_REL_TOL = 0.005


def is_cylindrical_zone(r_start: float, r_end: float) -> bool:
    return abs(r_start - r_end) <= CYLINDER_ZONE_REL_TOL * max(abs(r_start), abs(r_end), 1e-9)
