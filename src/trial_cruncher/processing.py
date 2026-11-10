"""Single-file import results, independent of the desktop interface."""

import logging
from dataclasses import dataclass
from pathlib import Path

from trial_cruncher.medpc import MedPCData, MedPCReader
from trial_cruncher.models import Session
from trial_cruncher.phase_metrics import PhaseSummary, calculate_phase_metrics
from trial_cruncher.prl import PRLNormalizer
from trial_cruncher.prl_metrics import PRLSessionSummary, calculate_prl_summary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportResult:
    source_file: Path
    raw: MedPCData | None = None
    session: Session | None = None
    error: str | None = None
    summary: PRLSessionSummary | None = None
    phase_summary: PhaseSummary | None = None


def import_medpc_file(path: Path, phase: str | None = None) -> ImportResult:
    """Retain raw extraction even when the program cannot be normalized."""
    raw = None
    try:
        raw = MedPCReader().read(path)
        (session,) = PRLNormalizer().normalize(raw, path)
        summary = calculate_prl_summary(session)
        phase_summary = calculate_phase_metrics(session, phase)
    except (ValueError, OSError) as exc:
        logger.warning(str(exc), extra={"path": path, "operation": "import_medpc"})
        return ImportResult(path, raw=raw, error=str(exc))
    return ImportResult(
        path, raw=raw, session=session, summary=summary, phase_summary=phase_summary
    )
