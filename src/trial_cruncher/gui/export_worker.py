"""Export the imported snapshot without blocking the GUI thread."""

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.analysis_plan import AnalysisPlan
from trial_cruncher.exporters import ExportFormat, ExportProfile, export_import_results
from trial_cruncher.processing import ImportResult
from trial_cruncher.source_tracking import SourcesChangedError

logger = logging.getLogger(__name__)


class ExportSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    sources_changed = Signal(object)


class ExportWorker(QRunnable):
    def __init__(
        self,
        results: dict[Path, ImportResult],
        paths: tuple[Path, ...],
        parent: Path,
        export_format: ExportFormat = "csv",
        metadata: dict[Path, AnalysisMetadata] | None = None,
        analysis_plan: AnalysisPlan | None = None,
        profile: ExportProfile = "detailed",
        folder_name: str | None = None,
    ) -> None:
        super().__init__()
        self.results = dict(results)
        self.paths = paths
        self.parent = parent
        self.export_format = export_format
        self.profile = profile
        self.folder_name = folder_name
        self.analysis_plan = analysis_plan
        self.metadata = dict(metadata or {})
        self.signals = ExportSignals()

    @Slot()
    def run(self) -> None:
        try:
            destination = export_import_results(
                self.results,
                self.paths,
                self.parent,
                self.export_format,
                profile=self.profile,
                folder_name=self.folder_name,
                assignments=self.metadata,
                analysis_plan=self.analysis_plan,
            )
        except Exception as exc:
            if isinstance(exc, SourcesChangedError):
                self.signals.sources_changed.emit(exc.checks)
            label = "Excel" if self.export_format == "xlsx" else "CSV"
            logger.exception("%s export failed", label, extra={"operation": "export"})
            self.signals.failed.emit(f"{label} export failed: {exc}")
        else:
            self.signals.finished.emit(destination)
