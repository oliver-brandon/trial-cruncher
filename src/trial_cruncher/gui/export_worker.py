"""Export the imported snapshot without blocking the GUI thread."""

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from trial_cruncher.exporters import export_import_results
from trial_cruncher.processing import ImportResult

logger = logging.getLogger(__name__)


class ExportSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class ExportWorker(QRunnable):
    def __init__(
        self, results: dict[Path, ImportResult], paths: tuple[Path, ...], parent: Path
    ) -> None:
        super().__init__()
        self.results = dict(results)
        self.paths = paths
        self.parent = parent
        self.signals = ExportSignals()

    @Slot()
    def run(self) -> None:
        try:
            destination = export_import_results(self.results, self.paths, self.parent)
        except Exception as exc:
            logger.exception("CSV export failed", extra={"operation": "export_csv"})
            self.signals.failed.emit(f"CSV export failed: {exc}")
        else:
            self.signals.finished.emit(destination)
