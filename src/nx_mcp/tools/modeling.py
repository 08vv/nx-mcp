import os

from ..bridge import runner
from ..nx_session import NXSession
from ..response import ToolError, ToolResult
from ..tools.registry import mcp_tool


def _use_mock_nxopen():
    return os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1"


def _bridge_result(result):
    if result.get("ok"):
        return ToolResult(result.get("message", "OK"))
    return ToolError(result.get("error", "NX bridge command failed"))


@mcp_tool("create_cube", "Create a cube with side length mm from origin x y z")
def create_cube(size: float = 10.0, x: float = 0.0, y: float = 0.0, z: float = 0.0):
    try:
        if size <= 0:
            return ToolError("Cube size must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("create_cube", {"size": size, "x": x, "y": y, "z": z})
            )
        b = NXSession.work_part().Features.CreateExtrudeBuilder(None)
        b.Limits.StartExtend.Value.RightHandSide = str(z)
        b.Limits.EndExtend.Value.RightHandSide = str(z + size)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Cube {size}mm at ({x},{y},{z})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("create_cuboid", "Create a cuboid with length width height mm from origin x y z")
def create_cuboid(
    length: float = 40.0,
    width: float = 25.0,
    height: float = 20.0,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
):
    try:
        if length <= 0 or width <= 0 or height <= 0:
            return ToolError("Cuboid dimensions must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_cuboid",
                    {
                        "length": length,
                        "width": width,
                        "height": height,
                        "x": x,
                        "y": y,
                        "z": z,
                    },
                )
            )
        b = NXSession.work_part().Features.CreateExtrudeBuilder(None)
        b.Limits.StartExtend.Value.RightHandSide = str(z)
        b.Limits.EndExtend.Value.RightHandSide = str(z + height)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Cuboid {length}x{width}x{height}mm at ({x},{y},{z})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("create_two_cuboids", "Create two cuboids next to each other")
def create_two_cuboids():
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("create_two_cuboids", {}))
        first = create_cuboid(40.0, 25.0, 20.0, 0.0, 0.0, 0.0)
        if isinstance(first, ToolError):
            return first
        second = create_cuboid(30.0, 25.0, 20.0, 45.0, 0.0, 0.0)
        if isinstance(second, ToolError):
            return second
        return ToolResult("Created two cuboids next to each other")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("create_cylinder", "Create a cylinder with radius height mm from origin x y z along direction X Y or Z")
def create_cylinder(
    radius: float = 10.0,
    height: float = 20.0,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    direction: str = "Z",
):
    try:
        if radius <= 0 or height <= 0:
            return ToolError("Cylinder radius and height must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_cylinder",
                    {
                        "radius": radius,
                        "height": height,
                        "x": x,
                        "y": y,
                        "z": z,
                        "direction": direction,
                    },
                )
            )
        return ToolResult(f"Cylinder R{radius} height {height} at ({x},{y},{z})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("extrude", "Extrude active sketch by distance mm")
def extrude(distance: float, start: float = 0.0):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("extrude", {"distance": distance, "start": start})
            )
        b = NXSession.work_part().Features.CreateExtrudeBuilder(None)
        b.Limits.StartExtend.Value.RightHandSide = str(start)
        b.Limits.EndExtend.Value.RightHandSide = str(distance)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Extruded {distance}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("revolve", "Revolve active sketch around axis by angle_deg")
def revolve(axis: str = "Z", angle_deg: float = 360.0):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("revolve", {"axis": axis, "angle_deg": angle_deg})
            )
        b = NXSession.work_part().Features.CreateRevolveBuilder(None)
        b.Limits.EndExtend.Value.RightHandSide = str(angle_deg)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Revolved {angle_deg} degrees around {axis}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("boolean_unite", "Unite two solid bodies")
