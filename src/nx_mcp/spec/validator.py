"""Static graph and schema validator for CAD Specs."""

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from ..tools.registry import ToolRegistry, _get_schema
from .schema import (
    CADSpec,
    SpecNode,
    extract_node_references,
    is_calc_ref,
    is_expr_ref,
    is_symbolic_ref,
    parse_calc_ref,
    parse_symbolic_ref,
)

# Standard known output fields produced by NX-MCP operations
KNOWN_OP_OUTPUTS: Dict[str, Set[str]] = {
    # Primitives & solids
    "create_cuboid": {"body_id", "feature_id"},
    "create_cube": {"body_id", "feature_id"},
    "create_two_cuboids": {"body_id", "feature_id", "body_ids"},
    "create_cylinder": {"body_id", "feature_id"},
    "extrude": {"body_id", "feature_id"},
    "extrude_profile": {"body_id", "feature_id", "profile_id"},
    "loft": {"body_id", "feature_id"},
    "revolve": {"body_id", "feature_id"},
    "add_hole": {"body_id", "feature_id"},
    "add_hole_nx": {"body_id", "feature_id"},
    "create_rib": {"body_id", "feature_id"},
    "edge_blend": {"body_id", "feature_id"},
    "chamfer": {"body_id", "feature_id"},
    "add_fillet": {"body_id", "feature_id"},
    "add_chamfer": {"body_id", "feature_id"},
    "boolean_unite": {"body_id", "feature_id"},
    "boolean_subtract": {"body_id", "feature_id"},
    "boolean_combine": {"body_id", "feature_id"},
    "split_body": {"body_id", "feature_id", "body_ids"},
    "pattern_feature": {"body_id", "feature_id", "body_ids"},
    "pattern_circular": {"body_id", "feature_id", "body_ids"},
    "pattern": {"body_id", "feature_id", "body_ids"},
    "shell": {"body_id", "feature_id"},
    "create_gear": {"body_id", "feature_id", "outer_diameter"},
    # Wireframe & profiles
    "create_profile": {"profile_id", "curve_ids", "curve_count"},
    "create_sketch": {"sketch_id"},
    "draw_line": {"curve_id"},
    "draw_circle": {"curve_id"},
    "draw_rectangle": {"curve_ids", "curve_id"},
    "draw_arc": {"curve_id"},
    "draw_spline": {"curve_id"},
    "offset_curve": {"curve_id", "profile_id"},
    "variable_offset": {"feature_id", "profile_id", "curve_ids", "body_id"},
    "close_curve_region": {"curve_ids", "profile_id"},
    # File operations
    "create_part": {"filepath"},
    "open_part": {"filepath"},
    "save_part": {"filepath"},
    "export_step": {"filepath"},
    "export_stl": {"filepath"},
}

# Generic fallback allowed fields for any tool
GENERIC_ALLOWED_FIELDS = {
    "body_id", "feature_id", "sketch_id", "curve_id", "curve_ids", "profile_id", "body_ids", "filepath", "ok", "message"
}


@dataclass
class ValidationError:
    node_id: Optional[str]
    field: Optional[str]
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "field": self.field,
            "message": self.message,
        }


def _ensure_tools_loaded():
    if not ToolRegistry.all():
        from ..tools import (  # noqa: F401
            modeling,
            sketch,
            edit_operations,
            assembly,
            surface_modeling,
            measure,
            file_ops,
            utility,
            discovery,
            recipe,
        )


