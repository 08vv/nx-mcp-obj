"""CAD Spec operation graph executor."""

from typing import Any, Dict, List, Optional, Tuple, Union

from ..bridge import runner
from ..response import ToolError, ToolResult
from ..tools._common import _use_mock_nxopen
from ..tools.registry import ToolRegistry
from .schema import (
    CADSpec,
    SpecNode,
    NODE_REF_PATTERN,
    EXPR_REF_PATTERN,
    EMBEDDED_NODE_REF_PATTERN,
    EMBEDDED_EXPR_REF_PATTERN,
    is_calc_ref,
    is_expr_ref,
    is_fn_ref,
    is_symbolic_ref,
    parse_calc_ref,
    parse_expr_ref,
    parse_fn_ref,
    parse_symbolic_ref,
)
from .calc import safe_calc_eval, CalcEvalError
from .geometry_math import GEOMETRY_FUNCTIONS
from .validator import validate_spec
from .plausibility import validate_plausibility as run_plausibility_check
from ..state.dependency_graph import GeometryDependencyGraph, get_session_graph, reset_session_graph


# Global in-memory storage for paused execution sessions keyed by token
_ACTIVE_EXECUTIONS: Dict[str, "SpecExecutor"] = {}


def get_active_execution(token: str) -> Optional["SpecExecutor"]:
    """Retrieve an active paused executor by its token."""
    return _ACTIVE_EXECUTIONS.get(token)


def clear_active_executions() -> None:
    """Clear all active paused executions (useful for test isolation)."""
    _ACTIVE_EXECUTIONS.clear()


class SpecExecutionError(RuntimeError):
    def __init__(self, node_id: str, message: str, original_error: Optional[Exception] = None):
        super().__init__(f"Error executing node '{node_id}': {message}")
        self.node_id = node_id
        self.message = message
        self.original_error = original_error


