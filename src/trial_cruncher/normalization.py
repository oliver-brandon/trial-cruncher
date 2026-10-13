"""Boundary between reader-specific raw variables and canonical sessions."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from trial_cruncher.models import Session


class Normalizer(Protocol):
    def normalize(self, raw: Mapping[str, Any], source_file: Path) -> Sequence[Session]:
        """Preserve identifiers, source provenance, units, and incomplete observations."""
        ...
