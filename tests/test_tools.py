import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nx_mcp.tools import file_ops, sketch, modeling, assembly, measure, utility
from nx_mcp.tools.registry import ToolRegistry
from nx_mcp.response import ToolResult, ToolError

def test_tools_registered():
    assert len(ToolRegistry.list_tools()) >= 20

def test_create_part():
    r = file_ops.create_part("test.prt")
    assert isinstance(r, ToolResult)
    assert "open_current_nx_result.cmd" in r.message

def test_open_part():
    r = file_ops.open_part("test.prt")
    assert isinstance(r, ToolResult)
    assert "open_current_nx_result.cmd" in r.message

def test_save_part():
    file_ops.create_part("test.prt")
    r = file_ops.save_part()
    assert isinstance(r, ToolResult)
    assert "open_current_nx_result.cmd" in r.message

def test_export_step():
    r = file_ops.export_step("out.stp")
    assert isinstance(r, ToolResult) and "out.stp" in r.message

def test_export_stl():
    assert isinstance(file_ops.export_stl("out.stl"), ToolResult)

def test_create_sketch():
    assert isinstance(sketch.create_sketch("XY"), ToolResult)

def test_draw_line():
    assert isinstance(sketch.draw_line(0,0,50,0), ToolResult)

def test_draw_rectangle():
    r = sketch.draw_rectangle(0,0,100,50)
    assert isinstance(r, ToolResult) and "100" in r.message

def test_draw_circle():
    r = sketch.draw_circle(0,0,25)
    assert isinstance(r, ToolResult) and "R=25" in r.message

def test_draw_arc():
    assert isinstance(sketch.draw_arc(0,0,20,0,90), ToolResult)

def test_extrude():
    r = modeling.extrude(20.0)
    assert isinstance(r, ToolResult) and "20" in r.message

def test_create_cube():
    r = modeling.create_cube(25.0)
    assert isinstance(r, ToolResult) and "25.0" in r.message

def test_create_cube_rejects_non_positive_size():
    r = modeling.create_cube(0.0)
    assert isinstance(r, ToolError) and "positive" in r.error

def test_create_cuboid():
    r = modeling.create_cuboid(40.0, 25.0, 20.0)
    assert isinstance(r, ToolResult) and "40.0x25.0x20.0" in r.message

def test_create_two_cuboids():
    r = modeling.create_two_cuboids()
    assert isinstance(r, ToolResult) and "two cuboids" in r.message

def test_create_cylinder():
    r = modeling.create_cylinder(10.0, 25.0)
    assert isinstance(r, ToolResult) and "Cylinder" in r.message

def test_revolve():
    assert isinstance(modeling.revolve("Z", 360.0), ToolResult)

def test_boolean_unite():
    assert isinstance(modeling.boolean_unite("b1","b2"), ToolResult)

def test_boolean_subtract():
    assert isinstance(modeling.boolean_subtract("b1","b2"), ToolResult)

def test_add_fillet():
    r = modeling.add_fillet(3.0)
    assert isinstance(r, ToolResult) and "3.0" in r.message

def test_add_hole():
    r = modeling.add_hole(0,0,10,8,20)
    assert isinstance(r, ToolResult) and "D=8" in r.message

def test_mirror_feature():
    assert isinstance(modeling.mirror_feature("Extrude(1)","XZ"), ToolResult)

def test_pattern_feature():
    r = modeling.pattern_feature("Hole(1)","X",4,15.0)
    assert isinstance(r, ToolResult) and "4" in r.message

