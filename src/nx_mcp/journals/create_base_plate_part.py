import sys
from pathlib import Path

import NXOpen


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd().joinpath("base_plate_100x60x10.prt").resolve()


def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    builder = work_part.Features.CreateBlockFeatureBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(origin, "100", "60", "10")
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        builder.CommitFeature()
    finally:
        builder.Destroy()

    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"Created base plate part: {output_path}")


if __name__ == "__main__":
    main()
