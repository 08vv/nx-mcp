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


def _resolve_face_by_coordinate(body_reference="last", x=0.0, y=0.0, z=0.0):
    body = _resolve_body(body_reference)
    faces = list(body.GetFaces() or [])
    if not faces:
        raise SelectionError(f"No faces found on body: {body_reference}")
    best_face = None
    min_dist = 999999.0
    for face in faces:
        try:
            face_type, origin, direction, bbox, radius, flag1, flag2 = UF_SESSION.Modl.AskFaceData(face.Tag)
            pt = _point_tuple(origin)
            dist = math.sqrt((pt[0]-x)**2 + (pt[1]-y)**2 + (pt[2]-z)**2)
            if dist < min_dist:
                min_dist = dist
                best_face = face
        except Exception:
            if best_face is None:
                best_face = face
    return best_face


def _resolve_edge_by_coordinate(body_reference="last", x=0.0, y=0.0, z=0.0):
    body = _resolve_body(body_reference)
    edges = list(body.GetEdges() or [])
    if not edges:
        raise SelectionError(f"No edges found on body: {body_reference}")
    best_edge = None
    min_dist = 999999.0
    for edge in edges:
        try:
            pt = _edge_midpoint(edge)
            dist = math.sqrt((pt[0]-x)**2 + (pt[1]-y)**2 + (pt[2]-z)**2)
            if dist < min_dist:
                min_dist = dist
                best_edge = edge
        except Exception:
            if best_edge is None:
                best_edge = edge
    return best_edge


def _resolve_curves(reference="last"):
    ref = str(reference or "last").strip().lower()
    if ref in {"last", "last_curves", "previous_curves"}:
        return _state.get("last_curves", [])
    if ref in _state["sketches"]:
        sketch_feature = _state["sketches"][ref]
        try:
            if hasattr(sketch_feature, "GetAllGeometry"):
                return list(sketch_feature.GetAllGeometry() or [])
            if hasattr(sketch_feature, "Sketch") and hasattr(sketch_feature.Sketch, "GetAllGeometry"):
                return list(sketch_feature.Sketch.GetAllGeometry() or [])
        except Exception:
            pass
    try:
        feature = _resolve_feature(reference)
        if hasattr(feature, "GetAllGeometry"):
            return list(feature.GetAllGeometry() or [])
        if hasattr(feature, "Sketch") and hasattr(feature.Sketch, "GetAllGeometry"):
            return list(feature.Sketch.GetAllGeometry() or [])
    except Exception:
        pass
    return _state.get("last_curves", [])


def _build_section_from_curves(work_part, curves):
    section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
    rules = [work_part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    if curves:
        section.AddToSection(
            rules, curves[0],
            NXOpen.NXObject.Null, NXOpen.NXObject.Null,
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Section.Mode.Create, False
        )
    return section


def _execute_surface_builder(builder_name, config_fn, success_message):
    work_part = _ensure_work_part()
    builder_factory = getattr(work_part.Features, builder_name, None)
    if not callable(builder_factory):
        for attr in dir(work_part.Features):
            if attr.lower() == builder_name.lower():
                builder_factory = getattr(work_part.Features, attr)
                break
    if not callable(builder_factory):
        return {"ok": False, "error": f"NXOpen Features has no builder: {builder_name}"}
    builder = builder_factory(NXOpen.Features.Feature.Null)
    try:
        config_fn(builder, work_part)
        commit_method = getattr(builder, "CommitFeature", None) or getattr(builder, "Commit", None)
        if callable(commit_method):
            feature = commit_method()
            if feature:
                _remember_feature(feature)
        else:
            raise RuntimeError(f"Builder {builder_name} has no Commit or CommitFeature method")
    except Exception as e:
        return {"ok": False, "error": f"Failed executing {builder_name}: {str(e)}"}
    finally:
        builder.Destroy()
    fit_view()
    return {"ok": True, "message": success_message}


def create_base_surface(plane="XY", width=50.0, height=50.0):
    width = float(width)
    height = float(height)
    work_part = _ensure_work_part()
    create_sketch(plane)
    draw_rectangle(-width/2, -height/2, width, height)
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "Failed to create curves for base surface"}
    def config(builder, wp):
        builder.Section = _build_section_from_curves(wp, curves)
    res = _execute_surface_builder("CreateBoundedPlaneBuilder", config, f"Created base surface {width}x{height} on {plane}")
    _state["last_curves"] = []
    return res


def extrude_surface(distance, start=0.0, direction="auto"):
    distance = float(distance)
    start = float(start)
    work_part = _ensure_work_part()
    curves = _state.get("last_curves", [])
    if not curves:
        return {"ok": False, "error": "No curves to extrude as surface"}
    def config(builder, wp):
        builder.Section = _build_section_from_curves(wp, curves)
        resolved_dir = _resolve_direction(direction)
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        builder.Direction = _create_direction(wp, origin, _direction_vector(resolved_dir))
        builder.Limits.StartExtend.Value.RightHandSide = _create_named_expression(wp, "EXTRUDE_SURF_START", start)
        builder.Limits.EndExtend.Value.RightHandSide = _create_named_expression(wp, "EXTRUDE_SURF_DIST", distance)
        for attr in ("FeatureOption", "FeatureOptions"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, getattr(NXOpen.Features, "FeatureOption", None).Sheet)
                except Exception:
                    pass
    res = _execute_surface_builder("CreateExtrudeBuilder", config, f"Extruded surface {distance}mm")
    _state["last_curves"] = []
    return res


def create_swept(section="last", guide="last"):
    sec_curves = _resolve_curves(section)
    guide_curves = _resolve_curves(guide)
    if not sec_curves or not guide_curves:
        return {"ok": False, "error": "Section or guide curves could not be resolved"}
    def config(builder, wp):
        sec = _build_section_from_curves(wp, sec_curves)
        gd = _build_section_from_curves(wp, guide_curves)
        for attr in ("Profile", "SweepProfile", "Section"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, sec)
                except Exception:
                    pass
        for attr in ("Guide", "SweepGuide", "Path"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, gd)
                except Exception:
                    pass
    return _execute_surface_builder("CreateSweepBuilder", config, "Swept surface created")


