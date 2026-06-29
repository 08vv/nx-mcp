import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nx_mcp.tools import surface_modeling, combine_operations, edit_operations
from nx_mcp.tools.registry import ToolRegistry
from nx_mcp.response import ToolResult, ToolError


def test_surface_tools_registered():
    tools = {t["name"] for t in ToolRegistry.list_tools()}
    assert "create_base_surface" in tools
    assert "extrude_surface" in tools
    assert "create_swept" in tools
    assert "thicken_sheet" in tools
    assert "boolean_combine" in tools
    assert "trim_sheet" in tools
    assert "sew_sheets" in tools
    assert "reverse_normal" in tools
    assert "local_untrim_extend" in tools


def test_surface_modeling_validation():
    # Base surface must have positive dims
    assert isinstance(surface_modeling.create_base_surface("XY", -10, 50), ToolError)
    assert isinstance(surface_modeling.create_base_surface("XY", 50, 0), ToolError)
    # Extrude must have positive distance
    assert isinstance(surface_modeling.extrude_surface(-5.0), ToolError)
    # Tube OD must be positive
    assert isinstance(surface_modeling.create_tube("last", -10), ToolError)
    # Thicken must be positive
    assert isinstance(surface_modeling.thicken_sheet(-2.0), ToolError)
    # Ribbon width must be positive
    assert isinstance(surface_modeling.ribbon_builder(-5.0), ToolError)


def test_combine_operations_validation():
    assert isinstance(combine_operations.boolean_combine("invalid_op"), ToolError)
    assert isinstance(combine_operations.extend_sheet(-5.0), ToolError)
    assert isinstance(combine_operations.emboss_body("last", "last", -10.0), ToolError)


def test_edit_operations_validation():
    assert isinstance(edit_operations.local_untrim_extend(0, 0, 0, -5.0), ToolError)
    assert isinstance(edit_operations.enlarge_face("last", -2.0), ToolError)


def test_mock_executions():
    os.environ["NX_MCP_USE_MOCK_NXOPEN"] = "1"
    assert isinstance(surface_modeling.create_base_surface("XY", 100, 100), ToolResult)
    assert isinstance(surface_modeling.extrude_surface(20.0), ToolResult)
    assert isinstance(surface_modeling.create_swept(), ToolResult)
    assert isinstance(combine_operations.trim_sheet(), ToolResult)
    assert isinstance(combine_operations.sew_sheets(), ToolResult)
    assert isinstance(edit_operations.reverse_normal(), ToolResult)


def test_surface_routing(monkeypatch):
    monkeypatch.delenv("NX_MCP_USE_MOCK_NXOPEN", raising=False)
    calls = []

    def fake_call_nx(tool, args):
        calls.append((tool, args))
        return {"ok": True, "message": f"bridge {tool}"}

    monkeypatch.setattr(surface_modeling.runner, "call_nx", fake_call_nx)
    monkeypatch.setattr(combine_operations.runner, "call_nx", fake_call_nx)
    monkeypatch.setattr(edit_operations.runner, "call_nx", fake_call_nx)

    assert surface_modeling.create_base_surface("XY", 10.0, 20.0).message == "bridge create_base_surface"
    assert surface_modeling.extrude_surface(15.0, 5.0, "Y").message == "bridge extrude_surface"
    assert combine_operations.trim_sheet("b1", "s1").message == "bridge trim_sheet"
    assert edit_operations.reverse_normal("b2").message == "bridge reverse_normal"

    assert calls == [
        ("create_base_surface", {"plane": "XY", "width": 10.0, "height": 20.0}),
        ("extrude_surface", {"distance": 15.0, "start": 5.0, "direction": "Y"}),
        ("trim_sheet", {"target_body": "b1", "boundary_sketch": "s1"}),
        ("reverse_normal", {"body": "b2"}),
    ]

