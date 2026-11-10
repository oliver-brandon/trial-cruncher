"""Versioned project setup, strict validation, and atomic local saves."""

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from trial_cruncher import __version__, phase_metrics, prl_metrics
from trial_cruncher.discovery import normalize_extensions
from trial_cruncher.prl import CHOICE_STORAGE_POLICY, NORMALIZER_VERSION
from trial_cruncher.source_tracking import SourceCheck, check_sources, source_sha256

PROJECT_FORMAT = "trial-cruncher-project"
PROJECT_VERSION = "1"
PROJECT_SUFFIX = ".tcproj.json"
MAX_PROJECT_BYTES = 16 * 1024 * 1024
_HASH = re.compile(r"[0-9a-f]{64}")


def analysis_configuration() -> dict[str, Any]:
    """Explicit fixed policies; these are restored by compatibility, not guessed."""
    return {
        "reader_version": "1",
        "normalizer_version": NORMALIZER_VERSION,
        "choice_storage_policy": CHOICE_STORAGE_POLICY,
        "session_definition_set": prl_metrics.DEFINITION_SET,
        "session_definition_version": prl_metrics.DEFINITION_VERSION,
        "session_policy": prl_metrics.ELIGIBILITY_POLICY,
        "phase_definition_set": phase_metrics.DEFINITION_SET,
        "phase_definition_version": phase_metrics.DEFINITION_VERSION,
        "phase_policy": phase_metrics.POLICY,
        "phase_profile": {
            k: v
            for k, v in asdict(phase_metrics.phase_config(None)).items()
            if k not in ("phase", "assignment_source")
        },
    }


@dataclass(frozen=True)
class ProjectSource:
    path: Path
    phase: str | None
    sha256: str | None


@dataclass(frozen=True)
class Project:
    sources: tuple[ProjectSource, ...]
    extensions: tuple[str, ...]
    recursive: bool


@dataclass(frozen=True)
class ProjectResult:
    project: Project
    path: Path
    file_sha256: str
    checks: tuple[SourceCheck, ...]


def _keys(value: Any, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"Invalid {label} fields.")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate project field: {key}")
        result[key] = value
    return result


