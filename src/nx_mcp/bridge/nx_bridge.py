import json
import os
import sys
import traceback
from pathlib import Path
import socket
import select
import time
import math

import NXOpen
import NXOpen.UF


SESSION = NXOpen.Session.GetSession()
UF_SESSION = NXOpen.UF.UFSession.GetUFSession()
ACTIVE_SKETCH_PLANE = "XY"
_state = {
    "last_curves": [],
    "last_feature": None,
    "last_body": None,
    "features": {},
    "bodies": {},
}


class SelectionError(RuntimeError):
    pass


def _default_part_path():
    return str(Path(os.getcwd()).joinpath("nx_mcp_result.prt").resolve())


def _ensure_work_part():
    if SESSION.Parts.Work is None:
        SESSION.Parts.NewDisplay(
            _default_part_path(),
            NXOpen.Part.Units.Millimeters,
        )
    return SESSION.Parts.Work


def _create_named_expression(work_part, prefix, value):
    if not hasattr(work_part, "Expressions"):
        return f"{prefix}_MOCK"
    counter = 1
    while True:
        name = f"{prefix}_{counter}"
        try:
            work_part.Expressions.FindObject(name)
            counter += 1
        except Exception:
            break
    work_part.Expressions.CreateExpression("Number", f"{name} = {value}")
    return name


def _feature_name(feature):
    if feature is None:
        return ""
    for attr in ("GetFeatureName", "Name", "JournalIdentifier"):
        value = getattr(feature, attr, None)
        if callable(value):
            try:
                name = value()
                if name:
                    return str(name)
            except Exception:
                pass
        elif value:
            return str(value)
    return f"feature_{getattr(feature, 'Tag', id(feature))}"


def _body_name(body):
    if body is None:
        return ""
    for attr in ("Name", "JournalIdentifier"):
        value = getattr(body, attr, None)
        if value:
            return str(value)
    return f"body_{getattr(body, 'Tag', id(body))}"


def _remember_feature(feature):
    if feature is None:
        return feature

    name = _feature_name(feature)
    _state["last_feature"] = feature
    _state["features"][name.lower()] = feature

    get_bodies = getattr(feature, "GetBodies", None)
    if callable(get_bodies):
        try:
            for body in get_bodies() or []:
                _remember_body(body)
        except Exception:
            pass
    return feature


def _remember_body(body):
    if body is None:
        return body
    name = _body_name(body)
    _state["last_body"] = body
    _state["bodies"][name.lower()] = body
    return body


def _iter_features(work_part):
    to_array = getattr(work_part.Features, "ToArray", None)
    if callable(to_array):
        return list(to_array() or [])
    return []


def _iter_bodies(work_part):
    bodies = getattr(work_part, "Bodies", None)
    if bodies is not None:
        to_array = getattr(bodies, "ToArray", None)
        if callable(to_array):
            return list(to_array() or [])
        try:
            return list(bodies)
        except TypeError:
            pass

    found = []
    for feature in _iter_features(work_part):
        get_bodies = getattr(feature, "GetBodies", None)
        if not callable(get_bodies):
            continue
        for body in get_bodies() or []:
            if body not in found:
                found.append(body)
    return found


def _resolve_feature(reference="last"):
    work_part = _ensure_work_part()
    ref = str(reference or "last").strip().lower()
    if ref in {"last", "previous", "previous feature", "last feature", "last_created"}:
        feature = _state.get("last_feature")
        if feature is not None:
            return feature

    if ref in _state["features"]:
        return _state["features"][ref]

    for feature in _iter_features(work_part):
        name = _feature_name(feature).lower()
        _state["features"][name] = feature
        if ref == name or ref in name:
            return feature

    raise SelectionError(f"Could not resolve feature reference: {reference}")


def _resolve_body(reference="last"):
    work_part = _ensure_work_part()
    ref = str(reference or "last").strip().lower()
    if ref in {"last", "last body", "last_created", "last created body", "target"}:
        body = _state.get("last_body")
        if body is not None:
            return body

    if ref in _state["bodies"]:
        return _state["bodies"][ref]

    bodies = _iter_bodies(work_part)
    for body in bodies:
        name = _body_name(body).lower()
        _state["bodies"][name] = body
        if ref == name or ref in name:
            return body

    if len(bodies) == 1 and ref in {"", "body", "solid", "work"}:
        return _remember_body(bodies[0])

    raise SelectionError(f"Could not resolve body reference: {reference}")


