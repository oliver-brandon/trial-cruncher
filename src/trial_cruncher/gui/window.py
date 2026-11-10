"""File selection, read-only Med-PC review, and CSV/Excel export."""

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from trial_cruncher.discovery import (
    DEFAULT_EXTENSIONS,
    DiscoveryResult,
    discover_files,
    normalize_extensions,
)
from trial_cruncher.exporters import ExportFormat
from trial_cruncher.gui.export_worker import ExportWorker
from trial_cruncher.gui.import_worker import ImportWorker
from trial_cruncher.gui.overview import BatchOverview
from trial_cruncher.gui.phases import PhaseDialog
from trial_cruncher.gui.review import ReviewPanel
from trial_cruncher.processing import ImportResult

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
        self.resize(1300, 900)
        self.selected_files: set[Path] = set()
        self.phase_assignments: dict[Path, str] = {}
        self._worker: DiscoveryWorker | None = None
        self._import_worker: ImportWorker | None = None
        self._export_worker: ExportWorker | None = None
        self._closing = False
        self.import_results: dict[Path, ImportResult] = {}
        self._pool = QThreadPool.globalInstance()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(QLabel("From raw trials to analysis-ready data."))
        description = QLabel(
            "Add Med-PC session files or a folder, then import to review session details, "
            "metrics, decoded choices, and warnings. "
            "Supports PRL_BO, PRL_OPTO, and PRL_OPTO_CORSTIM."
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
        self.import_button = QPushButton("Import Med-PC")
        self.phase_button = QPushButton("Assign phases…")
        self.phase_button.setToolTip(
            "Assign phases for all files before import, including hidden rows"
        )
        self.import_button.setToolTip(
            "Import or re-read all files in the batch, including rows hidden by filters"
        )
        self.cancel_button = QPushButton("Cancel after current file")
        self.cancel_button.setEnabled(False)
        self.export_button = QPushButton("Export CSV…")
        self.excel_button = QPushButton("Export Excel…")
        self._export_label = "CSV"
        self.export_button.setToolTip(
            "Export all successfully imported sessions and choices to a new folder; "
            "filters do not limit export; failed and unimported files are listed in the manifest"
        )
        self.excel_button.setToolTip(
            "Export Sessions, Choices, Phase metrics, Quality, and Provenance "
            "in a new folder; filters do not limit export"
        )
        for button in (
            self.add_files_button,
            self.add_folder_button,
            self.clear_button,
            self.phase_button,
            self.import_button,
            self.cancel_button,
            self.export_button,
            self.excel_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.export_status = QLabel(
            "CSV and Excel exports include all successfully imported files, "
            "including rows hidden by filters."
        )
        self.export_status.setWordWrap(True)
        self.export_status.setTextFormat(Qt.TextFormat.PlainText)
        self.export_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.export_status)
        self.overview = BatchOverview()
        self.review = ReviewPanel()
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.overview)
        splitter.addWidget(self.review)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([280, 480])
        layout.addWidget(splitter, 1)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        layout.addWidget(QLabel("Discovery messages:"))
        self.issue_list = QListWidget()
        self.issue_list.setAccessibleName("Discovery messages")
        self.issue_list.setMaximumHeight(75)
        layout.addWidget(self.issue_list)
        self.setCentralWidget(container)
        self.statusBar().showMessage("0 candidate files selected")
        self.add_files_button.clicked.connect(self.choose_files)
        self.add_folder_button.clicked.connect(self.choose_folder)
        self.clear_button.clicked.connect(self.clear_selection)
        self.import_button.clicked.connect(self.import_selected_files)
        self.phase_button.clicked.connect(self.assign_phases)
        self.cancel_button.clicked.connect(self.cancel_import)
        self.export_button.clicked.connect(self.export_csv)
        self.excel_button.clicked.connect(self.export_excel)
        self.overview.path_selected.connect(self.review_path)
        self._set_busy(False)

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
        if self._closing or self._is_working():
            return
        try:
            extensions = normalize_extensions(self.extensions.text().split(","))
        except ValueError as exc:
            QMessageBox.warning(self, "Check file extensions", str(exc))
            return
        self._set_busy(True)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.statusBar().showMessage("Discovering files…")
        self._worker = DiscoveryWorker(paths, extensions, self.recursive.isChecked())
        self._worker.signals.finished.connect(self._discovery_finished)
        self._worker.signals.failed.connect(self._discovery_failed)
        self._pool.start(self._worker)

    @Slot(object)
    def _discovery_finished(self, result: DiscoveryResult) -> None:
        self.selected_files.update(result.files)
        self.overview.set_files(tuple(self.selected_files), self.import_results)
        self.issue_list.addItems(f"{issue.path}: {issue.message}" for issue in result.issues)
        if not result.files and not result.issues:
            self.issue_list.addItem("No files matched the configured extensions in this selection.")
        self._worker = None
        self.progress.hide()
        self._set_busy(False)
        self.statusBar().showMessage(f"{len(self.selected_files)} candidate files selected")
        self._finish_close()

    @Slot(str)
    def _discovery_failed(self, message: str) -> None:
        self._worker = None
        self.progress.hide()
        self._set_busy(False)
        self.issue_list.addItem(message)
        self.statusBar().showMessage("Discovery failed; existing selection retained")
        if not self._closing:
            QMessageBox.warning(self, "File discovery failed", message)
        self._finish_close()

    @Slot(object)
    def review_path(self, path: Path | None) -> None:
        if path is None:
            message = (
                "No files match the current filters. Reset filters to see the batch."
                if self.selected_files and not self.overview.proxy.rowCount()
                else "Select a row in the batch overview to review its source and results."
            )
            self.review.clear(message)
            return
        result = self.import_results.get(path)
        if result is None:
            self.review.clear(f"{path.name} — No import result yet.")
        else:
            self.review.show_result(result)

    @Slot()
    def assign_phases(self) -> None:
        if self._closing or self._is_working() or not self.selected_files:
            return
        dialog = PhaseDialog(
            tuple(sorted(self.selected_files, key=str)), self.phase_assignments, self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.phase_assignments = dialog.assignments()
            self.statusBar().showMessage(
                "Phase assignments saved. Import Med-PC to apply; "
                "exports use the last imported snapshot."
            )

    @Slot()
    def import_selected_files(self) -> None:
        if (
            self._closing
            or not self.selected_files
            or self._worker is not None
            or self._import_worker is not None
            or self._export_worker is not None
        ):
            return
        paths = tuple(sorted(self.selected_files, key=str))
        self.import_results.clear()
        self.overview.start_import()
        self.review_path(self.overview.current_path())
        self._import_worker = ImportWorker(paths, self.phase_assignments)
        self._import_worker.signals.result.connect(self._import_result)
        self._import_worker.signals.progress.connect(self._import_progress)
        self._import_worker.signals.finished.connect(self._import_finished)
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.progress.setFormat("%v / %m files")
        self.progress.show()
        self._set_busy(True)
        self.statusBar().showMessage(f"Importing {len(paths)} file(s)…")
        self._pool.start(self._import_worker)

    @Slot(object)
    def _import_result(self, result: ImportResult) -> None:
        self.import_results[result.source_file] = result
        self.overview.set_result(result)

    @Slot(int, int)
    def _import_progress(self, completed: int, total: int) -> None:
        self.progress.setValue(completed)

    @Slot(bool)
    def _import_finished(self, cancelled: bool) -> None:
        self._import_worker = None
        self.overview.finish_import()
        failures = sum(result.error is not None for result in self.import_results.values())
        warnings = sum(
            bool(result.session and result.session.warnings)
            for result in self.import_results.values()
        )
        count = len(self.import_results) - failures
        prefix = "Cancelled" if cancelled else "Import complete"
        self.statusBar().showMessage(
            f"{prefix}: {count} imported ({warnings} with warnings), {failures} failed; "
            f"{len(self.selected_files) - len(self.import_results)} not imported."
        )
        self._set_busy(False)
        self._finish_close()

    @Slot()
    def cancel_import(self) -> None:
        if self._import_worker is not None:
            self._import_worker.cancel()
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage(
                "Cancelling after the current file; finished results are kept."
            )

    def _is_working(self) -> bool:
        return any(
            worker is not None
            for worker in (self._worker, self._import_worker, self._export_worker)
        )

    @Slot()
    def export_csv(self) -> None:
        self._start_export("csv")

    @Slot()
    def export_excel(self) -> None:
        self._start_export("xlsx")

    def _start_export(self, export_format: ExportFormat) -> None:
        if self._closing or self._is_working():
            return
        count = sum(
            result.session is not None and not result.error
            for result in self.import_results.values()
        )
        if not count:
            return
        self._export_label = "Excel" if export_format == "xlsx" else "CSV"
        parent = QFileDialog.getExistingDirectory(
            self, f"Choose parent folder — a new {self._export_label} export folder will be created"
        )
        if not parent:
            return
        self._export_worker = ExportWorker(
            self.import_results, tuple(self.selected_files), Path(parent), export_format
        )
        self._export_worker.signals.finished.connect(self._export_finished)
        self._export_worker.signals.failed.connect(self._export_failed)
        self._set_busy(True)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.export_status.setText(
            f"Exporting {count} session(s); {len(self.selected_files) - count} failed or "
            "unimported file(s) will be recorded in the manifest."
        )
        self.statusBar().showMessage("Exporting sessions and choices…")
        self._pool.start(self._export_worker)

    @Slot(object)
    def _export_finished(self, destination: Path) -> None:
        self._export_worker = None
        self.progress.hide()
        self._set_busy(False)
        self.export_status.setText(
            f"Saved results.xlsx and manifest.json in: {destination}"
            if self._export_label == "Excel"
            else f"Saved CSV tables and manifest.json in: {destination}"
        )
        self.statusBar().showMessage(f"{self._export_label} export complete")
        self._finish_close()

    @Slot(str)
    def _export_failed(self, message: str) -> None:
        self._export_worker = None
        self.progress.hide()
        self._set_busy(False)
        self.export_status.setText(message)
        self.statusBar().showMessage(
            f"{self._export_label} export failed; imported results retained"
        )
        if not self._closing:
            QMessageBox.warning(self, f"{self._export_label} export failed", message)
        self._finish_close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._is_working():
            self._closing = True
            self.cancel_import()
            self.statusBar().showMessage("Finishing the current operation before closing…")
            event.ignore()
        else:
            event.accept()

    def _finish_close(self) -> None:
        if self._closing:
            QTimer.singleShot(0, self.close)

    def _set_busy(self, busy: bool) -> None:
        for widget in (
            self.add_files_button,
            self.add_folder_button,
            self.clear_button,
            self.extensions,
            self.recursive,
        ):
            widget.setEnabled(not busy and not self._closing)
        self.import_button.setEnabled(not busy and not self._closing and bool(self.selected_files))
        self.phase_button.setEnabled(self.import_button.isEnabled())
        self.cancel_button.setEnabled(busy and self._import_worker is not None)
        self.export_button.setEnabled(
            not busy
            and not self._closing
            and any(
                result.session is not None and not result.error
                for result in self.import_results.values()
            )
        )
        self.excel_button.setEnabled(self.export_button.isEnabled())

    @Slot()
    def clear_selection(self) -> None:
        if self._closing or self._is_working():
            return
        self.selected_files.clear()
        self.phase_assignments.clear()
        self.import_results.clear()
        self.overview.clear_filters()
        self.overview.set_files((), {})
        self.issue_list.clear()
        self.review.clear()
        self.progress.hide()
        self._set_busy(False)
        self.statusBar().showMessage("0 candidate files selected")
