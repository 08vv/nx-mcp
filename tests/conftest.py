import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from nx_mcp.nx_session import NXSession


@pytest.fixture(autouse=True)
def mock_nxopen_session(monkeypatch):
    monkeypatch.setenv("NX_MCP_USE_MOCK_NXOPEN", "1")
    yield
    NXSession.reset()
