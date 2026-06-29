"""
create_spur_gear_part.py
========================
NX Journal (run via run_journal.exe / NX Python) that creates a parametric
spur gear with hub, bore, and lightening holes.  All dimensions are stored
as named NX Expressions so the model can be driven parametrically.

Spur Gear Specification
-----------------------
  OUTER_DIAMETER            = 90 mm   (tip circle / gear OD)
  TOOTH_COUNT               = 28
  FACE_WIDTH                = 20 mm   (gear tooth width along axis)
  HUB_DIAMETER              = 28 mm
  HUB_LENGTH                = 60 mm   (extends beyond gear face)
  BORE_DIAMETER             = 14 mm   (central shaft hole)
  LIGHTENING_HOLE_DIAMETER  = 20 mm
  LIGHTENING_HOLE_PCD       = 52 mm   (pitch circle for lightening holes)
  LIGHTENING_HOLE_COUNT     = 4

Derived (standard involute spur-gear relations)
------------------------------------------------
  MODULE          = OUTER_DIAMETER / (TOOTH_COUNT + 2)
  PITCH_DIAMETER  = MODULE * TOOTH_COUNT
  ROOT_DIAMETER   = PITCH_DIAMETER - 2.5 * MODULE
  ADDENDUM        = MODULE
  DEDENDUM        = 1.25 * MODULE
  TOOTH_THICKNESS = pi * MODULE / 2

Construction
------------
  1.  Gear blank cylinder (OUTER_DIAMETER x FACE_WIDTH)
  2.  28 tooth-space cuts (profile extrude + boolean subtract)
  3.  Hub cylinder united with gear body
  4.  Bore cylinder subtracted
  5.  4 lightening holes on PCD, subtracted

Usage
-----
  run_journal.exe create_spur_gear_part.py [output_path.prt]
"""

import math
import sys
import os
from pathlib import Path
import subprocess

import NXOpen

# ---------------------------------------------------------------------------
# Parametric constants
# ---------------------------------------------------------------------------
OUTER_DIAMETER = 90.0
TOOTH_COUNT = 28
FACE_WIDTH = 20.0
HUB_DIAMETER = 28.0
HUB_LENGTH = 60.0
BORE_DIAMETER = 14.0
LIGHTENING_HOLE_DIAMETER = 20.0
LIGHTENING_HOLE_PCD = 52.0
LIGHTENING_HOLE_COUNT = 4

# Derived from standard involute gear relations
MODULE = OUTER_DIAMETER / (TOOTH_COUNT + 2)          # 3.0 mm
PITCH_DIAMETER = MODULE * TOOTH_COUNT                 # 84.0 mm
ROOT_DIAMETER = PITCH_DIAMETER - 2.5 * MODULE         # 76.5 mm
ADDENDUM = MODULE                                     # 3.0 mm
DEDENDUM = 1.25 * MODULE                              # 3.75 mm
TOOTH_THICKNESS = math.pi * MODULE / 2.0              # ~4.712 mm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _output_path():
    """Return resolved output .prt path (from argv or default)."""
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd().joinpath("spur_gear_28T_m3.prt").resolve()


def _perform_subtract(work_part, target_body, tool_body):
    """Boolean subtract tool_body from target_body."""
    builder = work_part.Features.CreateBooleanBuilder(
        NXOpen.Features.BooleanFeature.Null
    )
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body)
                    break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body)
                    break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()


def _perform_unite(work_part, target_body, tool_body):
    """Boolean unite tool_body into target_body."""
    builder = work_part.Features.CreateBooleanBuilder(
        NXOpen.Features.BooleanFeature.Null
    )
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body)
                    break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body)
                    break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()