def _point_tuple(point):
    if isinstance(point, (tuple, list)):
        return float(point[0]), float(point[1]), float(point[2])
    return float(point.X), float(point.Y), float(point.Z)


def _body_bounds(body):
    try:
        bbox = UF_SESSION.Modl.AskBoundingBox(body.Tag)
        return (
            (float(bbox[0]), float(bbox[1]), float(bbox[2])),
            (float(bbox[3]), float(bbox[4]), float(bbox[5])),
        )
    except Exception:
        pass

    points = []
    for edge in list(body.GetEdges() or []):
        try:
            pt1, pt2, _vertex_count = UF_SESSION.Modeling.AskEdgeVerts(edge.Tag)
            points.extend([_point_tuple(pt1), _point_tuple(pt2)])
        except Exception:
            continue
    if not points:
        raise SelectionError("Could not determine body bounds")

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _edge_midpoint(edge):
    pt1, pt2, _vertex_count = UF_SESSION.Modeling.AskEdgeVerts(edge.Tag)
    p1 = _point_tuple(pt1)
    p2 = _point_tuple(pt2)
    return tuple((a + b) / 2.0 for a, b in zip(p1, p2))


def _edge_z_range(edge):
    pt1, pt2, _vertex_count = UF_SESSION.Modeling.AskEdgeVerts(edge.Tag)
    p1 = _point_tuple(pt1)
    p2 = _point_tuple(pt2)
    return min(p1[2], p2[2]), max(p1[2], p2[2])


def _resolve_edges(body_reference="last", edge_reference="outer_edges"):
    body = _resolve_body(body_reference)
    edges = list(body.GetEdges() or [])
    if not edges:
        raise SelectionError(f"No edges found on body reference: {body_reference}")

    ref = str(edge_reference or "all").strip().lower().replace("-", "_")
    if ref in {"all", "all_edges", "outer", "outer_edges"}:
        return edges

    if ref in {"vertical", "vertical_edges"}:
        selected = []
        for edge in edges:
            try:
                z_min, z_max = _edge_z_range(edge)
            except Exception:
                continue
            if abs(z_max - z_min) > 0.001:
                selected.append(edge)
        if selected:
            return selected

    if ref in {"top", "top_edges", "bottom", "bottom_edges"}:
        (_min_x, _min_y, min_z), (_max_x, _max_y, max_z) = _body_bounds(body)
        target_z = max_z if ref.startswith("top") else min_z
        selected = []
        for edge in edges:
            try:
                z_min, z_max = _edge_z_range(edge)
            except Exception:
                continue
            if abs(z_min - target_z) < 0.001 and abs(z_max - target_z) < 0.001:
                selected.append(edge)
        if selected:
            return selected

    raise SelectionError(f"Could not resolve edge reference: {edge_reference}")


def _direction_vector(direction):
    ref = str(direction or "Z").strip().upper()
    vectors = {
        "X": (1.0, 0.0, 0.0),
        "+X": (1.0, 0.0, 0.0),
        "-X": (-1.0, 0.0, 0.0),
        "Y": (0.0, 1.0, 0.0),
        "+Y": (0.0, 1.0, 0.0),
        "-Y": (0.0, -1.0, 0.0),
        "Z": (0.0, 0.0, 1.0),
        "+Z": (0.0, 0.0, 1.0),
        "-Z": (0.0, 0.0, -1.0),
    }
    if ref not in vectors:
        raise SelectionError(f"Invalid direction: {direction}")
    return NXOpen.Vector3d(*vectors[ref])


def _plane_normal(plane):
    ref = str(plane or "XY").strip().upper()
    normals = {
        "XY": (0.0, 0.0, 1.0),
        "XZ": (0.0, 1.0, 0.0),
        "YZ": (1.0, 0.0, 0.0),
    }
    if ref not in normals:
        raise SelectionError(f"Invalid plane: {plane}")
    return NXOpen.Vector3d(*normals[ref])


