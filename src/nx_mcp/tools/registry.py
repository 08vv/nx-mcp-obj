import inspect
import typing

_registry = {}

def mcp_tool(name: str, description: str):
    def decorator(fn):
        _registry[name] = {"fn": fn, "description": description}
        return fn
    return decorator

def _parse_param_descriptions(fn):
    """Extract parameter descriptions from docstring :param lines."""
    doc = inspect.getdoc(fn) or ""
    result = {}
    for line in doc.splitlines():
        line = line.strip()
        if line.startswith(":param "):
            rest = line[len(":param "):]
            colon_idx = rest.find(":")
            if colon_idx > 0:
                pname = rest[:colon_idx].strip()
                pdesc = rest[colon_idx + 1:].strip()
                result[pname] = pdesc
    return result

def _get_schema(fn):
    props = {}
    required = []
    param_descs = _parse_param_descriptions(fn)
    for param_name, param in inspect.signature(fn).parameters.items():
        ann = param.annotation
        prop = {}

        # Check for Literal types (enums)
        origin = getattr(ann, "__origin__", None)
        if origin is typing.Literal:
            args = typing.get_args(ann)
            prop["type"] = "string"
            prop["enum"] = list(args)
        elif ann == float or ann == int:
            prop["type"] = "number"
        elif ann == bool:
            prop["type"] = "boolean"
        else:
            prop["type"] = "string"

        # Add description from docstring
        if param_name in param_descs:
            prop["description"] = param_descs[param_name]

        # Add default value
        if param.default is not inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(param_name)

        props[param_name] = prop
    return {"type": "object", "properties": props, "required": required}

class ToolRegistry:
    @staticmethod
    def all(): return _registry
    @staticmethod
    def get(name): return _registry.get(name)
    @staticmethod
    def list_tools():
        return [{"name": k, "description": v["description"],
                 "inputSchema": _get_schema(v["fn"])}
                for k, v in _registry.items()]
