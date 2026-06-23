import json
import sys
import traceback
from pathlib import Path


def _repo_root():
    return Path(__file__).resolve().parents[3]


repo_root = _repo_root()
src_dir = repo_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import NXOpen  # noqa: E402
from nx_mcp.bridge import nx_bridge  # noqa: E402


SESSION = NXOpen.Session.GetSession()


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return repo_root / "live_validation" / "probe_revolve_mirror.json"


def _try(label, fn):
    try:
        value = fn()
        return {"label": label, "ok": True, "value": str(value)}
    except Exception as exc:
        return {
            "label": label,
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def _reset_state():
    nx_bridge._state["last_curves"] = []
    nx_bridge._state["last_feature"] = None
    nx_bridge._state["last_body"] = None
    nx_bridge._state["features"] = {}
    nx_bridge._state["bodies"] = {}


def _new_part(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    SESSION.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)
    _reset_state()
    return SESSION.Parts.Work


def _feature_name():
    return nx_bridge._feature_name(nx_bridge._state.get("last_feature"))


def _body_count():
    return len(nx_bridge._iter_bodies(SESSION.Parts.Work))


def _probe_mirror_plane_setvalue(out_dir):
    work_part = _new_part(out_dir / "probe_mirror_plane_setvalue.prt")
    nx_bridge.create_cuboid(12, 12, 12, 20, 0, 0)
    source_feature = nx_bridge._state["last_feature"]
    origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    normal = NXOpen.Vector3d(1.0, 0.0, 0.0)
    plane = work_part.Planes.CreatePlane(
        origin,
        normal,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )

    results = []
    for label, setter in [
        ("Plane.SetValue(plane)", lambda b: b.Plane.SetValue(plane)),
        ("Plane.SetValue(plane, origin)", lambda b: b.Plane.SetValue(plane, origin)),
        ("Plane.Value = plane", lambda b: setattr(b.Plane, "Value", plane)),
        ("PlaneConstructor = plane", lambda b: setattr(b, "PlaneConstructor", plane)),
        ("Plane.SetValue(None, plane, origin)", lambda b: b.Plane.SetValue(None, plane, origin)),
    ]:
        builder = work_part.Features.CreateMirrorFeatureBuilder(NXOpen.Features.Feature.Null)
        try:
            builder.FeatureSet.Add([source_feature])
            builder.PlaneOption = NXOpen.Features.MirrorFeatureBuilder.PlaneOptions.Existing
            result = _try(label, lambda builder=builder, setter=setter: setter(builder))
            if result["ok"]:
                commit = _try(f"{label} CommitFeature", builder.CommitFeature)
                result["commit"] = commit
        finally:
            try:
                builder.Destroy()
            except Exception:
                pass
        results.append(result)
    return results


def _probe_revolve_variants(out_dir):
    results = []
    variants = [
        ("axis Y, 360", "Y", 360),
        ("axis Z, 360", "Z", 360),
        ("axis Y, 180", "Y", 180),
    ]
    for label, axis, angle in variants:
        _new_part(out_dir / f"probe_revolve_{axis}_{angle}.prt")
        nx_bridge.create_sketch("XY")
        nx_bridge.draw_rectangle(6, -20, 4, 40)
        result = _try(label, lambda axis=axis, angle=angle: nx_bridge.revolve(axis, angle))
        result["last_feature"] = _feature_name()
        result["body_count"] = _body_count()
        results.append(result)
    return results


def _names(obj, needles=()):
    return sorted(
        name for name in dir(obj)
        if not needles or any(needle.lower() in name.lower() for needle in needles)
    )


def _probe_api_surface(out_dir):
    work_part = _new_part(out_dir / "probe_api_surface.prt")
    report = {
        "uf_modl_revolve_names": _names(nx_bridge.UF_SESSION.Modl, ("revol", "sweep")),
        "uf_modl_revolve_docs": {},
        "uf_modl_mirror_names": _names(nx_bridge.UF_SESSION.Modl, ("mirror", "reflect")),
        "uf_modl_mirror_docs": {},
        "feature_revolve_mirror_names": _names(
            work_part.Features,
            ("revol", "mirror", "datum", "plane"),
        ),
        "work_part_datum_names": _names(work_part, ("datum", "plane")),
        "feature_sign_names": _names(NXOpen.UF.Modl.FeatureSigns),
    }
    for name in report["uf_modl_revolve_names"]:
        value = getattr(nx_bridge.UF_SESSION.Modl, name, None)
        report["uf_modl_revolve_docs"][name] = str(getattr(value, "__doc__", ""))
    for name in report["uf_modl_mirror_names"]:
        value = getattr(nx_bridge.UF_SESSION.Modl, name, None)
        report["uf_modl_mirror_docs"][name] = str(getattr(value, "__doc__", ""))

    for label, factory in [
        (
            "mirror_body",
            lambda: work_part.Features.CreateMirrorBodyBuilder(NXOpen.Features.Feature.Null),
        ),
        (
            "datum_plane",
            lambda: work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null),
        ),
    ]:
        try:
            builder = factory()
        except Exception as exc:
            report[label] = {"error": str(exc)}
            continue
        try:
            report[label] = {
                "names": _names(builder),
                "interesting_names": _names(
                    builder,
                    ("body", "feature", "plane", "datum", "mirror", "collector", "select"),
                ),
            }
            plane_select = getattr(builder, "Plane", None)
            if plane_select is not None:
                report[label]["plane_setvalue_doc"] = str(getattr(plane_select.SetValue, "__doc__", ""))
            for name in report[label]["interesting_names"]:
                try:
                    report[label].setdefault("values", {})[name] = str(getattr(builder, name))
                except Exception as exc:
                    report[label].setdefault("values", {})[name] = f"<get failed: {exc}>"
        finally:
            try:
                builder.Destroy()
            except Exception:
                pass
    return report