def _fixed_datum_plane_type(plane):
    ref = str(plane or "XY").strip().upper()
    fixed_types = {
        "XY": NXOpen.Features.DatumPlaneBuilder.FixedType.Xy,
        "XZ": NXOpen.Features.DatumPlaneBuilder.FixedType.Zx,
        "ZX": NXOpen.Features.DatumPlaneBuilder.FixedType.Zx,
        "YZ": NXOpen.Features.DatumPlaneBuilder.FixedType.Yz,
    }
    if ref not in fixed_types:
        raise SelectionError(f"Invalid plane: {plane}")
    return fixed_types[ref]


def _create_direction(work_part, origin, direction):
    return work_part.Directions.CreateDirection(
        origin,
        direction,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )


def _create_axis(work_part, origin, direction):
    return work_part.Axes.CreateAxis(
        origin,
        direction,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )


def _vector_components(vector):
    return [float(vector.X), float(vector.Y), float(vector.Z)]


def _set_collector_rules(collector, rules):
    replace_rules = getattr(collector, "ReplaceRules", None)
    if not callable(replace_rules):
        raise SelectionError("NX collector does not support ReplaceRules")
    replace_rules(rules, False)


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
    try:
        # OpenDisplay opens the part AND makes it the active display/work part
        SESSION.Parts.OpenDisplay(filepath)
    except Exception:
        # Fallback for NX versions where OpenDisplay signature differs
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
    _remember_feature(feature)
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
    
    # Create expressions
    l_name = _create_named_expression(work_part, "CUBOID_L", length)
    w_name = _create_named_expression(work_part, "CUBOID_W", width)
    h_name = _create_named_expression(work_part, "CUBOID_H", height)
    
    builder = work_part.Features.CreateBlockFeatureBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(x, y, z)
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(origin, l_name, w_name, h_name)
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        feature = builder.CommitFeature()
        _remember_feature(feature)
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

    work_part = _ensure_work_part()
    s_name = _create_named_expression(work_part, "CUBE_SIZE", size)

    builder = work_part.Features.CreateBlockFeatureBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(x, y, z)
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(origin, s_name, s_name, s_name)
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {"ok": True, "message": f"Cube {size}mm at ({x},{y},{z})"}


def create_cylinder(radius=10.0, height=20.0, x=0.0, y=0.0, z=0.0, direction="Z"):
    radius = float(radius)
    height = float(height)
    x = float(x)
    y = float(y)
    z = float(z)

    if radius <= 0.0 or height <= 0.0:
        return {"ok": False, "error": "Cylinder radius and height must be positive"}

    work_part = _ensure_work_part()
    r_name = _create_named_expression(work_part, "CYLINDER_R", radius)
    h_name = _create_named_expression(work_part, "CYLINDER_H", height)

    builder = work_part.Features.CreateCylinderBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(x, y, z)
        nx_direction = _create_direction(work_part, origin, _direction_vector(direction))
        builder.Diameter.RightHandSide = f"2 * {r_name}"
        builder.Height.RightHandSide = h_name
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = nx_direction
        feature = builder.Commit()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {
        "ok": True,
        "message": f"Cylinder R{radius} height {height} at ({x},{y},{z})",
    }


def _make_body_collector(work_part, bodies):
    collector = work_part.ScCollectors.CreateCollector()
    rule = work_part.ScRuleFactory.CreateRuleBodyDumb(list(bodies), True)
    _set_collector_rules(collector, [rule])
    return collector