def _create_cylinder(work_part, origin, diameter_expr, height_expr):
    """Create a cylinder feature driven by expression strings.

    Returns the body object.
    """
    builder = work_part.Features.CreateCylinderBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        dir_vector = NXOpen.Vector3d(0.0, 0.0, 1.0)
        direction = work_part.Directions.CreateDirection(
            origin, dir_vector, NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        builder.Diameter.RightHandSide = diameter_expr
        builder.Height.RightHandSide = height_expr
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = direction
        feat = builder.Commit()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


def _create_tooth_space_cut(work_part, slot_index, total_teeth,
                             root_radius, outer_radius):
    """Create one tooth-space cutting body.

    Builds a closed profile (2 lines + 2 arcs) on the XY plane describing
    the inter-tooth slot, then extrudes it along Z for FACE_WIDTH.

    Returns the extruded body.
    """
    angular_pitch = 2.0 * math.pi / total_teeth

    # Space centre is halfway between tooth i and tooth i+1
    space_centre = slot_index * angular_pitch + angular_pitch / 2.0

    # Half angular width of the space at the pitch circle
    pitch_radius = PITCH_DIAMETER / 2.0
    space_half_angle = (TOOTH_THICKNESS / 2.0) / pitch_radius

    a_left = space_centre - space_half_angle
    a_right = space_centre + space_half_angle

    # Cutting radius extends slightly beyond the tip for a clean boolean
    cut_r = outer_radius + 1.0
    root_r = root_radius

    # Four corners of the closed profile
    P1 = NXOpen.Point3d(root_r * math.cos(a_left),
                        root_r * math.sin(a_left), 0.0)
    P2 = NXOpen.Point3d(cut_r * math.cos(a_left),
                        cut_r * math.sin(a_left), 0.0)
    P3 = NXOpen.Point3d(cut_r * math.cos(a_right),
                        cut_r * math.sin(a_right), 0.0)
    P4 = NXOpen.Point3d(root_r * math.cos(a_right),
                        root_r * math.sin(a_right), 0.0)

    centre = NXOpen.Point3d(0.0, 0.0, 0.0)
    orientation = work_part.WCS.CoordinateSystem.Orientation

    # Create 2 radial lines + 2 arcs forming a closed loop
    line_left = work_part.Curves.CreateLine(P1, P2)
    arc_outer = work_part.Curves.CreateArc(centre, orientation, cut_r,
                                           a_left, a_right)
    line_right = work_part.Curves.CreateLine(P3, P4)
    arc_root = work_part.Curves.CreateArc(centre, orientation, root_r,
                                          a_left, a_right)

    curves = [line_left, arc_outer, line_right, arc_root]

    # Build section and extrude
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

        dir_vec = NXOpen.Vector3d(0.0, 0.0, 1.0)
        direction = work_part.Directions.CreateDirection(
            centre, dir_vec, NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        builder.Direction = direction
        builder.Limits.StartExtend.Value.RightHandSide = "0"
        builder.Limits.EndExtend.Value.RightHandSide = "FACE_WIDTH"

        feat = builder.CommitFeature()
    finally:
        builder.Destroy()

    return feat.GetBodies()[0]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            output_path.unlink()
            print("[OK] Removed existing part file: {}".format(output_path))
        except Exception as exc:
            print("[WARN] Could not remove existing file: {}".format(exc))

    # Open a new empty part
    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    # ------------------------------------------------------------------
    # 1.  Register named NX Expressions (all nine user parameters + derived)
    # ------------------------------------------------------------------
    named_expressions = [
        # User-facing parameters
        ("OUTER_DIAMETER",           OUTER_DIAMETER),
        ("TOOTH_COUNT",              TOOTH_COUNT),
        ("FACE_WIDTH",               FACE_WIDTH),
        ("HUB_DIAMETER",             HUB_DIAMETER),
        ("HUB_LENGTH",               HUB_LENGTH),
        ("BORE_DIAMETER",            BORE_DIAMETER),
        ("LIGHTENING_HOLE_DIAMETER", LIGHTENING_HOLE_DIAMETER),
        ("LIGHTENING_HOLE_PCD",      LIGHTENING_HOLE_PCD),
        ("LIGHTENING_HOLE_COUNT",    LIGHTENING_HOLE_COUNT),
        # Derived helpers
        ("MODULE",                   MODULE),
        ("PITCH_DIAMETER",           PITCH_DIAMETER),
        ("ROOT_DIAMETER",            ROOT_DIAMETER),
        ("ADDENDUM",                 ADDENDUM),
        ("DEDENDUM",                 DEDENDUM),
        ("TOOTH_THICKNESS",          TOOTH_THICKNESS),
    ]
    for name, value in named_expressions:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))

    print("[OK] Named expressions created:")
    for name, value in named_expressions:
        print("     {} = {}".format(name, value))

    # ------------------------------------------------------------------
    # 2.  Gear blank — outer cylinder along Z
    # ------------------------------------------------------------------
    origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    gear_body = _create_cylinder(work_part, origin,
                                 "OUTER_DIAMETER", "FACE_WIDTH")
    print("[OK] Gear blank cylinder  (D={} x H={} mm)".format(
        OUTER_DIAMETER, FACE_WIDTH))

    # ------------------------------------------------------------------
    # 3.  Cut tooth spaces — 28 profile extrudes subtracted from blank
    # ------------------------------------------------------------------
    outer_r = OUTER_DIAMETER / 2.0
    root_r = ROOT_DIAMETER / 2.0
    N = int(TOOTH_COUNT)

    for i in range(N):
        slot_body = _create_tooth_space_cut(
            work_part, i, N, root_r, outer_r
        )
        _perform_subtract(work_part, gear_body, slot_body)
        if (i + 1) % 7 == 0 or i == N - 1:
            print("[OK] Tooth spaces cut: {}/{}".format(i + 1, N))

    # ------------------------------------------------------------------
    # 4.  Hub — cylinder at origin, united with gear body
    # ------------------------------------------------------------------
    hub_body = _create_cylinder(work_part, origin,
                                "HUB_DIAMETER", "HUB_LENGTH")
    _perform_unite(work_part, gear_body, hub_body)
    print("[OK] Hub united  (D={} x L={} mm)".format(
        HUB_DIAMETER, HUB_LENGTH))

    # ------------------------------------------------------------------
    # 5.  Bore — through the hub
    # ------------------------------------------------------------------
    bore_body = _create_cylinder(work_part, origin,
                                 "BORE_DIAMETER", "HUB_LENGTH")
    _perform_subtract(work_part, gear_body, bore_body)
    print("[OK] Bore subtracted  (D={} mm)".format(BORE_DIAMETER))

    # ------------------------------------------------------------------
    # 6.  Lightening holes — associative positions on PCD
    #     Uses expression-driven scalars and points so the hole centres
    #     update when LIGHTENING_HOLE_PCD or _COUNT change.
    # ------------------------------------------------------------------
    csys = work_part.WCS.CoordinateSystem
    lh_count = int(LIGHTENING_HOLE_COUNT)

    for i in range(lh_count):
        # Coordinate expressions (parametric, reference user expressions)
        expr_x = work_part.Expressions.CreateExpression(
            "Number",
            "LH_X_{0} = (LIGHTENING_HOLE_PCD / 2.0) * cos({0} * 360.0 / LIGHTENING_HOLE_COUNT)".format(i),
        )
        expr_y = work_part.Expressions.CreateExpression(
            "Number",
            "LH_Y_{0} = (LIGHTENING_HOLE_PCD / 2.0) * sin({0} * 360.0 / LIGHTENING_HOLE_COUNT)".format(i),
        )
        expr_z = work_part.Expressions.CreateExpression(
            "Number", "LH_Z_{} = 0.0".format(i),
        )

        # Associative scalars + point (update when expressions change)
        x_scalar = work_part.Scalars.CreateScalarExpression(
            expr_x, NXOpen.Scalar.DimensionalityType.NotSet,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        y_scalar = work_part.Scalars.CreateScalarExpression(
            expr_y, NXOpen.Scalar.DimensionalityType.NotSet,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        z_scalar = work_part.Scalars.CreateScalarExpression(
            expr_z, NXOpen.Scalar.DimensionalityType.NotSet,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        assoc_point = work_part.Points.CreatePoint(
            csys, x_scalar, y_scalar, z_scalar,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )

        # Create cylinder at associative point
        lh_builder = work_part.Features.CreateCylinderBuilder(
            NXOpen.Features.Feature.Null
        )
        try:
            lh_builder.Diameter.RightHandSide = "LIGHTENING_HOLE_DIAMETER"
            lh_builder.Height.RightHandSide = "FACE_WIDTH"
            lh_builder.Axis.Point = assoc_point
            dir_vec = NXOpen.Vector3d(0.0, 0.0, 1.0)
            direction = work_part.Directions.CreateDirection(
                assoc_point, dir_vec,
            )
            lh_builder.Axis.Direction = direction
            lh_feat = lh_builder.Commit()
        finally:
            lh_builder.Destroy()

        lh_body = lh_feat.GetBodies()[0]
        _perform_subtract(work_part, gear_body, lh_body)

        angle_deg = i * 360.0 / lh_count
        cx = (LIGHTENING_HOLE_PCD / 2.0) * math.cos(math.radians(angle_deg))
        cy = (LIGHTENING_HOLE_PCD / 2.0) * math.sin(math.radians(angle_deg))
        print("[OK] Lightening hole {}/{} at ({:.1f}, {:.1f})".format(
            i + 1, lh_count, cx, cy))

    # ------------------------------------------------------------------
    # 7.  Fit view, save part
    # ------------------------------------------------------------------
    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("[OK] Part saved -> {}".format(output_path))

    # ------------------------------------------------------------------
    # 8.  Update watcher files
    # ------------------------------------------------------------------
    try:
        latest_file = output_path.parent / "latest_nx_result.txt"
        latest_file.write_text(str(output_path.resolve()), encoding="utf-8")
        print("[OK] latest_nx_result.txt updated")
    except Exception as exc:
        print("[WARN] Could not update latest_nx_result.txt: {}".format(exc))

    # ------------------------------------------------------------------
    # 9.  Auto-open the .prt in the Siemens NX GUI
    # ------------------------------------------------------------------
    try:
        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        router_candidates = [
            base_path / "NXBIN" / "ugs_router.exe",
            base_path / "UGII" / "ugs_router.exe",
        ]
        ugs_router = next((c for c in router_candidates if c.exists()), None)
        if ugs_router:
            subprocess.Popen(
                [str(ugs_router), "-ug", "-use_file_dir",
                 str(output_path.resolve())]
            )
            print("[OK] NX GUI launched -> opening {}".format(output_path.name))
        else:
            print("[WARN] ugs_router.exe not found - open the part manually")
    except Exception as exc:
        print("[WARN] Could not auto-open in NX GUI: {}".format(exc))


if __name__ == "__main__":
    main()
