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


@mcp_tool("extrude", "Extrude active sketch curves by distance mm. Extrudes perpendicular to active sketch plane.")
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


@mcp_tool("revolve", "Revolve active sketch around axis by angle_deg. Axis defaults to 'auto' which resolves to sketch plane vertical direction.")
def revolve(axis: str = "auto", angle_deg: float = 360.0):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "revolve", {"axis": axis, "angle_deg": angle_deg}
                )
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


@mcp_tool("add_fillet", "Add edge fillet with radius mm to edges (e.g., outer_edges, vertical_edges, top_edges, bottom_edges, x_aligned_edges, y_aligned_edges, z_aligned_edges, min_z_edges, max_z_edges)")
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


@mcp_tool("add_chamfer", "Add chamfer with offset mm to edges (e.g., outer_edges, vertical_edges, top_edges, bottom_edges, x_aligned_edges, y_aligned_edges, z_aligned_edges, min_z_edges, max_z_edges)")
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


@mcp_tool("add_hole", "Add hole at x y z with diameter and depth in mm on a target body. Direction 'auto' drills into active sketch plane.")
def add_hole(
    x: float,
    y: float,
    z: float,
    diameter: float,
    depth: float,
    target: str = "last",
    direction: str = "auto",
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


# ---------------------------------------------------------------------------
# NEW TOOLS (10)
# ---------------------------------------------------------------------------


@mcp_tool(
    "create_real_sketch",
    "Create a proper constrained NX Sketch object on a plane (XY/XZ/YZ) and make it active for drawing",
)
def create_real_sketch(plane: str = "XY"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("create_real_sketch", {"plane": plane})
            )
        return ToolResult(f"Sketch created on {plane} plane")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "extrude_from_sketch",
    "Extrude a named sketch profile by distance mm along direction. Direction 'auto' extrudes normal to sketch plane.",
)
def extrude_from_sketch(
    distance: float,
    sketch_name: str = "last",
    start: float = 0.0,
    direction: str = "auto",
):
    try:
        if distance <= 0:
            return ToolError("Extrude distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "extrude_from_sketch",
                    {
                        "sketch_name": sketch_name,
                        "distance": distance,
                        "start": start,
                        "direction": direction,
                    },
                )
            )
        return ToolResult(f"Extruded sketch '{sketch_name}' {distance}mm along {direction}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "add_hole_nx",
    "Proper NX Hole Builder: create a simple hole at x y z with diameter and depth. Direction 'auto' drills into active sketch plane.",
)
def add_hole_nx(
    x: float,
    y: float,
    z: float,
    diameter: float,
    depth: float,
    target: str = "last",
    direction: str = "auto",
    hole_type: str = "simple",
):
    try:
        if diameter <= 0 or depth <= 0:
            return ToolError("Hole diameter and depth must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "add_hole_nx",
                    {
                        "x": x,
                        "y": y,
                        "z": z,
                        "diameter": diameter,
                        "depth": depth,
                        "target": target,
                        "direction": direction,
                        "hole_type": hole_type,
                    },
                )
            )
        return ToolResult(f"Hole D={diameter} depth={depth} at ({x},{y},{z})")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "create_rib",
    "Create a rib/web feature from the active sketch profile with a given thickness mm. Direction 'auto' is perpendicular to rib profile plane.",
)
def create_rib(
    thickness: float,
    direction: str = "auto",
    body: str = "last",
    flip: bool = False,
):
    try:
        if thickness <= 0:
            return ToolError("Rib thickness must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "create_rib",
                    {
                        "thickness": thickness,
                        "direction": direction,
                        "body": body,
                        "flip": flip,
                    },
                )
            )
        return ToolResult(f"Rib T={thickness}mm along {direction}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "pattern_circular",
    "Circular pattern of a feature: count instances evenly spaced over angle_total degrees about axis. Axis 'auto' is normal to active sketch plane.",
)
def pattern_circular(
    feature_name: str,
    axis: str = "auto",
    count: int = 4,
    angle_total: float = 360.0,
):
    try:
        if count < 2:
            return ToolError("Circular pattern count must be at least 2")
        if angle_total == 0:
            return ToolError("angle_total must be non-zero")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "pattern_circular",
                    {
                        "feature_name": feature_name,
                        "axis": axis,
                        "count": count,
                        "angle_total": angle_total,
                    },
                )
            )
        return ToolResult(f"Circular pattern '{feature_name}' {count}x over {angle_total}° about {axis}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "edge_blend",
    "Fillet edges by selection with a given radius mm (uses outer_edges/vertical_edges/top_edges/bottom_edges/x_aligned_edges/y_aligned_edges/z_aligned_edges/min_z_edges/max_z_edges hints)",
)
def edge_blend(radius: float, body: str = "last", edges: str = "outer_edges"):
    try:
        if radius <= 0:
            return ToolError("Edge blend radius must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "edge_blend",
                    {"radius": radius, "body": body, "edges": edges},
                )
            )
        return ToolResult(f"Edge blend R{radius}mm on {edges}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "chamfer",
    "Chamfer edges by selection with a given offset mm (uses outer_edges/vertical_edges/top_edges/bottom_edges/x_aligned_edges/y_aligned_edges/z_aligned_edges/min_z_edges/max_z_edges hints)",
)
def chamfer(offset: float, body: str = "last", edges: str = "outer_edges"):
    try:
        if offset <= 0:
            return ToolError("Chamfer offset must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "chamfer_edges",
                    {"offset": offset, "body": body, "edges": edges},
                )
            )
        return ToolResult(f"Chamfer {offset}mm on {edges}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "revolve_cut",
    "Revolve the active sketch profile around axis by angle_deg to cut/remove material from target body. Axis 'auto' is sketch plane vertical direction.",
)
def revolve_cut(axis: str = "auto", angle_deg: float = 360.0, target: str = "last"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "revolve_cut",
                    {"axis": axis, "angle_deg": angle_deg, "target": target},
                )
            )
        return ToolResult(f"Revolve-cut {angle_deg}° about {axis}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "extrude_cut",
    "Extrude the active sketch profile by distance mm to cut/remove material from an existing body. Direction 'auto' extrudes normal to sketch plane.",
)
def extrude_cut(
    distance: float,
    start: float = 0.0,
    target: str = "last",
    direction: str = "auto",
):
    try:
        if distance <= 0:
            return ToolError("Extrude-cut distance must be positive")
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "extrude_cut",
                    {
                        "distance": distance,
                        "start": start,
                        "target": target,
                        "direction": direction,
                    },
                )
            )
        return ToolResult(f"Extrude-cut {distance}mm from '{target}' along {direction}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool(
    "mirror_body_feature",
    "Mirror a feature about a plane (XY/XZ/YZ) — same as mirror_feature but with intent-specific name",
)
def mirror_body_feature(feature_name: str, plane: str = "XZ"):
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx(
                    "mirror_feature",
                    {"feature_name": feature_name, "plane": plane},
                )
            )
        return ToolResult(f"Mirrored '{feature_name}' about {plane}")
    except Exception as e:
        return ToolError(str(e))