def _set_boolean_inputs(builder, work_part, target_body, tool_bodies):
    tool_body = tool_bodies[0]
    for attr in ("Target", "TargetBody"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, target_body)
                return_attr = attr
                break
            except Exception:
                pass
    else:
        return_attr = None

    for attr in ("Tool", "ToolBody"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, tool_body)
                if return_attr:
                    return
            except Exception:
                pass

    if hasattr(builder, "Targets"):
        try:
            builder.Targets.Add([target_body])
        except Exception:
            pass
    if hasattr(builder, "Tools"):
        try:
            builder.Tools.Add(tool_bodies)
            return
        except Exception:
            pass

    collector = _make_body_collector(work_part, tool_bodies)
    for attr in ("ToolBodyCollector", "ToolCollector"):
        if hasattr(builder, attr):
            try:
                setattr(builder, attr, collector)
                return
            except Exception:
                try:
                    getattr(builder, attr).ReplaceRules(collector.GetRules(), False)
                    return
                except Exception:
                    pass

    boolean_tool = getattr(builder, "BooleanTool", None)
    if boolean_tool is not None:
        for attr in ("BodyCollector", "ToolBodyCollector"):
            if hasattr(boolean_tool, attr):
                try:
                    setattr(boolean_tool, attr, collector)
                    return
                except Exception:
                    pass

    raise SelectionError("Could not assign boolean target/tool bodies with this NXOpen API")


def _boolean_operation(operation, target="last", tool="last"):
    work_part = _ensure_work_part()
    target_body = _resolve_body(target)
    tool_body = _resolve_body(tool)
    if target_body == tool_body:
        raise SelectionError("Boolean target and tool resolve to the same body")

    builder = work_part.Features.CreateBooleanBuilder(
        NXOpen.Features.BooleanFeature.Null
    )
    try:
        operation_name = operation.lower()
        if operation_name == "unite":
            builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        elif operation_name == "subtract":
            builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        else:
            raise SelectionError(f"Unsupported boolean operation: {operation}")

        _set_boolean_inputs(builder, work_part, target_body, [tool_body])
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {
        "ok": True,
        "message": f"Boolean {operation_name}: {_body_name(target_body)} with {_body_name(tool_body)}",
    }


def boolean_unite(target="last", tool="last"):
    return _boolean_operation("unite", target, tool)


def boolean_subtract(target="last", tool="last"):
    return _boolean_operation("subtract", target, tool)


def add_chamfer(offset, body="last", edges="outer_edges"):
    offset = float(offset)
    if offset <= 0.0:
        return {"ok": False, "error": "Chamfer offset must be positive"}

    work_part = _ensure_work_part()
    selected_edges = _resolve_edges(body, edges)
    offset_name = _create_named_expression(work_part, "CHAMFER_OFFSET", offset)

    builder = work_part.Features.CreateChamferBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        builder.Option = NXOpen.Features.ChamferBuilder.ChamferOption.OffsetAndAngle
        builder.Method = NXOpen.Features.ChamferBuilder.OffsetMethod.EdgesAlongFaces
        builder.FirstOffset = offset_name
        builder.SecondOffset = offset_name
        builder.Angle = "45"
        builder.Tolerance = 0.01

        rules = [
            work_part.ScRuleFactory.CreateRuleEdgeTangent(
                edge,
                NXOpen.Edge.Null,
                False,
                0.5,
                False,
            )
            for edge in selected_edges
        ]
        collector = work_part.ScCollectors.CreateCollector()
        _set_collector_rules(collector, rules)
        builder.SmartCollector = collector
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {"ok": True, "message": f"Chamfer {offset}mm on {len(selected_edges)} edges"}


def add_fillet(radius, body="last", edges="outer_edges"):
    radius = float(radius)
    if radius <= 0.0:
        return {"ok": False, "error": "Fillet radius must be positive"}

    work_part = _ensure_work_part()
    selected_edges = _resolve_edges(body, edges)
    r_name = _create_named_expression(work_part, "FILLET_R", radius)

    builder = work_part.Features.CreateEdgeBlendBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        collector = work_part.ScCollectors.CreateCollector()
        rule = work_part.ScRuleFactory.CreateRuleEdgeMultipleSeedTangent(
            selected_edges,
            0.5,
            True,
        )
        _set_collector_rules(collector, [rule])

        builder.Tolerance = 0.01
        builder.AllInstancesOption = False
        builder.RemoveSelfIntersection = True
        builder.ConvexConcaveY = False
        builder.RollOverSmoothEdge = True
        builder.RollOntoEdge = True
        builder.MoveSharpEdge = True
        builder.OverlapOption = NXOpen.Features.EdgeBlendBuilder.Overlap.AnyConvexityRollOver
        builder.BlendOrder = NXOpen.Features.EdgeBlendBuilder.OrderOfBlending.ConvexFirst
        builder.SetbackOption = NXOpen.Features.EdgeBlendBuilder.Setback.SeparateFromCorner
        builder.AddChainset(collector, r_name)
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {"ok": True, "message": f"Fillet R{radius} on {len(selected_edges)} edges"}


