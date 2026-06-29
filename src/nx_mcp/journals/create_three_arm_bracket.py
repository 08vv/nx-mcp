"""
create_three_arm_bracket.py
===========================
NX Journal (run via run_journal.exe) that creates a parametric 3-arm linkage
bracket with a rectangular central block and three arms (two flat, one tilted).

Geometry
--------
  1. Central block: BLOCK_WIDTH x BLOCK_DEPTH x BLOCK_HEIGHT, centred on origin.
  2. Arm 1 (+X): flat horizontal arm from the right face, Z = 0.
  3. Arm 2 (-Y): flat horizontal arm from the front face, Z = 0.
  4. Arm 3 (+X+Z): tilted arm from the top face, rotated 45 deg about Y.
  5. Each arm: semicylinder tip cap and through-hole at the rounded end.
  6. Boolean union into a single solid body.

Named Expressions
-----------------
  ARM_LENGTH     = 110 mm
  ARM_WIDTH      =  22 mm
  ARM_THICKNESS  =   8 mm
  HOLE_DIAMETER  =  10 mm
  BLOCK_WIDTH    =  22 mm
  BLOCK_HEIGHT   =  35 mm
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
BLOCK_HEIGHT  =  35.0
BLOCK_DEPTH   =  22.0
TILT_ANGLE    =  45.0   # degrees — rotate arm 3 about Y toward +X+Z
ARM_OVERLAP   =  10.0   # mm overlap into block for reliable boolean union


# ---------------------------------------------------------------------------
def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "three_arm_bracket.prt"


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
    """Axis-aligned block from *corner* with expression-string edge lengths."""
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
    """Cylinder at Point3d *origin* along *dir_vec*."""
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


def _extrude_rect(work_part, corners, extrude_origin, extrude_dir, height_expr):
    """Extrude a closed rectangle (4 Point3d corners) along *extrude_dir*."""
    lines = [
        work_part.Curves.CreateLine(corners[0], corners[1]),
        work_part.Curves.CreateLine(corners[1], corners[2]),
        work_part.Curves.CreateLine(corners[2], corners[3]),
        work_part.Curves.CreateLine(corners[3], corners[0]),
    ]
    section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
    rules = [work_part.ScRuleFactory.CreateRuleCurveDumb([ln]) for ln in lines]
    section.AddToSection(
        rules, lines[0],
        NXOpen.NXObject.Null, NXOpen.NXObject.Null,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create, False,
    )
    builder = work_part.Features.CreateExtrudeBuilder(
        NXOpen.Features.Feature.Null)
    try:
        builder.Section = section
        nx_dir = work_part.Directions.CreateDirection(
            extrude_origin, extrude_dir,
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Direction = nx_dir
        builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        builder.Limits.EndExtend.Value.RightHandSide   = height_expr
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


# ---------------------------------------------------------------------------
# Build one flat arm on the Z = 0 plane
# ---------------------------------------------------------------------------
def _build_flat_arm_x(work_part, main_body, half_bw, half_aw):
    """Flat arm extending in +X from the right face of the central block."""
    z_axis = NXOpen.Vector3d(0.0, 0.0, 1.0)
    corner = NXOpen.Point3d(half_bw, -half_aw, 0.0)
    tip_x = half_bw + ARM_LENGTH

    print("[...] Creating Arm 1 (+X flat bar)...")
    arm_body = _create_block(work_part, corner, "ARM_LENGTH", "ARM_WIDTH", "ARM_THICKNESS")
    print("[OK]  Arm 1 bar created.")

    tip = NXOpen.Point3d(tip_x, 0.0, 0.0)
    cap_body = _create_cylinder(work_part, tip, z_axis, "ARM_WIDTH", "ARM_THICKNESS")
    _perform_unite(work_part, arm_body, cap_body)
    print("[OK]  Arm 1 cap united.")

    _perform_unite(work_part, main_body, arm_body)
    print("[OK]  Arm 1 united with block.")

    hole_origin = NXOpen.Point3d(tip_x, 0.0, -1.0)
    hole_body = _create_cylinder(work_part, hole_origin, z_axis,
                                 "HOLE_DIAMETER", "ARM_THICKNESS + 2.0")
    _perform_subtract(work_part, main_body, hole_body)
    print("[OK]  Arm 1 hole subtracted.")


def _build_flat_arm_neg_y(work_part, main_body, half_bd, half_aw):
    """Flat arm extending in -Y from the front face of the central block."""
    z_axis = NXOpen.Vector3d(0.0, 0.0, 1.0)
    corner = NXOpen.Point3d(-half_aw, -half_bd - ARM_LENGTH, 0.0)
    tip_y = -half_bd - ARM_LENGTH

    print("[...] Creating Arm 2 (-Y flat bar)...")
    arm_body = _create_block(work_part, corner, "ARM_WIDTH", "ARM_LENGTH", "ARM_THICKNESS")
    print("[OK]  Arm 2 bar created.")

    tip = NXOpen.Point3d(0.0, tip_y, 0.0)
    cap_body = _create_cylinder(work_part, tip, z_axis, "ARM_WIDTH", "ARM_THICKNESS")
    _perform_unite(work_part, arm_body, cap_body)
    print("[OK]  Arm 2 cap united.")

    _perform_unite(work_part, main_body, arm_body)
    print("[OK]  Arm 2 united with block.")

    hole_origin = NXOpen.Point3d(0.0, tip_y, -1.0)
    hole_body = _create_cylinder(work_part, hole_origin, z_axis,
                                 "HOLE_DIAMETER", "ARM_THICKNESS + 2.0")
    _perform_subtract(work_part, main_body, hole_body)
    print("[OK]  Arm 2 hole subtracted.")


# ---------------------------------------------------------------------------
# Build tilted arm (45 deg about Y toward +X+Z from top face)
# ---------------------------------------------------------------------------
def _build_tilted_arm(work_part, main_body):
    """Tilted arm rising from the top face, rotated 45 deg about Y."""
    tilt_rad = math.radians(TILT_ANGLE)
    cos_t = math.cos(tilt_rad)
    sin_t = math.sin(tilt_rad)
    hw = ARM_WIDTH / 2.0

    # Unit vectors for arm oriented by 45-deg rotation about Y from +X
    u_len = (cos_t, 0.0, sin_t)        # length toward +X+Z
    u_wid = (0.0, 1.0, 0.0)            # width along Y
    u_thk = (-sin_t, 0.0, cos_t)       # thickness (extrude direction)

    base_x, base_y, base_z = 0.0, 0.0, BLOCK_HEIGHT
    inner_x = base_x - ARM_OVERLAP * u_len[0]
    inner_y = base_y - ARM_OVERLAP * u_len[1]
    inner_z = base_z - ARM_OVERLAP * u_len[2]

    tip_x = base_x + (ARM_LENGTH - ARM_OVERLAP) * u_len[0]
    tip_y = base_y + (ARM_LENGTH - ARM_OVERLAP) * u_len[1]
    tip_z = base_z + (ARM_LENGTH - ARM_OVERLAP) * u_len[2]
    tip = NXOpen.Point3d(tip_x, tip_y, tip_z)

    def _pt(ax, ay, az):
        return NXOpen.Point3d(ax, ay, az)

    def _add(base, scale, vec):
        return (base[0] + scale * vec[0],
                base[1] + scale * vec[1],
                base[2] + scale * vec[2])

    inner = (inner_x, inner_y, inner_z)
    c1 = _pt(*_add(inner,  hw, u_wid))
    c2 = _pt(*_add(inner, -hw, u_wid))
    c3 = _pt(*_add((tip_x, tip_y, tip_z), -hw, u_wid))
    c4 = _pt(*_add((tip_x, tip_y, tip_z),  hw, u_wid))

    u_thk_vec = NXOpen.Vector3d(*u_thk)
    ext_origin = NXOpen.Point3d(base_x, base_y, base_z)

    print("[...] Creating Arm 3 (tilted +X+Z bar)...")
    arm_body = _extrude_rect(work_part, [c1, c2, c3, c4],
                             ext_origin, u_thk_vec, "ARM_THICKNESS")
    print("[OK]  Arm 3 bar extruded.")

    cap_body = _create_cylinder(work_part, tip, u_thk_vec,
                                "ARM_WIDTH", "ARM_THICKNESS")
    _perform_unite(work_part, arm_body, cap_body)
    print("[OK]  Arm 3 cap united.")

    _perform_unite(work_part, main_body, arm_body)
    print("[OK]  Arm 3 united with block.")

    session = NXOpen.Session.GetSession()
    session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)

    hole_origin = NXOpen.Point3d(tip_x - u_thk[0],
                                 tip_y - u_thk[1],
                                 tip_z - u_thk[2])
    hole_body = _create_cylinder(work_part, hole_origin, u_thk_vec,
                                 "HOLE_DIAMETER", "ARM_THICKNESS + 2.0")
    _perform_subtract(work_part, main_body, hole_body)
    print("[OK]  Arm 3 hole subtracted.")


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
    print("  CREATING PARAMETRIC 3-ARM LINKAGE BRACKET")
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

    half_bw = BLOCK_WIDTH / 2.0
    half_bd = BLOCK_DEPTH / 2.0
    half_aw = ARM_WIDTH / 2.0

    # ------------------------------------------------------------------
    # 2. Central block (centred on origin, base at Z = 0)
    # ------------------------------------------------------------------
    print("[...] Creating central block...")
    block_corner = NXOpen.Point3d(-half_bw, -half_bd, 0.0)
    main_body = _create_block(work_part, block_corner,
                              "BLOCK_WIDTH", "BLOCK_DEPTH", "BLOCK_HEIGHT")
    print("[OK] Central block created.")

    # ------------------------------------------------------------------
    # 3. Flat arms on base plane (Z = 0)
    # ------------------------------------------------------------------
    _build_flat_arm_x(work_part, main_body, half_bw, half_aw)
    _build_flat_arm_neg_y(work_part, main_body, half_bd, half_aw)

    # ------------------------------------------------------------------
    # 4. Tilted arm from top face
    # ------------------------------------------------------------------
    _build_tilted_arm(work_part, main_body)

    # ------------------------------------------------------------------
    # 5. Save
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
    # 6. Update result files
    # ------------------------------------------------------------------
    try:
        abs_str = str(output_path.resolve())
        project_root = Path(__file__).parent.parent.parent.parent.resolve()
        (project_root / "latest_nx_result.txt").write_text(abs_str, encoding="utf-8")
        (output_path.parent / "latest_nx_result.txt").write_text(abs_str, encoding="utf-8")
        cmd = '@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{}"\n'.format(abs_str)
        (project_root / "open_current_nx_result.cmd").write_text(cmd, encoding="utf-8")
        print("[OK] Result files updated.")
    except Exception as exc:
        print("[WARN] Could not update result files: {}".format(exc))

    # ------------------------------------------------------------------
    # 7. Auto-open in NX
    # ------------------------------------------------------------------
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

    print("[DONE] 3-arm linkage bracket complete.")


if __name__ == "__main__":
    main()
