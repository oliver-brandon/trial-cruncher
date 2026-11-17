"""Single-file import results, independent of the desktop interface."""

import logging
from dataclasses import dataclass
from pathlib import Path

from trial_cruncher import phase_metrics, prl_metrics
from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.medpc import MedPCData, MedPCReader
from trial_cruncher.models import Session
from trial_cruncher.phase_metrics import PhaseSummary, calculate_phase_metrics
from trial_cruncher.prl import NORMALIZER_VERSION, PRLNormalizer
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
    analysis_metadata: AnalysisMetadata = AnalysisMetadata()


def import_medpc_file(
    path: Path, phase: str | None = None, analysis_metadata: AnalysisMetadata | None = None
) -> ImportResult:
    """Retain raw extraction even when the program cannot be normalized."""
    annotation = AnalysisMetadata() if analysis_metadata is None else analysis_metadata
    if not isinstance(annotation, AnalysisMetadata):
        raise ValueError("Analysis metadata must be an AnalysisMetadata record.")
    raw = None
    try:
        raw = MedPCReader().read(path)
        (session,) = PRLNormalizer().normalize(raw, path)
        summary = calculate_prl_summary(session)
        phase_summary = calculate_phase_metrics(session, phase)
    except (ValueError, OSError) as exc:
        logger.warning(str(exc), extra={"path": path, "operation": "import_medpc"})
        return ImportResult(path, raw=raw, error=str(exc), analysis_metadata=annotation)
    return ImportResult(
        path,
        raw=raw,
        session=session,
        summary=summary,
        phase_summary=phase_summary,
        analysis_metadata=annotation,
    )


def validate_reviewed_result(result: ImportResult) -> None:
    """Require current session and phase interpretations for derived outputs."""
    session = result.session
    if session is None:
        raise ValueError("Session missing; re-import before analysis or export.")
    if result.summary is None:
        raise ValueError("Session metrics are missing; re-import before analysis or export.")
    if (
        session.metadata.get("normalizer_version") != NORMALIZER_VERSION
        or result.summary.definition_set != prl_metrics.DEFINITION_SET
        or result.summary.definition_version != prl_metrics.DEFINITION_VERSION
        or result.summary.eligibility_policy != prl_metrics.ELIGIBILITY_POLICY
        or tuple(m.name for m in result.summary.metrics) != tuple(prl_metrics.METRIC_LABELS)
        or any(
            m.definition_version != prl_metrics.DEFINITION_VERSION for m in result.summary.metrics
        )
    ):
        raise ValueError(
            "Session interpretation versions have changed; re-import before analysis or export."
        )
    phase = result.phase_summary
    if phase is None:
        raise ValueError("Phase results are missing; re-import before analysis or export.")
    if (
        phase.definition_set != phase_metrics.DEFINITION_SET
        or phase.definition_version != phase_metrics.DEFINITION_VERSION
        or phase.eligibility_policy != phase_metrics.POLICY
        or phase.config != phase_metrics.phase_config(phase.config.phase)
        or phase.source_file != session.source_file
        or phase.source_sha256 != session.metadata.get("raw_medpc", {}).get("source_sha256")
        or tuple(m.name for m in phase.metrics) != tuple(phase_metrics.METRIC_LABELS)
        or any(m.definition_version != phase.definition_version for m in phase.metrics)
    ):
        raise ValueError("Phase interpretation has changed; re-import before analysis or export.")
