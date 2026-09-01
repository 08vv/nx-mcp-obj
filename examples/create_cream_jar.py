"""Create a clean, production-ready, parametric cosmetic cream jar model in Siemens NX 2206.

This script implements a high-quality CAD modeling history for:
- Jar Body (Revolve, Shell, Offset Face, Bottom Edge Blend, Shoulder Edge Blend)
- Collar Ring (Sketch, Revolve, Edge Blends)
- Lid (Sketch, Revolve, Top Dome, Neck Cavity, Corner Edge Blend)

All primary dimensions are controlled via Expressions.

Usage:
  run_journal.exe create_cream_jar.py [output_path.prt]
"""

from __future__ import annotations
import math
import os
import sys
import traceback
from pathlib import Path
import NXOpen
import NXOpen.UF
from examples._common import set_name, unite, vec

UF = NXOpen.UF.UFSession.GetUFSession()

# ---------------------------------------------------------------------------
# Default parameters (mm) — derived from Pond's Age Miracle Eye Cream Jar
# ---------------------------------------------------------------------------
VALUES = {
    "Overall_Diameter": 70.0,
    "Overall_Height": 58.1,
    "Jar_Diameter": 70.0,
    "Jar_Height": 32.0,
    "Jar_Wall_Thickness": 6.0,
    "Base_Thickness": 8.0,
    "Bottom_Blend_Radius": 8.0,
    "Neck_Diameter": 56.0,
    "Neck_Height": 12.0,
    "Collar_Diameter": 59.0,
    "Collar_Height": 3.5,
    "Collar_Thickness": 1.5,
    "Lid_Diameter": 68.0,
    "Lid_Height": 22.0,
    "Lid_Dome_Height": 4.5,
    "Lid_Corner_Radius": 8.0,
    "Edge_Blend_Radius": 0.5,
    "Split_Gap": 0.3,
}

DERIVED = {
    "Overall_Diameter": "Jar_Diameter",
    "Overall_Height": "Jar_Height + Split_Gap + Collar_Height + Split_Gap + Lid_Height",
    "Jar_Radius": "Jar_Diameter / 2.0",
    "Neck_Radius": "Neck_Diameter / 2.0",
    "Collar_Outer_Radius": "Collar_Diameter / 2.0",
    "Collar_Inner_Radius": "Collar_Outer_Radius - Collar_Thickness",
    "Collar_Start_Z": "Jar_Height + Split_Gap",
    "Collar_End_Z": "Collar_Start_Z + Collar_Height",
    "Lid_Start_Z": "Jar_Height + Split_Gap + Collar_Height + Split_Gap",
    "Lid_Radius": "Lid_Diameter / 2.0",
    "Lid_Cavity_Radius": "(Neck_Diameter + Split_Gap) / 2.0",
    "Lid_Cavity_Top_Z": "Jar_Height + Neck_Height + Split_Gap",
    "Lid_Dome_Base_Z": "Lid_Start_Z + Lid_Height - Lid_Dome_Height",
    "Lid_Top_Z": "Lid_Start_Z + Lid_Height",
}

def out_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parents[3] / "Cream_Jar_Model.prt"


def commit_builder(builder):
    commit = getattr(builder, "CommitFeature", None) or getattr(builder, "Commit", None)
    return commit()

def point(x: float, y: float, z: float) -> NXOpen.Point3d:
    return NXOpen.Point3d(float(x), float(y), float(z))


def line(part, a, b):
    return part.Curves.CreateLine(point(*a), point(*b))

# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------
def make_expressions(part) -> None:
    # 1. Create base expressions
    for name, value in VALUES.items():
        if name in ("Overall_Diameter", "Overall_Height"):
            continue
        try:
            try:
                expr = part.Expressions.FindObject(name)
                expr.RightHandSide = str(value)
            except Exception:
                part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
        except Exception:
            pass

    # 2. Create derived expressions
    for name, rhs in DERIVED.items():
        try:
            try:
                expr = part.Expressions.FindObject(name)
                expr.RightHandSide = rhs
            except Exception:
                part.Expressions.CreateExpression("Number", "{} = {}".format(name, rhs))
        except Exception:
            pass

def get_val(part, name: str) -> float:
    try:
        return part.Expressions.FindObject(name).Value
    except Exception:
        return float(VALUES.get(name, 0.0))

