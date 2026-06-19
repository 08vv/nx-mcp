import json
import os
import sys
import traceback
from pathlib import Path

import NXOpen
import NXOpen.UF


SESSION = NXOpen.Session.GetSession()
UF_SESSION = NXOpen.UF.UFSession.GetUFSession()
ACTIVE_SKETCH_PLANE = "XY"
_state = {"last_curves": []}


def _default_part_path():
    return str(Path(os.getcwd()).joinpath("nx_mcp_result.prt").resolve())


def _ensure_work_part():
    if SESSION.Parts.Work is None:
        SESSION.Parts.NewDisplay(
            _default_part_path(),
            NXOpen.Part.Units.Millimeters,
        )
    return SESSION.Parts.Work


def fit_view():
    work_part = SESSION.Parts.Work
    if work_part is None:
        return {"ok": False, "error": "No work part is open"}
    work_part.ModelingViews.WorkView.Fit()
    return {"ok": True, "message": "View fitted"}


def create_part(filename):
    SESSION.Parts.NewDisplay(
        filename,
        NXOpen.Part.Units.Millimeters,
    )
    work_part = SESSION.Parts.Work
    if work_part is None:
        return {"ok": False, "error": "Part created but work part not set"}
    fit_view()
    return {"ok": True, "message": f"Created and displayed: {filename}"}


def open_part(filepath):
    SESSION.Parts.Open(filepath)
    fit_view()
    return {"ok": True, "message": f"Opened and displayed: {filepath}"}


def save_part():
    SESSION.Parts.Work.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    return {"ok": True, "message": "Saved"}


def create_sketch(plane="XY"):
    global ACTIVE_SKETCH_PLANE

    plane = plane.upper()
    if plane not in {"XY", "XZ", "YZ"}:
        return {"ok": False, "error": f"Invalid sketch plane: {plane}"}

    _ensure_work_part()

    ACTIVE_SKETCH_PLANE = plane
    return {"ok": True, "message": f"Sketch created on {plane} plane"}


def _point_on_active_plane(x, y):
    if ACTIVE_SKETCH_PLANE == "XY":
        return NXOpen.Point3d(x, y, 0.0)
    if ACTIVE_SKETCH_PLANE == "XZ":
        return NXOpen.Point3d(x, 0.0, y)
    return NXOpen.Point3d(0.0, x, y)


def draw_rectangle(x, y, width, height):
    x = float(x)
    y = float(y)
    width = float(width)
    height = float(height)

    part = _ensure_work_part()

    corners = [
        (x, y),
        (x + width, y),
        (x + width, y + height),
        (x, y + height),
        (x, y),
    ]
    lines = []
    for index in range(4):
        line = part.Curves.CreateLine(
            _point_on_active_plane(corners[index][0], corners[index][1]),
            _point_on_active_plane(corners[index + 1][0], corners[index + 1][1]),
        )
        lines.append(line)
    _state["last_curves"] = lines
    fit_view()

    return {
        "ok": True,
        "message": f"Rectangle {x},{y} size {width}x{height}",
    }


def _normal_for_active_plane():
    if ACTIVE_SKETCH_PLANE == "XY":
        return NXOpen.Vector3d(0.0, 0.0, 1.0)
    if ACTIVE_SKETCH_PLANE == "XZ":
        return NXOpen.Vector3d(0.0, 1.0, 0.0)
    return NXOpen.Vector3d(1.0, 0.0, 0.0)


def draw_circle(cx, cy, radius):
    cx = float(cx)
    cy = float(cy)
    radius = float(radius)

    if radius <= 0.0:
        return {"ok": False, "error": "Circle radius must be positive"}

    part = _ensure_work_part()
    circle = part.Curves.CreateArc(
        _point_on_active_plane(cx, cy),
        _normal_for_active_plane(),
        radius,
        0.0,
        6.283185307179586,
    )
    _state["last_curves"] = [circle]
    fit_view()
    return {"ok": True, "message": f"Circle {cx},{cy} R={radius}"}


def draw_cylinder_profile(outer_radius, inner_radius):
    outer_radius = float(outer_radius)
    inner_radius = float(inner_radius)

    _ensure_work_part()
    if inner_radius <= 0.0 or outer_radius <= 0.0:
        return {"ok": False, "error": "Radii must be positive"}
    if inner_radius >= outer_radius:
        return {"ok": False, "error": "Inner radius must be smaller than outer radius"}

    outer = _create_xy_arc(outer_radius)
    inner = _create_xy_arc(inner_radius)
    _state["last_curves"] = [outer, inner]
    return {
        "ok": True,
        "message": f"Cylinder profile outer R={outer_radius} inner R={inner_radius}",
    }


