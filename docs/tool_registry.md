# Tool Registry

## Overview

The tool registry (`src/nx_mcp/tools/registry.py`) provides centralized registration, introspection, and JSON Schema generation for all **154 MCP tools** in NX-MCP.

---

## Registration Mechanism

### 1. The `@mcp_tool` Decorator

Tools are declared using the `@mcp_tool` decorator, which registers the Python function and its human-readable description into an internal catalog:

```python
from nx_mcp.tools.registry import mcp_tool

@mcp_tool("create_cuboid", "Create a cuboid with length, width, and height in mm")
def create_cuboid(
    length: float = 10.0,
    width: float = 10.0,
    height: float = 10.0,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    centered: bool = False,
):
    """
    :param length: Length along X axis in mm
    :param width: Width along Y axis in mm
    :param height: Height along Z axis in mm
    :param x: X coordinate of corner/center in mm
    :param y: Y coordinate of corner/center in mm
    :param z: Z coordinate of corner/center in mm
    :param centered: If True, center cuboid at (x,y,z); if False, place corner at (x,y,z)
    """
    ...
```

---

## Reflection-Based JSON Schema Generation

`ToolRegistry._get_schema(fn)` inspects the Python function signature, type annotations, and docstrings to generate an MCP-compliant JSON Schema:

1. **Type Mapping**:
   - `float` / `int` → `{"type": "number"}`
   - `bool` → `{"type": "boolean"}`
   - `str` → `{"type": "string"}`
   - `List[...]` → `{"type": "array"}`
   - `Dict[...]` → `{"type": "object"}`
   - `Literal["a", "b", "c"]` → `{"type": "string", "enum": ["a", "b", "c"]}`
2. **Docstring Parameter Extraction**:
   - Parses `:param <name>: <desc>` or Google/Sphinx style parameter docstrings to populate schema property descriptions.
3. **Required vs. Optional Parameters**:
   - Parameters with default values (e.g. `length: float = 10.0`) include `"default": 10.0` and are optional.
   - Parameters without default values are added to the schema's `"required"` list.

---

## `ToolRegistry` API

```python
class ToolRegistry:
    @staticmethod
    def all() -> Dict[str, dict]:
        """Returns the full dictionary of registered tools: {name: {'fn': fn, 'description': desc}}."""

    @staticmethod
    def get(name: str) -> Optional[dict]:
        """Retrieves a single tool definition by name, or None if not found."""

    @staticmethod
    def list_tools() -> List[dict]:
        """
        Generates and returns the complete list of MCP tool descriptors:
        [{'name': '...', 'description': '...', 'inputSchema': {...}}, ...]
        """
```

---

## Auto-Discovery at Server Startup

When `src/nx_mcp/server.py` starts, it imports all tool modules:

```python
from nx_mcp.tools import (
    assembly,
    combine_operations,
    edit_operations,
    file_ops,
    measure,
    modeling,
    sketch,
    surface_modeling,
    utility,
    discovery,
    recipe,
    state_tools,
)
```

Importing each module triggers the `@mcp_tool` decorator evaluations, populating the `ToolRegistry` catalog with all 154 tools.

---

## Step-by-Step Guide: Adding a New Tool

1. **Implement Tool Function in `src/nx_mcp/tools/<module>.py`**:
   ```python
   @mcp_tool("my_new_tool", "Description of what this CAD tool does")
   def my_new_tool(param1: float, mode: Literal["fast", "accurate"] = "fast"):
       """
       :param param1: Numeric parameter in mm
       :param mode: Execution mode
       """
       if _use_mock_nxopen():
           return ToolResult("Mock execution")
       return _bridge_result(runner.call_nx("my_new_tool", {"param1": param1, "mode": mode}))
   ```

2. **Implement the In-NX Handler in `src/nx_mcp/bridge/nx_bridge.py`**:
   - Define `def my_new_tool(param1, mode="fast"):`
   - Acquire work part via `_ensure_work_part()`.
   - Create expressions via `_create_input_expression()`.
   - Execute the NXOpen feature builder and call `_remember_feature()`.
   - Return `{"ok": True, "message": "...", "filepath": str(work_part.FullPath)}`.

3. **Register Category & Keywords in `src/nx_mcp/router.py`**:
   - Add `"my_new_tool"` to the appropriate list in `CATEGORY_TOOLS`.
   - Add relevant keywords to `CATEGORY_KEYWORDS`.

4. **Add Pytest Unit Test in `tests/`**:
   - Verify tool schema, argument validation, and mock execution.

---

## Related Documentation

- [tool_routing.md](tool_routing.md) — Dynamic filtering and category routing.
- [architecture.md](architecture.md) — System architecture overview.
- [cad_spec_system.md](cad_spec_system.md) — Declarative CAD Spec engine.
- [workflow.md](workflow.md) — Request and execution workflow.
