"""Content fingerprints and explicit stale-source checks, independent of Qt."""

import hashlib
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceCheck:
    path: Path
    expected_sha256: str | None
    current_sha256: str | None
    status: str
    message: str


def source_sha256(path: Path) -> str:
    """Hash a regular file; reject files changed/replaced during the read."""
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise OSError("Source is not a regular file.")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("Source is not a regular file.")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        finished = os.fstat(stream.fileno())
    after = path.stat()

    def identity(info: os.stat_result) -> tuple[int, ...]:
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

    if len({identity(s) for s in (before, opened, finished, after)}) != 1:
        raise OSError("Source changed while it was being checked; retry after writing finishes.")
    return digest.hexdigest()


def check_sources(expected: Mapping[Path, str | None]) -> tuple[SourceCheck, ...]:
    checks = []
    for path, baseline in sorted(expected.items(), key=lambda pair: str(pair[0])):
        try:
            current = source_sha256(path)
        except FileNotFoundError:
            checks.append(
                SourceCheck(
                    path, baseline, None, "missing", "Source missing; restore it and re-import."
                )
            )
        except OSError as exc:
            checks.append(
                SourceCheck(path, baseline, None, "unreadable", f"Cannot check source: {exc}")
            )
        else:
            status = (
                "unverified"
                if baseline is None
                else "unchanged"
                if current == baseline
                else "changed"
            )
            message = {
                "unverified": "No saved fingerprint; import required.",
                "unchanged": "Content matches the saved fingerprint.",
                "changed": "Source content changed; re-import required.",
            }[status]
            checks.append(SourceCheck(path, baseline, current, status, message))
    return tuple(checks)


class SourcesChangedError(ValueError):
    def __init__(self, checks: tuple[SourceCheck, ...]):
        self.checks = checks
        super().__init__(
            "Source verification failed; re-import before exporting:\n"
            + "\n".join(f"{c.path}: {c.message}" for c in checks)
        )


def require_current_sources(expected: Mapping[Path, str | None]) -> None:
    problems = tuple(c for c in check_sources(expected) if c.status != "unchanged")
    if problems:
        raise SourcesChangedError(problems)