def test_advanced_modeling_tools_route_to_bridge(monkeypatch):
    monkeypatch.delenv("NX_MCP_USE_MOCK_NXOPEN", raising=False)
    calls = []

    def fake_call_nx(tool, args):
        calls.append((tool, args))
        return {"ok": True, "message": f"bridge {tool}"}

    monkeypatch.setattr(modeling.runner, "call_nx", fake_call_nx)

    assert modeling.create_cylinder(12.0, 30.0).message == "bridge create_cylinder"
    assert modeling.revolve("Z", 180.0).message == "bridge revolve"
    assert modeling.boolean_unite("body_a", "body_b").message == "bridge boolean_unite"
    assert modeling.boolean_subtract("body_a", "body_b").message == "bridge boolean_subtract"
    assert modeling.add_fillet(2.0, "last", "vertical_edges").message == "bridge add_fillet"
    assert modeling.add_chamfer(1.0, "last", "top_edges").message == "bridge add_chamfer"
    assert modeling.add_hole(10.0, 10.0, 5.0, 4.0, 10.0).message == "bridge add_hole"
    assert modeling.mirror_feature("last", "XZ").message == "bridge mirror_feature"
    assert modeling.pattern_feature("last", "X", 4, 20.0).message == "bridge pattern_feature"

    assert calls == [
        (
            "create_cylinder",
            {"radius": 12.0, "height": 30.0, "x": 0.0, "y": 0.0, "z": 0.0, "direction": "Z"},
        ),
        ("revolve", {"axis": "Z", "angle_deg": 180.0}),
        ("boolean_unite", {"target": "body_a", "tool": "body_b"}),
        ("boolean_subtract", {"target": "body_a", "tool": "body_b"}),
        ("add_fillet", {"radius": 2.0, "body": "last", "edges": "vertical_edges"}),
        ("add_chamfer", {"offset": 1.0, "body": "last", "edges": "top_edges"}),
        (
            "add_hole",
            {
                "x": 10.0,
                "y": 10.0,
                "z": 5.0,
                "diameter": 4.0,
                "depth": 10.0,
                "target": "last",
                "direction": "auto",
                "placement_face": "top",
            },
        ),
        ("mirror_feature", {"feature_name": "last", "plane": "XZ"}),
        ("pattern_feature", {"feature_name": "last", "direction": "X", "count": 4, "pitch": 20.0}),
    ]

def test_advanced_modeling_validation():
    assert isinstance(modeling.create_cylinder(0.0, 10.0), ToolError)
    assert isinstance(modeling.add_hole(0, 0, 0, 0.0, 10.0), ToolError)
    assert isinstance(modeling.add_fillet(0.0), ToolError)
    assert isinstance(modeling.add_chamfer(0.0), ToolError)
    assert isinstance(modeling.pattern_feature("last", "X", 1, 10.0), ToolError)

def test_add_component():
    assert isinstance(assembly.add_component("bracket.prt",0,0,0), ToolResult)

def test_list_components():
    assert isinstance(assembly.list_components(), ToolResult)

def test_mate_components():
    assert isinstance(assembly.mate_components("c1","f1","c2","f2"), ToolResult)

def test_reposition_component():
    assert isinstance(assembly.reposition_component("bracket",10,20,0), ToolResult)

def test_measure_distance():
    r = measure.measure_distance(0,0,0,3,4,0)
    assert isinstance(r, ToolResult) and "5.0000" in r.message

def test_measure_angle():
    r = measure.measure_angle(1,0,0,0,1,0)
    assert isinstance(r, ToolResult) and "90" in r.message

def test_measure_angle_zero_vector():
    assert isinstance(measure.measure_angle(0,0,0,1,0,0), ToolError)

def test_measure_volume():
    r = measure.measure_volume(10,20,5)
    assert isinstance(r, ToolResult) and "1000" in r.message

def test_get_bounding_box():
    assert isinstance(measure.get_bounding_box(), ToolResult)

def test_set_view_valid():
    assert isinstance(utility.set_view("ISO"), ToolResult)

def test_set_view_invalid():
    r = utility.set_view("DIAGONAL")
    assert isinstance(r, ToolError) and "DIAGONAL" in r.error

def test_reset_nx_bridge():
    assert isinstance(utility.reset_nx_bridge(), ToolResult)

def test_take_screenshot():
    assert isinstance(utility.take_screenshot("out.png"), ToolResult)

def test_list_features():
    assert isinstance(utility.list_features(), ToolResult)

