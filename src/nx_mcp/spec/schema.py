"""Structured schema models for CAD Spec operation graphs."""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Tuple, Union

# Regex patterns for reference syntax
# 1. Node output reference: $node_id.field_name (e.g. $n1.body_id, $n2.feature_id)
NODE_REF_PATTERN = re.compile(r"^\$([a-zA-Z0-9_\-]+)\.([a-zA-Z0-9_]+)$")
EMBEDDED_NODE_REF_PATTERN = re.compile(r"\$([a-zA-Z0-9_\-]+)\.([a-zA-Z0-9_]+)")

# 2. Expression reference: $expr:NAME (e.g. $expr:CUBOID_1_L)
EXPR_REF_PATTERN = re.compile(r"^\$expr:([a-zA-Z0-9_]+)$")
EMBEDDED_EXPR_REF_PATTERN = re.compile(r"\$expr:([a-zA-Z0-9_]+)")

# 3. Calc reference: $calc:EXPRESSION (e.g. $calc:100 / 2 - 5)
CALC_REF_PATTERN = re.compile(r"^\$calc:(.*)$")

# 4. Function reference: $fn:func_name(args) (e.g. $fn:bolt_circle(count=6, pcd=50))
FN_REF_PATTERN = re.compile(r"^\$fn:([a-zA-Z_][a-zA-Z0-9_]*)\((.*)\)$", re.DOTALL)


def is_symbolic_ref(val: Any) -> bool:
    """Return True if val is a node output reference string ($node_id.field)."""
    return isinstance(val, str) and bool(NODE_REF_PATTERN.match(val.strip()))


def parse_symbolic_ref(val: str) -> Optional[Tuple[str, str]]:
    """Parse a symbolic reference into (node_id, field_name) or None."""
    if not isinstance(val, str):
        return None
    m = NODE_REF_PATTERN.match(val.strip())
    if m:
        return m.group(1), m.group(2)
    return None


def is_expr_ref(val: Any) -> bool:
    """Return True if val is an expression reference string ($expr:NAME)."""
    return isinstance(val, str) and bool(EXPR_REF_PATTERN.match(val.strip()))


def parse_expr_ref(val: str) -> Optional[str]:
    """Parse an expression reference into expression name or None."""
    if not isinstance(val, str):
        return None
    m = EXPR_REF_PATTERN.match(val.strip())
    if m:
        return m.group(1)
    return None


def is_calc_ref(val: Any) -> bool:
    """Return True if val is a $calc:... reference string."""
    return isinstance(val, str) and bool(CALC_REF_PATTERN.match(val.strip()))


def parse_calc_ref(val: str) -> Optional[str]:
    """Parse a calc reference string into the raw calculation expression or None."""
    if not isinstance(val, str):
        return None
    m = CALC_REF_PATTERN.match(val.strip())
    if m:
        return m.group(1).strip()
    return None


def is_fn_ref(val: Any) -> bool:
    """Return True if val is a $fn:func_name(...) reference string."""
    return isinstance(val, str) and bool(FN_REF_PATTERN.match(val.strip()))


def parse_fn_ref(val: str) -> Optional[Tuple[str, str]]:
    """Parse a function reference into (func_name, raw_args_string) or None."""
    if not isinstance(val, str):
        return None
    m = FN_REF_PATTERN.match(val.strip())
    if m:
        return m.group(1), m.group(2).strip()
    return None


def extract_node_references(data: Any) -> List[Tuple[str, str]]:
    """Recursively extract all ($node_id, field_name) references from a data structure.

    Also extracts node references embedded inside $calc: expressions.
    """
    refs = []
    if isinstance(data, str):
        ref = parse_symbolic_ref(data)
        if ref:
            refs.append(ref)
        elif is_calc_ref(data):
            # Scan inside the calc expression for embedded $nodeId.field refs
            calc_body = parse_calc_ref(data) or ""
            for m in EMBEDDED_NODE_REF_PATTERN.finditer(calc_body):
                refs.append((m.group(1), m.group(2)))
    elif isinstance(data, dict):
        for v in data.values():
            refs.extend(extract_node_references(v))
    elif isinstance(data, (list, tuple)):
        for item in data:
            refs.extend(extract_node_references(item))
    return refs


@dataclass
class SpecNode:
    id: str
    op: str
    params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    produces: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpecNode":
        node_id = str(data.get("id", "")).strip()
        op = str(data.get("op", "")).strip()
        params = dict(data.get("params", {}))
        explicit_deps = list(data.get("depends_on", []))
        produces = dict(data.get("produces", {}))

        # Automatically infer dependencies from symbolic references in params
        inferred_deps = [ref[0] for ref in extract_node_references(params)]
        all_deps = []
        for d in explicit_deps + inferred_deps:
            if d and d not in all_deps and d != node_id:
                all_deps.append(d)

        return cls(
            id=node_id,
            op=op,
            params=params,
            depends_on=all_deps,
            produces=produces,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "op": self.op,
            "params": self.params,
            "depends_on": self.depends_on,
            "produces": self.produces,
        }


@dataclass
class CADSpec:
    part_name: str = "model"
    units: str = "mm"
    nodes: List[SpecNode] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CADSpec":
        part_name = str(data.get("part_name", "model")).strip()
        units = str(data.get("units", "mm")).strip().lower()
        nodes_raw = data.get("nodes", [])
        nodes = [SpecNode.from_dict(n) for n in nodes_raw]
        return cls(part_name=part_name, units=units, nodes=nodes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_name": self.part_name,
            "units": self.units,
            "nodes": [n.to_dict() for n in self.nodes],
        }
