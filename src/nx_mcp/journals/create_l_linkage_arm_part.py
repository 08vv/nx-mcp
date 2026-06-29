"""
create_l_linkage_arm_part.py
=============================
NX Journal (run via run_journal.exe / NX Python) that creates a parametric
L-shaped linkage arm as a single part.  All dimensions are stored as named
NX Expressions for fully parametric design.

L-Linkage Arm Geometry (viewed from above — Z up)
---------------------------------------------------

        +Y
        ^
        |   ╭──╮
        |   │○ │   ← Arm 2 far-end hole
        |   │  │
        |   │  │   ARM_WIDTH = 24
        |   │  │
        |   │  │
   ╭────┤   │  │
   │ ○  ├───┤  │   ← Junction hole (shared)
   ╰────┴───┴──╯────────────────────────╮
        │                        ○      │  ← Arm 1 far-end hole
        ╰───────────────────────────────╯──> +X
                    ARM_LENGTH = 120

  1. ARM 1  – flat bar along +X with rounded cylinder caps at both ends.
             Through-hole at each end, inset HOLE_INSET from the tip.
  2. ARM 2  – identical arm rotated 90°, extending along +Y.
             Same rounded caps and through-holes.
  3. JUNCTION – the two arms overlap in an ARM_WIDTH × ARM_WIDTH square
               at the corner and are boolean-united.  No extra block or boss.
  4. Both arms sit at the same Z height (Z = 0 to ARM_THICKNESS).

Named Expressions
-----------------
  ARM_LENGTH     = 120 mm
  ARM_WIDTH      =  24 mm
  ARM_THICKNESS  =   8 mm
  HOLE_DIAMETER  =  10 mm
  HOLE_INSET     =  12 mm

Usage
-----
  run_journal.exe create_l_linkage_arm_part.py
"""

import math
import sys
import os
from pathlib import Path
import subprocess

import NXOpen
import NXOpen.UF

# ---------------------------------------------------------------------------
# Parametric Constants (mm)
# ---------------------------------------------------------------------------
ARM_LENGTH     = 120.0
ARM_WIDTH      = 24.0
ARM_THICKNESS  = 8.0
HOLE_DIAMETER  = 10.0
HOLE_INSET     = 12.0


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
def _output_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "l_linkage_arm.prt"