def _probe_mirror_body_and_datum(out_dir):
    work_part = _new_part(out_dir / "probe_mirror_body_datum.prt")
    nx_bridge.create_cuboid(12, 12, 12, 20, 0, 0)
    source_body = nx_bridge._state["last_body"]
    origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    view = work_part.ModelingViews.WorkView
    normal = NXOpen.Vector3d(1.0, 0.0, 0.0)
    plane = work_part.Planes.CreatePlane(
        origin,
        normal,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )

    report = []
    datum_builder = work_part.Features.CreateDatumPlaneBuilder(NXOpen.Features.Feature.Null)
    datum = None
    datum_feature = None
    try:
        report.append({"DatumPlaneBuilder.FixedType_names": _names(datum_builder.FixedType)})
        report.append(_try("DatumPlaneBuilder.SetFixedDatumPlane(plane)", lambda: datum_builder.SetFixedDatumPlane(plane)))
        commit = _try("DatumPlaneBuilder.CommitFeature", datum_builder.CommitFeature)
        report.append(commit)
        if commit["ok"]:
            datum_feature = nx_bridge._state.get("last_feature")
        report.append(_try("DatumPlaneBuilder.GetDatum", lambda: datum_builder.GetDatum()))
        if commit["ok"]:
            try:
                datum = datum_builder.GetDatum()
            except Exception:
                datum = None
    finally:
        try:
            datum_builder.Destroy()
        except Exception:
            pass

    bodies = [source_body]
    for label, plane_obj in [
        ("MirrorBody Plane.SetValue(plane)", plane),
        ("MirrorBody Plane.SetValue(datum)", datum),
        ("MirrorBody Plane.SetValue(datum, origin)", (datum, origin)),
        ("MirrorBody Plane.SetValue(datum, view, origin)", (datum, view, origin)),
        ("MirrorBody Plane.Value = datum", ("value", datum)),
        ("MirrorBody Plane.SetValue(datum_feature)", datum_feature),
        ("MirrorBody Plane.SetValue(datum_feature, origin)", (datum_feature, origin)),
    ]:
        builder = work_part.Features.CreateMirrorBodyBuilder(NXOpen.Features.Feature.Null)
        try:
            builder.MirrorBodyList.Add(bodies)
            def set_plane(builder=builder, plane_obj=plane_obj):
                if isinstance(plane_obj, tuple) and plane_obj and plane_obj[0] == "value":
                    builder.Plane.Value = plane_obj[1]
                    return None
                if isinstance(plane_obj, tuple):
                    return builder.Plane.SetValue(*plane_obj)
                return builder.Plane.SetValue(plane_obj)

            result = _try(label, set_plane)
            if result["ok"]:
                result["commit"] = _try(f"{label} CommitFeature", builder.CommitFeature)
            report.append(result)
        finally:
            try:
                builder.Destroy()
            except Exception:
                pass
    report.append({"final_body_count": _body_count(), "last_feature": _feature_name()})
    return report


def _probe_uf_revolve(out_dir):
    results = []
    variants = [
        ("CreateRevolution tags", "CreateRevolution"),
    ]
    for label, method_name in variants:
        _new_part(out_dir / "probe_uf_revolve.prt")
        nx_bridge.create_sketch("XY")
        nx_bridge.draw_rectangle(6, -20, 4, 40)
        curves = list(nx_bridge._state["last_curves"])
        tags = [curve.Tag for curve in curves]
        method = getattr(nx_bridge.UF_SESSION.Modl, method_name)
        result = _try(
            label,
            lambda method=method, tags=tags: method(
                tags,
                len(tags),
                None,
                ["0", "360"],
                ["0", "0"],
                [8.0, 0.0, 0.0],
                True,
                True,
                [0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                NXOpen.UF.Modl.FeatureSigns.Nullsign,
            ),
        )
        result["last_feature"] = _feature_name()
        result["body_count"] = _body_count()
        results.append(result)
    return results


def main():
    output_path = _output_path()
    out_dir = output_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "api_surface": _probe_api_surface(out_dir),
        "mirror_body_and_datum": _probe_mirror_body_and_datum(out_dir),
        "uf_revolve": _probe_uf_revolve(out_dir),
        "mirror_plane_setvalue": _probe_mirror_plane_setvalue(out_dir),
        "revolve_variants": _probe_revolve_variants(out_dir),
    }
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
