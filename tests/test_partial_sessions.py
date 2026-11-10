"""Synthetic partial-session boundaries, not copied research recordings."""

import csv
import json
from dataclasses import replace

import pytest
from openpyxl import load_workbook

from trial_cruncher.exporters import export_import_results
from trial_cruncher.prl_metrics import METRIC_LABELS, calculate_prl_summary
from trial_cruncher.processing import import_medpc_file


@pytest.mark.parametrize("duration", ["75.0", "3600.1"])
@pytest.mark.parametrize("export_format", ["csv", "xlsx"])
@pytest.mark.parametrize("program", ["PRL_OPTO", "PRL_OPTO_CORSTIM"])
def test_partial_duration_uses_recorded_denominator_and_exports_snapshot(
    write_export, tmp_path, duration, export_format, program
):
    path = write_export(program=program)
    # Keep the stored target-based fraction distinct from the observed percentage.
    text = path.read_text().replace("S: 10.00", f"S: {duration}").replace("  5: 0.50", "  5: 0.07")
    path.write_text(text)
    before = path.read_bytes(), path.stat().st_mtime_ns
    result = import_medpc_file(path)
    assert result.error is None
    assert result.session.duration_s == float(duration)
    assert result.session.metadata["raw_medpc"]["scalars"]["M"] == 60
    assert all(result.session.metadata["summary_checks"].values())
    assert tuple(metric.value for metric in result.summary.metrics) == (4, 2, 2, 2, 2, 50)
    assert not result.session.warnings
    destination = export_import_results({path: result}, [path], tmp_path, export_format)
    if export_format == "xlsx":
        book = load_workbook(destination / "results.xlsx")
        headers, values = list(book["Sessions"].values)
        row = dict(zip(headers, values, strict=True))
        assert book["Choices"].max_row == 5
        book.close()
    else:
        with (destination / "sessions.csv").open(newline="") as stream:
            (row,) = csv.DictReader(stream)
        with (destination / "choices.csv").open(newline="") as stream:
            assert len(list(csv.DictReader(stream))) == 4
    assert float(row["prl.percent_correct"]) == 50
    assert float(row["duration_s"]) == float(duration)
    raw = json.loads(row["metadata_json"])["raw_medpc"]
    assert row["program"] == raw["headers"]["MSN"] == program
    assert raw["source_text"] == text
    assert raw["arrays"]["A"]["5"] == "0.07"
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_unknown_program_retains_raw_array_including_zero_tail(write_export):
    path = write_export(program="PRL_UNKNOWN")
    path.write_text(path.read_text().replace("4.57", "4.57 0.00 0.00"))
    result = import_medpc_file(path)
    assert "Unsupported PRL program 'PRL_UNKNOWN'" in result.error
    assert result.session is result.summary is None
    assert len(result.raw["arrays"]["C"]) == 6
    assert result.raw["arrays"]["C"][4] == result.raw["arrays"]["C"][5] == 0
    assert result.raw["arrays"]["A"][2] == 4
    assert result.raw["source_text"] == path.read_text()