def create_through_curves(sections="last"):
    sec_curves = _resolve_curves(sections)
    if not sec_curves:
        return {"ok": False, "error": "Through curves sections not found"}
    def config(builder, wp):
        sec = _build_section_from_curves(wp, sec_curves)
        if hasattr(builder, "SectionsList"):
            builder.SectionsList.Add(sec)
        elif hasattr(builder, "Sections"):
            builder.Sections.Add(sec)
    return _execute_surface_builder("CreateThroughCurvesBuilder", config, "Through curves surface created")


def create_through_curve_mesh(primary="last", cross="last"):
    prim_curves = _resolve_curves(primary)
    crs_curves = _resolve_curves(cross)
    def config(builder, wp):
        sec_p = _build_section_from_curves(wp, prim_curves)
        sec_c = _build_section_from_curves(wp, crs_curves)
        if hasattr(builder, "PrimarySections"):
            builder.PrimarySections.Add(sec_p)
        if hasattr(builder, "CrossSections"):
            builder.CrossSections.Add(sec_c)
    return _execute_surface_builder("CreateThroughCurveMeshBuilder", config, "Through curve mesh created")


def add_face_blend(face1_x, face1_y, face1_z, face2_x, face2_y, face2_z, radius=5.0, body="last"):
    radius = float(radius)
    f1 = _resolve_face_by_coordinate(body, face1_x, face1_y, face1_z)
    f2 = _resolve_face_by_coordinate(body, face2_x, face2_y, face2_z)
    def config(builder, wp):
        r_name = _create_named_expression(wp, "FACE_BLEND_R", radius)
        if hasattr(builder, "Radius"):
            builder.Radius.RightHandSide = r_name
        collector1 = wp.ScCollectors.CreateCollector()
        collector2 = wp.ScCollectors.CreateCollector()
        rule1 = wp.ScRuleFactory.CreateRuleFaceDumb([f1])
        rule2 = wp.ScRuleFactory.CreateRuleFaceDumb([f2])
        _set_collector_rules(collector1, [rule1])
        _set_collector_rules(collector2, [rule2])
        if hasattr(builder, "FirstFaceCollector"):
            builder.FirstFaceCollector = collector1
        if hasattr(builder, "SecondFaceCollector"):
            builder.SecondFaceCollector = collector2
    return _execute_surface_builder("CreateFaceBlendBuilder", config, f"Face blend R{radius}mm added between faces")


def offset_surface(distance, body="last", face_x=0.0, face_y=0.0, face_z=0.0):
    distance = float(distance)
    f = _resolve_face_by_coordinate(body, face_x, face_y, face_z)
    def config(builder, wp):
        dist_name = _create_named_expression(wp, "OFFSET_DIST", distance)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = dist_name
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleFaceDumb([f])
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "FaceCollector"):
            builder.FaceCollector = collector
    return _execute_surface_builder("CreateOffsetSurfaceBuilder", config, f"Created offset surface of {distance}mm")


def thicken_sheet(thickness, direction="auto", body="last"):
    thickness = float(thickness)
    target_body = _resolve_body(body)
    def config(builder, wp):
        t_name = _create_named_expression(wp, "THICKEN_T", thickness)
        if hasattr(builder, "FirstOffset"):
            builder.FirstOffset.RightHandSide = t_name
        if hasattr(builder, "SecondOffset"):
            builder.SecondOffset.RightHandSide = "0.0"
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleBodyDumb([target_body], True)
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "FaceCollector"):
            builder.FaceCollector = collector
        resolved_dir = _resolve_direction(direction)
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        builder.Direction = _create_direction(wp, origin, _direction_vector(resolved_dir))
    return _execute_surface_builder("CreateThickenBuilder", config, f"Thickened sheet body '{_body_name(target_body)}' by {thickness}mm")


def sweep_along_guide(section="last", guide="last"):
    sec_curves = _resolve_curves(section)
    guide_curves = _resolve_curves(guide)
    if not sec_curves or not guide_curves:
        return {"ok": False, "error": "Section or guide curves could not be resolved"}
    def config(builder, wp):
        sec = _build_section_from_curves(wp, sec_curves)
        gd = _build_section_from_curves(wp, guide_curves)
        for attr in ("Profile", "SweepProfile", "Section"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, sec)
                except Exception:
                    pass
        for attr in ("Guide", "SweepGuide", "Path"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, gd)
                except Exception:
                    pass
    return _execute_surface_builder("CreateSweepAlongGuideBuilder", config, "Sweep along guide created")


def variational_sweep(section="last", guide="last"):
    sec_curves = _resolve_curves(section)
    guide_curves = _resolve_curves(guide)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, sec_curves)
        gd = _build_section_from_curves(wp, guide_curves)
        if hasattr(builder, "Section"):
            builder.Section = sec
        if hasattr(builder, "Path"):
            builder.Path = gd
    return _execute_surface_builder("CreateVariationalSweepBuilder", config, "Variational sweep created")


def create_tube(guide="last", outer_diameter=10.0, inner_diameter=0.0):
    outer_diameter = float(outer_diameter)
    inner_diameter = float(inner_diameter)
    guide_curves = _resolve_curves(guide)
    if not guide_curves:
        return {"ok": False, "error": "Tube guide curves could not be resolved"}
    def config(builder, wp):
        gd = _build_section_from_curves(wp, guide_curves)
        od_name = _create_named_expression(wp, "TUBE_OD", outer_diameter)
        id_name = _create_named_expression(wp, "TUBE_ID", inner_diameter)
        if hasattr(builder, "OuterDiameter"):
            builder.OuterDiameter.RightHandSide = od_name
        if hasattr(builder, "InnerDiameter"):
            builder.InnerDiameter.RightHandSide = id_name
        if hasattr(builder, "Path"):
            builder.Path = gd
    return _execute_surface_builder("CreateTubeBuilder", config, f"Tube created along guide (OD={outer_diameter}, ID={inner_diameter})")


def swept_volume(tool_body="last", guide="last"):
    t_body = _resolve_body(tool_body)
    guide_curves = _resolve_curves(guide)
    def config(builder, wp):
        gd = _build_section_from_curves(wp, guide_curves)
        if hasattr(builder, "ToolBody"):
            builder.ToolBody = t_body
        if hasattr(builder, "Path"):
            builder.Path = gd
    return _execute_surface_builder("CreateSweptVolumeBuilder", config, "Swept volume created")


