import json
import os
import sys
import traceback
from pathlib import Path
import socket
import select
import time
import math

import NXOpen
import NXOpen.UF


def get_root_dir():
    env_root = os.environ.get("NX_MCP_ROOT")
    if env_root:
        return Path(env_root)
    try:
        file_path = Path(__file__).resolve()
        for parent in file_path.parents:
            if (parent / ".git").exists() or parent.name == "nx-mcp":
                return parent
        return file_path.parents[3]
    except Exception:
        return Path(os.getcwd())

ROOT_DIR = get_root_dir()


def _debug_log(filename, content, mode="a"):
    if os.environ.get("NX_MCP_DEBUG_LOGS") == "1":
        try:
            debug_path = ROOT_DIR / "scratch" / filename
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            with open(debug_path, mode, encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass


SESSION = NXOpen.Session.GetSession()
UF_SESSION = NXOpen.UF.UFSession.GetUFSession()
ACTIVE_SKETCH_PLANE = "XY"
_state = {
    "last_curves": [],
    "last_feature": None,
    "last_body": None,
    "features": {},
    "bodies": {},
    "sketches": {},
    "active_sketch": None,
}


class SelectionError(RuntimeError):
    pass

import ast
import operator

_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def _safe_math_eval(expr_str):
    """Evaluate a simple arithmetic expression safely without eval()."""
    node = ast.parse(expr_str.strip(), mode="eval").body
    return float(_eval_node(node))

def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"Unsupported expression node: {ast.dump(node)}")


def _eval_val(val):
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    try:
        return float(val_str)
    except ValueError:
        pass
    
    work_part = _ensure_work_part()
    counter = _expression_counters.get("EVAL_TEMP", 1)
    temp_name = f"EVAL_TEMP_{counter}"
    _expression_counters["EVAL_TEMP"] = counter + 1
    try:
        exp = work_part.Expressions.CreateExpression("Number", f"{temp_name} = {val_str}")
        res = exp.Value
        work_part.Expressions.Delete(exp)
        return res
    except Exception as e:
        sys.stderr.write(f"Expression eval error for '{val_str}': {e}\n")
        try:
            return _safe_math_eval(val_str)
        except Exception:
            raise RuntimeError(f"Could not evaluate expression '{val_str}': {e}")


def _default_part_path():
    return str(ROOT_DIR.joinpath("nx_mcp_result.prt").resolve())


_counters_seeded = False

def _ensure_work_part():
    global _counters_seeded
    if SESSION.Parts.Work is None:
        SESSION.Parts.NewDisplay(
            _default_part_path(),
            NXOpen.Part.Units.Millimeters,
        )
    work_part = SESSION.Parts.Work
    if not _counters_seeded and work_part is not None:
        _seed_counters_from_part(work_part)
        _counters_seeded = True
    return work_part


def _resolve_direction(direction):
    ref = str(direction or "auto").strip().lower()
    if ref == "auto":
        if ACTIVE_SKETCH_PLANE == "XY":
            return "Z"
        if ACTIVE_SKETCH_PLANE == "XZ":
            return "Y"
        return "X"
    return direction


def _resolve_hole_direction(direction):
    ref = str(direction or "auto").strip().lower()
    if ref == "auto":
        if ACTIVE_SKETCH_PLANE == "XY":
            return "-Z"
        if ACTIVE_SKETCH_PLANE == "XZ":
            return "-Y"
        return "-X"
    return direction


def _resolve_revolve_axis(axis):
    ref = str(axis or "auto").strip().lower()
    if ref == "auto":
        if ACTIVE_SKETCH_PLANE == "XY":
            return "Y"
        if ACTIVE_SKETCH_PLANE == "XZ":
            return "Z"
        return "Z"
    return axis


_expression_counters = {}

def _create_named_expression(work_part, prefix, value):
    if not hasattr(work_part, "Expressions"):
        return f"{prefix}_MOCK"
    # Use cached counter to avoid linear search every time
    start = _expression_counters.get(prefix, 1)
    for counter in range(start, start + 1000):
        name = f"{prefix}_{counter}"
        try:
            work_part.Expressions.FindObject(name)
        except Exception:
            work_part.Expressions.CreateExpression("Number", f"{name} = {value}")
            _expression_counters[prefix] = counter + 1
            return name
    raise RuntimeError(f"Could not create expression with prefix '{prefix}' after 1000 attempts")


_instance_counters = {}

def _next_instance_prefix(feature_type):
    """
    Returns a unique, human-readable prefix for ONE call to a feature-creating
    tool, e.g. "CUBOID_1", "CUBOID_2", "ARM_1", "ARM_2".

    Call this EXACTLY ONCE at the start of each feature-creating function,
    then build every expression name for that call using this prefix, e.g.:
        prefix = _next_instance_prefix("CUBOID")
        _create_input_expression(work_part, f"{prefix}_L", length)
        _create_input_expression(work_part, f"{prefix}_W", width)
    """
    count = _instance_counters.get(feature_type, 0) + 1
    _instance_counters[feature_type] = count
    return f"{feature_type}_{count}"


import re
_INSTANCE_PREFIX_RE = re.compile(r"^([A-Z_]+)_(\d+)_")

def _seed_counters_from_part(work_part):
    """Scan existing NX expressions in the part to seed in-memory counters.

    This prevents name collisions after a process restart when the part
    already contains expressions like CUBOID_3_L, FILLET_5_R, etc.
    """
    global _counters_seeded
    if not hasattr(work_part, "Expressions"):
        return
    try:
        expressions = list(work_part.Expressions)
    except Exception:
        return

    for expr in expressions:
        try:
            name = expr.Name
        except Exception:
            continue

        # Match instance prefix pattern: e.g. "CUBOID_3_L" → feature_type="CUBOID", instance=3
        m = _INSTANCE_PREFIX_RE.match(name)
        if m:
            feature_type = m.group(1)
            instance_num = int(m.group(2))
            current = _instance_counters.get(feature_type, 0)
            if instance_num > current:
                _instance_counters[feature_type] = instance_num

        # Also seed _expression_counters for legacy PREFIXED_N names (e.g. "CUBOID_L_3")
        # Find last underscore-delimited number
        parts = name.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            prefix = parts[0]
            num = int(parts[1])
            current = _expression_counters.get(prefix, 1)
            if num + 1 > current:
                _expression_counters[prefix] = num + 1

    _counters_seeded = True


def _create_input_expression(work_part, name, value):
    """
    Creates a plain-number NX expression with an exact, caller-chosen name.
    Use this for BASE inputs (values the user/agent directly sets),
    as opposed to _create_formula_expression() for DERIVED values.
    Unlike _create_named_expression(), this does NOT auto-append a counter
    suffix -- it uses the exact name given, and updates it if it already exists.
    """
    if not hasattr(work_part, "Expressions"):
        return name
    try:
        existing = work_part.Expressions.FindObject(name)
        existing.RightHandSide = str(value)
        return name
    except Exception:
        pass
    work_part.Expressions.CreateExpression("Number", f"{name} = {value}")
    return name


def _create_formula_expression(work_part, name, formula_rhs):
    """
    Creates an NX expression where the right-hand side is a FORMULA
    referencing other expression names (e.g. "ARM_LENGTH - 2 * END_RADIUS"),
    NOT a pre-computed Python number. This is what makes derived values
    truly parametric: if the referenced expressions change later (in NX
    or via edit_expression), this one recalculates automatically inside NX.
    """
    if not hasattr(work_part, "Expressions"):
        return name
    try:
        existing = work_part.Expressions.FindObject(name)
        existing.RightHandSide = formula_rhs
        return name
    except Exception:
        pass
    work_part.Expressions.CreateExpression("Number", f"{name} = {formula_rhs}")
    return name


def _feature_name(feature):
    if feature is None:
        return ""
    for attr in ("GetFeatureName", "Name", "JournalIdentifier"):
        value = getattr(feature, attr, None)
        if callable(value):
            try:
                name = value()
                if name:
                    return str(name)
            except Exception:
                pass
        elif value:
            return str(value)
    return f"feature_{getattr(feature, 'Tag', id(feature))}"


def _body_name(body):
    if body is None:
        return ""
    for attr in ("Name", "JournalIdentifier"):
        value = getattr(body, attr, None)
        if value:
            return str(value)
    return f"body_{getattr(body, 'Tag', id(body))}"


def _snapshot_body_state(body=None):
    if body is None:
        try:
            body = _resolve_body("last")
        except Exception:
            body = None
    if body is None:
        return set(), set()

    edges = getattr(body, "GetEdges", lambda: [])() or []
    faces = getattr(body, "GetFaces", lambda: [])() or []

    edge_tags = {e.Tag for e in edges if getattr(e, "Tag", None)}
    face_tags = {f.Tag for f in faces if getattr(f, "Tag", None)}
    return edge_tags, face_tags


def _remember_feature(feature):
    if feature is None:
        return feature

    name = _feature_name(feature)
    _state["last_feature"] = feature

    body = None
    get_bodies = getattr(feature, "GetBodies", None)
    if callable(get_bodies):
        try:
            bodies = get_bodies() or []
            if bodies:
                body = bodies[0]
                _remember_body(body)
        except Exception:
            pass

    if body is None:
        try:
            body = _resolve_body("last")
        except Exception:
            body = None

    post_edge_tags, post_face_tags = _snapshot_body_state(body)
    pre_edge_tags = _state.get("pre_body_edges", set())
    pre_face_tags = _state.get("pre_body_faces", set())

    delta_edge_tags = list(post_edge_tags - pre_edge_tags)
    delta_face_tags = list(post_face_tags - pre_face_tags)

    feature_entities = getattr(feature, "GetEntities", lambda: [])() or []
    for ent in feature_entities:
        ent_tag = getattr(ent, "Tag", None)
        if ent_tag:
            type_name = type(ent).__name__
            if "Edge" in type_name and ent_tag not in delta_edge_tags:
                delta_edge_tags.append(ent_tag)
            elif "Face" in type_name and ent_tag not in delta_face_tags:
                delta_face_tags.append(ent_tag)

    _state["features"][name.lower()] = {
        "feature": feature,
        "edge_tags": delta_edge_tags,
        "face_tags": delta_face_tags,
    }

    _state["pre_body_edges"] = post_edge_tags
    _state["pre_body_faces"] = post_face_tags

    return feature


def _remember_body(body):
    if body is None:
        return body
    name = _body_name(body)
    _state["last_body"] = body
    _state["bodies"][name.lower()] = body
    return body


def _iter_features(work_part):
    to_array = getattr(work_part.Features, "ToArray", None)
    if callable(to_array):
        return list(to_array() or [])
    return []


def _iter_bodies(work_part):
    bodies = getattr(work_part, "Bodies", None)
    if bodies is not None:
        to_array = getattr(bodies, "ToArray", None)
        if callable(to_array):
            return list(to_array() or [])
        try:
            return list(bodies)
        except TypeError:
            pass

    found = []
    for feature in _iter_features(work_part):
        get_bodies = getattr(feature, "GetBodies", None)
        if not callable(get_bodies):
            continue
        for body in get_bodies() or []:
            if body not in found:
                found.append(body)
    return found


def _resolve_feature(reference="last"):
    work_part = _ensure_work_part()
    ref = str(reference or "last").strip().lower()
    if ref in {"last", "previous", "previous feature", "last feature", "last_created"}:
        feature = _state.get("last_feature")
        if feature is not None:
            return feature

    if ref in _state["features"]:
        val = _state["features"][ref]
        return val["feature"] if isinstance(val, dict) and "feature" in val else val

    for feature in _iter_features(work_part):
        name = _feature_name(feature).lower()
        if name not in _state["features"]:
            _state["features"][name] = feature
        if ref == name or ref in name:
            return feature

    raise SelectionError(f"Could not resolve feature reference: {reference}")


def _resolve_body(reference="last"):
    work_part = _ensure_work_part()
    ref = str(reference or "last").strip().lower()
    if ref in {"last", "last body", "last_created", "last created body", "target"}:
        body = _state.get("last_body")
        if body is not None:
            return body

    if ref.startswith("body_"):
        suffix = ref[5:].strip()
        if suffix.isdigit():
            idx = int(suffix) - 1
            bodies = _iter_bodies(work_part)
            if 0 <= idx < len(bodies):
                return bodies[idx]

    if ref in _state["bodies"]:
        return _state["bodies"][ref]

    bodies = _iter_bodies(work_part)
    for body in bodies:
        name = _body_name(body).lower()
        _state["bodies"][name] = body
        if ref == name or ref in name:
            return body

    if len(bodies) == 1 and ref in {"", "body", "solid", "work"}:
        return _remember_body(bodies[0])

    raise SelectionError(f"Could not resolve body reference: {reference}")


def _point_tuple(point):
    if isinstance(point, (tuple, list)):
        return float(point[0]), float(point[1]), float(point[2])
    return float(point.X), float(point.Y), float(point.Z)


def _body_bounds(body):
    try:
        bbox = UF_SESSION.Modl.AskBoundingBox(body.Tag)
        return (
            (float(bbox[0]), float(bbox[1]), float(bbox[2])),
            (float(bbox[3]), float(bbox[4]), float(bbox[5])),
        )
    except Exception:
        pass

    points = []
    for edge in list(body.GetEdges() or []):
        try:
            pt1, pt2, _vertex_count = UF_SESSION.Modeling.AskEdgeVerts(edge.Tag)
            points.extend([_point_tuple(pt1), _point_tuple(pt2)])
        except Exception:
            continue
    if not points:
        raise SelectionError("Could not determine body bounds")

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _edge_midpoint(edge):
    pt1, pt2, _vertex_count = UF_SESSION.Modeling.AskEdgeVerts(edge.Tag)
    p1 = _point_tuple(pt1)
    p2 = _point_tuple(pt2)
    return tuple((a + b) / 2.0 for a, b in zip(p1, p2))


def _edge_z_range(edge):
    pt1, pt2, _vertex_count = UF_SESSION.Modeling.AskEdgeVerts(edge.Tag)
    p1 = _point_tuple(pt1)
    p2 = _point_tuple(pt2)
    return min(p1[2], p2[2]), max(p1[2], p2[2])


