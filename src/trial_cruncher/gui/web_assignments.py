"""Assignment editor transactions over the current batch of discovered source IDs."""

from dataclasses import asdict
from pathlib import Path

from trial_cruncher.analysis_metadata import AnalysisMetadata, analysis_metadata_from_dict
from trial_cruncher.gui.window import MainWindow


def assignment_page(window: MainWindow, offset: int, limit: int) -> dict:
    if offset < 0 or not 1 <= limit <= 250:
        raise ValueError("Invalid assignment page.")
    # The overview model contains the entire batch in stable path order.
    rows = window.overview.model.rows
    return {
        "total": len(rows),
        "rows": [
            {
                "id": str(row.path),
                "phase": window.phase_assignments.get(row.path, ""),
                "metadata": asdict(window.metadata_assignments.get(row.path, AnalysisMetadata())),
            }
            for row in rows[offset : offset + limit]
        ],
    }


def save_assignments(window: MainWindow, payload: dict) -> None:
    """Validate all edits, including their original values, before applying any."""
    if window._is_working() or window._closing:
        raise ValueError("Wait for the current operation to finish.")
    if not isinstance(payload, dict) or set(payload) != {"kind", "changes"}:
        raise ValueError("Invalid assignment request.")
    kind, changes = payload["kind"], payload["changes"]
    if kind not in ("phase", "metadata") or not isinstance(changes, list):
        raise ValueError("Invalid assignment fields.")
    phases = window.phase_assignments.copy()
    metadata = window.metadata_assignments.copy()
    seen = set()
    for item in changes:
        if not isinstance(item, dict) or set(item) != {"id", "before", "value"}:
            raise ValueError("Invalid assignment row.")
        if not isinstance(item["id"], str):
            raise ValueError("Invalid source identifier.")
        path = Path(item["id"])
        if path not in window.selected_files or path in seen:
            raise ValueError("Recording selection changed. Reopen the editor.")
        seen.add(path)
        if kind == "phase":
            if phases.get(path, "") != item["before"] or not isinstance(item["value"], str):
                raise ValueError(f"Phase assignment changed or is invalid for {path}.")
            label = item["value"].strip()
            if label:
                phases[path] = label
            else:
                phases.pop(path, None)
        else:
            current = metadata.get(path, AnalysisMetadata())
            if analysis_metadata_from_dict(item["before"]) != current:
                raise ValueError(f"Metadata changed for {path}. Reopen the editor.")
            try:
                value = analysis_metadata_from_dict(item["value"])
            except ValueError as exc:
                raise ValueError(f"{path}: {exc}") from exc
            if value.is_assigned:
                metadata[path] = value
            else:
                metadata.pop(path, None)
    if changes:
        if kind == "phase":
            window.apply_phase_assignments(phases)
        else:
            window.apply_metadata_assignments(metadata)
