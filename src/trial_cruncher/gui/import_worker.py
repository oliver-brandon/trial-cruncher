"""Background imports with per-file results and cooperative cancellation."""

import logging
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from trial_cruncher.processing import ImportResult, import_medpc_file

logger = logging.getLogger(__name__)


class ImportSignals(QObject):
    result = Signal(object)
    progress = Signal(int, int)
    finished = Signal(bool)


class ImportWorker(QRunnable):
    def __init__(self, paths: tuple[Path, ...], phases: dict[Path, str] | None = None) -> None:
        super().__init__()
        self.paths = paths
        self.phases = dict(phases or {})
        self.signals = ImportSignals()
        self._cancel = Event()

    def cancel(self) -> None:
        self._cancel.set()

    @Slot()
    def run(self) -> None:
        completed = 0
        try:
            for path in self.paths:
                if self._cancel.is_set():
                    break
                try:
                    phase = self.phases.get(path)
                    result = (
                        import_medpc_file(path, phase)
                        if phase is not None
                        else import_medpc_file(path)
                    )
                except Exception:
                    logger.exception("Unexpected import failure", extra={"path": path})
                    result = ImportResult(
                        path,
                        error="Unexpected import failure. See the application log for details.",
                    )
                self.signals.result.emit(result)
                completed += 1
                self.signals.progress.emit(completed, len(self.paths))
        finally:
            self.signals.finished.emit(completed < len(self.paths))
