import math
from ..nx_session import NXSession

def make_point(x, y, z=0.0): return NXSession.nxopen().Point3d(x, y, z)
def make_vector(x, y, z=1.0): return NXSession.nxopen().Vector3d(x, y, z)

PLANE_NORMALS = {"XY":(0,0,1), "XZ":(0,1,0), "YZ":(1,0,0)}

def plane_normal(plane: str):
    if plane.upper() not in PLANE_NORMALS:
        raise ValueError(f"Unknown plane '{plane}'")
    return make_vector(*PLANE_NORMALS[plane.upper()])
