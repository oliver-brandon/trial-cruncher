"""All exports in this module are synthetic, not copies of research recordings."""

import hashlib
import json
import subprocess
import sys
from decimal import Decimal

import pytest

from trial_cruncher.medpc import MedPCReader, MedPCReadError
from trial_cruncher.prl import PRLNormalizer


def normalized(path):
    raw = MedPCReader().read(path)
    (session,) = PRLNormalizer().normalize(raw, path)
    return raw, session


@pytest.mark.parametrize("program", ["PRL_BO", "PRL_OPTO_CORSTIM"])
def test_hand_checked_choice_decoding_and_provenance(write_export, program):
    path = write_export(program=program)
    before = path.read_bytes(), path.stat().st_mtime_ns
    raw, session = normalized(path)
    assert session.subject_id == "0007"
    assert session.session_id is None  # No explicit session identifier exists in this format.
    assert session.duration_s == 10.0  # Never the 3600-second header interval.
    assert session.source_file == path.resolve()
    assert raw["headers"]["Group"] == "00"
    assert raw["source_text"] == before[0].decode()
    assert raw["source_sha256"] == hashlib.sha256(before[0]).hexdigest()
    assert session.metadata["raw_medpc"] is raw
    assert [event.timestamp_s for event in session.events] == [0.0, 1.2, 2.3, 4.5]
    assert [event.attributes for event in session.events] == [
        {"outcome_code": 1, "correct": True, "rewarded": True},
        {"outcome_code": 2, "correct": True, "rewarded": False},
        {"outcome_code": 6, "correct": False, "rewarded": True},
        {"outcome_code": 7, "correct": False, "rewarded": False},
    ]
    assert [event.raw_values["index"] for event in session.events] == [0, 1, 2, 3]
    assert session.events[1].raw_values["value"] == Decimal("1.22")
    assert session.events[1].raw_values["line_number"] == 20
    assert all(value is True for value in session.metadata["summary_checks"].values())
    assert not session.warnings
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_ignored_fields_and_saved_values_are_preserved_without_latency(write_export):
    path = write_export()
    path = write_export(path.read_text().replace("0.50\nJ:", "0.50 1.90\nJ:\n  0: 1.00"))
    raw, session = normalized(path)
    assert raw["arrays"]["F"] == {0: Decimal("0.50"), 1: Decimal("1.90")}
    assert raw["arrays"]["J"] == {0: Decimal("1.00")}
    assert raw["arrays"]["A"][4] == 0
    assert session.metadata["head_entries_recorded"] is False
    assert session.metadata["latency_available"] is False
    assert len(session.events) == 4
    assert session.trials == ()  # No invented trial boundaries or identifiers.


def test_bom_crlf_unknown_fields_and_decimals(write_export):
    path = write_export()
    text = (
        path.read_text() + "Operator note: synthetic: calibration\nZ: -1.20\nQ:\n  0: 0.00 2.50\n"
    )
    path = write_export("\ufeff" + text.replace("\n", "\r\n"))
    reader = MedPCReader()
    assert reader.can_read(path)
    raw = reader.read(path)
    assert "\r\n" in raw["source_text"]
    assert raw["headers"]["Operator note"] == "synthetic: calibration"
    assert str(raw["scalars"]["Z"]) == "-1.20"
    assert raw["arrays"]["Q"][0] == 0
    assert raw["arrays"]["J"] == {}


@pytest.mark.parametrize(
    "suffix,text",
    [
        (".MPC", "\\ Program source\nDISKVARS = A, B\nS.S.1,\n"),
        (".txt", "not a session\n"),
        (".mat", "\x00binary content"),
    ],
)
def test_content_detection_rejects_non_exports(tmp_path, suffix, text):
    path = tmp_path / f"input{suffix}"
    path.write_text(text)
    assert not MedPCReader().can_read(path)
    with pytest.raises(MedPCReadError, match="session export"):
        MedPCReader().read(path)


def test_detection_does_not_depend_on_extension_and_skips_appledouble(write_export):
    path = write_export()
    renamed = path.with_suffix(".dat")
    path.rename(renamed)
    assert MedPCReader().can_read(renamed)
    sidecar = renamed.with_name("._synthetic.txt")
    sidecar.write_bytes(renamed.read_bytes())
    assert not MedPCReader().can_read(sidecar)
    with pytest.raises(MedPCReadError, match="AppleDouble"):
        MedPCReader().read(sidecar)


