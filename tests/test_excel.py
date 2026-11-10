"""Synthetic Excel round trips and safeguards; not scientific validation."""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from trial_cruncher import excel
from trial_cruncher.excel import save_workbook
from trial_cruncher.exporters import export_import_results
from trial_cruncher.prl_metrics import METRIC_LABELS, calculate_prl_summary
from trial_cruncher.processing import import_medpc_file
from trial_cruncher.tables import build_choice_table, build_session_table


def records(sheet):
    header, *body = sheet.values
    return [dict(zip(header, row, strict=True)) for row in body]


def restored_cell(book, sheet, coordinate):
    parts = [
        row
        for row in records(book["Provenance"])
        if row["kind"] == "overflow" and row["sheet"] == sheet and row["cell"] == coordinate
    ]
    if parts:
        assert [p["part"] for p in parts] == list(range(1, len(parts) + 1))
        assert all(p["parts"] == len(parts) for p in parts)
        return "".join(p["text"] for p in parts)
    return book[sheet][coordinate].value


def test_excel_round_trip_all_tables_and_source_snapshot(write_export, tmp_path):
    path = write_export()
    result = import_medpc_file(path)
    session = replace(
        result.session,
        subject_id="=1+1",
        session_id="00001234567890123456",
        warnings=("#N/A", '+cmd|"x"', "@SUM(A1)", 'comma, "quote"\nμ'),
    )
    result = replace(result, session=session, summary=calculate_prl_summary(session))
    # Export the reviewed values only while source content still matches.
    before = path.read_bytes(), path.stat().st_mtime_ns
    destination = export_import_results({path: result}, [path], tmp_path, "xlsx")
    book = load_workbook(destination / "results.xlsx")
    assert book.sheetnames == ["Sessions", "Choices", "Phase metrics", "Quality", "Provenance"]
    expected = {
        "Sessions": build_session_table([session], {path: result.summary}),
        "Choices": build_choice_table([session]),
    }
    for name, table in expected.items():
        assert list(next(book[name].values)) == list(table.columns)
        assert book[name].max_row == len(table) + 1
        for row_index, row in enumerate(table.itertuples(index=False, name=None), 2):
            for column, value in enumerate(row, 1):
                cell = book[name].cell(row_index, column)
                actual = restored_cell(book, name, cell.coordinate)
                if isinstance(value, Decimal):
                    value = str(value)
                if isinstance(value, float):
                    assert actual == pytest.approx(value, rel=1e-14)
                else:
                    assert actual == value
                if isinstance(value, str) and value:
                    assert cell.data_type == "s"
                if isinstance(value, bool):
                    assert cell.data_type == "b"
        assert book[name].freeze_panes == "A2"
        assert book[name].auto_filter.ref == book[name].dimensions
        assert book[name]["A1"].font.bold
    quality = records(book["Quality"])
    assert len(quality) == 15
    assert quality[0]["input_status"] == "exported"
    assert [row["metric"] for row in quality if row["record_type"] == "metric"] == list(
        METRIC_LABELS
    )
    manifest = json.loads((destination / "manifest.json").read_text())
    embedded = "".join(
        row["text"] for row in records(book["Provenance"]) if row["kind"] == "manifest"
    )
    assert json.loads(embedded) == manifest
    assert manifest["tables"]["Choices"]["rows"] == 4
    assert manifest["workbook_schema_version"] == "3"
    assert manifest["schema_version"] == "4"
    assert manifest["configuration"]["metric_eligibility_policy"] == "strict-withholding-v2"
    assert all(
        cell.data_type not in ("f", "e") and cell.hyperlink is None
        for sheet in book
        for row in sheet
        for cell in row
    )
    with ZipFile(destination / "results.xlsx") as archive:
        assert not any("externalLink" in name for name in archive.namelist())
        assert all(
            b"<f>" not in archive.read(name)
            for name in archive.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )
    book.close()
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


