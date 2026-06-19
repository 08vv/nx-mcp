import sys
from pathlib import Path

import NXOpen


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd().joinpath("cylinder_r10_h50_chamfer5.prt").resolve()


def _make_cylinder(work_part, radius, height):
    builder = work_part.Features.CreateCylinderBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
        nx_direction = work_part.Directions.CreateDirection(
            origin,
            direction,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Diameter.RightHandSide = str(radius * 2.0)
        builder.Height.RightHandSide = str(height)
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = nx_direction
        return builder.Commit()
    finally:
        builder.Destroy()


def _add_chamfer(work_part, body, offset):
    edges = list(body.GetEdges())
    if not edges:
        raise RuntimeError("Created cylinder has no edges to chamfer")

    builder = work_part.Features.CreateChamferBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        builder.Option = NXOpen.Features.ChamferBuilder.ChamferOption.OffsetAndAngle
        builder.Method = NXOpen.Features.ChamferBuilder.OffsetMethod.EdgesAlongFaces
        builder.FirstOffset = str(offset)
        builder.SecondOffset = str(offset)
        builder.Angle = "45"
        builder.Tolerance = 0.01

        rules = []
        for edge in edges:
            rule = work_part.ScRuleFactory.CreateRuleEdgeTangent(
                edge,
                NXOpen.Edge.Null,
                False,
                0.5,
                False,
            )
            rules.append(rule)

        collector = work_part.ScCollectors.CreateCollector()
        collector.ReplaceRules(rules, False)
        builder.SmartCollector = collector
        builder.CommitFeature()
    finally:
        builder.Destroy()


def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    feature = _make_cylinder(work_part, radius=10.0, height=50.0)
    body = feature.GetBodies()[0]
    _add_chamfer(work_part, body, offset=5.0)

    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"Created chamfered cylinder part: {output_path}")


if __name__ == "__main__":
    main()