# ---------------------------------------------------------------------------
# Helper: boolean subtract
# ---------------------------------------------------------------------------
def _perform_subtract(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
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


# ---------------------------------------------------------------------------
# Helper: boolean unite
# ---------------------------------------------------------------------------
def _perform_unite(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
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


# ---------------------------------------------------------------------------
# Helper: create a cylinder feature
# ---------------------------------------------------------------------------
def _create_cylinder(work_part, origin, direction_vec, diameter_expr, height_expr):
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        direction = work_part.Directions.CreateDirection(
            origin, direction_vec, NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        builder.Diameter.RightHandSide = diameter_expr
        builder.Height.RightHandSide   = height_expr
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = direction
        feat = builder.Commit()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


# ---------------------------------------------------------------------------
# Helper: create a block (cuboid) feature
# ---------------------------------------------------------------------------
def _create_block(work_part, corner_origin, length_str, width_str, height_str):
    builder = work_part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(corner_origin, length_str, width_str, height_str)
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
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

    session   = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    print("=" * 60)
    print("  CREATING PARAMETRIC L-SHAPED LINKAGE ARM (no block)")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Register named NX Expressions
    # ------------------------------------------------------------------
    named_expressions = [
        ("ARM_LENGTH",     ARM_LENGTH),
        ("ARM_WIDTH",      ARM_WIDTH),
        ("ARM_THICKNESS",  ARM_THICKNESS),
        ("HOLE_DIAMETER",  HOLE_DIAMETER),
        ("HOLE_INSET",     HOLE_INSET),
    ]
    for name, value in named_expressions:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
    print("[OK] Named expressions created.")

    # ------------------------------------------------------------------
    # Coordinate Layout (top-down view, Z up):
    #
    #   Arm 1 (along +X):
    #     X:[0, ARM_LENGTH=120], Y:[0, ARM_WIDTH=24], Z:[0, ARM_THICKNESS=8]
    #     Bar rectangle: corner (half_w, 0, 0), length=ARM_LENGTH-ARM_WIDTH
    #     Near-end cap centre: (half_w, half_w, 0) = (12, 12, 0)
    #     Far-end  cap centre: (ARM_LENGTH-half_w, half_w, 0) = (108, 12, 0)
    #
    #   Arm 2 (along +Y):
    #     X:[0, ARM_WIDTH=24], Y:[0, ARM_LENGTH=120], Z:[0, ARM_THICKNESS=8]
    #     Bar rectangle: corner (0, half_w, 0), width=ARM_LENGTH-ARM_WIDTH
    #     Near-end cap centre: (half_w, half_w, 0) = (12, 12, 0)  [shared]
    #     Far-end  cap centre: (half_w, ARM_LENGTH-half_w, 0) = (12, 108, 0)
    #
    #   Overlap region: X:[0,24], Y:[0,24] — a clean flush junction.
    # ------------------------------------------------------------------

    z_axis   = NXOpen.Vector3d(0.0, 0.0, 1.0)
    half_w   = ARM_WIDTH / 2.0            # 12.0
    bar_len  = ARM_LENGTH - ARM_WIDTH     # 96.0  (between cap centres)

    # ==================================================================
    # ARM 1  (along +X)
    # ==================================================================

    # 2a. Arm 1 rectangular bar
    print("[...] Creating Arm 1 bar...")
    arm1_corner = NXOpen.Point3d(half_w, 0.0, 0.0)
    main_body = _create_block(
        work_part, arm1_corner,
        str(bar_len), "ARM_WIDTH", "ARM_THICKNESS"
    )
    print("[OK] Arm 1 bar created ({} x {} x {} mm).".format(
        bar_len, ARM_WIDTH, ARM_THICKNESS))

    # 2b. Arm 1 near-end cylinder cap (rounded end at X = 0 tip)
    print("[...] Creating Arm 1 near-end cap...")
    near1_origin = NXOpen.Point3d(half_w, half_w, 0.0)
    near1_cap = _create_cylinder(
        work_part, near1_origin, z_axis,
        "ARM_WIDTH", "ARM_THICKNESS"
    )
    _perform_unite(work_part, main_body, near1_cap)
    print("[OK] Arm 1 near-end cap united.")

    # 2c. Arm 1 far-end cylinder cap (rounded end at X = ARM_LENGTH tip)
    print("[...] Creating Arm 1 far-end cap...")
    far1_origin = NXOpen.Point3d(ARM_LENGTH - half_w, half_w, 0.0)
    far1_cap = _create_cylinder(
        work_part, far1_origin, z_axis,
        "ARM_WIDTH", "ARM_THICKNESS"
    )
    _perform_unite(work_part, main_body, far1_cap)
    print("[OK] Arm 1 far-end cap united.")

    # ==================================================================
    # ARM 2  (along +Y) — identical arm rotated 90 degrees
    # ==================================================================

    # 3a. Arm 2 rectangular bar
    print("[...] Creating Arm 2 bar...")
    arm2_corner = NXOpen.Point3d(0.0, half_w, 0.0)
    arm2_body = _create_block(
        work_part, arm2_corner,
        "ARM_WIDTH", str(bar_len), "ARM_THICKNESS"
    )
    print("[OK] Arm 2 bar created ({} x {} x {} mm).".format(
        ARM_WIDTH, bar_len, ARM_THICKNESS))

    # 3b. Arm 2 near-end cylinder cap (at Y = 0 tip; overlaps arm 1 near cap)
    print("[...] Creating Arm 2 near-end cap...")
    near2_origin = NXOpen.Point3d(half_w, half_w, 0.0)
    near2_cap = _create_cylinder(
        work_part, near2_origin, z_axis,
        "ARM_WIDTH", "ARM_THICKNESS"
    )
    _perform_unite(work_part, arm2_body, near2_cap)
    print("[OK] Arm 2 near-end cap united.")

    # 3c. Arm 2 far-end cylinder cap (rounded end at Y = ARM_LENGTH tip)
    print("[...] Creating Arm 2 far-end cap...")
    far2_origin = NXOpen.Point3d(half_w, ARM_LENGTH - half_w, 0.0)
    far2_cap = _create_cylinder(
        work_part, far2_origin, z_axis,
        "ARM_WIDTH", "ARM_THICKNESS"
    )
    _perform_unite(work_part, arm2_body, far2_cap)
    print("[OK] Arm 2 far-end cap united.")

    # ==================================================================
    # BOOLEAN UNION — join Arm 2 into Arm 1 for a clean flush junction
    # ==================================================================
    print("[...] Uniting Arm 2 into Arm 1 (flush junction, no block)...")
    _perform_unite(work_part, main_body, arm2_body)
    print("[OK] Both arms united — clean L-junction formed.")

    # ==================================================================
    # THROUGH-HOLES  (3 unique locations)
    # ==================================================================
    hole_cut_height = ARM_THICKNESS + 2.0   # overcut for clean through-hole

    # 5a. Junction hole — shared near-end of both arms at (half_w, half_w)
    print("[...] Creating junction hole (D={} mm) at ({}, {})...".format(
        HOLE_DIAMETER, half_w, half_w))
    h1_origin = NXOpen.Point3d(half_w, half_w, -1.0)
    h1_body = _create_cylinder(
        work_part, h1_origin, z_axis,
        "HOLE_DIAMETER", str(hole_cut_height)
    )
    _perform_subtract(work_part, main_body, h1_body)
    print("[OK] Junction hole subtracted.")

    # 5b. Arm 1 far-end hole at (ARM_LENGTH - HOLE_INSET, half_w)
    arm1_hole_x = ARM_LENGTH - HOLE_INSET
    print("[...] Creating Arm 1 far-end hole (D={} mm) at ({}, {})...".format(
        HOLE_DIAMETER, arm1_hole_x, half_w))
    h2_origin = NXOpen.Point3d(arm1_hole_x, half_w, -1.0)
    h2_body = _create_cylinder(
        work_part, h2_origin, z_axis,
        "HOLE_DIAMETER", str(hole_cut_height)
    )
    _perform_subtract(work_part, main_body, h2_body)
    print("[OK] Arm 1 far-end hole subtracted.")

    # 5c. Arm 2 far-end hole at (half_w, ARM_LENGTH - HOLE_INSET)
    arm2_hole_y = ARM_LENGTH - HOLE_INSET
    print("[...] Creating Arm 2 far-end hole (D={} mm) at ({}, {})...".format(
        HOLE_DIAMETER, half_w, arm2_hole_y))
    h3_origin = NXOpen.Point3d(half_w, arm2_hole_y, -1.0)
    h3_body = _create_cylinder(
        work_part, h3_origin, z_axis,
        "HOLE_DIAMETER", str(hole_cut_height)
    )
    _perform_subtract(work_part, main_body, h3_body)
    print("[OK] Arm 2 far-end hole subtracted.")

    # ------------------------------------------------------------------
    # 6. Fit view and save
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
    # 7. Update latest_nx_result.txt and open_current_nx_result.cmd
    # ------------------------------------------------------------------
    try:
        abs_path_str = str(output_path.resolve())

        latest_file = output_path.parent / "latest_nx_result.txt"
        latest_file.write_text(abs_path_str, encoding="utf-8")

        project_root = Path(__file__).parent.parent.parent.parent.resolve()
        root_latest = project_root / "latest_nx_result.txt"
        root_latest.write_text(abs_path_str, encoding="utf-8")

        cmd_path = project_root / "open_current_nx_result.cmd"
        cmd_content = '@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{}"\n'.format(abs_path_str)
        cmd_path.write_text(cmd_content, encoding="utf-8")

        print("[OK] Result files updated.")
    except Exception as exc:
        print("[WARN] Could not update result files: {}".format(exc))

    # ------------------------------------------------------------------
    # 8. Auto-open in Siemens NX GUI
    # ------------------------------------------------------------------
    try:
        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        router_candidates = [
            base_path / "NXBIN" / "ugs_router.exe",
            base_path / "UGII"  / "ugs_router.exe",
        ]
        ugs_router = next((c for c in router_candidates if c.exists()), None)
        if ugs_router:
            subprocess.Popen([str(ugs_router), "-ug", "-use_file_dir", str(output_path.resolve())])
            print("[OK] NX GUI launched -> opening {}".format(output_path.name))
        else:
            print("[WARN] ugs_router.exe not found — open the part manually in NX.")
    except Exception as exc:
        print("[WARN] Could not auto-open in NX GUI: {}".format(exc))

    print("[DONE] L-shaped linkage arm complete (no block junction).")


if __name__ == "__main__":
    main()
