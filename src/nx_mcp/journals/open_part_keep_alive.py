import sys
import time
from pathlib import Path

import NXOpen


def _args():
    if len(sys.argv) < 2:
        raise ValueError("Expected part path argument")
    part_path = Path(sys.argv[1]).resolve()
    stop_path = (
        Path(sys.argv[2]).resolve()
        if len(sys.argv) > 2
        else part_path.with_suffix(".close_nx")
    )
    return part_path, stop_path


def main():
    part_path, stop_path = _args()
    if stop_path.exists():
        stop_path.unlink()

    session = NXOpen.Session.GetSession()
    session.Parts.Open(str(part_path))
    work_part = session.Parts.Work
    if work_part is not None:
        work_part.ModelingViews.WorkView.Fit()

    print(f"Opened part and keeping NX alive: {part_path}")
    print(f"Create this file to close the journal: {stop_path}")
    while not stop_path.exists():
        time.sleep(1)


if __name__ == "__main__":
    main()
