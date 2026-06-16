import json
import sys
import traceback

import NXOpen
import NXOpen.UF


SESSION = NXOpen.Session.GetSession()
UF_SESSION = NXOpen.UF.UFSession.GetUFSession()
ACTIVE_SKETCH_PLANE = "XY"
_state = {"last_curves": []}


def create_part(filename):
    SESSION.Parts.NewDisplay(
        filename,
        NXOpen.Part.Units.Millimeters,
    )
    work_part = SESSION.Parts.Work
    if work_part is None:
        return {"ok": False, "error": "Part created but work part not set"}
    return {"ok": True, "message": f"Created: {filename}"}


def open_part(filepath):
    SESSION.Parts.Open(filepath)
    return {"ok": True, "message": f"Opened: {filepath}"}


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

    if SESSION.Parts.Work is None:
        return {"ok": False, "error": "No work part is open"}

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

    part = SESSION.Parts.Work
    if part is None:
        return {"ok": False, "error": "No work part is open"}

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

    return {
        "ok": True,
        "message": f"Rectangle {x},{y} size {width}x{height}",
    }


def draw_cylinder_profile(outer_radius, inner_radius):
    outer_radius = float(outer_radius)
    inner_radius = float(inner_radius)

    part = SESSION.Parts.Work
    if part is None:
        return {"ok": False, "error": "No work part is open"}
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
    return {"ok": True, "message": f"Extruded {float(distance)}mm"}


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
    if tool == "draw_cylinder_profile":
        return draw_cylinder_profile(args["outer_radius"], args["inner_radius"])
    if tool == "extrude":
        return extrude(args["distance"], args.get("start", 0))

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
