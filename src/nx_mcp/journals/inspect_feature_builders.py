import json
import sys
from pathlib import Path

import NXOpen


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd() / "feature_builder_inspection.json"


def _names(obj, needles=()):
    names = []
    for name in dir(obj):
        if not needles or any(needle.lower() in name.lower() for needle in needles):
            names.append(name)
    return sorted(names)


def _value_repr(value):
    try:
        return str(value)
    except Exception as exc:
        return f"<repr failed: {exc}>"


def _enum_names(obj):
    result = {}
    for name in dir(obj):
        if name.startswith("_"):
            continue
        value = getattr(obj, name)
        if isinstance(value, type):
            result[name] = _names(value)
    return result


def _builder_report(work_part, name, factory, null_arg):
    try:
        builder = factory(null_arg)
    except Exception as exc:
        return {"error": f"create failed: {exc}"}

    try:
        report = {
            "type": str(type(builder)),
            "all_names": _names(builder),
            "selection_names": _names(
                builder,
                ("feature", "body", "target", "tool", "collector", "pattern", "axis", "plane", "direction"),
            ),
            "nested_enums": _enum_names(type(builder)),
        }
        for attr in report["selection_names"]:
            try:
                report.setdefault("selection_values", {})[attr] = _value_repr(getattr(builder, attr))
            except Exception as exc:
                report.setdefault("selection_values", {})[attr] = f"<get failed: {exc}>"
        return report
    finally:
        try:
            builder.Destroy()
        except Exception:
            pass


def main():
    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(
        str(_output_path().with_suffix(".prt")),
        NXOpen.Part.Units.Millimeters,
    )
    work_part = session.Parts.Work

    report = {
        "FeatureCollection_pattern_names": _names(work_part.Features, ("pattern", "mirror", "boolean", "revolve")),
        "BooleanBuilder_type_names": _enum_names(NXOpen.Features.BooleanBuilder),
        "Feature_BooleanType_names": _names(NXOpen.Features.Feature.BooleanType),
        "Axes_names": _names(getattr(work_part, "Axes", object()), ("create", "axis")),
        "Planes_names": _names(getattr(work_part, "Planes", object()), ("create", "plane")),
    }

    report["boolean"] = _builder_report(
        work_part,
        "boolean",
        work_part.Features.CreateBooleanBuilder,
        NXOpen.Features.BooleanFeature.Null,
    )
    report["revolve"] = _builder_report(
        work_part,
        "revolve",
        work_part.Features.CreateRevolveBuilder,
        NXOpen.Features.Feature.Null,
    )
    report["mirror"] = _builder_report(
        work_part,
        "mirror",
        work_part.Features.CreateMirrorFeatureBuilder,
        NXOpen.Features.Feature.Null,
    )
    report["pattern_feature"] = _builder_report(
        work_part,
        "pattern_feature",
        work_part.Features.CreatePatternFeatureBuilder,
        NXOpen.Features.Feature.Null,
    )

    output_path = _output_path()
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