def _create_xy_arc(radius):
    arc = NXOpen.UF.Curve.Arc()
    arc.StartAngle = 0.0
    arc.EndAngle = 6.283185307179586
    arc.ArcCenter.append(0.0)
    arc.ArcCenter.append(0.0)
    arc.ArcCenter.append(0.0)
    arc.Radius = float(radius)
    wcs_tag = UF_SESSION.Csys.AskWcs()
    arc.MatrixTag = UF_SESSION.Csys.AskMatrixOfObject(wcs_tag)
    arc_tag = UF_SESSION.Curve.CreateArc(arc)
    return NXOpen.TaggedObjectManager().GetTaggedObject(arc_tag)


def extrude(distance, start=0):
    work_part = SESSION.Parts.Work
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No curves to extrude"}

    builder = work_part.Features.CreateExtrudeBuilder(
        NXOpen.Features.Feature.Null
    )

    section = work_part.Sections.CreateSection(
        float(0.0095), float(0.01), float(0.5)
    )
    rules = []
    for curve in curves:
        rule = SESSION.Parts.Work.ScRuleFactory.CreateRuleCurveDumb(
            [curve]
        )
        rules.append(rule)
    section.AddToSection(
        rules, curves[0],
        NXOpen.NXObject.Null,
        NXOpen.NXObject.Null,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create,
        False
    )
    builder.Section = section
    direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
    origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    builder.Direction = work_part.Directions.CreateDirection(
        origin,
        direction,
        NXOpen.SmartObject.UpdateOption.WithinModeling
    )
    builder.Limits.StartExtend.Value.RightHandSide = str(float(start))
    builder.Limits.EndExtend.Value.RightHandSide = str(float(distance))
    feature = builder.CommitFeature()
    builder.Destroy()
    _state["last_curves"] = []
    fit_view()
    return {"ok": True, "message": f"Extruded {float(distance)}mm"}


def create_cuboid(length=40.0, width=25.0, height=20.0, x=0.0, y=0.0, z=0.0):
    length = float(length)
    width = float(width)
    height = float(height)
    x = float(x)
    y = float(y)
    z = float(z)

    if length <= 0.0 or width <= 0.0 or height <= 0.0:
        return {"ok": False, "error": "Cuboid dimensions must be positive"}

    work_part = _ensure_work_part()
    builder = work_part.Features.CreateBlockFeatureBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(x, y, z)
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(origin, str(length), str(width), str(height))
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        builder.CommitFeature()
    finally:
        builder.Destroy()

    fit_view()
    return {
        "ok": True,
        "message": f"Cuboid {length}x{width}x{height}mm at ({x},{y},{z})",
    }


def create_two_cuboids():
    first = create_cuboid(40.0, 25.0, 20.0, 0.0, 0.0, 0.0)
    if not first.get("ok"):
        return first

    second = create_cuboid(30.0, 25.0, 20.0, 45.0, 0.0, 0.0)
    if not second.get("ok"):
        return second

    fit_view()
    return {
        "ok": True,
        "message": "Created two cuboids next to each other",
    }


def create_cube(size=10.0, x=0.0, y=0.0, z=0.0):
    size = float(size)
    x = float(x)
    y = float(y)
    z = float(z)

    if size <= 0.0:
        return {"ok": False, "error": "Cube size must be positive"}

    sketch_result = create_sketch("XY")
    if not sketch_result.get("ok"):
        return sketch_result

    rectangle_result = draw_rectangle(x, y, size, size)
    if not rectangle_result.get("ok"):
        return rectangle_result

    extrude_result = extrude(size, z)
    if not extrude_result.get("ok"):
        return extrude_result

    fit_view()
    return {"ok": True, "message": f"Cube {size}mm at ({x},{y},{z})"}


def dispatch(command):
    tool = command.get("tool")
    args = command.get("args", {})

    if tool == "create_part":
        return create_part(args["filename"])
    if tool == "open_part":
        return open_part(args["filepath"])
    if tool == "save_part":
        return save_part()
    if tool == "create_sketch":
        return create_sketch(args.get("plane", "XY"))
    if tool == "draw_rectangle":
        return draw_rectangle(args["x"], args["y"], args["width"], args["height"])
    if tool == "draw_circle":
        return draw_circle(args["cx"], args["cy"], args["radius"])
    if tool == "draw_cylinder_profile":
        return draw_cylinder_profile(args["outer_radius"], args["inner_radius"])
    if tool == "create_cube":
        return create_cube(
            args.get("size", 10.0),
            args.get("x", 0.0),
            args.get("y", 0.0),
            args.get("z", 0.0),
        )
    if tool == "create_cuboid":
        return create_cuboid(
            args.get("length", 40.0),
            args.get("width", 25.0),
            args.get("height", 20.0),
            args.get("x", 0.0),
            args.get("y", 0.0),
            args.get("z", 0.0),
        )
    if tool == "create_two_cuboids":
        return create_two_cuboids()
    if tool == "extrude":
        return extrude(args["distance"], args.get("start", 0))
    if tool == "fit_view":
        return fit_view()

    return {"ok": False, "error": f"Unknown bridge tool: {tool}"}


def handle_line(line):
    try:
        command = json.loads(line)
        return dispatch(command)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        result = handle_line(line)
        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
