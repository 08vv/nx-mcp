import importlib
import os


class NXOpenUnavailable(RuntimeError):
    """Raised when Siemens NXOpen is not importable in production mode."""


def load_nxopen():
    """Return the active NXOpen module.

    Production loads Siemens' real ``NXOpen`` module. Tests can set
    ``NX_MCP_USE_MOCK_NXOPEN=1`` to opt into the local mock explicitly.
    """
    if os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1":
        return importlib.import_module("nx_mcp.testing.mock_nxopen")

    try:
        return importlib.import_module("NXOpen")
    except ModuleNotFoundError as exc:
        raise NXOpenUnavailable(
            "Siemens NXOpen is not installed or not on PYTHONPATH. "
            "Install/configure Siemens NX, or set NX_MCP_USE_MOCK_NXOPEN=1 "
            "when running tests."
        ) from exc