def create_ruled(section1="last", section2="last"):
    sec1 = _resolve_curves(section1)
    sec2 = _resolve_curves(section2)
    def config(builder, wp):
        s1 = _build_section_from_curves(wp, sec1)
        s2 = _build_section_from_curves(wp, sec2)
        if hasattr(builder, "FirstSection"):
            builder.FirstSection = s1
        if hasattr(builder, "SecondSection"):
            builder.SecondSection = s2
    return _execute_surface_builder("CreateRuledBuilder", config, "Ruled surface created")


def n_sided_surface(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "BoundaryCurves"):
            builder.BoundaryCurves.Add(sec)
    return _execute_surface_builder("CreateNsidedSurfaceBuilder", config, "N-Sided surface created")


def fill_surface(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "BoundaryCurves"):
            builder.BoundaryCurves.Add(sec)
    return _execute_surface_builder("CreateFillHoleBuilder", config, "Fill surface created")


def bounded_plane(boundary="last"):
    curves = _resolve_curves(boundary)
    if not curves:
        return {"ok": False, "error": "No boundary curves for Bounded Plane"}
    def config(builder, wp):
        builder.Section = _build_section_from_curves(wp, curves)
    return _execute_surface_builder("CreateBoundedPlaneBuilder", config, "Bounded plane created")


def patch_openings(body="last", boundary="last"):
    target_body = _resolve_body(body)
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = target_body
        if hasattr(builder, "BoundaryCurves"):
            builder.BoundaryCurves.Add(sec)
    return _execute_surface_builder("CreatePatchOpeningsBuilder", config, "Patched openings on sheet body")


def variable_offset(distance_start=2.0, distance_end=5.0, body="last", face_x=0.0, face_y=0.0, face_z=0.0):
    ds = float(distance_start)
    de = float(distance_end)
    f = _resolve_face_by_coordinate(body, face_x, face_y, face_z)
    def config(builder, wp):
        if hasattr(builder, "FaceCollector"):
            collector = wp.ScCollectors.CreateCollector()
            rule = wp.ScRuleFactory.CreateRuleFaceDumb([f])
            _set_collector_rules(collector, [rule])
            builder.FaceCollector = collector
        if hasattr(builder, "StartDistance"):
            builder.StartDistance.RightHandSide = _create_named_expression(wp, "VAR_OFFSET_START", ds)
        if hasattr(builder, "EndDistance"):
            builder.EndDistance.RightHandSide = _create_named_expression(wp, "VAR_OFFSET_END", de)
    return _execute_surface_builder("CreateVariableOffsetBuilder", config, f"Variable offset surface ({ds}mm to {de}mm) created")


def sheet_from_curve(boundary="last"):
    return bounded_plane(boundary)


def law_extension(distance=10.0, angle=45.0, boundary_edge_x=0.0, boundary_edge_y=0.0, boundary_edge_z=0.0, body="last"):
    dist = float(distance)
    ang = float(angle)
    edge = _resolve_edge_by_coordinate(body, boundary_edge_x, boundary_edge_y, boundary_edge_z)
    def config(builder, wp):
        if hasattr(builder, "Length"):
            builder.Length.RightHandSide = _create_named_expression(wp, "LAW_EXT_LEN", dist)
        if hasattr(builder, "Angle"):
            builder.Angle.RightHandSide = _create_named_expression(wp, "LAW_EXT_ANG", ang)
        if hasattr(builder, "BoundaryEdgeCollector"):
            collector = wp.ScCollectors.CreateCollector()
            rule = wp.ScRuleFactory.CreateRuleEdgeTangent(edge, NXOpen.Edge.Null, False, 0.5, False)
            _set_collector_rules(collector, [rule])
            builder.BoundaryEdgeCollector = collector
    return _execute_surface_builder("CreateLawExtensionBuilder", config, "Law extension surface created")


def studio_surface(section1="last", section2="last"):
    sec1 = _resolve_curves(section1)
    sec2 = _resolve_curves(section2)
    def config(builder, wp):
        s1 = _build_section_from_curves(wp, sec1)
        s2 = _build_section_from_curves(wp, sec2)
        if hasattr(builder, "Sections"):
            builder.Sections.Add(s1)
            builder.Sections.Add(s2)
    return _execute_surface_builder("CreateStudioSurfaceBuilder", config, "Studio surface created")


def styled_sweep(section="last", guide="last"):
    sec_curves = _resolve_curves(section)
    guide_curves = _resolve_curves(guide)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, sec_curves)
        gd = _build_section_from_curves(wp, guide_curves)
        if hasattr(builder, "Section"):
            builder.Section = sec
        if hasattr(builder, "Guide"):
            builder.Guide = gd
    return _execute_surface_builder("CreateStyledSweepBuilder", config, "Styled sweep surface created")


def section_surface(section1="last", section2="last"):
    sec1 = _resolve_curves(section1)
    sec2 = _resolve_curves(section2)
    def config(builder, wp):
        s1 = _build_section_from_curves(wp, sec1)
        s2 = _build_section_from_curves(wp, sec2)
        if hasattr(builder, "Sections"):
            builder.Sections.Add(s1)
            builder.Sections.Add(s2)
    return _execute_surface_builder("CreateSectionSurfaceBuilder", config, "Section surface created")


def aesthetic_face_blend(radius=5.0, body="last", face1_x=0.0, face1_y=0.0, face1_z=0.0, face2_x=0.0, face2_y=0.0, face2_z=0.0):
    radius = float(radius)
    f1 = _resolve_face_by_coordinate(body, face1_x, face1_y, face1_z)
    f2 = _resolve_face_by_coordinate(body, face2_x, face2_y, face2_z)
    def config(builder, wp):
        if hasattr(builder, "Radius"):
            builder.Radius.RightHandSide = _create_named_expression(wp, "AESTHETIC_BLEND_R", radius)
        collector1 = wp.ScCollectors.CreateCollector()
        collector2 = wp.ScCollectors.CreateCollector()
        rule1 = wp.ScRuleFactory.CreateRuleFaceDumb([f1])
        rule2 = wp.ScRuleFactory.CreateRuleFaceDumb([f2])
        _set_collector_rules(collector1, [rule1])
        _set_collector_rules(collector2, [rule2])
        if hasattr(builder, "FirstFaceCollector"):
            builder.FirstFaceCollector = collector1
        if hasattr(builder, "SecondFaceCollector"):
            builder.SecondFaceCollector = collector2
    return _execute_surface_builder("CreateAestheticFaceBlendBuilder", config, f"Aesthetic face blend R{radius}mm created")


