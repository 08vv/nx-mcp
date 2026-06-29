"""
create_linkage_arm_part.py
===========================
NX Journal (run via run_journal.exe / NX Python) that creates a parametric
linkage arm assembly as a single part.  All dimensions are stored as named
NX Expressions for fully parametric design.

Linkage Arm Geometry
--------------------
The linkage arm consists of:

  1. FLAT ARM BAR   – rectangular plate (ARM_LENGTH × ARM_WIDTH × ARM_THICKNESS)
                      running along the X-axis with rounded (cylindrical) ends.
  2. END BOSSES     – cylindrical caps at each end of the bar to form the
                      classic rounded linkage-arm profile.
  3. END HOLE       – through-bore at the near end of the arm (END_HOLE_DIAMETER).
  4. VERTICAL CYLINDER – cylindrical boss rising from the far end of the arm
                         (CYLINDER_DIAMETER × CYLINDER_HEIGHT, axis along Z).
  5. TOP HOLE       – through-bore through the vertical cylinder (TOP_HOLE_DIAMETER).

Named Expressions
-----------------
  ARM_LENGTH         = 100 mm
  ARM_WIDTH          =  20 mm
  ARM_THICKNESS      =   8 mm
  END_HOLE_DIAMETER  =  10 mm
  CYLINDER_HEIGHT    =  60 mm
  CYLINDER_DIAMETER  =  20 mm
  TOP_HOLE_DIAMETER  =   8 mm

Usage
-----
  run_journal.exe create_linkage_arm_part.py [output_path.prt]
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
ARM_LENGTH         = 100.0
ARM_WIDTH          = 20.0
ARM_THICKNESS      = 8.0
END_HOLE_DIAMETER  = 10.0
CYLINDER_HEIGHT    = 60.0
CYLINDER_DIAMETER  = 20.0
TOP_HOLE_DIAMETER  = 8.0


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
def _output_path() -> Path:
    """Return the resolved output .prt path (from argv or default)."""
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "linkage_arm.prt"


# ---------------------------------------------------------------------------
# Helper: boolean subtract
# ---------------------------------------------------------------------------
def _perform_subtract(work_part, target_body, tool_body):
    """Subtract *tool_body* from *target_body* in-place."""
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
    """Unite *tool_body* into *target_body* in-place."""
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
    """
    Create a cylinder feature driven by expression strings.
    Returns the NXOpen body object.
    """
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
    """
    Create a solid block feature. Extends from *corner_origin* by
    length_str(X) x width_str(Y) x height_str(Z).
    """
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
    print("  CREATING PARAMETRIC LINKAGE ARM")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Register named NX Expressions
    # ------------------------------------------------------------------
    named_expressions = [
        ("ARM_LENGTH",        ARM_LENGTH),
        ("ARM_WIDTH",         ARM_WIDTH),
        ("ARM_THICKNESS",     ARM_THICKNESS),
        ("END_HOLE_DIAMETER", END_HOLE_DIAMETER),
        ("CYLINDER_HEIGHT",   CYLINDER_HEIGHT),
        ("CYLINDER_DIAMETER", CYLINDER_DIAMETER),
        ("TOP_HOLE_DIAMETER", TOP_HOLE_DIAMETER),
        # Derived helpers
        ("ARM_WIDTH_HALF",    ARM_WIDTH / 2.0),
    ]
    for name, value in named_expressions:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
    print("[OK] Named expressions created.")

    # ------------------------------------------------------------------
    # Coordinate system layout:
    #   Arm runs along X-axis from X=0 to X=ARM_LENGTH
    #   Arm centred on Y: Y = -ARM_WIDTH/2 to +ARM_WIDTH/2
    #   Arm thickness in Z: Z = 0 to ARM_THICKNESS
    #
    #   Near end centre: (ARM_WIDTH/2, 0, 0)          — end hole here
    #   Far  end centre: (ARM_LENGTH - ARM_WIDTH/2, 0, 0) — cylinder here
    # ------------------------------------------------------------------
    z_axis       = NXOpen.Vector3d(0.0, 0.0, 1.0)
    half_width   = ARM_WIDTH / 2.0
    near_centre_x = half_width                       # 10
    far_centre_x  = ARM_LENGTH - half_width          # 90

    # ------------------------------------------------------------------
    # 2. Main arm — rectangular block
    #    Corner at (ARM_WIDTH/2, -ARM_WIDTH/2, 0)
    #    so the block spans from near-end centre to far-end centre in X,
    #    leaving the rounded caps to close the ends.
    # ------------------------------------------------------------------
    print("[...] Creating arm block...")
    arm_block_length = ARM_LENGTH - ARM_WIDTH  # 80 mm (between the two cap centres)
    arm_corner = NXOpen.Point3d(near_centre_x, -half_width, 0.0)
    arm_body = _create_block(
        work_part, arm_corner,
        str(arm_block_length), "ARM_WIDTH", "ARM_THICKNESS"
    )
    print("[OK] Arm block created ({} x {} x {} mm).".format(
        arm_block_length, ARM_WIDTH, ARM_THICKNESS))

    # ------------------------------------------------------------------
    # 3. Near-end cylindrical boss (rounded cap)
    #    Centre at (ARM_WIDTH/2, 0, 0), diameter=ARM_WIDTH, height=ARM_THICKNESS
    # ------------------------------------------------------------------
    print("[...] Creating near-end boss...")
    near_origin = NXOpen.Point3d(near_centre_x, 0.0, 0.0)
    near_boss = _create_cylinder(
        work_part, near_origin, z_axis,
        "ARM_WIDTH", "ARM_THICKNESS"
    )
    _perform_unite(work_part, arm_body, near_boss)
    print("[OK] Near-end boss united.")

    # ------------------------------------------------------------------
    # 4. Far-end cylindrical boss (rounded cap)
    #    Centre at (ARM_LENGTH - ARM_WIDTH/2, 0, 0)
    # ------------------------------------------------------------------
    print("[...] Creating far-end boss...")
    far_origin = NXOpen.Point3d(far_centre_x, 0.0, 0.0)
    far_boss = _create_cylinder(
        work_part, far_origin, z_axis,
        "ARM_WIDTH", "ARM_THICKNESS"
    )
    _perform_unite(work_part, arm_body, far_boss)
    print("[OK] Far-end boss united.")

    # ------------------------------------------------------------------
    # 5. End hole — through-bore at the near end
    #    Centre at (ARM_WIDTH/2, 0, -1), slightly oversized height
    # ------------------------------------------------------------------
    print("[...] Creating end hole (D={} mm)...".format(END_HOLE_DIAMETER))
    hole_origin = NXOpen.Point3d(near_centre_x, 0.0, -1.0)
    hole_body = _create_cylinder(
        work_part, hole_origin, z_axis,
        "END_HOLE_DIAMETER", str(ARM_THICKNESS + 2.0)
    )
    _perform_subtract(work_part, arm_body, hole_body)
    print("[OK] End hole subtracted.")

    # ------------------------------------------------------------------
    # 6. Vertical cylinder — rising from the far end of the arm
    #    Base at (ARM_LENGTH - ARM_WIDTH/2, 0, ARM_THICKNESS)
    #    Axis along Z, diameter=CYLINDER_DIAMETER, height=CYLINDER_HEIGHT
    # ------------------------------------------------------------------
    print("[...] Creating vertical cylinder (D={} x H={} mm)...".format(
        CYLINDER_DIAMETER, CYLINDER_HEIGHT))
    cyl_origin = NXOpen.Point3d(far_centre_x, 0.0, ARM_THICKNESS)
    cyl_body = _create_cylinder(
        work_part, cyl_origin, z_axis,
        "CYLINDER_DIAMETER", "CYLINDER_HEIGHT"
    )
    _perform_unite(work_part, arm_body, cyl_body)
    print("[OK] Vertical cylinder united to arm.")

    # ------------------------------------------------------------------
    # 7. Top hole — through-bore through the vertical cylinder
    #    Full depth: ARM_THICKNESS + CYLINDER_HEIGHT + 2 (overcut)
    #    Start just below the arm bottom surface
    # ------------------------------------------------------------------
    print("[...] Creating top hole through cylinder (D={} mm)...".format(TOP_HOLE_DIAMETER))
    top_hole_origin = NXOpen.Point3d(far_centre_x, 0.0, -1.0)
    total_bore_height = ARM_THICKNESS + CYLINDER_HEIGHT + 2.0
    top_hole_body = _create_cylinder(
        work_part, top_hole_origin, z_axis,
        "TOP_HOLE_DIAMETER", str(total_bore_height)
    )
    _perform_subtract(work_part, arm_body, top_hole_body)
    print("[OK] Top hole subtracted through cylinder.")

    # ------------------------------------------------------------------
    # 8. Fit view and save
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
    # 9. Update latest_nx_result.txt and open_current_nx_result.cmd
    # ------------------------------------------------------------------
    try:
        abs_path_str = str(output_path.resolve())

        # Write to local latest_nx_result.txt
        latest_file = output_path.parent / "latest_nx_result.txt"
        latest_file.write_text(abs_path_str, encoding="utf-8")

        # Also write to project root
        project_root = Path(__file__).parent.parent.parent.parent.resolve()
        root_latest = project_root / "latest_nx_result.txt"
        root_latest.write_text(abs_path_str, encoding="utf-8")

        # Update open_current_nx_result.cmd
        cmd_path = project_root / "open_current_nx_result.cmd"
        cmd_content = '@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{}"\n'.format(abs_path_str)
        cmd_path.write_text(cmd_content, encoding="utf-8")

        print("[OK] Result files updated.")
    except Exception as exc:
        print("[WARN] Could not update result files: {}".format(exc))

    # ------------------------------------------------------------------
    # 10. Auto-open in Siemens NX GUI
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

    print("[DONE] Linkage arm complete.")


if __name__ == "__main__":
    main()
