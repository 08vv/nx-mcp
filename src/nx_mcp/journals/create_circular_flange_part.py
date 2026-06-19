import math
import sys
from pathlib import Path

import NXOpen


OUTER_DIAMETER = 120.0
THICKNESS = 12.0
CENTER_BORE_DIAMETER = 40.0
BOLT_CIRCLE_DIAMETER = 90.0
BOLT_HOLE_DIAMETER = 10.0
BOLT_HOLE_COUNT = 6
ANGULAR_SEGMENTS = 384
RADIAL_SEGMENTS = 96
HOLE_SEGMENTS = 64
TOLERANCE = 1.0e-6


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd().joinpath("circular_flange_6_holes.prt").resolve()


class ObjMesh:
    def __init__(self):
        self.vertices = []
        self.faces = []

    def vertex(self, x, y, z):
        self.vertices.append((float(x), float(y), float(z)))
        return len(self.vertices)

    def face(self, *indices):
        self.faces.append(tuple(indices))

    def tri(self, a, b, c):
        self.face(a, b, c)

    def quad(self, a, b, c, d):
        self.face(a, b, c)
        self.face(a, c, d)

    def write(self, path):
        with path.open("w", encoding="ascii") as stream:
            stream.write("# circular flange OD120 T12 bore40 6xD10 on PCD90\n")
            for x, y, z in self.vertices:
                stream.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
            for face in self.faces:
                stream.write("f " + " ".join(str(index) for index in face) + "\n")


def _bolt_hole_centers():
    radius = BOLT_CIRCLE_DIAMETER / 2.0
    for index in range(BOLT_HOLE_COUNT):
        angle = 2.0 * math.pi * index / BOLT_HOLE_COUNT
        yield radius * math.cos(angle), radius * math.sin(angle)


def _inside_bolt_hole(x, y):
    hole_radius = BOLT_HOLE_DIAMETER / 2.0
    for cx, cy in _bolt_hole_centers():
        if math.hypot(x - cx, y - cy) < hole_radius - TOLERANCE:
            return True
    return False


def _inside_material(x, y):
    radius = math.hypot(x, y)
    return (
        CENTER_BORE_DIAMETER / 2.0 + TOLERANCE
        < radius
        < OUTER_DIAMETER / 2.0 - TOLERANCE
        and not _inside_bolt_hole(x, y)
    )


def _polar_point(radius, angle):
    return radius * math.cos(angle), radius * math.sin(angle)


def _add_planar_mesh(mesh, z, reverse=False):
    inner_radius = CENTER_BORE_DIAMETER / 2.0
    outer_radius = OUTER_DIAMETER / 2.0
    radial_step = (outer_radius - inner_radius) / RADIAL_SEGMENTS
    angular_step = 2.0 * math.pi / ANGULAR_SEGMENTS

    for radial_index in range(RADIAL_SEGMENTS):
        r0 = inner_radius + radial_step * radial_index
        r1 = r0 + radial_step
        mid_radius = (r0 + r1) / 2.0
        for angular_index in range(ANGULAR_SEGMENTS):
            a0 = angular_step * angular_index
            a1 = angular_step * (angular_index + 1)
            mid_angle = (a0 + a1) / 2.0
            mid_x, mid_y = _polar_point(mid_radius, mid_angle)
            if not _inside_material(mid_x, mid_y):
                continue

            p00 = (*_polar_point(r0, a0), z)
            p10 = (*_polar_point(r1, a0), z)
            p11 = (*_polar_point(r1, a1), z)
            p01 = (*_polar_point(r0, a1), z)
            vertices = [mesh.vertex(*point) for point in (p00, p10, p11, p01)]
            if reverse:
                mesh.quad(vertices[3], vertices[2], vertices[1], vertices[0])
            else:
                mesh.quad(vertices[0], vertices[1], vertices[2], vertices[3])


def _add_cylindrical_wall(mesh, radius, reverse=False):
    top = []
    bottom = []
    for index in range(ANGULAR_SEGMENTS):
        angle = 2.0 * math.pi * index / ANGULAR_SEGMENTS
        x, y = _polar_point(radius, angle)
        bottom.append(mesh.vertex(x, y, 0.0))
        top.append(mesh.vertex(x, y, THICKNESS))

    for index in range(ANGULAR_SEGMENTS):
        next_index = (index + 1) % ANGULAR_SEGMENTS
        if reverse:
            mesh.quad(bottom[index], top[index], top[next_index], bottom[next_index])
        else:
            mesh.quad(bottom[next_index], top[next_index], top[index], bottom[index])


def _add_hole_wall(mesh, cx, cy, radius):
    top = []
    bottom = []
    for index in range(HOLE_SEGMENTS):
        angle = 2.0 * math.pi * index / HOLE_SEGMENTS
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        bottom.append(mesh.vertex(x, y, 0.0))
        top.append(mesh.vertex(x, y, THICKNESS))

    for index in range(HOLE_SEGMENTS):
        next_index = (index + 1) % HOLE_SEGMENTS
        mesh.quad(bottom[index], top[index], top[next_index], bottom[next_index])


def _write_flange_obj(path):
    mesh = ObjMesh()
    _add_planar_mesh(mesh, THICKNESS)
    _add_planar_mesh(mesh, 0.0, reverse=True)
    _add_cylindrical_wall(mesh, OUTER_DIAMETER / 2.0)
    _add_cylindrical_wall(mesh, CENTER_BORE_DIAMETER / 2.0, reverse=True)

    for cx, cy in _bolt_hole_centers():
        _add_hole_wall(mesh, cx, cy, BOLT_HOLE_DIAMETER / 2.0)

    mesh.write(path)


def _import_obj(obj_path):
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
    _write_flange_obj(obj_path)

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    _import_obj(obj_path)

    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"Created circular flange with 6 evenly spaced holes: {output_path}")


if __name__ == "__main__":
    main()
