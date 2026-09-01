import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nx_mcp.tools import recipe, file_ops, modeling, utility
from nx_mcp.response import ToolResult, ToolError

def test_run_recipe_basic():
    steps = [
        {"tool": "create_cube", "args": {"size": 10.0}},
        {"tool": "list_expressions", "args": {}}
    ]
    res = recipe.run_recipe(steps)
    assert res["ok"] is True
    assert len(res["completed"]) == 2

def test_run_recipe_recursion_prevention():
    steps = [
        {"tool": "run_recipe", "args": {"steps": []}}
    ]
    res = recipe.run_recipe(steps)
    assert res["ok"] is False
    assert "not allowed" in res["error"]

def test_run_recipe_unknown_tool():
    steps = [
        {"tool": "non_existent_tool", "args": {}}
    ]
    res = recipe.run_recipe(steps)
    assert res["ok"] is False
    assert "Unknown tool" in res["error"]
