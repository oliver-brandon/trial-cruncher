"""Embedded desktop shell for the locally bundled interface."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QMainWindow

from trial_cruncher.gui.update_controls import UpdateControls
from trial_cruncher.gui.web_bridge import WebBridge
from trial_cruncher.gui.window import MainWindow

ASSET_DIRECTORY = Path(__file__).parent / "web"
INDEX = (ASSET_DIRECTORY / "index.html").resolve()


class AssetRequests(QWebEngineUrlRequestInterceptor):
    """Limit the renderer to bundled assets and Qt's channel script."""

    def interceptRequest(self, request: QWebEngineUrlRequestInfo) -> None:
        url = request.requestUrl()
        if url.scheme() == "qrc" and url.path() == "/qtwebchannel/qwebchannel.js":
            return
        if url.isLocalFile() and not url.host():
            path = Path(url.toLocalFile()).resolve()
            if path.is_relative_to(ASSET_DIRECTORY.resolve()):
                return
        request.block(True)


class LocalPage(QWebEnginePage):
    def acceptNavigationRequest(self, url: QUrl, navigation_type, is_main_frame: bool) -> bool:
        return url.isLocalFile() and not url.host() and Path(url.toLocalFile()).resolve() == INDEX


class WebShell(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Trial Cruncher")
        self.setWindowIcon(QIcon(str(ASSET_DIRECTORY / "icons" / "trial-cruncher.png")))
        self._closing = False
        self.update_action = self.menuBar().addMenu("Help").addAction("Check for Updates…")
        self.update_controls = UpdateControls(self)
        self.update_action.triggered.connect(self.update_controls.offer)
        self.resize(1300, 900)
        self.controller = MainWindow()
        self.controller.setParent(self, Qt.WindowType.Window)
        self.controller.dialog_parent = self
        self.bridge = WebBridge(self.controller, self)
        self.view = QWebEngineView(self)
        self.profile = QWebEngineProfile(self)
        self.page = LocalPage(self.profile, self.view)
        self.view.setPage(self.page)
        self.interceptor = AssetRequests(self)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.channel = QWebChannel(self.page)
        self.channel.registerObject("trialBridge", self.bridge)
        self.page.setWebChannel(self.channel)
        self.setCentralWidget(self.view)
        self.view.loadFinished.connect(self._load_finished)
        self.page.renderProcessTerminated.connect(self._renderer_failed)
        self.view.load(QUrl.fromLocalFile(str(INDEX)))

    def _show_failure(self, message: str) -> None:
        label = QLabel(message, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("background: #101521; color: #f3f6fc; padding: 30px;")
        self.setCentralWidget(label)

    def _load_finished(self, ok: bool) -> None:
        if not ok:
            self._show_failure(
                "The Trial Cruncher interface could not be loaded. Restart the application."
            )

    def _renderer_failed(self, status, exit_code: int) -> None:
        self._show_failure(
            "The Trial Cruncher interface stopped unexpectedly. Restart the application."
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        self.update_controls.stop_checks()
        if self.controller._is_working() or self.update_controls.tasks:
            if not self._closing:
                self._closing = True
                self.controller.close()
                self._wait_for_workers()
            event.ignore()
            return
        self.controller.close()
        event.accept()

    def _wait_for_workers(self) -> None:
        if self.controller._is_working() or self.update_controls.tasks:
            QTimer.singleShot(100, self._wait_for_workers)
        else:
            self.close()
