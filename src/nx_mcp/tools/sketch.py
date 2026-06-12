from ..tools.registry import mcp_tool
from ..nx_session import NXSession
from ..response import ToolResult, ToolError
import NXOpen


@mcp_tool("create_sketch", "Create a new sketch on a plane XY XZ or YZ")
def create_sketch(plane: str = "XY"):
    try:
        return ToolResult(f"Sketch created on {plane} plane")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("draw_line", "Draw a line from x1 y1 to x2 y2")
def draw_line(x1: float, y1: float, x2: float, y2: float):
    try:
        part = NXSession.work_part()
        part.Curves.CreateLine(NXOpen.Point3d(x1, y1, 0.0), NXOpen.Point3d(x2, y2, 0.0))
        return ToolResult(f"Line {x1},{y1} to {x2},{y2}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("draw_rectangle", "Draw rectangle from corner x y with width and height")
def draw_rectangle(x: float, y: float, width: float, height: float):
    try:
        part = NXSession.work_part()
        corners = [(x,y),(x+width,y),(x+width,y+height),(x,y+height),(x,y)]
        for i in range(4):
            part.Curves.CreateLine(
                NXOpen.Point3d(corners[i][0], corners[i][1], 0.0),
                NXOpen.Point3d(corners[i+1][0], corners[i+1][1], 0.0)
            )
        return ToolResult(f"Rectangle {x},{y} size {width}x{height}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("draw_circle", "Draw circle at cx cy with radius")
def draw_circle(cx: float, cy: float, radius: float):
    try:
        part = NXSession.work_part()
        part.Curves.CreateArc(NXOpen.Point3d(cx, cy, 0.0), NXOpen.Vector3d(0, 0, 1), radius, 0.0, 6.28318)
        return ToolResult(f"Circle {cx},{cy} R={radius}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("draw_arc", "Draw arc at cx cy with radius from start_angle to end_angle degrees")
def draw_arc(cx: float, cy: float, radius: float, start_angle: float, end_angle: float):
    try:
        import math
        part = NXSession.work_part()
        part.Curves.CreateArc(
            NXOpen.Point3d(cx, cy, 0.0), NXOpen.Vector3d(0, 0, 1),
            radius, math.radians(start_angle), math.radians(end_angle)
        )
        return ToolResult(f"Arc {cx},{cy} r={radius} {start_angle} to {end_angle} deg")
    except Exception as e:
        return ToolError(str(e))