def bridge_surface(edge1_x=0.0, edge1_y=0.0, edge1_z=0.0, edge2_x=0.0, edge2_y=0.0, edge2_z=0.0, body="last"):
    ed1 = _resolve_edge_by_coordinate(body, edge1_x, edge1_y, edge1_z)
    ed2 = _resolve_edge_by_coordinate(body, edge2_x, edge2_y, edge2_z)
    def config(builder, wp):
        c1 = wp.ScCollectors.CreateCollector()
        c2 = wp.ScCollectors.CreateCollector()
        r1 = wp.ScRuleFactory.CreateRuleEdgeTangent(ed1, NXOpen.Edge.Null, False, 0.5, False)
        r2 = wp.ScRuleFactory.CreateRuleEdgeTangent(ed2, NXOpen.Edge.Null, False, 0.5, False)
        _set_collector_rules(c1, [r1])
        _set_collector_rules(c2, [r2])
        if hasattr(builder, "FirstEdgeCollector"):
            builder.FirstEdgeCollector = c1
        if hasattr(builder, "SecondEdgeCollector"):
            builder.SecondEdgeCollector = c2
    return _execute_surface_builder("CreateBridgeSurfaceBuilder", config, "Bridge surface created between edges")


def blend_corner(radius=5.0, corner_vertex_x=0.0, corner_vertex_y=0.0, corner_vertex_z=0.0, body="last"):
    radius = float(radius)
    def config(builder, wp):
        r_name = _create_named_expression(wp, "BLEND_CORNER_R", radius)
        if hasattr(builder, "Radius"):
            builder.Radius.RightHandSide = r_name
    return _execute_surface_builder("CreateBlendCornerBuilder", config, "Blend corner feature created")


def styled_corner(corner_vertex_x=0.0, corner_vertex_y=0.0, corner_vertex_z=0.0, body="last"):
    def config(builder, wp):
        pass
    return _execute_surface_builder("CreateStyledCornerBuilder", config, "Styled corner created")


def four_point_surface(x1, y1, z1, x2, y2, z2, x3, y3, z3, x4, y4, z4):
    def config(builder, wp):
        p1 = NXOpen.Point3d(float(x1), float(y1), float(z1))
        p2 = NXOpen.Point3d(float(x2), float(y2), float(z2))
        p3 = NXOpen.Point3d(float(x3), float(y3), float(z3))
        p4 = NXOpen.Point3d(float(x4), float(y4), float(z4))
        if hasattr(builder, "Point1"):
            builder.Point1 = p1
        if hasattr(builder, "Point2"):
            builder.Point2 = p2
        if hasattr(builder, "Point3"):
            builder.Point3 = p3
        if hasattr(builder, "Point4"):
            builder.Point4 = p4
    return _execute_surface_builder("CreateFourPointSurfaceBuilder", config, "Four point surface created")


def rapid_surfacing(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "BoundaryCurves"):
            builder.BoundaryCurves.Add(sec)
    return _execute_surface_builder("CreateRapidSurfacingBuilder", config, "Rapid surfacing sheet created")


def fit_surface(target_face_x=0.0, target_face_y=0.0, target_face_z=0.0, body="last"):
    f = _resolve_face_by_coordinate(body, target_face_x, target_face_y, target_face_z)
    def config(builder, wp):
        if hasattr(builder, "FaceToFit"):
            builder.FaceToFit = f
    return _execute_surface_builder("CreateFitSurfaceBuilder", config, "Fit surface created")


def variable_offset_face(distance=5.0, body="last", face_x=0.0, face_y=0.0, face_z=0.0):
    dist = float(distance)
    f = _resolve_face_by_coordinate(body, face_x, face_y, face_z)
    def config(builder, wp):
        dist_name = _create_named_expression(wp, "VAR_OFFSET_FACE_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = dist_name
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleFaceDumb([f])
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "FaceCollector"):
            builder.FaceCollector = collector
    return _execute_surface_builder("CreateVariableOffsetFaceBuilder", config, f"Variable offset face by {dist}mm created")


def extension_surface(distance=10.0, boundary_edge_x=0.0, boundary_edge_y=0.0, boundary_edge_z=0.0, body="last"):
    dist = float(distance)
    edge = _resolve_edge_by_coordinate(body, boundary_edge_x, boundary_edge_y, boundary_edge_z)
    def config(builder, wp):
        dist_name = _create_named_expression(wp, "EXT_SURF_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = dist_name
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleEdgeTangent(edge, NXOpen.Edge.Null, False, 0.5, False)
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "EdgeCollector"):
            builder.EdgeCollector = collector
    return _execute_surface_builder("CreateExtensionSurfaceBuilder", config, f"Extension surface of {dist}mm created")


def silhouette_flange(distance=10.0, body="last", face_x=0.0, face_y=0.0, face_z=0.0):
    dist = float(distance)
    f = _resolve_face_by_coordinate(body, face_x, face_y, face_z)
    def config(builder, wp):
        dist_name = _create_named_expression(wp, "SILHOUETTE_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = dist_name
        if hasattr(builder, "Face"):
            builder.Face = f
    return _execute_surface_builder("CreateSilhouetteFlangeBuilder", config, f"Silhouette flange of {dist}mm created")


def face_pairs(distance=2.0, body="last"):
    dist = float(distance)
    target_body = _resolve_body(body)
    def config(builder, wp):
        dist_name = _create_named_expression(wp, "FACE_PAIRS_DIST", dist)
        if hasattr(builder, "SearchDistance"):
            builder.SearchDistance.RightHandSide = dist_name
        if hasattr(builder, "Body"):
            builder.Body = target_body
    return _execute_surface_builder("CreateFacePairsBuilder", config, f"Face pairs analysis created at distance {dist}mm")


def user_defined_surface(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "ProfileSection"):
            builder.ProfileSection = sec
    return _execute_surface_builder("CreateUserDefinedSurfaceBuilder", config, "User-defined surface created")


def offset_surface_advanced(distance=5.0, body="last", face_x=0.0, face_y=0.0, face_z=0.0):
    return offset_surface(distance, body, face_x, face_y, face_z)


def bisector_surface(face1_x=0.0, face1_y=0.0, face1_z=0.0, face2_x=0.0, face2_y=0.0, face2_z=0.0, body="last"):
    f1 = _resolve_face_by_coordinate(body, face1_x, face1_y, face1_z)
    f2 = _resolve_face_by_coordinate(body, face2_x, face2_y, face2_z)
    def config(builder, wp):
        if hasattr(builder, "FirstFace"):
            builder.FirstFace = f1
        if hasattr(builder, "SecondFace"):
            builder.SecondFace = f2
    return _execute_surface_builder("CreateBisectorSurfaceBuilder", config, "Bisector surface created between faces")


def surface_from_poles(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "ProfileSection"):
            builder.ProfileSection = sec
    return _execute_surface_builder("CreateSurfaceFromPolesBuilder", config, "Surface from poles created")


def surface_through_points(boundary="last"):
    curves = _resolve_curves(boundary)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "ProfileSection"):
            builder.ProfileSection = sec
    return _execute_surface_builder("CreateSurfaceThroughPointsBuilder", config, "Surface through points created")


