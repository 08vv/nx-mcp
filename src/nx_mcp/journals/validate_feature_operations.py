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


def _output_dir():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return repo_root / "live_validation"


def _reset_bridge_state():
    nx_bridge._state["last_curves"] = []
    nx_bridge._state["last_feature"] = None
    nx_bridge._state["last_body"] = None
    nx_bridge._state["features"] = {}
    nx_bridge._state["bodies"] = {}


def _new_part(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    SESSION.Parts.NewDisplay(str(path), NXOpen.Part.Units.Millimeters)
    _reset_bridge_state()


def _features():
    work_part = SESSION.Parts.Work
    if work_part is None:
        return []
    try:
        return list(work_part.Features.ToArray() or [])
    except Exception:
        return []


def _bodies():
    return nx_bridge._iter_bodies(SESSION.Parts.Work)


def _state_name(kind):
    obj = nx_bridge._state.get(kind)
    if obj is None:
        return None
    if kind == "last_feature":
        return nx_bridge._feature_name(obj)
    return nx_bridge._body_name(obj)


def _snapshot():
    return {
        "feature_count": len(_features()),
        "body_count": len(_bodies()),
        "last_feature": _state_name("last_feature"),
        "last_body": _state_name("last_body"),
    }


def _save_current_part():
    work_part = SESSION.Parts.Work
    if work_part is None:
        return
    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )


def _dispatch(tool, args=None):
    return nx_bridge.dispatch({"tool": tool, "args": args or {}})


def _record(results, name, output_path, commands):
    _new_part(output_path)
    entry = {"name": name, "part": str(output_path), "commands": [], "ok": True}
    before = _snapshot()

    try:
        for tool, args in commands:
            result = _dispatch(tool, args)
            entry["commands"].append({"tool": tool, "args": args, "result": result})
            if not result.get("ok"):
                entry["ok"] = False
                entry["error"] = result.get("error")
                break

        after = _snapshot()
        entry["before"] = before
        entry["after"] = after
        if (
            entry["ok"]
            and after["feature_count"] <= before["feature_count"]
            and after["last_feature"] == before["last_feature"]
        ):
            entry["ok"] = False
            entry["error"] = "No new feature was created"
        if entry["ok"] and after["body_count"] < 1:
            entry["ok"] = False
            entry["error"] = "No solid body was found after operation"
        _save_current_part()
    except Exception as exc:
        entry["ok"] = False
        entry["error"] = str(exc)
        entry["traceback"] = traceback.format_exc()

    results.append(entry)


def _body_ref():
    return nx_bridge._body_name(nx_bridge._state["last_body"])


def _feature_ref():
    return nx_bridge._feature_name(nx_bridge._state["last_feature"])


def _record_boolean_unite(results, output_path):
    _new_part(output_path)
    entry = {"name": "boolean_unite", "part": str(output_path), "commands": [], "ok": True}
    before = _snapshot()
    try:
        result = _dispatch(
            "create_cuboid",
            {"length": 30, "width": 20, "height": 12, "x": 0, "y": 0, "z": 0},
        )
        entry["commands"].append({"tool": "create_cuboid", "result": result})
        target = _body_ref()
        result = _dispatch(
            "create_cuboid",
            {"length": 20, "width": 20, "height": 12, "x": 25, "y": 0, "z": 0},
        )
        entry["commands"].append({"tool": "create_cuboid", "result": result})
        tool = _body_ref()
        result = _dispatch("boolean_unite", {"target": target, "tool": tool})
        entry["commands"].append({"tool": "boolean_unite", "args": {"target": target, "tool": tool}, "result": result})
        entry["ok"] = bool(result.get("ok"))
        entry["error"] = result.get("error")
        entry["before"] = before
        entry["after"] = _snapshot()
        _save_current_part()
    except Exception as exc:
        entry["ok"] = False
        entry["error"] = str(exc)
        entry["traceback"] = traceback.format_exc()
    results.append(entry)


def _record_boolean_subtract(results, output_path):
    _new_part(output_path)
    entry = {"name": "boolean_subtract", "part": str(output_path), "commands": [], "ok": True}
    before = _snapshot()
    try:
        result = _dispatch(
            "create_cuboid",
            {"length": 50, "width": 35, "height": 15, "x": 0, "y": 0, "z": 0},
        )
        entry["commands"].append({"tool": "create_cuboid", "result": result})
        target = _body_ref()
        result = _dispatch(
            "create_cylinder",
            {"radius": 5, "height": 25, "x": 25, "y": 17.5, "z": 20, "direction": "-Z"},
        )
        entry["commands"].append({"tool": "create_cylinder", "result": result})
        tool = _body_ref()
        result = _dispatch("boolean_subtract", {"target": target, "tool": tool})
        entry["commands"].append({"tool": "boolean_subtract", "args": {"target": target, "tool": tool}, "result": result})
        entry["ok"] = bool(result.get("ok"))
        entry["error"] = result.get("error")
        entry["before"] = before
        entry["after"] = _snapshot()
        _save_current_part()
    except Exception as exc:
        entry["ok"] = False
        entry["error"] = str(exc)
        entry["traceback"] = traceback.format_exc()
    results.append(entry)


