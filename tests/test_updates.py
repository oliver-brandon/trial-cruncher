"""Updater state transitions are verified with an isolated fake backend."""

import pytest

from trial_cruncher import updates
from trial_cruncher.updates import (
    UpdateConfigurationError,
    UpdateRelease,
    UpdateService,
    UpdateState,
)


class Backend:
    channel = "stable-win-x64"
    package_id = updates.UPDATE_PACKAGE_ID

    def __init__(self):
        self.applied = False

    def check(self):
        return UpdateRelease("1.2.0")

    def download(self, release, progress=None):
        if progress:
            progress(100)

    def apply_and_restart(self, release):
        self.applied = True


def test_update_requires_download_before_install(monkeypatch):
    monkeypatch.setattr(updates, "update_channel", lambda: "stable-win-x64")
    backend = Backend()
    service = UpdateService(lambda: backend, current_version="1.1.0", channel=backend.channel)
    assert service.check().state == UpdateState.AVAILABLE
    with pytest.raises(RuntimeError):
        service.install_and_restart()
    assert service.download().state == UpdateState.READY
    assert service.install_and_restart().state == UpdateState.INSTALLING
    assert backend.applied


def test_wrong_channel_and_linux_are_rejected(monkeypatch):
    monkeypatch.setattr(
        updates, "update_target", lambda: (_ for _ in ()).throw(ValueError("Linux"))
    )
    assert not updates.velopack_runtime_available()
    with pytest.raises(UpdateConfigurationError):
        updates.VelopackBackend()
    with pytest.raises(UpdateConfigurationError):
        updates.validate_update_channel("stable-win-x64", "stable-osx-arm64")


def test_offline_check_is_unavailable(monkeypatch):
    monkeypatch.setattr(updates, "update_channel", lambda: "stable-win-x64")

    def fail():
        raise OSError("offline")

    service = UpdateService(fail, channel="stable-win-x64")
    assert service.check().state == UpdateState.UNAVAILABLE


def test_stable_velopack_adapter_checks_package_and_release(monkeypatch):
    import sys
    from types import SimpleNamespace

    calls = []

    class Manager:
        def __init__(self, source, options):
            calls.append((source, options))

        def get_app_id(self):
            return updates.UPDATE_PACKAGE_ID

        def check_for_updates(self):
            return SimpleNamespace(
                TargetFullRelease=SimpleNamespace(
                    PackageId=updates.UPDATE_PACKAGE_ID, Version="2.0.0", NotesMarkdown="Notes"
                )
            )

    fake = SimpleNamespace(
        GithubSource=lambda *args: args,
        UpdateOptions=lambda *args: args,
        UpdateManager=Manager,
    )
    monkeypatch.setitem(sys.modules, "velopack", fake)
    monkeypatch.setattr(updates, "update_target", lambda: ("stable-win-x64", "win-x64"))
    monkeypatch.setattr(updates, "update_channel", lambda: "stable-win-x64")
    backend = updates.VelopackBackend()
    assert calls[0][0][2] is False
    assert calls[0][1][-1] == "stable-win-x64"
    assert backend.check().version == "2.0.0"
    monkeypatch.setattr(Manager, "get_app_id", lambda self: "wrong.package")
    with pytest.raises(UpdateConfigurationError):
        updates.VelopackBackend()


def test_check_rejects_old_version_and_wrong_backend(monkeypatch):
    monkeypatch.setattr(updates, "update_channel", lambda: "stable-win-x64")
    backend = Backend()
    service = UpdateService(lambda: backend, current_version="2.0", channel=backend.channel)
    assert service.check().state == UpdateState.CURRENT
    backend.package_id = "wrong.package"
    assert (
        UpdateService(lambda: backend, channel=backend.channel).check().state
        == UpdateState.DISABLED
    )


def test_restart_is_blocked_until_project_saved_and_work_finishes(app, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMainWindow, QMessageBox

    from trial_cruncher.gui.update_controls import UpdateControls
    from trial_cruncher.updates import UpdateSnapshot

    monkeypatch.setattr(updates, "update_channel", lambda: "stable-win-x64")
    shell = QMainWindow()
    shell._closing = False
    shell.controller = SimpleNamespace(_project_dirty=True, _is_working=lambda: False)
    controls = UpdateControls(shell)
    release = UpdateRelease("2.0.0")
    controls.service._snapshot = UpdateSnapshot(
        UpdateState.READY, "1.0.0", "stable-win-x64", release=release
    )
    alerts = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: alerts.append(args[-1]))
    try:
        controls.offer()
        assert "Save your project" in alerts[-1]
        shell.controller._project_dirty = False
        shell.controller._is_working = lambda: True
        controls.offer()
        assert "current operation" in alerts[-1]
    finally:
        shell.close()


def test_actual_worker_emits_on_gui_thread_and_keeps_ready_update(app, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QMainWindow
    from qt_helpers import wait_until

    from trial_cruncher.gui import update_controls
    from trial_cruncher.gui.update_controls import UpdateControls

    monkeypatch.setattr(updates, "update_channel", lambda: "stable-win-x64")
    monkeypatch.setattr(update_controls, "velopack_runtime_available", lambda: False)
    shell = QMainWindow()
    shell._closing = False
    shell.controller = SimpleNamespace(_project_dirty=False, _is_working=lambda: False)
    controls = UpdateControls(shell)
    backend = Backend()
    controls.service = UpdateService(
        lambda: backend, current_version="1.0", channel=backend.channel
    )
    threads = []

    def checked(snapshot):
        threads.append(QThread.currentThread() == app.thread())
        controls._checked(snapshot, False)

    try:
        controls._run(controls.service.check, checked)
        wait_until(app, lambda: not controls.tasks)
        assert threads == [True]
        assert controls.indicator.text() == "Update 1.2.0"
        controls.service._snapshot = updates.UpdateSnapshot(
            UpdateState.READY, "1.0", backend.channel, release=UpdateRelease("1.2.0")
        )
        monkeypatch.setattr(update_controls, "velopack_runtime_available", lambda: True)
        controls.check(False)
        assert controls.service.snapshot.state == UpdateState.READY
        assert not controls.tasks
    finally:
        shell.close()


def test_unsupported_mac_source_launch_has_no_feed(monkeypatch):
    import sys

    monkeypatch.setattr(
        updates, "update_target", lambda: (_ for _ in ()).throw(ValueError("Intel"))
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert updates.update_channel() == "stable-source"
    assert not updates.velopack_runtime_available()
    assert updates.create_update_service().channel == "stable-source"


def test_one_confirmation_downloads_and_hands_off_to_installer(app, monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMainWindow, QMessageBox
    from qt_helpers import wait_until

    from trial_cruncher.gui.update_controls import UpdateControls

    monkeypatch.setattr(updates, "update_channel", lambda: "stable-win-x64")
    shell = QMainWindow()
    shell._closing = False
    shell.controller = SimpleNamespace(
        _project_dirty=False, _is_working=lambda: False, _set_busy=lambda _: None
    )
    controls = UpdateControls(shell)
    backend = Backend()
    controls.service = UpdateService(
        lambda: backend, current_version="0.1.0", channel=backend.channel
    )
    prompts = []

    def approve(*args):
        prompts.append(args[-1])
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", approve)
    try:
        assert controls.service.check().state == UpdateState.AVAILABLE
        controls.offer()
        wait_until(app, lambda: backend.applied and not controls.tasks)
        assert len(prompts) == 1
        assert controls.service.snapshot.state == UpdateState.INSTALLING
    finally:
        shell.close()
