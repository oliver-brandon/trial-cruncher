"""Hand-checked and independent synthetic phase metric verification."""

import csv
import hashlib
import itertools
import json
from dataclasses import asdict, replace

import pytest
from openpyxl import load_workbook

from trial_cruncher.exporters import export_import_results
from trial_cruncher.phase_metrics import METRIC_LABELS, STRATEGIES, calculate_phase_metrics
from trial_cruncher.processing import import_medpc_file


def test_reference_example(phase_input):
    result = import_medpc_file(phase_input(), "Reversal 2")
    phase = result.phase_summary
    assert [m.name for m in phase.metrics] == list(METRIC_LABELS)
    assert [m.value for m in phase.metrics] == pytest.approx([0.5, 3, 2, 2 / 3, 1 / 4, 0, 0, 2 / 3])
    assert [(p.numerator, p.denominator) for p in phase.strategies] == [
        (1, 4),
        (0, 1),
        (0, 1),
        (2, 3),
    ]
    d = phase.diagnostics
    assert (d.criterion_reached, d.criterion_choice_ordinal, d.criterion_source_index) == (
        True,
        7,
        6,
    )
    assert (d.postcriterion_choice_count, d.eligible_pair_count) == (3, 9)
    assert (d.adjusted_regressive.numerator, d.adjusted_regressive.denominator) == (2, 3)
    assert phase.choice_error_classes == (
        "perseverative",
        "perseverative",
        "correct",
        "perseverative",
        "correct",
        "correct",
        "correct",
        "regressive",
        "correct",
        "regressive",
    )
    assert phase.status == "available"
    assert all(m.status == "available" for m in phase.metrics)
    assert phase.config.protocol_profile == "fixed-contingency-no-omissions-v1"


@pytest.mark.parametrize(
    "codes,expected,k,post",
    [
        ((7,), [0, 1, 0, None, None, None, None, None], None, 0),
        ((1, 1, 1), [1, 0, 0, None, 1, None, None, None], 3, 0),
        ((1, 1, 1, 7, 7, 1, 1, 1), [0.75, 0, 2, 0.4, 0.8, None, None, 0.5], 3, 5),
        ((), [None] * 8, None, None),
    ],
)
def test_boundaries(phase_input, codes, expected, k, post):
    phase = import_medpc_file(phase_input(codes), "Acquisition").phase_summary
    assert [m.value for m in phase.metrics] == expected
    assert phase.diagnostics.criterion_choice_ordinal == k
    assert phase.diagnostics.postcriterion_choice_count == post
    assert phase.diagnostics.criterion_reached == ((k is not None) if codes else None)
    assert phase.diagnostics.eligible_pair_count == max(0, len(codes) - 1)
    for evidence, metric in zip(phase.strategies, phase.metrics[4:], strict=True):
        assert evidence.undefined == (evidence.denominator == 0)
        if evidence.undefined:
            assert evidence.numerator == 0 and metric.value is None


def test_independent_exhaustive_small_sequences(phase_input):
    # Window-search criterion and transition contingency counts are an independent
    # reference for every four-outcome sequence of up to four choices (341 cases).
    for n in range(5):
        for codes in itertools.product((1, 2, 6, 7), repeat=n):
            result = import_medpc_file(phase_input(codes), "Synthetic phase")
            phase = result.phase_summary
            cls = "".join("C" if c in (1, 2) else "I" for c in codes)
            k = cls.find("CCC") + 3 if "CCC" in cls else None
            d = phase.diagnostics
            assert d.criterion_choice_ordinal == k
            if n:
                errors = [i for i, c in enumerate(cls, 1) if c == "I"]
                pre = sum(i < k for i in errors) if k else len(errors)
                post = len(errors) - pre
                assert [m.value for m in phase.metrics[:3]] == [cls.count("C") / n, pre, post]
                assert phase.metrics[3].value == (post / (n - k) if k and k < n else None)
            for conditioning, evidence in zip((1, 6, 2, 7), phase.strategies, strict=True):
                pairs = [
                    (a, b) for a, b in zip(codes, codes[1:], strict=False) if a == conditioning
                ]
                same = sum((a in (1, 2)) == (b in (1, 2)) for a, b in pairs)
                num = same if conditioning in (1, 6) else len(pairs) - same
                assert (evidence.numerator, evidence.denominator) == (num, len(pairs))
            assert sum(e.denominator for e in phase.strategies) == max(0, n - 1)


@pytest.mark.parametrize("first", [1, 2, 6, 7])
@pytest.mark.parametrize("next_classes", [(1, 2), (6, 7)])
def test_next_reward_does_not_condition_preceding_pair(phase_input, first, next_classes):
    phases = [
        import_medpc_file(phase_input((first, c)), "Reversal").phase_summary for c in next_classes
    ]
    assert phases[0].strategies == phases[1].strategies


