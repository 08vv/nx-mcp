"""
edit_shaft_expressions.py
=========================
NX Journal — edits named expressions inside an existing parametric shaft .prt
IN-PLACE.  No new file is created.

Operations performed
--------------------
  1. Open the target .prt  (or use the already-open work part if it matches).
  2. Locate named expressions by name.
  3. Set new RHS values so the model updates parametrically.
  4. Force a model update (session update cycle).
  5. Save the part in-place.
  6. Auto-open / bring forward in the NX GUI.

Usage
-----
  run_journal.exe edit_shaft_expressions.py
    -args <full_path_to.prt> <EXPR_NAME=VALUE> [<EXPR_NAME=VALUE> ...]

Example
-------
  run_journal.exe edit_shaft_expressions.py
    -args C:\\Users\\HP\\nx-mcp\\parametric_shaft_with_keyway.prt
          SHAFT_DIAMETER=40 SHAFT_LENGTH=200
"""

import sys
import os
import subprocess
from pathlib import Path

import NXOpen


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_args():
    """
    Returns (prt_path: Path, edits: dict[str, str])
    Edits values are kept as strings so they can be expression RHS values.
    """
    args = sys.argv[1:]          # argv[0] is the journal script itself in NX
    if not args:
        raise ValueError(
            "Usage: edit_shaft_expressions.py <path.prt> NAME=VALUE ..."
        )
    prt_path = Path(args[0]).resolve()
    edits = {}
    for token in args[1:]:
        if "=" not in token:
            raise ValueError("Each edit must be in NAME=VALUE format, got: {}".format(token))
        name, _, value = token.partition("=")
        edits[name.strip()] = value.strip()
    return prt_path, edits


def _find_expression(work_part, name: str):
    """Return the NX Expression object with the given name, or None."""
    for expr in work_part.Expressions:
        try:
            if expr.Name == name:
                return expr
        except Exception:
            continue
    return None


def _set_expression_value(work_part, name: str, new_rhs: str):
    """
    Update an existing named expression's right-hand side to *new_rhs*.
    Raises RuntimeError if the expression is not found.
    """
    expr = _find_expression(work_part, name)
    if expr is None:
        raise RuntimeError(
            "Expression '{}' not found in part. "
            "Available expressions: {}".format(
                name,
                ", ".join(
                    e.Name for e in work_part.Expressions
                    if hasattr(e, "Name") and e.Name
                ),
            )
        )
    # EditWithUnits works for simple numeric expressions in any unit system
    work_part.Expressions.EditWithUnits(expr, NXOpen.Unit.Null, new_rhs)
    print("[OK] {} -> {}".format(name, new_rhs))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    prt_path, edits = _parse_args()

    if not prt_path.exists():
        raise FileNotFoundError("Part file not found: {}".format(prt_path))

    session = NXOpen.Session.GetSession()

    # ------------------------------------------------------------------
    # 1. Open the part (NX will reuse it if already loaded)
    # ------------------------------------------------------------------
    base_part, load_status = session.Parts.OpenActiveDisplay(
        str(prt_path),
        NXOpen.DisplayPartOption.AllowAdditional,
    )
    load_status.Dispose()
    work_part = session.Parts.Work
    print("[OK] Opened part: {}".format(prt_path.name))

    # ------------------------------------------------------------------
    # 2. Edit each named expression in-place
    # ------------------------------------------------------------------
    print("[OK] Applying {} expression edit(s)...".format(len(edits)))
    for name, value in edits.items():
        _set_expression_value(work_part, name, value)

    # ------------------------------------------------------------------
    # 3. Force model update so geometry reflects new values
    # ------------------------------------------------------------------
    session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)
    print("[OK] Model update complete")

    # ------------------------------------------------------------------
    # 4. Fit view
    # ------------------------------------------------------------------
    work_part.ModelingViews.WorkView.Fit()

    # ------------------------------------------------------------------
    # 5. Save the part IN-PLACE (same file, no rename)
    # ------------------------------------------------------------------
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("[OK] Part saved in-place -> {}".format(prt_path))

    # ------------------------------------------------------------------
    # 6. Update latest_nx_result.txt
    # ------------------------------------------------------------------
    try:
        latest_file = prt_path.parent / "latest_nx_result.txt"
        latest_file.write_text(str(prt_path), encoding="utf-8")
        print("[OK] latest_nx_result.txt updated")
    except Exception as exc:
        print("[WARN] Could not update latest_nx_result.txt: {}".format(exc))

    # ------------------------------------------------------------------
    # 7. Bring forward / open in NX GUI
    # ------------------------------------------------------------------
    try:
        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        router_candidates = [
            base_path / "NXBIN" / "ugs_router.exe",
            base_path / "UGII"  / "ugs_router.exe",
        ]
        ugs_router = next((c for c in router_candidates if c.exists()), None)
        if ugs_router:
            subprocess.Popen(
                [str(ugs_router), "-ug", "-use_file_dir", str(prt_path)]
            )
            print("[OK] NX GUI launched -> {}".format(prt_path.name))
        else:
            print("[WARN] ugs_router.exe not found - open the part manually in NX")
    except Exception as exc:
        print("[WARN] Could not launch NX GUI: {}".format(exc))


if __name__ == "__main__":
    main()
