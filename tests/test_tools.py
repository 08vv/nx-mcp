import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nx_mcp.tools import file_ops, sketch, modeling, assembly, measure, utility
from nx_mcp.tools.registry import ToolRegistry
from nx_mcp.response import ToolResult, ToolError

def test_tools_registered():
    assert len(ToolRegistry.list_tools()) >= 20

def test_create_part():
    assert isinstance(file_ops.create_part("test.prt"), ToolResult)

def test_open_part():
    assert isinstance(file_ops.open_part("test.prt"), ToolResult)

def test_save_part():
    assert isinstance(file_ops.save_part(), ToolResult)

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

def test_take_screenshot():
    assert isinstance(utility.take_screenshot("out.png"), ToolResult)

def test_list_features():
    assert isinstance(utility.list_features(), ToolResult)