def ribbon_builder(width=10.0, boundary_edge_x=0.0, boundary_edge_y=0.0, boundary_edge_z=0.0, body="last"):
    w = float(width)
    edge = _resolve_edge_by_coordinate(body, boundary_edge_x, boundary_edge_y, boundary_edge_z)
    def config(builder, wp):
        w_name = _create_named_expression(wp, "RIBBON_WIDTH", w)
        if hasattr(builder, "Width"):
            builder.Width.RightHandSide = w_name
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleEdgeTangent(edge, NXOpen.Edge.Null, False, 0.5, False)
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "EdgeCollector"):
            builder.EdgeCollector = collector
    return _execute_surface_builder("CreateRibbonBuilder", config, f"Ribbon surface of {w}mm width created along edge")


def boolean_combine(operation="intersect", target="last", tool="last"):
    work_part = _ensure_work_part()
    target_body = _resolve_body(target)
    tool_body = _resolve_body(tool)
    if target_body == tool_body:
        raise SelectionError("Boolean target and tool resolve to the same body")
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        op_name = operation.lower()
        if op_name == "unite":
            builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        elif op_name == "subtract":
            builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        elif op_name == "intersect":
            builder.Operation = NXOpen.Features.Feature.BooleanType.Intersect
        else:
            raise SelectionError(f"Unsupported boolean operation: {operation}")
        _set_boolean_inputs(builder, work_part, target_body, [tool_body])
        feature = builder.CommitFeature()
        _remember_feature(feature)
    finally:
        builder.Destroy()
    fit_view()
    return {"ok": True, "message": f"Boolean {op_name} completed"}


def trim_sheet(target_body="last", boundary_sketch="last"):
    t_body = _resolve_body(target_body)
    curves = _resolve_curves(boundary_sketch)
    if not curves:
        return {"ok": False, "error": "Trim boundary curves not resolved"}
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = t_body
        if hasattr(builder, "BoundarySection"):
            builder.BoundarySection = sec
    return _execute_surface_builder("CreateTrimSheetBuilder", config, "Trimmed sheet body")


def extend_sheet(distance=10.0, boundary_edge_x=0.0, boundary_edge_y=0.0, boundary_edge_z=0.0, body="last"):
    dist = float(distance)
    edge = _resolve_edge_by_coordinate(body, boundary_edge_x, boundary_edge_y, boundary_edge_z)
    def config(builder, wp):
        d_name = _create_named_expression(wp, "EXT_SHEET_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = d_name
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleEdgeTangent(edge, NXOpen.Edge.Null, False, 0.5, False)
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "EdgeCollector"):
            builder.EdgeCollector = collector
    return _execute_surface_builder("CreateExtendSheetBuilder", config, f"Extended sheet edge by {dist}mm")


def trim_and_extend(target_body="last", tool_body="last"):
    tb = _resolve_body(target_body)
    tool = _resolve_body(tool_body)
    def config(builder, wp):
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "ToolBody"):
            builder.ToolBody = tool
    return _execute_surface_builder("CreateTrimAndExtendBuilder", config, "Trim and extend operation completed")


def sew_sheets(target_sheet="last", tool_sheets="last"):
    tb = _resolve_body(target_sheet)
    tool = _resolve_body(tool_sheets)
    def config(builder, wp):
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "ToolBodies"):
            builder.ToolBodies.Add([tool])
    return _execute_surface_builder("CreateSewBuilder", config, "Sheets sewn successfully")


def split_body(target_body="last", tool_face_x=0.0, tool_face_y=0.0, tool_face_z=0.0):
    tb = _resolve_body(target_body)
    f = _resolve_face_by_coordinate(target_body, tool_face_x, tool_face_y, tool_face_z)
    def config(builder, wp):
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "ToolFace"):
            builder.ToolFace = f
    return _execute_surface_builder("CreateSplitBodyBuilder", config, "Body split successfully")


def divide_face(target_face_x=0.0, target_face_y=0.0, target_face_z=0.0, boundary_sketch="last", body="last"):
    f = _resolve_face_by_coordinate(body, target_face_x, target_face_y, target_face_z)
    curves = _resolve_curves(boundary_sketch)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "FaceToDivide"):
            builder.FaceToDivide = f
        if hasattr(builder, "DividingCurves"):
            builder.DividingCurves = sec
    return _execute_surface_builder("CreateDivideFaceBuilder", config, "Divide face completed")


def snip_surface(target_face_x=0.0, target_face_y=0.0, target_face_z=0.0, body="last"):
    f = _resolve_face_by_coordinate(body, target_face_x, target_face_y, target_face_z)
    def config(builder, wp):
        if hasattr(builder, "FaceToSnip"):
            builder.FaceToSnip = f
    return _execute_surface_builder("CreateSnipSurfaceBuilder", config, "Snip surface completed")


def untrim_sheet(target_edge_x=0.0, target_edge_y=0.0, target_edge_z=0.0, body="last"):
    edge = _resolve_edge_by_coordinate(body, target_edge_x, target_edge_y, target_edge_z)
    def config(builder, wp):
        collector = wp.ScCollectors.CreateCollector()
        rule = wp.ScRuleFactory.CreateRuleEdgeTangent(edge, NXOpen.Edge.Null, False, 0.5, False)
        _set_collector_rules(collector, [rule])
        if hasattr(builder, "EdgeCollector"):
            builder.EdgeCollector = collector
    return _execute_surface_builder("CreateUntrimBuilder", config, "Untrimmed sheet successfully")


