"""Read-only candidate discovery. Extensions do not establish a file's schema."""

import logging
import os
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
DEFAULT_EXTENSIONS = (".mat", ".txt", ".med", ".mpc")


@dataclass(frozen=True)
class DiscoveryIssue:
    path: Path
    message: str


@dataclass(frozen=True)
class DiscoveryResult:
    files: tuple[Path, ...]
    issues: tuple[DiscoveryIssue, ...]


def normalize_extensions(extensions: Iterable[str]) -> frozenset[str]:
    normalized = frozenset(f".{item.strip().lstrip('.').lower()}" for item in extensions)
    if not normalized or any(
        item == "." or any(char in item for char in "/\\*?[] ") for item in normalized
    ):
        raise ValueError("Enter at least one file extension, such as .mat or .txt.")
    return normalized


def discover_files(
    inputs: Iterable[str | Path],
    *,
    extensions: Iterable[str] = DEFAULT_EXTENSIONS,
    recursive: bool = True,
) -> DiscoveryResult:
    """Find sorted, unique absolute paths; report inaccessible or invalid selections.

    Nested directory symlinks are skipped and reported to avoid cycles and leaving
    the selected tree. Explicitly selected symlinks are resolved. Unmatched files
    inside folders are filtered; unmatched explicitly selected files are reported.
    """
    suffixes = normalize_extensions(extensions)
    files: set[Path] = set()
    visited: set[Path] = set()
    issues: list[DiscoveryIssue] = []

    def report(path: Path, message: str) -> None:
        issues.append(DiscoveryIssue(path, message))
        logger.warning(message, extra={"path": path, "operation": "discover"})

    pending = [(Path(item).expanduser(), True) for item in inputs]
    while pending:
        path, explicit = pending.pop()
        try:
            if not explicit and path.is_symlink() and path.is_dir():
                report(path, "Skipped a linked folder; select it explicitly to include it.")
                continue
            resolved = path.resolve(strict=True)
            mode = resolved.stat().st_mode
            if stat.S_ISREG(mode):
                if resolved.suffix.lower() in suffixes:
                    files.add(resolved)
                elif explicit:
                    report(path, "File does not match the configured extensions.")
            elif stat.S_ISDIR(mode):
                if resolved in visited or (not explicit and not recursive):
                    continue
                visited.add(resolved)
                # Directory entries can identify ordinary files without resolving
                # and stat-ing every unrelated recording, backup or exported table.
                with os.scandir(resolved) as children:
                    for entry in children:
                        child = Path(entry.path)
                        try:
                            if (
                                entry.is_file(follow_symlinks=False)
                                and child.suffix.lower() not in suffixes
                            ):
                                continue
                        except OSError as exc:
                            report(child, f"Could not access this selection: {exc}")
                            continue
                        pending.append((child, False))
            else:
                report(path, "Selection is not a regular file or folder.")
        except (OSError, RuntimeError) as exc:
            report(path, f"Could not access this selection: {exc}")

    result = DiscoveryResult(
        tuple(sorted(files, key=str)), tuple(sorted(issues, key=lambda issue: str(issue.path)))
    )
    logger.info("Discovered %d candidate files", len(result.files), extra={"operation": "discover"})
    return result