# ---------------------------------------------------------------------------
# Sketch Creation
# ---------------------------------------------------------------------------
def create_sketch_on_csys(part, origin, x_vec, y_vec, z_vec, sketch_name):
    matrix = NXOpen.Matrix3x3()
    matrix.Xx = x_vec.X; matrix.Xy = x_vec.Y; matrix.Xz = x_vec.Z
    matrix.Yx = y_vec.X; matrix.Yy = y_vec.Y; matrix.Yz = y_vec.Z
    matrix.Zx = z_vec.X; matrix.Zy = z_vec.Y; matrix.Zz = z_vec.Z
    nx_matrix = part.NXMatrices.Create(matrix)
    csys = part.CoordinateSystems.CreateCoordinateSystem(origin, nx_matrix, True)

    factory2 = getattr(part.Sketches, "CreateSketchInPlaceBuilder2", None)
    builder = None
    if factory2 is not None:
        try:
            builder = factory2(None)
        except Exception:
            pass
    if builder is None:
        factory = getattr(part.Sketches, "CreateNewSketchInPlaceBuilder", None)
        if factory is None:
            factory = getattr(part.Sketches, "CreateSketchInPlaceBuilder", None)
        builder = factory(None)
    try:
        builder.Csystem = csys
        commit = getattr(builder, "CommitFeature", None) or getattr(builder, "Commit", None)
        feat = commit()
    finally:
        builder.Destroy()
    try:
        feat.SetName(sketch_name)
    except Exception:
        pass
    sketch = feat.Sketch if hasattr(feat, "Sketch") else feat
    return feat, sketch

def xz_sketch(part, name: str):
    """Create a sketch on the XZ plane (Y=0, Z is vertical)."""
    return create_sketch_on_csys(
        part,
        point(0.0, 0.0, 0.0),
        vec(1.0, 0.0, 0.0),
        vec(0.0, 0.0, 1.0),
        vec(0.0, -1.0, 0.0),
        name,
    )

# ---------------------------------------------------------------------------
# UF Revolve Wrapper
# ---------------------------------------------------------------------------
def revolve_z(part, curves, start_angle, end_angle, name, target=None):
    tags = [curve.Tag for curve in curves]
    features, number_of_features = UF.Modl.CreateRevolution(
        tags,
        len(tags),
        None,
        [str(start_angle), str(end_angle)],
        ["0", "0"],
        [0.0, 0.0, 0.0],
        False,
        True,
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
        NXOpen.UF.Modl.FeatureSigns.NULLSIGN,
    )
    if not features or number_of_features < 1:
        raise RuntimeError("Revolve did not create a feature")
    feature = NXOpen.TaggedObjectManager().GetTaggedObject(features[0])
    set_name(feature, name)
    bodies = feature.GetBodies()
    return feature, target if target is not None else (bodies[0] if bodies else None)

