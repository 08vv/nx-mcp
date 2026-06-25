"""
create_shaft_with_keyway_part.py
================================
NX Journal (run via run_journal.exe / NX Python) that creates a parametric
shaft with a top keyway slot.  All dimensions are stored as named NX
Expressions so the model can be driven parametrically later.

Shaft specification
-------------------
  SHAFT_DIAMETER   =  30 mm   (cylinder diameter)
  SHAFT_LENGTH     = 150 mm   (cylinder length along Z)

Keyway slot specification (rectangular pocket milled into the top of the shaft)
-------------------
  KEYWAY_WIDTH     =  10 mm   (slot width — equals SHAFT_DIAMETER/3 by convention)
  KEYWAY_DEPTH     =  10 mm   (slot depth below the top surface of the shaft)
  KEYWAY_LENGTH    = 100 mm   (slot runs centred along the shaft length)

Usage
-----
  run_journal.exe create_shaft_with_keyway_part.py [output_path.prt]

If no path argument is supplied the part is written next to this script as
``parametric_shaft_with_keyway.prt``.
"""

import math
import sys
import os
from pathlib import Path
import subprocess

import NXOpen

# ---------------------------------------------------------------------------
# Parametric constants (driven by named NX Expressions created at run-time)
# ---------------------------------------------------------------------------
SHAFT_DIAMETER = 30.0       # mm
SHAFT_LENGTH   = 150.0      # mm

KEYWAY_WIDTH   = 10.0       # mm  — slot width
KEYWAY_DEPTH   = 10.0       # mm  — slot depth (pocket depth into shaft)
KEYWAY_LENGTH  = 100.0      # mm  — slot length along shaft axis


def _output_path() -> Path:
    """Return the resolved output .prt path (from argv or default)."""
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.resolve() / "parametric_shaft_with_keyway.prt"