@pytest.mark.parametrize(
    "extra,problem",
    [
        ("garbled data", "Unrecognized line"),
        ("D: 0.00", "Duplicate variable"),
        ("Subject: another", "Duplicate header"),
        ("Q:\n  0: 1.00\n  0: 2.00", "Duplicate index"),
        ("Note: hello\n  0: 1.00", "no array heading"),
        ("Q:\n  0:", "no values"),
        ("Q: NaN", "Invalid numeric"),
        ("Q:\n  0: 1.0 broken", "Invalid numeric"),
    ],
)
def test_malformed_input_fails_with_source_and_line(write_export, extra, problem):
    path = write_export()
    path = write_export(path.read_text() + extra + "\n")
    with pytest.raises(MedPCReadError, match=problem) as error:
        MedPCReader().read(path)
    assert f"{path}:" in str(error.value)


def test_multiple_sessions_are_rejected(write_export):
    path = write_export()
    path = write_export(path.read_text() * 2)
    with pytest.raises(MedPCReadError, match="multiple sessions"):
        MedPCReader().read(path)


def test_missing_file_and_invalid_encoding(tmp_path):
    path = tmp_path / "missing.txt"
    assert not MedPCReader().can_read(path)
    with pytest.raises(MedPCReadError, match="could not read"):
        MedPCReader().read(path)
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(MedPCReadError, match="UTF-8"):
        MedPCReader().read(path)


def test_unknown_program_can_be_extracted_but_not_interpreted(write_export):
    path = write_export(program="UNCONFIRMED")
    raw = MedPCReader().read(path)
    with pytest.raises(ValueError, match="Unsupported PRL program"):
        PRLNormalizer().normalize(raw, path)


def test_normalizer_rejects_wrong_format_and_provenance(write_export):
    path = write_export()
    raw = MedPCReader().read(path)
    with pytest.raises(ValueError, match="requires MedPCReader"):
        PRLNormalizer().normalize({}, path)
    with pytest.raises(ValueError, match="provenance"):
        PRLNormalizer().normalize(raw, path.with_name("different.txt"))


@pytest.mark.parametrize("encoded", ["1.23", "1.211", "-1.00", "0.00", "1e9999"])
def test_invalid_choice_is_retained_not_silently_dropped(write_export, encoded):
    path = write_export()
    path = write_export(path.read_text().replace("1.22", encoded))
    _, session = normalized(path)
    assert len(session.events) == 4
    event = session.events[1]
    assert event.raw_values["value"] == Decimal(encoded)
    assert event.timestamp_s is None
    assert all(value is None for value in event.attributes.values())
    assert all(value is None for value in session.metadata["summary_checks"].values())
    assert any("C[1]" in warning for warning in session.warnings)


def test_sparse_out_of_order_indices_are_preserved(write_export):
    path = write_export()
    path = write_export(
        path.read_text().replace("0: 0.01 1.22 2.36 4.57", "3: 4.57\n  0: 0.01 1.22")
    )
    raw, session = normalized(path)
    assert list(raw["arrays"]["C"]) == [3, 0, 1]
    assert [event.raw_values["index"] for event in session.events] == [0, 1, 3]
    assert any("not contiguous" in warning for warning in session.warnings)
    assert any("out of index order" in warning for warning in session.warnings)
    assert all(value is None for value in session.metadata["summary_checks"].values())


def test_decreasing_times_and_choices_after_duration_are_reported(write_export):
    path = write_export()
    path = write_export(path.read_text().replace("0.01 1.22 2.36 4.57", "1.01 0.22 2.36 14.57"))
    _, session = normalized(path)
    assert [event.timestamp_s for event in session.events] == [1.0, 0.2, 2.3, 14.5]
    assert any("precedes" in warning for warning in session.warnings)
    assert any("exceeds" in warning for warning in session.warnings)


@pytest.mark.parametrize("suffix,expected_choices", [(" -987.987", 4), (" -987.987 9.01", 4)])
def test_explicit_terminator_is_raw_only(write_export, suffix, expected_choices):
    path = write_export()
    path = write_export(path.read_text().replace("2.36 4.57", "2.36 4.57" + suffix))
    raw, session = normalized(path)
    assert raw["arrays"]["C"][4] == Decimal("-987.987")
    assert len(session.events) == expected_choices
    if "9.01" in suffix:
        assert any("after the terminator" in warning for warning in session.warnings)
    else:
        assert not session.warnings


