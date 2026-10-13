"""Explicit task selection/configuration; automatic task identification is future work."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParadigmConfig:
    name: str
    version: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
