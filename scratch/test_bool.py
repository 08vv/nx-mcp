import NXOpen

def main():
    session = NXOpen.Session.GetSession()
    work_part = session.Parts.Work
    if work_part is None:
        work_part = session.Parts.NewDisplay("C:/Users/HP/nx-mcp/scratch/temp.prt", NXOpen.Part.Units.Millimeters)

    # Create a block to use as target body
    block_builder = work_part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        block_builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        block_builder.SetOriginAndLengths(NXOpen.Point3d(0.0, 0.0, 0.0), "10.0", "10.0", "10.0")
        feat = block_builder.CommitFeature()
        body = feat.GetBodies()[0]
    finally:
        block_builder.Destroy()

    builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        # Try calling SetBooleanOperationAndBody
        builder.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
            body
        )
        print("Success! Called SetBooleanOperationAndBody.")
    except Exception as e:
        print(f"Failed to call SetBooleanOperationAndBody: {e}")
    finally:
        builder.Destroy()

if __name__ == "__main__":
    main()
