"""Task-specific metric interface; approved PRL summaries live in prl_metrics.py."""

from typing import Protocol

from trial_cruncher.models import MetricResult, Session
from trial_cruncher.paradigms import ParadigmConfig


class Metric(Protocol):
    def calculate(self, session: Session, config: ParadigmConfig) -> MetricResult:
        """Use an explicitly documented definition and report missing requirements."""
        ...
