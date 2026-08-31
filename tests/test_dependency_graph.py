"""Unit tests for GeometryDependencyGraph — pure offline tests, no NX, no mocking."""

import pytest
from nx_mcp.state.dependency_graph import (
    GeometryDependencyGraph,
    GeometryNode,
    GeometryEdge,
    get_session_graph,
    reset_session_graph,
)


class TestGeometryNodeAndEdge:
    def test_node_type_inference(self):
        n_body = GeometryNode.from_dict({"id": "body_1"})
        assert n_body.type == "body"
        assert n_body.status == "alive"

        n_feat = GeometryNode.from_dict({"id": "feature_5"})
        assert n_feat.type == "feature"

        n_prof = GeometryNode.from_dict({"id": "profile_2"})
        assert n_prof.type == "profile"

        n_curve = GeometryNode.from_dict({"id": "curve_10"})
        assert n_curve.type == "curve"

    def test_edge_serialization_roundtrip(self):
        edge = GeometryEdge(
            source="body_2",
            target="feature_3",
            relation="consumed_by",
            op="add_hole",
            spec_node="hole_1",
        )
        d = edge.to_dict()
        restored = GeometryEdge.from_dict(d)
        assert restored.source == "body_2"
        assert restored.target == "feature_3"
        assert restored.relation == "consumed_by"
        assert restored.op == "add_hole"
        assert restored.spec_node == "hole_1"


class TestGeometryDependencyGraphOperations:
    def test_record_cuboid_creation(self):
        graph = GeometryDependencyGraph("test_part")
        graph.record_operation(
            op="create_cuboid",
            spec_node_id="n1",
            produced=["body_1"],
            feature_id="feature_1",
        )
        assert "body_1" in graph.nodes
        assert "feature_1" in graph.nodes
        assert graph.nodes["body_1"].status == "alive"
        assert graph.nodes["feature_1"].status == "alive"
        assert len(graph.get_alive_nodes()) == 2
        assert len(graph.get_consumed_nodes()) == 0

    def test_record_boolean_subtract_and_consumption(self):
        graph = GeometryDependencyGraph("test_part")
        # 1. Base cuboid
        graph.record_operation(
            op="create_cuboid",
            spec_node_id="base",
            produced=["body_1"],
            feature_id="feature_1",
        )
        # 2. Subtract cylinder hole: body_2 (tool) is consumed, body_1 is modified
        graph.record_operation(
            op="add_hole",
            spec_node_id="cut",
            consumed=["body_2"],
            modified=["body_1"],
            feature_id="feature_2",
        )

        assert graph.nodes["body_2"].status == "consumed"
        assert graph.nodes["body_1"].status == "alive"
        assert len(graph.get_consumed_nodes()) == 1
        assert graph.get_consumed_nodes()[0].id == "body_2"

        # Upstream of body_1 includes feature_2 and feature_1
        upstream_b1 = graph.get_upstream("body_1")
        upstream_ids = [u["id"] for u in upstream_b1]
        assert "feature_1" in upstream_ids
        assert "feature_2" in upstream_ids

        # Downstream of body_2 (the consumed tool) is feature_2
        downstream_b2 = graph.get_downstream("body_2")
        downstream_ids = [d["id"] for d in downstream_b2]
        assert "feature_2" in downstream_ids

    def test_record_loft_from_profiles(self):
        graph = GeometryDependencyGraph("loft_test")
        # Create profiles
        graph.record_operation(
            op="create_profile",
            spec_node_id="sec1",
            produced=["profile_1", "curve_1", "curve_2", "curve_3", "curve_4"],
        )
        graph.record_operation(
            op="create_profile",
            spec_node_id="sec2",
            produced=["profile_2", "curve_5", "curve_6", "curve_7", "curve_8"],
        )
        # Loft consumes profiles, produces body_1
        graph.record_operation(
            op="loft",
            spec_node_id="loft_mount",
            consumed=["profile_1", "profile_2"],
            produced=["body_1"],
            feature_id="feature_1",
        )

        assert graph.nodes["profile_1"].status == "consumed"
        assert graph.nodes["profile_2"].status == "consumed"
        assert graph.nodes["body_1"].status == "alive"

        # Upstream of body_1 must trace back to profiles
        upstream = graph.get_upstream("body_1")
        upstream_ids = [u["id"] for u in upstream]
        assert "feature_1" in upstream_ids
        assert "profile_1" in upstream_ids
        assert "profile_2" in upstream_ids

    def test_record_pattern_and_instance_bodies(self):
        graph = GeometryDependencyGraph("pattern_test")
        graph.record_operation(
            op="create_cuboid",
            spec_node_id="base",
            produced=["body_1"],
            feature_id="feature_1",
        )
        graph.record_operation(
            op="add_hole",
            spec_node_id="hole",
            consumed=["body_2"],
            modified=["body_1"],
            feature_id="feature_2",
        )
        # Pattern creates 4 instance bodies
        graph.record_operation(
            op="pattern",
            spec_node_id="pat",
            consumed=["feature_2"],  # references source feature
            produced=["body_3", "body_4", "body_5", "body_6"],
            feature_id="feature_3",
        )

        assert graph.nodes["body_3"].status == "alive"
        assert graph.nodes["body_4"].status == "alive"
        assert graph.nodes["body_5"].status == "alive"
        assert graph.nodes["body_6"].status == "alive"

        downstream_feat2 = graph.get_downstream("feature_2")
        downstream_ids = [d["id"] for d in downstream_feat2]
        assert "feature_3" in downstream_ids
        assert "body_3" in downstream_ids