def validate_spec(spec_input: Union[CADSpec, Dict[str, Any]]) -> Dict[str, Any]:
    """Perform comprehensive offline static validation on a CAD Spec DAG.

    Validates:
    - Non-empty DAG structure
    - Unique node IDs
    - Cycle-free dependency graph (DAG)
    - Reference resolution (ancestor existence, forward-reference prohibition, produced field matching)
    - Reserved $calc:... syntax well-formedness
    - Tool existence in ToolRegistry
    - Required parameter completeness and schema type matching

    Returns:
        Dictionary with:
            "valid": bool
            "errors": list of error dicts
            "topological_order": list of node IDs (if valid)
    """
    _ensure_tools_loaded()
    errors: List[ValidationError] = []

    if isinstance(spec_input, dict):
        try:
            spec = CADSpec.from_dict(spec_input)
        except Exception as e:
            return {
                "valid": False,
                "errors": [{"node_id": None, "field": None, "message": f"Malformed spec dictionary: {e}"}],
                "topological_order": [],
            }
    elif isinstance(spec_input, CADSpec):
        spec = spec_input
    else:
        return {
            "valid": False,
            "errors": [{"node_id": None, "field": None, "message": "spec_input must be a dict or CADSpec instance"}],
            "topological_order": [],
        }

    if not spec.nodes:
        errors.append(ValidationError(None, "nodes", "CAD Spec must contain at least one operation node."))
        return {"valid": False, "errors": [e.to_dict() for e in errors], "topological_order": []}

    # 1. Unique Node IDs
    node_map: Dict[str, SpecNode] = {}
    for node in spec.nodes:
        if not node.id:
            errors.append(ValidationError(None, "id", "Operation node is missing required 'id' attribute."))
            continue
        if node.id in node_map:
            errors.append(ValidationError(node.id, "id", f"Duplicate node ID '{node.id}' found in spec."))
        node_map[node.id] = node

    # 2. Tool existence in ToolRegistry
    all_tools = ToolRegistry.all()
    for node in spec.nodes:
        if not node.op:
            errors.append(ValidationError(node.id, "op", f"Node '{node.id}' is missing required 'op' attribute."))
        elif node.op not in all_tools:
            errors.append(
                ValidationError(node.id, "op", f"Unknown operation '{node.op}' on node '{node.id}'.")
            )

    # 3. Cycle Detection & Topological Sort (Kahn's Algorithm)
    in_degree: Dict[str, int] = {node_id: 0 for node_id in node_map}
    adj_list: Dict[str, List[str]] = {node_id: [] for node_id in node_map}

    for node in spec.nodes:
        for dep in node.depends_on:
            if dep not in node_map:
                errors.append(
                    ValidationError(node.id, "depends_on", f"Node '{node.id}' depends on non-existent node '{dep}'.")
                )
            else:
                adj_list[dep].append(node.id)
                in_degree[node.id] += 1

    queue = deque([n for n, deg in in_degree.items() if deg == 0])
    topological_order: List[str] = []

    while queue:
        curr = queue.popleft()
        topological_order.append(curr)
        for neighbor in adj_list.get(curr, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(topological_order) < len(node_map):
        cycle_nodes = [n for n, deg in in_degree.items() if deg > 0]
        errors.append(
            ValidationError(None, "graph", f"Cyclic dependency detected among nodes: {cycle_nodes}")
        )

    # Compute topological position lookup (index in execution order)
    topo_pos = {nid: idx for idx, nid in enumerate(topological_order)}

    # 4. Reference Validation & $calc syntax checks
    for node in spec.nodes:
        # Check all node references in params
        refs = extract_node_references(node.params)
        for target_id, field_name in refs:
            if target_id not in node_map:
                errors.append(
                    ValidationError(
                        node.id,
                        None,
                        f"Symbolic reference '${target_id}.{field_name}' in node '{node.id}' targets non-existent node '{target_id}'."
                    )
                )
            else:
                target_node = node_map[target_id]
                # Ensure target comes before current in topological ordering
                if topo_pos.get(target_id, 999999) >= topo_pos.get(node.id, -1):
                    errors.append(
                        ValidationError(
                            node.id,
                            None,
                            f"Illegal forward reference: node '{node.id}' references output '${target_id}.{field_name}' of downstream node '{target_id}'."
                        )
                    )
                # Ensure target op produces field
                allowed_fields = KNOWN_OP_OUTPUTS.get(target_node.op, GENERIC_ALLOWED_FIELDS)
                if field_name not in allowed_fields:
                    errors.append(
                        ValidationError(
                            node.id,
                            None,
                            f"Node '{target_id}' (op: '{target_node.op}') is not known to produce field '{field_name}' referenced by '${target_id}.{field_name}' in node '{node.id}'."
                        )
                    )

        # Check $calc syntax well-formedness
        _validate_calc_refs_recursive(node.id, node.params, errors)

        # 5. Param completeness & type checking against ToolRegistry schema
        if node.op in all_tools:
            tool_entry = all_tools[node.op]
            schema = _get_schema(tool_entry["fn"])
            props = schema.get("properties", {})
            required_params = schema.get("required", [])

            for req in required_params:
                if req not in node.params:
                    errors.append(
                        ValidationError(
                            node.id,
                            req,
                            f"Node '{node.id}' (op: '{node.op}') is missing required parameter '{req}'."
                        )
                    )

            for param_name, param_val in node.params.items():
                if param_name in props:
                    expected_type = props[param_name].get("type")
                    _validate_param_type(node.id, param_name, param_val, expected_type, errors)

    return {
        "valid": len(errors) == 0,
        "errors": [e.to_dict() for e in errors],
        "topological_order": topological_order if len(errors) == 0 else [],
    }


def _validate_calc_refs_recursive(node_id: str, data: Any, errors: List[ValidationError]):
    """Ensure any $calc:... strings are non-empty and well-formed."""
    if isinstance(data, str) and is_calc_ref(data):
        expr = parse_calc_ref(data)
        if not expr:
            errors.append(
                ValidationError(node_id, None, f"Empty or malformed $calc reference '{data}' in node '{node_id}'.")
            )
    elif isinstance(data, dict):
        for v in data.values():
            _validate_calc_refs_recursive(node_id, v, errors)
    elif isinstance(data, (list, tuple)):
        for item in data:
            _validate_calc_refs_recursive(node_id, item, errors)


def _validate_param_type(node_id: str, param_name: str, val: Any, expected_type: Optional[str], errors: List[ValidationError]):
    """Validate literal value type against schema (references bypass type checks as they resolve at runtime)."""
    if val is None or is_symbolic_ref(val) or is_expr_ref(val) or is_calc_ref(val):
        return

    if expected_type == "number":
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            errors.append(
                ValidationError(
                    node_id,
                    param_name,
                    f"Parameter '{param_name}' in node '{node_id}' expects a number, got {type(val).__name__} ({val!r})."
                )
            )
    elif expected_type == "boolean":
        if not isinstance(val, bool):
            errors.append(
                ValidationError(
                    node_id,
                    param_name,
                    f"Parameter '{param_name}' in node '{node_id}' expects a boolean, got {type(val).__name__} ({val!r})."
                )
            )
    elif expected_type == "array":
        if not isinstance(val, (list, tuple)):
            errors.append(
                ValidationError(
                    node_id,
                    param_name,
                    f"Parameter '{param_name}' in node '{node_id}' expects a list/array, got {type(val).__name__} ({val!r})."
                )
            )
    elif expected_type == "object":
        if not isinstance(val, dict):
            errors.append(
                ValidationError(
                    node_id,
                    param_name,
                    f"Parameter '{param_name}' in node '{node_id}' expects an object/dict, got {type(val).__name__} ({val!r})."
                )
            )