def delete_edge(target_edge_x=0.0, target_edge_y=0.0, target_edge_z=0.0, body="last"):
    edge = _resolve_edge_by_coordinate(body, target_edge_x, target_edge_y, target_edge_z)
    def config(builder, wp):
        if hasattr(builder, "EdgeToDelete"):
            builder.EdgeToDelete = edge
    return _execute_surface_builder("CreateDeleteEdgeBuilder", config, "Delete edge completed")


def emboss_body(target_body="last", boundary_sketch="last", depth=5.0):
    tb = _resolve_body(target_body)
    curves = _resolve_curves(boundary_sketch)
    depth = float(depth)
    def config(builder, wp):
        d_name = _create_named_expression(wp, "EMBOSS_DEPTH", depth)
        if hasattr(builder, "Depth"):
            builder.Depth.RightHandSide = d_name
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "BoundarySection"):
            builder.BoundarySection = _build_section_from_curves(wp, curves)
    return _execute_surface_builder("CreateEmbossBodyBuilder", config, f"Emboss body completed by {depth}mm")


def patch_body(target_body="last", tool_sheet="last"):
    tb = _resolve_body(target_body)
    tool = _resolve_body(tool_sheet)
    def config(builder, wp):
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "ToolBody"):
            builder.ToolBody = tool
    return _execute_surface_builder("CreatePatchBuilder", config, "Body patched successfully")


def unsew_sheets(target_body="last", split_edge_x=0.0, split_edge_y=0.0, split_edge_z=0.0):
    tb = _resolve_body(target_body)
    edge = _resolve_edge_by_coordinate(target_body, split_edge_x, split_edge_y, split_edge_z)
    def config(builder, wp):
        if hasattr(builder, "TargetBody"):
            builder.TargetBody = tb
        if hasattr(builder, "EdgeToUnsew"):
            builder.EdgeToUnsew = edge
    return _execute_surface_builder("CreateUnsewBuilder", config, "Unsewed sheet body")


def make_solid(target_sheet="last"):
    tb = _resolve_body(target_sheet)
    def config(builder, wp):
        if hasattr(builder, "SheetBody"):
            builder.SheetBody = tb
    return _execute_surface_builder("CreateMakeSolidBuilder", config, "Sewn sheet body successfully converted to Solid body")


def sheet_boundary_analysis(body="last"):
    tb = _resolve_body(body)
    edges = list(tb.GetEdges() or [])
    free_edges = 0
    for edge in edges:
        try:
            faces = list(edge.GetFaces() or [])
            if len(faces) == 1:
                free_edges += 1
        except Exception:
            pass
    return {"ok": True, "message": f"Sheet boundary analysis: {len(edges)} total edges, {free_edges} boundary edges found"}


def quilt_sheets(target_sheet="last"):
    return sew_sheets(target_sheet)


def reverse_normal(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "FaceCollector"):
            collector = wp.ScCollectors.CreateCollector()
            rule = wp.ScRuleFactory.CreateRuleBodyDumb([tb], True)
            _set_collector_rules(collector, [rule])
            builder.FaceCollector = collector
    return _execute_surface_builder("CreateReverseNormalBuilder", config, "Reversed sheet normal direction")


