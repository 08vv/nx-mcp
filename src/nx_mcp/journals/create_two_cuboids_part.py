import sys
from pathlib import Path

import NXOpen


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd().joinpath("two_cuboids.prt").resolve()


def _create_cuboid(work_part, length, width, height, x, y, z):
    builder = work_part.Features.CreateBlockFeatureBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(float(x), float(y), float(z))
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(
            origin,
            str(float(length)),
            str(float(width)),
            str(float(height)),
        )
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        builder.CommitFeature()
    finally:
        builder.Destroy()


def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    _create_cuboid(work_part, 40.0, 25.0, 20.0, 0.0, 0.0, 0.0)
    _create_cuboid(work_part, 30.0, 25.0, 20.0, 45.0, 0.0, 0.0)
    work_part.ModelingViews.WorkView.Fit()

    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"Created two cuboids part: {output_path}")


if __name__ == "__main__":
    main()
