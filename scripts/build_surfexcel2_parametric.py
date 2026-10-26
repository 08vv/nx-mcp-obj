"""
build_surfexcel2_parametric.py
==============================
Zone-wise parametric Siemens NX reconstruction of obj/Surfexcel2_reduced.obj
(Surf Excel detergent jug: asymmetric body, elliptical through-handle opening,
recessed front/back label field with raised border, narrow neck, flared cap).

OBJ units are normalised (height = 2.0); scale S = 110 -> 220 mm tall part.
Axes: OBJ X/Y/Z map 1:1 to NX X/Y/Z (Y = bottle axis, Z = thickness).

Feature tree
  ZONE1_LOWER_BODY   Extrude (Y-limits chained)    y -110 .. 33
  ZONE2_SHOULDER     Extrude (chained)             y  33 .. 68.2
  ZONE3_NECK         Extrude (chained)             y 68.2 .. 83.6
  ZONE4_CAP          Extrude (chained)             y 83.6 .. 110
  UNITE_*            Boolean unite zones
  SILHOUETTE_LEFT/RIGHT  Extrude-subtract of the OBJ outline (asymmetric taper)
  HANDLE_OPENING     Elliptical through-cut (tilted)
  RECESS_FRONT/BACK  Extrude-subtract label field (floor chained to expression)
  Blends: CAP_TOP, BASE, FACE perimeter, HANDLE RIM, RECESS FLOOR (all associative)

Usage: run_journal.exe scripts/build_surfexcel2_parametric.py [output_prt]
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

if "SPLM_LICENSE_SERVER" not in os.environ or "192.168.1.5" not in os.environ.get("SPLM_LICENSE_SERVER", ""):
    _c = os.environ.get("SPLM_LICENSE_SERVER", "28000@SunFibo19")
    os.environ["SPLM_LICENSE_SERVER"] = f"28000@192.168.1.5;28000@SunFibo19;28000@192.168.1.29;28000@192.168.1.3;{_c}"

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities

REPO = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
S = 110.0  # mm per OBJ unit
HALF_T = 17.0  # half thickness (OBJ z ~ +-0.155)


def P(x, y, z=0.0):
    return NXOpen.Point3d(float(x), float(y), float(z))


# ---- OBJ silhouette (OBJ units) measured from y-slices ----
LEFT = [(-0.367, -1.0), (-0.384, -0.95), (-0.399, -0.9), (-0.411, -0.85), (-0.421, -0.8), (-0.429, -0.75),
        (-0.434, -0.7), (-0.437, -0.6), (-0.434, -0.4), (-0.428, -0.3), (-0.415, -0.2), (-0.396, -0.1),
        (-0.370, 0.0), (-0.339, 0.1), (-0.309, 0.2), (-0.276, 0.3), (-0.242, 0.4), (-0.224, 0.5),
        (-0.207, 0.6), (-0.188, 0.65), (-0.163, 0.7), (-0.200, 0.75), (-0.231, 0.8), (-0.254, 0.85),
        (-0.256, 0.9), (-0.203, 0.95), (-0.170, 1.0)]
RIGHT = [(0.360, -1.0), (0.377, -0.95), (0.391, -0.9), (0.401, -0.85), (0.413, -0.8), (0.422, -0.75),
         (0.427, -0.7), (0.429, -0.6), (0.431, -0.3), (0.426, -0.1), (0.413, 0.0), (0.393, 0.1),
         (0.367, 0.2), (0.329, 0.3), (0.281, 0.4), (0.228, 0.5), (0.210, 0.6), (0.193, 0.65),
         (0.178, 0.7), (0.213, 0.75), (0.244, 0.8), (0.251, 0.85), (0.244, 0.9), (0.183, 0.95), (0.150, 1.0)]
# Recess (label field) polygon, OBJ units
RECESS = [(-0.355, -0.74), (0.36, -0.74), (0.36, -0.43), (0.03, -0.43), (0.03, 0.27), (-0.04, 0.34),
          (-0.17, 0.34), (-0.225, 0.27), (-0.27, 0.10), (-0.30, 0.0), (-0.345, -0.2), (-0.365, -0.4)]
HOLE_C = (0.222, -0.06)
HOLE_A, HOLE_B = 0.265, 0.098
HOLE_ROT = math.radians(97.7)


def set_name(o, n):
    try:
        o.SetName(n)
    except Exception:
        pass


def nx_section(part, curves, help_pt):
    sec = part.Sections.CreateSection(0.01, 0.01, 0.5)
    rules = [part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    sec.AddToSection(rules, curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, help_pt,
                     NXOpen.Section.Mode.Create, False)
    return sec


def poly_lines(part, pts):
    n = len(pts)
    return [part.Curves.CreateLine(P(*pts[i]), P(*pts[(i + 1) % n])) for i in range(n)]


def extrude(part, curves, help_pt, vec, start, end, name, cut_target=None):
    """Extrude closed curves. start/end are expression strings or 'THRU' (through-all).
    If cut_target is given, the extrude subtracts directly from that body."""
    ET = NXOpen.GeometricUtilities.Extend.ExtendType
    eb = part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        eb.Section = nx_section(part, curves, help_pt)
        eb.Direction = part.Directions.CreateDirection(P(0, 0, 0), NXOpen.Vector3d(*[float(c) for c in vec]),
                                                       NXOpen.SmartObject.UpdateOption.WithinModeling)
        for lim, val in ((eb.Limits.StartExtend, start), (eb.Limits.EndExtend, end)):
            if val == "THRU":
                lim.TrimType = ET.ThroughAll
            else:
                lim.Value.RightHandSide = str(val)
        if cut_target is None:
            eb.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        else:
            eb.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
            eb.BooleanOperation.SetTargetBodies([cut_target])
        feat = eb.CommitFeature()
        set_name(feat, name)
        return feat, (feat.GetBodies()[0] if cut_target is None else None)
    finally:
        eb.Destroy()



def boolean(part, target, tool, op, name):
    b = part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        b.Operation = op
        b.RetainTarget = False
        b.RetainTool = False
        b.Target = target
        b.Tools.Add(tool)
        f = b.CommitFeature()
        set_name(f, name)
        return f
    finally:
        b.Destroy()


def solid(part):
    return [b for b in part.Bodies if b.IsSolidBody][0]


def planar_faces(body):
    out = []
    for f in body.GetFaces():
        if f.SolidFaceType != NXOpen.Face.FaceType.Planar:
            continue
        vs = [v for e in f.GetEdges() for v in e.GetVertices()]
        if vs:
            out.append((f, vs))
    return out


def faces_at(body, axis, value, tol=0.05):
    res = []
    for f, vs in planar_faces(body):
        cs = [getattr(v, axis) for v in vs]
        if max(cs) - min(cs) < tol and abs(cs[0] - value) < tol:
            xs = [v.X for v in vs]
            ys = [v.Y for v in vs]
            area = (max(xs) - min(xs)) * (max(ys) - min(ys)) + 1e-6
            res.append((area, f))
    res.sort(key=lambda t: -t[0])
    return [f for _, f in res]


def blend(part, rules_fn, radius_expr, name):
    bb = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        coll = part.ScCollectors.CreateCollector()
        coll.ReplaceRules([rules_fn()], False)
        bb.Tolerance = 0.01
        bb.AddChainset(coll, radius_expr)
        f = bb.CommitFeature()
        set_name(f, name)
        print(f"  [OK] {name}")
        return f
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return None
    finally:
        bb.Destroy()


def main():
    out_prt = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO / "Surfexcel2_Parametric.prt"
    if out_prt.exists():
        out_prt.unlink()
    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(out_prt), NXOpen.Part.Units.Millimeters)

    exp_defs = [
        ("Z1_START", "-110.000"), ("Z1_H", "143.000"),
        ("Z2_START", "Z1_START + Z1_H"), ("Z2_H", "35.200"),
        ("NECK_START", "Z2_START + Z2_H"), ("NECK_H", "15.400"),
        ("CAP_START", "NECK_START + NECK_H"), ("CAP_H", "26.400"),
        ("CAP_TOP_R", "8.000"), ("BASE_R", "7.000"), ("FACE_EDGE_R", "5.000"),
        ("HANDLE_RIM_R", "5.000"), ("RECESS_FLOOR_Z", "12.400"), ("RECESS_FLOOR_R", "2.000"),
    ]
    for n, v in exp_defs:
        part.Expressions.CreateExpression("Number", f"{n} = {v}")
        print(f"  {n} = {v}")

    def rect(x0, x1):
        return [(x0 * S, 0, -HALF_T), (x1 * S, 0, -HALF_T), (x1 * S, 0, HALF_T), (x0 * S, 0, HALF_T)]

    zones = [("ZONE1_LOWER_BODY", -0.445, 0.435, "Z1_START", "Z1_START + Z1_H"),
             ("ZONE2_SHOULDER", -0.30, 0.34, "Z2_START", "Z2_START + Z2_H"),
             ("ZONE3_NECK", -0.21, 0.22, "NECK_START", "NECK_START + NECK_H"),
             ("ZONE4_CAP", -0.27, 0.27, "CAP_START", "CAP_START + CAP_H")]
    print("[1] Zones")
    main_body = None
    for name, x0, x1, s, e in zones:
        pts = rect(x0, x1)
        feat, body = extrude(part, poly_lines(part, pts), P(*pts[0]), (0, 1, 0), s, e, name)
        if main_body is None:
            main_body = body
        else:
            boolean(part, main_body, body, NXOpen.Features.Feature.BooleanType.Unite, "UNITE_" + name)
        main_body = solid(part)

    print("[2] Silhouette cuts")
    top_y, bot_y = 1.05 * S, -1.05 * S
    lpts = [(LEFT[0][0] * S, bot_y)] + [(x * S, y * S) for x, y in LEFT] + [(LEFT[-1][0] * S, top_y), (-0.8 * S, top_y), (-0.8 * S, bot_y)]
    rpts = [(RIGHT[0][0] * S, bot_y)] + [(x * S, y * S) for x, y in RIGHT] + [(RIGHT[-1][0] * S, top_y), (0.8 * S, top_y), (0.8 * S, bot_y)]
    for nm, pts in (("SILHOUETTE_LEFT", lpts), ("SILHOUETTE_RIGHT", rpts)):
        extrude(part, poly_lines(part, [(x, y, 0) for x, y in pts]), P(pts[0][0], pts[0][1], 0),
                (0, 0, 1), "THRU", "THRU", nm, cut_target=solid(part))
    main_body = solid(part)

    print("[3] Cap top / base blends")
    top = faces_at(main_body, "Y", 110.0)
    if top:
        blend(part, lambda: part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([top[0]]), "CAP_TOP_R", "CAP_TOP_BLEND")
    main_body = solid(part)
    bot = faces_at(main_body, "Y", -110.0)
    if bot:
        blend(part, lambda: part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([bot[0]]), "BASE_R", "BASE_BLEND")
    main_body = solid(part)

    print("[4] Handle opening")
    cen = P(HOLE_C[0] * S, HOLE_C[1] * S, 0)
    mat = session.Parts.Work.NXMatrices.Create(NXOpen.Matrix3x3()) if False else None
    ident = NXOpen.Matrix3x3()
    ident.Xx, ident.Xy, ident.Xz = 1.0, 0.0, 0.0
    ident.Yx, ident.Yy, ident.Yz = 0.0, 1.0, 0.0
    ident.Zx, ident.Zy, ident.Zz = 0.0, 0.0, 1.0
    mat = part.NXMatrices.Create(ident)
    ell = part.Curves.CreateEllipse(cen, HOLE_A * S, HOLE_B * S, 0.0, 2 * math.pi, HOLE_ROT, mat)
    hole_feat, _ = extrude(part, [ell], cen, (0, 0, 1), "THRU", "THRU", "HANDLE_OPENING", cut_target=solid(part))
    main_body = solid(part)

    print("[6] Handle rim blend")
    wall = []
    cx, cy = HOLE_C[0] * S, HOLE_C[1] * S
    ca, sa = math.cos(HOLE_ROT), math.sin(HOLE_ROT)
    for f in main_body.GetFaces():
        if f.SolidFaceType == NXOpen.Face.FaceType.Planar:
            continue
        vs = [v for e in f.GetEdges() for v in e.GetVertices()]
        if not vs:
            continue
        ok = True
        for v in vs:
            dx, dy = v.X - cx, v.Y - cy
            u = (dx * ca + dy * sa) / (HOLE_A * S)
            w = (-dx * sa + dy * ca) / (HOLE_B * S)
            if abs(math.hypot(u, w) - 1.0) > 0.05:
                ok = False
                break
        if ok:
            wall.append(f)
    print("  hole wall faces:", len(wall))
    if wall:
        blend(part, lambda: part.ScRuleFactory.CreateRuleEdgeFace(wall), "HANDLE_RIM_R", "HANDLE_RIM_BLEND")
    main_body = solid(part)

    print("[5] Face perimeter blends")
    for zval in (HALF_T, -HALF_T):
        fs = faces_at(main_body, "Z", zval)
        if fs:
            blend(part, lambda: part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([fs[0]]), "FACE_EDGE_R",
                  "FACE_PERIMETER_BLEND_%s" % ("FRONT" if zval > 0 else "BACK"))
        main_body = solid(part)

    print("[7] Recessed label fields")
    rp = [(x * S, y * S, 0) for x, y in RECESS]
    for nm, vec in (("RECESS_FRONT", (0, 0, 1)), ("RECESS_BACK", (0, 0, -1))):
        extrude(part, poly_lines(part, rp), P(*rp[0]), vec, "RECESS_FLOOR_Z", "THRU", nm, cut_target=solid(part))
    main_body = solid(part)
    for zval in (12.4, -12.4):
        fs = faces_at(main_body, "Z", zval, 0.2)
        if fs:
            blend(part, lambda: part.ScRuleFactory.CreateRuleOuterEdgesOfFaces([fs[0]]), "RECESS_FLOOR_R",
                  "RECESS_FLOOR_BLEND_%s" % ("FRONT" if zval > 0 else "BACK"))
        main_body = solid(part)

    print("Features:")
    for i, f in enumerate(part.Features):
        print(f"  [{i:2d}] {f.FeatureType:14s} {f.GetFeatureName()}")
    print("Solids:", len([b for b in part.Bodies if b.IsSolidBody]))
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    stl = out_prt.with_suffix(".stl")
    c = session.DexManager.CreateStlCreator()
    try:
        c.OutputFile = str(stl)
        c.ExportSelectionBlock.Add(solid(part))
        c.Commit()
    finally:
        c.Destroy()
    try:
        (REPO / "latest_nx_result.txt").write_text(str(out_prt), encoding="utf-8")
        (REPO / "open_current_nx_result.cmd").write_text(
            f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugraf.exe" "{out_prt}"\n', encoding="utf-8")
    except Exception:
        pass
    print("[DONE]", out_prt)
    part.Close(NXOpen.BasePart.CloseWholeTree.FalseValue, NXOpen.BasePart.CloseModified.CloseModified, None)


if __name__ == "__main__":
    main()