class SpecExecutor:
    """Resumable and steppable execution engine for CAD Spec operation graphs."""

    def __init__(
        self,
        spec: Union[CADSpec, Dict[str, Any]],
        auto_validate: bool = True,
        validate_plausibility: bool = True,
        strict_plausibility: bool = False,
    ):
        if isinstance(spec, dict):
            self.spec = CADSpec.from_dict(spec)
        else:
            self.spec = spec

        self.node_map: Dict[str, SpecNode] = {n.id: n for n in self.spec.nodes}
        self.symbol_table: Dict[str, Dict[str, Any]] = {}
        self.node_results: Dict[str, Dict[str, Any]] = {}
        self.executed_nodes: List[str] = []
        self.failed_node: Optional[str] = None
        self.failure_error: Optional[str] = None
        self.status: str = "pending"  # pending, running, paused, completed, failed
        self.execution_token: Optional[str] = None
        self.dependency_graph = GeometryDependencyGraph(part_name=self.spec.part_name)
        self.plausibility_report: Optional[Dict[str, Any]] = None

        if auto_validate:
            val_res = validate_spec(self.spec)
            if not val_res["valid"]:
                err_msgs = "; ".join(e["message"] for e in val_res["errors"])
                raise ValueError(f"Spec validation failed: {err_msgs}")
            self.topological_order = val_res["topological_order"]
        else:
            self.topological_order = [n.id for n in self.spec.nodes]

        if validate_plausibility:
            self.plausibility_report = run_plausibility_check(self.spec, strict=strict_plausibility)
            if not self.plausibility_report["plausible"]:
                err_msgs = "; ".join(e["message"] for e in self.plausibility_report["errors"])
                if strict_plausibility and self.plausibility_report["warnings"]:
                    warn_msgs = "; ".join(w["message"] for w in self.plausibility_report["warnings"])
                    err_msgs = f"{err_msgs}; Warnings: {warn_msgs}" if err_msgs else f"Warnings: {warn_msgs}"
                raise ValueError(f"Spec plausibility check failed: {err_msgs}")

        self.current_step_index = 0

    def has_next(self) -> bool:
        """Return True if there are remaining unexecuted nodes."""
        return self.current_step_index < len(self.topological_order) and self.status not in ("failed",)

    def execute_next_node(self) -> Dict[str, Any]:
        """Execute a single next node in topological order and update graph state."""
        if not self.has_next():
            return {
                "ok": self.status != "failed",
                "message": f"Execution finished with status: {self.status}",
            }

        self.status = "running"
        node_id = self.topological_order[self.current_step_index]
        node = self.node_map[node_id]

        try:
            # 1. Resolve all symbolic references in params
            resolved_params = self._resolve_params(node.params, node_id)

            # 2. Dispatch the tool
            res = self._dispatch_tool(node.op, resolved_params, node_id)
            if not res.get("ok", False):
                err_msg = res.get("error", res.get("message", "Operation returned failure"))
                raise SpecExecutionError(node_id, err_msg)

            # 3. Harvest returned persistent IDs into symbol table
            node_symbols = self._extract_symbols(res, node.op, node_id)
            self.symbol_table[node_id] = node_symbols
            self.node_results[node_id] = res
            self.executed_nodes.append(node_id)

            # 4. Record into dependency graph
            self._record_node_dependencies(node, res, resolved_params)

            self.current_step_index += 1

            if self.current_step_index >= len(self.topological_order):
                self.status = "completed"

            return {
                "ok": True,
                "node_id": node_id,
                "op": node.op,
                "result": res,
                "resolved_symbols": node_symbols,
            }

        except Exception as e:
            self.status = "failed"
            self.failed_node = node_id
            self.failure_error = str(e)
            self.node_results[node_id] = {"ok": False, "error": str(e)}
            return {
                "ok": False,
                "node_id": node_id,
                "op": node.op,
                "error": str(e),
            }

    def execute_all(
        self,
        stop_on_error: bool = True,
        pause_after: Union[List[str], str, None] = None,
        verify_postexecution: bool = True,
        geometry_check: bool = False,
        capture_screenshot: bool = False,
        live_check: bool = True,
    ) -> Dict[str, Any]:
        """Execute the CAD Spec graph, optionally pausing after specified nodes."""
        while self.has_next():
            step_res = self.execute_next_node()
            if not step_res.get("ok") and stop_on_error:
                break

            # Check pause condition
            should_pause = False
            executed_node = step_res.get("node_id")
            if pause_after == "every_node":
                should_pause = True
            elif isinstance(pause_after, (list, set, tuple)) and executed_node in pause_after:
                should_pause = True
            elif isinstance(pause_after, str) and executed_node == pause_after:
                should_pause = True

            if should_pause and self.has_next():
                self.status = "paused"
                if not self.execution_token:
                    import uuid
                    self.execution_token = uuid.uuid4().hex[:8]
                _ACTIVE_EXECUTIONS[self.execution_token] = self
                break

        if self.status == "completed" and self.execution_token in _ACTIVE_EXECUTIONS:
            _ACTIVE_EXECUTIONS.pop(self.execution_token, None)

        total_nodes = len(self.topological_order)
        skipped_nodes = [
            nid for nid in self.topological_order if nid not in self.executed_nodes and nid != self.failed_node
        ]

        report = {
            "ok": self.status in ("completed", "paused"),
            "part_name": self.spec.part_name,
            "status": self.status,
            "execution_token": self.execution_token,
            "paused_node": self.executed_nodes[-1] if self.status == "paused" and self.executed_nodes else None,
            "total_nodes": total_nodes,
            "executed_nodes": list(self.executed_nodes),
            "skipped_nodes": skipped_nodes,
            "failed_node": self.failed_node,
            "failure_error": self.failure_error,
            "symbol_table": dict(self.symbol_table),
            "node_results": dict(self.node_results),
            "dependency_graph": self.dependency_graph.to_dict(),
            "plausibility_report": self.plausibility_report,
        }

        if verify_postexecution and self.status == "completed":
            from .postcheck import verify_postexecution as run_postcheck
            report["postcheck_report"] = run_postcheck(
                self.spec,
                self.dependency_graph,
                report,
                live_check=live_check,
            )
        else:
            report["postcheck_report"] = None

        if geometry_check:
            from .geocheck import verify_geometry
            report["geometry_report"] = verify_geometry(
                self.spec,
                self.dependency_graph,
                report,
                capture_screenshot=capture_screenshot,
                live_check=live_check,
            )
        else:
            report["geometry_report"] = None

        return report



    def _record_node_dependencies(self, node: SpecNode, res: Dict[str, Any], resolved_params: Dict[str, Any]) -> None:
        """Record the execution outcome of a node into the geometry dependency graph."""
        consumed = list(res.get("consumed", []))
        produced = list(res.get("produced", []))
        modified = list(res.get("modified", []))
        feature_id = res.get("feature_id")

        # Fallback / Server-side inference for mock mode or tools without explicit tracking
        if not produced and not consumed and not modified:
            if "body_id" in res:
                if node.op in {"create_cuboid", "create_cylinder", "create_sphere", "create_block", "extrude", "loft"}:
                    produced.append(res["body_id"])
                elif node.op in {"add_hole", "boolean_subtract", "boolean_unite", "boolean_intersect", "shell", "add_fillet", "add_chamfer", "edge_blend"}:
                    modified.append(res["body_id"])
            if "body_ids" in res:
                produced.extend(res["body_ids"])
            if "profile_id" in res:
                produced.append(res["profile_id"])
            if "curve_ids" in res:
                produced.extend(res["curve_ids"])

            if node.op == "loft" and "profile_ids" in resolved_params:
                consumed.extend(resolved_params["profile_ids"])
            elif node.op in {"boolean_subtract", "boolean_unite", "boolean_intersect"}:
                if "tool" in resolved_params:
                    consumed.append(resolved_params["tool"])
                if "target" in resolved_params and resolved_params["target"] not in modified:
                    modified.append(resolved_params["target"])
            elif node.op == "pattern" and "feature_ref" in resolved_params:
                consumed.append(resolved_params["feature_ref"])

        # Also update global session graph
        session_graph = get_session_graph()

        self.dependency_graph.record_operation(
            op=node.op,
            spec_node_id=node.id,
            produced=produced,
            consumed=consumed,
            modified=modified,
            feature_id=feature_id,
            metadata=resolved_params,
        )
        session_graph.record_operation(
            op=node.op,
            spec_node_id=node.id,
            produced=produced,
            consumed=consumed,
            modified=modified,
            feature_id=feature_id,
            metadata=resolved_params,
        )

    def _resolve_params(self, params: Dict[str, Any], current_node_id: str) -> Dict[str, Any]:
        """Recursively resolve symbolic and expression references in a parameter dictionary."""
        resolved = {}
        for k, v in params.items():
            resolved[k] = self._resolve_value(v, current_node_id)
        return resolved

    def _resolve_value(self, val: Any, current_node_id: str) -> Any:
        """Resolve an individual value (supporting nested lists and dicts)."""
        if isinstance(val, str):
            if is_symbolic_ref(val):
                target_id, field_name = parse_symbolic_ref(val)
                if target_id not in self.symbol_table:
                    raise SpecExecutionError(
                        current_node_id,
                        f"Cannot resolve reference '{val}': node '{target_id}' has not produced outputs yet."
                    )
                target_symbols = self.symbol_table[target_id]
                if field_name not in target_symbols:
                    raise SpecExecutionError(
                        current_node_id,
                        f"Cannot resolve reference '{val}': field '{field_name}' not found in outputs of node '{target_id}' (available: {list(target_symbols.keys())})."
                    )
                return target_symbols[field_name]

            if is_expr_ref(val):
                # Pass expression name directly — NX expression value
                return parse_expr_ref(val)

            if is_calc_ref(val):
                calc_expr = parse_calc_ref(val)
                if not calc_expr:
                    raise SpecExecutionError(current_node_id, f"Empty $calc expression in '{val}'.")
                # Pre-resolve any embedded $nodeId.field references inside the calc string
                resolved_expr = calc_expr
                for m in EMBEDDED_NODE_REF_PATTERN.finditer(calc_expr):
                    ref_str = m.group(0)  # e.g. "$n1.width"
                    target_id, field_name = m.group(1), m.group(2)
                    if target_id not in self.symbol_table:
                        raise SpecExecutionError(
                            current_node_id,
                            f"Cannot resolve embedded reference '{ref_str}' in $calc expression: node '{target_id}' has not produced outputs yet."
                        )
                    resolved_val = self.symbol_table[target_id].get(field_name)
                    if resolved_val is None:
                        raise SpecExecutionError(
                            current_node_id,
                            f"Cannot resolve embedded reference '{ref_str}' in $calc expression: field not found."
                        )
                    resolved_expr = resolved_expr.replace(ref_str, str(resolved_val))
                # Pre-resolve any embedded $expr:NAME references via bridge round-trip
                for m in EMBEDDED_EXPR_REF_PATTERN.finditer(resolved_expr):
                    ref_str = m.group(0)  # e.g. "$expr:CUBOID_1_L"
                    expr_name = m.group(1)
                    if not _use_mock_nxopen():
                        nx_res = runner.call_nx("list_expressions", {})
                        if nx_res.get("ok") and expr_name in nx_res.get("expressions", {}):
                            expr_val = nx_res["expressions"][expr_name]
                            resolved_expr = resolved_expr.replace(ref_str, str(expr_val))
                        else:
                            raise SpecExecutionError(
                                current_node_id,
                                f"Cannot resolve {ref_str} in $calc expression: expression not found in NX."
                            )
                    else:
                        # Mock mode: treat expr refs as 1.0 placeholder
                        resolved_expr = resolved_expr.replace(ref_str, "1.0")

                try:
                    return safe_calc_eval(resolved_expr)
                except CalcEvalError as e:
                    raise SpecExecutionError(current_node_id, f"$calc evaluation error: {e}")

            if is_fn_ref(val):
                return self._resolve_fn_ref(val, current_node_id)

            return val

        if isinstance(val, dict):
            return {k: self._resolve_value(sub_v, current_node_id) for k, sub_v in val.items()}

        if isinstance(val, (list, tuple)):
            return [self._resolve_value(item, current_node_id) for item in val]

        return val

    def _resolve_fn_ref(self, val: str, current_node_id: str) -> Any:
        """Resolve a $fn:func_name(...) reference by invoking the geometry math function."""
        parsed = parse_fn_ref(val)
        if parsed is None:
            raise SpecExecutionError(current_node_id, f"Malformed $fn reference: '{val}'")

        fn_name, raw_args = parsed
        if fn_name not in GEOMETRY_FUNCTIONS:
            raise SpecExecutionError(
                current_node_id,
                f"Unknown geometry function '{fn_name}' in $fn reference."
            )

        fn = GEOMETRY_FUNCTIONS[fn_name]

        # Parse keyword-style args: "count=6, pcd=50, start_angle_deg=30"
        kwargs = {}
        positional_args = []
        if raw_args.strip():
            for part in raw_args.split(","):
                part = part.strip()
                if not part:
                    continue
                if "=" in part:
                    key, val_str = part.split("=", 1)
                    key = key.strip()
                    val_str = val_str.strip()
                    kwargs[key] = self._parse_fn_arg_value(val_str, current_node_id)
                else:
                    positional_args.append(self._parse_fn_arg_value(part, current_node_id))

        try:
            return fn(*positional_args, **kwargs)
        except Exception as e:
            raise SpecExecutionError(
                current_node_id,
                f"Error calling $fn:{fn_name}(...): {e}"
            )

    def _parse_fn_arg_value(self, val_str: str, current_node_id: str) -> Any:
        """Parse a single argument value from a $fn:... reference string."""
        val_str = val_str.strip()

        # Try to resolve as symbolic ref
        if is_symbolic_ref(val_str):
            return self._resolve_value(val_str, current_node_id)

        # Try to resolve as calc ref
        if is_calc_ref(val_str):
            return self._resolve_value(val_str, current_node_id)

        # Try numeric parse
        try:
            if "." in val_str:
                return float(val_str)
            return int(val_str)
        except ValueError:
            pass

        # Return as string
        return val_str

    def _dispatch_tool(self, op: str, params: Dict[str, Any], node_id: str) -> Dict[str, Any]:
        """Dispatch a single tool call via runner.call_nx or mock fallback."""
        if _use_mock_nxopen():
            # Mock mode execution
            mock_id = len(self.executed_nodes) + 1
            return {
                "ok": True,
                "message": f"Mock executed {op} for node {node_id}",
                "body_id": f"body_{mock_id}",
                "feature_id": f"feature_{mock_id}",
                "profile_id": f"profile_{mock_id}",
                "curve_ids": [f"curve_{mock_id}"],
            }

        return runner.call_nx(op, params)

    def _extract_symbols(self, res: Dict[str, Any], op: str, node_id: str) -> Dict[str, Any]:
        """Extract output IDs from tool response dictionary."""
        symbols = {}
        for key in (
            "body_id",
            "feature_id",
            "profile_id",
            "sketch_id",
            "curve_id",
            "curve_ids",
            "body_ids",
            "outer_diameter",
            "filepath",
        ):
            if key in res and res[key] is not None:
                symbols[key] = res[key]

        # Ensure minimal default symbols if tool returned ok
        if "body_id" not in symbols and "body_id" in str(res.get("message", "")):
            # Extracted from message if needed
            pass
        return symbols