def _parse(payload: bytes, project_path: Path) -> Project:
    if len(payload) > MAX_PROJECT_BYTES:
        raise ValueError("Project exceeds the 16 MiB size limit.")
    try:
        obj = json.loads(payload.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Project is not valid UTF-8 JSON.") from exc
    _keys(
        obj,
        {
            "format",
            "schema_version",
            "application_version",
            "saved_at_utc",
            "analysis_configuration",
            "discovery",
            "sources",
        },
        "project",
    )
    if obj["format"] != PROJECT_FORMAT or obj["schema_version"] != PROJECT_VERSION:
        raise ValueError("Unsupported project format or version.")
    if obj["analysis_configuration"] != analysis_configuration():
        raise ValueError(
            "Project analysis configuration is incompatible with this version. "
            "No settings were applied; use a compatible application "
            "or an explicitly reviewed migration."
        )
    if not isinstance(obj["application_version"], str) or not isinstance(obj["saved_at_utc"], str):
        raise ValueError("Project version and save time must be text.")
    try:
        if datetime.fromisoformat(obj["saved_at_utc"]).tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise ValueError("Project save time must include a time zone.") from exc
    discovery = obj["discovery"]
    _keys(discovery, {"extensions", "recursive"}, "discovery")
    if (
        not isinstance(discovery["extensions"], list)
        or not all(isinstance(v, str) for v in discovery["extensions"])
        or type(discovery["recursive"]) is not bool
    ):
        raise ValueError("Invalid project discovery settings.")
    extensions = tuple(sorted(normalize_extensions(discovery["extensions"])))
    if not isinstance(obj["sources"], list):
        raise ValueError("Project sources must be a list.")
    sources, seen = [], set()
    for item in obj["sources"]:
        _keys(item, {"path", "phase", "sha256"}, "source")
        if not isinstance(item["path"], str) or "\x00" in item["path"]:
            raise ValueError("Invalid source path.")
        path = Path(item["path"])
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("Project source paths must be absolute, without parent traversal.")
        if path in seen:
            raise ValueError("Duplicate source paths are not allowed.")
        if path.resolve() == project_path.resolve():
            raise ValueError("A project cannot use itself as a source recording.")
        seen.add(path)
        phase = phase_metrics.phase_config(item["phase"]).phase
        if phase != item["phase"]:
            raise ValueError("Project phase labels must be normalized text or null.")
        digest = item["sha256"]
        if digest is not None and (not isinstance(digest, str) or not _HASH.fullmatch(digest)):
            raise ValueError("Source SHA-256 must be 64 lowercase hex digits or null.")
        sources.append(ProjectSource(path, phase, digest))
    return Project(tuple(sources), extensions, discovery["recursive"])


def load_project(path: Path) -> ProjectResult:
    path = path.absolute()
    if not path.is_file() or path.stat().st_size > MAX_PROJECT_BYTES:
        raise ValueError("Project must be a regular file of at most 16 MiB.")
    with path.open("rb") as stream:
        payload = stream.read(MAX_PROJECT_BYTES + 1)
    project = _parse(payload, path)
    checks = check_sources({s.path: s.sha256 for s in project.sources})
    return ProjectResult(project, path, hashlib.sha256(payload).hexdigest(), checks)


def _protect_sources(destination: Path, sources: Sequence[ProjectSource]) -> None:
    for source in sources:
        if destination.resolve() == source.path.resolve():
            raise ValueError("A project cannot overwrite a source recording.")
        if destination.exists() and source.path.exists() and destination.samefile(source.path):
            raise ValueError("A project cannot replace an alias of a source recording.")


def save_project(
    path: Path,
    paths: Sequence[Path],
    phases: Mapping[Path, str],
    baseline_hashes: Mapping[Path, str | None],
    *,
    extensions: Sequence[str],
    recursive: bool,
    expected_project_sha256: str | None = None,
) -> ProjectResult:
    """Save setup only. Existing baselines never advance merely because of a save.

    Creation is exclusive. Replacement requires the previously loaded/saved project
    hash and refuses external edits. Atomic publication never truncates the old file.
    """
    path = path.absolute()
    if not path.name.endswith(PROJECT_SUFFIX):
        raise ValueError(f"Use the {PROJECT_SUFFIX} extension for projects.")
    if path.is_symlink():
        raise ValueError("Saving over a symbolic link is not supported.")
    sources = tuple(
        ProjectSource(
            p.absolute(), phase_metrics.phase_config(phases.get(p)).phase, baseline_hashes.get(p)
        )
        for p in sorted(set(paths), key=str)
    )
    _protect_sources(path, sources)
    checks = check_sources({s.path: s.sha256 for s in sources})
    observed = {c.path: c.current_sha256 for c in checks}
    sources = tuple(ProjectSource(s.path, s.phase, s.sha256 or observed[s.path]) for s in sources)
    checks = tuple(
        SourceCheck(
            c.path,
            c.current_sha256,
            c.current_sha256,
            "unchanged",
            "Fingerprint recorded; import required before export.",
        )
        if c.status == "unverified" and c.current_sha256 is not None
        else c
        for c in checks
    )
    payload = (
        json.dumps(
            {
                "format": PROJECT_FORMAT,
                "schema_version": PROJECT_VERSION,
                "application_version": __version__,
                "saved_at_utc": datetime.now(UTC).isoformat(),
                "analysis_configuration": analysis_configuration(),
                "discovery": {
                    "extensions": sorted(normalize_extensions(extensions)),
                    "recursive": recursive,
                },
                "sources": [
                    {"path": str(s.path), "phase": s.phase, "sha256": s.sha256} for s in sources
                ],
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    project = _parse(payload, path)

    def check_destination() -> None:
        _protect_sources(path, sources)
        if path.is_symlink():
            raise ValueError("Saving over a symbolic link is not supported.")
        if expected_project_sha256 is None:
            if path.exists():
                raise FileExistsError(
                    "Destination exists. Use Save for the open project, or a new filename."
                )
        else:
            if source_sha256(path) != expected_project_sha256:
                raise ValueError(
                    "Project changed outside this window; reopen it or Save As a new file."
                )
            if path.stat().st_size > MAX_PROJECT_BYTES:
                raise ValueError("Existing project exceeds the size limit.")
            _parse(path.read_bytes(), path)

    lock = path.with_name(f".{path.name}.lock")
    lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(lock_fd)
    temp = None
    try:
        check_destination()
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temp = Path(temp_name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        check_destination()
        if expected_project_sha256 is None:
            os.link(temp, path)  # Atomic and exclusive, including concurrent creators.
        else:
            os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
        lock.unlink()
    return ProjectResult(project, path, hashlib.sha256(payload).hexdigest(), checks)