def _resolve_edges(body_reference="last", edge_reference="outer_edges"):
    body = _resolve_body(body_reference)
    edges = list(body.GetEdges() or [])
    if not edges:
        raise SelectionError(f"No edges found on body reference: {body_reference}")

    ref = str(edge_reference or "all").strip().lower().replace("-", "_")

    # Feature-scoped edge lookup check
    feature_ref_key = ref.removeprefix("feature:").strip()
    if feature_ref_key in _state.get("features", {}):
        feat_meta = _state["features"][feature_ref_key]
        if isinstance(feat_meta, dict) and "edge_tags" in feat_meta:
            target_tags = set(feat_meta["edge_tags"])
            matched = [e for e in edges if getattr(e, "Tag", None) in target_tags]
            if matched:
                return matched
            raise SelectionError(
                f"Feature '{feature_ref_key}' has no surviving edges on active body after boolean/modifying operations."
            )
        elif hasattr(feat_meta, "GetEntities"):
            feat_entities = feat_meta.GetEntities() or []
            feat_edge_tags = {e.Tag for e in feat_entities if getattr(e, "Tag", None) and "Edge" in type(e).__name__}
            matched = [e for e in edges if getattr(e, "Tag", None) in feat_edge_tags]
            if matched:
                return matched
            raise SelectionError(
                f"Feature '{feature_ref_key}' has no surviving edges on active body after boolean/modifying operations."
            )

    if ref in {"all", "all_edges", "outer", "outer_edges"}:
        return edges

    try:
        (min_x, min_y, min_z), (max_x, max_y, max_z) = _body_bounds(body)
    except Exception:
        min_x = min_y = min_z = -999999.0
        max_x = max_y = max_z = 999999.0

    def get_edge_endpoints(edge):
        try:
            pt1, pt2, _ = UF_SESSION.Modeling.AskEdgeVerts(edge.Tag)
            p1 = _point_tuple(pt1)
            p2 = _point_tuple(pt2)
            return p1, p2
        except Exception:
            return None, None

    if ref in {"x_edges", "x_aligned", "x_aligned_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2:
                dx = abs(p2[0] - p1[0])
                dy = abs(p2[1] - p1[1])
                dz = abs(p2[2] - p1[2])
                if dx > 0.001 and dy < 0.001 and dz < 0.001:
                    selected.append(edge)
        return selected

    if ref in {"y_edges", "y_aligned", "y_aligned_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2:
                dx = abs(p2[0] - p1[0])
                dy = abs(p2[1] - p1[1])
                dz = abs(p2[2] - p1[2])
                if dy > 0.001 and dx < 0.001 and dz < 0.001:
                    selected.append(edge)
        return selected

    if ref in {"z_edges", "z_aligned", "z_aligned_edges", "vertical", "vertical_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2:
                dx = abs(p2[0] - p1[0])
                dy = abs(p2[1] - p1[1])
                dz = abs(p2[2] - p1[2])
                if dz > 0.001 and dx < 0.001 and dy < 0.001:
                    selected.append(edge)
        if not selected and ref in {"vertical", "vertical_edges"}:
            for edge in edges:
                p1, p2 = get_edge_endpoints(edge)
                if p1 and p2 and abs(p2[2] - p1[2]) > 0.001:
                    selected.append(edge)
        return selected

    if ref in {"top", "top_edges", "max_z", "max_z_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[2] - max_z) < 0.001 and abs(p2[2] - max_z) < 0.001:
                selected.append(edge)
        return selected

    if ref in {"bottom", "bottom_edges", "min_z", "min_z_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[2] - min_z) < 0.001 and abs(p2[2] - min_z) < 0.001:
                selected.append(edge)
        return selected

    if ref in {"max_x", "max_x_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[0] - max_x) < 0.001 and abs(p2[0] - max_x) < 0.001:
                selected.append(edge)
        return selected

    if ref in {"min_x", "min_x_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[0] - min_x) < 0.001 and abs(p2[0] - min_x) < 0.001:
                selected.append(edge)
        return selected

    if ref in {"max_y", "max_y_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[1] - max_y) < 0.001 and abs(p2[1] - max_y) < 0.001:
                selected.append(edge)
        return selected

    if ref in {"min_y", "min_y_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[1] - min_y) < 0.001 and abs(p2[1] - min_y) < 0.001:
                selected.append(edge)
        return selected

    raise SelectionError(f"Could not resolve edge reference: {edge_reference}")


def _direction_vector(direction):
    direction = _resolve_direction(direction)
    ref = str(direction).strip().upper()
    vectors = {
        "X": (1.0, 0.0, 0.0),
        "+X": (1.0, 0.0, 0.0),
        "-X": (-1.0, 0.0, 0.0),
        "Y": (0.0, 1.0, 0.0),
        "+Y": (0.0, 1.0, 0.0),
        "-Y": (0.0, -1.0, 0.0),
        "Z": (0.0, 0.0, 1.0),
        "+Z": (0.0, 0.0, 1.0),
        "-Z": (0.0, 0.0, -1.0),
    }
    if ref not in vectors:
        raise SelectionError(f"Invalid direction: {direction}")
    return NXOpen.Vector3d(*vectors[ref])


def _plane_normal(plane):
    ref = str(plane or "XY").strip().upper()
    normals = {
        "XY": (0.0, 0.0, 1.0),
        "XZ": (0.0, 1.0, 0.0),
        "YZ": (1.0, 0.0, 0.0),
    }
    if ref not in normals:
        raise SelectionError(f"Invalid plane: {plane}")
    return NXOpen.Vector3d(*normals[ref])


def _fixed_datum_plane_type(plane):
    ref = str(plane or "XY").strip().upper()
    fixed_types = {
        "XY": NXOpen.Features.DatumPlaneBuilder.FixedType.Xy,
        "XZ": NXOpen.Features.DatumPlaneBuilder.FixedType.Zx,
        "ZX": NXOpen.Features.DatumPlaneBuilder.FixedType.Zx,
        "YZ": NXOpen.Features.DatumPlaneBuilder.FixedType.Yz,
    }
    if ref not in fixed_types:
        raise SelectionError(f"Invalid plane: {plane}")
    return fixed_types[ref]


def _create_direction(work_part, origin, direction):
    return work_part.Directions.CreateDirection(
        origin,
        direction,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )


def _create_axis(work_part, origin, direction):
    return work_part.Axes.CreateAxis(
        origin,
        direction,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )


def _vector_components(vector):
    return [float(vector.X), float(vector.Y), float(vector.Z)]


def _set_collector_rules(collector, rules):
    replace_rules = getattr(collector, "ReplaceRules", None)
    if not callable(replace_rules):
        raise SelectionError("NX collector does not support ReplaceRules")
    replace_rules(rules, False)


def fit_view():
    work_part = SESSION.Parts.Work
    if work_part is None:
        return {"ok": False, "error": "No work part is open"}
    work_part.ModelingViews.WorkView.Fit()
    return {"ok": True, "message": "View fitted"}


def probe_screenshot():
    try:
        ui = NXOpen.UI.GetUI()
        builder = ui.CreateImageExportBuilder()
        attrs = dir(builder)
        
        # Check FileFormats properties
        formats_attrs = []
        try:
            formats_attrs = dir(NXOpen.Gateway.ImageExportBuilder.FileFormats)
        except Exception as e:
            formats_attrs = [f"Error formats: {e}"]
            
        builder.Destroy()
        return {"ok": True, "message": "Probe successful", "builder_attrs": attrs, "formats_attrs": formats_attrs}
    except Exception as e:
        return {"ok": False, "error": f"Probe failed: {e}"}


def take_screenshot(output_path):
    try:
        ui = NXOpen.UI.GetUI()
        builder = ui.CreateImageExportBuilder()
        
        # Try standard Png format setting
        try:
            builder.FileFormat = NXOpen.Gateway.ImageExportBuilder.FileFormats.Png
        except Exception:
            try:
                # Fallback to index if Enum is different
                builder.FileFormat = 1 # typical PNG index
            except Exception:
                pass
                
        builder.FileName = str(output_path)
        builder.Commit()
        builder.Destroy()
        return {"ok": True, "message": f"Screenshot saved to {output_path}"}
    except Exception as e:
        try:
            builder.Destroy()
        except Exception:
            pass
        return {"ok": False, "error": f"Failed to take screenshot: {e}"}



def _update_result_files(filepath):
    try:
        import os
        abs_path = os.path.abspath(filepath)
        root = str(ROOT_DIR)
        if os.path.exists(root):
            latest_txt = os.path.join(root, "latest_nx_result.txt")
            with open(latest_txt, "w", encoding="utf-8") as f:
                f.write(abs_path)
            
            # Resolve ugs_router path dynamically
            ugs_router_path = None
            base_dir = os.environ.get("UGII_BASE_DIR")
            if base_dir:
                base_path = Path(base_dir)
                candidates = [
                    base_path / "NXBIN" / "ugs_router.exe",
                    base_path / "UGII" / "ugs_router.exe",
                ]
                ugs_router_path = next((c for c in candidates if c.exists()), None)
            if not ugs_router_path:
                ugs_router_path = Path(r"C:\Program Files\Siemens\NX2206\NXBIN\ugs_router.exe")

            cmd_path = os.path.join(root, "open_current_nx_result.cmd")
            with open(cmd_path, "w", encoding="utf-8") as f:
                f.write(f'@echo off\nstart "" "{ugs_router_path}" -ug -use_file_dir "{abs_path}"\n')
            vbs_path = os.path.join(root, "open_latest_nx_result.vbs")
            with open(vbs_path, "w", encoding="utf-8") as f:
                f.write(f'Set shell = CreateObject("WScript.Shell")\nshell.Run """{ugs_router_path}"" -ug -use_file_dir ""{abs_path}""", 0, False\n')
    except Exception as e:
        sys.stderr.write(f"[WARN] _update_result_files failed: {e}\n")


def create_part(filename):
    global _counters_seeded
    SESSION.Parts.NewDisplay(
        filename,
        NXOpen.Part.Units.Millimeters,
    )
    work_part = SESSION.Parts.Work
    if work_part is None:
        return {"ok": False, "error": "Part created but work part not set"}
    # Reset and re-seed counters for the new part
    _expression_counters.clear()
    _instance_counters.clear()
    _counters_seeded = False
    _seed_counters_from_part(work_part)
    _counters_seeded = True
    fit_view()
    import os
    filepath = os.path.abspath(filename)
    _update_result_files(filepath)
    return {"ok": True, "message": f"Created and displayed: {filename}", "filepath": filepath}


def open_part(filepath):
    global _counters_seeded
    import os
    target_abs = os.path.abspath(filepath).lower()

    # Check if the part is already open in the session
    existing_part = None
    try:
        for part in SESSION.Parts:
            try:
                if os.path.abspath(part.FullPath).lower() == target_abs:
                    existing_part = part
                    break
            except Exception:
                pass
    except Exception:
        pass

    if existing_part is not None:
        try:
            SESSION.Parts.SetWork(existing_part)
        except Exception:
            pass
        try:
            existing_part.Display()
        except Exception:
            pass
        _expression_counters.clear()
        _instance_counters.clear()
        _counters_seeded = False
        _seed_counters_from_part(existing_part)
        _counters_seeded = True
        fit_view()
        _update_result_files(target_abs)
        return {"ok": True, "message": f"Part already open, activated: {filepath}", "filepath": target_abs}

    try:
        try:
            SESSION.Parts.OpenDisplay(filepath)
        except Exception:
            SESSION.Parts.Open(filepath)
    except Exception as e:
        return {"ok": False, "error": f"Failed to open part '{filepath}': {e}"}

    # Reset and re-seed counters for the opened part
    _expression_counters.clear()
    _instance_counters.clear()
    _counters_seeded = False
    work_part = SESSION.Parts.Work
    if work_part is not None:
        _seed_counters_from_part(work_part)
        _counters_seeded = True
    fit_view()
    actual_path = os.path.abspath(work_part.FullPath if work_part else filepath)
    _update_result_files(actual_path)
    return {"ok": True, "message": f"Opened and displayed: {filepath}", "filepath": actual_path}


def save_part():
    work_part = SESSION.Parts.Work
    if work_part is None:
        return {"ok": False, "error": "No work part is open"}
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    import os
    filepath = os.path.abspath(work_part.FullPath)
    _update_result_files(filepath)
    return {"ok": True, "message": "Saved", "filepath": filepath}


def create_sketch(plane="XY"):
    global ACTIVE_SKETCH_PLANE

    plane = plane.upper()
    if plane not in {"XY", "XZ", "YZ"}:
        return {"ok": False, "error": f"Invalid sketch plane: {plane}"}

    _ensure_work_part()

    ACTIVE_SKETCH_PLANE = plane
    _state["last_curves"] = []
    _state["active_sketch"] = None
    _state["profile_start_index"] = len(_state.get("curve_history", []))
    return {"ok": True, "message": f"Sketch created on {plane} plane"}


def _point_on_active_plane(x, y):
    ox, oy, oz = _state.get("sketch_origin", [0.0, 0.0, 0.0])
    angle_deg = _state.get("sketch_rotation", 0.0)
    
    if ACTIVE_SKETCH_PLANE == "XY":
        angle_rad = math.radians(angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        x_rot = x * cos_a - y * sin_a
        y_rot = x * sin_a + y * cos_a
        return NXOpen.Point3d(x_rot + ox, y_rot + oy, oz)
    if ACTIVE_SKETCH_PLANE == "XZ":
        return NXOpen.Point3d(x + ox, oy, y + oz)
    return NXOpen.Point3d(ox, x + oy, y + oz)


def draw_rectangle(x, y, width, height):
    x = float(x)
    y = float(y)
    width = float(width)
    height = float(height)

    part = _ensure_work_part()

    corners = [
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
        (x, y),
    ]
    lines = []
    active_sketch = _state.get("active_sketch")
    for index in range(4):
        line = part.Curves.CreateLine(
            _point_on_active_plane(corners[index][0], corners[index][1]),
            _point_on_active_plane(corners[index + 1][0], corners[index + 1][1]),
        )
        lines.append(line)
        if active_sketch is not None:
            try:
                active_sketch.AddGeometry(line, NXOpen.Sketch.ConstraintClass.Geometrical)
            except Exception:
                try:
                    active_sketch.AddGeometry(line)
                except Exception:
                    pass
    _state.setdefault("last_curves", []).extend(lines)
    fit_view()

    return {
        "ok": True,
        "message": f"Rectangle {x},{y} size {width}x{height}",
    }


def _normal_for_plane(plane_name):
    plane_name = str(plane_name).upper()
    if plane_name == "XY":
        return NXOpen.Vector3d(0.0, 0.0, 1.0)
    if plane_name == "XZ":
        return NXOpen.Vector3d(0.0, 1.0, 0.0)
    return NXOpen.Vector3d(1.0, 0.0, 0.0)


def _normal_for_active_plane():
    return _normal_for_plane(ACTIVE_SKETCH_PLANE)


def draw_circle(cx, cy, radius):
    cx = _eval_val(cx)
    cy = _eval_val(cy)
    radius = _eval_val(radius)

    if radius <= 0.0:
        return {"ok": False, "error": "Circle radius must be positive"}

    part = _ensure_work_part()
    
    # Calculate rotated orientation vectors:
    angle_deg = _state.get("sketch_rotation", 0.0)
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    x_dir = NXOpen.Vector3d(cos_a, sin_a, 0.0)
    y_dir = NXOpen.Vector3d(-sin_a, cos_a, 0.0)

    circle = part.Curves.CreateArc(
        _point_on_active_plane(cx, cy),
        x_dir,
        y_dir,
        radius,
        0.0,
        6.283185307179586,
    )
    active_sketch = _state.get("active_sketch")
    if active_sketch is not None:
        try:
            active_sketch.AddGeometry(circle, NXOpen.Sketch.ConstraintClass.Geometrical)
        except Exception:
            try:
                active_sketch.AddGeometry(circle)
            except Exception:
                pass
    _state.setdefault("last_curves", []).append(circle)
    fit_view()
    return {"ok": True, "message": f"Circle {cx},{cy} R={radius}"}


def draw_line(x1, y1, x2, y2):
    x1 = _eval_val(x1)
    y1 = _eval_val(y1)
    x2 = _eval_val(x2)
    y2 = _eval_val(y2)

    part = _ensure_work_part()
    line = part.Curves.CreateLine(
        _point_on_active_plane(x1, y1),
        _point_on_active_plane(x2, y2),
    )
    active_sketch = _state.get("active_sketch")
    if active_sketch is not None:
        try:
            active_sketch.AddGeometry(line, NXOpen.Sketch.ConstraintClass.Geometrical)
        except Exception:
            try:
                active_sketch.AddGeometry(line)
            except Exception:
                pass
    _state.setdefault("last_curves", []).append(line)
    fit_view()
    return {"ok": True, "message": f"Line {x1},{y1} to {x2},{y2}"}


def draw_arc(cx, cy, radius, start_angle, end_angle):
    cx = _eval_val(cx)
    cy = _eval_val(cy)
    radius = _eval_val(radius)
    start_angle = _eval_val(start_angle)
    end_angle = _eval_val(end_angle)

    if radius <= 0.0:
        return {"ok": False, "error": "Arc radius must be positive"}

    part = _ensure_work_part()
    
    # Calculate rotated orientation vectors:
    angle_deg = _state.get("sketch_rotation", 0.0)
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    x_dir = NXOpen.Vector3d(cos_a, sin_a, 0.0)
    y_dir = NXOpen.Vector3d(-sin_a, cos_a, 0.0)

    rot_val = _state.get("sketch_rotation", 0.0)
    arc = part.Curves.CreateArc(
        _point_on_active_plane(cx, cy),
        x_dir,
        y_dir,
        radius,
        math.radians(start_angle + rot_val),
        math.radians(end_angle + rot_val),
    )
    active_sketch = _state.get("active_sketch")
    if active_sketch is not None:
        try:
            active_sketch.AddGeometry(arc, NXOpen.Sketch.ConstraintClass.Geometrical)
        except Exception:
            try:
                active_sketch.AddGeometry(arc)
            except Exception:
                pass
    _state.setdefault("last_curves", []).append(arc)
    fit_view()
    return {"ok": True, "message": f"Arc {cx},{cy} R={radius} {start_angle} to {end_angle} deg"}


def draw_cylinder_profile(outer_radius, inner_radius):
    if inner_radius <= 0.0 or outer_radius <= 0.0:
        return {"ok": False, "error": "Radii must be positive"}
    if inner_radius >= outer_radius:
        return {"ok": False, "error": "Inner radius must be smaller than outer radius"}

    outer = _create_xy_arc(outer_radius)
    inner = _create_xy_arc(inner_radius)
    _state["last_curves"] = [outer, inner]
    _state.setdefault("curve_history", []).extend([outer, inner])
    return {
        "ok": True,
        "message": f"Cylinder profile outer R={outer_radius} inner R={inner_radius}",
    }


def draw_spline(points, degree=3, closed=False, plane="active"):
    """
    Draw a Studio Spline through 2D active-sketch-plane or 3D world points.
    Accepts point list as array pairs [[x, y], ...] or dict objects [{"x": ..., "y": ...}, ...].
    """
    degree = int(degree)
    closed = bool(closed)
    if degree < 1 or degree > 5:
        return {"ok": False, "error": "Spline degree must be between 1 and 5"}
    if not isinstance(points, (list, tuple)) or len(points) < (degree + 1):
        return {"ok": False, "error": f"Studio Spline (degree {degree}) requires at least {degree + 1} points"}

    parsed_points = []
    has_3d_points = False
    for idx, p in enumerate(points):
        if isinstance(p, dict):
            p_clean = {str(k).lower(): v for k, v in p.items()}
            if "x" not in p_clean or "y" not in p_clean:
                return {"ok": False, "error": f"point {idx} dict must contain 'x' and 'y' keys"}
            try:
                x_val = _eval_val(p_clean["x"])
                y_val = _eval_val(p_clean["y"])
                z_val = _eval_val(p_clean["z"]) if "z" in p_clean else None
            except Exception as exc:
                return {"ok": False, "error": f"point {idx} contains non-numeric coordinate: {exc}"}
            if z_val is not None:
                has_3d_points = True
                parsed_points.append([x_val, y_val, z_val])
            else:
                parsed_points.append([x_val, y_val])
        elif isinstance(p, (list, tuple)):
            if len(p) not in (2, 3):
                return {"ok": False, "error": f"point {idx} must have 2 or 3 coordinates, got {len(p)}"}
            try:
                coords = [_eval_val(val) for val in p]
            except Exception as exc:
                return {"ok": False, "error": f"point {idx} contains non-numeric coordinate: {exc}"}
            if len(coords) == 3:
                has_3d_points = True
            parsed_points.append(coords)
        else:
            return {"ok": False, "error": f"point {idx} must be a list/tuple or dict with x/y keys"}

    if plane != "active":
        return {"ok": False, "error": f"Unsupported plane '{plane}' — plane must be 'active'"}

    part = _ensure_work_part()
    studio_points = []
    for p in parsed_points:
        if len(p) == 3:
            pt3d = NXOpen.Point3d(p[0], p[1], p[2])
        else:
            pt3d = _point_on_active_plane(p[0], p[1])
        studio_points.append(part.Points.CreatePoint(pt3d))

    builder = part.Features.CreateStudioSplineBuilderEx(NXOpen.Features.Feature.Null)
    try:
        builder.Degree = degree
        builder.IsPeriodic = closed

        for pt in studio_points:
            gcd = builder.ConstraintManager.CreateGeometricConstraintData()
            gcd.Point = pt
            builder.ConstraintManager.Append(gcd)

        feature = builder.CommitFeature()
        _remember_feature(feature)
        spline_curve = feature.GetEntities()[0]
    finally:
        builder.Destroy()

    active_sketch = _state.get("active_sketch")
    if active_sketch is not None and not has_3d_points and hasattr(active_sketch, "AddGeometry"):
        try:
            active_sketch.AddGeometry(spline_curve, NXOpen.Sketch.ConstraintClass.Geometrical)
        except Exception:
            try:
                active_sketch.AddGeometry(spline_curve)
            except Exception:
                pass

    _state["last_curves"] = [spline_curve]
    _state.setdefault("curve_history", []).append(spline_curve)
    _state.setdefault("curve_metadata", {})[str(spline_curve.Tag)] = {
        "points": parsed_points,
        "degree": degree,
        "closed": closed,
        "plane": plane,
    }

    fit_view()
    return {
        "ok": True,
        "message": f"Studio spline through {len(parsed_points)} points (degree {degree}, closed={closed})",
        "curve_count": 1,
    }


def _resolve_single_curve(reference, require_spline_metadata=False):
    """
    Resolve a curve reference ('last', 'previous', Tag integer, or index) to a single curve object.
    When require_spline_metadata is True, filters history for curves present in _state['curve_metadata'].
    """
    history = list(_state.get("curve_history", []))

    if require_spline_metadata:
        metadata_map = _state.get("curve_metadata", {})
        valid = [c for c in history if str(getattr(c, "Tag", "")) in metadata_map]
        if valid:
            history = valid

    if not history:
        last_curves = _state.get("last_curves", [])
        if require_spline_metadata:
            metadata_map = _state.get("curve_metadata", {})
            last_curves = [c for c in last_curves if str(getattr(c, "Tag", "")) in metadata_map]
        if len(last_curves) == 1:
            return last_curves[0]

    if not history:
        raise SelectionError("No curve available in session history")

    ref_str = str(reference).strip().lower()
    if ref_str == "last":
        return history[-1]
    elif ref_str in ("previous", "prev"):
        if len(history) >= 2:
            return history[-2]
        return history[0]

    try:
        tag_val = int(ref_str)
        for c in history:
            if getattr(c, "Tag", None) == tag_val:
                return c
    except ValueError:
        pass

    raise SelectionError(f"Curve reference '{reference}' did not resolve to a valid curve")


def _resolve_curve_group(reference="last_profile"):
    """
    Resolve curve reference to a list of curves added in the active sketch profile.
    If reference is 'last', 'last_profile', or 'profile', returns all curves added
    since the most recent create_sketch() call.
    If exactly 1 curve exists, or if a specific single curve reference/tag is requested,
    returns a list containing that curve.
    """
    ref_str = str(reference or "last_profile").strip().lower()
    history = list(_state.get("curve_history", []))

    if ref_str in {"last", "last_profile", "profile", "all"}:
        start_idx = _state.get("profile_start_index", 0)
        profile_curves = history[start_idx:]
        if not profile_curves:
            profile_curves = list(_state.get("last_curves", []))
        if profile_curves:
            return profile_curves

    if not history:
        last_curves = _state.get("last_curves", [])
        if last_curves:
            return last_curves
        raise SelectionError("No curve available in session history")

    try:
        single = _resolve_single_curve(reference)
        return [single]
    except Exception:
        start_idx = _state.get("profile_start_index", 0)
        profile_curves = history[start_idx:]
        if profile_curves:
            return profile_curves
        return history


def offset_curve(curve_reference="last", start_width=5.0, end_width=7.0, side="auto"):
    start_width = float(start_width)
    end_width = float(end_width)

    source_curve = _resolve_single_curve(curve_reference, require_spline_metadata=True)
    metadata = _state.get("curve_metadata", {}).get(str(source_curve.Tag))
    if not metadata:
        raise SelectionError("Source curve metadata not found — offset_curve requires a draw_spline curve")

    pts = metadata["points"]
    degree = metadata.get("degree", 3)
    n_pts = len(pts)

    offset_sign = -1.0 if str(side).strip().lower() == "right" else 1.0

    offset_points = []
    for i, p in enumerate(pts):
        t = i / max(n_pts - 1, 1)
        w = start_width + t * (end_width - start_width)

        if i == 0:
            dx = pts[1][0] - pts[0][0]
            dy = pts[1][1] - pts[0][1]
        elif i == n_pts - 1:
            dx = pts[-1][0] - pts[-2][0]
            dy = pts[-1][1] - pts[-2][1]
        else:
            dx = pts[i + 1][0] - pts[i - 1][0]
            dy = pts[i + 1][1] - pts[i - 1][1]

        length = math.hypot(dx, dy)
        if length < 1e-6:
            nx_val, ny_val = 0.0, 1.0
        else:
            nx_val = -dy / length
            ny_val = dx / length

        px = p[0] + offset_sign * w * nx_val
        py = p[1] + offset_sign * w * ny_val
        if len(p) == 3:
            offset_points.append([px, py, p[2]])
        else:
            offset_points.append([px, py])

    res = draw_spline(points=offset_points, degree=degree, closed=False, plane=metadata.get("plane", "active"))
    if not res.get("ok"):
        return res

    offset_spline = _state["last_curves"][0]
    return {
        "ok": True,
        "message": f"Variable offset spline {start_width}mm to {end_width}mm on {side} side",
        "curve_count": 1,
    }


def close_curve_region(curve1="last", curve2="previous", method="tangent_lines"):
    c1 = _resolve_single_curve(curve1, require_spline_metadata=True)
    c2 = _resolve_single_curve(curve2, require_spline_metadata=True)

    part = _ensure_work_part()

    m1 = _state.get("curve_metadata", {}).get(str(c1.Tag), {})
    m2 = _state.get("curve_metadata", {}).get(str(c2.Tag), {})
    pts1 = m1.get("points", [])
    pts2 = m2.get("points", [])

    if len(pts1) >= 2 and len(pts2) >= 2:
        p1_start = _point_on_active_plane(pts1[0][0], pts1[0][1])
        p1_end = _point_on_active_plane(pts1[-1][0], pts1[-1][1])
        p2_start = _point_on_active_plane(pts2[0][0], pts2[0][1])
        p2_end = _point_on_active_plane(pts2[-1][0], pts2[-1][1])
    else:
        p1_start = c1.StartPoint
        p1_end = c1.EndPoint
        p2_start = c2.StartPoint
        p2_end = c2.EndPoint

    start_connector = part.Curves.CreateLine(p1_start, p2_start)
    end_connector = part.Curves.CreateLine(p1_end, p2_end)

    active_sketch = _state.get("active_sketch")
    if active_sketch is not None and hasattr(active_sketch, "AddGeometry"):
        for conn in (start_connector, end_connector):
            try:
                active_sketch.AddGeometry(conn, NXOpen.Sketch.ConstraintClass.Geometrical)
            except Exception:
                try:
                    active_sketch.AddGeometry(conn)
                except Exception:
                    pass

    _state["last_curves"] = [c1, end_connector, c2, start_connector]
    _state.setdefault("curve_history", []).extend([end_connector, start_connector])
    fit_view()
    return {
        "ok": True,
        "message": f"Closed region from two curves using {method}",
        "curve_count": 4,
    }


def _create_xy_arc(radius):
    arc = NXOpen.UF.Curve.Arc()
    arc.StartAngle = 0.0
    arc.EndAngle = 6.283185307179586
    arc.ArcCenter.append(0.0)
    arc.ArcCenter.append(0.0)
    arc.ArcCenter.append(0.0)
    arc.Radius = float(radius)
    wcs_tag = UF_SESSION.Csys.AskWcs()
    arc.MatrixTag = UF_SESSION.Csys.AskMatrixOfObject(wcs_tag)
    arc_tag = UF_SESSION.Curve.CreateArc(arc)
    return NXOpen.TaggedObjectManager().GetTaggedObject(arc_tag)


def draw_rounded_rectangle(arm_length, arm_width, end_radius, cx_left=None, cy=0.0, z=None):
    """
    Draw a closed rounded-rectangle (stadium/oblong) profile.

    The profile has:
      - Left rounded end arc centered at (cx_left, cy, z_plane)
      - Right rounded end arc centered at (cx_left + arm_length - 2*end_radius, cy, z_plane)

    Parameters:
      arm_length (float): Total tip-to-tip length of the profile
      arm_width  (float): Total width (= 2 * end_radius for tangent arcs)
      end_radius (float): Radius of the rounded end semicircles
      cx_left    (float): X of the left arc center. Defaults to 0.0.
      cy         (float): Y of both arc centers. Defaults to 0.0.
      z          (float): Z plane for the profile. Defaults to 0.0.

    Curves are appended to _state["last_curves"].
    Returns ok dict with number of curves added.
    """
    arm_length = _eval_val(arm_length)
    arm_width  = _eval_val(arm_width)
    end_radius = _eval_val(end_radius)
    if cx_left is None:
        cx_left = 0.0
    cx_left = _eval_val(cx_left)
    cy      = _eval_val(cy)
    if z is None:
        z_val = 0.0
    else:
        z_val = _eval_val(z)

    cx_right = cx_left + (arm_length - 2.0 * end_radius)
    half_w   = arm_width / 2.0

    part   = _ensure_work_part()
    
    # Rotated local coordinate vectors:
    angle_deg = _state.get("sketch_rotation", 0.0)
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    x_dir = NXOpen.Vector3d(cos_a, sin_a, 0.0)
    y_dir = NXOpen.Vector3d(-sin_a, cos_a, 0.0)

    curves = []

    # Left arc: 90° → 270° (left-facing semicircle, CCW)
    p_left = _point_on_active_plane(cx_left, cy)
    curves.append(part.Curves.CreateArc(
        p_left, x_dir, y_dir, end_radius,
        math.radians(90.0), math.radians(270.0)
    ))

    # Bottom line: left_bottom → right_bottom
    p1 = _point_on_active_plane(cx_left,  cy - half_w)
    p2 = _point_on_active_plane(cx_right, cy - half_w)
    curves.append(part.Curves.CreateLine(p1, p2))

    # Right arc: 270° → 90° (right-facing semicircle, CCW)
    p_right = _point_on_active_plane(cx_right, cy)
    curves.append(part.Curves.CreateArc(
        p_right, x_dir, y_dir, end_radius,
        math.radians(270.0), math.radians(90.0)
    ))

    # Top line: right_top → left_top  (closes the loop)
    p3 = _point_on_active_plane(cx_right, cy + half_w)
    p4 = _point_on_active_plane(cx_left,  cy + half_w)
    curves.append(part.Curves.CreateLine(p3, p4))

    active_sketch = _state.get("active_sketch")
    if active_sketch is not None:
        for curve in curves:
            try:
                active_sketch.AddGeometry(curve, NXOpen.Sketch.ConstraintClass.Geometrical)
            except Exception:
                try:
                    active_sketch.AddGeometry(curve)
                except Exception:
                    pass

    _state.setdefault("last_curves", []).extend(curves)
    fit_view()
    return {
        "ok": True,
        "message": (
            f"Rounded rectangle: L={arm_length} W={arm_width} R={end_radius} "
            f"left_arc=({cx_left},{cy}) right_arc=({cx_right},{cy}) z={z_val}"
        ),
    }


def create_offset_linkage_arm(output_path=None):
    """
    Create a fully parametric offset linkage arm.

    Part description:
      Two identical rounded-end arms connected by a vertical cylindrical spacer.
      The upper arm is rotated 180° relative to the lower arm.

    Named expressions created:
      ARM_LENGTH=90, ARM_WIDTH=24, ARM_THICK=8, END_RADIUS=12,
      HOLE_DIA=10, HOLE_OFFSET=12, CYLINDER_DIA=22, CYLINDER_HEIGHT=55,
      BLEND_RADIUS=2, CHAMFER_OFFSET=0.5

    Coordinate origin = left hole of lower arm = cylinder axis at Z=0.

    If output_path is None, uses the current work part.
    """
    import os as _os

    # ---- Parameters ----
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

    # ---- Create/get part ----
    if output_path:
        create_part(output_path)
    work_part = _ensure_work_part()

    # ---- Create NX Expressions for Base Inputs ----
    prefix = _next_instance_prefix("ARM")
    for name, val in PARAMS.items():
        _create_input_expression(work_part, f"{prefix}_{name}", val)

    # ---- Create NX Expressions for Derived/Calculated parameters ----
    _create_formula_expression(work_part, f"{prefix}_ARM_SPAN", f"{prefix}_ARM_LENGTH - 2.0 * {prefix}_END_RADIUS")
    _create_formula_expression(work_part, f"{prefix}_CYL_R", f"{prefix}_CYLINDER_DIA / 2.0")

    _create_formula_expression(work_part, f"{prefix}_LOWER_LEFT_ARC_X", f"-{prefix}_HOLE_OFFSET")
    _create_formula_expression(work_part, f"{prefix}_LOWER_RIGHT_ARC_X", f"{prefix}_LOWER_LEFT_ARC_X + {prefix}_ARM_SPAN")
    _create_formula_expression(work_part, f"{prefix}_LOWER_LEFT_HOLE_X", "0.0")
    _create_formula_expression(work_part, f"{prefix}_LOWER_RIGHT_HOLE_X", f"{prefix}_ARM_SPAN - 2.0 * {prefix}_HOLE_OFFSET")

    _create_formula_expression(work_part, f"{prefix}_UPPER_RIGHT_ARC_X", f"{prefix}_HOLE_OFFSET")
    _create_formula_expression(work_part, f"{prefix}_UPPER_LEFT_ARC_X", f"{prefix}_UPPER_RIGHT_ARC_X - {prefix}_ARM_SPAN")
    _create_formula_expression(work_part, f"{prefix}_UPPER_RIGHT_HOLE_X", "0.0")
    _create_formula_expression(work_part, f"{prefix}_UPPER_LEFT_HOLE_X", f"- ({prefix}_ARM_SPAN - 2.0 * {prefix}_HOLE_OFFSET)")

    _create_formula_expression(work_part, f"{prefix}_Z_LOWER_TOP", f"{prefix}_ARM_THICK")
    _create_formula_expression(work_part, f"{prefix}_Z_CYL_TOP", f"{prefix}_ARM_THICK + {prefix}_CYLINDER_HEIGHT")
    _create_formula_expression(work_part, f"{prefix}_Z_UPPER_TOP", f"{prefix}_ARM_THICK + {prefix}_CYLINDER_HEIGHT + {prefix}_ARM_THICK")

    # Read float values back from NX expressions for geometry creation calls that require raw numbers
    ARM_L   = work_part.Expressions.FindObject(f"{prefix}_ARM_LENGTH").Value
    ARM_W   = work_part.Expressions.FindObject(f"{prefix}_ARM_WIDTH").Value
    ARM_T   = work_part.Expressions.FindObject(f"{prefix}_ARM_THICK").Value
    END_R   = work_part.Expressions.FindObject(f"{prefix}_END_RADIUS").Value
    HOLE_D  = work_part.Expressions.FindObject(f"{prefix}_HOLE_DIA").Value
    HOLE_O  = work_part.Expressions.FindObject(f"{prefix}_HOLE_OFFSET").Value
    CYL_D   = work_part.Expressions.FindObject(f"{prefix}_CYLINDER_DIA").Value
    CYL_H   = work_part.Expressions.FindObject(f"{prefix}_CYLINDER_HEIGHT").Value
    BLEND_R = work_part.Expressions.FindObject(f"{prefix}_BLEND_RADIUS").Value
    CHAM_O  = work_part.Expressions.FindObject(f"{prefix}_CHAMFER_OFFSET").Value

    ARM_SPAN = work_part.Expressions.FindObject(f"{prefix}_ARM_SPAN").Value
    CYL_R    = work_part.Expressions.FindObject(f"{prefix}_CYL_R").Value

    LOWER_LEFT_ARC_X   = work_part.Expressions.FindObject(f"{prefix}_LOWER_LEFT_ARC_X").Value
    LOWER_RIGHT_ARC_X  = work_part.Expressions.FindObject(f"{prefix}_LOWER_RIGHT_ARC_X").Value
    LOWER_LEFT_HOLE_X  = 0.0
    LOWER_RIGHT_HOLE_X = work_part.Expressions.FindObject(f"{prefix}_LOWER_RIGHT_HOLE_X").Value

    UPPER_RIGHT_ARC_X  = work_part.Expressions.FindObject(f"{prefix}_UPPER_RIGHT_ARC_X").Value
    UPPER_LEFT_ARC_X   = work_part.Expressions.FindObject(f"{prefix}_UPPER_LEFT_ARC_X").Value
    UPPER_RIGHT_HOLE_X = 0.0
    UPPER_LEFT_HOLE_X  = work_part.Expressions.FindObject(f"{prefix}_UPPER_LEFT_HOLE_X").Value

    Z_LOWER_TOP = work_part.Expressions.FindObject(f"{prefix}_Z_LOWER_TOP").Value
    Z_CYL_TOP   = work_part.Expressions.FindObject(f"{prefix}_Z_CYL_TOP").Value
    Z_UPPER_TOP = work_part.Expressions.FindObject(f"{prefix}_Z_UPPER_TOP").Value

    def _extrude_profile(curves, start_val, end_val, bool_type=None, bool_target=None):
        """Extrude curves in +Z from start_val to end_val."""
        work_part = SESSION.Parts.Work
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
            origin = NXOpen.Point3d(0.0, 0.0, 0.0)
            nx_dir = work_part.Directions.CreateDirection(
                origin, NXOpen.Vector3d(0.0, 0.0, 1.0),
                NXOpen.SmartObject.UpdateOption.WithinModeling,
            )
            builder.Direction = nx_dir
            builder.Limits.StartExtend.Value.RightHandSide = str(start_val)
            builder.Limits.EndExtend.Value.RightHandSide = str(end_val)
            if bool_type is not None:
                builder.BooleanOperation.Type = bool_type
                if bool_target is not None:
                    try:
                        builder.BooleanOperation.SetTarget(bool_target)
                    except Exception:
                        pass
            else:
                builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
            feat = builder.CommitFeature()
            _remember_feature(feat)
            return feat
        finally:
            builder.Destroy()

    def _get_body():
        bodies = list(SESSION.Parts.Work.Bodies)
        return bodies[-1] if bodies else None

    def _subtract_hole(cx, cy, z_top, diameter, depth):
        """Create a hole by cylinder-subtract."""
        work_part = SESSION.Parts.Work
        target_body = _get_body()
        d_name = _create_input_expression(work_part, f"{prefix}_HOLE_D", diameter)
        depth_name = _create_input_expression(work_part, f"{prefix}_HOLE_DEPTH", depth)
        return _subtract_cylinder_hole_parametric(target_body, cx, cy, z_top, d_name, depth_name, "-Z")

    # ========== Lower Arm (F3 + F4) ==========
    global ACTIVE_SKETCH_PLANE
    ACTIVE_SKETCH_PLANE = "XY"
    _state["last_curves"] = []

    r = draw_rounded_rectangle(ARM_L, ARM_W, END_R, cx_left=LOWER_LEFT_ARC_X, cy=0.0, z=0.0)
    lower_curves = list(_state["last_curves"])
    _state["last_curves"] = []
    if not lower_curves:
        return {"ok": False, "error": "Failed to draw lower arm profile"}

    _extrude_profile(lower_curves, "0.0", f"{prefix}_ARM_THICK")
    main_body = _get_body()

    # ========== Cylinder Spacer (F7 + F8) ==========
    _state["last_curves"] = []
    x_dir = NXOpen.Vector3d(1.0, 0.0, 0.0)
    y_dir = NXOpen.Vector3d(0.0, 1.0, 0.0)
    cyl_circle = work_part.Curves.CreateArc(
        NXOpen.Point3d(0.0, 0.0, 0.0), x_dir, y_dir, CYL_R, 0.0, 2.0 * math.pi
    )
    _state["last_curves"] = [cyl_circle]
    cyl_curves = [cyl_circle]
    _state["last_curves"] = []

    builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rule = work_part.ScRuleFactory.CreateRuleCurveDumb([cyl_circle])
        section.AddToSection(
            [rule], cyl_circle,
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False,
        )
        builder.Section = section
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        builder.Direction = work_part.Directions.CreateDirection(
            origin, NXOpen.Vector3d(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Limits.StartExtend.Value.RightHandSide = f"{prefix}_ARM_THICK"
        builder.Limits.EndExtend.Value.RightHandSide = f"{prefix}_Z_CYL_TOP"
        cyl_feat = builder.CommitFeature()
        _remember_feature(cyl_feat)
    finally:
        builder.Destroy()
    cyl_body = _get_body()
    boolean_unite(_body_name(main_body), _body_name(cyl_body))
    main_body = _get_body()

    # ========== Upper Arm (F10 + F12) ==========
    _state["last_curves"] = []

    # Upper arm: right arc at UPPER_RIGHT_ARC_X=12, going left
    upper_curves_raw = []
    norm = NXOpen.Vector3d(0.0, 0.0, 1.0)
    # Right arc: center=(12, 0, Z_CYL_TOP), 270°→90°
    x_dir = NXOpen.Vector3d(1.0, 0.0, 0.0)
    y_dir = NXOpen.Vector3d(0.0, 1.0, 0.0)
    upper_curves_raw.append(work_part.Curves.CreateArc(
        NXOpen.Point3d(UPPER_RIGHT_ARC_X, 0.0, Z_CYL_TOP), x_dir, y_dir, END_R,
        math.radians(270.0), math.radians(90.0)
    ))
    # Top line: (12, 12, Z_CYL_TOP) → (-54, 12, Z_CYL_TOP)
    upper_curves_raw.append(work_part.Curves.CreateLine(
        NXOpen.Point3d(UPPER_RIGHT_ARC_X, ARM_W/2.0, Z_CYL_TOP),
        NXOpen.Point3d(UPPER_LEFT_ARC_X,  ARM_W/2.0, Z_CYL_TOP)
    ))
    # Left arc: center=(-54, 0, Z_CYL_TOP), 90°→270°
    x_dir = NXOpen.Vector3d(1.0, 0.0, 0.0)
    y_dir = NXOpen.Vector3d(0.0, 1.0, 0.0)
    upper_curves_raw.append(work_part.Curves.CreateArc(
        NXOpen.Point3d(UPPER_LEFT_ARC_X, 0.0, Z_CYL_TOP), x_dir, y_dir, END_R,
        math.radians(90.0), math.radians(270.0)
    ))
    # Bottom line: (-54, -12, Z_CYL_TOP) → (12, -12, Z_CYL_TOP)
    upper_curves_raw.append(work_part.Curves.CreateLine(
        NXOpen.Point3d(UPPER_LEFT_ARC_X,  -ARM_W/2.0, Z_CYL_TOP),
        NXOpen.Point3d(UPPER_RIGHT_ARC_X, -ARM_W/2.0, Z_CYL_TOP)
    ))

    # Extrude from Z_CYL_TOP to Z_UPPER_TOP
    _extrude_profile(
        upper_curves_raw, f"{prefix}_Z_CYL_TOP", f"{prefix}_Z_UPPER_TOP"
    )
    upper_arm_body = _get_body()
    boolean_unite(_body_name(main_body), _body_name(upper_arm_body))
    main_body = _get_body()

    # ========== Lower Arm Holes (F5) ==========
    _subtract_hole(LOWER_LEFT_HOLE_X,  0.0, Z_LOWER_TOP, HOLE_D, ARM_T)
    main_body = _get_body()
    _subtract_hole(LOWER_RIGHT_HOLE_X, 0.0, Z_LOWER_TOP, HOLE_D, ARM_T)
    main_body = _get_body()

    # ========== Upper Arm Holes (F13) ==========
    _subtract_hole(UPPER_RIGHT_HOLE_X, 0.0, Z_UPPER_TOP, HOLE_D, ARM_T)
    main_body = _get_body()
    _subtract_hole(UPPER_LEFT_HOLE_X,  0.0, Z_UPPER_TOP, HOLE_D, ARM_T)
    main_body = _get_body()

    # ========== Edge Blend (F14) ==========
    warnings = []
    try:
        add_fillet(BLEND_R, "last", "outer_edges")
        main_body = _get_body()
    except Exception as e:
        sys.stderr.write(f"[WARN] Edge blend in create_offset_linkage_arm failed: {e}\n")
        warnings.append(f"fillet failed ({e})")

    # ========== Chamfer (F15) ==========
    try:
        add_chamfer(CHAM_O, "last", "top_edges")
        main_body = _get_body()
    except Exception as e:
        sys.stderr.write(f"[WARN] Chamfer in create_offset_linkage_arm failed: {e}\n")
        warnings.append(f"chamfer failed ({e})")

    # ========== Fit view ==========
    fit_view()

    warn_str = f" (warnings: {', '.join(warnings)})" if warnings else ""
    return {
        "ok": True,
        "message": (
            f"Offset linkage arm created: "
            f"ARM_LENGTH={ARM_L} ARM_WIDTH={ARM_W} ARM_THICK={ARM_T} "
            f"END_RADIUS={END_R} HOLE_DIA={HOLE_D} HOLE_OFFSET={HOLE_O} "
            f"CYLINDER_DIA={CYL_D} CYLINDER_HEIGHT={CYL_H} "
            f"Total height={Z_UPPER_TOP}mm{warn_str}"
        ),
    }


def extrude(distance, start=0, direction="auto"):
    work_part = SESSION.Parts.Work
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No curves to extrude"}

    builder = work_part.Features.CreateExtrudeBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        section = work_part.Sections.CreateSection(
            float(0.0095), float(0.01), float(0.5)
        )
        rules = []
        for curve in curves:
            rule = SESSION.Parts.Work.ScRuleFactory.CreateRuleCurveDumb(
                [curve]
            )
            rules.append(rule)
        section.AddToSection(
            rules, curves[0],
            NXOpen.NXObject.Null,
            NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create,
            False
        )
        builder.Section = section
        resolved_dir = _resolve_direction(direction)
        dir_vec = _direction_vector(resolved_dir)
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        builder.Direction = work_part.Directions.CreateDirection(
            origin,
            dir_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        builder.Limits.StartExtend.Value.RightHandSide = str(float(start))
        builder.Limits.EndExtend.Value.RightHandSide = str(float(distance))
        
        try:
            builder.BooleanOperation.Type = NXOpen.Features.Feature.BooleanType.Create
        except Exception:
            pass

        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    _state["last_curves"] = []
    fit_view()
    return {"ok": True, "message": f"Extruded {float(distance)}mm"}


def create_cuboid(length=40.0, width=25.0, height=20.0, x=0.0, y=0.0, z=0.0):
    length = float(length)
    width = float(width)
    height = float(height)
    x = float(x)
    y = float(y)
    z = float(z)

    if length <= 0.0 or width <= 0.0 or height <= 0.0:
        return {"ok": False, "error": "Cuboid dimensions must be positive"}

    work_part = _ensure_work_part()
    
    # Create expressions
    prefix = _next_instance_prefix("CUBOID")
    l_name = _create_input_expression(work_part, f"{prefix}_L", length)
    w_name = _create_input_expression(work_part, f"{prefix}_W", width)
    h_name = _create_input_expression(work_part, f"{prefix}_H", height)
    
    builder = work_part.Features.CreateBlockFeatureBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(x, y, z)
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(origin, l_name, w_name, h_name)
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {
        "ok": True,
        "message": f"Cuboid {length}x{width}x{height}mm at ({x},{y},{z})",
    }


def create_two_cuboids():
    first = create_cuboid(40.0, 25.0, 20.0, 0.0, 0.0, 0.0)
    if not first.get("ok"):
        return first

    second = create_cuboid(30.0, 25.0, 20.0, 45.0, 0.0, 0.0)
    if not second.get("ok"):
        return second

    fit_view()
    return {
        "ok": True,
        "message": "Created two cuboids next to each other",
    }


def create_cube(size=10.0, x=0.0, y=0.0, z=0.0):
    size = float(size)
    x = float(x)
    y = float(y)
    z = float(z)

    if size <= 0.0:
        return {"ok": False, "error": "Cube size must be positive"}

    work_part = _ensure_work_part()
    prefix = _next_instance_prefix("CUBE")
    s_name = _create_input_expression(work_part, f"{prefix}_SIZE", size)

    builder = work_part.Features.CreateBlockFeatureBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(x, y, z)
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(origin, s_name, s_name, s_name)
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {"ok": True, "message": f"Cube {size}mm at ({x},{y},{z})"}


def create_cylinder(radius=10.0, height=20.0, x=0.0, y=0.0, z=0.0, direction="Z"):
    radius = float(radius)
    height = float(height)
    x = float(x)
    y = float(y)
    z = float(z)

    if radius <= 0.0 or height <= 0.0:
        return {"ok": False, "error": "Cylinder radius and height must be positive"}

    work_part = _ensure_work_part()
    prefix = _next_instance_prefix("CYLINDER")
    r_name = _create_input_expression(work_part, f"{prefix}_R", radius)
    h_name = _create_input_expression(work_part, f"{prefix}_H", height)

    builder = work_part.Features.CreateCylinderBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(x, y, z)
        nx_direction = _create_direction(work_part, origin, _direction_vector(direction))
        builder.Diameter.RightHandSide = f"2 * {r_name}"
        builder.Height.RightHandSide = h_name
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = nx_direction
        feature = builder.Commit()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {
        "ok": True,
        "message": f"Cylinder R{radius} height {height} at ({x},{y},{z})",
    }


def _make_body_collector(work_part, bodies):
    collector = work_part.ScCollectors.CreateCollector()
    rule = work_part.ScRuleFactory.CreateRuleBodyDumb(list(bodies), True)
    _set_collector_rules(collector, [rule])
    return collector


def _set_boolean_inputs(builder, work_part, target_body, tool_bodies):
    tool_body = tool_bodies[0]
    
    # Prioritize modern BooleanBuilder targets/tools assignment:
    if hasattr(builder, "Targets") and (hasattr(builder, "ToolBodyCollector") or hasattr(builder, "BooleanTool")):
        try:
            builder.Targets.Add(target_body)
            
            collector = work_part.ScCollectors.CreateCollector()
            rule = work_part.ScRuleFactory.CreateRuleBodyDumb([tool_body], True)
            _set_collector_rules(collector, [rule])
            
            if hasattr(builder, "ToolBodyCollector"):
                builder.ToolBodyCollector = collector
                return
            elif hasattr(builder, "BooleanTool"):
                boolean_tool = builder.BooleanTool
                for attr in ("BodyCollector", "ToolBodyCollector"):
                    if hasattr(boolean_tool, attr):
                        setattr(boolean_tool, attr, collector)
                        return
        except Exception as e:
            _debug_log("debug_boolean.txt", f"Exception: {e}\n")

    for attr in ("Target", "TargetBody"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, target_body)
                return_attr = attr
                break
            except Exception:
                pass
    else:
        return_attr = None

    for attr in ("Tool", "ToolBody"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, tool_body)
                if return_attr:
                    return
            except Exception:
                pass

    if hasattr(builder, "Targets"):
        try:
            builder.Targets.Add([target_body])
        except Exception:
            pass
    if hasattr(builder, "Tools"):
        try:
            builder.Tools.Add(tool_bodies)
            return
        except Exception:
            pass

    collector = _make_body_collector(work_part, tool_bodies)
    for attr in ("ToolBodyCollector", "ToolCollector"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, collector)
                return
            except Exception:
                try:
                    getattr(builder, attr).ReplaceRules(collector.GetRules(), False)
                    return
                except Exception:
                    pass

    boolean_tool = getattr(builder, "BooleanTool", None)
    if boolean_tool is not None:
        for attr in ("BodyCollector", "ToolBodyCollector"):
            if hasattr(boolean_tool, attr):
                try:
                    setattr(boolean_tool, attr, collector)
                    return
                except Exception:
                    pass

    raise SelectionError("Could not assign boolean target/tool bodies with this NXOpen API")


def _boolean_operation(operation, target="last", tool="last"):
    work_part = _ensure_work_part()
    try:
        target_body = _resolve_body(target)
    except Exception:
        target_body = None
    try:
        tool_body = _resolve_body(tool)
    except Exception:
        tool_body = None

    # Smart fallback if exactly 2 bodies exist in the part
    bodies = _iter_bodies(work_part)
    if len(bodies) == 2:
        if target_body is None or tool_body is None or target_body == tool_body:
            last_body = _state.get("last_body")
            if last_body in bodies:
                target_body = last_body
                tool_body = bodies[0] if bodies[1] == last_body else bodies[1]
            else:
                target_body = bodies[0]
                tool_body = bodies[1]

    # Re-evaluate to raise exception if still unresolved
    if target_body is None:
        target_body = _resolve_body(target)
    if tool_body is None:
        tool_body = _resolve_body(tool)

    if target_body == tool_body:
        raise SelectionError("Boolean target and tool resolve to the same body")

    _debug_log("debug_unite_run.txt", f"Operation: {operation}\n"
               f"target input: {target} -> resolved tag: {target_body.Tag if target_body else None}\n"
               f"tool input: {tool} -> resolved tag: {tool_body.Tag if tool_body else None}\n")

    builder = work_part.Features.CreateBooleanBuilder(
        NXOpen.Features.BooleanFeature.Null
    )
    try:
        operation_name = operation.lower()
        if operation_name == "unite":
            builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        elif operation_name == "subtract":
            builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        else:
            raise SelectionError(f"Unsupported boolean operation: {operation}")

        _set_boolean_inputs(builder, work_part, target_body, [tool_body])
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {
        "ok": True,
        "message": f"Boolean {operation_name}: {_body_name(target_body)} with {_body_name(tool_body)}",
    }


def boolean_unite(target="last", tool="last"):
    return _boolean_operation("unite", target, tool)


def boolean_subtract(target="last", tool="last"):
    return _boolean_operation("subtract", target, tool)


def add_chamfer(offset, body="last", edges="outer_edges"):
    offset = float(offset)
    if offset <= 0.0:
        return {"ok": False, "error": "Chamfer offset must be positive"}

    work_part = _ensure_work_part()
    selected_edges = _resolve_edges(body, edges)
    prefix = _next_instance_prefix("CHAMFER")
    offset_name = _create_input_expression(work_part, f"{prefix}_OFFSET", offset)

    builder = work_part.Features.CreateChamferBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        builder.Option = NXOpen.Features.ChamferBuilder.ChamferOption.OffsetAndAngle
        builder.Method = NXOpen.Features.ChamferBuilder.OffsetMethod.EdgesAlongFaces
        builder.FirstOffset = offset_name
        builder.SecondOffset = offset_name
        builder.Angle = "45"
        builder.Tolerance = 0.01

        rules = [
            work_part.ScRuleFactory.CreateRuleEdgeTangent(
                edge,
                NXOpen.Edge.Null,
                False,
                0.5,
                False,
            )
            for edge in selected_edges
        ]
        collector = work_part.ScCollectors.CreateCollector()
        _set_collector_rules(collector, rules)
        builder.SmartCollector = collector
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {"ok": True, "message": f"Chamfer {offset}mm on {len(selected_edges)} edges"}


def add_fillet(radius, body="last", edges="outer_edges"):
    radius = _eval_val(radius)
    if radius <= 0.0:
        return {"ok": False, "error": "Fillet radius must be positive"}

    work_part = _ensure_work_part()
    selected_edges = _resolve_edges(body, edges)
    prefix = _next_instance_prefix("FILLET")
    r_name = _create_input_expression(work_part, f"{prefix}_R", radius)

    builder = work_part.Features.CreateEdgeBlendBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        collector = work_part.ScCollectors.CreateCollector()
        rule = work_part.ScRuleFactory.CreateRuleEdgeMultipleSeedTangent(
            selected_edges,
            0.5,
            True,
        )
        _set_collector_rules(collector, [rule])

        builder.Tolerance = 0.01
        builder.AllInstancesOption = False
        builder.RemoveSelfIntersection = True
        builder.ConvexConcaveY = False
        builder.RollOverSmoothEdge = True
        builder.RollOntoEdge = True
        builder.MoveSharpEdge = True
        builder.OverlapOption = NXOpen.Features.EdgeBlendBuilder.Overlap.AnyConvexityRollOver
        builder.BlendOrder = NXOpen.Features.EdgeBlendBuilder.OrderOfBlending.ConvexFirst
        builder.SetbackOption = NXOpen.Features.EdgeBlendBuilder.Setback.SeparateFromCorner
        builder.AddChainset(collector, r_name)
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {"ok": True, "message": f"Fillet R{radius} on {len(selected_edges)} edges"}


def _subtract_cylinder_hole(target_body, x, y, z, diameter, depth, direction):
    work_part = _ensure_work_part()
    prefix = _next_instance_prefix("HOLE")
    d_name = _create_input_expression(work_part, f"{prefix}_D", diameter)
    depth_name = _create_input_expression(work_part, f"{prefix}_DEPTH", depth)
    return _subtract_cylinder_hole_parametric(target_body, x, y, z, d_name, depth_name, direction)


def _subtract_cylinder_hole_parametric(target_body, x, y, z, d_name, depth_name, direction):
    work_part = _ensure_work_part()
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        origin = NXOpen.Point3d(x, y, z)
        nx_direction = _create_direction(work_part, origin, _direction_vector(direction))
        builder.Diameter.RightHandSide = d_name
        builder.Height.RightHandSide = depth_name
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = nx_direction
        feature = builder.Commit()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    tool_body = _state.get("last_body")
    saved_last_body = _state.get("last_body")
    _state["last_body"] = target_body
    try:
        result = boolean_subtract(_body_name(target_body), _body_name(tool_body))
    except Exception as e:
        _state["last_body"] = saved_last_body
        return {"ok": False, "error": f"Boolean subtract failed during hole creation: {e}"}
    if result.get("ok"):
        result["message"] = (
            f"Hole created by subtracting a cylindrical tool body"
        )
    return result


def add_hole(x, y, z, diameter, depth, target="last", direction="auto", placement_face="top"):
    diameter = float(diameter)
    depth = float(depth)
    if diameter <= 0.0 or depth <= 0.0:
        return {"ok": False, "error": "Hole diameter and depth must be positive"}

    target_body = _resolve_body(target)
    work_part = _ensure_work_part()
    prefix = _next_instance_prefix("HOLE")
    d_name = _create_input_expression(work_part, f"{prefix}_D", diameter)
    depth_name = _create_input_expression(work_part, f"{prefix}_DEPTH", depth)

    resolved_dir = _resolve_hole_direction(direction)

    builder_factory = getattr(work_part.Features, "CreateHoleBuilder", None)
    if not callable(builder_factory):
        return _subtract_cylinder_hole_parametric(target_body, x, y, z, d_name, depth_name, resolved_dir)

    builder = builder_factory(NXOpen.Features.Feature.Null)
    try:
        builder.Diameter.RightHandSide = d_name
        builder.Depth.RightHandSide = depth_name

        feature = None
        try:
            point = NXOpen.Point3d(float(x), float(y), float(z))
            if hasattr(builder, "Position"):
                builder.Position = point
            if hasattr(builder, "Direction"):
                builder.Direction = _create_direction(work_part, point, _direction_vector(resolved_dir))
            feature = builder.CommitFeature()
        except Exception:
            feature = None

        if feature is None:
            builder.Destroy()
            return _subtract_cylinder_hole_parametric(target_body, x, y, z, d_name, depth_name, resolved_dir)

        _remember_feature(feature)
    finally:
        try:
            builder.Destroy()
        except Exception:
            pass

    fit_view()
    return {
        "ok": True,
        "message": f"Hole D={diameter} depth={depth} at ({float(x)},{float(y)},{float(z)}) on {placement_face}",
    }


def revolve(axis="auto", angle_deg=360.0):
    angle_deg = float(angle_deg)
    work_part = _ensure_work_part()
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No curves to revolve"}

    resolved_axis = _resolve_revolve_axis(axis)

    tags = [curve.Tag for curve in curves]
    direction = _vector_components(_direction_vector(resolved_axis))
    features, number_of_features = UF_SESSION.Modl.CreateRevolution(
        tags,
        len(tags),
        None,
        ["0", str(angle_deg)],
        ["0", "0"],
        [0.0, 0.0, 0.0],
        False,
        True,
        [0.0, 0.0, 0.0],
        direction,
        NXOpen.UF.Modl.FeatureSigns.NULLSIGN,
    )

    if number_of_features > 0 and features:
        feature = NXOpen.TaggedObjectManager().GetTaggedObject(features[0])
        _remember_feature(feature)
    _state["last_curves"] = []

    fit_view()
    return {"ok": True, "message": f"Revolved {angle_deg} degrees around {resolved_axis}"}


def mirror_feature(feature_name="last", plane="XZ"):
    work_part = _ensure_work_part()
    source_feature = _resolve_feature(feature_name)
    datum_builder = work_part.Features.CreateDatumPlaneBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        datum_builder.SetFixedDatumPlane(_fixed_datum_plane_type(plane))
        datum_builder.CommitFeature()
        datum_plane = datum_builder.GetDatum()
    finally:
        datum_builder.Destroy()

    builder = work_part.Features.CreateMirrorFeatureBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        if hasattr(builder, "FeatureSet"):
            builder.FeatureSet.Add([source_feature])
        elif hasattr(builder, "Features"):
            builder.Features.Add([source_feature])
        else:
            raise SelectionError("Mirror builder has no supported feature selection property")

        if hasattr(builder, "PlaneOption"):
            builder.PlaneOption = NXOpen.Features.MirrorFeatureBuilder.PlaneOptions.Existing
        if hasattr(builder, "Plane"):
            builder.Plane.SetValue(
                datum_plane,
                work_part.ModelingViews.WorkView,
                NXOpen.Point3d(0.0, 0.0, 0.0),
            )
        elif hasattr(builder, "MirrorPlane"):
            builder.MirrorPlane = datum_plane
        else:
            raise SelectionError("Mirror builder has no supported mirror plane property")
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {"ok": True, "message": f"Mirrored '{_feature_name(source_feature)}' about {plane}"}


def pattern_feature(feature_name="last", direction="X", count=3, pitch=10.0):
    count = int(count)
    pitch = float(pitch)
    if count < 2:
        return {"ok": False, "error": "Pattern count must be at least 2"}
    if pitch == 0.0:
        return {"ok": False, "error": "Pattern pitch must be non-zero"}

    work_part = _ensure_work_part()
    source_feature = _resolve_feature(feature_name)
    
    prefix = _next_instance_prefix("PATTERN")
    count_name = _create_input_expression(work_part, f"{prefix}_COUNT", count)
    pitch_name = _create_input_expression(work_part, f"{prefix}_PITCH", pitch)

    builder_factory = getattr(work_part.Features, "CreatePatternFeatureBuilder", None)
    if not callable(builder_factory):
        builder_factory = getattr(work_part.Features, "CreateLinearPatternBuilder", None)
    if not callable(builder_factory):
        return {"ok": False, "error": "This NXOpen API has no supported feature pattern builder"}

    builder = builder_factory(NXOpen.Features.Feature.Null)
    try:
        if hasattr(builder, "FeatureList"):
            builder.FeatureList.Add([source_feature])
        elif hasattr(builder, "Features"):
            builder.Features.Add([source_feature])
        elif hasattr(builder, "Feature"):
            builder.Feature = source_feature
        else:
            raise SelectionError("Pattern builder has no supported feature selection property")

        service = getattr(builder, "PatternService", None)
        if service is None:
            raise SelectionError("Pattern builder has no PatternService")
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        nx_direction = _create_direction(work_part, origin, _direction_vector(direction))
        rect = getattr(service, "RectangularDefinition", None)
        if rect is not None:
            rect.XDirection = nx_direction
            rect.UseYDirectionToggle = False
            rect.XSpacing.NCopies.RightHandSide = count_name
            rect.XSpacing.PitchDistance.RightHandSide = pitch_name
        else:
            service.PatternCount.RightHandSide = count_name
            service.Pitch.RightHandSide = pitch_name
            if hasattr(service, "Direction"):
                service.Direction = nx_direction

        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {
        "ok": True,
        "message": f"Pattern '{_feature_name(source_feature)}' {count}x @ {pitch}mm along {direction}",
    }



# ---------------------------------------------------------------------------
# NEW TOOLS: create_real_sketch, extrude_from_sketch, add_hole_nx,
#            create_rib, pattern_circular, edge_blend, chamfer_edges,
#            revolve_cut, extrude_cut
# ---------------------------------------------------------------------------


def create_real_sketch(plane="XY", z_offset=0.0, origin_x=0.0, origin_y=0.0, rotate_z_deg=0.0):
    """Create a proper constrained NX Sketch object on a plane with offset and rotation.

    Stores the sketch plane origin and rotation in _state for curve transformations,
    and attempts to build a real Sketch on a local Plane object if a sketch builder is found.
    """
    global ACTIVE_SKETCH_PLANE

    plane = str(plane or "XY").strip().upper()
    if plane not in {"XY", "XZ", "YZ"}:
        return {"ok": False, "error": f"Invalid sketch plane: {plane}"}

    work_part = _ensure_work_part()
    ACTIVE_SKETCH_PLANE = plane

    z_val = _eval_val(z_offset)
    ox_val = _eval_val(origin_x)
    oy_val = _eval_val(origin_y)
    rot_val = _eval_val(rotate_z_deg)

    _state["sketch_origin"] = [ox_val, oy_val, z_val]
    _state["sketch_rotation"] = rot_val
    _state["last_curves"] = []
    _state["active_sketch"] = None

    # --- Try to create a real sketch on a local Plane object ---
    builder_factory = getattr(work_part.Sketches, "CreateNewSketchInPlaceBuilder", None)
    if not callable(builder_factory):
        builder_factory = getattr(work_part.Sketches, "CreateSimpleSketchInPlaceBuilder", None)
    if not callable(builder_factory):
        builder_factory = getattr(work_part.Sketches, "CreateNewSketch", None)
    if not callable(builder_factory):
        builder_factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder", None)

    if callable(builder_factory):
        try:
            origin = NXOpen.Point3d(ox_val, oy_val, z_val)
            normal = _normal_for_active_plane()
            plane_obj = work_part.Planes.CreatePlane(
                origin, normal, NXOpen.SmartObject.UpdateOption.WithinModeling
            )

            sketch_builder = builder_factory(NXOpen.Features.Feature.Null)
            try:
                for attr in ("PlaneReference", "PlacementFace", "SketchOrigin"):
                    if hasattr(sketch_builder, attr):
                        try:
                            setattr(sketch_builder, attr, plane_obj)
                            break
                        except Exception:
                            pass
                feature = sketch_builder.CommitFeature()
            finally:
                sketch_builder.Destroy()

            _remember_feature(feature)
            sketch_name = _feature_name(feature)
            _state["sketches"][plane] = feature
            _state["sketches"][sketch_name.lower()] = feature
            _state["active_sketch"] = feature
            fit_view()
            return {
                "ok": True,
                "message": (
                    f"Sketch created on {plane} plane (id={sketch_name}) "
                    f"with offset z={z_val} rotation={rot_val}"
                ),
            }
        except Exception as e:
            return {"ok": False, "error": f"Failed to create sketch in NX: {e}"}

    # Mock mode fallback
    if os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1":
        fit_view()
        return {
            "ok": True,
            "message": f"Sketch created on {plane} plane with offset z={z_val} rotation={rot_val} (mock mode)",
        }

    return {"ok": False, "error": "NX Sketches API not available on this Siemens NX installation"}


def extrude_from_sketch(sketch_name="last", distance=10.0, start=0.0, direction="auto"):
    distance = _eval_val(distance)
    start = _eval_val(start)
    work_part = _ensure_work_part()
    prefix = _next_instance_prefix("EXTRUDE")
    dist_name = _create_input_expression(work_part, f"{prefix}_DIST", distance)
    start_name = _create_input_expression(work_part, f"{prefix}_START", start)

    # Try resolving real sketch feature curves if sketch_name is specified
    curves = []
    sketch_feature = None
    if sketch_name and sketch_name.lower() != "last":
        try:
            sketch_feature = _resolve_feature(sketch_name)
        except Exception:
            pass

    if sketch_feature is not None:
        sketch_obj = None
        if hasattr(sketch_feature, "GetAllGeometry"):
            sketch_obj = sketch_feature
        elif hasattr(sketch_feature, "Sketch"):
            sketch_obj = sketch_feature.Sketch
        
        if sketch_obj is not None:
            try:
                curves = list(sketch_obj.GetAllGeometry() or [])
            except Exception:
                pass

    if not curves:
        curves = _state.get("last_curves", [])

    if not curves:
        return {"ok": False, "error": "No curves to extrude — draw a profile first"}

    builder = work_part.Features.CreateExtrudeBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rules = [
            work_part.ScRuleFactory.CreateRuleCurveDumb([c])
            for c in curves
        ]
        section.AddToSection(
            rules, curves[0],
            NXOpen.NXObject.Null,
            NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create,
            False,
        )
        builder.Section = section

        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        resolved_dir = _resolve_direction(direction)
        nx_dir = _create_direction(work_part, origin, _direction_vector(resolved_dir))
        builder.Direction = nx_dir
        builder.Limits.StartExtend.Value.RightHandSide = start_name
        builder.Limits.EndExtend.Value.RightHandSide = dist_name
        try:
            builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        except Exception:
            try:
                builder.BooleanOperation.Type = NXOpen.Features.Feature.BooleanType.Create
            except Exception:
                pass

        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    _state["last_curves"] = []
    fit_view()
    return {"ok": True, "message": f"Extruded sketch '{sketch_name}' {distance}mm along {resolved_dir}"}


def add_hole_nx(
    x, y, z, diameter, depth,
    target="last", direction="auto", hole_type="simple"
):
    """Proper NX HoleBuilder: simple hole at (x,y,z) with diameter and depth.

    Uses CreateHoleBuilder with SimpleHole type and full parametric expressions.
    Falls back to cylinder-subtract if HoleBuilder is not available.
    """
    x_val = _eval_val(x)
    y_val = _eval_val(y)
    z_val = _eval_val(z)
    diameter = _eval_val(diameter)
    depth = _eval_val(depth)
    if diameter <= 0.0 or depth <= 0.0:
        return {"ok": False, "error": "Hole diameter and depth must be positive"}

    # Apply sketch coordinate transformation:
    pt = _point_on_active_plane(x_val, y_val)
    x_trans = pt.X
    y_trans = pt.Y
    z_trans = z_val

    target_body = _resolve_body(target)
    work_part = _ensure_work_part()
    prefix = _next_instance_prefix("HOLE")
    d_name = _create_input_expression(work_part, f"{prefix}_D", diameter)
    depth_name = _create_input_expression(work_part, f"{prefix}_DEPTH", depth)

    debug_msg = ""
    resolved_dir = _resolve_hole_direction(direction)
    if direction == "auto" or not direction:
        try:
            import NXOpen.UF
            uf_session = NXOpen.UF.UFSession.GetUFSession()
            pt_plus = [float(x_trans), float(y_trans), float(z_trans) + 0.1]
            pt_minus = [float(x_trans), float(y_trans), float(z_trans) - 0.1]
            contain_plus = uf_session.Modeling.AskPointContainment(pt_plus, target_body.Tag)
            contain_minus = uf_session.Modeling.AskPointContainment(pt_minus, target_body.Tag)
            debug_msg += f"pt_plus={pt_plus} contain_plus={contain_plus} pt_minus={pt_minus} contain_minus={contain_minus}\n"
            if contain_plus in {1, 3, 4, 5} and contain_minus not in {1, 3, 4, 5}:
                resolved_dir = "+Z"
            elif contain_minus in {1, 3, 4, 5} and contain_plus not in {1, 3, 4, 5}:
                resolved_dir = "-Z"
        except Exception as e:
            debug_msg += f"Exception: {e}\n"

    _debug_log("debug_hole.txt", f"x_trans={x_trans} y_trans={y_trans} z_trans={z_trans}\n"
               f"target_body={target_body} tag={target_body.Tag if target_body else None}\n"
               f"{debug_msg}"
               f"final_dir={resolved_dir}\n", mode="w")

    builder_factory = getattr(work_part.Features, "CreateHoleBuilder", None)
    if not callable(builder_factory):
        return _subtract_cylinder_hole_parametric(
            target_body, x_trans, y_trans, z_trans, d_name, depth_name, resolved_dir
        )

    builder = builder_factory(NXOpen.Features.Feature.Null)
    try:
        # Set hole type to simple
        for attr in ("Type", "HoleType"):
            if hasattr(builder, attr):
                try:
                    simple_val = getattr(
                        type(builder),
                        attr,
                        None
                    )
                    # Try to set the Simple enum value
                    type_enum = getattr(builder, attr + "s", None) or getattr(builder, attr)
                    simple = getattr(type_enum, "Simple",
                               getattr(type_enum, "GeneralHole", None))
                    if simple is not None:
                        setattr(builder, attr, simple)
                    break
                except Exception:
                    pass

        builder.Diameter.RightHandSide = d_name
        # Depth attribute name varies by NX release
        for depth_attr in ("Depth", "HoleDepth", "TipDepth"):
            if hasattr(builder, depth_attr):
                try:
                    getattr(builder, depth_attr).RightHandSide = depth_name
                    break
                except Exception:
                    pass

        point = NXOpen.Point3d(float(x_trans), float(y_trans), float(z_trans))
        if hasattr(builder, "Position"):
            try:
                builder.Position = point
            except Exception:
                pass
        if hasattr(builder, "Direction"):
            try:
                builder.Direction = _create_direction(
                    work_part, point, _direction_vector(resolved_dir)
                )
            except Exception:
                pass

        # Target body for boolean
        for attr in ("Target", "TargetBody", "BooleanOperation"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body)
                    break
                except Exception:
                    pass

        try:
            feature = builder.CommitFeature()
        except Exception:
            builder.Destroy()
            return _subtract_cylinder_hole_parametric(
                target_body, x, y, z, d_name, depth_name, resolved_dir
            )

        _remember_feature(feature)
    finally:
        try:
            builder.Destroy()
        except Exception:
            pass

    fit_view()
    return {
        "ok": True,
        "message": (
            f"Hole D={diameter} depth={depth} at "
            f"({float(x):.3f},{float(y):.3f},{float(z):.3f})"
        ),
    }


def create_rib(thickness, direction="auto", body="last", flip=False):
    """Create a rib/web feature from the active sketch profile.

    Uses CreateRibBuilder when available.  Falls back to a thin solid extrude
    (half thickness each side) united with the target body.
    """
    thickness = float(thickness)
    if thickness <= 0.0:
        return {"ok": False, "error": "Rib thickness must be positive"}

    work_part = _ensure_work_part()
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No profile curves — draw a rib profile first"}

    prefix = _next_instance_prefix("RIB")
    _create_input_expression(work_part, f"{prefix}_T", thickness)
    _create_formula_expression(work_part, f"{prefix}_HALF_T", f"{prefix}_T / 2.0")
    t_name = f"{prefix}_T"
    half_t_name = f"{prefix}_HALF_T"
    half_t = work_part.Expressions.FindObject(half_t_name).Value

    resolved_dir = _resolve_direction(direction)

    # --- Try native RibBuilder ---
    rib_factory = getattr(work_part.Features, "CreateRibBuilder", None)
    if callable(rib_factory):
        try:
            builder = rib_factory(NXOpen.Features.Feature.Null)
            try:
                section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
                rules = [
                    work_part.ScRuleFactory.CreateRuleCurveDumb([c])
                    for c in curves
                ]
                section.AddToSection(
                    rules, curves[0],
                    NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                    NXOpen.Point3d(0.0, 0.0, 0.0),
                    NXOpen.Section.Mode.Create, False,
                )

                if hasattr(builder, "Section"):
                    builder.Section = section
                elif hasattr(builder, "Profile"):
                    builder.Profile = section

                # Thickness
                for attr in ("Thickness", "Width"):
                    if hasattr(builder, attr):
                        try:
                            getattr(builder, attr).RightHandSide = t_name
                            break
                        except Exception:
                            pass

                # Direction / extrude direction
                origin = NXOpen.Point3d(0.0, 0.0, 0.0)
                nx_dir = _create_direction(work_part, origin, _direction_vector(resolved_dir))
                for attr in ("ExtrudeDirection", "Direction", "ThicknessDirection"):
                    if hasattr(builder, attr):
                        try:
                            setattr(builder, attr, nx_dir)
                            break
                        except Exception:
                            pass

                if flip and hasattr(builder, "ReverseDirection"):
                    builder.ReverseDirection = True

                feature = builder.CommitFeature()
                _remember_feature(feature)
            finally:
                builder.Destroy()

            _state["last_curves"] = []
            fit_view()
            return {"ok": True, "message": f"Rib T={thickness}mm along {resolved_dir}"}
        except Exception:
            pass  # fall through to fallback

    # --- Fallback: thin extrude symmetrical about the profile plane ---
    target_body_ref = _state.get("last_body")

    builder = work_part.Features.CreateExtrudeBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rules = [
            work_part.ScRuleFactory.CreateRuleCurveDumb([c])
            for c in curves
        ]
        section.AddToSection(
            rules, curves[0],
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False,
        )
        builder.Section = section
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        nx_dir = _create_direction(work_part, origin, _direction_vector(resolved_dir))
        builder.Direction = nx_dir
        # Symmetric: -half_t to +half_t
        builder.Limits.StartExtend.Value.RightHandSide = f"-{half_t_name}"
        builder.Limits.EndExtend.Value.RightHandSide = half_t_name

        if target_body_ref is not None:
            try:
                builder.BooleanOperation.Type = (
                    NXOpen.Features.Feature.BooleanType.Unite
                )
                builder.BooleanOperation.SetTarget(target_body_ref)
            except Exception:
                pass
        else:
            builder.BooleanOperation.Type = (
                NXOpen.Features.Feature.BooleanType.Create
            )

        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    _state["last_curves"] = []
    fit_view()
    return {"ok": True, "message": f"Rib T={thickness}mm (extrude fallback) along {resolved_dir}"}


def pattern_circular(
    feature_name="last", axis="auto", count=4, angle_total=360.0
):
    """Circular pattern of a feature: count instances over angle_total degrees."""
    count = int(count)
    angle_total = float(angle_total)
    if count < 2:
        return {"ok": False, "error": "Circular pattern count must be at least 2"}
    if angle_total == 0.0:
        return {"ok": False, "error": "angle_total must be non-zero"}

    work_part = _ensure_work_part()
    source_feature = _resolve_feature(feature_name)

    prefix = _next_instance_prefix("CIRC_PAT")
    count_name = _create_input_expression(work_part, f"{prefix}_COUNT", count)
    angle_name = _create_input_expression(work_part, f"{prefix}_ANGLE", angle_total)

    resolved_axis = _resolve_direction(axis)

    builder_factory = getattr(work_part.Features, "CreatePatternFeatureBuilder", None)
    if not callable(builder_factory):
        return {"ok": False, "error": "CreatePatternFeatureBuilder not available in this NX version"}

    builder = builder_factory(NXOpen.Features.Feature.Null)
    try:
        # Add source feature
        if hasattr(builder, "FeatureList"):
            builder.FeatureList.Add([source_feature])
        elif hasattr(builder, "Features"):
            builder.Features.Add([source_feature])
        elif hasattr(builder, "Feature"):
            builder.Feature = source_feature
        else:
            raise SelectionError("Pattern builder has no supported feature property")

        service = getattr(builder, "PatternService", None)
        if service is None:
            raise SelectionError("Pattern builder has no PatternService")

        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        nx_dir = _create_direction(work_part, origin, _direction_vector(resolved_axis))

        # Try CircularDefinition first (NX 10+)
        circ = getattr(service, "CircularDefinition", None)
        if circ is not None:
            # Set RotationAxis and RotationCenter
            origin_pt = NXOpen.Point3d(0.0, 0.0, 0.0)
            dir_vector = _direction_vector(resolved_axis)
            axis_obj = work_part.Axes.CreateAxis(origin_pt, dir_vector, NXOpen.SmartObjectUpdateOption.WithinModeling)
            
            circ.RotationAxis = axis_obj
            circ.RotationCenter = work_part.Points.CreatePoint(origin_pt)
            
            # Set spacing type to count and span (PitchAndSpan)
            circ.AngularSpacing.SpaceType = NXOpen.GeometricUtilities.PatternSpacingSpacingType.PitchAndSpan
            circ.AngularSpacing.NCopies.RightHandSide = count_name
            circ.AngularSpacing.SpanAngle.RightHandSide = angle_name
            if hasattr(service, "PatternType"):
                try:
                    service.PatternType = getattr(
                        type(service).PatternType,
                        "Circular",
                        service.PatternType
                    )
                except Exception:
                    pass
        else:
            # Fallback: rectangular service with only X populated
            rect = getattr(service, "RectangularDefinition", None)
            if rect is not None:
                rect.XDirection = nx_dir
                rect.UseYDirectionToggle = False
                rect.XSpacing.NCopies.RightHandSide = count_name
                # pitch = total_angle / (count-1) as angular — use numeric
                pitch_deg = angle_total / max(count - 1, 1)
                pitch_name = _create_input_expression(
                    work_part, f"{prefix}_PITCH_DEG", pitch_deg
                )
                rect.XSpacing.PitchDistance.RightHandSide = pitch_name
            else:
                service.PatternCount.RightHandSide = count_name
                if hasattr(service, "Direction"):
                    service.Direction = nx_dir

        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {
        "ok": True,
        "message": (
            f"Circular pattern '{_feature_name(source_feature)}' "
            f"{count}x over {angle_total}° about {resolved_axis}"
        ),
    }


def edge_blend(radius, body="last", edges="outer_edges"):
    """Fillet edges by semantic selection — thin wrapper over add_fillet."""
    return add_fillet(radius, body, edges)


def chamfer_edges(offset, body="last", edges="outer_edges"):
    """Chamfer edges by semantic selection — thin wrapper over add_chamfer."""
    return add_chamfer(offset, body, edges)


def revolve_cut(axis="auto", angle_deg=360.0, target="last"):
    """Revolve active sketch profile around axis to CUT/remove material.

    Uses CreateRevolveBuilder with BooleanType.Subtract.
    Falls back to: revolve() to create a solid, then boolean_subtract.
    """
    angle_deg = float(angle_deg)
    work_part = _ensure_work_part()
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No curves to revolve-cut — draw a profile first"}

    target_body = _resolve_body(target)
    prefix = _next_instance_prefix("REVOLVE_CUT")
    angle_name = _create_input_expression(work_part, f"{prefix}_ANGLE", angle_deg)
    resolved_axis = _resolve_revolve_axis(axis)

    # --- Try modern CreateRevolveBuilder path ---
    builder_factory = getattr(work_part.Features, "CreateRevolveBuilder", None)
    if callable(builder_factory):
        try:
            builder = builder_factory(NXOpen.Features.Feature.Null)
            try:
                section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
                rules = [
                    work_part.ScRuleFactory.CreateRuleCurveDumb([c])
                    for c in curves
                ]
                section.AddToSection(
                    rules, curves[0],
                    NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                    NXOpen.Point3d(0.0, 0.0, 0.0),
                    NXOpen.Section.Mode.Create, False,
                )
                builder.Section = section

                origin = NXOpen.Point3d(0.0, 0.0, 0.0)
                nx_dir = _direction_vector(resolved_axis)
                revolve_axis_obj = _create_axis(work_part, origin, nx_dir)
                builder.Axis = revolve_axis_obj

                builder.Limits.StartExtend.Value.RightHandSide = "0"
                builder.Limits.EndExtend.Value.RightHandSide = angle_name

                builder.BooleanOperation.Type = (
                    NXOpen.Features.Feature.BooleanType.Subtract
                )
                try:
                    builder.BooleanOperation.SetTarget(target_body)
                except Exception:
                    pass

                feature = builder.CommitFeature()
                _remember_feature(feature)
            finally:
                builder.Destroy()

            _state["last_curves"] = []
            fit_view()
            return {"ok": True, "message": f"Revolve-cut {angle_deg}° about {resolved_axis}"}
        except Exception as e:
            sys.stderr.write(f"revolve_cut builder failed, falling back to revolve+subtract: {e}\n")

    # --- Fallback: revolve to solid then boolean subtract ---
    revolve_result = revolve(resolved_axis, angle_deg)
    if not revolve_result.get("ok"):
        return revolve_result
    cut_body = _state.get("last_body")
    if cut_body is None:
        return {"ok": False, "error": "Revolve succeeded but no body was recorded for subtraction"}
    saved_last_body = _state.get("last_body")
    _state["last_body"] = target_body
    try:
        result = boolean_subtract(_body_name(target_body), _body_name(cut_body))
    except Exception as e:
        _state["last_body"] = saved_last_body
        return {"ok": False, "error": f"Boolean subtract failed during revolve-cut: {e}"}
    if result.get("ok"):
        result["message"] = f"Revolve-cut {angle_deg}° about {resolved_axis}"
    return result


def extrude_cut(distance, start=0.0, target="last", direction="auto", reverse_direction=False):
    """Extrude active sketch profile to CUT/remove material from target body.

    Uses CreateExtrudeBuilder with BooleanType.Subtract.
    """
    distance = float(distance)
    start = float(start)
    if distance <= 0.0:
        return {"ok": False, "error": "Extrude-cut distance must be positive"}

    work_part = _ensure_work_part()
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No curves to extrude-cut — draw a profile first"}

    target_body = _resolve_body(target)
    prefix = _next_instance_prefix("EXTRUDE_CUT")
    dist_name = _create_input_expression(work_part, f"{prefix}_DIST", distance)
    start_name = _create_input_expression(work_part, f"{prefix}_START", start)

    builder = work_part.Features.CreateExtrudeBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rules = [
            work_part.ScRuleFactory.CreateRuleCurveDumb([c])
            for c in curves
        ]
        section.AddToSection(
            rules, curves[0],
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False,
        )
        builder.Section = section

        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        dir_vec = _direction_vector("-Z") if direction in ("auto", "-Z", "-auto") else _direction_vector(direction)
        if reverse_direction:
            dir_vec = NXOpen.Vector3d(-dir_vec.X, -dir_vec.Y, -dir_vec.Z)

        nx_dir = _create_direction(work_part, origin, dir_vec)
        builder.Direction = nx_dir
        builder.Limits.StartExtend.Value.RightHandSide = start_name
        builder.Limits.EndExtend.Value.RightHandSide = dist_name

        target_set = False
        if target_body is not None:
            for bool_attr in ("BooleanOperation", "BooleanOption"):
                if hasattr(builder, bool_attr):
                    b_opt = getattr(builder, bool_attr)
                    try:
                        b_opt.Type = NXOpen.Features.Feature.BooleanType.Subtract
                    except Exception:
                        pass
                    for target_method in ("SetTarget", "SetTargetBody", "SetTargetBodies"):
                        if hasattr(b_opt, target_method):
                            try:
                                m = getattr(b_opt, target_method)
                                if target_method == "SetTargetBodies":
                                    m([target_body])
                                else:
                                    m(target_body)
                                target_set = True
                                break
                            except Exception as e:
                                sys.stderr.write(f"Target method {target_method} failed: {e}\n")
                    if target_set:
                        break

        if not target_set:
            try:
                builder.BooleanOperation.Type = NXOpen.Features.Feature.BooleanType.Create
            except Exception:
                pass

        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    _state["last_curves"] = []
    fit_view()

    if not target_set and target_body is not None:
        created_body = _state.get("last_body")
        if created_body is not None and created_body != target_body:
            builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
            try:
                builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
                _set_boolean_inputs(builder, work_part, target_body, [created_body])
                feature = builder.CommitFeature()
                _remember_feature(feature)
            finally:
                builder.Destroy()

    return {"ok": True, "message": f"Extrude-cut {distance}mm from '{_body_name(target_body)}'"}

    if not target_set:
        cut_body = _state.get("last_body")
        if cut_body is None:
            return {"ok": False, "error": "Extrude-cut solid creation succeeded but no body was recorded"}
        saved_last_body = _state.get("last_body")
        _state["last_body"] = target_body
        try:
            result = boolean_subtract(_body_name(target_body), _body_name(cut_body))
        except Exception as e:
            _state["last_body"] = saved_last_body
            return {"ok": False, "error": f"Boolean subtract failed during extrude-cut: {e}"}
        if result.get("ok"):
            result["message"] = f"Extrude-cut {distance}mm from '{_body_name(target_body)}' along {direction}"
        return result

    return {
        "ok": True,
        "message": f"Extrude-cut {distance}mm from '{_body_name(target_body)}' along {direction}",
    }


def _resolve_face_by_coordinate(body_reference="last", x=0.0, y=0.0, z=0.0):
    body = _resolve_body(body_reference)
    faces = list(body.GetFaces() or [])
    if not faces:
        raise SelectionError(f"No faces found on body: {body_reference}")
    best_face = None
    min_dist = 999999.0
    for face in faces:
        try:
            face_type, origin, direction, bbox, radius, flag1, flag2 = UF_SESSION.Modl.AskFaceData(face.Tag)
            pt = _point_tuple(origin)
            dist = math.sqrt((pt[0]-x)**2 + (pt[1]-y)**2 + (pt[2]-z)**2)
            if dist < min_dist:
                min_dist = dist
                best_face = face
        except Exception:
            if best_face is None:
                best_face = face
    return best_face


def _resolve_edge_by_coordinate(body_reference="last", x=0.0, y=0.0, z=0.0):
    body = _resolve_body(body_reference)
    edges = list(body.GetEdges() or [])
    if not edges:
        raise SelectionError(f"No edges found on body: {body_reference}")
    best_edge = None
    min_dist = 999999.0
    for edge in edges:
        try:
            pt = _edge_midpoint(edge)
            dist = math.sqrt((pt[0]-x)**2 + (pt[1]-y)**2 + (pt[2]-z)**2)
            if dist < min_dist:
                min_dist = dist
                best_edge = edge
        except Exception:
            if best_edge is None:
                best_edge = edge
    return best_edge


def _resolve_curves(reference="last"):
    ref = str(reference or "last").strip().lower()
    if ref in {"last", "last_curves", "previous_curves"}:
        return _state.get("last_curves", [])
    if ref in _state["sketches"]:
        sketch_feature = _state["sketches"][ref]
        try:
            if hasattr(sketch_feature, "GetAllGeometry"):
                return list(sketch_feature.GetAllGeometry() or [])
            if hasattr(sketch_feature, "Sketch") and hasattr(sketch_feature.Sketch, "GetAllGeometry"):
                return list(sketch_feature.Sketch.GetAllGeometry() or [])
        except Exception:
            pass
    try:
        feature = _resolve_feature(reference)
        if hasattr(feature, "GetAllGeometry"):
            return list(feature.GetAllGeometry() or [])
        if hasattr(feature, "Sketch") and hasattr(feature.Sketch, "GetAllGeometry"):
            return list(feature.Sketch.GetAllGeometry() or [])
    except Exception:
        pass
    return _state.get("last_curves", [])


def _build_section_from_curves(work_part, curves):
    section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
    rules = [work_part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    if curves:
        section.AddToSection(
            rules, curves[0],
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False
        )
    return section


def _execute_surface_builder(builder_name, config_fn, success_message):
    work_part = _ensure_work_part()
    builder_factory = getattr(work_part.Features, builder_name, None)
    if not callable(builder_factory):
        for attr in dir(work_part.Features):
            if attr.lower() == builder_name.lower():
                builder_factory = getattr(work_part.Features, attr)
                break
    if not callable(builder_factory):
        return {"ok": False, "error": f"NXOpen Features has no builder: {builder_name}"}
    builder = builder_factory(NXOpen.Features.Feature.Null)
    try:
        config_fn(builder, work_part)
        commit_method = getattr(builder, "CommitFeature", None) or getattr(builder, "Commit", None)
        if callable(commit_method):
            feature = commit_method()
            if feature:
                _remember_feature(feature)
        else:
            raise RuntimeError(f"Builder {builder_name} has no Commit or CommitFeature method")
    except Exception as e:
        return {"ok": False, "error": f"Failed executing {builder_name}: {str(e)}"}
    finally:
        builder.Destroy()
    fit_view()
    return {"ok": True, "message": success_message}


def create_base_surface(plane="XY", width=50.0, height=50.0):
    width = float(width)
    height = float(height)
    work_part = _ensure_work_part()
    create_sketch(plane)
    draw_rectangle(-width/2, -height/2, width, height)
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "Failed to create curves for base surface"}
    def config(builder, wp):
        builder.Section = _build_section_from_curves(wp, curves)
    res = _execute_surface_builder("CreateBoundedPlaneBuilder", config, f"Created base surface {width}x{height} on {plane}")
    _state["last_curves"] = []
    return res


def extrude_surface(distance, start=0.0, direction="auto"):
    distance = float(distance)
    start = float(start)
    work_part = _ensure_work_part()
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No curves to extrude as surface"}
    prefix = _next_instance_prefix("EXTRUDE_SURF")
    def config(builder, wp):
        builder.Section = _build_section_from_curves(wp, curves)
        resolved_dir = _resolve_direction(direction)
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        builder.Direction = _create_direction(wp, origin, _direction_vector(resolved_dir))
        builder.Limits.StartExtend.Value.RightHandSide = _create_input_expression(wp, f"{prefix}_START", start)
        builder.Limits.EndExtend.Value.RightHandSide = _create_input_expression(wp, f"{prefix}_DIST", distance)
        for attr in ("FeatureOption", "FeatureOptions"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, getattr(NXOpen.Features, "FeatureOption", None).Sheet)
                except Exception:
                    pass
    res = _execute_surface_builder("CreateExtrudeBuilder", config, f"Extruded surface {distance}mm")
    _state["last_curves"] = []
    return res


def create_swept(section="last", guide="last"):
    sec_curves = _resolve_curves(section)
    guide_curves = _resolve_curves(guide)
    if not sec_curves or not guide_curves:
        return {"ok": False, "error": "Section or guide curves could not be resolved"}
    def config(builder, wp):
        sec = _build_section_from_curves(wp, sec_curves)
        gd = _build_section_from_curves(wp, guide_curves)
        for attr in ("Profile", "SweepProfile", "Section"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, sec)
                except Exception:
                    pass
        for attr in ("Guide", "SweepGuide", "Path"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, gd)
                except Exception:
                    pass
    return _execute_surface_builder("CreateSweepBuilder", config, "Swept surface created")


def create_through_curves(sections="last"):
    sec_curves = _resolve_curves(sections)
    if not sec_curves:
        return {"ok": False, "error": "Through curves sections not found"}
    def config(builder, wp):
        sec = _build_section_from_curves(wp, sec_curves)
        if hasattr(builder, "SectionsList"):
            builder.SectionsList.Add(sec)
        elif hasattr(builder, "Sections"):
            builder.Sections.Add(sec)
    return _execute_surface_builder("CreateThroughCurvesBuilder", config, "Through curves surface created")


def create_through_curve_mesh(primary="last", cross="last"):
    prim_curves = _resolve_curves(primary)
    crs_curves = _resolve_curves(cross)
    def config(builder, wp):
        sec_p = _build_section_from_curves(wp, prim_curves)
        sec_c = _build_section_from_curves(wp, crs_curves)
        if hasattr(builder, "PrimarySections"):
            builder.PrimarySections.Add(sec_p)
        if hasattr(builder, "CrossSections"):
            builder.CrossSections.Add(sec_c)
    return _execute_surface_builder("CreateThroughCurveMeshBuilder", config, "Through curve mesh created")


def add_face_blend(face1_x, face1_y, face1_z, face2_x, face2_y, face2_z, radius=5.0, body="last"):
    radius = float(radius)
    f1 = _resolve_face_by_coordinate(body, face1_x, face1_y, face1_z)
    f2 = _resolve_face_by_coordinate(body, face2_x, face2_y, face2_z)
    prefix = _next_instance_prefix("FACE_BLEND")
    def config(builder, wp):
        r_name = _create_input_expression(wp, f"{prefix}_R", radius)
        if hasattr(builder, "Radius"):
            builder.Radius.RightHandSide = r_name
        collector1 = wp.ScCollectors.CreateCollector()
        collector2 = wp.ScCollectors.CreateCollector()
        rule1 = wp.ScRuleFactory.CreateRuleFaceDumb([f1])
        rule2 = wp.ScRuleFactory.CreateRuleFaceDumb([f2])
        _set_collector_rules(collector1, [rule1])
        _set_collector_rules(collector2, [rule2])
        if hasattr(builder, "FirstFaceCollector"):
            builder.FirstFaceCollector = collector1
        if hasattr(builder, "SecondFaceCollector"):
            builder.SecondFaceCollector = collector2
    return _execute_surface_builder("CreateFaceBlendBuilder", config, f"Face blend R{radius}mm added between faces")


def offset_surface(distance, body="last", face_x=0.0, face_y=0.0, face_z=0.0):
    distance = float(distance)
    f = _resolve_face_by_coordinate(body, face_x, face_y, face_z)
    prefix = _next_instance_prefix("OFFSET_SURF")
    def config(builder, wp):
        dist_name = _create_input_expression(wp, f"{prefix}_DIST", distance)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = dist_name
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleFaceDumb([f])
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "FaceCollector"):
            builder.FaceCollector = collector
    return _execute_surface_builder("CreateOffsetSurfaceBuilder", config, f"Created offset surface of {distance}mm")


def thicken_sheet(thickness, direction="auto", body="last"):
    thickness = float(thickness)
    target_body = _resolve_body(body)
    prefix = _next_instance_prefix("THICKEN")
    def config(builder, wp):
        t_name = _create_input_expression(wp, f"{prefix}_T", thickness)
        if hasattr(builder, "FirstOffset"):
            builder.FirstOffset.RightHandSide = t_name
        if hasattr(builder, "SecondOffset"):
            builder.SecondOffset.RightHandSide = "0.0"
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleBodyDumb([target_body], True)
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "FaceCollector"):
            builder.FaceCollector = collector
        resolved_dir = _resolve_direction(direction)
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        builder.Direction = _create_direction(wp, origin, _direction_vector(resolved_dir))
    return _execute_surface_builder("CreateThickenBuilder", config, f"Thickened sheet body '{_body_name(target_body)}' by {thickness}mm")


def sweep_along_guide(section="last", guide="last"):
    sec_curves = _resolve_curves(section)
    guide_curves = _resolve_curves(guide)
    if not sec_curves or not guide_curves:
        return {"ok": False, "error": "Section or guide curves could not be resolved"}
    def config(builder, wp):
        sec = _build_section_from_curves(wp, sec_curves)
        gd = _build_section_from_curves(wp, guide_curves)
        for attr in ("Profile", "SweepProfile", "Section"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, sec)
                except Exception:
                    pass
        for attr in ("Guide", "SweepGuide", "Path"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, gd)
                except Exception:
                    pass
    return _execute_surface_builder("CreateSweepAlongGuideBuilder", config, "Sweep along guide created")


def variational_sweep(section="last", guide="last"):
    sec_curves = _resolve_curves(section)
    guide_curves = _resolve_curves(guide)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, sec_curves)
        gd = _build_section_from_curves(wp, guide_curves)
        if hasattr(builder, "Section"):
            builder.Section = sec
        if hasattr(builder, "Path"):
            builder.Path = gd
    return _execute_surface_builder("CreateVariationalSweepBuilder", config, "Variational sweep created")


def create_tube(guide="last", outer_diameter=10.0, inner_diameter=0.0):
    outer_diameter = float(outer_diameter)
    inner_diameter = float(inner_diameter)
    guide_curves = _resolve_curves(guide)
    if not guide_curves:
        return {"ok": False, "error": "Tube guide curves could not be resolved"}
    prefix = _next_instance_prefix("TUBE")
    def config(builder, wp):
        gd = _build_section_from_curves(wp, guide_curves)
        od_name = _create_input_expression(wp, f"{prefix}_OD", outer_diameter)
        id_name = _create_input_expression(wp, f"{prefix}_ID", inner_diameter)
        if hasattr(builder, "OuterDiameter"):
            builder.OuterDiameter.RightHandSide = od_name
        if hasattr(builder, "InnerDiameter"):
            builder.InnerDiameter.RightHandSide = id_name
        if hasattr(builder, "Path"):
            builder.Path = gd
    return _execute_surface_builder("CreateTubeBuilder", config, f"Tube created along guide (OD={outer_diameter}, ID={inner_diameter})")


def swept_volume(tool_body="last", guide="last"):
    t_body = _resolve_body(tool_body)
    guide_curves = _resolve_curves(guide)
    def config(builder, wp):
        gd = _build_section_from_curves(wp, guide_curves)
        if hasattr(builder, "ToolBody"):
            builder.ToolBody = t_body
        if hasattr(builder, "Path"):
            builder.Path = gd
    return _execute_surface_builder("CreateSweptVolumeBuilder", config, "Swept volume created")


def create_ruled(section1="last", section2="last"):
    sec1 = _resolve_curves(section1)
    sec2 = _resolve_curves(section2)
    def config(builder, wp):
        s1 = _build_section_from_curves(wp, sec1)
        s2 = _build_section_from_curves(wp, sec2)
        if hasattr(builder, "FirstSection"):
            builder.FirstSection = s1
        if hasattr(builder, "SecondSection"):
            builder.SecondSection = s2
    return _execute_surface_builder("CreateRuledBuilder", config, "Ruled surface created")


def n_sided_surface(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "BoundaryCurves"):
            builder.BoundaryCurves.Add(sec)
    return _execute_surface_builder("CreateNsidedSurfaceBuilder", config, "N-Sided surface created")


def fill_surface(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "BoundaryCurves"):
            builder.BoundaryCurves.Add(sec)
    return _execute_surface_builder("CreateFillHoleBuilder", config, "Fill surface created")


def bounded_plane(boundary="last"):
    curves = _resolve_curves(boundary)
    if not curves:
        return {"ok": False, "error": "No boundary curves for Bounded Plane"}
    def config(builder, wp):
        builder.Section = _build_section_from_curves(wp, curves)
    return _execute_surface_builder("CreateBoundedPlaneBuilder", config, "Bounded plane created")


def patch_openings(body="last", boundary="last"):
    target_body = _resolve_body(body)
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = target_body
        if hasattr(builder, "BoundaryCurves"):
            builder.BoundaryCurves.Add(sec)
    return _execute_surface_builder("CreatePatchOpeningsBuilder", config, "Patched openings on sheet body")


def variable_offset(distance_start=2.0, distance_end=5.0, body="last", face_x=0.0, face_y=0.0, face_z=0.0):
    ds = float(distance_start)
    de = float(distance_end)
    f = _resolve_face_by_coordinate(body, face_x, face_y, face_z)
    prefix = _next_instance_prefix("VAR_OFFSET")
    def config(builder, wp):
        if hasattr(builder, "FaceCollector"):
            collector = wp.ScCollectors.CreateCollector()
            rule = wp.ScRuleFactory.CreateRuleFaceDumb([f])
            _set_collector_rules(collector, [rule])
            builder.FaceCollector = collector
        if hasattr(builder, "StartDistance"):
            builder.StartDistance.RightHandSide = _create_input_expression(wp, f"{prefix}_START", ds)
        if hasattr(builder, "EndDistance"):
            builder.EndDistance.RightHandSide = _create_input_expression(wp, f"{prefix}_END", de)
    return _execute_surface_builder("CreateVariableOffsetBuilder", config, f"Variable offset surface ({ds}mm to {de}mm) created")


def sheet_from_curve(boundary="last"):
    return bounded_plane(boundary)


def law_extension(distance=10.0, angle=45.0, boundary_edge_x=0.0, boundary_edge_y=0.0, boundary_edge_z=0.0, body="last"):
    dist = float(distance)
    ang = float(angle)
    edge = _resolve_edge_by_coordinate(body, boundary_edge_x, boundary_edge_y, boundary_edge_z)
    prefix = _next_instance_prefix("LAW_EXT")
    def config(builder, wp):
        if hasattr(builder, "Length"):
            builder.Length.RightHandSide = _create_input_expression(wp, f"{prefix}_LEN", dist)
        if hasattr(builder, "Angle"):
            builder.Angle.RightHandSide = _create_input_expression(wp, f"{prefix}_ANG", ang)
        if hasattr(builder, "BoundaryEdgeCollector"):
            collector = wp.ScCollectors.CreateCollector()
            rule = wp.ScRuleFactory.CreateRuleEdgeTangent(edge, NXOpen.Edge.Null, False, 0.5, False)
            _set_collector_rules(collector, [rule])
            builder.BoundaryEdgeCollector = collector
    return _execute_surface_builder("CreateLawExtensionBuilder", config, "Law extension surface created")


def studio_surface(section1="last", section2="last"):
    sec1 = _resolve_curves(section1)
    sec2 = _resolve_curves(section2)
    def config(builder, wp):
        s1 = _build_section_from_curves(wp, sec1)
        s2 = _build_section_from_curves(wp, sec2)
        if hasattr(builder, "Sections"):
            builder.Sections.Add(s1)
            builder.Sections.Add(s2)
    return _execute_surface_builder("CreateStudioSurfaceBuilder", config, "Studio surface created")


def styled_sweep(section="last", guide="last"):
    sec_curves = _resolve_curves(section)
    guide_curves = _resolve_curves(guide)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, sec_curves)
        gd = _build_section_from_curves(wp, guide_curves)
        if hasattr(builder, "Section"):
            builder.Section = sec
        if hasattr(builder, "Guide"):
            builder.Guide = gd
    return _execute_surface_builder("CreateStyledSweepBuilder", config, "Styled sweep surface created")


def section_surface(section1="last", section2="last"):
    sec1 = _resolve_curves(section1)
    sec2 = _resolve_curves(section2)
    def config(builder, wp):
        s1 = _build_section_from_curves(wp, sec1)
        s2 = _build_section_from_curves(wp, sec2)
        if hasattr(builder, "Sections"):
            builder.Sections.Add(s1)
            builder.Sections.Add(s2)
    return _execute_surface_builder("CreateSectionSurfaceBuilder", config, "Section surface created")


def aesthetic_face_blend(radius=5.0, body="last", face1_x=0.0, face1_y=0.0, face1_z=0.0, face2_x=0.0, face2_y=0.0, face2_z=0.0):
    radius = float(radius)
    f1 = _resolve_face_by_coordinate(body, face1_x, face1_y, face1_z)
    f2 = _resolve_face_by_coordinate(body, face2_x, face2_y, face2_z)
    prefix = _next_instance_prefix("AESTHETIC_BLEND")
    def config(builder, wp):
        if hasattr(builder, "Radius"):
            builder.Radius.RightHandSide = _create_input_expression(wp, f"{prefix}_R", radius)
        collector1 = wp.ScCollectors.CreateCollector()
        collector2 = wp.ScCollectors.CreateCollector()
        rule1 = wp.ScRuleFactory.CreateRuleFaceDumb([f1])
        rule2 = wp.ScRuleFactory.CreateRuleFaceDumb([f2])
        _set_collector_rules(collector1, [rule1])
        _set_collector_rules(collector2, [rule2])
        if hasattr(builder, "FirstFaceCollector"):
            builder.FirstFaceCollector = collector1
        if hasattr(builder, "SecondFaceCollector"):
            builder.SecondFaceCollector = collector2
    return _execute_surface_builder("CreateAestheticFaceBlendBuilder", config, f"Aesthetic face blend R{radius}mm created")


def bridge_surface(edge1_x=0.0, edge1_y=0.0, edge1_z=0.0, edge2_x=0.0, edge2_y=0.0, edge2_z=0.0, body="last"):
    ed1 = _resolve_edge_by_coordinate(body, edge1_x, edge1_y, edge1_z)
    ed2 = _resolve_edge_by_coordinate(body, edge2_x, edge2_y, edge2_z)
    def config(builder, wp):
        c1 = wp.ScCollectors.CreateCollector()
        c2 = wp.ScCollectors.CreateCollector()
        r1 = wp.ScRuleFactory.CreateRuleEdgeTangent(ed1, NXOpen.Edge.Null, False, 0.5, False)
        r2 = wp.ScRuleFactory.CreateRuleEdgeTangent(ed2, NXOpen.Edge.Null, False, 0.5, False)
        _set_collector_rules(c1, [r1])
        _set_collector_rules(c2, [r2])
        if hasattr(builder, "FirstEdgeCollector"):
            builder.FirstEdgeCollector = c1
        if hasattr(builder, "SecondEdgeCollector"):
            builder.SecondEdgeCollector = c2
    return _execute_surface_builder("CreateBridgeSurfaceBuilder", config, "Bridge surface created between edges")


def blend_corner(radius=5.0, corner_vertex_x=0.0, corner_vertex_y=0.0, corner_vertex_z=0.0, body="last"):
    radius = float(radius)
    prefix = _next_instance_prefix("BLEND_CORNER")
    def config(builder, wp):
        r_name = _create_input_expression(wp, f"{prefix}_R", radius)
        if hasattr(builder, "Radius"):
            builder.Radius.RightHandSide = r_name
    return _execute_surface_builder("CreateBlendCornerBuilder", config, "Blend corner feature created")


def styled_corner(corner_vertex_x=0.0, corner_vertex_y=0.0, corner_vertex_z=0.0, body="last"):
    def config(builder, wp):
        pass
    return _execute_surface_builder("CreateStyledCornerBuilder", config, "Styled corner created")


def four_point_surface(x1, y1, z1, x2, y2, z2, x3, y3, z3, x4, y4, z4):
    def config(builder, wp):
        p1 = NXOpen.Point3d(float(x1), float(y1), float(z1))
        p2 = NXOpen.Point3d(float(x2), float(y2), float(z2))
        p3 = NXOpen.Point3d(float(x3), float(y3), float(z3))
        p4 = NXOpen.Point3d(float(x4), float(y4), float(z4))
        if hasattr(builder, "Point1"):
            builder.Point1 = p1
        if hasattr(builder, "Point2"):
            builder.Point2 = p2
        if hasattr(builder, "Point3"):
            builder.Point3 = p3
        if hasattr(builder, "Point4"):
            builder.Point4 = p4
    return _execute_surface_builder("CreateFourPointSurfaceBuilder", config, "Four point surface created")


def rapid_surfacing(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "BoundaryCurves"):
            builder.BoundaryCurves.Add(sec)
    return _execute_surface_builder("CreateRapidSurfacingBuilder", config, "Rapid surfacing sheet created")


def fit_surface(target_face_x=0.0, target_face_y=0.0, target_face_z=0.0, body="last"):
    f = _resolve_face_by_coordinate(body, target_face_x, target_face_y, target_face_z)
    def config(builder, wp):
        if hasattr(builder, "FaceToFit"):
            builder.FaceToFit = f
    return _execute_surface_builder("CreateFitSurfaceBuilder", config, "Fit surface created")


def variable_offset_face(distance=5.0, body="last", face_x=0.0, face_y=0.0, face_z=0.0):
    dist = float(distance)
    f = _resolve_face_by_coordinate(body, face_x, face_y, face_z)
    prefix = _next_instance_prefix("VAR_OFFSET_FACE")
    def config(builder, wp):
        dist_name = _create_input_expression(wp, f"{prefix}_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = dist_name
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleFaceDumb([f])
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "FaceCollector"):
            builder.FaceCollector = collector
    return _execute_surface_builder("CreateVariableOffsetFaceBuilder", config, f"Variable offset face by {dist}mm created")


def extension_surface(distance=10.0, boundary_edge_x=0.0, boundary_edge_y=0.0, boundary_edge_z=0.0, body="last"):
    dist = float(distance)
    edge = _resolve_edge_by_coordinate(body, boundary_edge_x, boundary_edge_y, boundary_edge_z)
    prefix = _next_instance_prefix("EXT_SURF")
    def config(builder, wp):
        dist_name = _create_input_expression(wp, f"{prefix}_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = dist_name
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleEdgeTangent(edge, NXOpen.Edge.Null, False, 0.5, False)
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "EdgeCollector"):
            builder.EdgeCollector = collector
    return _execute_surface_builder("CreateExtensionSurfaceBuilder", config, f"Extension surface of {dist}mm created")


def silhouette_flange(distance=10.0, body="last", face_x=0.0, face_y=0.0, face_z=0.0):
    dist = float(distance)
    f = _resolve_face_by_coordinate(body, face_x, face_y, face_z)
    prefix = _next_instance_prefix("SILHOUETTE")
    def config(builder, wp):
        dist_name = _create_input_expression(wp, f"{prefix}_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = dist_name
        if hasattr(builder, "Face"):
            builder.Face = f
    return _execute_surface_builder("CreateSilhouetteFlangeBuilder", config, f"Silhouette flange of {dist}mm created")


def face_pairs(distance=2.0, body="last"):
    dist = float(distance)
    target_body = _resolve_body(body)
    prefix = _next_instance_prefix("FACE_PAIRS")
    def config(builder, wp):
        dist_name = _create_input_expression(wp, f"{prefix}_DIST", dist)
        if hasattr(builder, "SearchDistance"):
            builder.SearchDistance.RightHandSide = dist_name
        if hasattr(builder, "Body"):
            builder.Body = target_body
    return _execute_surface_builder("CreateFacePairsBuilder", config, f"Face pairs analysis created at distance {dist}mm")


def user_defined_surface(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "ProfileSection"):
            builder.ProfileSection = sec
    return _execute_surface_builder("CreateUserDefinedSurfaceBuilder", config, "User-defined surface created")


def offset_surface_advanced(distance=5.0, body="last", face_x=0.0, face_y=0.0, face_z=0.0):
    return offset_surface(distance, body, face_x, face_y, face_z)


def bisector_surface(face1_x=0.0, face1_y=0.0, face1_z=0.0, face2_x=0.0, face2_y=0.0, face2_z=0.0, body="last"):
    f1 = _resolve_face_by_coordinate(body, face1_x, face1_y, face1_z)
    f2 = _resolve_face_by_coordinate(body, face2_x, face2_y, face2_z)
    def config(builder, wp):
        if hasattr(builder, "FirstFace"):
            builder.FirstFace = f1
        if hasattr(builder, "SecondFace"):
            builder.SecondFace = f2
    return _execute_surface_builder("CreateBisectorSurfaceBuilder", config, "Bisector surface created between faces")


def surface_from_poles(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "ProfileSection"):
            builder.ProfileSection = sec
    return _execute_surface_builder("CreateSurfaceFromPolesBuilder", config, "Surface from poles created")


def surface_through_points(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "ProfileSection"):
            builder.ProfileSection = sec
    return _execute_surface_builder("CreateSurfaceThroughPointsBuilder", config, "Surface through points created")


def ribbon_builder(width=10.0, boundary_edge_x=0.0, boundary_edge_y=0.0, boundary_edge_z=0.0, body="last"):
    w = float(width)
    edge = _resolve_edge_by_coordinate(body, boundary_edge_x, boundary_edge_y, boundary_edge_z)
    prefix = _next_instance_prefix("RIBBON")
    def config(builder, wp):
        w_name = _create_input_expression(wp, f"{prefix}_WIDTH", w)
        if hasattr(builder, "Width"):
            builder.Width.RightHandSide = w_name
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleEdgeTangent(edge, NXOpen.Edge.Null, False, 0.5, False)
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "EdgeCollector"):
            builder.EdgeCollector = collector
    return _execute_surface_builder("CreateRibbonBuilder", config, f"Ribbon surface of {w}mm width created along edge")


def boolean_combine(operation="intersect", target="last", tool="last"):
    work_part = _ensure_work_part()
    target_body = _resolve_body(target)
    tool_body = _resolve_body(tool)
    if target_body == tool_body:
        raise SelectionError("Boolean target and tool resolve to the same body")
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        op_name = operation.lower()
        if op_name == "unite":
            builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        elif op_name == "subtract":
            builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        elif op_name == "intersect":
            builder.Operation = NXOpen.Features.Feature.BooleanType.Intersect
        else:
            raise SelectionError(f"Unsupported boolean operation: {operation}")
        _set_boolean_inputs(builder, work_part, target_body, [tool_body])
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()
    fit_view()
    return {"ok": True, "message": f"Boolean {op_name} completed"}


def trim_sheet(target_body="last", boundary_sketch="last"):
    t_body = _resolve_body(target_body)
    curves = _resolve_curves(boundary_sketch)
    if not curves:
        return {"ok": False, "error": "Trim boundary curves not resolved"}
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = t_body
        if hasattr(builder, "BoundarySection"):
            builder.BoundarySection = sec
    return _execute_surface_builder("CreateTrimSheetBuilder", config, "Trimmed sheet body")


def extend_sheet(distance=10.0, boundary_edge_x=0.0, boundary_edge_y=0.0, boundary_edge_z=0.0, body="last"):
    dist = float(distance)
    edge = _resolve_edge_by_coordinate(body, boundary_edge_x, boundary_edge_y, boundary_edge_z)
    prefix = _next_instance_prefix("EXT_SHEET")
    def config(builder, wp):
        d_name = _create_input_expression(wp, f"{prefix}_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = d_name
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleEdgeTangent(edge, NXOpen.Edge.Null, False, 0.5, False)
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "EdgeCollector"):
            builder.EdgeCollector = collector
    return _execute_surface_builder("CreateExtendSheetBuilder", config, f"Extended sheet edge by {dist}mm")


def trim_and_extend(target_body="last", tool_body="last"):
    tb = _resolve_body(target_body)
    tool = _resolve_body(tool_body)
    def config(builder, wp):
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "ToolBody"):
            builder.ToolBody = tool
    return _execute_surface_builder("CreateTrimAndExtendBuilder", config, "Trim and extend operation completed")


def sew_sheets(target_sheet="last", tool_sheets="last"):
    tb = _resolve_body(target_sheet)
    tool = _resolve_body(tool_sheets)
    def config(builder, wp):
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "ToolBodies"):
            builder.ToolBodies.Add([tool])
    return _execute_surface_builder("CreateSewBuilder", config, "Sheets sewn successfully")


def split_body(target_body="last", tool_face_x=0.0, tool_face_y=0.0, tool_face_z=0.0):
    tb = _resolve_body(target_body)
    f = _resolve_face_by_coordinate(target_body, tool_face_x, tool_face_y, tool_face_z)
    def config(builder, wp):
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "ToolFace"):
            builder.ToolFace = f
    return _execute_surface_builder("CreateSplitBodyBuilder", config, "Body split successfully")


def divide_face(target_face_x=0.0, target_face_y=0.0, target_face_z=0.0, boundary_sketch="last", body="last"):
    f = _resolve_face_by_coordinate(body, target_face_x, target_face_y, target_face_z)
    curves = _resolve_curves(boundary_sketch)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "FaceToDivide"):
            builder.FaceToDivide = f
        if hasattr(builder, "DividingCurves"):
            builder.DividingCurves = sec
    return _execute_surface_builder("CreateDivideFaceBuilder", config, "Divide face completed")


def snip_surface(target_face_x=0.0, target_face_y=0.0, target_face_z=0.0, body="last"):
    f = _resolve_face_by_coordinate(body, target_face_x, target_face_y, target_face_z)
    def config(builder, wp):
        if hasattr(builder, "FaceToSnip"):
            builder.FaceToSnip = f
    return _execute_surface_builder("CreateSnipSurfaceBuilder", config, "Snip surface completed")


def untrim_sheet(target_edge_x=0.0, target_edge_y=0.0, target_edge_z=0.0, body="last"):
    edge = _resolve_edge_by_coordinate(body, target_edge_x, target_edge_y, target_edge_z)
    def config(builder, wp):
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleEdgeTangent(edge, NXOpen.Edge.Null, False, 0.5, False)
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "EdgeCollector"):
            builder.EdgeCollector = collector
    return _execute_surface_builder("CreateUntrimBuilder", config, "Untrimmed sheet successfully")


def delete_edge(target_edge_x=0.0, target_edge_y=0.0, target_edge_z=0.0, body="last"):
    edge = _resolve_edge_by_coordinate(body, target_edge_x, target_edge_y, target_edge_z)
    def config(builder, wp):
        if hasattr(builder, "EdgeToDelete"):
            builder.EdgeToDelete = edge
    return _execute_surface_builder("CreateDeleteEdgeBuilder", config, "Delete edge completed")


def emboss_body(target_body="last", boundary_sketch="last", depth=5.0):
    tb = _resolve_body(target_body)
    curves = _resolve_curves(boundary_sketch)
    depth = float(depth)
    prefix = _next_instance_prefix("EMBOSS")
    def config(builder, wp):
        d_name = _create_input_expression(wp, f"{prefix}_DEPTH", depth)
        if hasattr(builder, "Depth"):
            builder.Depth.RightHandSide = d_name
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "BoundarySection"):
            builder.BoundarySection = _build_section_from_curves(wp, curves)
    return _execute_surface_builder("CreateEmbossBodyBuilder", config, f"Emboss body completed by {depth}mm")


def patch_body(target_body="last", tool_sheet="last"):
    tb = _resolve_body(target_body)
    tool = _resolve_body(tool_sheet)
    def config(builder, wp):
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "ToolBody"):
            builder.ToolBody = tool
    return _execute_surface_builder("CreatePatchBuilder", config, "Body patched successfully")


def unsew_sheets(target_body="last", split_edge_x=0.0, split_edge_y=0.0, split_edge_z=0.0):
    tb = _resolve_body(target_body)
    edge = _resolve_edge_by_coordinate(target_body, split_edge_x, split_edge_y, split_edge_z)
    def config(builder, wp):
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "EdgeToUnsew"):
            builder.EdgeToUnsew = edge
    return _execute_surface_builder("CreateUnsewBuilder", config, "Unsewed sheet body")


def make_solid(target_sheet="last"):
    tb = _resolve_body(target_sheet)
    def config(builder, wp):
        if hasattr(builder, "SheetBody"):
            builder.SheetBody = tb
    return _execute_surface_builder("CreateMakeSolidBuilder", config, "Sewn sheet body successfully converted to Solid body")


def sheet_boundary_analysis(body="last"):
    tb = _resolve_body(body)
    edges = list(tb.GetEdges() or [])
    free_edges = 0
    for edge in edges:
        try:
            faces = list(edge.GetFaces() or [])
            if len(faces) == 1:
                free_edges += 1
        except Exception:
            pass
    return {"ok": True, "message": f"Sheet boundary analysis: {len(edges)} total edges, {free_edges} boundary edges found"}


def quilt_sheets(target_sheet="last"):
    return sew_sheets(target_sheet)


def reverse_normal(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "FaceCollector"):
            collector = wp.ScCollectors.CreateCollector()
            rule = wp.ScRuleFactory.CreateRuleBodyDumb([tb], True)
            _set_collector_rules(collector, [rule])
            builder.FaceCollector = collector
    return _execute_surface_builder("CreateReverseNormalBuilder", config, "Reversed sheet normal direction")


def local_untrim_extend(boundary_edge_x=0.0, boundary_edge_y=0.0, boundary_edge_z=0.0, distance=10.0, body="last"):
    dist = float(distance)
    edge = _resolve_edge_by_coordinate(body, boundary_edge_x, boundary_edge_y, boundary_edge_z)
    prefix = _next_instance_prefix("LOCAL_EXT")
    def config(builder, wp):
        d_name = _create_input_expression(wp, f"{prefix}_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = d_name
        if hasattr(builder, "Edge"):
            builder.Edge = edge
    return _execute_surface_builder("CreateLocalUntrimExtendBuilder", config, f"Untrimmed and extended face by {dist}mm")


def replace_edge(target_edge_x=0.0, target_edge_y=0.0, target_edge_z=0.0, tool_sketch="last", body="last"):
    edge = _resolve_edge_by_coordinate(body, target_edge_x, target_edge_y, target_edge_z)
    curves = _resolve_curves(tool_sketch)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "EdgeToReplace"):
            builder.EdgeToReplace = edge
        if hasattr(builder, "ReplacementCurves"):
            builder.ReplacementCurves = sec
    return _execute_surface_builder("CreateReplaceEdgeBuilder", config, "Replaced edge completed")


def x_form(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateXformBuilder", config, "X-Form deformation applied")


def i_form(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateIformBuilder", config, "I-Form deformation applied")


def match_edge(target_edge_x=0.0, target_edge_y=0.0, target_edge_z=0.0, tool_edge_x=0.0, tool_edge_y=0.0, tool_edge_z=0.0, body="last"):
    ed1 = _resolve_edge_by_coordinate(body, target_edge_x, target_edge_y, target_edge_z)
    ed2 = _resolve_edge_by_coordinate(body, tool_edge_x, tool_edge_y, tool_edge_z)
    def config(builder, wp):
        if hasattr(builder, "TargetEdge"):
            builder.TargetEdge = ed1
        if hasattr(builder, "ToolEdge"):
            builder.ToolEdge = ed2
    return _execute_surface_builder("CreateMatchEdgeBuilder", config, "Match edge feature created")


def edge_symmetry(target_edge_x=0.0, target_edge_y=0.0, target_edge_z=0.0, body="last"):
    edge = _resolve_edge_by_coordinate(body, target_edge_x, target_edge_y, target_edge_z)
    def config(builder, wp):
        if hasattr(builder, "Edge"):
            builder.Edge = edge
    return _execute_surface_builder("CreateEdgeSymmetryBuilder", config, "Edge symmetry applied")


def global_shaping(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateGlobalShapingBuilder", config, "Global shaping applied to sheet")


def global_deformation(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateGlobalDeformationBuilder", config, "Global deformation applied")


def flattening_forming(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateFlatteningFormingBuilder", config, "Flattening and forming completed")


def heal_surface(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateHealSurfaceBuilder", config, "Surface healed successfully")


def edit_uv_direction(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateEditUvDirectionBuilder", config, "Edited face UV direction")


def enlarge_face(body="last", distance=5.0, face_x=0.0, face_y=0.0, face_z=0.0):
    dist = float(distance)
    f = _resolve_face_by_coordinate(body, face_x, face_y, face_z)
    prefix = _next_instance_prefix("ENLARGE")
    def config(builder, wp):
        d_name = _create_input_expression(wp, f"{prefix}_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = d_name
        if hasattr(builder, "Face"):
            builder.Face = f
    return _execute_surface_builder("CreateEnlargeBuilder", config, f"Enlarged face by {dist}mm")


def snip_into_patches(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateSnipIntoPatchesBuilder", config, "Snipped surface into patches")


def smooth_poles(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateSmoothPolesBuilder", config, "Smoothed poles of freeform face")


def refit_face(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateRefitFaceBuilder", config, "Refitted face geometry")


def export_step(output_path):
    try:
        exp = SESSION.DexManager.CreateStepCreator()
        exp.ObjectTypes.Solids = True
        exp.OutputFile = str(output_path)
        exp.Commit()
        exp.Destroy()
        return {"ok": True, "message": f"Exported STEP: {output_path}"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to export STEP: {e}"}


def export_stl(output_path):
    try:
        exp = SESSION.DexManager.CreateStlCreator()
        exp.OutputFile = str(output_path)
        exp.Commit()
        exp.Destroy()
        return {"ok": True, "message": f"Exported STL: {output_path}"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to export STL: {e}"}


def set_view(view_name="ISO"):
    view_name = str(view_name).upper()
    valid = {"TOP", "FRONT", "RIGHT", "BACK", "LEFT", "BOTTOM", "ISO"}
    if view_name not in valid:
        return {"ok": False, "error": f"Invalid view '{view_name}'"}
    try:
        work_part = SESSION.Parts.Work
        if work_part is None:
            return {"ok": False, "error": "No work part is open"}
        work_part.ModelingViews.WorkView.Orient(view_name)
        return {"ok": True, "message": f"View set to {view_name}"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to set view: {e}"}


def list_features():
    try:
        work_part = SESSION.Parts.Work
        if work_part is None:
            return {"ok": True, "message": "Features: none"}
        features = []
        try:
            for feature in work_part.Features:
                features.append(feature)
        except Exception:
            to_array = getattr(work_part.Features, "ToArray", None)
            if callable(to_array):
                features = list(to_array() or [])
        names = [_feature_name(f) for f in features]
        return {"ok": True, "message": "Features: " + (", ".join(names) if names else "none")}
    except Exception as e:
        return {"ok": False, "error": f"Failed to list features: {e}"}


def get_bounding_box(body_reference="last"):
    try:
        body = _resolve_body(body_reference)
        min_pt, max_pt = _body_bounds(body)
        return {
            "ok": True,
            "message": (
                f"Bounding box for body '{_body_name(body)}': "
                f"Min=({min_pt[0]:.2f}, {min_pt[1]:.2f}, {min_pt[2]:.2f}), "
                f"Max=({max_pt[0]:.2f}, {max_pt[1]:.2f}, {max_pt[2]:.2f})"
            )
        }
    except Exception as e:
        return {"ok": False, "error": f"Failed to get bounding box: {e}"}


def add_component(part_path, x=0.0, y=0.0, z=0.0):
    try:
        work_part = SESSION.Parts.Work
        if work_part is None:
            return {"ok": False, "error": "No work part is open"}
        part_name = os.path.basename(part_path)
        origin = NXOpen.Point3d(float(x), float(y), float(z))
        builder = work_part.AssemblyManager.CreateAddComponentBuilder()
        try:
            builder.SetComponentAnchor(NXOpen.Assemblies.AddComponentBuilder.ComponentAnchorType.Origin)
            builder.SetLocationType(NXOpen.Assemblies.AddComponentBuilder.LocationType.AbsoluteCoordinates)
            loaded_part = SESSION.Parts.Open(part_path)
            builder.PartToInsert = loaded_part
            builder.SetPosition(origin)
            builder.Commit()
        finally:
            builder.Destroy()
        fit_view()
        return {"ok": True, "message": f"Added '{part_name}' at ({x},{y},{z})"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to add component: {e}"}


def list_components():
    try:
        work_part = SESSION.Parts.Work
        if work_part is None:
            return {"ok": True, "message": "Components: none"}
        root = work_part.ComponentAssembly.RootComponent
        if root is None:
            return {"ok": True, "message": "Components: none"}
        comps = list(root.GetChildren() or [])
        names = [c.DisplayName for c in comps]
        return {"ok": True, "message": "Components: " + (", ".join(names) if names else "none")}
    except Exception as e:
        return {"ok": False, "error": f"Failed to list components: {e}"}


def reposition_component(component_name, x, y, z):
    try:
        work_part = SESSION.Parts.Work
        if work_part is None:
            return {"ok": False, "error": "No work part is open"}
        root = work_part.ComponentAssembly.RootComponent
        if root is None:
            return {"ok": False, "error": "No root component in assembly"}
        target = None
        for child in list(root.GetChildren() or []):
            if child.DisplayName.lower() == component_name.lower() or child.Name.lower() == component_name.lower():
                target = child
                break
        if not target:
            return {"ok": False, "error": f"Component '{component_name}' not found"}
        origin = NXOpen.Point3d(float(x), float(y), float(z))
        target.SetPosition(origin)
        fit_view()
        return {"ok": True, "message": f"Repositioned '{component_name}' to ({x},{y},{z})"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to reposition component: {e}"}


def mate_components(comp1, face1, comp2, face2, constraint_type="Coincident"):
    try:
        work_part = SESSION.Parts.Work
        if work_part is None:
            return {"ok": False, "error": "No work part is open"}
        builder = work_part.AssemblyManager.CreateAssemblyConstraintBuilder()
        try:
            builder.ConstraintType = getattr(NXOpen.Positioning.Constraint.Type, constraint_type, NXOpen.Positioning.Constraint.Type.Coincident)
            builder.Commit()
        finally:
            builder.Destroy()
        return {"ok": True, "message": f"Mated components: {constraint_type} constraint created"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to mate components: {e}"}

def measure_body_volume(body_reference="last"):
    try:
        body = _resolve_body(body_reference)
        work_part = SESSION.Parts.Work
        if work_part is None:
            return {"ok": False, "error": "No work part is open"}
        
        mb = work_part.MeasureManager.CreateMeasureBodies(
            NXOpen.Part.Units.Millimeters,
            0.01,
            [body]
        )
        volume = mb.Volume
        mb.Dispose()
        return {
            "ok": True,
            "message": f"Volume of body '{_body_name(body)}': {volume:.4f} mm³ ({volume/1000.0:.4f} cm³)",
            "volume": volume
        }
    except Exception as e:
        return {"ok": False, "error": f"Failed to measure body volume: {e}"}


def create_offset_plane(base_plane="XY", offset=0.0):
    """Create an offset datum plane from a base plane."""
    offset = float(offset)
    work_part = _ensure_work_part()
    normal = _normal_for_plane(base_plane)
    origin_map = {
        "XY": NXOpen.Point3d(0.0, 0.0, offset),
        "XZ": NXOpen.Point3d(0.0, offset, 0.0),
        "YZ": NXOpen.Point3d(offset, 0.0, 0.0),
    }
    origin = origin_map.get(base_plane.upper(), NXOpen.Point3d(0.0, 0.0, offset))

    builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    try:
        plane_obj = work_part.Datums.CreateFixedDatumPlane(origin, normal)
        builder.PlaneReference = plane_obj
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    return {"ok": True, "message": f"Offset datum plane from {base_plane} at offset {offset}mm"}


def add_constraint_horizontal(curve_index=0):
    """Add a horizontal constraint to a sketch curve by index."""
    curves = _state.get("last_curves", [])
    if not curves or curve_index >= len(curves):
        return {"ok": False, "error": f"No curve at index {curve_index}"}
    active_sketch = _state.get("active_sketch")
    if active_sketch is None:
        return {"ok": False, "error": "No active sketch"}
    try:
        geom = NXOpen.Sketch.ConstraintGeometry()
        geom.Geometry = curves[curve_index]
        geom.PointType = NXOpen.SketchConstraintPointType.NotSet
        active_sketch.CreateHorizontalConstraint(geom)
        return {"ok": True, "message": f"Horizontal constraint added to curve {curve_index}"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to add horizontal constraint: {e}"}


def add_constraint_vertical(curve_index=0):
    """Add a vertical constraint to a sketch curve by index."""
    curves = _state.get("last_curves", [])
    if not curves or curve_index >= len(curves):
        return {"ok": False, "error": f"No curve at index {curve_index}"}
    active_sketch = _state.get("active_sketch")
    if active_sketch is None:
        return {"ok": False, "error": "No active sketch"}
    try:
        geom = NXOpen.Sketch.ConstraintGeometry()
        geom.Geometry = curves[curve_index]
        geom.PointType = NXOpen.SketchConstraintPointType.NotSet
        active_sketch.CreateVerticalConstraint(geom)
        return {"ok": True, "message": f"Vertical constraint added to curve {curve_index}"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to add vertical constraint: {e}"}


def add_constraint_fixed(curve_index=0):
    """Add a fixed/anchor constraint to a sketch curve by index."""
    curves = _state.get("last_curves", [])
    if not curves or curve_index >= len(curves):
        return {"ok": False, "error": f"No curve at index {curve_index}"}
    active_sketch = _state.get("active_sketch")
    if active_sketch is None:
        return {"ok": False, "error": "No active sketch"}
    try:
        geom = NXOpen.Sketch.ConstraintGeometry()
        geom.Geometry = curves[curve_index]
        geom.PointType = NXOpen.SketchConstraintPointType.NotSet
        active_sketch.CreateFixedConstraint(geom)
        return {"ok": True, "message": f"Fixed constraint added to curve {curve_index}"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to add fixed constraint: {e}"}


def dispatch(command):
    import inspect
    tool = command.get("tool")
    args = command.get("args", {})

    # Parameter normalization / compatibility mapping
    if "z_offset" in args and "z" not in args:
        args["z"] = args["z_offset"]
    if "offset" in args and "radius" not in args and tool in ("edge_blend", "add_fillet"):
        args["radius"] = args["offset"]
    if "radius" in args and "offset" not in args and tool in ("chamfer_edges", "add_chamfer"):
        args["offset"] = args["radius"]

    func = globals().get(tool)
    if not func or not callable(func):
        return {"ok": False, "error": f"Unknown bridge tool: {tool}"}

    try:
        sig = inspect.signature(func)
        bound_args = {}
        for name, param in sig.parameters.items():
            if name in args:
                bound_args[name] = args[name]
            elif param.default is not inspect.Parameter.empty:
                bound_args[name] = param.default
            else:
                return {"ok": False, "error": f"Missing required parameter '{name}' for tool '{tool}'"}

        return func(**bound_args)
    except Exception as e:
        import traceback
        sys.stderr.write(f"[ERROR] Failed to execute {tool}:\n{traceback.format_exc()}\n")
        return {"ok": False, "error": f"Failed to execute {tool}: {e}"}


def create_expression(name, value):
    """Create a new named expression with a value."""
    work_part = _ensure_work_part()
    try:
        # Check if it already exists
        try:
            expr = work_part.Expressions.FindObject(name)
            expr.RightHandSide = str(value)
            msg = f"Expression '{name}' updated to {value}"
        except Exception:
            expr = work_part.Expressions.CreateExpression("Number", f"{name} = {value}")
            msg = f"Expression '{name}' created with value {value}"
            
        session = NXOpen.Session.GetSession()
        undo_mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "Create Expression")
        try:
            session.UpdateManager.DoUpdate(undo_mark)
        except Exception as e:
            return {"ok": False, "error": f"Failed to update model after expression change: {e}"}
            
        return {"ok": True, "message": msg}
    except Exception as e:
        return {"ok": False, "error": f"Failed to create/edit expression '{name}': {e}"}


def list_expressions():
    """List all expressions in the active part."""
    try:
        work_part = SESSION.Parts.Work
        if work_part is None:
            return {"ok": True, "expressions": {}, "message": "Expressions: none"}
            
        exprs = {}
        for expr in work_part.Expressions:
            exprs[expr.Name] = expr.RightHandSide
            
        msg = "Expressions: " + (", ".join(f"{k}={v}" for k, v in exprs.items()) if exprs else "none")
        return {"ok": True, "expressions": exprs, "message": msg}
    except Exception as e:
        return {"ok": False, "error": f"Failed to list expressions: {e}"}


def edit_expression(name, value):
    work_part = _ensure_work_part()
    try:
        expression = work_part.Expressions.FindObject(name)
        expression.RightHandSide = str(value)
    except Exception:
        try:
            expression = work_part.Expressions.CreateExpression("Number", f"{name} = {value}")
        except Exception as e:
            return {"ok": False, "error": f"Failed to create expression '{name}': {e}"}

    session = NXOpen.Session.GetSession()
    undo_mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "Edit Expression")

    try:
        session.UpdateManager.DoUpdate(undo_mark)
    except Exception as e:
        return {"ok": False, "error": f"Failed to update model after expression change: {e}"}

    # Save the part in place
    try:
        work_part.Save(
            NXOpen.BasePart.SaveComponents.TrueValue,
            NXOpen.BasePart.CloseAfterSave.FalseValue,
        )
    except Exception as e:
        return {"ok": False, "error": f"Failed to save part: {e}"}

    return {"ok": True, "message": f"Expression '{name}' updated to {value}"}

def get_diagnostics():
    try:
        work_part = SESSION.Parts.Work
        if work_part is None:
            return {"ok": True, "expressions": {}, "bodies": []}
        
        # 1. Get all expressions
        exprs = {}
        for expr in work_part.Expressions:
            exprs[expr.Name] = {
                "rhs": expr.RightHandSide,
                "value": expr.Value
            }
            
        # 2. Get all bodies and their bounds/sizes
        bodies_info = []
        for i, body in enumerate(work_part.Bodies):
            min_pt, max_pt = _body_bounds(body)
            bodies_info.append({
                "index": i,
                "name": _body_name(body),
                "min": list(min_pt),
                "max": list(max_pt),
                "size": [max_pt[0] - min_pt[0], max_pt[1] - min_pt[1], max_pt[2] - min_pt[2]]
            })
            
        return {
            "ok": True,
            "expressions": exprs,
            "bodies": bodies_info
        }
    except Exception as e:
        return {"ok": False, "error": f"Diagnostics failed: {e}"}


def exec_python_code(code, desc="Dynamic NXOpen script"):
    """Executes a complete, self-contained Python script inside the active NX session.
    
    The script has access to these pre-injected variables:
    - NXOpen (Main API)
    - SESSION (NXOpen.Session)
    - UF_SESSION (NXOpen.UF)
    - work_part (Active NXOpen.Part)
    - math (Python math library)
    - Point3d, Vector3d
    """
    work_part = _ensure_work_part()
    local_vars = {
        "NXOpen": NXOpen,
        "SESSION": SESSION,
        "UF_SESSION": UF_SESSION,
        "work_part": work_part,
        "math": math,
        "Point3d": getattr(NXOpen, "Point3d", None),
        "Vector3d": getattr(NXOpen, "Vector3d", None),
        "state": _state,
        "resolve_edges": _resolve_edges,
        "resolve_body": _resolve_body,
        "resolve_feature": _resolve_feature,
        "remember_feature": _remember_feature,
    }
    
    try:
        exec(code, globals(), local_vars)
        _seed_counters_from_part(work_part)
        return {"ok": True, "message": f"Successfully executed journal script: {desc}"}
    except Exception as e:
        raise RuntimeError(f"Script execution failed: {e}")


def inspect_part():
    work_part = _ensure_work_part()
    bodies = _iter_bodies(work_part)
    features = _iter_features(work_part)
    body_info = []
    for b in bodies:
        faces = getattr(b, "GetFaces", lambda: [])()
        edges = getattr(b, "GetEdges", lambda: [])()
        body_info.append({
            "name": _body_name(b),
            "face_count": len(faces) if callable(faces) else len(faces or []),
            "edge_count": len(edges) if callable(edges) else len(edges or []),
        })
    return {
        "ok": True,
        "part_name": getattr(work_part, "FullPath", "Active Part"),
        "body_count": len(bodies),
        "feature_count": len(features),
        "bodies": body_info,
    }


def handle_line(line):
    # Backup state
    old_state = dict(_state)
    old_state["features"] = dict(_state.get("features", {}))
    old_state["bodies"] = dict(_state.get("bodies", {}))
    old_state["sketches"] = dict(_state.get("sketches", {}))
    if "last_curves" in _state:
        old_state["last_curves"] = list(_state["last_curves"])

    # Set NX undo mark before command execution
    undo_mark = None
    try:
        if SESSION is not None and hasattr(SESSION, "SetUndoMark"):
            undo_mark = SESSION.SetUndoMark(
                NXOpen.Session.MarkVisibility.Invisible, "nx_mcp_command"
            )
    except Exception as e:
        sys.stderr.write(f"Failed to set NX undo mark: {e}\n")

    def _rollback_nx():
        _state.clear()
        _state.update(old_state)
        if undo_mark is not None and SESSION is not None:
            try:
                if hasattr(SESSION, "UndoToMark"):
                    SESSION.UndoToMark(undo_mark, "nx_mcp_command")
            except Exception as rollback_err:
                sys.stderr.write(f"NX UndoToMark rollback failed: {rollback_err}\n")

    try:
        command = json.loads(line)
        res = dispatch(command)
        if isinstance(res, dict) and not res.get("ok"):
            # Command returned error status, restore state and roll back NX geometry
            _rollback_nx()
        return res
    except Exception as exc:
        # Command raised exception, restore state and roll back NX geometry
        _rollback_nx()
        return {
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def run_socket_bridge(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        sys.stderr.write(f"Failed to read live bridge config: {e}\n")
        return

    part_path = config.get("part_path")
    port = config.get("port", 43210)

    if part_path:
        try:
            open_part(part_path)
        except Exception as e:
            sys.stderr.write(f"Failed to open part: {e}\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    server.setblocking(False)

    sys.stderr.write(f"Live bridge socket server listening on port {port}...\n")

    clients = []
    try:
        ui = NXOpen.UI.GetUI()
    except Exception:
        ui = None

    last_health_log = time.time()
    HEALTH_LOG_INTERVAL = 300  # Log health every 5 minutes
    CLIENT_TIMEOUT = 120  # Disconnect idle clients after 2 minutes

    try:
        while config_path.exists():
            if ui:
                try:
                    ui.ProcessDeviceEvents()
                except Exception:
                    pass

            # Periodic health log
            now = time.time()
            if now - last_health_log > HEALTH_LOG_INTERVAL:
                sys.stderr.write(f"Socket bridge alive: {len(clients)} connected client(s)\n")
                last_health_log = now

            try:
                client_sock, client_addr = server.accept()
                client_sock.setblocking(False)
                client_sock.settimeout(CLIENT_TIMEOUT)
                clients.append((client_sock, "", time.time()))
                sys.stderr.write(f"Connected client: {client_addr}\n")
            except BlockingIOError:
                pass
            except Exception:
                pass

            still_connected = []
            for client_sock, buffer, last_activity in clients:
                try:
                    # Check for idle timeout
                    if time.time() - last_activity > CLIENT_TIMEOUT:
                        sys.stderr.write("Disconnecting idle client\n")
                        client_sock.close()
                        continue

                    data = client_sock.recv(4096)
                    if not data:
                        client_sock.close()
                        continue
                    buffer += data.decode("utf-8")
                    last_activity = time.time()

                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue

                        result = handle_line(line)
                        response = json.dumps(result) + "\n"
                        client_sock.sendall(response.encode("utf-8"))

                    still_connected.append((client_sock, buffer, last_activity))
                except BlockingIOError:
                    still_connected.append((client_sock, buffer, last_activity))
                except Exception as e:
                    sys.stderr.write(f"Error handling client: {e}\n")
                    try:
                        client_sock.close()
                    except Exception:
                        pass

            clients = still_connected
            time.sleep(0.01)
    finally:
        for client_sock, _, _ in clients:
            try:
                client_sock.close()
            except Exception:
                pass
        server.close()
        sys.stderr.write("Socket bridge server stopped\n")


def main():
    config_path = ROOT_DIR / "live_bridge_config.json"
    if config_path.exists():
        run_socket_bridge(config_path)
    else:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            result = handle_line(line)
            sys.stdout.write(json.dumps(result) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
