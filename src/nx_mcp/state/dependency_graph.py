"""Persistent, queryable dependency graph of actual resulting CAD geometry state.

Models the ground-truth execution state returned by the NX bridge:
- Nodes: Persistent entities (body_N, feature_N, sketch_N, curve_N, profile_N, etc.)
- Status: 'alive' (currently existing active geometry) vs 'consumed' (absorbed/deleted by operations)
- Edges: Geometric relationships ('consumed_by', 'produced_by', 'modified_by')
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from collections import deque


@dataclass
class GeometryNode:
    """A single geometric entity node in the state graph."""
    id: str
    type: str  # body, feature, profile, curve, sketch, component
    status: str = "alive"  # 'alive' or 'consumed'
    created_by_op: Optional[str] = None
    created_by_node: Optional[str] = None  # SpecNode id if executed from a CADSpec
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeometryNode":
        return cls(
            id=data["id"],
            type=data.get("type", _infer_type_from_id(data["id"])),
            status=data.get("status", "alive"),
            created_by_op=data.get("created_by_op"),
            created_by_node=data.get("created_by_node"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class GeometryEdge:
    """A directed edge representing geometric dependency."""
    source: str  # source node id
    target: str  # target node id
    relation: str  # 'consumed_by', 'produced_by', 'modified_by', 'contains'
    op: Optional[str] = None
    spec_node: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeometryEdge":
        return cls(
            source=data["source"],
            target=data["target"],
            relation=data["relation"],
            op=data.get("op"),
            spec_node=data.get("spec_node"),
        )


def _infer_type_from_id(entity_id: str) -> str:
    """Infer entity type from standard monotonic ID prefix."""
    if entity_id.startswith("body_"):
        return "body"
    if entity_id.startswith("feature_"):
        return "feature"
    if entity_id.startswith("profile_"):
        return "profile"
    if entity_id.startswith("curve_"):
        return "curve"
    if entity_id.startswith("sketch_"):
        return "sketch"
    if entity_id.startswith("comp_") or entity_id.startswith("component_"):
        return "component"
    return "unknown"


class GeometryDependencyGraph:
    """Directed dependency graph tracking ground-truth NX geometry state."""

    def __init__(self, part_name: Optional[str] = None):
        self.part_name: Optional[str] = part_name
        self.nodes: Dict[str, GeometryNode] = {}
        # Adjacency lists for fast bidirectional lookups
        # outgoing: source -> list of edges (downstream)
        self._outgoing: Dict[str, List[GeometryEdge]] = {}
        # incoming: target -> list of edges (upstream)
        self._incoming: Dict[str, List[GeometryEdge]] = {}
        # Consumption history: entity_id -> list of features/ops that consumed it
        self._consumption_history: Dict[str, List[Dict[str, Any]]] = {}

    def register_node(
        self,
        node_id: str,
        node_type: Optional[str] = None,
        status: str = "alive",
        created_by_op: Optional[str] = None,
        created_by_node: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> GeometryNode:
        """Register or update a geometry node in the graph."""
        if not node_type:
            node_type = _infer_type_from_id(node_id)

        if node_id in self.nodes:
            node = self.nodes[node_id]
            # Update attributes if newly provided
            if created_by_op and not node.created_by_op:
                node.created_by_op = created_by_op
            if created_by_node and not node.created_by_node:
                node.created_by_node = created_by_node
            if metadata:
                node.metadata.update(metadata)
            return node

        node = GeometryNode(
            id=node_id,
            type=node_type,
            status=status,
            created_by_op=created_by_op,
            created_by_node=created_by_node,
            metadata=metadata or {},
        )
        self.nodes[node_id] = node
        self._outgoing.setdefault(node_id, [])
        self._incoming.setdefault(node_id, [])
        return node

    def add_edge(
        self,
        source: str,
        target: str,
        relation: str,
        op: Optional[str] = None,
        spec_node: Optional[str] = None,
    ) -> GeometryEdge:
        """Add a directed edge between two geometric entities."""
        # Ensure both nodes exist
        if source not in self.nodes:
            self.register_node(source)
        if target not in self.nodes:
            self.register_node(target)

        edge = GeometryEdge(
            source=source,
            target=target,
            relation=relation,
            op=op,
            spec_node=spec_node,
        )
        self._outgoing[source].append(edge)
        self._incoming[target].append(edge)
        return edge

    def record_operation(
        self,
        op: str,
        spec_node_id: Optional[str] = None,
        produced: Optional[List[str]] = None,
        consumed: Optional[List[str]] = None,
        modified: Optional[List[str]] = None,
        feature_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an executed operation into the geometry dependency graph.

        Args:
            op: Operation name (e.g. 'loft', 'add_hole', 'boolean_subtract', 'shell')
            spec_node_id: Optional CADSpec node ID (e.g. 'n1', 'cut_1')
            produced: Entity IDs created by this operation (e.g. ['body_1', 'feature_1'])
            consumed: Entity IDs consumed/absorbed by this operation (e.g. ['body_2'])
            modified: Entity IDs modified in-place (e.g. surviving target 'body_1')
            feature_id: Specific feature ID representing the operation in NX
            metadata: Additional operation metadata (e.g. parameters)
        """
        produced = produced or []
        consumed = consumed or []
        modified = modified or []

        # If a feature ID represents the operation
        feat_node = None
        if feature_id:
            feat_node = self.register_node(
                feature_id,
                node_type="feature",
                status="alive",
                created_by_op=op,
                created_by_node=spec_node_id,
                metadata=metadata,
            )

        # 1. Process consumed entities (e.g. tool bodies in booleans, profiles in loft)
        for cid in consumed:
            if not cid:
                continue
            c_node = self.register_node(cid)
            c_node.status = "consumed"
            self._consumption_history.setdefault(cid, []).append({
                "op": op,
                "feature_id": feature_id,
                "spec_node": spec_node_id,
            })
            if feature_id:
                self.add_edge(cid, feature_id, relation="consumed_by", op=op, spec_node=spec_node_id)
            else:
                for pid in produced:
                    self.add_edge(cid, pid, relation="consumed_by", op=op, spec_node=spec_node_id)

        # 2. Process produced entities (e.g. new bodies, new curves, new profiles)
        for pid in produced:
            if not pid or pid == feature_id:
                continue
            p_node = self.register_node(
                pid,
                status="alive",
                created_by_op=op,
                created_by_node=spec_node_id,
                metadata=metadata,
            )
            if feature_id:
                self.add_edge(feature_id, pid, relation="produced_by", op=op, spec_node=spec_node_id)

        # 3. Process modified entities (e.g. surviving target body in subtract/unite/shell)
        for mid in modified:
            if not mid:
                continue
            m_node = self.register_node(mid)
            # A modified entity remains alive
            m_node.status = "alive"
            if feature_id:
                self.add_edge(feature_id, mid, relation="modified_by", op=op, spec_node=spec_node_id)

    def get_node(self, node_id: str) -> Optional[GeometryNode]:
        """Retrieve a node by its monotonic ID."""
        return self.nodes.get(node_id)

    def get_alive_nodes(self, type_filter: Optional[str] = None) -> List[GeometryNode]:
        """Return all nodes currently in 'alive' status."""
        return [
            n for n in self.nodes.values()
            if n.status == "alive" and (type_filter is None or n.type == type_filter)
        ]

    def get_consumed_nodes(self, type_filter: Optional[str] = None) -> List[GeometryNode]:
        """Return all nodes in 'consumed' status."""
        return [
            n for n in self.nodes.values()
            if n.status == "consumed" and (type_filter is None or n.type == type_filter)
        ]

    @property
    def edges(self) -> List[GeometryEdge]:
        """Return all edges in the dependency graph."""
        res = []
        for edge_list in self._outgoing.values():
            res.extend(edge_list)
        return res

    def get_upstream(self, node_id: str, depth: Optional[int] = None) -> List[Dict[str, Any]]:
        """Query all entities upstream of node_id (what did this entity come from or depend on?).

        Traverses incoming edges backwards using BFS.
        """
        if node_id not in self.nodes:
            return []

        results = []
        visited: Set[str] = {node_id}
        queue = deque([(node_id, 0)])

        while queue:
            curr_id, curr_depth = queue.popleft()
            if depth is not None and curr_depth >= depth:
                continue

            for edge in self._incoming.get(curr_id, []):
                src = edge.source
                results.append({
                    "id": src,
                    "type": self.nodes[src].type if src in self.nodes else _infer_type_from_id(src),
                    "status": self.nodes[src].status if src in self.nodes else "unknown",
                    "relation": edge.relation,
                    "op": edge.op,
                    "spec_node": edge.spec_node,
                    "depth": curr_depth + 1,
                })
                if src not in visited:
                    visited.add(src)
                    queue.append((src, curr_depth + 1))

        return results

    def get_downstream(self, node_id: str, depth: Optional[int] = None) -> List[Dict[str, Any]]:
        """Query all entities downstream of node_id (what depends on or was produced from this entity?).

        Traverses outgoing edges forwards using BFS.
        """
        if node_id not in self.nodes:
            return []

        results = []
        visited: Set[str] = {node_id}
        queue = deque([(node_id, 0)])

        while queue:
            curr_id, curr_depth = queue.popleft()
            if depth is not None and curr_depth >= depth:
                continue

            for edge in self._outgoing.get(curr_id, []):
                tgt = edge.target
                results.append({
                    "id": tgt,
                    "type": self.nodes[tgt].type if tgt in self.nodes else _infer_type_from_id(tgt),
                    "status": self.nodes[tgt].status if tgt in self.nodes else "unknown",
                    "relation": edge.relation,
                    "op": edge.op,
                    "spec_node": edge.spec_node,
                    "depth": curr_depth + 1,
                })
                if tgt not in visited:
                    visited.add(tgt)
                    queue.append((tgt, curr_depth + 1))

        return results

    def validate_graph_integrity(self) -> Tuple[bool, List[str]]:
        """Validate geometric state graph integrity.

        Integrity Rules:
        1. No double-consumption: Every consumed entity must have been consumed by at most one operation.
        2. Every node in an edge must exist in nodes map.
        3. Every consumed node must have at least one outgoing 'consumed_by' relationship.
        """
        violations = []

        # 1. Double consumption check
        for cid, history in self._consumption_history.items():
            if len(history) > 1:
                ops_str = ", ".join(f"'{h.get('op')}' (feature: {h.get('feature_id')})" for h in history)
                violations.append(
                    f"Double consumption detected: Entity '{cid}' was consumed {len(history)} times by: {ops_str}."
                )

        # 2. Edge node existence check
        for src, edges in self._outgoing.items():
            if src not in self.nodes:
                violations.append(f"Edge source node '{src}' not registered in graph nodes.")
            for edge in edges:
                if edge.target not in self.nodes:
                    violations.append(f"Edge target node '{edge.target}' not registered in graph nodes.")

        # 3. Consumed status consistency
        for nid, node in self.nodes.items():
            if node.status == "consumed":
                outgoing_consumed = [
                    e for e in self._outgoing.get(nid, [])
                    if e.relation == "consumed_by"
                ]
                if not outgoing_consumed and nid not in self._consumption_history:
                    violations.append(
                        f"Node '{nid}' is marked as 'consumed' but has no 'consumed_by' edge or consumption history."
                    )

        return len(violations) == 0, violations

    def to_dict(self) -> Dict[str, Any]:
        """Serialize dependency graph to dictionary representation."""
        all_edges = []
        for edges in self._outgoing.values():
            for edge in edges:
                all_edges.append(edge.to_dict())

        return {
            "part_name": self.part_name,
            "total_nodes": len(self.nodes),
            "alive_count": len(self.get_alive_nodes()),
            "consumed_count": len(self.get_consumed_nodes()),
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": all_edges,
            "consumption_history": self._consumption_history,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeometryDependencyGraph":
        """Deserialize graph from dictionary."""
        graph = cls(part_name=data.get("part_name"))
        for nid, ndata in data.get("nodes", {}).items():
            graph.nodes[nid] = GeometryNode.from_dict(ndata)
            graph._outgoing.setdefault(nid, [])
            graph._incoming.setdefault(nid, [])

        for edata in data.get("edges", []):
            edge = GeometryEdge.from_dict(edata)
            graph._outgoing.setdefault(edge.source, []).append(edge)
            graph._incoming.setdefault(edge.target, []).append(edge)

        graph._consumption_history = data.get("consumption_history", {})
        return graph


# ── Global session dependency graph instance ──
_SESSION_DEPENDENCY_GRAPH = GeometryDependencyGraph()


def get_session_graph() -> GeometryDependencyGraph:
    """Return the active global session dependency graph."""
    global _SESSION_DEPENDENCY_GRAPH
    return _SESSION_DEPENDENCY_GRAPH


def reset_session_graph(part_name: Optional[str] = None) -> GeometryDependencyGraph:
    """Reset the session dependency graph (e.g. on new part creation)."""
    global _SESSION_DEPENDENCY_GRAPH
    _SESSION_DEPENDENCY_GRAPH = GeometryDependencyGraph(part_name=part_name)
    return _SESSION_DEPENDENCY_GRAPH