def test_missing_fields_are_not_replaced_with_zero(write_export):
    path = write_export()
    text = path.read_text().replace("Subject: 0007\n", "").replace("S: 10.00\n", "")
    text = text.replace("C:\n  0: 0.01 1.22 2.36 4.57\n", "")
    _, session = normalized(write_export(text))
    assert session.subject_id is None
    assert session.duration_s is None
    assert not session.events
    assert all(value is None for value in session.metadata["summary_checks"].values())
    assert any("choice array is missing" in warning for warning in session.warnings)


def test_empty_choice_array_is_distinct_from_missing(write_export):
    path = write_export()
    text = path.read_text().replace("0: 0.01 1.22 2.36 4.57", "")
    text = text.replace("2.00 2.00 4.00", "0.00 0.00 0.00")
    text = text.replace("1.00 1.00 1.00 1.00", "0.00 0.00 0.00 0.00")
    raw, session = normalized(write_export(text))
    assert raw["arrays"]["C"] == {}
    assert not session.events
    assert all(value is True for value in session.metadata["summary_checks"].values())
    assert not session.warnings


def test_disagreeing_summaries_are_reported_not_corrected(write_export):
    path = write_export()
    text = path.read_text().replace("2.00 2.00 4.00", "3.00 2.00 5.00")
    raw, session = normalized(write_export(text))
    assert raw["arrays"]["A"][0] == 3
    assert session.metadata["summary_checks"]["A[0]"] is False
    assert session.metadata["summary_checks"]["A[2]"] is False
    assert session.metadata["summary_checks"]["B[0]"] is True
    assert len(session.warnings) == 2


def test_incomplete_summary_and_negative_duration(write_export):
    path = write_export()
    text = path.read_text().replace("S: 10.00", "S: -1.00")
    text = text.replace("0: 1.00 1.00 1.00 1.00", "0: 1.50")
    _, session = normalized(write_export(text))
    assert session.duration_s is None
    assert session.metadata["summary_checks"]["B[0]"] is None
    assert session.metadata["summary_checks"]["B[3]"] is None
    assert any("nonnegative integer" in warning for warning in session.warnings)
    assert any("saved count is missing" in warning for warning in session.warnings)


def test_unrepresentable_duration_remains_unavailable(write_export):
    path = write_export()
    _, session = normalized(write_export(path.read_text().replace("S: 10.00", "S: 1e9999")))
    assert session.duration_s is None
    assert any("S: task duration" in warning for warning in session.warnings)


def test_partial_session_does_not_recompute_saved_fraction_or_infer_limit(write_export):
    path = write_export()
    text = path.read_text().replace("0: 0.01 1.22 2.36 4.57", "0: 0.01 1.22")
    text = text.replace("2.00 2.00 4.00", "2.00 0.00 2.00")
    text = text.replace("1.00 1.00 1.00 1.00", "1.00 1.00 0.00 0.00")
    text = text.replace("5: 0.50", "5: 0.07")
    raw, session = normalized(write_export(text))
    assert len(session.events) == 2
    assert raw["arrays"]["A"][5] == Decimal("0.07")
    assert "Y" not in raw["scalars"]
    assert not session.warnings


def test_cli_inspection_success_warning_and_failure(write_export):
    path = write_export()

    def invoke():
        return subprocess.run(
            [sys.executable, "-m", "trial_cruncher", "--inspect-medpc", str(path)],
            text=True,
            capture_output=True,
        )

    result = invoke()
    assert result.returncode == 0
    assert json.loads(result.stdout)["choices"][1]["timestamp_s"] == 1.2
    write_export(path.read_text().replace("1.22", "1.23"))
    result = invoke()
    assert result.returncode == 2
    assert json.loads(result.stdout)["warnings"]
    assert json.loads(result.stderr.splitlines()[0])["level"] == "WARNING"
    write_export("not a session")
    result = invoke()
    assert result.returncode == 1
    assert not result.stdout
    assert "Traceback" not in result.stderr
    assert json.loads(result.stderr)["level"] == "ERROR"