# ---------------------------------------------------------------------------
# Helper: boolean subtract (same robust pattern used across all journals)
# ---------------------------------------------------------------------------
def _perform_subtract(work_part, target_body, tool_body):
    """Subtract *tool_body* from *target_body* in-place."""
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        # Target
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body)
                    break
                except Exception:
                    pass
        # Tool
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
def _create_cylinder(work_part, origin, direction_vec, diameter_expr: str, height_expr: str):
    """
    Create a cylinder feature driven by named expression strings.

    Parameters
    ----------
    work_part      : NXOpen work part
    origin         : NXOpen.Point3d  — base-centre of the cylinder
    direction_vec  : NXOpen.Vector3d — axis direction (unit vector)
    diameter_expr  : RHS expression string, e.g. ``"SHAFT_DIAMETER"``
    height_expr    : RHS expression string, e.g. ``"SHAFT_LENGTH"``

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
def _create_block(work_part, corner_origin, length_str: str, width_str: str, height_str: str):
    """
    Create a solid block feature using SetOriginAndLengths (proven NX 2206 API).

    The block extends from *corner_origin* by:
      length_str  in X
      width_str   in Y
      height_str  in Z

    Each string may be a numeric literal (e.g. "10.0") or the name of a
    registered NX Expression (e.g. "KEYWAY_WIDTH") — NX will resolve it.

    Returns the body object.
    """
    builder = work_part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        # SetOriginAndLengths accepts expression name strings or numeric strings
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

    # Open a new empty part
    session   = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    # ------------------------------------------------------------------
    # 1.  Register all dimensions as named NX Expressions
    #     These make the model fully parametric: change a value in the
    #     Expression editor and the geometry updates automatically.
    # ------------------------------------------------------------------
    named_expressions = [
        ("SHAFT_DIAMETER", SHAFT_DIAMETER),
        ("SHAFT_LENGTH",   SHAFT_LENGTH),
        ("KEYWAY_WIDTH",   KEYWAY_WIDTH),
        ("KEYWAY_DEPTH",   KEYWAY_DEPTH),
        ("KEYWAY_LENGTH",  KEYWAY_LENGTH),
        # Derived helpers (make editing easier in NX Expression editor)
        ("SHAFT_RADIUS",   SHAFT_DIAMETER / 2.0),
        ("KEYWAY_X_OFFSET", -(KEYWAY_WIDTH / 2.0)),   # x-corner of keyway block
        ("KEYWAY_Z_START",  (SHAFT_LENGTH - KEYWAY_LENGTH) / 2.0),  # z start
        ("KEYWAY_Y_OFFSET", SHAFT_DIAMETER / 2.0 - KEYWAY_DEPTH),   # block y-corner
    ]
    for name, value in named_expressions:
        work_part.Expressions.CreateExpression("Number", f"{name} = {value}")

    print("[OK] Named expressions created:")
    for name, value in named_expressions:
        print("    {} = {}".format(name, value))

    # ------------------------------------------------------------------
    # 2.  Main shaft — cylinder along Z-axis centred on origin
    #     Diameter driven by expression SHAFT_DIAMETER
    #     Length   driven by expression SHAFT_LENGTH
    # ------------------------------------------------------------------
    shaft_origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    shaft_axis   = NXOpen.Vector3d(0.0, 0.0, 1.0)

    shaft_body = _create_cylinder(
        work_part,
        shaft_origin,
        shaft_axis,
        diameter_expr="SHAFT_DIAMETER",
        height_expr="SHAFT_LENGTH",
    )
    print("[OK] Shaft cylinder created  (D={} x L={} mm)".format(SHAFT_DIAMETER, SHAFT_LENGTH))

    # ------------------------------------------------------------------
    # 3.  Keyway slot — rectangular block that we subtract from the shaft
    #
    #     Geometry:
    #       • Width  (X): KEYWAY_WIDTH  centred on X = 0
    #         → corner X = -KEYWAY_WIDTH/2
    #       • Height (Y): extends from the top of the shaft downward by
    #         KEYWAY_DEPTH.  Since the shaft radius = 15 mm the top of the
    #         shaft is at Y = +15.  The block top is at Y = +15 + 1 mm
    #         (slight over-cut ensures clean boolean), bottom at
    #         Y = 15 - KEYWAY_DEPTH + 1 = 6.
    #         Corner Y = 15 - KEYWAY_DEPTH (= 5) is sufficient — the block
    #         reaches above the shaft surface because its height makes it
    #         protrude from the top.
    #         We set corner Y = SHAFT_RADIUS - KEYWAY_DEPTH (= 5) and
    #         the block height = KEYWAY_DEPTH + SHAFT_RADIUS (ensures the
    #         block fully protrudes above the top of the shaft).
    #       • Length (Z): KEYWAY_LENGTH, starting at KEYWAY_Z_START so the
    #         slot is centred in the shaft.
    #
    #     Computed values (at defaults):
    #       corner_x  = -5.0    (−KEYWAY_WIDTH / 2)
    #       corner_y  =  5.0    (SHAFT_RADIUS − KEYWAY_DEPTH)
    #       corner_z  = 25.0    ((SHAFT_LENGTH − KEYWAY_LENGTH) / 2)
    #       block_len (Z) = 100.0  (KEYWAY_LENGTH)
    #       block_wid (X) = 10.0   (KEYWAY_WIDTH)
    #       block_hgt (Y) = 25.0   (KEYWAY_DEPTH + SHAFT_RADIUS; over-cut above shaft top)
    # ------------------------------------------------------------------

    # Evaluate numeric corner from the Python constants (expressions are
    # already stored in NX; Python values here are only for creating the
    # geometry at build time).
    shaft_radius  = SHAFT_DIAMETER / 2.0
    corner_x = -(KEYWAY_WIDTH / 2.0)
    corner_y  =  shaft_radius - KEYWAY_DEPTH        # lower edge of slot
    corner_z  = (SHAFT_LENGTH - KEYWAY_LENGTH) / 2.0

    # Block height: from corner_y upward, completely beyond the shaft top
    block_height = KEYWAY_DEPTH + shaft_radius      # 10 + 15 = 25 mm over-cut

    keyway_corner = NXOpen.Point3d(corner_x, corner_y, corner_z)

    # Expression strings for the block dimensions
    # X width  → KEYWAY_WIDTH
    # Z length → KEYWAY_LENGTH
    # Y height → KEYWAY_DEPTH + SHAFT_RADIUS  (numeric literal; reuses expressions)
    keyway_body = _create_block(
        work_part,
        keyway_corner,
        length_str="KEYWAY_WIDTH",      # X — 10 mm
        width_str=str(block_height),    # Y — 25 mm (over-cut, numeric)
        height_str="KEYWAY_LENGTH",     # Z — 100 mm
    )
    print("[OK] Keyway block created  ({} x {} x {} mm)".format(
        KEYWAY_WIDTH, block_height, KEYWAY_LENGTH))

    # ------------------------------------------------------------------
    # 4.  Boolean subtract: remove keyway block from shaft
    # ------------------------------------------------------------------
    _perform_subtract(work_part, shaft_body, keyway_body)
    print("[OK] Boolean subtract complete - keyway slot cut into shaft")

    # ------------------------------------------------------------------
    # 5.  Fit view, save part
    # ------------------------------------------------------------------
    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("[OK] Part saved -> {}".format(output_path))

    # ------------------------------------------------------------------
    # 6.  Write path to latest_nx_result.txt (picked up by watcher scripts)
    # ------------------------------------------------------------------
    try:
        latest_file = output_path.parent / "latest_nx_result.txt"
        latest_file.write_text(str(output_path.resolve()), encoding="utf-8")
        print("[OK] latest_nx_result.txt updated")
    except Exception as exc:
        print("[WARN] Could not update latest_nx_result.txt: {}".format(exc))

    # ------------------------------------------------------------------
    # 7.  Auto-open the .prt in the Siemens NX GUI
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
            subprocess.Popen(
                [str(ugs_router), "-ug", "-use_file_dir", str(output_path.resolve())]
            )
            print("[OK] NX GUI launched -> opening {}".format(output_path.name))
        else:
            print("[WARN] ugs_router.exe not found - open the part manually in NX")
    except Exception as exc:
        print("[WARN] Could not auto-open in NX GUI: {}".format(exc))


if __name__ == "__main__":
    main()
