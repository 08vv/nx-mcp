import inspect

_registry = {}

def mcp_tool(name: str, description: str):
    def decorator(fn):
        _registry[name] = {"fn": fn, "description": description}
        return fn
    return decorator

def _get_schema(fn):
    props = {}
    required = []
    for param_name, param in inspect.signature(fn).parameters.items():
        ann = param.annotation
        if ann == float or ann == int:
            t = "number"
        elif ann == bool:
            t = "boolean"
        else:
            t = "string"
        props[param_name] = {"type": t}
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
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
