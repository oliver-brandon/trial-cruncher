"""The frozen CLI uses the regular argument parser and a separate GUI launcher."""

import importlib.util
from pathlib import Path

from trial_cruncher.cli import main


def test_cli_dispatch_uses_argument_parser(tmp_path, capsys):
    calls = []
    assert main(["--gui"], gui_launcher=lambda: calls.append(True) or 0) == 0
    assert calls == [True]
    assert main(["--inspect-medpc", str(tmp_path / "--gui")], gui_launcher=lambda: 9) == 1
    assert calls == [True]


def test_frozen_launcher_locates_installed_windows_app(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "packaging" / "cli_entry.py"
    spec = importlib.util.spec_from_file_location("packaged_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    desktop = tmp_path / "Trial Cruncher.exe"
    desktop.touch()
    spawned = []
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.sys, "executable", str(tmp_path / "trial-cruncher-cli.exe"))
    monkeypatch.setattr(module.subprocess, "Popen", lambda args, **kw: spawned.append(args))
    assert module.launch_desktop() == 0
    assert spawned == [[str(desktop)]]
