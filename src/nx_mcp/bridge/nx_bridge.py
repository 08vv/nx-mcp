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
    "sketches": {},
    "active_sketch": None,
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


def _resolve_direction(direction):
    ref = str(direction or "auto").strip().lower()
    if ref == "auto":
        if ACTIVE_SKETCH_PLANE == "XY":
            return "Z"
        if ACTIVE_SKETCH_PLANE == "XZ":
            return "Y"
        return "X"
    return direction


def _resolve_hole_direction(direction):
    ref = str(direction or "auto").strip().lower()
    if ref == "auto":
        if ACTIVE_SKETCH_PLANE == "XY":
            return "-Z"
        if ACTIVE_SKETCH_PLANE == "XZ":
            return "-Y"
        return "-X"
    return direction


def _resolve_revolve_axis(axis):
    ref = str(axis or "auto").strip().lower()
    if ref == "auto":
        if ACTIVE_SKETCH_PLANE == "XY":
            return "Y"
        if ACTIVE_SKETCH_PLANE == "XZ":
            return "Z"
        return "Z"
    return axis


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

    try:
        (min_x, min_y, min_z), (max_x, max_y, max_z) = _body_bounds(body)
    except Exception:
        min_x = min_y = min_z = -999999.0
        max_x = max_y = max_z = 999999.0

    def get_edge_endpoints(edge):
        try:
            pt1, pt2, _ = UF_SESSION.Modeling.AskEdgeVerts(edge.Tag)
            p1 = _point_tuple(pt1)
            p2 = _point_tuple(pt2)
            return p1, p2
        except Exception:
            return None, None

    if ref in {"x_edges", "x_aligned", "x_aligned_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2:
                dx = abs(p2[0] - p1[0])
                dy = abs(p2[1] - p1[1])
                dz = abs(p2[2] - p1[2])
                if dx > 0.001 and dy < 0.001 and dz < 0.001:
                    selected.append(edge)
        return selected

    if ref in {"y_edges", "y_aligned", "y_aligned_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2:
                dx = abs(p2[0] - p1[0])
                dy = abs(p2[1] - p1[1])
                dz = abs(p2[2] - p1[2])
                if dy > 0.001 and dx < 0.001 and dz < 0.001:
                    selected.append(edge)
        return selected

    if ref in {"z_edges", "z_aligned", "z_aligned_edges", "vertical", "vertical_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2:
                dx = abs(p2[0] - p1[0])
                dy = abs(p2[1] - p1[1])
                dz = abs(p2[2] - p1[2])
                if dz > 0.001 and dx < 0.001 and dy < 0.001:
                    selected.append(edge)
        if not selected and ref in {"vertical", "vertical_edges"}:
            for edge in edges:
                p1, p2 = get_edge_endpoints(edge)
                if p1 and p2 and abs(p2[2] - p1[2]) > 0.001:
                    selected.append(edge)
        return selected

    if ref in {"top", "top_edges", "max_z", "max_z_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[2] - max_z) < 0.001 and abs(p2[2] - max_z) < 0.001:
                selected.append(edge)
        return selected

    if ref in {"bottom", "bottom_edges", "min_z", "min_z_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[2] - min_z) < 0.001 and abs(p2[2] - min_z) < 0.001:
                selected.append(edge)
        return selected

    if ref in {"max_x", "max_x_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[0] - max_x) < 0.001 and abs(p2[0] - max_x) < 0.001:
                selected.append(edge)
        return selected

    if ref in {"min_x", "min_x_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[0] - min_x) < 0.001 and abs(p2[0] - min_x) < 0.001:
                selected.append(edge)
        return selected

    if ref in {"max_y", "max_y_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[1] - max_y) < 0.001 and abs(p2[1] - max_y) < 0.001:
                selected.append(edge)
        return selected

    if ref in {"min_y", "min_y_edges"}:
        selected = []
        for edge in edges:
            p1, p2 = get_edge_endpoints(edge)
            if p1 and p2 and abs(p1[1] - min_y) < 0.001 and abs(p2[1] - min_y) < 0.001:
                selected.append(edge)
        return selected

    raise SelectionError(f"Could not resolve edge reference: {edge_reference}")


def _direction_vector(direction):
    direction = _resolve_direction(direction)
    ref = str(direction).strip().upper()
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


def _update_result_files(filepath):
    try:
        import os
        abs_path = os.path.abspath(filepath)
        root = "C:\\Users\\HP\\nx-mcp"
        if os.path.exists(root):
            latest_txt = os.path.join(root, "latest_nx_result.txt")
            with open(latest_txt, "w", encoding="utf-8") as f:
                f.write(abs_path)
            cmd_path = os.path.join(root, "open_current_nx_result.cmd")
            with open(cmd_path, "w", encoding="utf-8") as f:
                f.write(f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{abs_path}"\n')
            vbs_path = os.path.join(root, "open_latest_nx_result.vbs")
            with open(vbs_path, "w", encoding="utf-8") as f:
                f.write(f'Set shell = CreateObject("WScript.Shell")\nshell.Run """C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe"" -ug -use_file_dir ""{abs_path}""", 0, False\n')
    except Exception:
        pass


def create_part(filename):
    SESSION.Parts.NewDisplay(
        filename,
        NXOpen.Part.Units.Millimeters,
    )
    work_part = SESSION.Parts.Work
    if work_part is None:
        return {"ok": False, "error": "Part created but work part not set"}
    fit_view()
    import os
    filepath = os.path.abspath(filename)
    _update_result_files(filepath)
    return {"ok": True, "message": f"Created and displayed: {filename}", "filepath": filepath}


def open_part(filepath):
    try:
        # OpenDisplay opens the part AND makes it the active display/work part
        SESSION.Parts.OpenDisplay(filepath)
    except Exception:
        # Fallback for NX versions where OpenDisplay signature differs
        SESSION.Parts.Open(filepath)
    fit_view()
    work_part = SESSION.Parts.Work
    import os
    actual_path = os.path.abspath(work_part.FullPath if work_part else filepath)
    _update_result_files(actual_path)
    return {"ok": True, "message": f"Opened and displayed: {filepath}", "filepath": actual_path}


def save_part():
    work_part = SESSION.Parts.Work
    if work_part is None:
        return {"ok": False, "error": "No work part is open"}
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    import os
    filepath = os.path.abspath(work_part.FullPath)
    _update_result_files(filepath)
    return {"ok": True, "message": "Saved", "filepath": filepath}


def create_sketch(plane="XY"):
    global ACTIVE_SKETCH_PLANE

    plane = plane.upper()
    if plane not in {"XY", "XZ", "YZ"}:
        return {"ok": False, "error": f"Invalid sketch plane: {plane}"}

    _ensure_work_part()

    ACTIVE_SKETCH_PLANE = plane
    _state["last_curves"] = []
    _state["active_sketch"] = None
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
    active_sketch = _state.get("active_sketch")
    for index in range(4):
        line = part.Curves.CreateLine(
            _point_on_active_plane(corners[index][0], corners[index][1]),
            _point_on_active_plane(corners[index + 1][0], corners[index + 1][1]),
        )
        lines.append(line)
        if active_sketch is not None:
            try:
                active_sketch.AddGeometry(line, NXOpen.Sketch.ConstraintClass.Geometrical)
            except Exception:
                try:
                    active_sketch.AddGeometry(line)
                except Exception:
                    pass
    _state.setdefault("last_curves", []).extend(lines)
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
    active_sketch = _state.get("active_sketch")
    if active_sketch is not None:
        try:
            active_sketch.AddGeometry(circle, NXOpen.Sketch.ConstraintClass.Geometrical)
        except Exception:
            try:
                active_sketch.AddGeometry(circle)
            except Exception:
                pass
    _state.setdefault("last_curves", []).append(circle)
    fit_view()
    return {"ok": True, "message": f"Circle {cx},{cy} R={radius}"}


def draw_line(x1, y1, x2, y2):
    x1 = float(x1)
    y1 = float(y1)
    x2 = float(x2)
    y2 = float(y2)

    part = _ensure_work_part()
    line = part.Curves.CreateLine(
        _point_on_active_plane(x1, y1),
        _point_on_active_plane(x2, y2),
    )
    active_sketch = _state.get("active_sketch")
    if active_sketch is not None:
        try:
            active_sketch.AddGeometry(line, NXOpen.Sketch.ConstraintClass.Geometrical)
        except Exception:
            try:
                active_sketch.AddGeometry(line)
            except Exception:
                pass
    _state.setdefault("last_curves", []).append(line)
    fit_view()
    return {"ok": True, "message": f"Line {x1},{y1} to {x2},{y2}"}


def draw_arc(cx, cy, radius, start_angle, end_angle):
    cx = float(cx)
    cy = float(cy)
    radius = float(radius)
    start_angle = float(start_angle)
    end_angle = float(end_angle)

    if radius <= 0.0:
        return {"ok": False, "error": "Arc radius must be positive"}

    part = _ensure_work_part()
    arc = part.Curves.CreateArc(
        _point_on_active_plane(cx, cy),
        _normal_for_active_plane(),
        radius,
        math.radians(start_angle),
        math.radians(end_angle),
    )
    active_sketch = _state.get("active_sketch")
    if active_sketch is not None:
        try:
            active_sketch.AddGeometry(arc, NXOpen.Sketch.ConstraintClass.Geometrical)
        except Exception:
            try:
                active_sketch.AddGeometry(arc)
            except Exception:
                pass
    _state.setdefault("last_curves", []).append(arc)
    fit_view()
    return {"ok": True, "message": f"Arc {cx},{cy} R={radius} {start_angle} to {end_angle} deg"}


def draw_cylinder_profile(outer_radius, inner_radius):
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


def extrude(distance, start=0, direction="auto"):
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
    resolved_dir = _resolve_direction(direction)
    dir_vec = _direction_vector(resolved_dir)
    origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    builder.Direction = work_part.Directions.CreateDirection(
        origin,
        dir_vec,
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


def add_hole(x, y, z, diameter, depth, target="last", direction="auto", placement_face="top"):
    diameter = float(diameter)
    depth = float(depth)
    if diameter <= 0.0 or depth <= 0.0:
        return {"ok": False, "error": "Hole diameter and depth must be positive"}

    target_body = _resolve_body(target)
    work_part = _ensure_work_part()
    d_name = _create_named_expression(work_part, "HOLE_D", diameter)
    depth_name = _create_named_expression(work_part, "HOLE_DEPTH", depth)

    resolved_dir = _resolve_hole_direction(direction)

    builder_factory = getattr(work_part.Features, "CreateHoleBuilder", None)
    if not callable(builder_factory):
        return _subtract_cylinder_hole_parametric(target_body, x, y, z, d_name, depth_name, resolved_dir)

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
                builder.Direction = _create_direction(work_part, point, _direction_vector(resolved_dir))
            feature = builder.CommitFeature()
        except Exception:
            feature = None

        if feature is None:
            builder.Destroy()
            return _subtract_cylinder_hole_parametric(target_body, x, y, z, d_name, depth_name, resolved_dir)

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


def revolve(axis="auto", angle_deg=360.0):
    angle_deg = float(angle_deg)
    work_part = _ensure_work_part()
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No curves to revolve"}

    resolved_axis = _resolve_revolve_axis(axis)

    tags = [curve.Tag for curve in curves]
    direction = _vector_components(_direction_vector(resolved_axis))
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
    return {"ok": True, "message": f"Revolved {angle_deg} degrees around {resolved_axis}"}


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



# ---------------------------------------------------------------------------
# NEW TOOLS: create_real_sketch, extrude_from_sketch, add_hole_nx,
#            create_rib, pattern_circular, edge_blend, chamfer_edges,
#            revolve_cut, extrude_cut
# ---------------------------------------------------------------------------


def create_real_sketch(plane="XY"):
    """Create a proper constrained NX Sketch object on a datum plane.

    The sketch is stored in _state["sketches"][plane] and made the active
    sketch so that subsequent draw_* calls populate it.  Falls back to the
    existing lightweight plane-reference if SketchInPlaceBuilder is absent.
    """
    global ACTIVE_SKETCH_PLANE

    plane = str(plane or "XY").strip().upper()
    if plane not in {"XY", "XZ", "YZ"}:
        return {"ok": False, "error": f"Invalid sketch plane: {plane}"}

    work_part = _ensure_work_part()
    ACTIVE_SKETCH_PLANE = plane

    # --- Try the modern SketchInPlaceBuilder path ---
    builder_factory = getattr(work_part.Sketches, "CreateNewSketch", None)
    if not callable(builder_factory):
        builder_factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder", None)

    if callable(builder_factory):
        try:
            # Build a datum plane to attach the sketch to
            datum_builder = work_part.Features.CreateDatumPlaneBuilder(
                NXOpen.Features.Feature.Null
            )
            try:
                datum_builder.SetFixedDatumPlane(_fixed_datum_plane_type(plane))
                datum_builder.CommitFeature()
                datum_plane = datum_builder.GetDatum()
            finally:
                datum_builder.Destroy()

            # Create sketch on that datum plane
            sketch_builder = builder_factory(NXOpen.Features.Feature.Null)
            try:
                # API varies: PlaneReference or PlacementFace
                for attr in ("PlaneReference", "PlacementFace", "SketchOrigin"):
                    if hasattr(sketch_builder, attr):
                        try:
                            setattr(sketch_builder, attr, datum_plane)
                            break
                        except Exception:
                            pass
                feature = sketch_builder.CommitFeature()
            finally:
                sketch_builder.Destroy()

            _remember_feature(feature)
            sketch_name = _feature_name(feature)
            _state["sketches"][plane] = feature
            _state["sketches"][sketch_name.lower()] = feature
            _state["active_sketch"] = feature
            # Reset last_curves so next draw_* accumulates into fresh set
            _state["last_curves"] = []
            fit_view()
            return {"ok": True, "message": f"Sketch created on {plane} plane (id={sketch_name})"}
        except Exception as e:
            # Fall through to lightweight path
            pass

    # --- Lightweight fallback: just track the plane reference ---
    _state["last_curves"] = []
    _state["active_sketch"] = None
    fit_view()
    return {"ok": True, "message": f"Sketch created on {plane} plane"}


def extrude_from_sketch(sketch_name="last", distance=10.0, start=0.0, direction="auto"):
    distance = float(distance)
    start = float(start)
    work_part = _ensure_work_part()

    dist_name = _create_named_expression(work_part, "EXTRUDE_DIST", distance)
    start_name = _create_named_expression(work_part, "EXTRUDE_START", start)

    # Try resolving real sketch feature curves if sketch_name is specified
    curves = []
    sketch_feature = None
    if sketch_name and sketch_name.lower() != "last":
        try:
            sketch_feature = _resolve_feature(sketch_name)
        except Exception:
            pass

    if sketch_feature is not None:
        sketch_obj = None
        if hasattr(sketch_feature, "GetAllGeometry"):
            sketch_obj = sketch_feature
        elif hasattr(sketch_feature, "Sketch"):
            sketch_obj = sketch_feature.Sketch
        
        if sketch_obj is not None:
            try:
                curves = list(sketch_obj.GetAllGeometry() or [])
            except Exception:
                pass

    if not curves:
        curves = _state.get("last_curves", [])

    if not curves:
        return {"ok": False, "error": "No curves to extrude — draw a profile first"}

    builder = work_part.Features.CreateExtrudeBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rules = [
            work_part.ScRuleFactory.CreateRuleCurveDumb([c])
            for c in curves
        ]
        section.AddToSection(
            rules, curves[0],
            NXOpen.NXObject.Null,
            NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create,
            False,
        )
        builder.Section = section

        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        resolved_dir = _resolve_direction(direction)
        nx_dir = _create_direction(work_part, origin, _direction_vector(resolved_dir))
        builder.Direction = nx_dir
        builder.Limits.StartExtend.Value.RightHandSide = start_name
        builder.Limits.EndExtend.Value.RightHandSide = dist_name
        builder.BooleanOperation.Type = NXOpen.Features.Feature.BooleanType.Create

        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    _state["last_curves"] = []
    fit_view()
    return {"ok": True, "message": f"Extruded sketch '{sketch_name}' {distance}mm along {resolved_dir}"}


def add_hole_nx(
    x, y, z, diameter, depth,
    target="last", direction="auto", hole_type="simple"
):
    """Proper NX HoleBuilder: simple hole at (x,y,z) with diameter and depth.

    Uses CreateHoleBuilder with SimpleHole type and full parametric expressions.
    Falls back to cylinder-subtract if HoleBuilder is not available.
    """
    diameter = float(diameter)
    depth = float(depth)
    if diameter <= 0.0 or depth <= 0.0:
        return {"ok": False, "error": "Hole diameter and depth must be positive"}

    target_body = _resolve_body(target)
    work_part = _ensure_work_part()
    d_name = _create_named_expression(work_part, "HOLE_D", diameter)
    depth_name = _create_named_expression(work_part, "HOLE_DEPTH", depth)

    resolved_dir = _resolve_hole_direction(direction)

    builder_factory = getattr(work_part.Features, "CreateHoleBuilder", None)
    if not callable(builder_factory):
        return _subtract_cylinder_hole_parametric(
            target_body, x, y, z, d_name, depth_name, resolved_dir
        )

    builder = builder_factory(NXOpen.Features.Feature.Null)
    try:
        # Set hole type to simple
        for attr in ("Type", "HoleType"):
            if hasattr(builder, attr):
                try:
                    simple_val = getattr(
                        type(builder),
                        attr,
                        None
                    )
                    # Try to set the Simple enum value
                    type_enum = getattr(builder, attr + "s", None) or getattr(builder, attr)
                    simple = getattr(type_enum, "Simple",
                               getattr(type_enum, "GeneralHole", None))
                    if simple is not None:
                        setattr(builder, attr, simple)
                    break
                except Exception:
                    pass

        builder.Diameter.RightHandSide = d_name
        # Depth attribute name varies by NX release
        for depth_attr in ("Depth", "HoleDepth", "TipDepth"):
            if hasattr(builder, depth_attr):
                try:
                    getattr(builder, depth_attr).RightHandSide = depth_name
                    break
                except Exception:
                    pass

        point = NXOpen.Point3d(float(x), float(y), float(z))
        if hasattr(builder, "Position"):
            try:
                builder.Position = point
            except Exception:
                pass
        if hasattr(builder, "Direction"):
            try:
                builder.Direction = _create_direction(
                    work_part, point, _direction_vector(resolved_dir)
                )
            except Exception:
                pass

        # Target body for boolean
        for attr in ("Target", "TargetBody", "BooleanOperation"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body)
                    break
                except Exception:
                    pass

        try:
            feature = builder.CommitFeature()
        except Exception:
            builder.Destroy()
            return _subtract_cylinder_hole_parametric(
                target_body, x, y, z, d_name, depth_name, resolved_dir
            )

        _remember_feature(feature)
    finally:
        try:
            builder.Destroy()
        except Exception:
            pass

    fit_view()
    return {
        "ok": True,
        "message": (
            f"Hole D={diameter} depth={depth} at "
            f"({float(x):.3f},{float(y):.3f},{float(z):.3f})"
        ),
    }


def create_rib(thickness, direction="auto", body="last", flip=False):
    """Create a rib/web feature from the active sketch profile.

    Uses CreateRibBuilder when available.  Falls back to a thin solid extrude
    (half thickness each side) united with the target body.
    """
    thickness = float(thickness)
    if thickness <= 0.0:
        return {"ok": False, "error": "Rib thickness must be positive"}

    work_part = _ensure_work_part()
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No profile curves — draw a rib profile first"}

    t_name = _create_named_expression(work_part, "RIB_T", thickness)
    half_t = thickness / 2.0
    half_t_name = _create_named_expression(work_part, "RIB_HALF_T", half_t)

    resolved_dir = _resolve_direction(direction)

    # --- Try native RibBuilder ---
    rib_factory = getattr(work_part.Features, "CreateRibBuilder", None)
    if callable(rib_factory):
        try:
            builder = rib_factory(NXOpen.Features.Feature.Null)
            try:
                section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
                rules = [
                    work_part.ScRuleFactory.CreateRuleCurveDumb([c])
                    for c in curves
                ]
                section.AddToSection(
                    rules, curves[0],
                    NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                    NXOpen.Point3d(0.0, 0.0, 0.0),
                    NXOpen.Section.Mode.Create, False,
                )

                if hasattr(builder, "Section"):
                    builder.Section = section
                elif hasattr(builder, "Profile"):
                    builder.Profile = section

                # Thickness
                for attr in ("Thickness", "Width"):
                    if hasattr(builder, attr):
                        try:
                            getattr(builder, attr).RightHandSide = t_name
                            break
                        except Exception:
                            pass

                # Direction / extrude direction
                origin = NXOpen.Point3d(0.0, 0.0, 0.0)
                nx_dir = _create_direction(work_part, origin, _direction_vector(resolved_dir))
                for attr in ("ExtrudeDirection", "Direction", "ThicknessDirection"):
                    if hasattr(builder, attr):
                        try:
                            setattr(builder, attr, nx_dir)
                            break
                        except Exception:
                            pass

                if flip and hasattr(builder, "ReverseDirection"):
                    builder.ReverseDirection = True

                feature = builder.CommitFeature()
                _remember_feature(feature)
            finally:
                builder.Destroy()

            _state["last_curves"] = []
            fit_view()
            return {"ok": True, "message": f"Rib T={thickness}mm along {resolved_dir}"}
        except Exception:
            pass  # fall through to fallback

    # --- Fallback: thin extrude symmetrical about the profile plane ---
    target_body_ref = _state.get("last_body")

    builder = work_part.Features.CreateExtrudeBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rules = [
            work_part.ScRuleFactory.CreateRuleCurveDumb([c])
            for c in curves
        ]
        section.AddToSection(
            rules, curves[0],
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False,
        )
        builder.Section = section
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        nx_dir = _create_direction(work_part, origin, _direction_vector(resolved_dir))
        builder.Direction = nx_dir
        # Symmetric: -half_t to +half_t
        builder.Limits.StartExtend.Value.RightHandSide = f"-{half_t_name}"
        builder.Limits.EndExtend.Value.RightHandSide = half_t_name

        if target_body_ref is not None:
            try:
                builder.BooleanOperation.Type = (
                    NXOpen.Features.Feature.BooleanType.Unite
                )
                builder.BooleanOperation.SetTarget(target_body_ref)
            except Exception:
                pass
        else:
            builder.BooleanOperation.Type = (
                NXOpen.Features.Feature.BooleanType.Create
            )

        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    _state["last_curves"] = []
    fit_view()
    return {"ok": True, "message": f"Rib T={thickness}mm (extrude fallback) along {resolved_dir}"}


def pattern_circular(
    feature_name="last", axis="auto", count=4, angle_total=360.0
):
    """Circular pattern of a feature: count instances over angle_total degrees."""
    count = int(count)
    angle_total = float(angle_total)
    if count < 2:
        return {"ok": False, "error": "Circular pattern count must be at least 2"}
    if angle_total == 0.0:
        return {"ok": False, "error": "angle_total must be non-zero"}

    work_part = _ensure_work_part()
    source_feature = _resolve_feature(feature_name)

    count_name = _create_named_expression(work_part, "CIRC_PAT_COUNT", count)
    angle_name = _create_named_expression(work_part, "CIRC_PAT_ANGLE", angle_total)

    resolved_axis = _resolve_direction(axis)

    builder_factory = getattr(work_part.Features, "CreatePatternFeatureBuilder", None)
    if not callable(builder_factory):
        return {"ok": False, "error": "CreatePatternFeatureBuilder not available in this NX version"}

    builder = builder_factory(NXOpen.Features.Feature.Null)
    try:
        # Add source feature
        if hasattr(builder, "FeatureList"):
            builder.FeatureList.Add([source_feature])
        elif hasattr(builder, "Features"):
            builder.Features.Add([source_feature])
        elif hasattr(builder, "Feature"):
            builder.Feature = source_feature
        else:
            raise SelectionError("Pattern builder has no supported feature property")

        service = getattr(builder, "PatternService", None)
        if service is None:
            raise SelectionError("Pattern builder has no PatternService")

        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        nx_dir = _create_direction(work_part, origin, _direction_vector(resolved_axis))

        # Try CircularDefinition first (NX 10+)
        circ = getattr(service, "CircularDefinition", None)
        if circ is not None:
            circ.RotationDirection = nx_dir
            circ.NCopies.RightHandSide = count_name
            circ.PitchAngle.RightHandSide = f"{angle_name} / ({count_name} - 1)"
            if hasattr(service, "PatternType"):
                try:
                    service.PatternType = getattr(
                        type(service).PatternType,
                        "Circular",
                        service.PatternType
                    )
                except Exception:
                    pass
        else:
            # Fallback: rectangular service with only X populated
            rect = getattr(service, "RectangularDefinition", None)
            if rect is not None:
                rect.XDirection = nx_dir
                rect.UseYDirectionToggle = False
                rect.XSpacing.NCopies.RightHandSide = count_name
                # pitch = total_angle / (count-1) as angular — use numeric
                pitch_deg = angle_total / max(count - 1, 1)
                pitch_name = _create_named_expression(
                    work_part, "CIRC_PAT_PITCH_DEG", pitch_deg
                )
                rect.XSpacing.PitchDistance.RightHandSide = pitch_name
            else:
                service.PatternCount.RightHandSide = count_name
                if hasattr(service, "Direction"):
                    service.Direction = nx_dir

        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    fit_view()
    return {
        "ok": True,
        "message": (
            f"Circular pattern '{_feature_name(source_feature)}' "
            f"{count}x over {angle_total}° about {resolved_axis}"
        ),
    }


def edge_blend(radius, body="last", edges="outer_edges"):
    """Fillet edges by semantic selection — thin wrapper over add_fillet."""
    return add_fillet(radius, body, edges)


def chamfer_edges(offset, body="last", edges="outer_edges"):
    """Chamfer edges by semantic selection — thin wrapper over add_chamfer."""
    return add_chamfer(offset, body, edges)


def revolve_cut(axis="auto", angle_deg=360.0, target="last"):
    """Revolve active sketch profile around axis to CUT/remove material.

    Uses CreateRevolveBuilder with BooleanType.Subtract.
    Falls back to: revolve() to create a solid, then boolean_subtract.
    """
    angle_deg = float(angle_deg)
    work_part = _ensure_work_part()
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No curves to revolve-cut — draw a profile first"}

    target_body = _resolve_body(target)
    angle_name = _create_named_expression(work_part, "REVOLVE_CUT_ANGLE", angle_deg)
    resolved_axis = _resolve_revolve_axis(axis)

    # --- Try modern CreateRevolveBuilder path ---
    builder_factory = getattr(work_part.Features, "CreateRevolveBuilder", None)
    if callable(builder_factory):
        try:
            builder = builder_factory(NXOpen.Features.Feature.Null)
            try:
                section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
                rules = [
                    work_part.ScRuleFactory.CreateRuleCurveDumb([c])
                    for c in curves
                ]
                section.AddToSection(
                    rules, curves[0],
                    NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                    NXOpen.Point3d(0.0, 0.0, 0.0),
                    NXOpen.Section.Mode.Create, False,
                )
                builder.Section = section

                origin = NXOpen.Point3d(0.0, 0.0, 0.0)
                nx_dir = _direction_vector(resolved_axis)
                revolve_axis_obj = _create_axis(work_part, origin, nx_dir)
                builder.Axis = revolve_axis_obj

                builder.Limits.StartExtend.Value.RightHandSide = "0"
                builder.Limits.EndExtend.Value.RightHandSide = angle_name

                builder.BooleanOperation.Type = (
                    NXOpen.Features.Feature.BooleanType.Subtract
                )
                try:
                    builder.BooleanOperation.SetTarget(target_body)
                except Exception:
                    pass

                feature = builder.CommitFeature()
                _remember_feature(feature)
            finally:
                builder.Destroy()

            _state["last_curves"] = []
            fit_view()
            return {"ok": True, "message": f"Revolve-cut {angle_deg}° about {resolved_axis}"}
        except Exception:
            pass  # fall through to UF path + subtract

    # --- Fallback: revolve to solid then boolean subtract ---
    revolve_result = revolve(resolved_axis, angle_deg)
    if not revolve_result.get("ok"):
        return revolve_result
    cut_body = _state.get("last_body")
    if cut_body is None:
        return {"ok": False, "error": "Revolve succeeded but no body was recorded for subtraction"}
    _state["last_body"] = target_body
    result = boolean_subtract(_body_name(target_body), _body_name(cut_body))
    if result.get("ok"):
        result["message"] = f"Revolve-cut {angle_deg}° about {resolved_axis}"
    return result


def extrude_cut(distance, start=0.0, target="last", direction="auto"):
    """Extrude active sketch profile to CUT/remove material from target body.

    Uses CreateExtrudeBuilder with BooleanType.Subtract.
    """
    distance = float(distance)
    start = float(start)
    if distance <= 0.0:
        return {"ok": False, "error": "Extrude-cut distance must be positive"}

    work_part = _ensure_work_part()
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No curves to extrude-cut — draw a profile first"}

    target_body = _resolve_body(target)
    dist_name = _create_named_expression(work_part, "EXTRUDE_CUT_DIST", distance)
    start_name = _create_named_expression(work_part, "EXTRUDE_CUT_START", start)

    builder = work_part.Features.CreateExtrudeBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
        rules = [
            work_part.ScRuleFactory.CreateRuleCurveDumb([c])
            for c in curves
        ]
        section.AddToSection(
            rules, curves[0],
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False,
        )
        builder.Section = section

        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        nx_dir = _create_direction(work_part, origin, _direction_vector(direction))
        builder.Direction = nx_dir
        builder.Limits.StartExtend.Value.RightHandSide = start_name
        builder.Limits.EndExtend.Value.RightHandSide = dist_name

        builder.BooleanOperation.Type = (
            NXOpen.Features.Feature.BooleanType.Subtract
        )
        try:
            builder.BooleanOperation.SetTarget(target_body)
        except Exception:
            pass

        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()

    _state["last_curves"] = []
    fit_view()
    return {
        "ok": True,
        "message": f"Extrude-cut {distance}mm from '{_body_name(target_body)}' along {direction}",
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
    if tool == "draw_line":
        return draw_line(args["x1"], args["y1"], args["x2"], args["y2"])
    if tool == "draw_arc":
        return draw_arc(args["cx"], args["cy"], args["radius"], args["start_angle"], args["end_angle"])
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
        return extrude(args["distance"], args.get("start", 0), args.get("direction", "auto"))
    if tool == "revolve":
        return revolve(args.get("axis", "auto"), args.get("angle_deg", 360.0))
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
            args.get("direction", "auto"),
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
    # --- New tools ---
    if tool == "create_real_sketch":
        return create_real_sketch(args.get("plane", "XY"))
    if tool == "extrude_from_sketch":
        return extrude_from_sketch(
            args.get("sketch_name", "last"),
            args.get("distance", 10.0),
            args.get("start", 0.0),
            args.get("direction", "auto"),
        )
    if tool == "add_hole_nx":
        return add_hole_nx(
            args["x"], args["y"], args["z"],
            args["diameter"], args["depth"],
            args.get("target", "last"),
            args.get("direction", "auto"),
            args.get("hole_type", "simple"),
        )
    if tool == "create_rib":
        return create_rib(
            args["thickness"],
            args.get("direction", "auto"),
            args.get("body", "last"),
            args.get("flip", False),
        )
    if tool == "pattern_circular":
        return pattern_circular(
            args.get("feature_name", "last"),
            args.get("axis", "auto"),
            args.get("count", 4),
            args.get("angle_total", 360.0),
        )
    if tool == "edge_blend":
        return edge_blend(
            args["radius"],
            args.get("body", "last"),
            args.get("edges", "outer_edges"),
        )
    if tool == "chamfer_edges":
        return chamfer_edges(
            args["offset"],
            args.get("body", "last"),
            args.get("edges", "outer_edges"),
        )
    if tool == "revolve_cut":
        return revolve_cut(
            args.get("axis", "auto"),
            args.get("angle_deg", 360.0),
            args.get("target", "last"),
        )
    if tool == "extrude_cut":
        return extrude_cut(
            args["distance"],
            args.get("start", 0.0),
            args.get("target", "last"),
            args.get("direction", "auto"),
        )

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
