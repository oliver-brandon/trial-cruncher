"""File selection, read-only Med-PC review, and CSV/Excel export."""

import logging
from dataclasses import replace
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from trial_cruncher.aggregation import AnalysisPlan
from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.discovery import (
    DEFAULT_EXTENSIONS,
    DiscoveryResult,
    discover_files,
    normalize_extensions,
)
from trial_cruncher.exporters import ExportFormat
from trial_cruncher.gui.animal_analysis import AnalysisReview, AnalysisWorker, PlanDialog
from trial_cruncher.gui.export_worker import ExportWorker
from trial_cruncher.gui.import_worker import ImportWorker
from trial_cruncher.gui.metadata import MetadataDialog
from trial_cruncher.gui.overview import BatchOverview
from trial_cruncher.gui.phase_overview import BatchPhaseOverview
from trial_cruncher.gui.phases import PhaseDialog
from trial_cruncher.gui.project_worker import ProjectWorker
from trial_cruncher.gui.review import ReviewPanel
from trial_cruncher.processing import ImportResult
from trial_cruncher.projects import PROJECT_SUFFIX, ProjectResult
from trial_cruncher.source_tracking import SourceCheck

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
        self.metadata_assignments: dict[Path, AnalysisMetadata] = {}
        self.analysis_plan: AnalysisPlan | None = None
        self._analysis_worker: AnalysisWorker | None = None
        self._worker: DiscoveryWorker | None = None
        self._import_worker: ImportWorker | None = None
        self._export_worker: ExportWorker | None = None
        self._project_worker: ProjectWorker | None = None
        self._project_path: Path | None = None
        self._project_sha256: str | None = None
        self._source_hashes: dict[Path, str | None] = {}
        self._source_issues: dict[Path, str] = {}
        self._project_dirty = False
        self._reviewed_path: Path | None = None
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
        project_bar = QHBoxLayout()
        self.open_project_button = QPushButton("Open project…")
        self.save_project_button = QPushButton("Save project")
        self.save_project_as_button = QPushButton("Save project as…")
        self.check_sources_button = QPushButton("Check sources")
        for button in (
            self.open_project_button,
            self.save_project_button,
            self.save_project_as_button,
            self.check_sources_button,
        ):
            project_bar.addWidget(button)
        self.analysis_button = QPushButton("Animal analysis…")
        self.analysis_button.clicked.connect(self.configure_analysis)
        project_bar.addWidget(self.analysis_button)
        project_bar.addStretch()
        layout.addLayout(project_bar)
        self.project_label = QLabel("Project: unsaved")
        self.project_label.setTextFormat(Qt.TextFormat.PlainText)
        self.project_label.setWordWrap(True)
        layout.addWidget(self.project_label)
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
        self.metadata_button = QPushButton("Session metadata…")
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
            self.metadata_button,
            self.import_button,
            self.cancel_button,
            self.export_button,
            self.excel_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.export_status = QLabel(
            "Exports retain all successful files with inclusion flags, including Excluded, "
            "Not reviewed, and rows hidden by filters."
        )
        self.export_status.setWordWrap(True)
        self.export_status.setTextFormat(Qt.TextFormat.PlainText)
        self.export_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.export_status)
        self.overview = BatchOverview()
        self.phase_overview = BatchPhaseOverview(self.overview.model)
        self.batch_tabs = QTabWidget()
        self.batch_tabs.addTab(self.overview, "Sessions")
        self.batch_tabs.addTab(self.phase_overview, "Phase results")
        self.review = ReviewPanel()
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.batch_tabs)
        splitter.addWidget(self.review)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 300])
        layout.addWidget(splitter, 1)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        layout.addWidget(QLabel("File and project messages:"))
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
        self.metadata_button.clicked.connect(self.assign_metadata)
        self.cancel_button.clicked.connect(self.cancel_import)
        self.export_button.clicked.connect(self.export_csv)
        self.excel_button.clicked.connect(self.export_excel)
        self.overview.path_selected.connect(
            lambda path: self._batch_path_selected(self.overview, path)
        )
        self.phase_overview.path_selected.connect(
            lambda path: self._batch_path_selected(self.phase_overview, path)
        )
        self.batch_tabs.currentChanged.connect(self._batch_tab_changed)
        self.open_project_button.clicked.connect(self.open_project)
        self.save_project_button.clicked.connect(self.save_project)
        self.save_project_as_button.clicked.connect(self.save_project_as)
        self.check_sources_button.clicked.connect(self.check_source_files)
        self.extensions.textChanged.connect(self._mark_project_dirty)
        self.recursive.toggled.connect(self._mark_project_dirty)
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
        if result.files:
            self._mark_project_dirty()
        self.overview.set_files(
            tuple(self.selected_files), self.import_results, self.metadata_assignments
        )
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
        self._reviewed_path = path
        if path is None:
            message = (
                "No files match the current filters. Reset filters to see the batch."
                if self.selected_files and not self._active_batch().proxy.rowCount()
                else "Select a row in the batch overview to review its source and results."
            )
            self.review.clear(message)
            return
        if path in self._source_issues:
            self.review.clear(f"{path.name} — {self._source_issues[path]}")
            self.review.show_analysis_metadata(
                path, self.metadata_assignments.get(path, AnalysisMetadata())
            )
            return
        result = self.import_results.get(path)
        if result is None:
            self.review.clear(f"{path.name} — No import result yet.")
            self.review.show_analysis_metadata(
                path, self.metadata_assignments.get(path, AnalysisMetadata())
            )
        else:
            self.review.show_result(result)

    def _active_batch(self) -> BatchOverview | BatchPhaseOverview:
        return (
            self.phase_overview
            if self.batch_tabs.currentWidget() is self.phase_overview
            else self.overview
        )

    def _batch_path_selected(
        self, view: BatchOverview | BatchPhaseOverview, path: Path | None
    ) -> None:
        if self._active_batch() is not view:
            return
        self.review_path(path)
        result = self.import_results.get(path)
        if (
            view is self.phase_overview
            and path is not None
            and view.column_view.currentText() == "Experiment metadata"
        ):
            self.review.tabs.setCurrentWidget(self.review.analysis_details)
            return
        if (
            view is self.phase_overview
            and result
            and result.session
            and path not in self._source_issues
        ):
            self.review.tabs.setCurrentWidget(
                self.review.metric_page if view.proxy.rate_view else self.review.phase_page
            )

    def _batch_tab_changed(self, *args) -> None:
        self._active_batch().select_path(self._reviewed_path)

    @Slot()
    def assign_phases(self) -> None:
        if self._closing or self._is_working() or not self.selected_files:
            return
        dialog = PhaseDialog(
            tuple(sorted(self.selected_files, key=str)), self.phase_assignments, self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.phase_assignments = dialog.assignments()
            self._mark_project_dirty()
            self.statusBar().showMessage(
                "Phase assignments saved. Import Med-PC to apply; "
                "exports use the last imported snapshot."
            )

    @Slot()
    def assign_metadata(self) -> None:
        if self._closing or self._is_working() or not self.selected_files:
            return
        dialog = MetadataDialog(
            tuple(sorted(self.selected_files, key=str)), self.metadata_assignments, self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = self._active_batch().current_path()
            self.metadata_assignments = dialog.assignments()
            self.import_results = {
                path: replace(
                    result,
                    analysis_metadata=self.metadata_assignments.get(path, AnalysisMetadata()),
                )
                for path, result in self.import_results.items()
            }
            self.overview.set_files(
                tuple(self.selected_files), self.import_results, self.metadata_assignments
            )
            self.overview.model.set_source_issues(self._source_issues)
            self._active_batch().select_path(selected)
            self._mark_project_dirty()
            self.statusBar().showMessage(
                "Metadata applied. All recordings remain in exports with their inclusion flags."
            )

    @Slot()
    def import_selected_files(self) -> None:
        if self._closing or not self.selected_files or self._is_working():
            return
        paths = tuple(sorted(self.selected_files, key=str))
        self.import_results.clear()
        self._source_issues.clear()
        self._update_project_label()
        self.overview.start_import()
        self.review_path(self._active_batch().current_path())
        self._import_worker = ImportWorker(paths, self.phase_assignments, self.metadata_assignments)
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
        self._source_issues.pop(result.source_file, None)
        if result.raw is not None:
            digest = result.raw["source_sha256"]
            if self._source_hashes.get(result.source_file) != digest:
                self._source_hashes[result.source_file] = digest
                self._mark_project_dirty()
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
            for worker in (
                self._worker,
                self._import_worker,
                self._export_worker,
                self._project_worker,
                self._analysis_worker,
            )
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
            self.import_results,
            tuple(self.selected_files),
            Path(parent),
            export_format,
            self.metadata_assignments,
            self.analysis_plan,
        )
        self._export_worker.signals.finished.connect(self._export_finished)
        self._export_worker.signals.failed.connect(self._export_failed)
        self._export_worker.signals.sources_changed.connect(self._apply_source_checks)
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
            f"{self._export_label} export failed; check the reported issue"
        )
        if not self._closing:
            QMessageBox.warning(self, f"{self._export_label} export failed", message)
        self._finish_close()

    @Slot()
    def configure_analysis(self):
        if self._closing or self._is_working():
            return
        labels = self.metadata_assignments.values()
        dialog = PlanDialog(
            {a.cohort for a in labels if a.cohort},
            {a.condition for a in labels if a.condition},
            {
                r.phase_summary.config.phase
                for r in self.import_results.values()
                if r.phase_summary and r.phase_summary.config.phase
            },
            self.analysis_plan,
            self,
        )
        action = dialog.exec()
        if action == PlanDialog.EDIT_METADATA:
            self.assign_metadata()
            return
        if action != QDialog.DialogCode.Accepted:
            return
        if self.analysis_plan != dialog.plan:
            self.analysis_plan = dialog.plan
            self._mark_project_dirty()
        if self.analysis_plan is None:
            return
        worker = AnalysisWorker(
            self.analysis_plan, self.import_results, self.selected_files, self.metadata_assignments
        )
        self._analysis_worker = worker
        worker.signals.finished.connect(self._analysis_finished)
        worker.signals.failed.connect(self._analysis_failed)
        worker.signals.changed.connect(self._apply_source_checks)
        self._set_busy(True)
        self.statusBar().showMessage("Building animal analysis…")
        self._pool.start(worker)

    @Slot(object)
    def _analysis_finished(self, tables):
        self._analysis_worker = None
        self._set_busy(False)
        self.statusBar().showMessage(
            "Animal analysis ready. CSV and Excel exports include the analysis tables."
        )
        if not self._closing:
            review = AnalysisReview(self.analysis_plan, tables, self)
            review.exec()
            review.deleteLater()
        self._finish_close()

    @Slot(str)
    def _analysis_failed(self, message):
        self._analysis_worker = None
        self._set_busy(False)
        self.statusBar().showMessage("Animal analysis unavailable")
        if not self._closing:
            QMessageBox.warning(self, "Animal analysis", message)
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
            self.open_project_button,
            self.save_project_button,
            self.save_project_as_button,
        ):
            widget.setEnabled(not busy and not self._closing)
        self.import_button.setEnabled(not busy and not self._closing and bool(self.selected_files))
        self.analysis_button.setEnabled(self.import_button.isEnabled())
        self.phase_button.setEnabled(self.import_button.isEnabled())
        self.metadata_button.setEnabled(self.import_button.isEnabled())
        self.check_sources_button.setEnabled(self.import_button.isEnabled())
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
        self.analysis_plan = None
        self.selected_files.clear()
        self.phase_assignments.clear()
        self.metadata_assignments.clear()
        self._source_hashes.clear()
        self._source_issues.clear()
        self._mark_project_dirty()
        self.import_results.clear()
        self.overview.clear_filters()
        self.phase_overview.clear_filters()
        self.overview.set_files((), {})
        self.issue_list.clear()
        self.review.clear()
        self.progress.hide()
        self._set_busy(False)
        self.statusBar().showMessage("0 candidate files selected")

    def _update_project_label(self) -> None:
        name = str(self._project_path) if self._project_path else "unsaved"
        dirty = " · unsaved changes" if self._project_dirty else ""
        issues = f" · {len(self._source_issues)} source issue(s)" if self._source_issues else ""
        analysis = (
            f" · Animal analysis: {self.analysis_plan.cohort} ({self.analysis_plan.design})"
            if self.analysis_plan
            else ""
        )
        self.project_label.setText(f"Project: {name}{dirty}{issues}{analysis}")

    def _mark_project_dirty(self) -> None:
        self._project_dirty = True
        self._update_project_label()

    @Slot(object)
    def _apply_source_checks(self, checks: tuple[SourceCheck, ...]) -> None:
        current = self._active_batch().current_path()
        if current not in self.selected_files:
            current = None
        for check in checks:
            if check.status != "unchanged":
                self._source_issues[check.path] = check.message
                self.import_results.pop(check.path, None)
                self.issue_list.addItem(f"{check.path}: {check.message}")
            else:
                self._source_issues.pop(check.path, None)
        self.overview.set_files(
            tuple(self.selected_files), self.import_results, self.metadata_assignments
        )
        self.overview.model.set_source_issues(self._source_issues)
        if current is not None:
            self._active_batch().select_path(current)
        self.review_path(self._active_batch().current_path())
        self._update_project_label()
        self._set_busy(self._is_working())

    def _start_project_worker(self, worker: ProjectWorker) -> None:
        self._project_worker = worker
        worker.signals.finished.connect(self._project_finished)
        worker.signals.failed.connect(self._project_failed)
        self._set_busy(True)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.statusBar().showMessage("Checking project and source files…")
        self._pool.start(worker)

    @Slot()
    def open_project(self) -> None:
        if self._closing or self._is_working():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open project — replaces the current selection on success",
            "",
            f"Trial Cruncher projects (*{PROJECT_SUFFIX})",
        )
        if path:
            self._start_project_worker(ProjectWorker("load", Path(path)))

    @Slot()
    def save_project(self) -> None:
        self._save_project(False)

    @Slot()
    def save_project_as(self) -> None:
        self._save_project(True)

    def _save_project(self, save_as: bool) -> None:
        if self._closing or self._is_working():
            return
        try:
            extensions = tuple(sorted(normalize_extensions(self.extensions.text().split(","))))
        except ValueError as exc:
            QMessageBox.warning(self, "Check file extensions", str(exc))
            return
        path = self._project_path
        expected = self._project_sha256
        if save_as or path is None:
            text, _ = QFileDialog.getSaveFileName(
                self,
                "Save project as a new file",
                f"trial-cruncher{PROJECT_SUFFIX}",
                f"Trial Cruncher projects (*{PROJECT_SUFFIX})",
                options=QFileDialog.Option.DontConfirmOverwrite,
            )
            if not text:
                return
            path = Path(text if text.endswith(PROJECT_SUFFIX) else text + PROJECT_SUFFIX)
            expected = None
        self._start_project_worker(
            ProjectWorker(
                "save",
                path,
                paths=tuple(self.selected_files),
                phases=self.phase_assignments,
                hashes=self._source_hashes,
                extensions=extensions,
                recursive=self.recursive.isChecked(),
                expected_project_sha256=expected,
                metadata=self.metadata_assignments,
                analysis_plan=self.analysis_plan,
            )
        )

    @Slot()
    def check_source_files(self) -> None:
        if self._closing or self._is_working() or not self.selected_files:
            return
        self._start_project_worker(
            ProjectWorker(
                "check", hashes={p: self._source_hashes.get(p) for p in self.selected_files}
            )
        )

    @Slot(object)
    def _project_finished(self, result: ProjectResult | tuple[SourceCheck, ...]) -> None:
        mode = self._project_worker.mode
        self._project_worker = None
        self.progress.hide()
        if mode == "check":
            self._apply_source_checks(result)
            self.statusBar().showMessage(
                f"Source check complete: {len(self._source_issues)} source issue(s). "
                "Unimported files still need import."
            )
        else:
            project = result.project
            if mode == "load":
                self.analysis_plan = project.analysis_plan
                self.selected_files = {s.path for s in project.sources}
                self.phase_assignments = {s.path: s.phase for s in project.sources if s.phase}
                self.metadata_assignments = {
                    s.path: s.analysis_metadata
                    for s in project.sources
                    if s.analysis_metadata.is_assigned
                }
                self.import_results.clear()
                self._source_issues.clear()
                self.overview.set_files((), {})
                self.overview.clear_filters()
                self.phase_overview.clear_filters()
                self.issue_list.clear()
                self.extensions.setText(", ".join(project.extensions))
                self.recursive.setChecked(project.recursive)
                self.export_status.setText(
                    "Project restored. Import Med-PC to calculate and review results."
                )
            self._source_hashes = {s.path: s.sha256 for s in project.sources}
            self._project_path, self._project_sha256 = result.path, result.file_sha256
            self._apply_source_checks(result.checks)
            self._project_dirty = project.configuration_updated
            self._update_project_label()
            self.statusBar().showMessage(
                f"{project.configuration_update_message} "
                "Re-import required; save to update the project."
                if project.configuration_updated
                else "Project loaded; import required before export."
                if mode == "load"
                else "Project saved. Changed sources still require re-import."
            )
        self._set_busy(False)
        self._finish_close()

    @Slot(str)
    def _project_failed(self, message: str) -> None:
        self._project_worker = None
        self.progress.hide()
        self._set_busy(False)
        self.statusBar().showMessage(message)
        if not self._closing:
            QMessageBox.warning(self, "Project operation failed", message)
        self._finish_close()
