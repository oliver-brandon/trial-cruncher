"""Compact workbook uses reviewed results and preserves data and audit links."""

from io import BytesIO

from openpyxl import load_workbook

from trial_cruncher.analysis_metadata import AnalysisMetadata
from trial_cruncher.compact_excel import build_compact_workbook
from trial_cruncher.processing import import_medpc_file


def test_compact_workbook_choices_links_and_literal_subject(phase_input):
    source = phase_input((1, 2, 6, 7))
    source.write_text(source.read_text().replace("Subject: 0007", "Subject: =test"))
    result = import_medpc_file(source, "Reversal", AnalysisMetadata("Vehicle", "C", included=True))
    manifest = {
        "inputs": [
            {
                "source_file": str(source),
                "status": "exported",
                "source_sha256": result.raw["source_sha256"],
                "warnings": [],
                "error": None,
            }
        ]
    }
    book = build_compact_workbook({source: result}, [source], manifest)
    stream = BytesIO()
    book.save(stream)
    stream.seek(0)
    loaded = load_workbook(stream)
    assert loaded.sheetnames == ["Data", "=test", "Metadata"]
    assert loaded["Data"]["A2"].value == "=test"
    assert loaded["Data"]["A2"].data_type == "s"
    assert loaded["Data"]["A2"].hyperlink.location == "'=test'!A1"
    guide = dict(loaded["Metadata"].iter_rows(min_col=1, max_col=2, values_only=True))
    assert guide["Choice"] == "1 = correct lever, 0 = incorrect lever."
    assert guide["Outcome"] == "1 = rewarded, 0 = unrewarded."
    assert "three consecutive correct" in guide["Trials to criterion"]
    sheet = loaded["=test"]
    assert [sheet.cell(3, c).value for c in range(1, 4)] == [1, 1, 1]
    assert [sheet.cell(4, c).value for c in range(1, 4)] == [2, 1, 0]
    assert [sheet.cell(5, c).value for c in range(1, 4)] == [3, 0, 1]
    meta = loaded["Metadata"]
    assert meta["B2"].value == 2
    assert meta["C2"].value == "=test!A"
    assert meta["C2"].data_type == "s"


def test_sheet_name_collisions_and_metadata_overflow(phase_input):
    paths = [phase_input((1,), name=f"{i}.txt") for i in range(4)]
    subjects = ["Metadata", "a/b", "a:b", "Data"]
    results = {}
    inputs = []
    for source, subject in zip(paths, subjects, strict=True):
        source.write_text(source.read_text().replace("Subject: 0007", f"Subject: {subject}"))
        result = import_medpc_file(source, "Acquisition", AnalysisMetadata("T" * 35000))
        results[source] = result
        inputs.append(
            {
                "source_file": str(source),
                "status": "exported",
                "source_sha256": result.raw["source_sha256"],
                "warnings": [],
                "error": None,
            }
        )
    book = build_compact_workbook(results, paths, {"inputs": inputs})
    assert book.sheetnames == ["Data", "Metadata (2)", "a_b", "a_b (2)", "Data (2)", "Metadata"]
    data = book["Data"]
    cell = data["C2"]
    assert cell.value.startswith("[Full text: Metadata rows ")
    start, end = (int(v) for v in cell.value.split("rows ")[1].strip("]").split("-"))
    meta = book["Metadata"]
    assert "".join(meta.cell(row, 6).value for row in range(start, end + 1)) == "T" * 35000
    assert meta["C2"].value == "Metadata (2)!A"


def test_unidentified_recordings_remain_separate_and_failed_inputs_are_audited(phase_input):
    first = phase_input((1, 7), name="first.txt")
    second = phase_input((1, 7), name="second.txt")
    invalid = phase_input(name="invalid.txt", program="UNSUPPORTED")
    for path in (first, second):
        path.write_text(path.read_text().replace("Subject: 0007\n", ""))
    results = {p: import_medpc_file(p, "Reversal") for p in (first, second, invalid)}
    inputs = []
    for path, result in results.items():
        inputs.append(
            {
                "source_file": str(path),
                "status": "failed" if result.error else "exported",
                "source_sha256": result.raw["source_sha256"],
                "warnings": [],
                "error": result.error,
            }
        )
    book = build_compact_workbook(results, [first, second, invalid], {"inputs": inputs})
    assert book.sheetnames == ["Data", "Unassigned", "Unassigned (2)", "Metadata"]
    assert book["Data"].max_row == 3
    rows = list(book["Metadata"].values)
    fields = {label: index for index, label in enumerate(rows[0])}
    assert rows[3][fields["Status"]] == "failed"
    assert rows[3][fields["Error"]]
    assert rows[3][fields["Data row"]] is None
    assert book["Metadata"].auto_filter.ref.split(":")[-1].endswith("4")
    assert sum(row[fields["Status"]] in ("exported", "failed") for row in rows[1:]) == 3