@pytest.mark.parametrize("variant", ["zero", "empty", "missing", "invalid", "mismatch", "sparse"])
def test_missing_zero_withheld_and_excluded_inputs(write_export, tmp_path, variant):
    text = "File: synthetic\nMSN: PRL_BO\nSubject: 0007\nC:\n  0: 0.06 1.27\n"
    text = {
        "empty": text.replace("  0: 0.06 1.27\n", ""),
        "missing": text.replace("C:\n  0: 0.06 1.27\n", ""),
        "invalid": text.replace("1.27", "1.23"),
        "mismatch": text + "A:\n  0: 0 2 99\n",
        "sparse": text.replace("0: 0.06 1.27", "2: 0.06 -987.987 1.27"),
    }.get(variant, text)
    path = write_export(text)
    result = import_medpc_file(path)
    bad = tmp_path / "bad.txt"
    bad.write_text("malformed")
    pending = tmp_path / "pending.txt"
    results = {path: result, bad: import_medpc_file(bad)}
    destination = export_import_results(results, [*results, pending], tmp_path, "xlsx")
    book = load_workbook(destination / "results.xlsx")
    (session,) = records(book["Sessions"])
    assert session["subject_id"] == "0007"
    assert session["duration_s"] is None
    assert session["head_entries_recorded"] is False
    for metric in result.summary.metrics:
        assert session[metric.name] == metric.value
    if variant in ("empty", "zero"):
        assert session["prl.correct_choice_count"] == 0
    if variant in ("invalid", "mismatch", "sparse", "missing"):
        assert all(session[name] is None for name in METRIC_LABELS)
    if variant == "zero":
        assert session["prl.proportion_correct"] == 0
    if variant == "empty":
        assert session["prl.proportion_correct"] is None
    assert book["Choices"].max_row == len(result.session.events) + 1
    quality = records(book["Quality"])
    inputs = {row["source_file"]: row for row in quality if row["record_type"] == "input"}
    assert inputs[str(bad)]["input_status"] == "failed"
    assert inputs[str(bad)]["error"]
    assert inputs[str(pending)]["input_status"] == "not_imported"
    for row, metric in zip(
        [r for r in quality if r["record_type"] == "metric"], result.summary.metrics, strict=True
    ):
        assert row["metric_status"] == metric.status
        assert json.loads(row["reasons_json"]) == list(metric.reasons)
    if variant == "invalid":
        assert records(book["Choices"])[1]["correct"] is None
        assert records(book["Choices"])[1]["raw_value"] == "1.23"
    book.close()


def test_large_metadata_unicode_and_line_feeds_are_lossless(write_export, tmp_path):
    path = write_export()
    result = import_medpc_file(path)
    metadata = {**result.session.metadata, "large": "😀" * 35000}
    session = replace(result.session, metadata=metadata, subject_id="x\n" * 600)
    result = replace(result, session=session)
    destination = export_import_results({path: result}, [path], tmp_path, "xlsx")
    book = load_workbook(destination / "results.xlsx")
    table = build_session_table([session], {path: result.summary})
    for index, name in enumerate(table.columns, 1):
        if name in ("subject_id", "metadata_json"):
            cell = book["Sessions"].cell(2, index)
            assert cell.value.startswith("[Full text: Provenance rows")
            assert restored_cell(book, "Sessions", cell.coordinate) == table.iloc[0][name]
    assert all(
        len(str(cell.value or "").encode("utf-16-le")) // 2 <= 32767
        and str(cell.value or "").count("\n") <= 253
        for sheet in book
        for row in sheet
        for cell in row
    )
    book.close()


def test_repeated_exports_and_write_failures_preserve_previous(write_export, tmp_path, monkeypatch):
    path = write_export()
    results = {path: import_medpc_file(path)}
    first = export_import_results(results, [path], tmp_path, "xlsx")
    before = {p.name: p.read_bytes() for p in first.iterdir()}
    second = export_import_results(results, [path], tmp_path, "xlsx")
    assert first != second
    real_save = Workbook.save

    def broken_save(self, stream):
        stream.write(b"partial workbook")
        raise OSError("Synthetic disk full")

    monkeypatch.setattr(Workbook, "save", broken_save)
    with pytest.raises(OSError, match="disk full"):
        export_import_results(results, [path], tmp_path, "xlsx")
    assert set(tmp_path.glob("trial-cruncher-export-*")) == {first, second}
    assert {p.name: p.read_bytes() for p in first.iterdir()} == before
    monkeypatch.setattr(Workbook, "save", real_save)
    real_open = Path.open

    def broken_manifest(self, *args, **kwargs):
        if self.name == "manifest.json" and args[0] == "x":
            raise OSError("Synthetic manifest failure")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken_manifest)
    with pytest.raises(OSError, match="manifest failure"):
        export_import_results(results, [path], tmp_path, "xlsx")
    assert set(tmp_path.glob("trial-cruncher-export-*")) == {first, second}


