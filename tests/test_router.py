"""Tests for the tool router (Tasks 4-7, 9)."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nx_mcp.router import (
    route,
    get_routed_tool_names,
    get_all_tool_names,
    CATEGORY_TOOLS,
    CATEGORY_KEYWORDS,
    MIN_RAW_WEIGHT,
)


class TestSingleCategory:
    """Test that single-category prompts route to exactly one category."""

    def test_sketch_only(self):
        result = route("Draw a rectangle and a circle")
        cats = [c["name"] for c in result["categories"]]
        assert "Sketch" in cats
        assert not result["is_fallback"]
        # Should NOT include unrelated categories like Assembly
        assert "Assembly" not in cats

    def test_modeling_only(self):
        result = route("Create a cuboid and add a fillet")
        cats = [c["name"] for c in result["categories"]]
        assert "Modeling" in cats
        assert not result["is_fallback"]

    def test_file_operations_only(self):
        result = route("Save the part and export as STEP file")
        cats = [c["name"] for c in result["categories"]]
        assert "File Operations" in cats
        assert not result["is_fallback"]

    def test_measurement_only(self):
        result = route("Measure the distance between two points")
        cats = [c["name"] for c in result["categories"]]
        assert "Measurement" in cats
        assert not result["is_fallback"]

    def test_surface_modeling_only(self):
        result = route("Create a swept surface and thicken it")
        cats = [c["name"] for c in result["categories"]]
        assert "Surface Modeling" in cats
        assert not result["is_fallback"]

    def test_assembly_only(self):
        result = route("Add a component to the assembly and mate it")
        cats = [c["name"] for c in result["categories"]]
        assert "Assembly" in cats
        assert not result["is_fallback"]

    def test_edit_operations_only(self):
        result = route("Heal the surface and smooth the poles")
        cats = [c["name"] for c in result["categories"]]
        assert "Edit Operations" in cats
        assert not result["is_fallback"]

    def test_utility_only(self):
        result = route("Take a screenshot of the viewport")
        cats = [c["name"] for c in result["categories"]]
        assert "Utility" in cats
        assert not result["is_fallback"]


class TestMultiCategory:
    """Test that multi-category prompts route to multiple categories."""

    def test_sketch_plus_modeling(self):
        result = route("Sketch a rectangle, extrude it 30mm, add fillets")
        cats = [c["name"] for c in result["categories"]]
        assert "Sketch" in cats
        assert "Modeling" in cats
        assert not result["is_fallback"]

    def test_modeling_plus_file_ops(self):
        result = route("Create a cylinder then export as STL file")
        cats = [c["name"] for c in result["categories"]]
        assert "Modeling" in cats
        assert "File Operations" in cats
        assert not result["is_fallback"]

    def test_three_categories(self):
        result = route("Draw a circle, extrude it, then measure the volume")
        cats = [c["name"] for c in result["categories"]]
        assert "Sketch" in cats
        assert "Modeling" in cats
        assert "Measurement" in cats
        assert not result["is_fallback"]


class TestFallback:
    """Test that unmatched/unknown prompts trigger fallback to all tools."""

    def test_completely_unrelated(self):
        result = route("What is the weather in Tokyo?")
        assert result["is_fallback"] is True
        assert result["total_tools"] == len(get_all_tool_names())

    def test_empty_string(self):
        result = route("")
        assert result["is_fallback"] is True

    def test_gibberish(self):
        result = route("asdfghjkl qwertyuiop zxcvbnm")
        assert result["is_fallback"] is True


class TestConfidenceScoring:
    """Test that confidence scores are computed correctly."""

    def test_scores_are_between_0_and_1(self):
        result = route("Create a cuboid and extrude it")
        for cat in result["categories"]:
            assert 0.0 <= cat["score"] <= 1.0

    def test_more_keywords_higher_score(self):
        # "extrude" matches Modeling with 1 keyword
        r1 = route("extrude")
        # "extrude cuboid fillet chamfer hole" matches Modeling with 5 keywords
        r2 = route("extrude cuboid fillet chamfer hole")
        s1 = next((c["score"] for c in r1["categories"] if c["name"] == "Modeling"), 0)
        s2 = next((c["score"] for c in r2["categories"] if c["name"] == "Modeling"), 0)
        assert s2 > s1

    def test_matched_category_has_correct_tools(self):
        result = route("Create a new part file")
        for cat in result["categories"]:
            if cat["name"] == "File Operations":
                # All tools should be from File Operations
                for tool in cat["tools"]:
                    assert tool in CATEGORY_TOOLS["File Operations"]


class TestRouterEdgeCases:
    """Test edge cases and invariants."""

    def test_all_categories_have_tools(self):
        for cat, tools in CATEGORY_TOOLS.items():
            assert len(tools) > 0, f"Category '{cat}' has no tools"

    def test_all_categories_have_keywords(self):
        for cat in CATEGORY_TOOLS:
            assert cat in CATEGORY_KEYWORDS, f"Category '{cat}' has no keywords"
            assert len(CATEGORY_KEYWORDS[cat]) > 0

    def test_no_tool_in_multiple_categories(self):
        seen = {}
        for cat, tools in CATEGORY_TOOLS.items():
            for tool in tools:
                assert tool not in seen, (
                    f"Tool '{tool}' in both '{seen[tool]}' and '{cat}'"
                )
                seen[tool] = cat

    def test_total_tools_matches_registry(self):
        total = sum(len(tools) for tools in CATEGORY_TOOLS.values())
        assert total >= 126, f"Expected at least 126 tools, got {total}"

    def test_routing_latency_under_10ms(self):
        result = route("Create a cuboid and add fillets")
        assert result["routing_time_ms"] < 10.0

    def test_get_routed_tool_names_returns_list(self):
        names = get_routed_tool_names("Draw a circle")
        assert isinstance(names, list)
        assert len(names) > 0
        assert "draw_circle" in names

    def test_curve_profile_requests_include_reusable_curve_tools(self):
        names = get_routed_tool_names("Create a variable-width impeller blade spline profile")
        assert {"draw_spline", "offset_curve", "close_curve_region"}.issubset(names)

    def test_get_all_tool_names_returns_126(self):
        assert len(get_all_tool_names()) >= 126


class TestServerRouting:
    """Test router integration in server.py."""

    def test_server_list_tools_routing_disabled(self, monkeypatch):
        monkeypatch.setenv("NX_MCP_ENABLE_ROUTING", "0")
        from nx_mcp.server import handle
        from nx_mcp.tools.registry import ToolRegistry
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {"prompt": "Draw a rectangle"}
        }
        res = handle(req)
        assert len(res["result"]["tools"]) == len(ToolRegistry.list_tools())

    def test_server_list_tools_routing_enabled(self, monkeypatch):
        monkeypatch.setenv("NX_MCP_ENABLE_ROUTING", "1")
        from nx_mcp.server import handle
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {"prompt": "Draw a rectangle"}
        }
        res = handle(req)
        # Sketch tools plus the discovery tool.
        assert len(res["result"]["tools"]) == len(CATEGORY_TOOLS["Sketch"]) + 1
        tool_names = {t["name"] for t in res["result"]["tools"]}
        assert "draw_rectangle" in tool_names
        assert "create_cuboid" not in tool_names

    def test_server_list_tools_routing_fallback(self, monkeypatch):
        monkeypatch.setenv("NX_MCP_ENABLE_ROUTING", "1")
        from nx_mcp.server import handle, _session_state
        from nx_mcp.tools.registry import ToolRegistry
        handle({"jsonrpc": "2.0", "id": 0, "method": "initialize"})
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {"prompt": "What is the meaning of life?"}
        }
        res = handle(req)
        assert len(res["result"]["tools"]) == len(ToolRegistry.list_tools())

    def test_server_escape_hatch_triggers_on_unrouted_tool_call(self, monkeypatch):
        monkeypatch.setenv("NX_MCP_ENABLE_ROUTING", "1")
        from nx_mcp.server import handle
        from nx_mcp.tools.registry import ToolRegistry

        # Initialize session
        handle({"jsonrpc": "2.0", "id": 0, "method": "initialize"})

        # Call tools/list with sketch prompt -> returns filtered sketch tools (create_cuboid excluded)
        res1 = handle({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {"prompt": "Draw a rectangle"}
        })
        tool_names1 = {t["name"] for t in res1["result"]["tools"]}
        assert "create_cuboid" not in tool_names1

        # Call unrouted tool "create_cuboid" -> allowed & triggers escape hatch
        call_res = handle({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "create_cuboid", "arguments": {"length": 10, "width": 10, "height": 10}}
        })
        assert "result" in call_res

        # Next tools/list call returns full tool catalog
        res2 = handle({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/list",
            "params": {}
        })
        assert len(res2["result"]["tools"]) == len(ToolRegistry.list_tools())

