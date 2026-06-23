"""
Parametric Circular Flange - NXOpen Journal
============================================
OUTER_DIAMETER       = 120 mm
CENTER_BORE_DIAMETER = 50  mm
THICKNESS            = 15  mm
BOLT_CIRCLE_DIAMETER = 95  mm
BOLT_HOLE_DIAMETER   = 10  mm
BOLT_HOLE_COUNT      = 6

Output: C:/Users/HP/Documents/NX_MCP_Parts/circular_flange_120_50_15.prt

All dimensions are stored as named NX Expressions so they can be
edited later with edit_expression() for live in-place updates.
"""
import math
import os
from pathlib import Path

import NXOpen

# ── Dimensions ────────────────────────────────────────────────────────────────
OUTER_DIAMETER       = 120.0
CENTER_BORE_DIAMETER =  50.0
THICKNESS            =  15.0
BOLT_CIRCLE_DIAMETER =  95.0
BOLT_HOLE_DIAMETER   =  10.0
BOLT_HOLE_COUNT      =   6

# ── Hard-coded output path (no sys.argv needed) ───────────────────────────────
OUTPUT_PATH = Path("C:/Users/HP/Documents/NX_MCP_Parts/circular_flange_120_50_15.prt")


def _subtract(work_part, target_body, tool_body):
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


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    session   = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(OUTPUT_PATH), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    # ── 1. Named Expressions ─────────────────────────────────────────────────
    named_exprs = [
        ("OUTER_DIAMETER",       OUTER_DIAMETER),
        ("CENTER_BORE_DIAMETER", CENTER_BORE_DIAMETER),
        ("THICKNESS",            THICKNESS),
        ("BOLT_CIRCLE_DIAMETER", BOLT_CIRCLE_DIAMETER),
        ("BOLT_HOLE_DIAMETER",   BOLT_HOLE_DIAMETER),
        ("BOLT_HOLE_COUNT",      BOLT_HOLE_COUNT),
    ]
    for name, value in named_exprs:
        work_part.Expressions.CreateExpression("Number", f"{name} = {value}")

    dir_up = NXOpen.Vector3d(0.0, 0.0, 1.0)

    def make_dir(origin):
        return work_part.Directions.CreateDirection(
            origin, dir_up,
            NXOpen.SmartObject.UpdateOption.WithinModeling
        )

    origin_z = NXOpen.Point3d(0.0, 0.0, 0.0)

    # ── 2. Outer flange cylinder ──────────────────────────────────────────────
    cb = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        cb.Diameter.RightHandSide = "OUTER_DIAMETER"
        cb.Height.RightHandSide   = "THICKNESS"
        cb.Axis.Point.SetCoordinates(origin_z)
        cb.Axis.Direction = make_dir(origin_z)
        main_feat = cb.Commit()
    finally:
        cb.Destroy()
    main_body = main_feat.GetBodies()[0]

    # ── 3. Centre bore ────────────────────────────────────────────────────────
    cb = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        cb.Diameter.RightHandSide = "CENTER_BORE_DIAMETER"
        cb.Height.RightHandSide   = "THICKNESS"
        cb.Axis.Point.SetCoordinates(origin_z)
        cb.Axis.Direction = make_dir(origin_z)
        bore_feat = cb.Commit()
    finally:
        cb.Destroy()
    _subtract(work_part, main_body, bore_feat.GetBodies()[0])

    # ── 4. Bolt holes ─────────────────────────────────────────────────────────
    for i in range(BOLT_HOLE_COUNT):
        angle_deg = i * 360.0 / BOLT_HOLE_COUNT
        # NX expression stored in degrees (NX trig functions accept degrees)
        work_part.Expressions.CreateExpression(
            "Number",
            f"HOLE_X_{i} = (BOLT_CIRCLE_DIAMETER / 2.0) * cos({angle_deg})"
        )
        work_part.Expressions.CreateExpression(
            "Number",
            f"HOLE_Y_{i} = (BOLT_CIRCLE_DIAMETER / 2.0) * sin({angle_deg})"
        )

        # Numeric placement (Python uses radians)
        angle_rad = math.radians(angle_deg)
        cx = (BOLT_CIRCLE_DIAMETER / 2.0) * math.cos(angle_rad)
        cy = (BOLT_CIRCLE_DIAMETER / 2.0) * math.sin(angle_rad)
        hole_origin = NXOpen.Point3d(cx, cy, 0.0)

        cb = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        try:
            cb.Diameter.RightHandSide = "BOLT_HOLE_DIAMETER"
            cb.Height.RightHandSide   = "THICKNESS"
            cb.Axis.Point.SetCoordinates(hole_origin)
            cb.Axis.Direction = make_dir(hole_origin)
            hole_feat = cb.Commit()
        finally:
            cb.Destroy()
        _subtract(work_part, main_body, hole_feat.GetBodies()[0])

    # ── 5. Fit, save, done ────────────────────────────────────────────────────
    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    NXOpen.UI.GetUI().NXMessageBox.Show(
        "NX MCP",
        NXOpen.NXMessageBox.DialogType.Information,
        f"Flange created!\n{OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
