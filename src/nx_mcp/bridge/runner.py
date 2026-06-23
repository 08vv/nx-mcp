import json
import os
import subprocess
import threading
import socket
import time
from importlib import resources
from pathlib import Path

DEFAULT_RUN_JOURNAL = r"C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe"
LIVE_PORT = 43210
CONFIG_PATH = Path("C:/Users/HP/nx-mcp/live_bridge_config.json")


def _bridge_script_path():
    return Path(resources.files("nx_mcp.bridge").joinpath("nx_bridge.py"))


def verify_nx_environment():
    base_dir = os.environ.get("UGII_BASE_DIR")
    if not base_dir:
        raise RuntimeError(
            "Environment variable UGII_BASE_DIR is not set. Please set it to the "
            "Siemens NX installation directory, such as C:\\Program Files\\Siemens\\NX2206."
        )

    base_path = Path(base_dir)
    missing = []

    # Check run_journal.exe
    run_journal_candidates = [
        base_path / "NXBIN" / "run_journal.exe",
        base_path / "UGII" / "run_journal.exe",
    ]
    run_journal_path = next((c for c in run_journal_candidates if c.exists()), None)
    if not run_journal_path:
        missing.append("run_journal.exe")

    # Check ugraf.exe
    ugraf_candidates = [
        base_path / "NXBIN" / "ugraf.exe",
        base_path / "UGII" / "ugraf.exe",
    ]
    ugraf_path = next((c for c in ugraf_candidates if c.exists()), None)
    if not ugraf_path:
        missing.append("ugraf.exe")

    # Check ugs_router.exe
    ugs_router_candidates = [
        base_path / "NXBIN" / "ugs_router.exe",
        base_path / "UGII" / "ugs_router.exe",
    ]
    ugs_router_path = next((c for c in ugs_router_candidates if c.exists()), None)
    if not ugs_router_path:
        missing.append("ugs_router.exe")

    if missing:
        raise RuntimeError(
            f"Missing required Siemens NX executables under {base_dir}: {', '.join(missing)}"
        )

    return run_journal_path, ugraf_path, ugs_router_path


def try_connect_socket(port=LIVE_PORT):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(("127.0.0.1", port))
        return s
    except Exception:
        return None


def launch_interactive_nx(part_path=None, port=LIVE_PORT):
    run_journal_path, ugraf_path, ugs_router_path = verify_nx_environment()

    config = {
        "part_path": str(Path(part_path).resolve()) if part_path else "",
        "port": port
    }
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f)

    bridge_script = _bridge_script_path()
    subprocess.Popen([str(ugraf_path), f"-auto={bridge_script}"])

    # Poll connection
    start_time = time.time()
    while time.time() - start_time < 12:
        s = try_connect_socket(port)
        if s:
            s.close()
            return True
        time.sleep(0.5)
    return False


class NXBridgeProcess:
    _proc = None
    _lock = threading.Lock()

    @classmethod
    def reset(cls):
        with cls._lock:
            # Delete configuration file to stop active socket bridge
            if CONFIG_PATH.exists():
                try:
                    CONFIG_PATH.unlink()
                except Exception:
                    pass

            proc = cls._proc
            cls._proc = None
            if proc is None or proc.poll() is not None:
                return
            try:
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:
                proc.kill()

    @classmethod
    def _start(cls):
        run_journal, _, _ = verify_nx_environment()
        bridge_script = _bridge_script_path()

        cls._proc = subprocess.Popen(
            [str(run_journal), str(bridge_script)],
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
        # 1. Verify NX is available
        verify_nx_environment()

        # 2. Extract part path if we are opening or creating a part
        part_path = None
        if tool == "create_part":
            part_path = args.get("filename")
        elif tool == "open_part":
            part_path = args.get("filepath")

        # 3. Check if active socket server is running
        s = try_connect_socket(LIVE_PORT)
        if s is None:
            # Not running. If we need to open or create, launch interactive NX GUI
            if tool in ("create_part", "open_part"):
                launched = launch_interactive_nx(part_path, LIVE_PORT)
                if launched:
                    s = try_connect_socket(LIVE_PORT)

        # 4. If socket is connected, execute command live in the GUI!
        if s is not None:
            try:
                payload = json.dumps({"tool": tool, "args": args}) + "\n"
                s.sendall(payload.encode("utf-8"))
                # Read response line
                buffer = ""
                while "\n" not in buffer:
                    chunk = s.recv(4096).decode("utf-8")
                    if not chunk:
                        break
                    buffer += chunk
                
                if "\n" in buffer:
                    line, _ = buffer.split("\n", 1)
                    return json.loads(line)
            except Exception as e:
                return {"ok": False, "error": f"Socket communication error: {e}"}
            finally:
                s.close()

        # 5. Fallback: Batch mode using run_journal.exe
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
                result = json.loads(line)
                # If a part was created or opened successfully in batch, open it in GUI too
                if result.get("ok") and tool in ("create_part", "open_part") and part_path:
                    # ugraf.exe <filepath> opens the interactive NX GUI with the file pre-loaded
                    _, ugraf_path, _ = verify_nx_environment()
                    subprocess.Popen([str(ugraf_path), str(Path(part_path).resolve())])
                return result
            except json.JSONDecodeError as exc:
                return {"ok": False, "error": f"Invalid bridge result JSON: {exc}"}


def call_nx(tool, args):
    return NXBridgeProcess.call(tool, args)


def reset_nx_bridge():
    NXBridgeProcess.reset()


def run_tool(tool, **args):
    return call_nx(tool, args)