def test_sketch_tools_route_to_bridge(monkeypatch):
    monkeypatch.delenv("NX_MCP_USE_MOCK_NXOPEN", raising=False)
    calls = []

    def fake_call_nx(tool, args):
        calls.append((tool, args))
        return {"ok": True, "message": f"bridge {tool}"}

    monkeypatch.setattr(sketch.runner, "call_nx", fake_call_nx)

    assert sketch.draw_line(0, 0, 10, 20).message == "bridge draw_line"
    assert sketch.draw_arc(5, 5, 10, 0, 90).message == "bridge draw_arc"

    assert calls == [
        ("draw_line", {"x1": 0, "y1": 0, "x2": 10, "y2": 20}),
        ("draw_arc", {"cx": 5, "cy": 5, "radius": 10, "start_angle": 0, "end_angle": 90}),
    ]

def test_new_modeling_tools_route_to_bridge(monkeypatch):
    monkeypatch.delenv("NX_MCP_USE_MOCK_NXOPEN", raising=False)
    calls = []

    def fake_call_nx(tool, args):
        calls.append((tool, args))
        return {"ok": True, "message": f"bridge {tool}"}

    monkeypatch.setattr(modeling.runner, "call_nx", fake_call_nx)

    assert modeling.create_real_sketch("XZ").message == "bridge create_real_sketch"
    assert modeling.extrude_from_sketch(15.0, "sketch_1", 2.0, "Y").message == "bridge extrude_from_sketch"
    assert modeling.add_hole_nx(1.0, 2.0, 3.0, 8.0, 12.0, "body_1", "-Z", "simple").message == "bridge add_hole_nx"
    assert modeling.create_rib(6.0, "X", "body_2", True).message == "bridge create_rib"
    assert modeling.pattern_circular("feat_1", "Y", 6, 180.0).message == "bridge pattern_circular"
    assert modeling.edge_blend(4.0, "body_3", "top_edges").message == "bridge edge_blend"
    assert modeling.chamfer(1.5, "body_4", "bottom_edges").message == "bridge chamfer_edges"
    assert modeling.revolve_cut("X", 90.0, "body_5").message == "bridge revolve_cut"
    assert modeling.extrude_cut(25.0, 5.0, "body_6", "Y").message == "bridge extrude_cut"
    assert modeling.mirror_body_feature("feat_2", "YZ").message == "bridge mirror_feature"

    assert calls == [
        ("create_real_sketch", {"plane": "XZ"}),
        ("extrude_from_sketch", {"sketch_name": "sketch_1", "distance": 15.0, "start": 2.0, "direction": "Y"}),
        ("add_hole_nx", {"x": 1.0, "y": 2.0, "z": 3.0, "diameter": 8.0, "depth": 12.0, "target": "body_1", "direction": "-Z", "hole_type": "simple"}),
        ("create_rib", {"thickness": 6.0, "direction": "X", "body": "body_2", "flip": True}),
        ("pattern_circular", {"feature_name": "feat_1", "axis": "Y", "count": 6, "angle_total": 180.0}),
        ("edge_blend", {"radius": 4.0, "body": "body_3", "edges": "top_edges"}),
        ("chamfer_edges", {"offset": 1.5, "body": "body_4", "edges": "bottom_edges"}),
        ("revolve_cut", {"axis": "X", "angle_deg": 90.0, "target": "body_5"}),
        ("extrude_cut", {"distance": 25.0, "start": 5.0, "target": "body_6", "direction": "Y"}),
        ("mirror_feature", {"feature_name": "feat_2", "plane": "YZ"}),
    ]

def test_new_modeling_validation():
    assert isinstance(modeling.extrude_from_sketch(-5.0), ToolError)
    assert isinstance(modeling.add_hole_nx(0, 0, 0, -1, 10), ToolError)
    assert isinstance(modeling.add_hole_nx(0, 0, 0, 10, -5), ToolError)
    assert isinstance(modeling.create_rib(-2.0), ToolError)
    assert isinstance(modeling.pattern_circular("feat", "Z", 1, 360), ToolError)
    assert isinstance(modeling.pattern_circular("feat", "Z", 4, 0), ToolError)
    assert isinstance(modeling.edge_blend(-1.0), ToolError)
    assert isinstance(modeling.chamfer(-0.5), ToolError)
    assert isinstance(modeling.extrude_cut(-10.0), ToolError)
