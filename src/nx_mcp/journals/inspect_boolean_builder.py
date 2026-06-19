import NXOpen


def main():
    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay("C:\\Users\\HP\\nx-mcp\\inspect_boolean_builder.prt", NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        names = [name for name in dir(builder) if "Body" in name or "Target" in name or "Tool" in name or "Operation" in name or "Boolean" in name]
        print("BOOLEAN_BUILDER_NAMES=" + ",".join(sorted(names)))
        print("OPERATION_TYPE=" + str(type(builder.Operation)))
    finally:
        builder.Destroy()


if __name__ == "__main__":
    main()