def _record_mirror(results, output_path):
    _new_part(output_path)
    entry = {"name": "mirror_feature", "part": str(output_path), "commands": [], "ok": True}
    before = _snapshot()
    try:
        result = _dispatch(
            "create_cuboid",
            {"length": 12, "width": 12, "height": 12, "x": 20, "y": 0, "z": 0},
        )
        entry["commands"].append({"tool": "create_cuboid", "result": result})
        feature = _feature_ref()
        result = _dispatch("mirror_feature", {"feature_name": feature, "plane": "YZ"})
        entry["commands"].append({"tool": "mirror_feature", "args": {"feature_name": feature, "plane": "YZ"}, "result": result})
        entry["ok"] = bool(result.get("ok"))
        entry["error"] = result.get("error")
        entry["before"] = before
        entry["after"] = _snapshot()
        _save_current_part()
    except Exception as exc:
        entry["ok"] = False
        entry["error"] = str(exc)
        entry["traceback"] = traceback.format_exc()
    results.append(entry)


def _record_pattern(results, output_path):
    _new_part(output_path)
    entry = {"name": "pattern_feature", "part": str(output_path), "commands": [], "ok": True}
    before = _snapshot()
    try:
        result = _dispatch(
            "create_cylinder",
            {"radius": 3, "height": 10, "x": 0, "y": 0, "z": 0, "direction": "Z"},
        )
        entry["commands"].append({"tool": "create_cylinder", "result": result})
        feature = _feature_ref()
        result = _dispatch("pattern_feature", {"feature_name": feature, "direction": "X", "count": 4, "pitch": 15})
        entry["commands"].append({"tool": "pattern_feature", "args": {"feature_name": feature}, "result": result})
        entry["ok"] = bool(result.get("ok"))
        entry["error"] = result.get("error")
        entry["before"] = before
        entry["after"] = _snapshot()
        _save_current_part()
    except Exception as exc:
        entry["ok"] = False
        entry["error"] = str(exc)
        entry["traceback"] = traceback.format_exc()
    results.append(entry)


def main():
    out_dir = _output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "feature_validation_results.json"
    results = []

    def write_results():
        result_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    _record(
        results,
        "create_cylinder",
        out_dir / "validate_create_cylinder.prt",
        [("create_cylinder", {"radius": 10, "height": 35, "x": 0, "y": 0, "z": 0, "direction": "Z"})],
    )
    write_results()
    _record(
        results,
        "add_hole",
        out_dir / "validate_add_hole.prt",
        [
            ("create_cuboid", {"length": 60, "width": 40, "height": 12, "x": 0, "y": 0, "z": 0}),
            ("add_hole", {"x": 30, "y": 20, "z": 12, "diameter": 8, "depth": 16, "target": "last", "direction": "-Z"}),
        ],
    )
    write_results()
    _record_boolean_unite(results, out_dir / "validate_boolean_unite.prt")
    write_results()
    _record_boolean_subtract(results, out_dir / "validate_boolean_subtract.prt")
    write_results()
    _record(
        results,
        "add_fillet",
        out_dir / "validate_add_fillet.prt",
        [
            ("create_cuboid", {"length": 40, "width": 30, "height": 16, "x": 0, "y": 0, "z": 0}),
            ("add_fillet", {"radius": 2, "body": "last", "edges": "vertical_edges"}),
        ],
    )
    write_results()
    _record(
        results,
        "add_chamfer",
        out_dir / "validate_add_chamfer.prt",
        [
            ("create_cuboid", {"length": 40, "width": 30, "height": 16, "x": 0, "y": 0, "z": 0}),
            ("add_chamfer", {"offset": 2, "body": "last", "edges": "top_edges"}),
        ],
    )
    write_results()
    _record(
        results,
        "revolve",
        out_dir / "validate_revolve.prt",
        [
            ("create_sketch", {"plane": "XY"}),
            ("draw_rectangle", {"x": 6, "y": -20, "width": 4, "height": 40}),
            ("revolve", {"axis": "Y", "angle_deg": 360}),
        ],
    )
    write_results()
    _record_mirror(results, out_dir / "validate_mirror_feature.prt")
    write_results()
    _record_pattern(results, out_dir / "validate_pattern_feature.prt")
    write_results()

    print(json.dumps(results, indent=2))

    failed = [entry for entry in results if not entry.get("ok")]
    if failed:
        print(f"FAILED_VALIDATIONS={len(failed)}")
        raise SystemExit(1)
    print("ALL_VALIDATIONS_PASSED")


if __name__ == "__main__":
    main()
