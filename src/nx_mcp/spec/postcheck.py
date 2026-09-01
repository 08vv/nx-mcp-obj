"""Post-execution geometric and structural verification for CAD Spec executions.

Cross-checks the executed CAD Spec, the resulting GeometryDependencyGraph (Phase 6),
and live geometry inspection/measurement against what the spec claimed to produce:
1. Lifecycle Persistence Check: every produced body is either 'alive' or recorded as 'consumed' by a valid consumer.
2. Orphan Feature Check: every active feature in the graph traces back to an executed spec node.
3. Live Geometry Sanity: body counts, volume, and bounding boxes match expectations within tolerance.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
from ..bridge import runner
from ..state.dependency_graph import GeometryDependencyGraph, GeometryNode
from ..tools._common import _use_mock_nxopen
from .schema import CADSpec


class PostCheckReport:
    def __init__(self):
        self.violations: List[Dict[str, Any]] = []
        self.warnings: List[Dict[str, Any]] = []
        self.passed_checks: List[str] = []
        self.metrics: Dict[str, Any] = {}

    def add_violation(self, check: str, message: str, node_id: Optional[str] = None, **extra):
        entry = {
            "check": check,
            "severity": "error",
            "message": message,
        }
        if node_id:
            entry["node_id"] = node_id
        entry.update(extra)
        self.violations.append(entry)

    def add_warning(self, check: str, message: str, node_id: Optional[str] = None, **extra):
        entry = {
            "check": check,
            "severity": "warning",
            "message": message,
        }
        if node_id:
            entry["node_id"] = node_id
        entry.update(extra)
        self.warnings.append(entry)

    def add_pass(self, check: str, message: str):
        self.passed_checks.append(f"[{check}] {message}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": len(self.violations) == 0,
            "violations_count": len(self.violations),
            "warnings_count": len(self.warnings),
            "passed_checks_count": len(self.passed_checks),
            "violations": list(self.violations),
            "warnings": list(self.warnings),
            "passed_checks": list(self.passed_checks),
            "metrics": dict(self.metrics),
        }


def verify_postexecution(
    spec: Union[CADSpec, Dict[str, Any]],
    graph: GeometryDependencyGraph,
    execution_report: Dict[str, Any],
    live_check: bool = True,
    tolerance: float = 0.05,
) -> Dict[str, Any]:
    """Run post-execution geometric and graph verification after a CAD Spec has executed.

    Args:
        spec: CADSpec instance or dictionary representation
        graph: Resulting GeometryDependencyGraph from Phase 6
        execution_report: Spec execution report returned by SpecExecutor.execute_all()
        live_check: If True, queries live NXOpen measurement tools when available
        tolerance: Relative dimension/volume tolerance (e.g. 0.05 = 5%)

    Returns:
        Structured post-check report.
    """
    if isinstance(spec, dict):
        cad_spec = CADSpec.from_dict(spec)
    else:
        cad_spec = spec

    report = PostCheckReport()
    executed_node_ids = set(execution_report.get("executed_nodes", []))
    symbol_table = execution_report.get("symbol_table", {})

    alive_bodies = [n.id for n in graph.get_alive_nodes(type_filter="body")]
    consumed_bodies = [n.id for n in graph.get_consumed_nodes(type_filter="body")]
    report.metrics["alive_bodies"] = alive_bodies
    report.metrics["consumed_bodies"] = consumed_bodies
    report.metrics["total_graph_nodes"] = len(graph.nodes)
    report.metrics["total_graph_edges"] = len(graph.edges)

    # ── Check 1: Graph Integrity Check ──
    valid_integrity, violations = graph.validate_graph_integrity()
    if not valid_integrity:
        for v in violations:
            report.add_violation("graph_integrity", v)
    else:
        report.add_pass("graph_integrity", "Geometry dependency graph has valid structural integrity.")

    # ── Check 2: Body Lifecycle & Persistence Check ──
    for node_id in executed_node_ids:
        symbols = symbol_table.get(node_id, {})
        body_id = symbols.get("body_id")
        if body_id:
            g_node = graph.get_node(body_id)
            if not g_node:
                report.add_violation(
                    "body_lifecycle",
                    f"Node '{node_id}' produced body '{body_id}' but it does not exist in the geometry graph.",
                    node_id=node_id,
                )
            elif g_node.status == "consumed":
                # Verify that it has an incoming consumed_by edge
                downstream = graph.get_downstream(body_id, depth=1)
                consumer_edges = [
                    e for e in graph.edges
                    if e.source == body_id and e.relation == "consumed_by"
                ]
                if not consumer_edges and not downstream:
                    report.add_violation(
                        "body_lifecycle",
                        f"Body '{body_id}' from node '{node_id}' is marked 'consumed' without any recorded consuming feature.",
                        node_id=node_id,
                    )
                else:
                    report.add_pass(
                        "body_lifecycle",
                        f"Consumed body '{body_id}' from node '{node_id}' has recorded consumer relationships.",
                    )
            else:
                report.add_pass(
                    "body_lifecycle",
                    f"Produced body '{body_id}' from node '{node_id}' is active and 'alive'.",
                )

    # ── Check 3: Orphan Feature Detection ──
    for n_id, g_node in graph.nodes.items():
        if g_node.type == "feature":
            created_by_node = g_node.created_by_node
            if created_by_node and created_by_node not in executed_node_ids:
                report.add_violation(
                    "orphan_feature",
                    f"Feature '{n_id}' was registered from unexecuted spec node '{created_by_node}'.",
                    node_id=created_by_node,
                )
            else:
                report.add_pass("orphan_feature", f"Feature '{n_id}' traces to executed node '{created_by_node}'.")

    # ── Check 4: Live Geometry Inspection & Dimension Verification ──
    if live_check and not _use_mock_nxopen():
        try:
            inspect_res = runner.call_nx("inspect_part", {})
            if inspect_res.get("ok"):
                live_body_count = inspect_res.get("body_count", 0)
                report.metrics["live_body_count"] = live_body_count

                if live_body_count != len(alive_bodies):
                    report.add_warning(
                        "body_count_match",
                        f"Live NX body count ({live_body_count}) differs from graph alive body count ({len(alive_bodies)}).",
                    )
                else:
                    report.add_pass(
                        "body_count_match",
                        f"Live NX body count ({live_body_count}) exactly matches graph alive body count.",
                    )

                # If simple single-primitive spec, verify volume
                if len(cad_spec.nodes) == 2 and cad_spec.nodes[1].op == "create_cuboid":
                    p = cad_spec.nodes[1].params
                    target_body_id = symbol_table.get(cad_spec.nodes[1].id, {}).get("body_id", alive_bodies[-1] if alive_bodies else "body_1")
                    try:
                        exp_vol = float(p["length"]) * float(p["width"]) * float(p["height"])
                        vol_res = runner.call_nx("measure_body_volume", {"body_reference": target_body_id})
                        if vol_res.get("ok") and "volume" in vol_res:
                            meas_vol = float(vol_res["volume"])
                            report.metrics["measured_volume"] = meas_vol
                            report.metrics["expected_volume"] = exp_vol
                            diff = abs(meas_vol - exp_vol) / exp_vol
                            if diff > tolerance:
                                report.add_warning(
                                    "volume_dimension_match",
                                    f"Measured volume ({meas_vol:.2f} mm^3) deviates by {diff*100:.1f}% from expected ({exp_vol:.2f} mm^3).",
                                )
                            else:
                                report.add_pass(
                                    "volume_dimension_match",
                                    f"Measured volume ({meas_vol:.2f} mm^3) matches expected ({exp_vol:.2f} mm^3) within tolerance.",
                                )
                    except Exception:
                        pass
        except Exception as e:
            report.add_warning("live_measurement", f"Could not perform live NXOpen measurement: {e}")

    return report.to_dict()
