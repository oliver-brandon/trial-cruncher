"""Hand-calculated synthetic acceptance cases for the approved PRL definitions."""

from copy import deepcopy
from dataclasses import replace

import pytest

from trial_cruncher.prl_metrics import METRIC_LABELS, calculate_prl_summary
from trial_cruncher.processing import import_medpc_file


@pytest.fixture
def imported(tmp_path):
    def load(
        c="C:\n  0: 0.01 1.22 2.36 4.57\n",
        summaries="A:\n  0: 2 2 4\nB:\n  0: 1 1 1 1\n",
        *,
        duration="S: 10\n",
        subject="Subject: 0007\n",
        extra="",
        program="PRL_BO",
    ):
        path = tmp_path / "synthetic-metrics.txt"
        path.write_text(
            f"File: synthetic\n{subject}MSN: {program}\n{duration}{c}{summaries}{extra}"
        )
        result = import_medpc_file(path)
        assert result.error is None
        assert result.summary is not None
        return result

    return load


@pytest.mark.parametrize("program", ["PRL_BO", "PRL_OPTO", "PRL_OPTO_CORSTIM"])
@pytest.mark.parametrize(
    "choices,summaries,expected",
    [
        ("0.01 1.22 2.36 4.57", "A:\n  0: 2 2 4\nB:\n  0: 1 1 1 1\n", (4, 2, 2, 2, 2, 0.5)),
        ("0.01 1.22 2.31", "A:\n  0: 3 0 3\nB:\n  0: 2 1 0 0\n", (3, 3, 0, 2, 1, 1)),
        ("0.06 1.27", "A:\n  0: 0 2 2\nB:\n  0: 0 0 1 1\n", (2, 0, 2, 1, 1, 0)),
        ("0.01 1.26 2.37", "A:\n  0: 1 2 3\nB:\n  0: 1 0 1 1\n", (3, 1, 2, 2, 1, 1 / 3)),
        ("0.01 1.22 -987.987", "A:\n  0: 2 0 2\nB:\n  0: 1 1 0 0\n", (2, 2, 0, 1, 1, 1)),
    ],
)
def test_hand_calculated_examples(imported, program, choices, summaries, expected):
    result = imported(f"C:\n  0: {choices}\n", summaries, program=program)
    summary = result.summary
    assert [m.name for m in summary.metrics] == list(METRIC_LABELS)
    assert tuple(m.value for m in summary.metrics) == expected
    assert all(isinstance(m.value, int) for m in summary.metrics[:5])
    assert all(m.status == "available" and not m.reasons for m in summary.metrics)
    assert all(m.definition_version == "3" for m in summary.metrics)
    assert [m.unit for m in summary.metrics] == ["count"] * 5 + ["proportion"]
    assert summary.eligibility_policy == "strict-withholding-v2"


@pytest.mark.parametrize("c", ["C:\n", "C:\n  0: -987.987\n"])
def test_explicit_empty_sequence_zero_counts_undefined_percentage(imported, c):
    result = imported(c, "A:\n  0: 0 0 0\nB:\n  0: 0 0 0 0\n")
    counts, percent = result.summary.metrics[:5], result.summary.metrics[-1]
    assert all(m.value == 0 and m.status == "available" for m in counts)
    assert percent.value is None and percent.status == "unavailable"
    assert "zero recorded choices" in percent.reasons[0]
    diagnostics = result.summary.diagnostics
    assert diagnostics.c_present
    assert diagnostics.observed_record_count == diagnostics.decoded_choice_count == 0
    assert diagnostics.invalid_record_count == diagnostics.post_terminator_count == 0
    assert diagnostics.terminator_seen == ("-987" in c)


def test_missing_c_never_becomes_zero(imported):
    result = imported("", "A:\n  0: 0 0 0\nB:\n  0: 0 0 0 0\n")
    assert all(m.value is None and "C is missing" in m.reasons[0] for m in result.summary.metrics)
    quality = result.summary.diagnostics
    assert not quality.c_present
    assert quality.terminator_seen is None
    assert quality.observed_record_count is quality.decoded_choice_count is None
    assert quality.invalid_record_count is quality.post_terminator_count is None
    assert quality.c_indices_have_gaps is None


@pytest.mark.parametrize("invalid", ["1.23", "0", "-1", "1.234", "1E+999"])
def test_invalid_record_withholds_all_metrics_and_keeps_diagnostics(imported, invalid):
    result = imported(f"C:\n  0: 0.01 {invalid} 2.36 4.57\n")
    assert all(m.value is None and m.status == "unavailable" for m in result.summary.metrics)
    assert all("1 invalid choice" in m.reasons[0] for m in result.summary.metrics)
    quality = result.summary.diagnostics
    assert (
        quality.observed_record_count,
        quality.decoded_choice_count,
        quality.invalid_record_count,
    ) == (4, 3, 1)
    assert len(result.session.events) == 4


@pytest.mark.parametrize(
    "c,reason",
    [
        ("C:\n  0: 0.01\n  2: 2.36\n", "not contiguous"),
        ("C:\n  1: 0.01 1.22 2.36 4.57\n", "not contiguous"),
        ("C:\n  0: 0.01 -987.987 2.36\n", "after the terminator"),
        ("C:\n  0: 0.01 -987.987 -987.987\n", "after the terminator"),
    ],
)
def test_incomplete_or_ambiguous_sequences_are_withheld(imported, c, reason):
    result = imported(c)
    assert all(m.value is None for m in result.summary.metrics)
    assert all(reason in " ".join(m.reasons) for m in result.summary.metrics)


