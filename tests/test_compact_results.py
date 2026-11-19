"""Synthetic regression checks for the concise per-recording result."""

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.compact_results import DATA_COLUMNS, data_reasons, data_values
from trial_cruncher.processing import import_medpc_file


def test_compact_result_uses_reviewed_values_and_phase(phase_input):
    path = phase_input((1, 1, 1, 7))
    result = import_medpc_file(path, "Reversal", AnalysisMetadata(condition="Vehicle"))
    row = dict(zip(DATA_COLUMNS, data_values(result), strict=True))
    assert row["ID"] == "0007"
    assert row["Treatment"] == "Vehicle"
    assert row["Phase"] == "Reversal"
    assert row["Proportion correct"] == 0.75
    assert row["Trials to criterion"] == 3
    assert row["Regressive errors"] == 1
    assert "Trials to criterion" not in data_reasons(result)


def test_missing_phase_withholding_and_real_zero(phase_input):
    path = phase_input((7, 7))
    result = import_medpc_file(path)
    row = dict(zip(DATA_COLUMNS, data_values(result), strict=True))
    assert row["Proportion correct"] == 0
    assert row["Regressive errors"] is None
    assert "phase" in data_reasons(result)["Regressive errors"].lower()
    result = import_medpc_file(path, "Reversal")
    assert "not reached" in data_reasons(result)["Trials to criterion"]
    path.write_text(path.read_text().replace("0: 0 2 2", "0: 0 2 3"))
    result = import_medpc_file(path, "Reversal")
    assert dict(zip(DATA_COLUMNS, data_values(result), strict=True))["Proportion correct"] is None
    assert data_reasons(result)["Proportion correct"]
