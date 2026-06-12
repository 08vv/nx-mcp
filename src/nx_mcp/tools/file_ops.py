import NXOpen
from ..tools.registry import mcp_tool
from ..nx_session import NXSession
from ..response import ToolResult, ToolError

@mcp_tool("create_part", "Create a new empty NX part file")
def create_part(filename: str):
    try:
        NXSession.get().Parts.NewDisplay(filename, NXOpen.Part.Units.Millimeters)
        return ToolResult(f"Created part: {filename}")
    except Exception as e: return ToolError(str(e))

@mcp_tool("open_part", "Open an existing NX part file by full path")
def open_part(filepath: str):
    try:
        NXSession.get().Parts.Open(filepath)
        return ToolResult(f"Opened: {filepath}")
    except Exception as e: return ToolError(str(e))

@mcp_tool("save_part", "Save the current work part")
def save_part():
    try:
        NXSession.work_part().Save()
        return ToolResult("Part saved")
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