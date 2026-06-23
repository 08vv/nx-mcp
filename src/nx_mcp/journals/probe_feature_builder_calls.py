import json
import sys
import traceback
from pathlib import Path

import NXOpen


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd() / "feature_builder_probe.json"


def _names(obj, needles=()):
    return sorted(
        name for name in dir(obj)
        if not needles or any(needle.lower() in name.lower() for needle in needles)
    )


def _try(label, fn):
    try:
        value = fn()
        return {"label": label, "ok": True, "value": str(value)}
    except Exception as exc:
        return {"label": label, "ok": False, "error": str(exc), "traceback": traceback.format_exc()}


def main():
    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(_output_path().with_suffix(".prt")), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    vector = NXOpen.Vector3d(0.0, 1.0, 0.0)
    direction = work_part.Directions.CreateDirection(
        origin,
        vector,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )

    report = {"probes": []}
    report["probes"].append(_try("Axes.CreateAxis(point, direction)", lambda: work_part.Axes.CreateAxis(origin, direction, NXOpen.SmartObject.UpdateOption.WithinModeling)))
    report["probes"].append(_try("Axes.CreateAxis(point, vector)", lambda: work_part.Axes.CreateAxis(origin, vector, NXOpen.SmartObject.UpdateOption.WithinModeling)))
    report["probes"].append(_try("Planes.CreatePlane(point, vector)", lambda: work_part.Planes.CreatePlane(origin, vector, NXOpen.SmartObject.UpdateOption.WithinModeling)))

    mirror = work_part.Features.CreateMirrorFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        report["mirror_feature_set_names"] = _names(mirror.FeatureSet, ("add", "remove", "clear"))
        report["mirror_plane_names"] = _names(mirror.Plane, ("set", "object", "value"))
        report["mirror_plane_constructor_names"] = _names(mirror.PlaneConstructor or object())
    finally:
        mirror.Destroy()

    pattern = work_part.Features.CreatePatternFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        report["pattern_feature_list_names"] = _names(pattern.FeatureList, ("add", "remove", "clear"))
        service = pattern.PatternService
        report["pattern_service_names"] = _names(
            service,
            ("count", "pitch", "spacing", "direction", "vector", "linear", "pattern", "distance", "orientation", "rect"),
        )
        report["pattern_service_all_names"] = _names(service)
        for name in report["pattern_service_names"]:
            try:
                report.setdefault("pattern_service_values", {})[name] = str(getattr(service, name))
            except Exception as exc:
                report.setdefault("pattern_service_values", {})[name] = f"<get failed: {exc}>"
        rect = service.RectangularDefinition
        report["rectangular_names"] = _names(rect)
        report["rectangular_interesting_names"] = _names(
            rect,
            ("count", "pitch", "spacing", "distance", "direction", "vector", "x", "y", "primary", "secondary"),
        )
        for name in report["rectangular_interesting_names"]:
            try:
                report.setdefault("rectangular_values", {})[name] = str(getattr(rect, name))
            except Exception as exc:
                report.setdefault("rectangular_values", {})[name] = f"<get failed: {exc}>"
        increments = service.PatternIncrementsBuilder
        report["increments_names"] = _names(
            increments,
            ("count", "pitch", "spacing", "distance", "direction", "increment", "primary", "secondary"),
        )
        for name in report["increments_names"]:
            try:
                report.setdefault("increments_values", {})[name] = str(getattr(increments, name))
            except Exception as exc:
                report.setdefault("increments_values", {})[name] = f"<get failed: {exc}>"
        xspacing = rect.XSpacing
        report["xspacing_names"] = _names(xspacing)
        report["xspacing_interesting_names"] = _names(
            xspacing,
            ("count", "pitch", "span", "spacing", "distance", "number", "expression"),
        )
        for name in report["xspacing_interesting_names"]:
            try:
                report.setdefault("xspacing_values", {})[name] = str(getattr(xspacing, name))
            except Exception as exc:
                report.setdefault("xspacing_values", {})[name] = f"<get failed: {exc}>"
        inc1 = increments.IncrementsListInDirection1
        report["increment_list_names"] = _names(inc1)
        report["increment_list_interesting_names"] = _names(inc1, ("add", "count", "pitch", "spacing", "distance", "expression"))
    finally:
        pattern.Destroy()

    path = _output_path()
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
