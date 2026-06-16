import subprocess

from nx_mcp import nx_bridge


def test_find_run_journal_from_ugii_base_dir(monkeypatch, tmp_path):
    run_journal = tmp_path / "NXBIN" / "run_journal.exe"
    run_journal.parent.mkdir()
    run_journal.write_text("", encoding="utf-8")
    monkeypatch.setenv("UGII_BASE_DIR", str(tmp_path))

    assert nx_bridge.find_run_journal() == run_journal


def test_run_journal_uses_run_journal_exe(monkeypatch, tmp_path):
    run_journal_exe = tmp_path / "NXBIN" / "run_journal.exe"
    run_journal_exe.parent.mkdir()
    run_journal_exe.write_text("", encoding="utf-8")
    journal = tmp_path / "probe.py"
    journal.write_text("print('probe')", encoding="utf-8")
    monkeypatch.setenv("UGII_BASE_DIR", str(tmp_path))

    calls = []

    def fake_run(command, check, capture_output, text, timeout):
        calls.append((command, check, capture_output, text, timeout))
        return subprocess.CompletedProcess(command, 0, "ok\n", "")

    monkeypatch.setattr(nx_bridge.subprocess, "run", fake_run)

    result = nx_bridge.run_journal(journal, "a", "b", timeout=3)

    assert result.ok
    assert result.stdout == "ok\n"
    assert calls == [
        (
            [str(run_journal_exe), str(journal), "-args", "a", "b"],
            False,
            True,
            True,
            3,
        )
    ]
