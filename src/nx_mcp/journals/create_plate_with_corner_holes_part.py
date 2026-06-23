import sys
from pathlib import Path

import NXOpen

LENGTH = 100.0
WIDTH = 60.0
THICKNESS = 10.0
HOLE_DIAMETER = 8.0
HOLE_EDGE_OFFSET = 10.0


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd().joinpath("plate_100x60x10_4x_d8_holes.prt").resolve()


def perform_subtract(work_part, target_body, tool_body):
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


def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    # Create Named Expressions
    expressions = [
        ("LENGTH", LENGTH),
        ("WIDTH", WIDTH),
        ("THICKNESS", THICKNESS),
        ("HOLE_DIAMETER", HOLE_DIAMETER),
        ("HOLE_EDGE_OFFSET", HOLE_EDGE_OFFSET),
    ]
    for name, value in expressions:
        work_part.Expressions.CreateExpression("Number", f"{name} = {value}")

    # 1. Main plate block
    block_builder = work_part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        block_builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        block_builder.SetOriginAndLengths(origin, "LENGTH", "WIDTH", "THICKNESS")
        block_builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        block_feat = block_builder.CommitFeature()
    finally:
        block_builder.Destroy()

    main_body = block_feat.GetBodies()[0]

    # Corner coordinates expressions definition
    hole_positions = [
        ("1", "HOLE_EDGE_OFFSET", "HOLE_EDGE_OFFSET", HOLE_EDGE_OFFSET, HOLE_EDGE_OFFSET),
        ("2", "LENGTH - HOLE_EDGE_OFFSET", "HOLE_EDGE_OFFSET", LENGTH - HOLE_EDGE_OFFSET, HOLE_EDGE_OFFSET),
        ("3", "HOLE_EDGE_OFFSET", "WIDTH - HOLE_EDGE_OFFSET", HOLE_EDGE_OFFSET, WIDTH - HOLE_EDGE_OFFSET),
        ("4", "LENGTH - HOLE_EDGE_OFFSET", "WIDTH - HOLE_EDGE_OFFSET", LENGTH - HOLE_EDGE_OFFSET, WIDTH - HOLE_EDGE_OFFSET),
    ]

    # Create holes
    for idx, x_formula, y_formula, cx, cy in hole_positions:
        work_part.Expressions.CreateExpression("Number", f"HOLE{idx}_X = {x_formula}")
        work_part.Expressions.CreateExpression("Number", f"HOLE{idx}_Y = {y_formula}")

        hole_builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        try:
            origin = NXOpen.Point3d(cx, cy, 0.0)
            dir_vector = NXOpen.Vector3d(0.0, 0.0, 1.0)
            direction = work_part.Directions.CreateDirection(origin, dir_vector, NXOpen.SmartObject.UpdateOption.WithinModeling)

            hole_builder.Diameter.RightHandSide = "HOLE_DIAMETER"
            hole_builder.Height.RightHandSide = "THICKNESS"
            hole_builder.Axis.Point.SetCoordinates(origin)
            hole_builder.Axis.Direction = direction

            hole_feat = hole_builder.Commit()
        finally:
            hole_builder.Destroy()

        hole_body = hole_feat.GetBodies()[0]
        perform_subtract(work_part, main_body, hole_body)

    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"Created plate with corner holes: {output_path}")


if __name__ == "__main__":
    main()