class TestGraphIntegrity:
    def test_valid_graph_passes_integrity(self):
        graph = GeometryDependencyGraph("valid_test")
        graph.record_operation(
            op="create_cuboid",
            produced=["body_1"],
            feature_id="feature_1",
        )
        graph.record_operation(
            op="add_hole",
            consumed=["body_2"],
            modified=["body_1"],
            feature_id="feature_2",
        )
        valid, violations = graph.validate_graph_integrity()
        assert valid is True
        assert len(violations) == 0

    def test_double_consumption_detected(self):
        graph = GeometryDependencyGraph("double_consume")
        graph.record_operation(
            op="create_cuboid",
            produced=["body_2"],
            feature_id="feature_1",
        )
        # First consumption
        graph.record_operation(
            op="boolean_subtract",
            consumed=["body_2"],
            feature_id="feature_2",
        )
        # Illegal second consumption of the same body
        graph.record_operation(
            op="boolean_subtract",
            consumed=["body_2"],
            feature_id="feature_3",
        )

        valid, violations = graph.validate_graph_integrity()
        assert valid is False
        assert len(violations) == 1
        assert "Double consumption detected" in violations[0]
        assert "body_2" in violations[0]


class TestGraphSerialization:
    def test_graph_to_dict_and_from_dict_roundtrip(self):
        graph = GeometryDependencyGraph("roundtrip_part")
        graph.record_operation(
            op="create_cuboid",
            spec_node_id="n1",
            produced=["body_1"],
            feature_id="feature_1",
        )
        graph.record_operation(
            op="add_hole",
            spec_node_id="n2",
            consumed=["body_2"],
            modified=["body_1"],
            feature_id="feature_2",
        )

        data = graph.to_dict()
        assert data["part_name"] == "roundtrip_part"
        assert data["alive_count"] == 3  # body_1, feature_1, feature_2
        assert data["consumed_count"] == 1  # body_2

        restored = GeometryDependencyGraph.from_dict(data)
        assert restored.part_name == "roundtrip_part"
        assert len(restored.nodes) == len(graph.nodes)
        assert restored.nodes["body_2"].status == "consumed"
        assert restored.nodes["body_1"].status == "alive"

        # Verify query on restored graph
        downstream = restored.get_downstream("body_2")
        assert len(downstream) >= 1
        assert downstream[0]["id"] == "feature_2"


class TestSessionGraphSingleton:
    def test_session_graph_reset_and_access(self):
        g1 = reset_session_graph("part_A")
        g1.register_node("body_1")
        assert get_session_graph().part_name == "part_A"
        assert "body_1" in get_session_graph().nodes

        g2 = reset_session_graph("part_B")
        assert get_session_graph().part_name == "part_B"
        assert "body_1" not in get_session_graph().nodes
