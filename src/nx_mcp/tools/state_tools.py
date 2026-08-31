"""MCP tools for querying the CAD geometry dependency and state graph."""

import json
from typing import Any, Dict, List, Optional, Literal
from ..response import ToolError, ToolResult
from ..state.dependency_graph import get_session_graph
from .registry import mcp_tool


@mcp_tool(
    "get_dependency_graph",
    "Query the persistent geometry dependency graph of actual resulting NX CAD state",
)
def get_dependency_graph(scope: Literal["session", "part"] = "session") -> Any:
    """Retrieve the persistent dependency graph of actual NX geometry state.

    Returns:
        JSON representation containing all nodes (bodies, features, sketches, profiles, curves),
        their status ('alive' vs 'consumed'), and geometric dependency edges ('consumed_by',
        'produced_by', 'modified_by').
    """
    try:
        graph = get_session_graph()
        data = graph.to_dict()
        valid, violations = graph.validate_graph_integrity()
        data["integrity_valid"] = valid
        data["integrity_violations"] = violations
        return ToolResult(
            f"Geometry Dependency Graph: {data['total_nodes']} total nodes "
            f"({data['alive_count']} alive, {data['consumed_count']} consumed), "
            f"{len(data['edges'])} edges. Integrity: {'VALID' if valid else 'VIOLATIONS: ' + str(violations)}\n\n"
            f"{json.dumps(data, indent=2)}"
        )
    except Exception as e:
        return ToolError(f"Failed to query dependency graph: {e}")


@mcp_tool(
    "get_downstream",
    "Query all geometric entities and features downstream of a given node ID",
)
def get_downstream(node_id: str, depth: int = 0) -> Any:
    """Query what geometric entities/features depend on or were produced downstream from node_id.

    Args:
        node_id: Monotonic ID of the entity or feature (e.g. 'body_1', 'feature_2', 'profile_1')
        depth: Maximum traversal depth (0 or negative for unlimited depth)
    """
    try:
        graph = get_session_graph()
        node = graph.get_node(node_id)
        if not node:
            return ToolError(f"Node '{node_id}' not found in geometry dependency graph.")

        d_limit = None if depth <= 0 else depth
        downstream = graph.get_downstream(node_id, depth=d_limit)
        return ToolResult(
            f"Downstream from '{node_id}' ({node.type}, status: {node.status}): {len(downstream)} entities found.\n\n"
            f"{json.dumps(downstream, indent=2)}"
        )
    except Exception as e:
        return ToolError(f"Failed to query downstream for '{node_id}': {e}")


@mcp_tool(
    "get_upstream",
    "Query all geometric entities and features upstream of a given node ID",
)
def get_upstream(node_id: str, depth: int = 0) -> Any:
    """Query what geometric entities/features contributed to or created node_id.

    Args:
        node_id: Monotonic ID of the entity or feature (e.g. 'body_1', 'feature_2', 'profile_1')
        depth: Maximum traversal depth (0 or negative for unlimited depth)
    """
    try:
        graph = get_session_graph()
        node = graph.get_node(node_id)
        if not node:
            return ToolError(f"Node '{node_id}' not found in geometry dependency graph.")

        d_limit = None if depth <= 0 else depth
        upstream = graph.get_upstream(node_id, depth=d_limit)
        return ToolResult(
            f"Upstream of '{node_id}' ({node.type}, status: {node.status}): {len(upstream)} entities found.\n\n"
            f"{json.dumps(upstream, indent=2)}"
        )
    except Exception as e:
        return ToolError(f"Failed to query upstream for '{node_id}': {e}")


@mcp_tool(
    "validate_dependency_graph",
    "Validate the geometric integrity of the active dependency graph (e.g. check for double-consumption)",
)
def validate_dependency_graph() -> Any:
    """Validate geometric state graph integrity.

    Verifies that no entity was consumed more than once (double consumption) and all
    edge references are internally consistent.
    """
    try:
        graph = get_session_graph()
        valid, violations = graph.validate_graph_integrity()
        if valid:
            return ToolResult(
                f"Dependency graph integrity is VALID ({len(graph.nodes)} nodes, {len(graph.get_alive_nodes())} alive, "
                f"{len(graph.get_consumed_nodes())} consumed)."
            )
        else:
            return ToolError(
                f"Dependency graph integrity FAILED with {len(violations)} violation(s):\n"
                + "\n".join(f"- {v}" for v in violations)
            )
    except Exception as e:
        return ToolError(f"Failed to validate dependency graph: {e}")