@pytest.mark.parametrize("program", ["PRL_BO", "PRL_OPTO", "PRL_OPTO_CORSTIM"])
@pytest.mark.parametrize("export_format", ["csv", "xlsx"])
def test_corroborated_zero_tail_preserves_raw_and_exports_exclusions(
    write_export, tmp_path, program, export_format
):
    path = write_export(program=program)
    path.write_text(path.read_text().replace("4.57", "4.57 0.00 0.00"))
    before = path.read_bytes(), path.stat().st_mtime_ns
    result = import_medpc_file(path)
    assert result.error is None
    assert result.summary.diagnostics.raw_c_entry_count == 6
    assert result.summary.diagnostics.unused_slot_count == 2
    assert result.summary.diagnostics.observed_record_count == 4
    assert result.summary.diagnostics.decoded_choice_count == 4
    assert result.summary.diagnostics.invalid_record_count == 0
    assert len(result.session.events) == 4
    assert len(result.raw["arrays"]["C"]) == 6
    assert result.session.metadata["choice_storage"] == {
        "policy": "validated-zero-tail-v1",
        "raw_c_entry_count": 6,
        "unused_slot_count": 2,
        "unused_slot_indices": (4, 5),
    }
    assert all(result.session.metadata["summary_checks"].values())
    assert [metric.name for metric in result.summary.metrics] == list(METRIC_LABELS)
    assert tuple(m.value for m in result.summary.metrics) == (4, 2, 2, 2, 2, 50)
    assert not result.session.warnings
    destination = export_import_results({path: result}, [path], tmp_path, export_format)
    if export_format == "csv":
        with (destination / "sessions.csv").open(newline="") as stream:
            (row,) = csv.DictReader(stream)
        with (destination / "choices.csv").open(newline="") as stream:
            assert len(list(csv.DictReader(stream))) == 4
    else:
        book = load_workbook(destination / "results.xlsx")
        headers, values = book["Sessions"].values
        row = dict(zip(headers, values, strict=True))
        assert book["Choices"].max_row == 5
        book.close()
    metadata = json.loads(row["metadata_json"])
    raw = metadata["raw_medpc"]
    assert raw["source_text"] == before[0].decode()
    assert raw["arrays"]["C"]["4"] == raw["arrays"]["C"]["5"] == "0.00"
    assert "C[4]" in raw["line_numbers"] and "C[5]" in raw["line_numbers"]
    assert metadata["choice_storage"]["unused_slot_indices"] == [4, 5]
    assert json.loads(row["metric_diagnostics_json"])["unused_slot_count"] == 2
    assert row["normalizer_version"] == row["metric_definition_version"] == "2"
    assert (
        json.loads((destination / "manifest.json").read_text())["configuration"][
            "choice_storage_policy"
        ]
        == "validated-zero-tail-v1"
    )
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize(
    "problem",
    [
        "missing_a",
        "missing_b",
        "missing_counter",
        "fractional_count",
        "negative_count",
        "too_large_count",
        "incorrect_count",
        "correct_mismatch",
        "reward_mismatch",
        "invalid_prefix",
        "internal_zero",
        "nonzero_tail",
        "gap",
        "terminator",
    ],
)
def test_ambiguous_or_conflicting_tails_are_never_trimmed(write_export, problem):
    path = write_export()
    text = path.read_text().replace("4.57", "4.57 0.00 0.00")
    changes = {
        "missing_a": ("A:\n  0: 2.00 2.00 4.00 24.00 0.00\n  5: 0.50\n", ""),
        "missing_b": ("B:\n  0: 1.00 1.00 1.00 1.00\n", ""),
        "missing_counter": ("B:\n  0: 1.00 1.00 1.00 1.00", "B:\n  0: 1.00 1.00 1.00"),
        "fractional_count": ("2.00 2.00 4.00", "2.00 2.00 4.50"),
        "negative_count": ("2.00 2.00 4.00", "2.00 2.00 -1.00"),
        "too_large_count": ("2.00 2.00 4.00", "2.00 2.00 99999999999999999999999"),
        "incorrect_count": ("2.00 2.00 4.00", "2.00 2.00 3.00"),
        "correct_mismatch": ("2.00 2.00 4.00", "3.00 2.00 4.00"),
        "reward_mismatch": ("B:\n  0: 1.00", "B:\n  0: 2.00"),
        "invalid_prefix": ("1.22", "1.23"),
        "internal_zero": ("1.22", "0.00"),
        "nonzero_tail": ("4.57 0.00 0.00", "4.57 0.00 5.01"),
        "gap": ("C:\n  0:", "C:\n  1:"),
        "terminator": ("4.57 0.00 0.00", "4.57 -987.987 0.00"),
    }
    old, new = changes[problem]
    assert old in text
    path.write_text(text.replace(old, new))
    result = import_medpc_file(path)
    assert result.error is None
    assert result.session.metadata["choice_storage"]["unused_slot_count"] == 0
    assert result.session.metadata["choice_storage"]["unused_slot_indices"] == ()
    assert len(result.raw["arrays"]["C"]) == 6
    assert all(metric.value is None for metric in result.summary.metrics)
    assert result.session.warnings


def test_all_zero_storage_with_zero_counters_is_empty_not_missing(write_export):
    path = write_export(
        "File: synthetic\nMSN: PRL_OPTO\nSubject: 0007\nS: 1\n"
        "A:\n  0: 0 0 0\nB:\n  0: 0 0 0 0\nC:\n  0: 0 0 0\n"
    )
    result = import_medpc_file(path)
    assert result.error is None
    assert not result.session.events
    assert [m.value for m in result.summary.metrics] == [0, 0, 0, 0, 0, None]
    assert result.summary.diagnostics.raw_c_entry_count == 3
    assert result.summary.diagnostics.unused_slot_count == 3
    assert result.summary.diagnostics.observed_record_count == 0
    assert not result.session.warnings


def test_stale_or_forged_exclusions_fail_closed(write_export):
    path = write_export()
    path.write_text(path.read_text().replace("4.57", "4.57 0.00 0.00"))
    result = import_medpc_file(path)
    session = result.session
    with pytest.raises(ValueError, match="storage metadata"):
        calculate_prl_summary(replace(session, metadata={**session.metadata, "choice_storage": {}}))
    with pytest.raises(ValueError, match="do not match"):
        calculate_prl_summary(replace(session, events=session.events[:-1]))
    with pytest.raises(ValueError, match="re-import"):
        calculate_prl_summary(
            replace(session, metadata={**session.metadata, "normalizer_version": "1"})
        )


@pytest.mark.parametrize("export_format", ["csv", "xlsx"])
@pytest.mark.parametrize("stale", ["normalizer", "definition", "policy", "metric"])
def test_exports_refuse_stale_interpretations(write_export, tmp_path, export_format, stale):
    path = write_export()
    result = import_medpc_file(path)
    if stale == "normalizer":
        result = replace(
            result,
            session=replace(
                result.session,
                metadata={
                    **result.session.metadata,
                    "normalizer_version": "1",
                },
            ),
        )
    elif stale == "definition":
        result = replace(result, summary=replace(result.summary, definition_version="1"))
    elif stale == "policy":
        result = replace(
            result, summary=replace(result.summary, eligibility_policy="strict-withholding-v1")
        )
    else:
        result = replace(
            result,
            summary=replace(
                result.summary,
                metrics=(
                    replace(result.summary.metrics[0], definition_version="1"),
                    *result.summary.metrics[1:],
                ),
            ),
        )
    with pytest.raises(ValueError, match="re-import"):
        export_import_results({path: result}, [path], tmp_path, export_format)
    assert not list(tmp_path.glob("trial-cruncher-export-*"))