def execute_spec(
    spec: Union[CADSpec, Dict[str, Any]],
    stop_on_error: bool = True,
    validate_plausibility: bool = True,
    strict_plausibility: bool = False,
    pause_after: Union[List[str], str, None] = None,
    verify_postexecution: bool = True,
    geometry_check: bool = False,
    capture_screenshot: bool = False,
    live_check: bool = True,
) -> Dict[str, Any]:
    """Top-level convenience function to validate and execute a CAD Spec."""
    executor = SpecExecutor(
        spec,
        auto_validate=True,
        validate_plausibility=validate_plausibility,
        strict_plausibility=strict_plausibility,
    )
    return executor.execute_all(
        stop_on_error=stop_on_error,
        pause_after=pause_after,
        verify_postexecution=verify_postexecution,
        geometry_check=geometry_check,
        capture_screenshot=capture_screenshot,
        live_check=live_check,
    )


def resume_spec_execution(
    execution_token: str,
    pause_after: Union[List[str], str, None] = None,
    stop_on_error: bool = True,
    verify_postexecution: bool = True,
    geometry_check: bool = False,
    capture_screenshot: bool = False,
    live_check: bool = True,
) -> Dict[str, Any]:
    """Resume execution of a previously paused CAD Spec graph using its token."""
    executor = get_active_execution(execution_token)
    if not executor:
        raise ValueError(
            f"No active paused execution found for token '{execution_token}'. "
            "The execution may have already completed or the server process was restarted."
        )
    return executor.execute_all(
        stop_on_error=stop_on_error,
        pause_after=pause_after,
        verify_postexecution=verify_postexecution,
        geometry_check=geometry_check,
        capture_screenshot=capture_screenshot,
        live_check=live_check,
    )


