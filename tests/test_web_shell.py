"""Shell request boundaries and native dialog ownership."""

import os

import pytest
from PySide6.QtCore import QByteArray, QPoint, QSize, QUrl
from PySide6.QtWidgets import QFileDialog

from trial_cruncher.gui import preferences
from trial_cruncher.gui.web_shell import INDEX, AssetRequests, LocalPage

pytestmark = pytest.mark.skipif(
    os.environ.get("TRIAL_CRUNCHER_WEBENGINE_TESTS") != "1",
    reason="WebEngine integration requires a working Chromium runtime",
)


class Request:
    def __init__(self, url):
        self.url = QUrl(url)
        self.blocked = False

    def requestUrl(self):
        return self.url

    def block(self, blocked):
        self.blocked = blocked


def test_asset_interceptor_rejects_network_and_unrelated_local_files(app, tmp_path):
    guard = AssetRequests()
    for url, blocked in (
        (QUrl.fromLocalFile(str(INDEX)).toString(), False),
        ("qrc:///qtwebchannel/qwebchannel.js", False),
        ("https://example.org/", True),
        ("http://127.0.0.1:8123/", True),
        (QUrl.fromLocalFile(str(tmp_path / "secret.txt")).toString(), True),
        ("qrc:///other.js", True),
    ):
        request = Request(url)
        guard.interceptRequest(request)
        assert request.blocked is blocked


def test_navigation_accepts_only_application_index(app, tmp_path):
    page = LocalPage()
    assert page.acceptNavigationRequest(QUrl.fromLocalFile(str(INDEX)), None, True)
    assert not page.acceptNavigationRequest(QUrl("https://example.org/"), None, True)
    assert not page.acceptNavigationRequest(QUrl.fromLocalFile(str(tmp_path / "x")), None, True)


def test_file_picker_uses_visible_shell_as_parent(app, monkeypatch):
    from trial_cruncher.gui.web_shell import WebShell

    shell = WebShell()
    parents = []
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames", lambda parent, *args: (parents.append(parent) or [], "")
    )
    try:
        shell.controller.choose_files()
        assert parents == [shell]
    finally:
        shell.close()


def test_close_waits_for_active_controller_work(app, monkeypatch):
    from trial_cruncher.gui.web_shell import WebShell

    shell = WebShell()
    shell.show()
    working = [True]
    monkeypatch.setattr(shell.controller, "_is_working", lambda: working[0])
    try:
        assert shell.close() is False
        assert shell.isVisible()
        assert not preferences.workspace_settings().contains("window/geometry")
        assert shell.controller._closing
        working[0] = False
        shell._wait_for_workers()
        assert not shell.isVisible()
        assert preferences.workspace_settings().contains("window/geometry")
    finally:
        working[0] = False
        shell.close()


@pytest.mark.parametrize("invalid", [None, "corrupt", QByteArray(b"invalid geometry")])
def test_window_geometry_survives_reopening(app, invalid):
    from trial_cruncher.gui.web_shell import WebShell

    if invalid is not None:
        preferences.workspace_settings().setValue("window/geometry", invalid)
    first = WebShell()
    assert first.size() == QSize(1300, 900)
    first.resize(640, 400)
    first.show()
    first.move(QPoint(55, 70))
    app.processEvents()
    position, size = first.pos(), first.size()
    assert first.close()

    reopened = WebShell()
    reopened.show()
    try:
        app.processEvents()
        assert reopened.pos() == position
        assert reopened.size() == size
    finally:
        reopened.close()
