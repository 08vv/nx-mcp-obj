"""
feature_graph.py
================
Phase 3: Multi-Axis Feature Dependency Graph (CAD DAG).

Replaces single global-Y axis station stacking with a true Directed Acyclic
Feature Graph (DAG) of CAD operations:
    Base Solid -> Child Cuts / Bores -> Child Bosses -> Patterns -> Edge Blends

Every node supports an arbitrary 3D local datum coordinate system (origin, normal, in-plane ref),
so features can be oriented along any axis in 3D space.

Geometric Justifications for Core Thresholds:
- revolve_min_area_fraction (0.25): Pareto envelope rule; base solid envelope must cover >= 25% of surface.
- revolve_min_angular_span_deg (270.0): 3/4 turn separates full revolution from fillets/sidewalls (<= 180 deg).
- cavity_normal_dot_threshold (-0.30): Distinguishes inward cavity normals from outward boss normals.
- parallel_plane_dot_threshold (0.98): Angular alignment within ~11.5 deg for parallel functional faces.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import trimesh

from .primitive_feature_extractor import ExtractedFeature
from .primitive_segmenter import PrimitivePatch


class CADNodeType(str, Enum):
    BASE_SOLID = "BASE_SOLID"
    SUBTRACTIVE_FEATURE = "SUBTRACTIVE_FEATURE"
    ADDITIVE_FEATURE = "ADDITIVE_FEATURE"
    PATTERN_FEATURE = "PATTERN_FEATURE"
    TRANSITION_FEATURE = "TRANSITION_FEATURE"


class CADOperationType(str, Enum):
    REVOLVE = "REVOLVE"
    LOFT = "LOFT"
    EXTRUDE = "EXTRUDE"
    HOLE = "HOLE"
    COMPOUND_HOLE = "COMPOUND_HOLE"
    POCKET = "POCKET"
    BOSS = "BOSS"
    CIRCULAR_PATTERN = "CIRCULAR_PATTERN"
    LINEAR_PATTERN = "LINEAR_PATTERN"
    EDGE_BLEND = "EDGE_BLEND"


@dataclass
class LocalDatumFrame:
    """Arbitrary 3D coordinate system for multi-axis feature placement."""
    origin: List[float]               # [x, y, z]
    normal: List[float]               # primary normal / tool axis [nx, ny, nz]
    x_axis: List[float]               # in-plane reference vector [ux, uy, uz]
    y_axis: List[float]               # orthogonal in-plane vector [wx, wy, wz]

    @classmethod
    def from_normal_and_origin(cls, normal: List[float], origin: List[float]) -> LocalDatumFrame:
        n = np.array(normal, dtype=float)
        norm_len = np.linalg.norm(n)
        if norm_len < 1e-6:
            n = np.array([0.0, 1.0, 0.0])
        else:
            n = n / norm_len

        # Choose stable reference vector not parallel to n
        ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.8 else np.array([0.0, 1.0, 0.0])
        u = np.cross(n, ref)
        u /= np.linalg.norm(u)
        w = np.cross(n, u)
        w /= np.linalg.norm(w)

        return cls(
            origin=[round(float(x), 4) for x in origin],
            normal=[round(float(x), 4) for x in n],
            x_axis=[round(float(x), 4) for x in u],
            y_axis=[round(float(x), 4) for x in w],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CADFeatureNode:
    """A node in the CAD Feature Dependency Graph representing a single CAD feature."""
    node_id: str
    node_type: CADNodeType
    operation: CADOperationType
    parent_id: Optional[str]
    datum_frame: LocalDatumFrame
    parameters: Dict[str, Any]
    expressions: Dict[str, float] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    confidence: float = 1.0
    source_primitive_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "operation": self.operation.value,
            "parent_id": self.parent_id,
            "datum_frame": self.datum_frame.to_dict(),
            "parameters": self.parameters,
            "expressions": self.expressions,
            "dependencies": self.dependencies,
            "confidence": round(self.confidence, 4),
            "source_primitive_ids": self.source_primitive_ids,
        }


class CADFeatureDAG:
    """
    Directed Acyclic Graph representing hierarchical parametric CAD operations.
    Enforces build order: Base Solid -> Cuts/Bosses -> Patterns -> Blends.
    """

    def __init__(self):
        self.nodes: Dict[str, CADFeatureNode] = {}
        self.edges: Dict[str, List[str]] = {}       # parent -> list of children
        self.reverse_edges: Dict[str, List[str]] = {} # child -> list of parents/dependencies

    def add_node(self, node: CADFeatureNode) -> None:
        self.nodes[node.node_id] = node
        if node.node_id not in self.edges:
            self.edges[node.node_id] = []
        if node.node_id not in self.reverse_edges:
            self.reverse_edges[node.node_id] = []

        # Connect parent dependency
        if node.parent_id:
            self.add_dependency(child_id=node.node_id, parent_id=node.parent_id)

        # Connect any additional dependencies
        for dep in node.dependencies:
            self.add_dependency(child_id=node.node_id, parent_id=dep)

    def add_dependency(self, child_id: str, parent_id: str) -> None:
        if parent_id not in self.edges:
            self.edges[parent_id] = []
        if child_id not in self.edges[parent_id]:
            self.edges[parent_id].append(child_id)

        if child_id not in self.reverse_edges:
            self.reverse_edges[child_id] = []
        if parent_id not in self.reverse_edges[child_id]:
            self.reverse_edges[child_id].append(parent_id)

    def topological_sort(self) -> List[CADFeatureNode]:
        """
        Returns nodes in valid CAD reconstruction order.
        Guarantees that a parent feature is always built before its children.
        """
        in_degree = {nid: len(self.reverse_edges.get(nid, [])) for nid in self.nodes}
        queue = [nid for nid, deg in in_degree.items() if deg == 0]

        # Prioritize Base Solids first in queue
        queue.sort(key=lambda nid: 0 if self.nodes[nid].node_type == CADNodeType.BASE_SOLID else 1)

        sorted_nodes: List[CADFeatureNode] = []
        while queue:
            curr_id = queue.pop(0)
            sorted_nodes.append(self.nodes[curr_id])

            for child_id in self.edges.get(curr_id, []):
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)

        if len(sorted_nodes) != len(self.nodes):
            missing = set(self.nodes.keys()) - {n.node_id for n in sorted_nodes}
            raise ValueError(f"Cycle or unresolved dependency in CAD Feature Graph. Unresolved: {missing}")

        return sorted_nodes

    def to_reconstruction_intent(self) -> Dict[str, Any]:
        """
        Serializes the DAG into the standardized, geometry-derived Reconstruction Intent IR.
        """
        sorted_nodes = self.topological_sort()
        all_expressions: Dict[str, float] = {}
        for n in sorted_nodes:
            all_expressions.update(n.expressions)

        base_nodes = [n for n in sorted_nodes if n.node_type == CADNodeType.BASE_SOLID]
        primary_axis = [0.0, 1.0, 0.0]
        shape_family = "UNKNOWN"

        if base_nodes:
            base = base_nodes[0]
            primary_axis = base.datum_frame.normal
            if base.operation == CADOperationType.REVOLVE:
                shape_family = "AXISYMMETRIC_REVOLVE"
            elif base.operation == CADOperationType.LOFT:
                shape_family = "LOFTED_SOLID"
            elif base.operation == CADOperationType.EXTRUDE:
                shape_family = "PRISMATIC_EXTRUSION"

        return {
            "$schema": "nx_mcp_reconstruction_intent_v2",
            "global_shape_family": shape_family,
            "primary_axis": primary_axis,
            "feature_tree": [n.to_dict() for n in sorted_nodes],
            "expressions": all_expressions,
            "node_count": len(sorted_nodes),
        }


class FeatureGraphBuilder:
    """
    Transforms extracted primitive features into a validated CAD Feature DAG.
    """

    def __init__(self, mesh: trimesh.Trimesh, extracted_features: List[ExtractedFeature]):
        # Normalize to millimeters if mesh extents < 10.0
        scale = 100.0 if (mesh.bounds[1][1] - mesh.bounds[0][1]) < 10.0 else 1.0
        self.mesh = mesh.copy()
        if scale != 1.0:
            self.mesh.vertices *= scale
        self.features = extracted_features

    def build_dag(self) -> CADFeatureDAG:
        """Constructs and returns the fully linked CAD Feature DAG."""
        dag = CADFeatureDAG()
        base_node_id: Optional[str] = None

        # -------------------------------------------------------------------
        # 1. Add Base Solid Node
        # -------------------------------------------------------------------
        base_feats = [f for f in self.features if f.feature_type in ("REVOLVE_BODY", "LOFT_BODY", "PRISMATIC_EXTRUSION")]
        if base_feats:
            bf = base_feats[0]
            base_node_id = "base_solid_1"

            if bf.feature_type == "REVOLVE_BODY":
                normal = bf.parameters["axis_direction"]
                origin = bf.parameters["axis_origin"]
                datum = LocalDatumFrame.from_normal_and_origin(normal, origin)
                dia = float(bf.parameters["diameter_mm"])
                length = float(bf.parameters["length_mm"])

                dag.add_node(CADFeatureNode(
                    node_id=base_node_id,
                    node_type=CADNodeType.BASE_SOLID,
                    operation=CADOperationType.REVOLVE,
                    parent_id=None,
                    datum_frame=datum,
                    parameters=bf.parameters,
                    expressions={
                        "P1_BASE_DIAMETER": round(dia, 3),
                        "P2_BASE_HEIGHT": round(length, 3),
                    },
                    confidence=bf.confidence,
                    source_primitive_ids=bf.source_primitive_ids,
                ))

            elif bf.feature_type == "LOFT_BODY":
                bounds_min = bf.parameters["bounds_min_mm"]
                bounds_max = bf.parameters["bounds_max_mm"]
                center = [(a + b) / 2.0 for a, b in zip(bounds_min, bounds_max)]
                datum = LocalDatumFrame.from_normal_and_origin([0.0, 1.0, 0.0], center)
                ext = bf.parameters["extents_mm"]

                dag.add_node(CADFeatureNode(
                    node_id=base_node_id,
                    node_type=CADNodeType.BASE_SOLID,
                    operation=CADOperationType.LOFT,
                    parent_id=None,
                    datum_frame=datum,
                    parameters=bf.parameters,
                    expressions={
                        "P1_LOFT_SPAN_X": round(float(ext[0]), 3),
                        "P2_LOFT_SPAN_Y": round(float(ext[1]), 3),
                        "P3_LOFT_SPAN_Z": round(float(ext[2]), 3),
                    },
                    confidence=bf.confidence,
                    source_primitive_ids=bf.source_primitive_ids,
                ))

            elif bf.feature_type == "PRISMATIC_EXTRUSION":
                axis = bf.parameters.get("extrusion_axis", [0.0, 1.0, 0.0])
                datum = LocalDatumFrame.from_normal_and_origin(axis, [0.0, 0.0, 0.0])
                height = float(bf.parameters.get("height_mm", 50.0))

                dag.add_node(CADFeatureNode(
                    node_id=base_node_id,
                    node_type=CADNodeType.BASE_SOLID,
                    operation=CADOperationType.EXTRUDE,
                    parent_id=None,
                    datum_frame=datum,
                    parameters=bf.parameters,
                    expressions={
                        "P1_EXTRUDE_HEIGHT": round(height, 3),
                    },
                    confidence=bf.confidence,
                    source_primitive_ids=bf.source_primitive_ids,
                ))

        # -------------------------------------------------------------------
        # 2. Add Secondary Child Features (Holes, Pockets, Bosses)
        # -------------------------------------------------------------------
        feature_id_map: Dict[str, str] = {} # maps ExtractedFeature.feature_id to CADFeatureNode.node_id

        for idx, feat in enumerate(self.features):
            if feat.feature_type == "HOLE":
                nid = f"hole_{idx + 1}"
                feature_id_map[feat.feature_id] = nid
                center = feat.parameters["center"]
                direction = feat.parameters["direction"]
                datum = LocalDatumFrame.from_normal_and_origin(direction, center)
                dia = float(feat.parameters["diameter_mm"])
                depth = float(feat.parameters["depth_mm"])

                dag.add_node(CADFeatureNode(
                    node_id=nid,
                    node_type=CADNodeType.SUBTRACTIVE_FEATURE,
                    operation=CADOperationType.HOLE,
                    parent_id=base_node_id,
                    datum_frame=datum,
                    parameters=feat.parameters,
                    expressions={
                        f"P_HOLE_{idx + 1}_DIA": round(dia, 3),
                        f"P_HOLE_{idx + 1}_DEPTH": round(depth, 3),
                    },
                    confidence=feat.confidence,
                    source_primitive_ids=feat.source_primitive_ids,
                ))

            elif feat.feature_type == "COMPOUND_HOLE":
                nid = f"cbore_hole_{idx + 1}"
                feature_id_map[feat.feature_id] = nid
                center = feat.parameters["center"]
                direction = feat.parameters["direction"]
                datum = LocalDatumFrame.from_normal_and_origin(direction, center)
                cbore_dia = float(feat.parameters["cbore_diameter_mm"])
                cbore_depth = float(feat.parameters["cbore_depth_mm"])
                dia = float(feat.parameters["diameter_mm"])
                depth = float(feat.parameters["depth_mm"])

                dag.add_node(CADFeatureNode(
                    node_id=nid,
                    node_type=CADNodeType.SUBTRACTIVE_FEATURE,
                    operation=CADOperationType.COMPOUND_HOLE,
                    parent_id=base_node_id,
                    datum_frame=datum,
                    parameters=feat.parameters,
                    expressions={
                        f"P_CBORE_{idx + 1}_DIA": round(cbore_dia, 3),
                        f"P_CBORE_{idx + 1}_DEPTH": round(cbore_depth, 3),
                        f"P_HOLE_{idx + 1}_DIA": round(dia, 3),
                        f"P_HOLE_{idx + 1}_DEPTH": round(depth, 3),
                    },
                    confidence=feat.confidence,
                    source_primitive_ids=feat.source_primitive_ids,
                ))

            elif feat.feature_type == "POCKET":
                nid = f"pocket_{idx + 1}"
                feature_id_map[feat.feature_id] = nid
                center = feat.parameters["center"]
                normal = feat.parameters["normal"]
                datum = LocalDatumFrame.from_normal_and_origin(normal, center)
                depth = float(feat.parameters["step_depth_mm"])

                dag.add_node(CADFeatureNode(
                    node_id=nid,
                    node_type=CADNodeType.SUBTRACTIVE_FEATURE,
                    operation=CADOperationType.POCKET,
                    parent_id=base_node_id,
                    datum_frame=datum,
                    parameters=feat.parameters,
                    expressions={
                        f"P_POCKET_{idx + 1}_DEPTH": round(depth, 3),
                    },
                    confidence=feat.confidence,
                    source_primitive_ids=feat.source_primitive_ids,
                ))

            elif feat.feature_type == "BOSS":
                nid = f"boss_{idx + 1}"
                feature_id_map[feat.feature_id] = nid
                center = feat.parameters["center"]
                normal = feat.parameters["normal"]
                datum = LocalDatumFrame.from_normal_and_origin(normal, center)
                height = float(feat.parameters["step_depth_mm"])

                dag.add_node(CADFeatureNode(
                    node_id=nid,
                    node_type=CADNodeType.ADDITIVE_FEATURE,
                    operation=CADOperationType.BOSS,
                    parent_id=base_node_id,
                    datum_frame=datum,
                    parameters=feat.parameters,
                    expressions={
                        f"P_BOSS_{idx + 1}_HEIGHT": round(height, 3),
                    },
                    confidence=feat.confidence,
                    source_primitive_ids=feat.source_primitive_ids,
                ))

        # -------------------------------------------------------------------
        # 3. Add Pattern Features
        # -------------------------------------------------------------------
        for idx, feat in enumerate(self.features):
            if feat.feature_type == "CIRCULAR_PATTERN":
                nid = f"pattern_circ_{idx + 1}"
                target_fid = feat.parameters.get("target_feature_id")
                target_nid = feature_id_map.get(target_fid, base_node_id)
                axis_dir = feat.parameters["axis_direction"]
                axis_orig = feat.parameters["axis_origin"]
                datum = LocalDatumFrame.from_normal_and_origin(axis_dir, axis_orig)

                count = int(feat.parameters["instance_count"])
                pitch = float(feat.parameters["pitch_deg"])
                p_radius = float(feat.parameters.get("pitch_radius_mm", 0.0))

                dag.add_node(CADFeatureNode(
                    node_id=nid,
                    node_type=CADNodeType.PATTERN_FEATURE,
                    operation=CADOperationType.CIRCULAR_PATTERN,
                    parent_id=target_nid,
                    datum_frame=datum,
                    parameters=feat.parameters,
                    expressions={
                        f"P_PAT_{idx + 1}_COUNT": float(count),
                        f"P_PAT_{idx + 1}_PITCH": round(pitch, 3),
                        f"P_PAT_{idx + 1}_RADIUS": round(p_radius, 3),
                    },
                    confidence=feat.confidence,
                    source_primitive_ids=feat.source_primitive_ids,
                ))

        return dag