def boolean_unite(target: str, tool: str):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("boolean_unite", {"target": target, "tool": tool})
            )
        nxopen = NXSession.nxopen()
        b = NXSession.work_part().Features.CreateBooleanBuilder(None)
        b.Operation = nxopen.Features.BooleanBuilder.BooleanType.Unite
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"United '{target}' + '{tool}'")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("boolean_subtract", "Subtract tool body from target body")
def boolean_subtract(target: str, tool: str):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("boolean_subtract", {"target": target, "tool": tool})
            )
        nxopen = NXSession.nxopen()
        b = NXSession.work_part().Features.CreateBooleanBuilder(None)
        b.Operation = nxopen.Features.BooleanBuilder.BooleanType.Subtract
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Subtracted '{tool}' from '{target}'")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("add_fillet", "Add edge fillet with radius mm to edges such as outer_edges vertical_edges top_edges bottom_edges")
def add_fillet(radius: float, body: str = "last", edges: str = "outer_edges"):
    try:
        if radius <= 0:
            return ToolError("Fillet radius must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "add_fillet",
                    {"radius": radius, "body": body, "edges": edges},
                )
            )
        b = NXSession.work_part().Features.CreateEdgeBlendBuilder(None)
        b.Tolerance = 0.01
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Fillet R{radius}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("add_chamfer", "Add chamfer with offset mm to edges such as outer_edges vertical_edges top_edges bottom_edges")
def add_chamfer(offset: float, body: str = "last", edges: str = "outer_edges"):
    try:
        if offset <= 0:
            return ToolError("Chamfer offset must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "add_chamfer",
                    {"offset": offset, "body": body, "edges": edges},
                )
            )
        b = NXSession.work_part().Features.CreateChamferBuilder(None)
        b.FirstOffset = str(offset)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Chamfer {offset}mm")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("add_hole", "Add hole at x y z with diameter and depth in mm on a target body")
def add_hole(
    x: float,
    y: float,
    z: float,
    diameter: float,
    depth: float,
    target: str = "last",
    direction: str = "-Z",
    placement_face: str = "top",
):
    try:
        if diameter <= 0 or depth <= 0:
            return ToolError("Hole diameter and depth must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "add_hole",
                    {
                        "x": x,
                        "y": y,
                        "z": z,
                        "diameter": diameter,
                        "depth": depth,
                        "target": target,
                        "direction": direction,
                        "placement_face": placement_face,
                    },
                )
            )
        b = NXSession.work_part().Features.CreateHoleBuilder(None)
        b.Diameter.RightHandSide = str(diameter)
        b.Depth.RightHandSide = str(depth)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Hole D={diameter} depth={depth} at ({x},{y},{z})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("mirror_feature", "Mirror a feature about a plane (XY/XZ/YZ)")
def mirror_feature(feature_name: str, plane: str = "XZ"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "mirror_feature",
                    {"feature_name": feature_name, "plane": plane},
                )
            )
        b = NXSession.work_part().Features.CreateMirrorFeatureBuilder(None)
        b.MirrorPlane = plane
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Mirrored '{feature_name}' about {plane}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("pattern_feature", "Linear pattern: count items spaced pitch mm along direction")
def pattern_feature(feature_name: str, direction: str = "X", count: int = 3, pitch: float = 10.0):
    try:
        if count < 2:
            return ToolError("Pattern count must be at least 2")
        if pitch == 0:
            return ToolError("Pattern pitch must be non-zero")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "pattern_feature",
                    {
                        "feature_name": feature_name,
                        "direction": direction,
                        "count": count,
                        "pitch": pitch,
                    },
                )
            )
        b = NXSession.work_part().Features.CreateLinearPatternBuilder(None)
        b.PatternService.PatternCount.RightHandSide = str(count)
        b.PatternService.Pitch.RightHandSide = str(pitch)
        b.CommitFeature()
        b.Destroy()
        return ToolResult(f"Pattern '{feature_name}' {count}x @ {pitch}mm along {direction}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("edit_expression", "Edit a named expression inside the work part and update the model in place")
def edit_expression(name: str, value: str):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "edit_expression",
                    {
                        "name": name,
                        "value": value,
                    },
                )
            )
        return ToolResult(f"Expression '{name}' updated to '{value}'")
    except Exception as e:
        return ToolError(str(e))
