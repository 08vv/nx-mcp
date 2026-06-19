import math
import sys
from pathlib import Path

import NXOpen


LENGTH = 100.0
WIDTH = 60.0
THICKNESS = 10.0
HOLE_DIAMETER = 8.0
HOLE_EDGE_OFFSET = 10.0
HOLE_SEGMENTS = 64
TOLERANCE = 1.0e-6


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd().joinpath("plate_100x60x10_4x_d8_holes.prt").resolve()


class ObjMesh:
    def __init__(self):
        self.vertices = []
        self.faces = []

    def vertex(self, x, y, z):
        self.vertices.append((float(x), float(y), float(z)))
        return len(self.vertices)

    def face(self, *indices):
        self.faces.append(tuple(indices))

    def quad(self, a, b, c, d):
        self.face(a, b, c)
        self.face(a, c, d)

    def write(self, path):
        with path.open("w", encoding="ascii") as stream:
            stream.write("# 100x60x10 plate with 4x D8 corner holes\n")
            for x, y, z in self.vertices:
                stream.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
            for face in self.faces:
                stream.write("f " + " ".join(str(index) for index in face) + "\n")


def _hole_centers():
    return (
        (HOLE_EDGE_OFFSET, HOLE_EDGE_OFFSET),
        (LENGTH - HOLE_EDGE_OFFSET, HOLE_EDGE_OFFSET),
        (HOLE_EDGE_OFFSET, WIDTH - HOLE_EDGE_OFFSET),
        (LENGTH - HOLE_EDGE_OFFSET, WIDTH - HOLE_EDGE_OFFSET),
    )


def _hole_square_bounds():
    radius = HOLE_DIAMETER / 2.0
    return [
        (cx - radius, cx + radius, cy - radius, cy + radius)
        for cx, cy in _hole_centers()
    ]


def _is_hole_square(x0, x1, y0, y1):
    for hx0, hx1, hy0, hy1 in _hole_square_bounds():
        if (
            abs(x0 - hx0) < TOLERANCE
            and abs(x1 - hx1) < TOLERANCE
            and abs(y0 - hy0) < TOLERANCE
            and abs(y1 - hy1) < TOLERANCE
        ):
            return True
    return False


def _square_point_on_ray(cx, cy, angle, radius):
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)
    scale = radius / max(abs(cos_angle), abs(sin_angle))
    return cx + cos_angle * scale, cy + sin_angle * scale


def _add_planar_quad(mesh, x0, x1, y0, y1, z, reverse=False):
    a = mesh.vertex(x0, y0, z)
    b = mesh.vertex(x1, y0, z)
    c = mesh.vertex(x1, y1, z)
    d = mesh.vertex(x0, y1, z)
    if reverse:
        mesh.quad(d, c, b, a)
    else:
        mesh.quad(a, b, c, d)


def _add_top_bottom_faces(mesh):
    radius = HOLE_DIAMETER / 2.0
    x_breaks = sorted(
        {
            0.0,
            LENGTH,
            *(coord for cx, _ in _hole_centers() for coord in (cx - radius, cx + radius)),
        }
    )
    y_breaks = sorted(
        {
            0.0,
            WIDTH,
            *(coord for _, cy in _hole_centers() for coord in (cy - radius, cy + radius)),
        }
    )

    for x0, x1 in zip(x_breaks, x_breaks[1:]):
        for y0, y1 in zip(y_breaks, y_breaks[1:]):
            if _is_hole_square(x0, x1, y0, y1):
                continue
            _add_planar_quad(mesh, x0, x1, y0, y1, THICKNESS)
            _add_planar_quad(mesh, x0, x1, y0, y1, 0.0, reverse=True)

    for cx, cy in _hole_centers():
        _add_hole_annulus_faces(mesh, cx, cy, THICKNESS, reverse=False)
        _add_hole_annulus_faces(mesh, cx, cy, 0.0, reverse=True)


def _add_hole_annulus_faces(mesh, cx, cy, z, reverse=False):
    radius = HOLE_DIAMETER / 2.0
    outer_points = []
    inner_points = []
    for index in range(HOLE_SEGMENTS):
        angle = 2.0 * math.pi * index / HOLE_SEGMENTS
        outer_points.append(_square_point_on_ray(cx, cy, angle, radius))
        inner_points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))

    outer_vertices = [mesh.vertex(x, y, z) for x, y in outer_points]
    inner_vertices = [mesh.vertex(x, y, z) for x, y in inner_points]
    for index in range(HOLE_SEGMENTS):
        next_index = (index + 1) % HOLE_SEGMENTS
        if reverse:
            mesh.quad(
                inner_vertices[index],
                inner_vertices[next_index],
                outer_vertices[next_index],
                outer_vertices[index],
            )
        else:
            mesh.quad(
                outer_vertices[index],
                outer_vertices[next_index],
                inner_vertices[next_index],
                inner_vertices[index],
            )


def _add_vertical_faces(mesh):
    corners = (
        (0.0, 0.0),
        (LENGTH, 0.0),
        (LENGTH, WIDTH),
        (0.0, WIDTH),
    )
    for index, (x0, y0) in enumerate(corners):
        x1, y1 = corners[(index + 1) % len(corners)]
        bottom_a = mesh.vertex(x0, y0, 0.0)
        bottom_b = mesh.vertex(x1, y1, 0.0)
        top_b = mesh.vertex(x1, y1, THICKNESS)
        top_a = mesh.vertex(x0, y0, THICKNESS)
        mesh.quad(bottom_a, bottom_b, top_b, top_a)

    radius = HOLE_DIAMETER / 2.0
    for cx, cy in _hole_centers():
        top = []
        bottom = []
        for index in range(HOLE_SEGMENTS):
            angle = 2.0 * math.pi * index / HOLE_SEGMENTS
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            top.append(mesh.vertex(x, y, THICKNESS))
            bottom.append(mesh.vertex(x, y, 0.0))
        for index in range(HOLE_SEGMENTS):
            next_index = (index + 1) % HOLE_SEGMENTS
            mesh.quad(
                bottom[index],
                top[index],
                top[next_index],
                bottom[next_index],
            )


def _write_plate_obj(path):
    mesh = ObjMesh()
    _add_top_bottom_faces(mesh)
    _add_vertical_faces(mesh)
    mesh.write(path)


def _import_obj(work_part, obj_path):
    importer = NXOpen.Session.GetSession().DexManager.CreateWavefrontObjImporter()
    try:
        importer.InputFile = str(obj_path)
        importer.ImportTo = NXOpen.WavefrontObjImporter.ImportToOption.WorkPart
        importer.ImportAs = NXOpen.WavefrontObjImporter.ImportAsOption.ConvergentGeometry
        importer.ImportUnits = NXOpen.WavefrontObjImporter.UnitsEnum.Millimeters
        importer.Commit()
    finally:
        importer.Destroy()


def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    obj_path = output_path.with_suffix(".obj")
    _write_plate_obj(obj_path)

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    _import_obj(work_part, obj_path)

    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"Created 100x60x10 plate with 4x D8 corner holes: {output_path}")


if __name__ == "__main__":
    main()
