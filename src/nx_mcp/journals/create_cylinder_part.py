import sys
from pathlib import Path

import NXOpen


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd().joinpath("cylinder_r20_h50.prt").resolve()


def _radius():
    if len(sys.argv) > 2:
        return float(sys.argv[2])
    return 20.0


def _height():
    if len(sys.argv) > 3:
        return float(sys.argv[3])
    return 50.0


def main():
    output_path = _output_path()
    radius = _radius()
    height = _height()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

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
        builder.Commit()
    finally:
        builder.Destroy()

    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"Created cylinder part: {output_path}")


if __name__ == "__main__":
    main()