def _subtract_cylinder_hole(target_body, x, y, z, diameter, depth, direction):
    work_part = _ensure_work_part()
    d_name = _create_named_expression(work_part, "HOLE_D", diameter)
    depth_name = _create_named_expression(work_part, "HOLE_DEPTH", depth)
    return _subtract_cylinder_hole_parametric(target_body, x, y, z, d_name, depth_name, direction)


def _subtract_cylinder_hole_parametric(target_body, x, y, z, d_name, depth_name, direction):
    work_part = _ensure_work_part()
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        origin = NXOpen.Point3d(x, y, z)
        nx_direction = _create_direction(work_part, origin, _direction_vector(direction))
        builder.Diameter.RightHandSide = d_name
        builder.Height.RightHandSide = depth_name
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = nx_direction
        feature = builder.Commit()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    tool_body = _state.get("last_body")
    _state["last_body"] = target_body
    result = boolean_subtract(_body_name(target_body), _body_name(tool_body))
    if result.get("ok"):
        result["message"] = (
            f"Hole created by subtracting a cylindrical tool body"
        )
    return result


def add_hole(x, y, z, diameter, depth, target="last", direction="-Z", placement_face="top"):
    diameter = float(diameter)
    depth = float(depth)
    if diameter <= 0.0 or depth <= 0.0:
        return {"ok": False, "error": "Hole diameter and depth must be positive"}

    target_body = _resolve_body(target)
    work_part = _ensure_work_part()
    d_name = _create_named_expression(work_part, "HOLE_D", diameter)
    depth_name = _create_named_expression(work_part, "HOLE_DEPTH", depth)

    builder_factory = getattr(work_part.Features, "CreateHoleBuilder", None)
    if not callable(builder_factory):
        return _subtract_cylinder_hole_parametric(target_body, x, y, z, d_name, depth_name, direction)

    builder = builder_factory(NXOpen.Features.Feature.Null)
    try:
        builder.Diameter.RightHandSide = d_name
        builder.Depth.RightHandSide = depth_name

        feature = None
        try:
            point = NXOpen.Point3d(float(x), float(y), float(z))
            if hasattr(builder, "Position"):
                builder.Position = point
            if hasattr(builder, "Direction"):
                builder.Direction = _create_direction(work_part, point, _direction_vector(direction))
            feature = builder.CommitFeature()
        except Exception:
            feature = None

        if feature is None:
            builder.Destroy()
            return _subtract_cylinder_hole_parametric(target_body, x, y, z, d_name, depth_name, direction)

        _remember_feature(feature)
    finally:
        try:
            builder.Destroy()
        except Exception:
            pass

    fit_view()
    return {
        "ok": True,
        "message": f"Hole D={diameter} depth={depth} at ({float(x)},{float(y)},{float(z)}) on {placement_face}",
    }


def revolve(axis="Z", angle_deg=360.0):
    angle_deg = float(angle_deg)
    work_part = _ensure_work_part()
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No curves to revolve"}

    tags = [curve.Tag for curve in curves]
    direction = _vector_components(_direction_vector(axis))
    features, number_of_features = UF_SESSION.Modl.CreateRevolution(
        tags,
        len(tags),
        None,
        ["0", str(angle_deg)],
        ["0", "0"],
        [0.0, 0.0, 0.0],
        False,
        True,
        [0.0, 0.0, 0.0],
        direction,
        NXOpen.UF.Modl.FeatureSigns.NULLSIGN,
    )

    if number_of_features > 0 and features:
        feature = NXOpen.TaggedObjectManager().GetTaggedObject(features[0])
        _remember_feature(feature)
    _state["last_curves"] = []

    fit_view()
    return {"ok": True, "message": f"Revolved {angle_deg} degrees around {axis}"}


