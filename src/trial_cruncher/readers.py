"""Format-specific extraction contract; see medpc.py for the first implementation."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol


class Reader(Protocol):
    def can_read(self, path: Path) -> bool:
        """Inspect enough content to identify the format; extensions are only hints."""
        ...

    def read(self, path: Path) -> Mapping[str, Any]:
        """Extract source variables without modifying the file or calculating metrics."""
        ...
