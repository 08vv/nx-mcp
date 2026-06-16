from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass
from importlib import resources
from pathlib import Path


class NXBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class JournalResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def find_run_journal() -> Path:
    base_dir = os.environ.get("UGII_BASE_DIR")
    candidates = []

    if base_dir:
        base_path = Path(base_dir)
        candidates.extend(
            [
                base_path / "NXBIN" / "run_journal.exe",
                base_path / "UGII" / "run_journal.exe",
            ]
        )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise NXBridgeError(
        "Could not find run_journal.exe. Set UGII_BASE_DIR to the Siemens NX "
        "installation directory, such as C:\\Program Files\\Siemens\\NX2206."
    )


def packaged_journal(name: str) -> Path:
    return Path(resources.files("nx_mcp.journals").joinpath(name))


def run_journal(journal_path: str | Path, *args: str, timeout: int = 120) -> JournalResult:
    journal = Path(journal_path)
    if not journal.exists():
        raise NXBridgeError(f"Journal file does not exist: {journal}")

    command = [str(find_run_journal()), str(journal)]
    if args:
        command.extend(["-args", *args])

    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return JournalResult(completed.returncode, completed.stdout, completed.stderr)


def validate_nxopen(timeout: int = 120) -> JournalResult:
    return run_journal(packaged_journal("validate_nxopen.py"), timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run nx-mcp Siemens NX bridge checks.")
    parser.add_argument(
        "command",
        choices=["validate"],
        help="Bridge command to run.",
    )
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    if args.command == "validate":
        result = validate_nxopen(timeout=args.timeout)
    else:
        raise NXBridgeError(f"Unknown command: {args.command}")

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
