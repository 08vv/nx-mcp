import sys
from pathlib import Path

import NXOpen


def _args():
    output_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd() / "cuboid.prt"
    length = float(sys.argv[2]) if len(sys.argv) > 2 else 100.0
    width = float(sys.argv[3]) if len(sys.argv) > 3 else 60.0
    height = float(sys.argv[4]) if len(sys.argv) > 4 else 10.0
    return output_path.resolve(), length, width, height


def main():
    output_path, length, width, height = _args()
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
        builder.SetOriginAndLengths(origin, str(length), str(width), str(height))
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
    print(f"Created cuboid part: {output_path}")


if __name__ == "__main__":
    main()
