"""
create_linkage_bracket.py
=========================
NX Journal that creates a parametric linkage bracket: central block,
flat arms in -X and -Y (90-degree L-shape from above), and a tilted
arm from a rotated block (no extrude/revolve on that arm).

Named Expressions
-----------------
  ARM_LENGTH     = 110 mm
  ARM_WIDTH      =  22 mm
  ARM_THICKNESS  =   8 mm
  HOLE_DIAMETER  =  10 mm
  BLOCK_WIDTH    =  22 mm
  BLOCK_HEIGHT   =  40 mm
  BLOCK_DEPTH    =  22 mm
"""

import sys
import os
import math
from pathlib import Path
import subprocess

import NXOpen
import NXOpen.UF


# ---------------------------------------------------------------------------
# Default parametric constants (mm)
# ---------------------------------------------------------------------------
ARM_LENGTH    = 110.0
ARM_WIDTH     =  22.0
ARM_THICKNESS =   8.0
HOLE_DIAMETER =  10.0
BLOCK_WIDTH   =  22.0
BLOCK_HEIGHT  =  40.0
BLOCK_DEPTH   =  22.0
TILT_ANGLE    =  45.0    # deg about Y at pivot (0,0,BLOCK_HEIGHT) -> rises +X+Z


# ---------------------------------------------------------------------------
def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "linkage_bracket.prt"


# ---------------------------------------------------------------------------
# Boolean helpers
# ---------------------------------------------------------------------------
def _perform_subtract(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(
        NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body); break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body); break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()


def _perform_unite(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(
        NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body); break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body); break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _create_block(work_part, corner, lx, ly, lz):
    builder = work_part.Features.CreateBlockFeatureBuilder(
        NXOpen.Features.Feature.Null)
    try:
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(corner, str(lx), str(ly), str(lz))
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


