"""Project IO and source hashing outside the widget thread."""

import logging
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from trial_cruncher.projects import load_project, save_project
from trial_cruncher.source_tracking import check_sources

logger = logging.getLogger(__name__)


class ProjectSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class ProjectWorker(QRunnable):
    def __init__(
        self,
        mode: Literal["load", "save", "check"],
        path: Path | None = None,
        *,
        paths: tuple[Path, ...] = (),
        phases: dict[Path, str] | None = None,
        hashes: dict[Path, str | None] | None = None,
        extensions: tuple[str, ...] = (),
        recursive: bool = False,
        expected_project_sha256: str | None = None,
    ) -> None:
        super().__init__()
        self.mode, self.path, self.paths = mode, path, paths
        self.phases, self.hashes = dict(phases or {}), dict(hashes or {})
        self.extensions, self.recursive = extensions, recursive
        self.expected_project_sha256 = expected_project_sha256
        self.signals = ProjectSignals()

    @Slot()
    def run(self) -> None:
        try:
            if self.mode == "load":
                result = load_project(self.path)
            elif self.mode == "save":
                result = save_project(
                    self.path,
                    self.paths,
                    self.phases,
                    self.hashes,
                    extensions=self.extensions,
                    recursive=self.recursive,
                    expected_project_sha256=self.expected_project_sha256,
                )
            else:
                result = check_sources(self.hashes)
        except Exception as exc:
            logger.exception("Project %s failed", self.mode)
            self.signals.failed.emit(f"Project {self.mode} failed: {exc}")
        else:
            self.signals.finished.emit(result)
