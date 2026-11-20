"""Background update checks and explicit restart for packaged installations."""

import logging

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QPushButton

from trial_cruncher.updates import UpdateState, create_update_service, velopack_runtime_available

logger = logging.getLogger(__name__)


class UpdateSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int)


class UpdateTask(QRunnable):
    def __init__(self, operation, with_progress=False):
        super().__init__()
        self.operation = operation
        self.with_progress = with_progress
        self.signals = UpdateSignals()

    @Slot()
    def run(self):
        try:
            result = (
                self.operation(self.signals.progress.emit)
                if self.with_progress
                else self.operation()
            )
        except Exception:
            logger.exception("Unexpected updater failure")
            self.signals.failed.emit("The update could not be completed. Please try again.")
        else:
            self.signals.finished.emit(result)


class UpdateControls(QObject):
    """Own the updater task and route completion on the GUI thread."""

    def __init__(self, shell):
        super().__init__(shell)
        self.shell = shell
        self.service = create_update_service()
        self.tasks = set()
        self._task = None
        self._restarting = False
        self._done = None
        self.progress_dialog = None
        self.indicator = QPushButton(shell)
        self.indicator.setStyleSheet(
            "QPushButton { background:#df7622; color:white; border:0;"
            "border-radius:5px; padding:5px 12px; font-weight:600; }"
        )
        self.indicator.clicked.connect(self.offer)
        self.indicator.hide()
        shell.statusBar().addPermanentWidget(self.indicator)
        shell.statusBar().hide()
        self.timer = QTimer(self)
        self.timer.setInterval(6 * 60 * 60 * 1000)
        self.timer.timeout.connect(lambda: self.check(False))
        self.first_check = QTimer(self)
        self.first_check.setSingleShot(True)
        self.first_check.timeout.connect(lambda: self.check(False))
        if velopack_runtime_available():
            self.timer.start()
            self.first_check.start(5000)

    def stop_checks(self):
        self.timer.stop()
        self.first_check.stop()

    def _run(self, operation, done, *, with_progress=False):
        if self._task is not None:
            return
        task = UpdateTask(operation, with_progress)
        self._task, self._done = task, done
        self.tasks.add(task)
        task.signals.progress.connect(self._progress)
        task.signals.finished.connect(self._finished)
        task.signals.failed.connect(self._failed)
        QThreadPool.globalInstance().start(task)

    def _release_task(self):
        task = self._task
        self._task = None
        self.tasks.discard(task)
        done, self._done = self._done, None
        return done

    @Slot(object)
    def _finished(self, result):
        done = self._release_task()
        if done:
            done(result)

    @Slot(str)
    def _failed(self, message):
        self._release_task()
        self._close_progress()
        if self._restarting and not self.shell._closing:
            self._restarting = False
            self.shell.controller._closing = False
            self.shell.controller._set_busy(self.shell.controller._is_working())
        if not self.shell._closing:
            QMessageBox.warning(self.shell, "Updates", message)

    def check(self, manual=True):
        if self.shell._closing:
            return
        if self.tasks:
            if manual:
                QMessageBox.information(
                    self.shell, "Updates", "An update operation is in progress."
                )
            return
        if not velopack_runtime_available():
            if manual:
                QMessageBox.information(
                    self.shell,
                    "Updates",
                    "Updates are available in supported installed macOS and Windows builds. "
                    "This launch is not managed by the updater.",
                )
            return
        if self.service.snapshot.state in {
            UpdateState.AVAILABLE,
            UpdateState.READY,
            UpdateState.DOWNLOAD_FAILED,
            UpdateState.INSTALL_FAILED,
        }:
            if manual:
                self.offer()
            return
        self._run(self.service.check, lambda result: self._checked(result, manual))

    def _checked(self, result, manual):
        if self.shell._closing:
            return
        if result.state == UpdateState.AVAILABLE:
            self.indicator.setText(f"Update {result.release.version}")
            self.shell.statusBar().show()
            self.indicator.show()
            if manual:
                self.offer()
        elif manual:
            QMessageBox.information(self.shell, "Updates", result.message)

    def offer(self):
        if self.tasks:
            return
        snapshot = self.service.snapshot
        if snapshot.state not in {
            UpdateState.AVAILABLE,
            UpdateState.DOWNLOAD_FAILED,
            UpdateState.READY,
            UpdateState.INSTALL_FAILED,
        }:
            self.check()
            return
        if self.shell.controller._is_working():
            QMessageBox.information(
                self.shell, "Updates", "Wait for the current operation to finish."
            )
            return
        if self.shell.controller._project_dirty:
            QMessageBox.information(
                self.shell, "Updates", "Save your project before restarting to update."
            )
            return
        release = snapshot.release
        answer = QMessageBox.question(
            self.shell,
            "Trial Cruncher update",
            f"Version {release.version} is available.\n\n{release.notes_markdown}\n\n"
            "Download and restart to install the update?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if snapshot.state in (UpdateState.READY, UpdateState.INSTALL_FAILED):
            self._install()
            return
        self.progress_dialog = QProgressDialog("Downloading update…", "", 0, 100, self.shell)
        self.progress_dialog.setWindowTitle("Trial Cruncher update")
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.show()
        self._run(self.service.download, self._downloaded, with_progress=True)

    @Slot(int)
    def _progress(self, value):
        if self.progress_dialog is not None:
            self.progress_dialog.setValue(max(0, min(100, value)))

    def _close_progress(self):
        if self.progress_dialog is not None:
            self.progress_dialog.close()
            self.progress_dialog.deleteLater()
            self.progress_dialog = None

    def _downloaded(self, result):
        self._close_progress()
        if self.shell._closing:
            return
        if result.state == UpdateState.READY:
            self.indicator.setText("Restart to update")
            self._install()
        else:
            QMessageBox.warning(self.shell, "Updates", result.message)

    def _install(self):
        # User edits can occur during download, so recheck before handoff.
        if self.shell.controller._is_working() or self.shell.controller._project_dirty:
            QMessageBox.information(
                self.shell,
                "Updates",
                "Save your project and finish the current operation, "
                "then choose Restart to update.",
            )
            return
        self._restarting = True
        self.shell.controller._closing = True
        self.shell.controller._set_busy(True)
        self._run(self.service.install_and_restart, self._installed)

    def _installed(self, result):
        if result.state == UpdateState.INSTALL_FAILED:
            self._restarting = False
            if self.shell._closing:
                return
            self.shell.controller._closing = False
            self.shell.controller._set_busy(self.shell.controller._is_working())
            self.indicator.setText("Retry update")
            QMessageBox.warning(self.shell, "Updates", result.message)
