import json
import os
import subprocess
import threading
from importlib import resources
from pathlib import Path


DEFAULT_RUN_JOURNAL = r"C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe"


def _bridge_script_path():
    return Path(resources.files("nx_mcp.bridge").joinpath("nx_bridge.py"))


class NXBridgeProcess:
    _proc = None
    _lock = threading.Lock()

    @classmethod
    def _start(cls):
        run_journal = os.environ.get("NX_RUN_JOURNAL", DEFAULT_RUN_JOURNAL)
        bridge_script = _bridge_script_path()

        cls._proc = subprocess.Popen(
            [run_journal, str(bridge_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    @classmethod
    def _ensure_started(cls):
        if cls._proc is None or cls._proc.poll() is not None:
            cls._start()

    @classmethod
    def call(cls, tool, args):
        with cls._lock:
            cls._ensure_started()

            payload = json.dumps({"tool": tool, "args": args})
            try:
                cls._proc.stdin.write(payload + "\n")
                cls._proc.stdin.flush()
                line = cls._proc.stdout.readline()
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

            if not line:
                stderr = cls._proc.stderr.read() if cls._proc.stderr else ""
                return {"ok": False, "error": stderr or "NX bridge process exited"}

            try:
                return json.loads(line)
            except json.JSONDecodeError as exc:
                return {"ok": False, "error": f"Invalid bridge result JSON: {exc}"}


def call_nx(tool, args):
    return NXBridgeProcess.call(tool, args)


def run_tool(tool, **args):
    return call_nx(tool, args)
