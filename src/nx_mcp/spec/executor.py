"""CAD Spec operation graph executor."""

from typing import Any, Dict, List, Optional, Tuple, Union

from ..bridge import runner
from ..response import ToolError, ToolResult
from ..tools._common import _use_mock_nxopen
from ..tools.registry import ToolRegistry
from .schema import (
    CADSpec,
    SpecNode,
    is_calc_ref,
    is_expr_ref,
    is_symbolic_ref,
    parse_calc_ref,
    parse_expr_ref,
    parse_symbolic_ref,
)
from .validator import validate_spec


class SpecExecutionError(RuntimeError):
    def __init__(self, node_id: str, message: str, original_error: Optional[Exception] = None):
        super().__init__(f"Error executing node '{node_id}': {message}")
        self.node_id = node_id
        self.message = message
        self.original_error = original_error


class SpecExecutor:
    """Resumable and steppable execution engine for CAD Spec operation graphs."""

    def __init__(self, spec: Union[CADSpec, Dict[str, Any]], auto_validate: bool = True):
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
        self.status: str = "pending"  # pending, running, completed, failed

        if auto_validate:
            val_res = validate_spec(self.spec)
            if not val_res["valid"]:
                err_msgs = "; ".join(e["message"] for e in val_res["errors"])
                raise ValueError(f"Spec validation failed: {err_msgs}")
            self.topological_order = val_res["topological_order"]
        else:
            self.topological_order = [n.id for n in self.spec.nodes]

        self.current_step_index = 0

    def has_next(self) -> bool:
        """Return True if there are remaining unexecuted nodes."""
        return self.current_step_index < len(self.topological_order) and self.status != "failed"

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

    def execute_all(self, stop_on_error: bool = True) -> Dict[str, Any]:
        """Execute the entire CAD Spec graph atomically."""
        while self.has_next():
            step_res = self.execute_next_node()
            if not step_res.get("ok") and stop_on_error:
                break

        total_nodes = len(self.topological_order)
        skipped_nodes = [
            nid for nid in self.topological_order if nid not in self.executed_nodes and nid != self.failed_node
        ]

        return {
            "ok": self.status == "completed",
            "part_name": self.spec.part_name,
            "status": self.status,
            "total_nodes": total_nodes,
            "executed_nodes": list(self.executed_nodes),
            "skipped_nodes": skipped_nodes,
            "failed_node": self.failed_node,
            "failure_error": self.failure_error,
            "symbol_table": dict(self.symbol_table),
            "node_results": dict(self.node_results),
        }

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
                # Pass expression name directly
                return parse_expr_ref(val)

            if is_calc_ref(val):
                # Phase 5 forward-compatibility reserved contract
                calc_expr = parse_calc_ref(val)
                raise SpecExecutionError(
                    current_node_id,
                    f"Calculation reference '{val}' is reserved for Phase 5 deterministic math layer and cannot be evaluated in Phase 4."
                )

            return val

        if isinstance(val, dict):
            return {k: self._resolve_value(sub_v, current_node_id) for k, sub_v in val.items()}

        if isinstance(val, (list, tuple)):
            return [self._resolve_value(item, current_node_id) for item in val]

        return val

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


def execute_spec(spec: Union[CADSpec, Dict[str, Any]], stop_on_error: bool = True) -> Dict[str, Any]:
    """Top-level convenience function to validate and execute a CAD Spec atomically."""
    executor = SpecExecutor(spec, auto_validate=True)
    return executor.execute_all(stop_on_error=stop_on_error)