@pytest.mark.parametrize(
    "array,index", [("A", 0), ("A", 1), ("A", 2), *[("B", i) for i in range(4)]]
)
def test_each_saved_count_mismatch_withholds_all_six(imported, array, index):
    a, b = [2, 2, 4], [1, 1, 1, 1]
    (a if array == "A" else b)[index] += 1
    result = imported(
        summaries=f"A:\n  0: {' '.join(map(str, a))}\nB:\n  0: {' '.join(map(str, b))}\n"
    )
    assert all(m.value is None and m.status == "unavailable" for m in result.summary.metrics)
    assert all(f"{array}[{index}]" in " ".join(m.reasons) for m in result.summary.metrics)
    assert result.summary.diagnostics.decoded_choice_count == 4  # Diagnostic only.
    assert result.raw["arrays"][array][index] == (a if array == "A" else b)[index]


def test_mismatch_overrides_empty_sequence_zero_counts(imported):
    result = imported("C:\n", "A:\n  0: 0 0 10\nB:\n  0: 0 0 0 0\n")
    assert all(m.value is None for m in result.summary.metrics)
    assert "A[2]" in result.summary.metrics[0].reasons[0]
    assert result.summary.diagnostics.observed_record_count == 0


def test_all_independent_blocking_reasons_are_retained(imported):
    result = imported("C:\n  1: 0.01 1.23 -987.987 2.36\n")
    for metric in result.summary.metrics:
        assert metric.value is None
        assert len(metric.reasons) == 3
        assert "not contiguous" in metric.reasons[0]
        assert "invalid choice" in metric.reasons[1]
        assert "after the terminator" in metric.reasons[2]


@pytest.mark.parametrize("summaries", ["", "A:\n  0: -1 2.5\nB:\n", "B:\n  1: 1\n"])
def test_unavailable_saved_checks_warn_without_withholding(imported, summaries):
    result = imported(summaries=summaries)
    assert tuple(m.value for m in result.summary.metrics) == (4, 2, 2, 2, 2, 0.5)
    assert all(m.status == "available_with_warnings" for m in result.summary.metrics)
    assert all(
        m.warnings == result.session.warnings and not m.reasons for m in result.summary.metrics
    )


@pytest.mark.parametrize("duration", ["", "S: -1\n", "S: 1E+999\n", "S: 0\n"])
def test_duration_does_not_control_choice_metrics(imported, duration):
    result = imported(duration=duration)
    assert result.session.duration_s == (0 if duration == "S: 0\n" else None)
    assert tuple(m.value for m in result.summary.metrics) == (4, 2, 2, 2, 2, 0.5)
    assert all(m.status == "available_with_warnings" for m in result.summary.metrics)


@pytest.mark.parametrize(
    "c",
    ["C:\n  0: 9.01 1.22 2.36 14.57\n", "C:\n  2: 2.36 4.57\n  0: 0.01 1.22\n"],
)
def test_time_or_printed_row_order_warnings_do_not_withhold(imported, c):
    result = imported(c)
    assert tuple(m.value for m in result.summary.metrics) == (4, 2, 2, 2, 2, 0.5)
    assert all(m.status == "available_with_warnings" for m in result.summary.metrics)


def test_identical_indexed_records_count_separately(imported):
    result = imported("C:\n  0: 0.01 0.01\n", "A:\n  0: 2 0 2\nB:\n  0: 2 0 0 0\n")
    assert tuple(m.value for m in result.summary.metrics) == (2, 2, 0, 2, 0, 1)
    assert not result.session.warnings


def test_unrelated_warnings_and_missing_ids_do_not_withhold(imported):
    result = imported(subject="", extra="F:\n  2: 99\n")
    assert result.session.subject_id is result.session.session_id is None
    assert all(
        m.value is not None and m.status == "available_with_warnings"
        for m in result.summary.metrics
    )


def test_calculation_does_not_parse_warning_text_or_modify_source(imported):
    result = imported()
    session = replace(result.session, warnings=("C is missing; synthetic text only.",))
    before = deepcopy(session)
    summary = calculate_prl_summary(session)
    assert summary.metrics[0].value == 4
    assert all(m.warnings == session.warnings for m in summary.metrics)
    assert session == before
    assert result.summary.metrics[0].status == "available"


def test_missing_eligibility_not_hidden_by_empty_warning_text(imported):
    result = imported("C:\n  1: 0.01 1.23 -987.987 2.36\n")
    summary = calculate_prl_summary(replace(result.session, warnings=()))
    assert all(m.value is None and len(m.reasons) == 3 for m in summary.metrics)


@pytest.mark.parametrize(
    "text",
    [
        "File: synthetic\nMSN: OTHER\nC:\n",
        "File: synthetic\nMSN: PRL_BO\nC:\n  0: garbage\n",
        "File: synthetic\nMSN: PRL_BO\nC:\n  0: 0.01\n  0: 1.22\n",
    ],
)
def test_failed_inputs_have_no_metric_results(tmp_path, text):
    path = tmp_path / "synthetic-bad.txt"
    path.write_text(text)
    result = import_medpc_file(path)
    assert result.error and result.session is result.summary is None


def test_unsupported_normalizer_or_stale_events_fail_closed(imported):
    result = imported()
    with pytest.raises(ValueError, match="normalizer version 2"):
        calculate_prl_summary(
            replace(
                result.session, metadata={**result.session.metadata, "normalizer_version": "999"}
            )
        )
    with pytest.raises(ValueError, match="do not match"):
        calculate_prl_summary(replace(result.session, events=result.session.events[:-1]))
