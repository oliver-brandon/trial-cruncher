"""Initial canonical records; unavailable observations stay None, never invented zeroes."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Event:
    name: str
    timestamp_s: float | None
    raw_values: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Trial:
    trial_id: str
    raw_values: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Session:
    """One source session; events and trials may both be absent or incomplete.

    timestamp_s uses a documented session-relative origin, specified in metadata
    by the normalizer. Trial boundaries are task-specific, never inferred here.
    Frozen records are shallow: callers must not mutate the supplied mappings.
    """

    source_file: Path
    subject_id: str | None = None
    session_id: str | None = None
    events: tuple[Event, ...] = ()
    trials: tuple[Trial, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetricResult:
    """Calculated values remain separate from raw observations."""

    name: str
    definition_version: str
    value: float | None
    unit: str
    warnings: tuple[str, ...] = ()