def local_untrim_extend(boundary_edge_x=0.0, boundary_edge_y=0.0, boundary_edge_z=0.0, distance=10.0, body="last"):
    dist = float(distance)
    edge = _resolve_edge_by_coordinate(body, boundary_edge_x, boundary_edge_y, boundary_edge_z)
    def config(builder, wp):
        d_name = _create_named_expression(wp, "LOCAL_EXT_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = d_name
        if hasattr(builder, "Edge"):
            builder.Edge = edge
    return _execute_surface_builder("CreateLocalUntrimExtendBuilder", config, f"Untrimmed and extended face by {dist}mm")


def replace_edge(target_edge_x=0.0, target_edge_y=0.0, target_edge_z=0.0, tool_sketch="last", body="last"):
    edge = _resolve_edge_by_coordinate(body, target_edge_x, target_edge_y, target_edge_z)
    curves = _resolve_curves(tool_sketch)
    def config(builder, wp):
        sec = _build_section_from_curves(wp, curves)
        if hasattr(builder, "EdgeToReplace"):
            builder.EdgeToReplace = edge
        if hasattr(builder, "ReplacementCurves"):
            builder.ReplacementCurves = sec
    return _execute_surface_builder("CreateReplaceEdgeBuilder", config, "Replaced edge completed")


def x_form(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateXformBuilder", config, "X-Form deformation applied")


def i_form(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateIformBuilder", config, "I-Form deformation applied")


def match_edge(target_edge_x=0.0, target_edge_y=0.0, target_edge_z=0.0, tool_edge_x=0.0, tool_edge_y=0.0, tool_edge_z=0.0, body="last"):
    ed1 = _resolve_edge_by_coordinate(body, target_edge_x, target_edge_y, target_edge_z)
    ed2 = _resolve_edge_by_coordinate(body, tool_edge_x, tool_edge_y, tool_edge_z)
    def config(builder, wp):
        if hasattr(builder, "TargetEdge"):
            builder.TargetEdge = ed1
        if hasattr(builder, "ToolEdge"):
            builder.ToolEdge = ed2
    return _execute_surface_builder("CreateMatchEdgeBuilder", config, "Match edge feature created")


def edge_symmetry(target_edge_x=0.0, target_edge_y=0.0, target_edge_z=0.0, body="last"):
    edge = _resolve_edge_by_coordinate(body, target_edge_x, target_edge_y, target_edge_z)
    def config(builder, wp):
        if hasattr(builder, "Edge"):
            builder.Edge = edge
    return _execute_surface_builder("CreateEdgeSymmetryBuilder", config, "Edge symmetry applied")


def global_shaping(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateGlobalShapingBuilder", config, "Global shaping applied to sheet")


def global_deformation(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateGlobalDeformationBuilder", config, "Global deformation applied")


def flattening_forming(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateFlatteningFormingBuilder", config, "Flattening and forming completed")


def heal_surface(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateHealSurfaceBuilder", config, "Surface healed successfully")


def edit_uv_direction(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateEditUvDirectionBuilder", config, "Edited face UV direction")


def enlarge_face(body="last", distance=5.0, face_x=0.0, face_y=0.0, face_z=0.0):
    dist = float(distance)
    f = _resolve_face_by_coordinate(body, face_x, face_y, face_z)
    def config(builder, wp):
        d_name = _create_named_expression(wp, "ENLARGE_DIST", dist)
        if hasattr(builder, "Distance"):
            builder.Distance.RightHandSide = d_name
        if hasattr(builder, "Face"):
            builder.Face = f
    return _execute_surface_builder("CreateEnlargeBuilder", config, f"Enlarged face by {dist}mm")


def snip_into_patches(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateSnipIntoPatchesBuilder", config, "Snipped surface into patches")


def smooth_poles(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateSmoothPolesBuilder", config, "Smoothed poles of freeform face")


def refit_face(body="last"):
    tb = _resolve_body(body)
    def config(builder, wp):
        if hasattr(builder, "Body"):
            builder.Body = tb
    return _execute_surface_builder("CreateRefitFaceBuilder", config, "Refitted face geometry")


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
    # --- Standard Surface Tools ---
    if tool == "create_base_surface":
        return create_base_surface(args.get("plane", "XY"), args.get("width", 50.0), args.get("height", 50.0))
    if tool == "extrude_surface":
        return extrude_surface(args["distance"], args.get("start", 0.0), args.get("direction", "auto"))
    if tool == "create_swept":
        return create_swept(args.get("section", "last"), args.get("guide", "last"))
    if tool == "create_through_curves":
        return create_through_curves(args.get("sections", "last"))
    if tool == "create_through_curve_mesh":
        return create_through_curve_mesh(args.get("primary", "last"), args.get("cross", "last"))
    if tool == "add_face_blend":
        return add_face_blend(
            args["face1_x"], args["face1_y"], args["face1_z"],
            args["face2_x"], args["face2_y"], args["face2_z"],
            args.get("radius", 5.0), args.get("body", "last")
        )
    if tool == "offset_surface":
        return offset_surface(
            args["distance"], args.get("body", "last"),
            args.get("face_x", 0.0), args.get("face_y", 0.0), args.get("face_z", 0.0)
        )
    if tool == "thicken_sheet":
        return thicken_sheet(args["thickness"], args.get("direction", "auto"), args.get("body", "last"))
    if tool == "sweep_along_guide":
        return sweep_along_guide(args.get("section", "last"), args.get("guide", "last"))
    if tool == "variational_sweep":
        return variational_sweep(args.get("section", "last"), args.get("guide", "last"))
    if tool == "create_tube":
        return create_tube(args.get("guide", "last"), args.get("outer_diameter", 10.0), args.get("inner_diameter", 0.0))
    if tool == "swept_volume":
        return swept_volume(args.get("tool_body", "last"), args.get("guide", "last"))
    if tool == "create_ruled":
        return create_ruled(args.get("section1", "last"), args.get("section2", "last"))
    if tool == "n_sided_surface":
        return n_sided_surface(args.get("boundary", "last"))
    if tool == "fill_surface":
        return fill_surface(args.get("boundary", "last"))
    if tool == "bounded_plane":
        return bounded_plane(args.get("boundary", "last"))
    if tool == "patch_openings":
        return patch_openings(args.get("body", "last"), args.get("boundary", "last"))
    if tool == "variable_offset":
        return variable_offset(
            args.get("distance_start", 2.0), args.get("distance_end", 5.0),
            args.get("body", "last"), args.get("face_x", 0.0), args.get("face_y", 0.0), args.get("face_z", 0.0)
        )
    if tool == "sheet_from_curve":
        return sheet_from_curve(args.get("boundary", "last"))

    # --- Advanced Surface Tools ---
    if tool == "law_extension":
        return law_extension(
            args.get("distance", 10.0), args.get("angle", 45.0),
            args.get("boundary_edge_x", 0.0), args.get("boundary_edge_y", 0.0), args.get("boundary_edge_z", 0.0),
            args.get("body", "last")
        )
    if tool == "studio_surface":
        return studio_surface(args.get("section1", "last"), args.get("section2", "last"))
    if tool == "styled_sweep":
        return styled_sweep(args.get("section", "last"), args.get("guide", "last"))
    if tool == "section_surface":
        return section_surface(args.get("section1", "last"), args.get("section2", "last"))
    if tool == "aesthetic_face_blend":
        return aesthetic_face_blend(
            args.get("radius", 5.0), args.get("body", "last"),
            args.get("face1_x", 0.0), args.get("face1_y", 0.0), args.get("face1_z", 0.0),
            args.get("face2_x", 0.0), args.get("face2_y", 0.0), args.get("face2_z", 0.0)
        )
    if tool == "bridge_surface":
        return bridge_surface(
            args.get("edge1_x", 0.0), args.get("edge1_y", 0.0), args.get("edge1_z", 0.0),
            args.get("edge2_x", 0.0), args.get("edge2_y", 0.0), args.get("edge2_z", 0.0),
            args.get("body", "last")
        )
    if tool == "blend_corner":
        return blend_corner(
            args.get("radius", 5.0),
            args.get("corner_vertex_x", 0.0), args.get("corner_vertex_y", 0.0), args.get("corner_vertex_z", 0.0),
            args.get("body", "last")
        )
    if tool == "styled_corner":
        return styled_corner(
            args.get("corner_vertex_x", 0.0), args.get("corner_vertex_y", 0.0), args.get("corner_vertex_z", 0.0),
            args.get("body", "last")
        )
    if tool == "four_point_surface":
        return four_point_surface(
            args["x1"], args["y1"], args["z1"], args["x2"], args["y2"], args["z2"],
            args["x3"], args["y3"], args["z3"], args["x4"], args["y4"], args["z4"]
        )
    if tool == "rapid_surfacing":
        return rapid_surfacing(args.get("boundary", "last"))
    if tool == "fit_surface":
        return fit_surface(
            args.get("target_face_x", 0.0), args.get("target_face_y", 0.0), args.get("target_face_z", 0.0),
            args.get("body", "last")
        )
    if tool == "variable_offset_face":
        return variable_offset_face(
            args.get("distance", 5.0), args.get("body", "last"),
            args.get("face_x", 0.0), args.get("face_y", 0.0), args.get("face_z", 0.0)
        )
    if tool == "extension_surface":
        return extension_surface(
            args.get("distance", 10.0),
            args.get("boundary_edge_x", 0.0), args.get("boundary_edge_y", 0.0), args.get("boundary_edge_z", 0.0),
            args.get("body", "last")
        )
    if tool == "silhouette_flange":
        return silhouette_flange(
            args.get("distance", 10.0), args.get("body", "last"),
            args.get("face_x", 0.0), args.get("face_y", 0.0), args.get("face_z", 0.0)
        )
    if tool == "face_pairs":
        return face_pairs(args.get("distance", 2.0), args.get("body", "last"))
    if tool == "user_defined_surface":
        return user_defined_surface(args.get("boundary", "last"))
    if tool == "offset_surface_advanced":
        return offset_surface_advanced(
            args.get("distance", 5.0), args.get("body", "last"),
            args.get("face_x", 0.0), args.get("face_y", 0.0), args.get("face_z", 0.0)
        )
    if tool == "bisector_surface":
        return bisector_surface(
            args.get("face1_x", 0.0), args.get("face1_y", 0.0), args.get("face1_z", 0.0),
            args.get("face2_x", 0.0), args.get("face2_y", 0.0), args.get("face2_z", 0.0),
            args.get("body", "last")
        )
    if tool == "surface_from_poles":
        return surface_from_poles(args.get("boundary", "last"))
    if tool == "surface_through_points":
        return surface_through_points(args.get("boundary", "last"))
    if tool == "ribbon_builder":
        return ribbon_builder(
            args.get("width", 10.0),
            args.get("boundary_edge_x", 0.0), args.get("boundary_edge_y", 0.0), args.get("boundary_edge_z", 0.0),
            args.get("body", "last")
        )

    # --- Combine Tools ---
    if tool == "boolean_combine":
        return boolean_combine(args.get("operation", "intersect"), args.get("target", "last"), args.get("tool", "last"))
    if tool == "trim_sheet":
        return trim_sheet(args.get("target_body", "last"), args.get("boundary_sketch", "last"))
    if tool == "extend_sheet":
        return extend_sheet(
            args.get("distance", 10.0),
            args.get("boundary_edge_x", 0.0), args.get("boundary_edge_y", 0.0), args.get("boundary_edge_z", 0.0),
            args.get("body", "last")
        )
    if tool == "trim_and_extend":
        return trim_and_extend(args.get("target_body", "last"), args.get("tool_body", "last"))
    if tool == "sew_sheets":
        return sew_sheets(args.get("target_sheet", "last"), args.get("tool_sheets", "last"))
    if tool == "split_body":
        return split_body(
            args.get("target_body", "last"),
            args.get("tool_face_x", 0.0), args.get("tool_face_y", 0.0), args.get("tool_face_z", 0.0)
        )
    if tool == "divide_face":
        return divide_face(
            args.get("target_face_x", 0.0), args.get("target_face_y", 0.0), args.get("target_face_z", 0.0),
            args.get("boundary_sketch", "last"), args.get("body", "last")
        )
    if tool == "snip_surface":
        return snip_surface(
            args.get("target_face_x", 0.0), args.get("target_face_y", 0.0), args.get("target_face_z", 0.0),
            args.get("body", "last")
        )
    if tool == "untrim_sheet":
        return untrim_sheet(
            args.get("target_edge_x", 0.0), args.get("target_edge_y", 0.0), args.get("target_edge_z", 0.0),
            args.get("body", "last")
        )
    if tool == "delete_edge":
        return delete_edge(
            args.get("target_edge_x", 0.0), args.get("target_edge_y", 0.0), args.get("target_edge_z", 0.0),
            args.get("body", "last")
        )
    if tool == "emboss_body":
        return emboss_body(args.get("target_body", "last"), args.get("boundary_sketch", "last"), args.get("depth", 5.0))
    if tool == "patch_body":
        return patch_body(args.get("target_body", "last"), args.get("tool_sheet", "last"))
    if tool == "unsew_sheets":
        return unsew_sheets(
            args.get("target_body", "last"),
            args.get("split_edge_x", 0.0), args.get("split_edge_y", 0.0), args.get("split_edge_z", 0.0)
        )
    if tool == "make_solid":
        return make_solid(args.get("target_sheet", "last"))
    if tool == "sheet_boundary_analysis":
        return sheet_boundary_analysis(args.get("body", "last"))
    if tool == "quilt_sheets":
        return quilt_sheets(args.get("target_sheet", "last"))

    # --- Edit Tools ---
    if tool == "reverse_normal":
        return reverse_normal(args.get("body", "last"))
    if tool == "local_untrim_extend":
        return local_untrim_extend(
            args.get("boundary_edge_x", 0.0), args.get("boundary_edge_y", 0.0), args.get("boundary_edge_z", 0.0),
            args.get("distance", 10.0), args.get("body", "last")
        )
    if tool == "replace_edge":
        return replace_edge(
            args.get("target_edge_x", 0.0), args.get("target_edge_y", 0.0), args.get("target_edge_z", 0.0),
            args.get("tool_sketch", "last"), args.get("body", "last")
        )
    if tool == "x_form":
        return x_form(args.get("body", "last"))
    if tool == "i_form":
        return i_form(args.get("body", "last"))
    if tool == "match_edge":
        return match_edge(
            args.get("target_edge_x", 0.0), args.get("target_edge_y", 0.0), args.get("target_edge_z", 0.0),
            args.get("tool_edge_x", 0.0), args.get("tool_edge_y", 0.0), args.get("tool_edge_z", 0.0),
            args.get("body", "last")
        )
    if tool == "edge_symmetry":
        return edge_symmetry(
            args.get("target_edge_x", 0.0), args.get("target_edge_y", 0.0), args.get("target_edge_z", 0.0),
            args.get("body", "last")
        )
    if tool == "global_shaping":
        return global_shaping(args.get("body", "last"))
    if tool == "global_deformation":
        return global_deformation(args.get("body", "last"))
    if tool == "flattening_forming":
        return flattening_forming(args.get("body", "last"))
    if tool == "heal_surface":
        return heal_surface(args.get("body", "last"))
    if tool == "edit_uv_direction":
        return edit_uv_direction(args.get("body", "last"))
    if tool == "enlarge_face":
        return enlarge_face(
            args.get("body", "last"), args.get("distance", 5.0),
            args.get("face_x", 0.0), args.get("face_y", 0.0), args.get("face_z", 0.0)
        )
    if tool == "snip_into_patches":
        return snip_into_patches(args.get("body", "last"))
    if tool == "smooth_poles":
        return smooth_poles(args.get("body", "last"))
    if tool == "refit_face":
        return refit_face(args.get("body", "last"))

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
