"""Export the imported snapshot without blocking the GUI thread."""

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from trial_cruncher.exporters import ExportFormat, export_import_results
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
    ) -> None:
        super().__init__()
        self.results = dict(results)
        self.paths = paths
        self.parent = parent
        self.export_format = export_format
        self.signals = ExportSignals()

    @Slot()
    def run(self) -> None:
        try:
            destination = export_import_results(
                self.results, self.paths, self.parent, self.export_format
            )
        except Exception as exc:
            if isinstance(exc, SourcesChangedError):
                self.signals.sources_changed.emit(exc.checks)
            label = "Excel" if self.export_format == "xlsx" else "CSV"
            logger.exception("%s export failed", label, extra={"operation": "export"})
            self.signals.failed.emit(f"{label} export failed: {exc}")
        else:
            self.signals.finished.emit(destination)
