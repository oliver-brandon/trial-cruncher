"""Minimal candidate selection UI with filesystem traversal off the GUI thread."""

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from trial_cruncher.discovery import (
    DEFAULT_EXTENSIONS,
    DiscoveryResult,
    discover_files,
    normalize_extensions,
)

logger = logging.getLogger(__name__)


class DiscoverySignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class DiscoveryWorker(QRunnable):
    def __init__(self, paths: list[str], extensions: frozenset[str], recursive: bool) -> None:
        super().__init__()
        self.paths = paths
        self.extensions = extensions
        self.recursive = recursive
        self.signals = DiscoverySignals()

    @Slot()
    def run(self) -> None:
        try:
            result = discover_files(
                self.paths, extensions=self.extensions, recursive=self.recursive
            )
        except Exception:
            logger.exception("File discovery failed", extra={"operation": "discover"})
            self.signals.failed.emit(
                "Could not discover files. See the application log for details."
            )
        else:
            self.signals.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Trial Cruncher")
        self.resize(850, 550)
        self.selected_files: set[Path] = set()
        self._worker: DiscoveryWorker | None = None
        self._pool = QThreadPool.globalInstance()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel("From raw trials to analysis-ready data."))
        description = QLabel(
            "Select candidate behavioral files. "
            "Parsing, analysis, and export are not yet available."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        options = QHBoxLayout()
        label = QLabel("File extensions (comma-separated):")
        self.extensions = QLineEdit(", ".join(DEFAULT_EXTENSIONS))
        label.setBuddy(self.extensions)
        options.addWidget(label)
        options.addWidget(self.extensions)
        self.recursive = QCheckBox("Include subfolders")
        self.recursive.setChecked(True)
        options.addWidget(self.recursive)
        layout.addLayout(options)

        buttons = QHBoxLayout()
        self.add_files_button = QPushButton("Add files…")
        self.add_folder_button = QPushButton("Add folder…")
        self.clear_button = QPushButton("Clear selection")
        for button in (self.add_files_button, self.add_folder_button, self.clear_button):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.file_list = QListWidget()
        self.file_list.setAccessibleName("Selected candidate files")
        layout.addWidget(self.file_list)
        layout.addWidget(QLabel("Discovery messages:"))
        self.issue_list = QListWidget()
        self.issue_list.setAccessibleName("Discovery messages")
        self.issue_list.setMaximumHeight(120)
        layout.addWidget(self.issue_list)
        self.setCentralWidget(container)
        self.statusBar().showMessage("0 candidate files selected")
        self.add_files_button.clicked.connect(self.choose_files)
        self.add_folder_button.clicked.connect(self.choose_folder)
        self.clear_button.clicked.connect(self.clear_selection)

    @Slot()
    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select behavioral files", "", "All files (*)"
        )
        if paths:
            self.add_paths(paths)

    @Slot()
    def choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select a folder")
        if path:
            self.add_paths([path])

    def add_paths(self, paths: list[str]) -> None:
        if self._worker is not None:
            return
        try:
            extensions = normalize_extensions(self.extensions.text().split(","))
        except ValueError as exc:
            QMessageBox.warning(self, "Check file extensions", str(exc))
            return
        self._set_busy(True)
        self.statusBar().showMessage("Discovering files…")
        self._worker = DiscoveryWorker(paths, extensions, self.recursive.isChecked())
        self._worker.signals.finished.connect(self._discovery_finished)
        self._worker.signals.failed.connect(self._discovery_failed)
        self._pool.start(self._worker)

    @Slot(object)
    def _discovery_finished(self, result: DiscoveryResult) -> None:
        self.selected_files.update(result.files)
        self.file_list.clear()
        self.file_list.addItems(str(path) for path in sorted(self.selected_files, key=str))
        self.issue_list.addItems(f"{issue.path}: {issue.message}" for issue in result.issues)
        if not result.files and not result.issues:
            self.issue_list.addItem("No files matched the configured extensions in this selection.")
        self._worker = None
        self._set_busy(False)
        self.statusBar().showMessage(f"{len(self.selected_files)} candidate files selected")

    @Slot(str)
    def _discovery_failed(self, message: str) -> None:
        self._worker = None
        self._set_busy(False)
        self.issue_list.addItem(message)
        self.statusBar().showMessage("Discovery failed; existing selection retained")
        QMessageBox.warning(self, "File discovery failed", message)

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.add_files_button,
            self.add_folder_button,
            self.clear_button,
            self.extensions,
            self.recursive,
        ):
            widget.setEnabled(not busy)

    @Slot()
    def clear_selection(self) -> None:
        self.selected_files.clear()
        self.file_list.clear()
        self.issue_list.clear()
        self.statusBar().showMessage("0 candidate files selected")
