import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nx_mcp.tools import (
    assembly, combine_operations, edit_operations, file_ops, measure,
    modeling, recipe, sketch, surface_modeling, utility, discovery
)
from nx_mcp.tools.registry import ToolRegistry


def test_discovery_tool_registered():
    tools = {t["name"] for t in ToolRegistry.list_tools()}
    assert "get_relevant_nx_tools" in tools


def test_discovery_tool_filters_correctly():
    # Calling the tool should return a JSON string
    result_json = discovery.get_relevant_nx_tools("Sketch a rectangle")
    assert isinstance(result_json, str)
    
    result = json.loads(result_json)
    
    # Should not be fallback
    assert result["is_fallback"] is False
    assert "Sketch" in result["matched_categories"]
    
    # Total tools returned should be less than all tools
    all_tools_count = len(ToolRegistry.list_tools()) - 1  # excluding self
    assert 0 < result["total_returned"] < all_tools_count
    
    # Ensure "draw_rectangle" is in the returned list
    returned_names = {t["name"] for t in result["tools"]}
    assert "draw_rectangle" in returned_names
    
    # Ensure unrelated tool is not in the list
    assert "create_cuboid" not in returned_names
    
    # Ensure the discovery tool itself is excluded
    assert "get_relevant_nx_tools" not in returned_names


def test_discovery_tool_fallback():
    # Calling the tool with gibberish
    result_json = discovery.get_relevant_nx_tools("What is the meaning of life?")
    result = json.loads(result_json)
    
    # Should trigger fallback
    assert result["is_fallback"] is True
    
    # Total tools returned should be exactly all tools minus self
    all_tools_count = len(ToolRegistry.list_tools()) - 1
    assert result["total_returned"] == all_tools_count
    
    # Ensure a random tool is present
    returned_names = {t["name"] for t in result["tools"]}
    assert "create_cuboid" in returned_names
    assert "draw_rectangle" in returned_names
    
    # Ensure the discovery tool itself is excluded
    assert "get_relevant_nx_tools" not in returned_names


def test_tools_list_remains_unchanged(monkeypatch):
    """Ensure that the default tools/list behavior is completely unchanged."""
    monkeypatch.setenv("NX_MCP_ENABLE_ROUTING", "0")
    from nx_mcp.server import handle
    
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }
    res = handle(req)
    
    tools = res["result"]["tools"]
    from nx_mcp.tools.registry import ToolRegistry
    assert len(tools) == len(ToolRegistry.list_tools())
    names = {t["name"] for t in tools}
    assert "get_relevant_nx_tools" in names
    assert "create_cuboid" in names