def mirror_feature(feature_name="last", plane="XZ"):
    work_part = _ensure_work_part()
    source_feature = _resolve_feature(feature_name)
    datum_builder = work_part.Features.CreateDatumPlaneBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        datum_builder.SetFixedDatumPlane(_fixed_datum_plane_type(plane))
        datum_builder.CommitFeature()
        datum_plane = datum_builder.GetDatum()
    finally:
        datum_builder.Destroy()

    builder = work_part.Features.CreateMirrorFeatureBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        if hasattr(builder, "FeatureSet"):
            builder.FeatureSet.Add([source_feature])
        elif hasattr(builder, "Features"):
            builder.Features.Add([source_feature])
        else:
            raise SelectionError("Mirror builder has no supported feature selection property")

        if hasattr(builder, "PlaneOption"):
            builder.PlaneOption = NXOpen.Features.MirrorFeatureBuilder.PlaneOptions.Existing
        if hasattr(builder, "Plane"):
            builder.Plane.SetValue(
                datum_plane,
                work_part.ModelingViews.WorkView,
                NXOpen.Point3d(0.0, 0.0, 0.0),
            )
        elif hasattr(builder, "MirrorPlane"):
            builder.MirrorPlane = datum_plane
        else:
            raise SelectionError("Mirror builder has no supported mirror plane property")
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {"ok": True, "message": f"Mirrored '{_feature_name(source_feature)}' about {plane}"}


def pattern_feature(feature_name="last", direction="X", count=3, pitch=10.0):
    count = int(count)
    pitch = float(pitch)
    if count < 2:
        return {"ok": False, "error": "Pattern count must be at least 2"}
    if pitch == 0.0:
        return {"ok": False, "error": "Pattern pitch must be non-zero"}

    work_part = _ensure_work_part()
    source_feature = _resolve_feature(feature_name)
    
    count_name = _create_named_expression(work_part, "PATTERN_COUNT", count)
    pitch_name = _create_named_expression(work_part, "PATTERN_PITCH", pitch)

    builder_factory = getattr(work_part.Features, "CreatePatternFeatureBuilder", None)
    if not callable(builder_factory):
        builder_factory = getattr(work_part.Features, "CreateLinearPatternBuilder", None)
    if not callable(builder_factory):
        return {"ok": False, "error": "This NXOpen API has no supported feature pattern builder"}

    builder = builder_factory(NXOpen.Features.Feature.Null)
    try:
        if hasattr(builder, "FeatureList"):
            builder.FeatureList.Add([source_feature])
        elif hasattr(builder, "Features"):
            builder.Features.Add([source_feature])
        elif hasattr(builder, "Feature"):
            builder.Feature = source_feature
        else:
            raise SelectionError("Pattern builder has no supported feature selection property")

        service = getattr(builder, "PatternService", None)
        if service is None:
            raise SelectionError("Pattern builder has no PatternService")
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        nx_direction = _create_direction(work_part, origin, _direction_vector(direction))
        rect = getattr(service, "RectangularDefinition", None)
        if rect is not None:
            rect.XDirection = nx_direction
            rect.UseYDirectionToggle = False
            rect.XSpacing.NCopies.RightHandSide = count_name
            rect.XSpacing.PitchDistance.RightHandSide = pitch_name
        else:
            service.PatternCount.RightHandSide = count_name
            service.Pitch.RightHandSide = pitch_name
            if hasattr(service, "Direction"):
                service.Direction = nx_direction

        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {
        "ok": True,
        "message": f"Pattern '{_feature_name(source_feature)}' {count}x @ {pitch}mm along {direction}",
    }


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
    if tool == "create_cylinder":
        return create_cylinder(
            args.get("radius", 10.0),
            args.get("height", 20.0),
            args.get("x", 0.0),
            args.get("y", 0.0),
            args.get("z", 0.0),
            args.get("direction", "Z"),
        )
    if tool == "create_two_cuboids":
        return create_two_cuboids()
    if tool == "extrude":
        return extrude(args["distance"], args.get("start", 0))
    if tool == "revolve":
        return revolve(args.get("axis", "Z"), args.get("angle_deg", 360.0))
    if tool == "boolean_unite":
        return boolean_unite(args.get("target", "last"), args.get("tool", "last"))
    if tool == "boolean_subtract":
        return boolean_subtract(args.get("target", "last"), args.get("tool", "last"))
    if tool == "add_fillet":
        return add_fillet(
            args["radius"],
            args.get("body", "last"),
            args.get("edges", "outer_edges"),
        )
    if tool == "add_chamfer":
        return add_chamfer(
            args["offset"],
            args.get("body", "last"),
            args.get("edges", "outer_edges"),
        )
    if tool == "add_hole":
        return add_hole(
            args["x"],
            args["y"],
            args["z"],
            args["diameter"],
            args["depth"],
            args.get("target", "last"),
            args.get("direction", "-Z"),
            args.get("placement_face", "top"),
        )
    if tool == "mirror_feature":
        return mirror_feature(args.get("feature_name", "last"), args.get("plane", "XZ"))
    if tool == "pattern_feature":
        return pattern_feature(
            args.get("feature_name", "last"),
            args.get("direction", "X"),
            args.get("count", 3),
            args.get("pitch", 10.0),
        )
    if tool == "edit_expression":
        return edit_expression(args["name"], args["value"])
    if tool == "fit_view":
        return fit_view()

    return {"ok": False, "error": f"Unknown bridge tool: {tool}"}


