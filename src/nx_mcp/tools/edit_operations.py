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


@mcp_tool("reverse_normal", "Reverse the surface normal direction of sheet body faces")
def reverse_normal(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("reverse_normal", {"body": body}))
        return ToolResult("Reversed sheet normal direction")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("local_untrim_extend", "Locally untrim and extend a sheet edge boundary")
def local_untrim_extend(
    boundary_edge_x: float = 0.0, boundary_edge_y: float = 0.0, boundary_edge_z: float = 0.0,
    distance: float = 10.0, body: str = "last"
):
    try:
        if distance <= 0:
            return ToolError("Extension distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("local_untrim_extend", {
                "boundary_edge_x": boundary_edge_x, "boundary_edge_y": boundary_edge_y, "boundary_edge_z": boundary_edge_z,
                "distance": distance, "body": body
            }))
        return ToolResult(f"Untrimmed and extended face by {distance}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("replace_edge", "Replace a face boundary edge using projecting curve geometries")
def replace_edge(target_edge_x: float = 0.0, target_edge_y: float = 0.0, target_edge_z: float = 0.0, tool_sketch: str = "last", body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("replace_edge", {
                "target_edge_x": target_edge_x, "target_edge_y": target_edge_y, "target_edge_z": target_edge_z,
                "tool_sketch": tool_sketch, "body": body
            }))
        return ToolResult("Replaced edge completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("x_form", "Modify freeform sheet faces using X-Form pole grid translation")
def x_form(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("x_form", {"body": body}))
        return ToolResult("X-Form deformation applied")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("i_form", "Modify freeform sheet faces using I-Form shape matching")
def i_form(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("i_form", {"body": body}))
        return ToolResult("I-Form deformation applied")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("match_edge", "Deform a sheet face boundary edge to match target edge curvature continuity")
def match_edge(
    target_edge_x: float = 0.0, target_edge_y: float = 0.0, target_edge_z: float = 0.0,
    tool_edge_x: float = 0.0, tool_edge_y: float = 0.0, tool_edge_z: float = 0.0,
    body: str = "last"
):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("match_edge", {
                "target_edge_x": target_edge_x, "target_edge_y": target_edge_y, "target_edge_z": target_edge_z,
                "tool_edge_x": tool_edge_x, "tool_edge_y": tool_edge_y, "tool_edge_z": tool_edge_z,
                "body": body
            }))
        return ToolResult("Match edge feature created")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("edge_symmetry", "Apply symmetric boundary constraints to face edges")
def edge_symmetry(target_edge_x: float = 0.0, target_edge_y: float = 0.0, target_edge_z: float = 0.0, body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("edge_symmetry", {
                "target_edge_x": target_edge_x, "target_edge_y": target_edge_y, "target_edge_z": target_edge_z, "body": body
            }))
        return ToolResult("Edge symmetry applied")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("global_shaping", "Apply global shaping deform maps across sheet faces")
def global_shaping(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("global_shaping", {"body": body}))
        return ToolResult("Global shaping applied to sheet")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("global_deformation", "Deform a sheet body using displacement points/regions")
def global_deformation(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("global_deformation", {"body": body}))
        return ToolResult("Global deformation applied")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("flattening_forming", "Flatten highly curved sheets or form curves back onto sheets")
def flattening_forming(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("flattening_forming", {"body": body}))
        return ToolResult("Flattening and forming completed")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("heal_surface", "Heal topological errors and gaps inside open sheet geometries")
def heal_surface(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("heal_surface", {"body": body}))
        return ToolResult("Surface healed successfully")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("edit_uv_direction", "Edit or transpose surface coordinate UV directions on faces")
def edit_uv_direction(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("edit_uv_direction", {"body": body}))
        return ToolResult("Edited face UV direction")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("enlarge_face", "Enlarge a sheet face boundary proportionally by scale distance")
def enlarge_face(body: str = "last", distance: float = 5.0, face_x: float = 0.0, face_y: float = 0.0, face_z: float = 0.0):
    try:
        if distance <= 0:
            return ToolError("Enlarge distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("enlarge_face", {
                "body": body, "distance": distance, "face_x": face_x, "face_y": face_y, "face_z": face_z
            }))
        return ToolResult(f"Enlarged face by {distance}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("snip_into_patches", "Snip sheet faces into rectangular patch subdivisions")
def snip_into_patches(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("snip_into_patches", {"body": body}))
        return ToolResult("Snipped surface into patches")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("smooth_poles", "Smooth control points of freeform sheet boundaries")
def smooth_poles(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("smooth_poles", {"body": body}))
        return ToolResult("Smoothed poles of freeform face")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("refit_face", "Refit sheet face boundary geometries to match exact constraints")
def refit_face(body: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("refit_face", {"body": body}))
        return ToolResult("Refitted face geometry")
    except Exception as e:
        return ToolError(str(e))
