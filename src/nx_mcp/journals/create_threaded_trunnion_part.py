"""
create_threaded_trunnion_part.py
================================
NX Journal (run via run_journal.exe / NX Python) that creates a parametric
threaded trunnion.  All dimensions are stored as named NX Expressions so the
model can be driven parametrically.

Threaded Trunnion Geometry
--------------------------
The trunnion consists of five geometric features built from primitives:

  1. CYLINDRICAL BODY  – main cylindrical body (BODY_DIAMETER × BODY_LENGTH)
     centred on the origin, axis along Z.
  2. FLAT-CUT BLOCK    – a pair of symmetric blocks subtract material from
     the cylinder sides so the body has a flat thickness of BODY_THICKNESS
     (creating the classic trunnion "ear" shape).
  3. BORE HOLE         – a through-hole along the Z-axis (BORE_DIAMETER).
  4. SHOULDER          – a stepped shoulder cylinder (SHOULDER_DIAMETER)
     projecting from the top face (+Z) of the body.
  5. THREADED STUD     – a smaller cylinder (STUD_DIAMETER) projecting
     beyond the shoulder to accept a nut/thread.

Named Expressions
-----------------
  BODY_DIAMETER    = 24 mm   (trunnion body OD)
  BODY_LENGTH      = 26 mm   (trunnion body height along Z)
  BODY_THICKNESS   = 15 mm   (flat width between ear faces)
  BORE_DIAMETER    = 13 mm   (through-bore hole)
  SHOULDER_DIAMETER= 14 mm   (shoulder step OD)
  STUD_DIAMETER    = 10 mm   (threaded stud OD)

Derived (computed internally):
  SHOULDER_LENGTH  = 8 mm    (shoulder projection — ~1/3 BODY_LENGTH)
  STUD_LENGTH      = 12 mm   (threaded stud projection — ~1/2 BODY_LENGTH)

Usage
-----
  run_journal.exe create_threaded_trunnion_part.py [output_path.prt]
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
BODY_DIAMETER     = 24.0
BODY_LENGTH       = 26.0
BODY_THICKNESS    = 15.0
BORE_DIAMETER     = 13.0
SHOULDER_DIAMETER = 14.0
STUD_DIAMETER     = 10.0

# Derived dimensions
SHOULDER_LENGTH   = 8.0     # shoulder projection beyond body top
STUD_LENGTH       = 12.0    # threaded stud projection beyond shoulder


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------
def _output_path() -> Path:
    """Return the resolved output .prt path (from argv or default)."""
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "threaded_trunnion.prt"


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
    Create a cylinder feature driven by named expression strings.

    Parameters
    ----------
    work_part      : NXOpen work part
    origin         : NXOpen.Point3d  — base-centre of the cylinder
    direction_vec  : NXOpen.Vector3d — axis direction (unit vector)
    diameter_expr  : RHS expression string, e.g. ``"BODY_DIAMETER"``
    height_expr    : RHS expression string, e.g. ``"BODY_LENGTH"``

    Returns
    -------
    NXOpen body object of the new cylinder solid.
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
    length_str(X) × width_str(Y) × height_str(Z).
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
    print("  CREATING PARAMETRIC THREADED TRUNNION")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Register named NX Expressions
    # ------------------------------------------------------------------
    named_expressions = [
        ("BODY_DIAMETER",     BODY_DIAMETER),
        ("BODY_LENGTH",       BODY_LENGTH),
        ("BODY_THICKNESS",    BODY_THICKNESS),
        ("BORE_DIAMETER",     BORE_DIAMETER),
        ("SHOULDER_DIAMETER", SHOULDER_DIAMETER),
        ("STUD_DIAMETER",     STUD_DIAMETER),
        # Derived helpers
        ("SHOULDER_LENGTH",   SHOULDER_LENGTH),
        ("STUD_LENGTH",       STUD_LENGTH),
        ("BODY_RADIUS",       BODY_DIAMETER / 2.0),
    ]
    for name, value in named_expressions:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
    print("[OK] Named expressions created.")

    # ------------------------------------------------------------------
    # 2. Main cylindrical body (axis along Z, centred on origin)
    #    Base at Z = 0, top at Z = BODY_LENGTH
    # ------------------------------------------------------------------
    z_axis = NXOpen.Vector3d(0.0, 0.0, 1.0)
    body_origin = NXOpen.Point3d(0.0, 0.0, 0.0)

    print("[...] Creating main cylindrical body...")
    body_cyl = _create_cylinder(
        work_part, body_origin, z_axis,
        "BODY_DIAMETER", "BODY_LENGTH"
    )
    print("[OK] Body cylinder created (D={} x L={} mm).".format(BODY_DIAMETER, BODY_LENGTH))

    # ------------------------------------------------------------------
    # 3. Flat-cut the body to create the trunnion ear shape
    #    We subtract two blocks from opposite sides of the cylinder to
    #    leave a flat slab of thickness BODY_THICKNESS in Y.
    #
    #    The cylinder spans Y = [-BODY_RADIUS, +BODY_RADIUS].
    #    We want to keep Y = [-BODY_THICKNESS/2, +BODY_THICKNESS/2].
    #
    #    Block A (positive Y side):
    #       corner = (-BODY_RADIUS, BODY_THICKNESS/2, 0)
    #       size   = (BODY_DIAMETER, BODY_RADIUS - BODY_THICKNESS/2, BODY_LENGTH)
    #
    #    Block B (negative Y side):
    #       corner = (-BODY_RADIUS, -BODY_RADIUS, 0)
    #       size   = (BODY_DIAMETER, BODY_RADIUS - BODY_THICKNESS/2, BODY_LENGTH)
    # ------------------------------------------------------------------
    body_radius   = BODY_DIAMETER / 2.0
    half_thick    = BODY_THICKNESS / 2.0
    cut_depth     = body_radius - half_thick   # material to remove per side

    if cut_depth > 0.01:
        print("[...] Flat-cutting body to BODY_THICKNESS = {} mm...".format(BODY_THICKNESS))

        # Block A — positive Y side
        corner_a = NXOpen.Point3d(-body_radius, half_thick, 0.0)
        block_a = _create_block(
            work_part, corner_a,
            str(BODY_DIAMETER), str(cut_depth), str(BODY_LENGTH)
        )
        _perform_subtract(work_part, body_cyl, block_a)
        print("[OK] Positive-Y flat cut done.")

        # Block B — negative Y side
        corner_b = NXOpen.Point3d(-body_radius, -body_radius, 0.0)
        block_b = _create_block(
            work_part, corner_b,
            str(BODY_DIAMETER), str(cut_depth), str(BODY_LENGTH)
        )
        _perform_subtract(work_part, body_cyl, block_b)
        print("[OK] Negative-Y flat cut done.")
    else:
        print("[SKIP] BODY_THICKNESS >= BODY_DIAMETER — no flat-cut needed.")

    # ------------------------------------------------------------------
    # 4. Bore hole — through-hole along Z-axis through the entire body
    #    Slightly oversized height to ensure clean boolean cut.
    # ------------------------------------------------------------------
    print("[...] Creating bore hole (D={} mm)...".format(BORE_DIAMETER))
    bore_origin = NXOpen.Point3d(0.0, 0.0, -1.0)
    bore_body = _create_cylinder(
        work_part, bore_origin, z_axis,
        "BORE_DIAMETER", str(BODY_LENGTH + 2.0)
    )
    _perform_subtract(work_part, body_cyl, bore_body)
    print("[OK] Bore hole subtracted.")

    # ------------------------------------------------------------------
    # 5. Shoulder cylinder — projects from the top face of the body (+Z)
    #    SHOULDER_DIAMETER, SHOULDER_LENGTH tall
    # ------------------------------------------------------------------
    print("[...] Creating shoulder (D={} x L={} mm)...".format(SHOULDER_DIAMETER, SHOULDER_LENGTH))
    shoulder_origin = NXOpen.Point3d(0.0, 0.0, BODY_LENGTH)
    shoulder_body = _create_cylinder(
        work_part, shoulder_origin, z_axis,
        "SHOULDER_DIAMETER", "SHOULDER_LENGTH"
    )
    _perform_unite(work_part, body_cyl, shoulder_body)
    print("[OK] Shoulder united to body.")

    # ------------------------------------------------------------------
    # 6. Threaded stud — projects from the top of the shoulder
    #    STUD_DIAMETER, STUD_LENGTH tall
    # ------------------------------------------------------------------
    print("[...] Creating threaded stud (D={} x L={} mm)...".format(STUD_DIAMETER, STUD_LENGTH))
    stud_origin = NXOpen.Point3d(0.0, 0.0, BODY_LENGTH + SHOULDER_LENGTH)
    stud_body = _create_cylinder(
        work_part, stud_origin, z_axis,
        "STUD_DIAMETER", "STUD_LENGTH"
    )
    _perform_unite(work_part, body_cyl, stud_body)
    print("[OK] Threaded stud united to body.")

    # ------------------------------------------------------------------
    # 7. Fit view and save
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
    # 8. Update latest_nx_result.txt and open_current_nx_result.cmd
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
    # 9. Auto-open in Siemens NX GUI
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

    print("[DONE] Threaded trunnion complete.")


if __name__ == "__main__":
    main()