def edit_expression(name, value):
    work_part = _ensure_work_part()
    try:
        expression = work_part.Expressions.FindObject(name)
    except Exception:
        return {"ok": False, "error": f"Expression '{name}' not found in the work part"}

    session = NXOpen.Session.GetSession()
    undo_mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "Edit Expression")
    expression.RightHandSide = str(value)

    try:
        session.UpdateManager.DoUpdate(undo_mark)
    except Exception as e:
        return {"ok": False, "error": f"Failed to update model after expression change: {e}"}

    # Save the part in place
    try:
        work_part.Save(
            NXOpen.BasePart.SaveComponents.TrueValue,
            NXOpen.BasePart.CloseAfterSave.FalseValue,
        )
    except Exception as e:
        return {"ok": False, "error": f"Failed to save part: {e}"}

    return {"ok": True, "message": f"Expression '{name}' updated to '{value}'"}


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


def run_socket_bridge(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        sys.stderr.write(f"Failed to read live bridge config: {e}\n")
        return

    part_path = config.get("part_path")
    port = config.get("port", 43210)

    if part_path:
        try:
            open_part(part_path)
        except Exception as e:
            sys.stderr.write(f"Failed to open part: {e}\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port))
    server.listen(1)
    server.setblocking(False)

    sys.stderr.write(f"Live bridge socket server listening on port {port}...\n")

    clients = []
    try:
        ui = NXOpen.UI.GetUI()
    except Exception:
        ui = None

    while config_path.exists():
        if ui:
            try:
                ui.ProcessDeviceEvents()
            except Exception:
                pass

        try:
            client_sock, client_addr = server.accept()
            client_sock.setblocking(False)
            clients.append((client_sock, ""))
            sys.stderr.write(f"Connected client: {client_addr}\n")
        except BlockingIOError:
            pass
        except Exception:
            pass

        still_connected = []
        for client_sock, buffer in clients:
            try:
                data = client_sock.recv(4096)
                if not data:
                    client_sock.close()
                    continue
                buffer += data.decode("utf-8")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    result = handle_line(line)
                    response = json.dumps(result) + "\n"
                    client_sock.sendall(response.encode("utf-8"))

                still_connected.append((client_sock, buffer))
            except BlockingIOError:
                still_connected.append((client_sock, buffer))
            except Exception as e:
                sys.stderr.write(f"Error handling client: {e}\n")
                try:
                    client_sock.close()
                except Exception:
                    pass

        clients = still_connected
        time.sleep(0.01)

    server.close()


def main():
    config_path = Path("C:/Users/HP/nx-mcp/live_bridge_config.json")
    if config_path.exists():
        run_socket_bridge(config_path)
    else:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            result = handle_line(line)
            sys.stdout.write(json.dumps(result) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
