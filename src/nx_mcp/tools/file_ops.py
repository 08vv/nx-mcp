import os

from ..bridge import runner
from ..tools.registry import mcp_tool
from ..nx_session import NXSession
from ..response import ToolResult, ToolError


def _use_mock_nxopen():
    return os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1"


def _bridge_result(result):
    if result.get("ok"):
        return ToolResult(result.get("message", "OK"))
    return ToolError(result.get("error", "NX bridge command failed"))

@mcp_tool("create_part", "Create a new empty NX part file")
def create_part(filename: str):
    try:
        if _use_mock_nxopen():
            nxopen = NXSession.nxopen()
            NXSession.get().Parts.NewDisplay(filename, nxopen.Part.Units.Millimeters)
            return ToolResult(f"Created part: {filename}")
        return _bridge_result(runner.call_nx("create_part", {"filename": filename}))
    except Exception as e: return ToolError(str(e))

@mcp_tool("open_part", "Open an existing NX part file by full path")
def open_part(filepath: str):
    try:
        if _use_mock_nxopen():
            NXSession.get().Parts.Open(filepath)
            return ToolResult(f"Opened: {filepath}")
        return _bridge_result(runner.call_nx("open_part", {"filepath": filepath}))
    except Exception as e: return ToolError(str(e))

@mcp_tool("save_part", "Save the current work part")
def save_part():
    try:
        if _use_mock_nxopen():
            NXSession.work_part().Save()
            return ToolResult("Part saved")
        return _bridge_result(runner.call_nx("save_part", {}))
    except Exception as e: return ToolError(str(e))

@mcp_tool("export_step", "Export current part as STEP file")
def export_step(output_path: str):
    try:
        exp = NXSession.get().DexManager.CreateStepCreator()
        exp.ObjectTypes.Solids = True
        exp.OutputFile = output_path
        exp.Commit(); exp.Destroy()
        return ToolResult(f"Exported STEP: {output_path}")
    except Exception as e: return ToolError(str(e))

@mcp_tool("export_stl", "Export current part as STL file")
def export_stl(output_path: str):
    try:
        exp = NXSession.get().DexManager.CreateStlCreator()
        exp.OutputFile = output_path
        exp.Commit(); exp.Destroy()
        return ToolResult(f"Exported STL: {output_path}")
    except Exception as e: return ToolError(str(e))
