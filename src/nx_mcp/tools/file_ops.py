import os

from ..bridge import runner
from ..tools.registry import mcp_tool
from ..nx_session import NXSession
from ..response import ToolResult, ToolError


def _use_mock_nxopen():
    return os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1"


def _bridge_result(result):
    if result.get("ok"):
        msg = result.get("message", "OK")
        filepath = result.get("filepath")
        if filepath:
            cmd_path = r"C:\Users\HP\nx-mcp\open_current_nx_result.cmd"
            msg += f"\n\nTo manually open in NX, run:\n{cmd_path}"
        return ToolResult(msg)
    return ToolError(result.get("error", "NX bridge command failed"))

@mcp_tool("create_part", "Create a new empty NX part file")
def create_part(filename: str):
    try:
        if _use_mock_nxopen():
            nxopen = NXSession.nxopen()
            NXSession.get().Parts.NewDisplay(filename, nxopen.Part.Units.Millimeters)
            runner._update_watcher_files(filename)
            cmd_path = r"C:\Users\HP\nx-mcp\open_current_nx_result.cmd"
            return ToolResult(f"Created part: {filename}\n\nTo manually open in NX, run:\n{cmd_path}")
        return _bridge_result(runner.call_nx("create_part", {"filename": filename}))
    except Exception as e: return ToolError(str(e))

@mcp_tool("open_part", "Open an existing NX part file by full path")
def open_part(filepath: str):
    try:
        if _use_mock_nxopen():
            NXSession.get().Parts.Open(filepath)
            runner._update_watcher_files(filepath)
            cmd_path = r"C:\Users\HP\nx-mcp\open_current_nx_result.cmd"
            return ToolResult(f"Opened: {filepath}\n\nTo manually open in NX, run:\n{cmd_path}")
        return _bridge_result(runner.call_nx("open_part", {"filepath": filepath}))
    except Exception as e: return ToolError(str(e))

@mcp_tool("save_part", "Save the current work part")
def save_part():
    try:
        if _use_mock_nxopen():
            part = NXSession.work_part()
            part.Save()
            filepath = getattr(part, "FullPath", "")
            if filepath:
                runner._update_watcher_files(filepath)
                cmd_path = r"C:\Users\HP\nx-mcp\open_current_nx_result.cmd"
                return ToolResult(f"Part saved\n\nTo manually open in NX, run:\n{cmd_path}")
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