def test_save_refuses_sources_existing_files_and_links(tmp_path):
    book = Workbook()
    source = tmp_path / "source.txt"
    source.write_bytes(b"original")
    absent = tmp_path / "deleted.txt"
    for path in (source, absent):
        with pytest.raises(ValueError, match="input file"):
            save_workbook(book, path, [path])
    alias, dangling, hardlink = (tmp_path / name for name in ("alias", "dangling", "hard"))
    alias.symlink_to(source)
    dangling.symlink_to(absent)
    hardlink.hardlink_to(source)
    for path in (source, alias, dangling, hardlink):
        with pytest.raises(FileExistsError):
            save_workbook(book, path)
    assert source.read_bytes() == b"original"
    assert dangling.is_symlink()
    assert not absent.exists()


@pytest.mark.parametrize(
    "problem", ["rows", "columns", "provenance", "xml", "nonfinite", "summary"]
)
def test_validation_fails_without_creating_output(write_export, tmp_path, monkeypatch, problem):
    path = write_export()
    result = import_medpc_file(path)
    if problem == "rows":
        monkeypatch.setattr(excel, "MAX_ROWS", 4)
    elif problem == "columns":
        monkeypatch.setattr(excel, "MAX_COLUMNS", 2)
    elif problem == "provenance":
        monkeypatch.setattr(excel, "MAX_ROWS", 8)
        monkeypatch.setattr(excel, "TEXT_UNITS", 1000)
        result = replace(result, session=replace(result.session, subject_id="a" * 20000))
    elif problem == "xml":
        result = replace(result, session=replace(result.session, subject_id="abc\x01"))
    elif problem == "nonfinite":
        result = replace(result, session=replace(result.session, duration_s=float("inf")))
    else:
        result = replace(result, summary=None)
    with pytest.raises(ValueError):
        export_import_results({path: result}, [path], tmp_path, "xlsx")
    assert not list(tmp_path.glob("trial-cruncher-export-*"))


def test_large_integer_and_decimal_precision(tmp_path):
    book = Workbook()
    table = pd.DataFrame(
        {
            "value": [
                12345678901234567,
                Decimal("1.23456789012345678900"),
                0,
                False,
                None,
                "-1+1",
                "#REF!",
            ]
        },
        dtype=object,
    )
    excel._write_table(book.active, table, [])
    path = save_workbook(book, tmp_path / "precision.xlsx")
    loaded = load_workbook(path)
    assert [row[0] for row in list(loaded.active.values)[1:]] == [
        "12345678901234567",
        "1.23456789012345678900",
        0,
        False,
        None,
        "-1+1",
        "#REF!",
    ]
    assert loaded.active["A8"].data_type == "s"
    loaded.close()


def test_competing_excel_writers_do_not_replace_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)
    destination = tmp_path / "shared.xlsx"

    def write(value):
        book = Workbook()
        book.active["A1"] = value
        barrier.wait(timeout=5)
        try:
            save_workbook(book, destination)
        except FileExistsError:
            return None
        finally:
            book.close()
        return value

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, ("first", "second")))
    (winner,) = [value for value in outcomes if value is not None]
    book = load_workbook(destination)
    assert book.active["A1"].value == winner
    book.close()


def test_no_successes_or_invalid_format_create_no_output(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        export_import_results({}, [], tmp_path, "xlsx")
    with pytest.raises(ValueError, match="format"):
        export_import_results({}, [], tmp_path, "unknown")
    assert not list(tmp_path.iterdir())
