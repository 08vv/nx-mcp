import json, sys, logging

from nx_mcp.tools import file_ops, sketch, modeling, assembly, measure, utility  # noqa
from nx_mcp.tools.registry import ToolRegistry

logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                    format="[nx-mcp] %(levelname)s %(message)s")
log = logging.getLogger("nx-mcp")

def ok(id_, result):  return {"jsonrpc":"2.0","id":id_,"result":result}
def err(id_, c, msg): return {"jsonrpc":"2.0","id":id_,"error":{"code":c,"message":msg}}

def handle(req):
    id_    = req.get("id")
    method = req.get("method","")
    params = req.get("params",{})
    log.debug(f"→ {method}")

    if method == "initialize":
        return ok(id_, {"protocolVersion":"2024-11-05",
                        "capabilities":{"tools":{}},
                        "serverInfo":{"name":"nx-mcp","version":"0.1.0"}})

    if method == "notifications/initialized": return None

    if method == "tools/list":
        return ok(id_, {"tools": ToolRegistry.list_tools()})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        tool = ToolRegistry.get(name)
        if not tool: return err(id_, -32601, f"Unknown tool: {name}")
        try:
            result = tool["fn"](**args)
            return ok(id_, {"content":[{"type":"text","text":str(result)}]})
        except TypeError as e:
            return err(id_, -32602, f"Bad args for '{name}': {e}")
        except Exception as e:
            return err(id_, -32603, f"Error in '{name}': {e}")

    return err(id_, -32601, f"Unknown method: {method}")

def main():
    log.info(f"NX MCP started — {len(ToolRegistry.all())} tools")
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            resp = handle(json.loads(line))
            if resp:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as e:
            sys.stdout.write(json.dumps(err(None,-32700,str(e)))+"\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()