"""Compact CSV export preserves reviewed values, identity and stale-source checks."""

import csv
import json

import pytest

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.exporters import export_import_results
from trial_cruncher.processing import import_medpc_file
from trial_cruncher.source_tracking import SourcesChangedError


def test_compact_csv_values_metadata_and_changed_source(tmp_path, phase_input):
    source = phase_input((1, 7, 1), name="session.txt")
    annotation = AnalysisMetadata("Vehicle", "Cohort", included=False, inclusion_reason="Retest")
    result = import_medpc_file(source, "Reversal", annotation)
    parent = tmp_path / "exports"
    parent.mkdir()
    output = export_import_results({source: result}, [source], parent, profile="compact")
    with (output / "data.csv").open(newline="") as stream:
        (row,) = csv.DictReader(stream)
    assert row["Treatment"] == "Vehicle"
    assert float(row["Proportion correct"]) == pytest.approx(2 / 3)
    assert row["Trials to criterion"] == ""
    with (output / "trials.csv").open(newline="") as stream:
        trials = list(csv.DictReader(stream))
    assert [(r["Trial"], r["Choice"], r["Outcome"]) for r in trials] == [
        ("1", "1", "1"),
        ("2", "0", "0"),
        ("3", "1", "1"),
    ]
    with (output / "metadata.csv").open(newline="") as stream:
        (metadata,) = csv.DictReader(stream)
    assert metadata["Inclusion"] == "Excluded"
    assert metadata["Inclusion reason"] == "Retest"
    assert "Trials to criterion:" in metadata["Metric unavailability"]
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["profile"] == "compact"
    source.write_text(source.read_text() + "\n")
    with pytest.raises(SourcesChangedError):
        export_import_results({source: result}, [source], parent, profile="compact")
    assert len(list(parent.iterdir())) == 1


def test_metadata_rows_link_data_for_duplicate_subject_and_failed_file(tmp_path, phase_input):
    first = phase_input((1,), name="a.txt")
    failed = phase_input((1,), name="b.txt", program="UNKNOWN")
    second = phase_input((7,), name="c.txt")
    results = {
        path: import_medpc_file(path, "Reversal", AnalysisMetadata("A", "C", included=True))
        for path in (first, failed, second)
    }
    output = export_import_results(results, [first, failed, second], tmp_path, profile="compact")
    with (output / "data.csv").open(newline="") as stream:
        data = list(csv.DictReader(stream))
    assert [row["ID"] for row in data] == ["0007", "0007"]
    with (output / "metadata.csv").open(newline="") as stream:
        metadata = {row["Source file"]: row for row in csv.DictReader(stream)}
    assert [metadata[str(p)]["Data row"] for p in (first, failed, second)] == ["2", "", "3"]
    assert metadata[str(failed)]["Status"] == "failed"
    assert metadata[str(failed)]["Error"]
    assert "Recording details" not in metadata[str(first)]