def _create_cylinder(work_part, origin, dir_vec, diam_expr, height_expr):
    builder = work_part.Features.CreateCylinderBuilder(
        NXOpen.Features.Feature.Null)
    try:
        direction = work_part.Directions.CreateDirection(
            origin, dir_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Diameter.RightHandSide = diam_expr
        builder.Height.RightHandSide   = height_expr
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = direction
        feat = builder.Commit()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


def _rotate_body_about_y(work_part, body, pivot, angle_deg):
    """Rotate *body* in-place about Y through *pivot* (positive angle -> +X toward +Z)."""
    builder = work_part.BaseFeatures.CreateMoveObjectBuilder(
        NXOpen.Features.MoveObject.Null)
    try:
        builder.MoveParents = False
        builder.Associative = False
        result_opts = NXOpen.Features.MoveObjectBuilder.MoveObjectResultOptions
        builder.MoveObjectResult = result_opts.MoveOriginal
        builder.ObjectToMoveObject.Add(body)
        builder.TransformMotion.Option = (
            NXOpen.GeometricUtilities.ModlMotion.Options.Angle)
        builder.TransformMotion.Angle.RightHandSide = str(angle_deg)
        # Negative Y axis so +45 deg rotates +X toward +Z (upper-right in XZ)
        y_vec = NXOpen.Vector3d(0.0, -1.0, 0.0)
        axis = work_part.Axes.CreateAxis(
            pivot, y_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.TransformMotion.AngularAxis = axis
        builder.Commit()
    finally:
        builder.Destroy()


def _rotate_point_about_y(point, pivot, angle_deg):
    """Return Point3d after +45-about-Y rotation (+X toward +Z)."""
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    dx = point.X - pivot.X
    dy = point.Y - pivot.Y
    dz = point.Z - pivot.Z
    rx = cos_a * dx - sin_a * dz
    ry = dy
    rz = sin_a * dx + cos_a * dz
    return NXOpen.Point3d(pivot.X + rx, pivot.Y + ry, pivot.Z + rz)


def _rotate_vector_about_y(vec, angle_deg):
    """Return Vector3d after +45-about-Y rotation (+X toward +Z)."""
    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)
    rx = cos_a * vec.X - sin_a * vec.Z
    ry = vec.Y
    rz = sin_a * vec.X + cos_a * vec.Z
    return NXOpen.Vector3d(rx, ry, rz)


def _solid_body_count(work_part):
    return len([b for b in work_part.Bodies if b.IsSolidBody])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            output_path.unlink()
            print("[OK] Removed existing file: {}".format(output_path))
        except Exception as exc:
            print("[WARN] Could not remove: {}".format(exc))

    session   = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    print("=" * 60)
    print("  CREATING PARAMETRIC LINKAGE BRACKET")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Named expressions
    # ------------------------------------------------------------------
    for name, val in [("ARM_LENGTH",    ARM_LENGTH),
                      ("ARM_WIDTH",     ARM_WIDTH),
                      ("ARM_THICKNESS", ARM_THICKNESS),
                      ("HOLE_DIAMETER", HOLE_DIAMETER),
                      ("BLOCK_WIDTH",   BLOCK_WIDTH),
                      ("BLOCK_HEIGHT",  BLOCK_HEIGHT),
                      ("BLOCK_DEPTH",   BLOCK_DEPTH)]:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, val))
    print("[OK] Named expressions registered.")

    z_axis = NXOpen.Vector3d(0.0, 0.0, 1.0)
    half_bw = BLOCK_WIDTH / 2.0   # 11

    # ------------------------------------------------------------------
    # Step 1 — Central vertical block
    # ------------------------------------------------------------------
    print("[...] Step 1: central vertical block...")
    block_corner = NXOpen.Point3d(-half_bw, -half_bw, 0.0)
    central_body = _create_block(work_part, block_corner,
                                 "BLOCK_WIDTH", "BLOCK_DEPTH", "BLOCK_HEIGHT")
    print("[OK]  Central block created.")

    # ------------------------------------------------------------------
    # Step 2 — Flat arm at bottom-left (−X)
    # ------------------------------------------------------------------
    print("[...] Step 2: flat arm bottom-left (-X)...")
    arm_left_corner = NXOpen.Point3d(-half_bw - ARM_LENGTH, -half_bw, 0.0)
    arm_left_body = _create_block(work_part, arm_left_corner,
                                  "ARM_LENGTH", "ARM_WIDTH", "ARM_THICKNESS")
    tip_left = NXOpen.Point3d(-half_bw - ARM_LENGTH, 0.0, 0.0)
    cap_left = _create_cylinder(work_part, tip_left, z_axis, "ARM_WIDTH", "ARM_THICKNESS")
    _perform_unite(work_part, arm_left_body, cap_left)
    print("[OK]  Left arm + cap created.")

    # ------------------------------------------------------------------
    # Step 3 -- Flat arm going forward (-Y), perpendicular to arm 1
    # ------------------------------------------------------------------
    print("[...] Step 3: flat arm forward (-Y)...")
    arm_fwd_corner = NXOpen.Point3d(-half_bw, -half_bw - ARM_LENGTH, 0.0)
    arm_fwd_body = _create_block(work_part, arm_fwd_corner,
                                 "ARM_WIDTH", "ARM_LENGTH", "ARM_THICKNESS")
    tip_fwd = NXOpen.Point3d(0.0, -half_bw - ARM_LENGTH, 0.0)
    cap_fwd = _create_cylinder(work_part, tip_fwd, z_axis, "ARM_WIDTH", "ARM_THICKNESS")
    _perform_unite(work_part, arm_fwd_body, cap_fwd)
    print("[OK]  Forward arm + cap created.")

    # ------------------------------------------------------------------
    # Step 4 — Tilted arm (block + rotate, no extrude/revolve)
    # ------------------------------------------------------------------
    print("[...] Step 4: tilted arm (block + rotate)...")
    tilt_corner = NXOpen.Point3d(-half_bw, -half_bw, BLOCK_HEIGHT)
    tilt_body = _create_block(work_part, tilt_corner,
                              "ARM_LENGTH", "ARM_WIDTH", "ARM_THICKNESS")
    pivot = NXOpen.Point3d(0.0, 0.0, BLOCK_HEIGHT)
    _rotate_body_about_y(work_part, tilt_body, pivot, TILT_ANGLE)
    print("[OK]  Tilted arm block rotated {} deg about Y.".format(TILT_ANGLE))

    # Semicylinder cap at upper tip (far end centre before rotation, then rotated)
    tip_tilt_before = NXOpen.Point3d(-half_bw + ARM_LENGTH, 0.0,
                                     BLOCK_HEIGHT + ARM_THICKNESS / 2.0)
    tip_tilt = _rotate_point_about_y(tip_tilt_before, pivot, TILT_ANGLE)
    thk_dir = _rotate_vector_about_y(z_axis, TILT_ANGLE)
    cap_tilt = _create_cylinder(work_part, tip_tilt, thk_dir,
                                "ARM_WIDTH", "ARM_THICKNESS")
    _perform_unite(work_part, tilt_body, cap_tilt)
    print("[OK]  Tilted arm cap united.")

    # ------------------------------------------------------------------
    # Step 5 — Boolean unite all four bodies
    # ------------------------------------------------------------------
    print("[...] Step 5: boolean unite all bodies...")
    main_body = central_body
    for label, tool in [("left arm", arm_left_body),
                        ("forward arm", arm_fwd_body),
                        ("tilted arm", tilt_body)]:
        _perform_unite(work_part, main_body, tool)
        print("[OK]  United {}.".format(label))

    session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)
    body_count = _solid_body_count(work_part)
    print("[INFO] Solid body count after unions: {}".format(body_count))
    if body_count != 1:
        print("[WARN] Expected 1 solid body, found {}.".format(body_count))
    else:
        print("[OK]  Body count verified: 1 solid.")

    # Through-holes at all three tips
    hole_left = _create_cylinder(work_part, tip_left, z_axis,
                                 "HOLE_DIAMETER", "10.0")
    _perform_subtract(work_part, main_body, hole_left)
    print("[OK]  Left arm hole subtracted.")

    hole_fwd = _create_cylinder(work_part, tip_fwd, z_axis,
                                "HOLE_DIAMETER", "10.0")
    _perform_subtract(work_part, main_body, hole_fwd)
    print("[OK]  Forward arm hole subtracted.")

    hole_tilt_origin = NXOpen.Point3d(
        tip_tilt.X - thk_dir.X,
        tip_tilt.Y - thk_dir.Y,
        tip_tilt.Z - thk_dir.Z,
    )
    hole_tilt = _create_cylinder(work_part, hole_tilt_origin, thk_dir,
                                 "HOLE_DIAMETER", "10.0")
    _perform_subtract(work_part, main_body, hole_tilt)
    print("[OK]  Tilted arm hole subtracted.")

    session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)
    final_count = _solid_body_count(work_part)
    print("[INFO] Final solid body count: {}".format(final_count))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("=" * 60)
    print("[OK] Part saved -> {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # Update result files & auto-open
    # ------------------------------------------------------------------
    try:
        abs_str = str(output_path.resolve())
        project_root = Path(__file__).parent.parent.parent.parent.resolve()
        (project_root / "latest_nx_result.txt").write_text(abs_str, encoding="utf-8")
        cmd = ('@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" '
               '-ug -use_file_dir "{}"\n').format(abs_str)
        (project_root / "open_current_nx_result.cmd").write_text(cmd, encoding="utf-8")
        print("[OK] Result files updated.")
    except Exception as exc:
        print("[WARN] Could not update result files: {}".format(exc))

    try:
        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        candidates = [base_path / "NXBIN" / "ugs_router.exe",
                      base_path / "UGII"  / "ugs_router.exe"]
        ugs = next((c for c in candidates if c.exists()), None)
        if ugs:
            subprocess.Popen([str(ugs), "-ug", "-use_file_dir",
                              str(output_path.resolve())])
            print("[OK] NX GUI launched -> {}".format(output_path.name))
        else:
            print("[WARN] ugs_router.exe not found.")
    except Exception as exc:
        print("[WARN] Could not auto-open: {}".format(exc))

    print("[DONE] Linkage bracket complete.")


if __name__ == "__main__":
    main()
