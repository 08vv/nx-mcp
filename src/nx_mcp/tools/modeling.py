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

@mcp_tool("extrude", "Extrude active sketch by distance mm")
def extrude(distance: float, start: float = 0.0):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("extrude", {"distance": distance, "start": start})
            )
        b = NXSession.work_part().Features.CreateExtrudeBuilder(None)
        b.Limits.StartExtend.Value.RightHandSide = str(start)
        b.Limits.EndExtend.Value.RightHandSide   = str(distance)
        b.CommitFeature(); b.Destroy()
        return ToolResult(f"Extruded {distance}mm")
    except Exception as e: return ToolError(str(e))

@mcp_tool("revolve", "Revolve active sketch around axis by angle_deg")
def revolve(axis: str = "Z", angle_deg: float = 360.0):
    try:
        b = NXSession.work_part().Features.CreateRevolveBuilder(None)
        b.Limits.EndExtend.Value.RightHandSide = str(angle_deg)
        b.CommitFeature(); b.Destroy()
        return ToolResult(f"Revolved {angle_deg}° around {axis}")
    except Exception as e: return ToolError(str(e))

@mcp_tool("boolean_unite", "Unite two solid bodies")
def boolean_unite(target: str, tool: str):
    try:
        nxopen = NXSession.nxopen()
        b = NXSession.work_part().Features.CreateBooleanBuilder(None)
        b.Operation = nxopen.Features.BooleanBuilder.BooleanType.Unite
        b.CommitFeature(); b.Destroy()
        return ToolResult(f"United '{target}' + '{tool}'")
    except Exception as e: return ToolError(str(e))

@mcp_tool("boolean_subtract", "Subtract tool body from target body")
def boolean_subtract(target: str, tool: str):
    try:
        nxopen = NXSession.nxopen()
        b = NXSession.work_part().Features.CreateBooleanBuilder(None)
        b.Operation = nxopen.Features.BooleanBuilder.BooleanType.Subtract
        b.CommitFeature(); b.Destroy()
        return ToolResult(f"Subtracted '{tool}' from '{target}'")
    except Exception as e: return ToolError(str(e))

@mcp_tool("add_fillet", "Add edge fillet with radius mm")
def add_fillet(radius: float):
    try:
        b = NXSession.work_part().Features.CreateEdgeBlendBuilder(None)
        b.Tolerance = 0.01
        b.CommitFeature(); b.Destroy()
        return ToolResult(f"Fillet R{radius}mm")
    except Exception as e: return ToolError(str(e))

@mcp_tool("add_chamfer", "Add chamfer with offset mm")
def add_chamfer(offset: float):
    try:
        b = NXSession.work_part().Features.CreateChamferBuilder(None)
        b.FirstOffset = str(offset)
        b.CommitFeature(); b.Destroy()
        return ToolResult(f"Chamfer {offset}mm")
    except Exception as e: return ToolError(str(e))

@mcp_tool("add_hole", "Add hole at (x,y,z) with diameter and depth in mm")
def add_hole(x: float, y: float, z: float, diameter: float, depth: float):
    try:
        b = NXSession.work_part().Features.CreateHoleBuilder(None)
        b.Diameter.RightHandSide = str(diameter)
        b.Depth.RightHandSide    = str(depth)
        b.CommitFeature(); b.Destroy()
        return ToolResult(f"Hole D={diameter} depth={depth} at ({x},{y},{z})")
    except Exception as e: return ToolError(str(e))

@mcp_tool("mirror_feature", "Mirror a feature about a plane (XY/XZ/YZ)")
def mirror_feature(feature_name: str, plane: str = "XZ"):
    try:
        b = NXSession.work_part().Features.CreateMirrorFeatureBuilder(None)
        b.MirrorPlane = plane
        b.CommitFeature(); b.Destroy()
        return ToolResult(f"Mirrored '{feature_name}' about {plane}")
    except Exception as e: return ToolError(str(e))

@mcp_tool("pattern_feature", "Linear pattern: count items spaced pitch mm along direction")
def pattern_feature(feature_name: str, direction: str = "X", count: int = 3, pitch: float = 10.0):
    try:
        b = NXSession.work_part().Features.CreateLinearPatternBuilder(None)
        b.PatternService.PatternCount.RightHandSide = str(count)
        b.PatternService.Pitch.RightHandSide        = str(pitch)
        b.CommitFeature(); b.Destroy()
        return ToolResult(f"Pattern '{feature_name}' {count}x @ {pitch}mm along {direction}")
    except Exception as e: return ToolError(str(e))
