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
    current_param = None
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.startswith(":param "):
            rest = stripped[len(":param "):]
            colon_idx = rest.find(":")
            if colon_idx > 0:
                current_param = rest[:colon_idx].strip()
                pdesc = rest[colon_idx + 1:].strip()
                result[current_param] = pdesc
        elif current_param and stripped and not stripped.startswith(":"):
            # Continuation line for the current param
            result[current_param] += " " + stripped
        else:
            current_param = None
    return result



def _get_schema(fn):
    props = {}
    required = []
    param_descs = _parse_param_descriptions(fn)
    for param_name, param in inspect.signature(fn).parameters.items():
        ann = param.annotation
        prop = {}

        origin = typing.get_origin(ann)
        # Check for Literal types (enums)
        if origin is typing.Literal:
            args = typing.get_args(ann)
            prop["type"] = "string"
            prop["enum"] = list(args)
        elif origin is list or ann == list:
            prop["type"] = "array"
            item_args = typing.get_args(ann)
            if item_args:
                item_origin = typing.get_origin(item_args[0])
                if item_origin is dict or item_args[0] is dict:
                    prop["items"] = {"type": "object"}
                elif item_args[0] == str:
                    prop["items"] = {"type": "string"}
                elif item_args[0] in (int, float):
                    prop["items"] = {"type": "number"}
                else:
                    prop["items"] = {"type": "object"}
            else:
                prop["items"] = {"type": "object"}
        elif origin is typing.Union or (isinstance(origin, type) and origin.__name__ == "UnionType") or str(type(ann)) == "<class 'types.UnionType'>":
            union_args = typing.get_args(ann)
            if all(typing.get_origin(a) is list or a is list for a in union_args):
                prop["type"] = "array"
                prop["items"] = {"type": "object"}
            elif all(a in (int, float) for a in union_args):
                prop["type"] = "number"
            else:
                prop["type"] = "string"
        elif origin is dict or ann is dict:
            prop["type"] = "object"
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
    def all():
        return _registry

    @staticmethod
    def get(name):
        return _registry.get(name)

    @staticmethod
    def list_tools():
        return [
            {
                "name": k,
                "description": v["description"],
                "inputSchema": _get_schema(v["fn"]),
            }
            for k, v in _registry.items()
        ]
