import os
from ..bridge import runner
from ..tools.registry import mcp_tool
from ..response import ToolResult, ToolError


def _use_mock_nxopen():
    return os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1"


def _bridge_result(result):
    if result.get("ok"):
        return ToolResult(result.get("message", "OK"))
    return ToolError(result.get("error", "NX bridge command failed"))


@mcp_tool("boolean_combine", "Perform combine operations (Unite, Subtract, Intersect)")
def boolean_combine(operation: str = "intersect", target: str = "last", tool: str = "last"):
    try:
        if operation.lower() not in {"unite", "subtract", "intersect"}:
            return ToolError(f"Unsupported combine operation: {operation}")
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("boolean_combine", {"operation": operation, "target": target, "tool": tool}))
        return ToolResult(f"Boolean {operation} completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("trim_sheet", "Trim a sheet body using a boundary curve or sheet")
def trim_sheet(target_body: str = "last", boundary_sketch: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("trim_sheet", {"target_body": target_body, "boundary_sketch": boundary_sketch}))
        return ToolResult("Trimmed sheet body")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("extend_sheet", "Extend a sheet boundary edge by a distance")
def extend_sheet(
    distance: float = 10.0,
    boundary_edge_x: float = 0.0, boundary_edge_y: float = 0.0, boundary_edge_z: float = 0.0,
    body: str = "last"
):
    try:
        if distance <= 0:
            return ToolError("Extend distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("extend_sheet", {
                "distance": distance, "boundary_edge_x": boundary_edge_x, "boundary_edge_y": boundary_edge_y, "boundary_edge_z": boundary_edge_z,
                "body": body
            }))
        return ToolResult(f"Extended sheet edge by {distance}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("trim_and_extend", "Trim and extend two intersecting sheet bodies")
def trim_and_extend(target_body: str = "last", tool_body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("trim_and_extend", {"target_body": target_body, "tool_body": tool_body}))
        return ToolResult("Trim and extend operation completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("sew_sheets", "Sew multiple sheet bodies together along edges")
def sew_sheets(target_sheet: str = "last", tool_sheets: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("sew_sheets", {"target_sheet": target_sheet, "tool_sheets": tool_sheets}))
        return ToolResult("Sheets sewn successfully")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("split_body", "Split a solid or sheet body using a plane or face")
def split_body(target_body: str = "last", tool_face_x: float = 0.0, tool_face_y: float = 0.0, tool_face_z: float = 0.0):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("split_body", {
                "target_body": target_body, "tool_face_x": tool_face_x, "tool_face_y": tool_face_y, "tool_face_z": tool_face_z
            }))
        return ToolResult("Body split successfully")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("divide_face", "Divide a face using projecting curves or edges")
def divide_face(target_face_x: float = 0.0, target_face_y: float = 0.0, target_face_z: float = 0.0, boundary_sketch: str = "last", body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("divide_face", {
                "target_face_x": target_face_x, "target_face_y": target_face_y, "target_face_z": target_face_z,
                "boundary_sketch": boundary_sketch, "body": body
            }))
        return ToolResult("Divide face completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("snip_surface", "Snip or split a surface face at specified UV coordinates or points")
def snip_surface(target_face_x: float = 0.0, target_face_y: float = 0.0, target_face_z: float = 0.0, body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("snip_surface", {
                "target_face_x": target_face_x, "target_face_y": target_face_y, "target_face_z": target_face_z, "body": body
            }))
        return ToolResult("Snip surface completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("untrim_sheet", "Remove trim boundaries from sheet body faces")
def untrim_sheet(target_edge_x: float = 0.0, target_edge_y: float = 0.0, target_edge_z: float = 0.0, body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("untrim_sheet", {
                "target_edge_x": target_edge_x, "target_edge_y": target_edge_y, "target_edge_z": target_edge_z, "body": body
            }))
        return ToolResult("Untrimmed sheet successfully")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("delete_edge", "Delete an edge of a sheet face to combine faces")
def delete_edge(target_edge_x: float = 0.0, target_edge_y: float = 0.0, target_edge_z: float = 0.0, body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("delete_edge", {
                "target_edge_x": target_edge_x, "target_edge_y": target_edge_y, "target_edge_z": target_edge_z, "body": body
            }))
        return ToolResult("Delete edge completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("emboss_body", "Emboss sheet profiles into solid/sheet body")
def emboss_body(target_body: str = "last", boundary_sketch: str = "last", depth: float = 5.0):
    try:
        if depth <= 0:
            return ToolError("Emboss depth must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("emboss_body", {"target_body": target_body, "boundary_sketch": boundary_sketch, "depth": depth}))
        return ToolResult(f"Emboss body completed by {depth}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("patch_body", "Patch a sheet body into a solid target body")
def patch_body(target_body: str = "last", tool_sheet: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("patch_body", {"target_body": target_body, "tool_sheet": tool_sheet}))
        return ToolResult("Body patched successfully")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("unsew_sheets", "Unsew or disconnect sheet boundaries along edges")
def unsew_sheets(target_body: str = "last", split_edge_x: float = 0.0, split_edge_y: float = 0.0, split_edge_z: float = 0.0):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("unsew_sheets", {
                "target_body": target_body, "split_edge_x": split_edge_x, "split_edge_y": split_edge_y, "split_edge_z": split_edge_z
            }))
        return ToolResult("Unsewed sheet body")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("make_solid", "Convert closed sewn sheet body to solid body")
def make_solid(target_sheet: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("make_solid", {"target_sheet": target_sheet}))
        return ToolResult("Sewn sheet body successfully converted to Solid body")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("sheet_boundary_analysis", "Analyze sheet body perimeter to find open edges")
def sheet_boundary_analysis(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("sheet_boundary_analysis", {"body": body}))
        return ToolResult("Sheet boundary analysis: 0 open edges found")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("quilt_sheets", "Quilt sheet boundaries together")
def quilt_sheets(target_sheet: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("quilt_sheets", {"target_sheet": target_sheet}))
        return ToolResult("Sheets quilted successfully")
    except Exception as e:
        return ToolError(str(e))
