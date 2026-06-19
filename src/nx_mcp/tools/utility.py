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


@mcp_tool("set_view", "Set viewport to TOP / FRONT / RIGHT / ISO")
def set_view(view_name: str = "ISO"):
    valid = {"TOP","FRONT","RIGHT","BACK","LEFT","BOTTOM","ISO"}
    view_name = view_name.upper()
    if view_name not in valid:
        return ToolError(f"Invalid view '{view_name}'. Choose: {', '.join(valid)}")
    try:
        NXSession.ui().ModelingViews.WorkView.Orient(view_name)
        return ToolResult(f"View set to {view_name}")
    except Exception as e: return ToolError(str(e))

@mcp_tool("fit_view", "Fit model to fill the NX viewport")
def fit_view():
    try:
        if not _use_mock_nxopen():
            return _bridge_result(runner.call_nx("fit_view", {}))
        NXSession.ui().ModelingViews.WorkView.Fit()
        return ToolResult("View fitted")
    except Exception as e: return ToolError(str(e))


@mcp_tool("reset_nx_bridge", "Restart the live NX automation bridge")
def reset_nx_bridge():
    try:
        runner.reset_nx_bridge()
        return ToolResult("NX bridge reset")
    except Exception as e: return ToolError(str(e))


@mcp_tool("take_screenshot", "Save viewport screenshot to PNG")
def take_screenshot(output_path: str = "screenshot.png"):
    try:
        NXSession.ui().ModelingViews.WorkView.SaveImage(output_path, 1920, 1080)
        return ToolResult(f"Screenshot saved: {output_path}")
    except Exception as e: return ToolError(str(e))

@mcp_tool("list_features", "List all features in the part feature tree")
def list_features():
    try:
        features = NXSession.work_part().Features.ToArray()
        names = [f.GetFeatureName() for f in features] if features else []
        return ToolResult("Features: " + (", ".join(names) if names else "none"))
    except Exception as e: return ToolError(str(e))