@pytest.mark.parametrize(
    "damage", ["missing", "invalid", "gap", "mismatch", "post_terminator", "uncorroborated_zero"]
)
def test_source_integrity_withholds_all_new_metrics(phase_input, damage):
    path = phase_input((1, 1, 1, 7))
    text = path.read_text()
    if damage == "missing":
        text = text[: text.index("C:\n")]
    if damage == "invalid":
        text = text.replace("1.01", "1.03")
    if damage == "gap":
        text = text.replace("C:\n  0:", "C:\n  1:")
    if damage == "mismatch":
        text = text.replace("0: 3 1 4", "0: 3 1 5")
    if damage == "post_terminator":
        text = text.replace("2.01", "-987.987")
    if damage == "uncorroborated_zero":
        text = text.replace("3.07", "3.07 0.00").replace("0: 3 0 0 1", "0: 4 0 0 1")
    path.write_text(text)
    result = import_medpc_file(path, "Reversal")
    assert result.error is None
    phase = result.phase_summary
    assert phase.status == "withheld"
    assert all(m.value is None and m.reasons for m in phase.metrics)
    assert all(e.numerator is e.denominator is e.undefined is None for e in phase.strategies)
    assert phase.diagnostics.criterion_reached is None
    assert all(c is None for c in phase.choice_error_classes)


def test_unassigned_phase_and_no_cross_file_criterion(phase_input):
    a = import_medpc_file(phase_input((1, 1), name="a.txt"))
    assert a.summary.metrics[0].value == 2
    assert a.phase_summary.status == "phase_unassigned"
    assert all(m.value is None for m in a.phase_summary.metrics)
    for path in (a.source_file, phase_input((1,), name="b.txt")):
        p = import_medpc_file(path, "Reversal").phase_summary
        assert p.diagnostics.criterion_reached is False
        assert p.diagnostics.eligible_pair_count == len(p.choice_error_classes) - 1


def test_order_padding_and_missing_duration(phase_input):
    path = phase_input((1, 1, 1, 7))
    original = import_medpc_file(path, "Acquisition").phase_summary
    text = path.read_text().replace("S: 5\n", "").replace("1.01", "0.01").replace("2.01", "0.01")
    path.write_text(text.replace("3.07", "3.07 0 0"))
    result = import_medpc_file(path, "Acquisition")
    assert [m.value for m in result.phase_summary.metrics] == [m.value for m in original.metrics]
    assert result.phase_summary.strategies == original.strategies
    assert result.phase_summary.diagnostics.criterion_source_index == 2
    assert result.summary.diagnostics.unused_slot_count == 2
    assert result.phase_summary.metrics[0].status == "available_with_warnings"


@pytest.mark.parametrize("format", ["csv", "xlsx"])
def test_phase_exports_literal_labels_evidence_and_versions(phase_input, tmp_path, format):
    path = phase_input()
    before = path.read_bytes(), path.stat().st_mtime_ns
    result = import_medpc_file(path, "=Reversal 2")
    out = export_import_results({path: result}, [path], tmp_path, format)
    if format == "csv":
        with (out / "phase_metrics.csv").open(newline="") as stream:
            (row,) = csv.DictReader(stream)
        with (out / "choices.csv").open(newline="") as stream:
            choices = list(csv.DictReader(stream))
    else:
        book = load_workbook(out / "results.xlsx")
        header, values = book["Phase metrics"].values
        row = dict(zip(header, values, strict=True))
        hdr, *body = book["Choices"].values
        choices = [dict(zip(hdr, r, strict=True)) for r in body]
        assert book["Phase metrics"].cell(2, list(header).index("phase") + 1).data_type == "s"
        assert all(c.data_type not in ("f", "e") for sh in book for r in sh for c in r)
        book.close()
    assert row["phase"] == "=Reversal 2"
    assert int(row["criterion_choice_ordinal"]) == 7
    assert int(row["criterion_source_index"]) == 6
    assert float(row["prl.phase.adjusted_regressive_error_proportion"]) == pytest.approx(2 / 3)
    for name, e in zip(STRATEGIES, result.phase_summary.strategies, strict=True):
        assert int(row[f"{name}_numerator"]) == e.numerator
        assert int(row[f"{name}_denominator"]) == e.denominator
    assert [c["phase_error_classification"] for c in choices] == list(
        result.phase_summary.choice_error_classes
    )
    config = json.loads(row["configuration_json"])
    assert (
        row["configuration_sha256"]
        == hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    )
    assert int(row["omission_count"]) == 0
    assert row["omission_count_basis"] == "owner-confirmed no-omission protocol"
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["schema_version"] == "4"
    assert manifest["configuration"]["phase_definition_version"] == "2"
    assert manifest["configuration"]["phase_configurations"][0]["configuration"] == asdict(
        result.phase_summary.config
    )
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize("stale", ["missing", "version", "profile", "source"])
def test_export_refuses_stale_phase_snapshot(phase_input, tmp_path, stale):
    path = phase_input()
    result = import_medpc_file(path, "Reversal")
    phase = result.phase_summary
    if stale == "missing":
        phase = None
    if stale == "version":
        phase = replace(phase, definition_version="old")
    if stale == "profile":
        phase = replace(phase, config=replace(phase.config, protocol_profile="unknown"))
    if stale == "source":
        phase = replace(phase, source_sha256="wrong")
    with pytest.raises(ValueError, match="re-import"):
        export_import_results({path: replace(result, phase_summary=phase)}, [path], tmp_path)
    assert not list(tmp_path.glob("trial-cruncher-export-*"))


def test_stale_events_and_unknown_program_fail(phase_input):
    result = import_medpc_file(phase_input(), "Reversal")
    with pytest.raises(ValueError, match="do not match"):
        calculate_phase_metrics(
            replace(result.session, events=result.session.events[:-1]), "Reversal"
        )
    bad = import_medpc_file(phase_input(program="UNKNOWN"), "Reversal")
    assert bad.error and bad.phase_summary is None