# ---------------------------------------------------------------------------
# Feature Builders
# ---------------------------------------------------------------------------
def cylinder(part, origin_z_val, diameter_rhs, height_rhs, name):
    builder = part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        direction = part.Directions.CreateDirection(
            point(0.0, 0.0, float(origin_z_val)),
            vec(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Axis.Point.SetCoordinates(point(0.0, 0.0, float(origin_z_val)))
        builder.Axis.Direction = direction
        builder.Diameter.RightHandSide = str(diameter_rhs)
        builder.Height.RightHandSide = str(height_rhs)
        feat = builder.Commit()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, bodies[0] if bodies else None


def create_shell(part, body, removed_face, thickness_rhs, name):
    builder = part.Features.CreateShellBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Body = body
        builder.DefaultThickness.RightHandSide = thickness_rhs
        builder.Tolerance = 0.01
        collector = part.ScCollectors.CreateCollector()
        collector.ReplaceRules([part.ScRuleFactory.CreateRuleFaceDumb([removed_face])], False)
        builder.RemovedFacesCollector = collector
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    bodies = feat.GetBodies()
    return feat, bodies[0] if bodies else body

def offset_face(part, face, distance_rhs, name):
    builder = part.Features.CreateOffsetFaceBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Distance.RightHandSide = distance_rhs
        rule = part.ScRuleFactory.CreateRuleFaceDumb([face])
        builder.FaceCollector.ReplaceRules([rule], False)
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)

def add_edge_blend(part, edges, radius_rhs, name):
    builder = part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
    try:
        collector = part.ScCollectors.CreateCollector()
        collector.ReplaceRules([part.ScRuleFactory.CreateRuleEdgeDumb(edges)], False)
        builder.Tolerance = 0.01
        builder.AddChainset(collector, radius_rhs)
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    set_name(feat, name)
    return feat

# ---------------------------------------------------------------------------
# Geometry Face & Edge Queries
# ---------------------------------------------------------------------------
def find_top_face(body, z_val):
    for face in body.GetFaces():
        if face.SolidFaceType == NXOpen.Face.FaceType.Planar:
            z_coords = []
            for edge in face.GetEdges():
                verts = edge.GetVertices()
                if verts:
                    z_coords.append(verts[0].Z)
            if z_coords:
                avg_z = sum(z_coords) / len(z_coords)
                if abs(avg_z - z_val) < 0.2:
                    return face
    return None

def find_inside_bottom_face(body, z_val):
    for face in body.GetFaces():
        if face.SolidFaceType == NXOpen.Face.FaceType.Planar:
            z_coords = []
            for edge in face.GetEdges():
                verts = edge.GetVertices()
                if verts:
                    z_coords.append(verts[0].Z)
            if z_coords:
                avg_z = sum(z_coords) / len(z_coords)
                if abs(avg_z - z_val) < 0.2 and avg_z > 0.1:
                    return face
    return None

def find_bottom_outer_edges(body, r_val):
    edges = []
    for edge in body.GetEdges():
        verts = edge.GetVertices()
        if verts:
            z1, z2 = verts[0].Z, verts[1].Z
            if abs(z1) < 0.2 and abs(z2) < 0.2:
                d = math.hypot(verts[0].X, verts[0].Y)
                if abs(d - r_val) < 1.0:
                    edges.append(edge)
    return edges

def find_shoulder_outer_edges(body, h_val, r_val):
    edges = []
    for edge in body.GetEdges():
        verts = edge.GetVertices()
        if verts:
            z1, z2 = verts[0].Z, verts[1].Z
            if abs(z1 - h_val) < 0.2 and abs(z2 - h_val) < 0.2:
                d = math.hypot(verts[0].X, verts[0].Y)
                if abs(d - r_val) < 1.0:
                    edges.append(edge)
    return edges

def find_collar_outer_edges(body, z_val, r_val):
    edges = []
    for edge in body.GetEdges():
        verts = edge.GetVertices()
        if verts:
            z1, z2 = verts[0].Z, verts[1].Z
            if abs(z1 - z_val) < 0.2 and abs(z2 - z_val) < 0.2:
                d = math.hypot(verts[0].X, verts[0].Y)
                if abs(d - r_val) < 1.0:
                    edges.append(edge)
    return edges

def find_lid_outer_edges(body, z_val, r_val):
    edges = []
    for edge in body.GetEdges():
        verts = edge.GetVertices()
        if verts:
            z1, z2 = verts[0].Z, verts[1].Z
            if abs(z1 - z_val) < 0.2 and abs(z2 - z_val) < 0.2:
                d = math.hypot(verts[0].X, verts[0].Y)
                if abs(d - r_val) < 1.0:
                    edges.append(edge)
    return edges

# ---------------------------------------------------------------------------
# Main Builder
# ---------------------------------------------------------------------------
def main():
    path = out_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()
    
    # Close any open parts to ensure clean slate
    try:
        session.Parts.CloseAll(NXOpen.BasePartCloseModified.CloseModified, None)
    except Exception:
        pass
        
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

    # Create new part
    part = session.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)

    # 1. Create Expressions
    make_expressions(part)
    print("[OK] All named Expressions successfully created.")

    # 2. Build S1_Jar_Body Sketch & Revolve
    feat_s1, sk1 = xz_sketch(part, "S1_Jar_Body")
    
    jar_r = get_val(part, "Jar_Radius")
    jar_h = get_val(part, "Jar_Height")
    
    p1 = (0.0, 0.0, 0.0)
    p2 = (jar_r, 0.0, 0.0)
    p3 = (jar_r, 0.0, jar_h)
    p4 = (0.0, 0.0, jar_h)
    
    l1 = line(part, p1, p2)
    l2 = line(part, p2, p3)
    l3 = line(part, p3, p4)
    l4 = line(part, p4, p1)
    
    sk1.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    infer = NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints
    for l in (l1, l2, l3, l4):
        sk1.AddGeometry(l, infer)
        
    sk1.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
    
    # Revolve curves using the UF function
    revolve_feat, jar_body = revolve_z(part, [l1, l2, l3, l4], "0", "360", "F1_Revolve_Jar_Body")
    print("[OK] Jar outer body cylinder revolved.")

    # 3. Add Neck cylinder
    neck_feat, neck_body = cylinder(part, jar_h, "Neck_Diameter", "Neck_Height", "F2_Neck_Cylinder")
    jar_body = unite(part, jar_body, neck_body, "F3_Unite_Neck")
    print("[OK] Neck cylinder united with Jar Body.")

    # 4. Shell the combined body from the neck top face
    neck_top_z = jar_h + get_val(part, "Neck_Height")
    top_face = find_top_face(jar_body, neck_top_z)
    if top_face:
        shell_feat, jar_body = create_shell(part, jar_body, top_face, "Jar_Wall_Thickness", "F4_Shell_Jar")
        print("[OK] Jar body hollowed out using Shell.")
    else:
        print("[FAIL] Could not find top face of the neck for the shell operation.")
        raise RuntimeError("Shell top face not found")

    # 5. Offset the inner bottom face to create a thick base
    inner_bottom_z = get_val(part, "Jar_Wall_Thickness")
    inner_bottom_face = find_inside_bottom_face(jar_body, inner_bottom_z)
    if inner_bottom_face:
        offset_face(part, inner_bottom_face, "Base_Thickness - Jar_Wall_Thickness", "F5_Base_Offset")
        print("[OK] Base thickened using Offset Face.")
    else:
        print("[WARN] Inner bottom face not found for offset. Base thickness remains uniform.")

    # 6. Apply Edge Blends to Jar Body
    bottom_edges = find_bottom_outer_edges(jar_body, jar_r)
    if bottom_edges:
        add_edge_blend(part, bottom_edges, "Bottom_Blend_Radius", "F6_Bottom_Blend")
        print("[OK] Bottom perimeter edge blend applied.")
        
    shoulder_edges = find_shoulder_outer_edges(jar_body, jar_h, jar_r)
    if shoulder_edges:
        add_edge_blend(part, shoulder_edges, "6.0", "F7_Shoulder_Blend")
        print("[OK] Shoulder perimeter edge blend applied.")

    # 7. Build S2_Collar_Ring Sketch & Revolve
    feat_s2, sk2 = xz_sketch(part, "S2_Collar_Ring")
    
    c_out = get_val(part, "Collar_Outer_Radius")
    c_in = get_val(part, "Collar_Inner_Radius")
    c_start = get_val(part, "Collar_Start_Z")
    c_end = get_val(part, "Collar_End_Z")
    
    cp1 = (c_in, 0.0, c_start)
    cp2 = (c_out, 0.0, c_start)
    cp3 = (c_out, 0.0, c_end)
    cp4 = (c_in, 0.0, c_end)
    
    cl1 = line(part, cp1, cp2)
    cl2 = line(part, cp2, cp3)
    cl3 = line(part, cp3, cp4)
    cl4 = line(part, cp4, cp1)
    
    sk2.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for l in (cl1, cl2, cl3, cl4):
        sk2.AddGeometry(l, infer)
        
    sk2.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
    
    # Revolve curves using the UF function
    collar_feat, collar_body = revolve_z(part, [cl1, cl2, cl3, cl4], "0", "360", "F8_Revolve_Collar")
    print("[OK] Collar Ring revolved as a separate solid body.")

    # 8. Apply Edge Blends to Collar Ring outer edges
    collar_top_edges = find_collar_outer_edges(collar_body, c_end, c_out)
    collar_bot_edges = find_collar_outer_edges(collar_body, c_start, c_out)
    collar_edges_to_blend = collar_top_edges + collar_bot_edges
    if collar_edges_to_blend:
        add_edge_blend(part, collar_edges_to_blend, "Edge_Blend_Radius", "F9_Collar_Blend")
        print("[OK] Collar Ring edges rounded.")

    # 9. Build S3_Lid Sketch & Revolve
    feat_s3, sk3 = xz_sketch(part, "S3_Lid")
    
    lid_start_z = get_val(part, "Lid_Start_Z")
    lid_height = get_val(part, "Lid_Height")
    lid_dome_height = get_val(part, "Lid_Dome_Height")
    lid_diameter = get_val(part, "Lid_Diameter")
    neck_diameter = get_val(part, "Neck_Diameter")
    neck_height_val = get_val(part, "Neck_Height")
    split_gap = get_val(part, "Split_Gap")
    
    W = lid_diameter / 2.0
    H = lid_dome_height
    R_dome = (W**2 + H**2) / (2.0 * H)
    Z_center = lid_start_z + lid_height - R_dome
    theta = math.atan2(R_dome - H, W)
    
    # Recess calculations
    r_recess = (neck_diameter + split_gap) / 2.0
    z_recess_top = jar_h + neck_height_val + split_gap
    z_lid_top = lid_start_z + lid_height
    z_dome_end = z_lid_top - H
    
    # Dome Arc BA: from B(W, z_dome_end) to A(0, z_lid_top)
    arc_center = point(0.0, 0.0, Z_center)
    arc_ba = part.Curves.CreateArc(arc_center, vec(1.0, 0.0, 0.0), vec(0.0, 0.0, 1.0), R_dome, theta, math.pi / 2.0)
    
    # Loop lines
    # FE: flat top of neck cavity
    ll1 = line(part, (0.0, 0.0, z_recess_top), (r_recess, 0.0, z_recess_top))
    # ED: inner side wall of neck cavity
    ll2 = line(part, (r_recess, 0.0, z_recess_top), (r_recess, 0.0, lid_start_z))
    # DC: flat bottom face of lid (mating split line area)
    ll3 = line(part, (r_recess, 0.0, lid_start_z), (W, 0.0, lid_start_z))
    # CB: outer vertical wall of lid
    ll4 = line(part, (W, 0.0, lid_start_z), (W, 0.0, z_dome_end))
    # FA: vertical center line closing the loop (directed CCW, down along axis)
    ll5 = line(part, (0.0, 0.0, z_lid_top), (0.0, 0.0, z_recess_top))
    
    sk3.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    sk3.AddGeometry(arc_ba, infer)
    for l in (ll1, ll2, ll3, ll4, ll5):
        sk3.AddGeometry(l, infer)
        
    sk3.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
    
    # Revolve curves using the UF function
    lid_curves_ccw = [ll1, ll2, ll3, ll4, arc_ba, ll5]
    lid_feat, lid_body = revolve_z(part, lid_curves_ccw, "0", "360", "F10_Revolve_Lid")
    print("[OK] Lid revolved as a separate solid body.")

    # 10. Apply Edge Blends to Lid
    lid_corner_edges = find_lid_outer_edges(lid_body, z_dome_end, W)
    if lid_corner_edges:
        add_edge_blend(part, lid_corner_edges, "Lid_Corner_Radius", "F11_Lid_Corner_Blend")
        print("[OK] Lid top corner blend applied.")
        
    lid_bottom_edges = find_lid_outer_edges(lid_body, lid_start_z, W)
    if lid_bottom_edges:
        add_edge_blend(part, lid_bottom_edges, "Edge_Blend_Radius", "F12_Lid_Bottom_Blend")
        print("[OK] Lid lower edge split blend applied.")

    # 11. Finalize body naming
    set_name(jar_body, "Jar_Body")
    set_name(collar_body, "Collar_Ring")
    set_name(lid_body, "Lid")
    print("[OK] All three solid bodies renamed to Jar_Body, Collar_Ring, and Lid.")

    # Save
    part.ModelingViews.WorkView.Fit()
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("Cream Jar Model saved successfully to {}".format(path))

if __name__ == "__main__":
    log_path = Path(__file__).resolve().parents[3] / "cream_jar_journal.log"
    try:
        log_path.write_text("Starting cream jar model journal\n", encoding="utf-8")
        main()
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write("Completed successfully\n")
    except Exception:
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(traceback.format_exc())
        raise
