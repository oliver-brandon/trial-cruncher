"""Export contract only; table generation and CSV/Excel writers are future work."""

from pathlib import Path
from typing import Protocol

import pandas as pd


class Exporter(Protocol):
    def export(self, table: pd.DataFrame, destination: Path) -> Path:
        """Write a provenance-bearing table; refuse source paths and existing files."""
        ...
