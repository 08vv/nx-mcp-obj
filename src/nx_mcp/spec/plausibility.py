"""Pre-execution geometric and physical plausibility validation for CAD Specs.

Validates that parameter values are not only syntactically well-formed (Phase 4),
but physically plausible and geometrically sound before submitting them to NXOpen:
- Strictly positive dimensions (lengths, radii, thicknesses, depths).
- Safe geometric aspect ratios (hole diameter vs body face extents, shell thickness vs body minimum extents).
- Non-collapsing blend radii (fillets/chamfers vs body extents).
- Meaningful pattern counts.
- Best-effort static $calc: evaluation and tracking of non-checkable dynamic nodes.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
from .calc import safe_calc_eval, CalcEvalError
from .schema import (
    CADSpec,
    SpecNode,
    is_calc_ref,
    is_symbolic_ref,
    parse_calc_ref,
    parse_symbolic_ref,
    EMBEDDED_NODE_REF_PATTERN,
)

# Parameters that must be strictly positive (> 0.0)
POSITIVE_DIMENSION_PARAMS = {
    "create_cuboid": ["length", "width", "height"],
    "create_cylinder": ["radius", "height"],
    "create_sphere": ["radius"],
    "create_cube": ["size"],
    "create_block": ["length", "width", "height"],
    "add_hole": ["diameter", "depth"],
    "add_fillet": ["radius"],
    "add_chamfer": ["offset"],
    "edge_blend": ["radius"],
    "chamfer_edges": ["offset"],
    "shell": ["thickness"],
    "extrude": ["distance"],
    "extrude_profile": ["distance"],
    "variable_offset": ["offset_start"],
}

# Operations that produce canonical primitive solid bodies with statically known extents
PRIMITIVE_CREATORS = {"create_cuboid", "create_cylinder", "create_sphere", "create_cube", "create_block"}


class PlausibilityCheckResult:
    def __init__(self):
        self.errors: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.details: List[Dict[str, Any]] = []
        self.checks_performed: int = 0
        self.checks_passed: int = 0
        self.checks_not_checked: int = 0

    def add_error(self, node_id: str, op: str, check: str, message: str, **extra):
        self.checks_performed += 1
        entry = {
            "node_id": node_id,
            "op": op,
            "check": check,
            "status": "error",
            "severity": "error",
            "message": message,
        }
        entry.update(extra)
        self.errors.append(entry)
        self.details.append(entry)

    def add_warning(self, node_id: str, op: str, check: str, message: str, **extra):
        self.checks_performed += 1
        entry = {
            "node_id": node_id,
            "op": op,
            "check": check,
            "status": "warning",
            "severity": "warning",
            "message": message,
        }
        entry.update(extra)
        self.warnings.append(entry)
        self.details.append(entry)

    def add_pass(self, node_id: str, op: str, check: str, message: str):
        self.checks_performed += 1
        self.checks_passed += 1
        self.details.append({
            "node_id": node_id,
            "op": op,
            "check": check,
            "status": "passed",
            "message": message,
        })

    def add_not_checked(self, node_id: str, op: str, check: str, reason: str):
        self.checks_not_checked += 1
        self.details.append({
            "node_id": node_id,
            "op": op,
            "check": check,
            "status": "not_checked",
            "reason": reason,
        })

    def to_dict(self, strict: bool = False) -> Dict[str, Any]:
        is_plausible = len(self.errors) == 0
        if strict and len(self.warnings) > 0:
            is_plausible = False

        return {
            "plausible": is_plausible,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "checks_performed": self.checks_performed,
            "checks_passed": self.checks_passed,
            "checks_not_checked": self.checks_not_checked,
            "details": list(self.details),
        }


def _try_resolve_static_scalar(
    val: Any,
    known_nodes: Dict[str, Dict[str, Any]],
) -> Optional[float]:
    """Attempt to resolve a parameter value to a float statically without running NX."""
    if isinstance(val, (int, float)):
        return float(val)

    if not isinstance(val, str):
        return None

    val_str = val.strip()

    # If it's a symbolic reference $node.field
    if is_symbolic_ref(val_str):
        target_id, field_name = parse_symbolic_ref(val_str)
        if target_id in known_nodes and field_name in known_nodes[target_id]:
            sub_val = known_nodes[target_id][field_name]
            if isinstance(sub_val, (int, float)):
                return float(sub_val)
        return None

    # If it's a $calc: expression
    if is_calc_ref(val_str):
        expr = parse_calc_ref(val_str)

        # Try to resolve embedded $node.field inside the calc expression
        def replace_sym(m):
            t_id, f_name = m.group(1), m.group(2)
            if t_id in known_nodes and f_name in known_nodes[t_id]:
                return str(known_nodes[t_id][f_name])
            return m.group(0)

        resolved_expr = EMBEDDED_NODE_REF_PATTERN.sub(replace_sym, expr)
        if "$" in resolved_expr:
            # Contains unresolvable symbolic or expression ref
            return None

        try:
            res = safe_calc_eval(resolved_expr)
            if isinstance(res, (int, float)):
                return float(res)
        except CalcEvalError:
            return None

    try:
        return float(val_str)
    except ValueError:
        return None


def _extract_body_bounds(
    node: SpecNode,
    known_nodes: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, float]]:
    """Extract known bounding extents for a primitive creation node."""
    p = node.params
    op = node.op

    if op in {"create_cuboid", "create_block"}:
        l = _try_resolve_static_scalar(p.get("length"), known_nodes)
        w = _try_resolve_static_scalar(p.get("width"), known_nodes)
        h = _try_resolve_static_scalar(p.get("height"), known_nodes)
        if l is not None and w is not None and h is not None:
            return {
                "type": "cuboid",
                "length": l,
                "width": w,
                "height": h,
                "min_dim": min(l, w, h),
                "min_face": min(l, w),
                "max_dim": max(l, w, h),
            }

    elif op == "create_cylinder":
        r = _try_resolve_static_scalar(p.get("radius"), known_nodes)
        h = _try_resolve_static_scalar(p.get("height"), known_nodes)
        if r is not None and h is not None:
            return {
                "type": "cylinder",
                "radius": r,
                "diameter": 2 * r,
                "height": h,
                "min_dim": min(2 * r, h),
                "min_face": 2 * r,
                "max_dim": max(2 * r, h),
            }

    elif op == "create_cube":
        s = _try_resolve_static_scalar(p.get("size"), known_nodes)
        if s is not None:
            return {
                "type": "cube",
                "size": s,
                "min_dim": s,
                "min_face": s,
                "max_dim": s,
            }

    elif op == "create_sphere":
        r = _try_resolve_static_scalar(p.get("radius"), known_nodes)
        if r is not None:
            return {
                "type": "sphere",
                "radius": r,
                "min_dim": 2 * r,
                "min_face": 2 * r,
                "max_dim": 2 * r,
            }

    return None


def _find_target_node_bounds(
    target_param: Any,
    node_map: Dict[str, SpecNode],
    known_bodies: Dict[str, Dict[str, float]],
) -> Optional[Tuple[str, Dict[str, float]]]:
    """Find the target node and its bounding extents if statically known."""
    if not isinstance(target_param, str):
        return None

    target_str = target_param.strip()
    if is_symbolic_ref(target_str):
        target_id, _ = parse_symbolic_ref(target_str)
        if target_id in known_bodies:
            return target_id, known_bodies[target_id]
        if target_id in node_map:
            # Check if target was a primitive creator
            bounds = _extract_body_bounds(node_map[target_id], {})
            if bounds:
                return target_id, bounds

    return None


def validate_plausibility(
    spec: Union[CADSpec, Dict[str, Any]],
    strict: bool = False,
) -> Dict[str, Any]:
    """Run pre-execution geometric and physical plausibility checks on a CAD Spec.

    Args:
        spec: CADSpec instance or dictionary representation
        strict: If True, warnings are also treated as failures (plausible=False)

    Returns:
        Structured plausibility report with errors, warnings, details, and pass counts.
    """
    if isinstance(spec, dict):
        cad_spec = CADSpec.from_dict(spec)
    else:
        cad_spec = spec

    result = PlausibilityCheckResult()
    node_map: Dict[str, SpecNode] = {n.id: n for n in cad_spec.nodes}
    known_static_params: Dict[str, Dict[str, Any]] = {}
    known_bodies: Dict[str, Dict[str, float]] = {}

    for node in cad_spec.nodes:
        op = node.op
        p = node.params
        node_static_params: Dict[str, Any] = {}

        # 1. Dimension Sanity: Check strictly positive dimensions
        if op in POSITIVE_DIMENSION_PARAMS:
            for param_name in POSITIVE_DIMENSION_PARAMS[op]:
                if param_name in p:
                    val = _try_resolve_static_scalar(p[param_name], known_static_params)
                    if val is not None:
                        node_static_params[param_name] = val
                        if val <= 0.0:
                            result.add_error(
                                node_id=node.id,
                                op=op,
                                check="positive_dimension",
                                message=(
                                    f"Parameter '{param_name}' in node '{node.id}' must be positive (> 0.0), "
                                    f"but evaluated to {val}."
                                ),
                                param=param_name,
                                value=val,
                            )
                        else:
                            result.add_pass(
                                node_id=node.id,
                                op=op,
                                check="positive_dimension",
                                message=f"Parameter '{param_name}' is positive ({val}).",
                            )
                    else:
                        result.add_not_checked(
                            node_id=node.id,
                            op=op,
                            check="positive_dimension",
                            reason=f"Parameter '{param_name}' value '{p[param_name]}' could not be evaluated statically.",
                        )

        # Track primitive creation body bounds
        if op in PRIMITIVE_CREATORS:
            bounds = _extract_body_bounds(node, known_static_params)
            if bounds:
                known_bodies[node.id] = bounds

        # 2. Geometric Plausibility: Hole vs Target Body
        if op == "add_hole":
            target_ref = p.get("target") or p.get("body")
            target_info = _find_target_node_bounds(target_ref, node_map, known_bodies)
            d_val = _try_resolve_static_scalar(p.get("diameter"), known_static_params)
            depth_val = _try_resolve_static_scalar(p.get("depth"), known_static_params)

            if target_info and d_val is not None:
                t_id, bounds = target_info
                min_face = bounds.get("min_face", bounds.get("min_dim", 0.0))

                if min_face > 0.0 and d_val >= min_face:
                    result.add_error(
                        node_id=node.id,
                        op=op,
                        check="hole_diameter_vs_body",
                        message=(
                            f"Hole diameter ({d_val}mm) is greater than or equal to target body '{t_id}' "
                            f"face extent ({min_face}mm) — cut would completely sever or hollow out the body."
                        ),
                        hole_diameter=d_val,
                        target_face_extent=min_face,
                        target_node=t_id,
                    )
                elif min_face > 0.0 and d_val > 0.8 * min_face:
                    result.add_warning(
                        node_id=node.id,
                        op=op,
                        check="hole_diameter_vs_body",
                        message=(
                            f"Hole diameter ({d_val}mm) exceeds 80% of target body '{t_id}' "
                            f"face extent ({min_face}mm) — thin wall of {(min_face - d_val)/2:.2f}mm remains."
                        ),
                        hole_diameter=d_val,
                        target_face_extent=min_face,
                        target_node=t_id,
                    )
                else:
                    result.add_pass(
                        node_id=node.id,
                        op=op,
                        check="hole_diameter_vs_body",
                        message=f"Hole diameter {d_val}mm is within safe bounds of target body '{t_id}' ({min_face}mm).",
                    )

                if depth_val is not None and "height" in bounds:
                    body_h = bounds["height"]
                    if depth_val > body_h:
                        result.add_warning(
                            node_id=node.id,
                            op=op,
                            check="hole_depth_vs_body",
                            message=(
                                f"Hole depth ({depth_val}mm) exceeds target body '{t_id}' "
                                f"thickness ({body_h}mm) — operation will create a through-hole."
                            ),
                            hole_depth=depth_val,
                            body_thickness=body_h,
                        )
            else:
                result.add_not_checked(
                    node_id=node.id,
                    op=op,
                    check="hole_vs_body_plausibility",
                    reason="Target body bounds or hole dimensions not statically determinable before execution.",
                )

        # 3. Geometric Plausibility: Shell vs Target Body
        elif op == "shell":
            target_ref = p.get("body_id") or p.get("body")
            target_info = _find_target_node_bounds(target_ref, node_map, known_bodies)
            t_val = _try_resolve_static_scalar(p.get("thickness"), known_static_params)

            if target_info and t_val is not None:
                t_id, bounds = target_info
                min_dim = bounds.get("min_dim", 0.0)

                if min_dim > 0.0 and t_val >= 0.5 * min_dim:
                    result.add_error(
                        node_id=node.id,
                        op=op,
                        check="shell_thickness_vs_body",
                        message=(
                            f"Shell thickness ({t_val}mm) is >= 50% of target body '{t_id}' "
                            f"minimum dimension ({min_dim}mm) — inner cavity will collapse or invert."
                        ),
                        shell_thickness=t_val,
                        body_min_dimension=min_dim,
                        target_node=t_id,
                    )
                elif min_dim > 0.0 and t_val > 0.3 * min_dim:
                    result.add_warning(
                        node_id=node.id,
                        op=op,
                        check="shell_thickness_vs_body",
                        message=(
                            f"Shell thickness ({t_val}mm) is > 30% of target body '{t_id}' "
                            f"minimum dimension ({min_dim}mm)."
                        ),
                        shell_thickness=t_val,
                        body_min_dimension=min_dim,
                    )
                else:
                    result.add_pass(
                        node_id=node.id,
                        op=op,
                        check="shell_thickness_vs_body",
                        message=f"Shell thickness {t_val}mm is within safe proportion of target body '{t_id}'.",
                    )
            else:
                result.add_not_checked(
                    node_id=node.id,
                    op=op,
                    check="shell_vs_body_plausibility",
                    reason="Target body bounds or shell thickness not statically determinable before execution.",
                )

        # 4. Geometric Plausibility: Fillet / Chamfer vs Target Body
        elif op in {"add_fillet", "add_chamfer", "edge_blend", "chamfer_edges"}:
            target_ref = p.get("body") or p.get("target")
            target_info = _find_target_node_bounds(target_ref, node_map, known_bodies)
            r_val = _try_resolve_static_scalar(p.get("radius") or p.get("offset"), known_static_params)

            if target_info and r_val is not None:
                t_id, bounds = target_info
                min_dim = bounds.get("min_dim", 0.0)

                if min_dim > 0.0 and r_val >= 0.5 * min_dim:
                    result.add_error(
                        node_id=node.id,
                        op=op,
                        check="blend_radius_vs_body",
                        message=(
                            f"Blend radius/offset ({r_val}mm) is >= 50% of target body '{t_id}' "
                            f"minimum dimension ({min_dim}mm) — adjacent faces will self-intersect."
                        ),
                        blend_radius=r_val,
                        body_min_dimension=min_dim,
                        target_node=t_id,
                    )
                elif min_dim > 0.0 and r_val > 0.25 * min_dim:
                    result.add_warning(
                        node_id=node.id,
                        op=op,
                        check="blend_radius_vs_body",
                        message=(
                            f"Blend radius/offset ({r_val}mm) is > 25% of target body '{t_id}' "
                            f"minimum dimension ({min_dim}mm)."
                        ),
                        blend_radius=r_val,
                        body_min_dimension=min_dim,
                    )
                else:
                    result.add_pass(
                        node_id=node.id,
                        op=op,
                        check="blend_radius_vs_body",
                        message=f"Blend radius/offset {r_val}mm is within safe proportion of target body '{t_id}'.",
                    )
            else:
                result.add_not_checked(
                    node_id=node.id,
                    op=op,
                    check="blend_vs_body_plausibility",
                    reason="Target body bounds or blend radius not statically determinable before execution.",
                )

        # 5. Pattern Plausibility
        elif op in {"pattern", "pattern_circular", "pattern_feature"}:
            count_val = _try_resolve_static_scalar(p.get("count"), known_static_params)
            if count_val is not None:
                if count_val < 2:
                    result.add_error(
                        node_id=node.id,
                        op=op,
                        check="pattern_count",
                        message=f"Pattern count in node '{node.id}' must be at least 2, got {int(count_val)}.",
                    )
                else:
                    result.add_pass(
                        node_id=node.id,
                        op=op,
                        check="pattern_count",
                        message=f"Pattern count {int(count_val)} is valid.",
                    )
            else:
                result.add_not_checked(
                    node_id=node.id,
                    op=op,
                    check="pattern_count",
                    reason="Pattern count not statically determinable.",
                )

        known_static_params[node.id] = node_static_params

    return result.to_dict(strict=strict)
