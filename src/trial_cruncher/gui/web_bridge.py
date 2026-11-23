"""Restricted WebChannel facade over the desktop workflow controller."""

import json
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from trial_cruncher.analysis_sort import SHEETS, validate_analysis_sorts
from trial_cruncher.gui import preferences, web_animal, web_assignments, web_data
from trial_cruncher.gui.window import MainWindow


class WebBridge(QObject):
    changed = Signal()

    def __init__(self, controller: MainWindow, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.window = controller
        self._native_action_open = False
        self._settings = preferences.workspace_settings()
        self._batch_revision = 0
        self._detail_revision = 0
        self._message_revision = 0
        controller.review_changed.connect(self._detail_changed)
        self._notify_timer = QTimer(self)
        self._notify_timer.setSingleShot(True)
        self._notify_timer.setInterval(40)
        self._notify_timer.timeout.connect(self.changed)
        for signal in (
            controller.statusBar().messageChanged,
            controller.progress.valueChanged,
            controller.workflow.currentChanged,
            controller.review.tabs.currentChanged,
        ):
            signal.connect(self._notify)
        for signal in (
            controller.overview.model.dataChanged,
            controller.overview.model.modelReset,
            controller.overview.table.selectionModel().currentChanged,
            controller.phase_overview.table.selectionModel().currentChanged,
        ):
            signal.connect(self._batch_changed)
        messages = controller.issue_list.model()
        for signal in (messages.rowsInserted, messages.rowsRemoved, messages.modelReset):
            signal.connect(self._messages_changed)
        for proxy in (controller.overview.proxy, controller.phase_overview.proxy):
            for signal in (
                proxy.layoutChanged,
                proxy.modelReset,
                proxy.rowsInserted,
                proxy.rowsRemoved,
            ):
                signal.connect(self._batch_changed)

    def _messages_changed(self, *args):
        self._message_revision += 1
        self._notify()

    def _batch_changed(self, *args):
        self._batch_revision += 1
        self._notify()

    def _detail_changed(self):
        self._detail_revision += 1
        self._notify()

    def _notify(self, *args):
        # Throttle updates: continuous per-file progress must still reach the renderer.
        if not self._notify_timer.isActive():
            self._notify_timer.start()

    def _buttons(self):
        w = self.window
        return {
            "choose_files": w.add_files_button,
            "choose_folder": w.add_folder_button,
            "clear": w.clear_button,
            "import": w.import_button,
            "assign_phases": w.phase_button,
            "assign_metadata": w.metadata_button,
            "animal_analysis": w.analysis_button,
            "export_csv": w.export_button,
            "export_excel": w.excel_button,
            "export_detailed_csv": w.export_button,
            "export_detailed_excel": w.excel_button,
            "open_project": w.open_project_button,
            "save_project": w.save_project_button,
            "save_project_as": w.save_project_as_button,
            "check_sources": w.check_sources_button,
            "cancel": w.cancel_button,
        }

    @Slot(result=str)
    def state(self) -> str:
        w = self.window

        def options(combo, data=True):
            return [
                {
                    "label": combo.itemText(i),
                    "value": combo.itemData(i) if data else combo.itemText(i),
                }
                for i in range(combo.count())
            ]

        return json.dumps(
            {
                "batch_revision": self._batch_revision,
                "detail_revision": self._detail_revision,
                "busy": w._is_working(),
                "has_files": bool(w.selected_files),
                "has_results": bool(w.import_results),
                "can_cancel": w._import_worker is not None,
                "enabled": {name: widget.isEnabled() for name, widget in self._buttons().items()},
                "status": w.statusBar().currentMessage(),
                "export_status": w.export_status.text(),
                "default_export_folder": w.default_export_folder_name(),
                "project": w.project_label.text(),
                "progress": {
                    "visible": not w.progress.isHidden(),
                    "value": w.progress.value(),
                    "maximum": w.progress.maximum(),
                },
                "message_revision": self._message_revision,
                "message_count": w.issue_list.count(),
                "extensions": w.extensions.text(),
                "recursive": w.recursive.isChecked(),
                "workflow": w.workflow.tabText(w.workflow.currentIndex()).lower(),
                "ui_preferences": {
                    "mode": self._settings.value("workspace/mode", "batch"),
                    "split": self._settings.value("workspace/split", 0.34, type=float),
                },
                "inspector_tab": (
                    w.review.tabs.tabText(w.review.tabs.currentIndex())
                    if w._active_batch() is w.phase_overview
                    else None
                ),
                "filter_values": {
                    "sessions": {
                        "search": w.overview.search.text(),
                        "program": w.overview.program.currentData(),
                        "quality": w.overview.quality.currentText(),
                    },
                    "phase": {
                        "search": w.phase_overview.search.text(),
                        "phase": w.phase_overview.phase_filter.currentData(),
                        "status": w.phase_overview.status_filter.currentText(),
                        "condition": w.phase_overview.condition_filter.currentData(),
                        "inclusion": w.phase_overview.inclusion_filter.currentData(),
                        "layout": w.phase_overview.column_view.currentText(),
                    },
                },
                "filters": {
                    "program": options(w.overview.program),
                    "quality": options(w.overview.quality, False),
                    "phase": options(w.phase_overview.phase_filter),
                    "status": options(w.phase_overview.status_filter, False),
                    "condition": options(w.phase_overview.condition_filter),
                    "inclusion": options(w.phase_overview.inclusion_filter),
                    "layout": options(w.phase_overview.column_view, False),
                },
            },
            ensure_ascii=False,
        )

    @Slot(int, int, result=str)
    def messages(self, offset: int, limit: int) -> str:
        if offset < 0 or not 1 <= limit <= 250:
            return json.dumps({"error": "Invalid message page."})
        issues = self.window.issue_list
        return json.dumps(
            {
                "rows": [
                    issues.item(i).text()
                    for i in range(offset, min(offset + limit, issues.count()))
                ],
                "total": issues.count(),
            },
            ensure_ascii=False,
        )

    @Slot(str, int, int, result=str)
    def batch(self, view: str, offset: int, limit: int) -> str:
        try:
            return json.dumps(web_data.batch(self.window, view, offset, limit), ensure_ascii=False)
        except (ValueError, TypeError, KeyError) as exc:
            return json.dumps({"error": str(exc)})

    @Slot(str, str, int, result=str)
    def batchTooltip(self, view: str, path: str, column: int) -> str:
        try:
            return web_data.batch_tooltip(self.window, view, path, column)
        except (ValueError, TypeError, KeyError):
            return ""

    @Slot(str, int, int, result=str)
    def detailSection(self, section: str, offset: int, limit: int) -> str:
        try:
            return json.dumps(
                web_data.detail_section(self.window, section, offset, limit), ensure_ascii=False
            )
        except (ValueError, TypeError, KeyError) as exc:
            return json.dumps({"error": str(exc)})

    @Slot(result=str)
    def animalConfig(self) -> str:
        return json.dumps(web_animal.configuration(self.window), ensure_ascii=False)

    @Slot(str, result=str)
    def animalApply(self, payload: str) -> str:
        try:
            web_animal.apply(self.window, json.loads(payload))
            self._notify()
            return json.dumps({"ok": True})
        except (ValueError, TypeError, KeyError) as exc:
            return json.dumps({"error": str(exc)})

    @Slot(result=str)
    def animalDismiss(self) -> str:
        self.window.invalidate_animal_preview()
        return json.dumps({"ok": True})

    @Slot(str, str, result=str)
    def animalSort(self, table: str, payload: str) -> str:
        try:
            rules = validate_analysis_sorts({table: json.loads(payload)})[table]
            tables = self.window._web_analysis_tables
            if self.window._is_working() or not tables or table not in tables:
                raise ValueError("Analysis results are unavailable.")
            allowed = set(tables[table].columns)
            if table == "analysis_audit.csv":
                allowed.add("recording_proportion_correct")
            # A saved condition/phase column can temporarily leave the scope.
            allowed.update(rule["column"] for rule in self.window.analysis_sorts.get(table, []))
            if any(rule["column"] not in allowed for rule in rules):
                raise ValueError("Sort column is unavailable.")
            if self.window.analysis_sorts.get(table) != rules:
                self.window.analysis_sorts[table] = rules
                self.window._mark_project_dirty()
            return json.dumps({"ok": True})
        except (ValueError, TypeError, KeyError) as exc:
            return json.dumps({"error": str(exc)})

    @Slot(str, result=str)
    def animalResetSort(self, table: str) -> str:
        if table not in SHEETS or self.window._is_working():
            return json.dumps({"error": "Sorting is unavailable."})
        if table in self.window.analysis_sorts:
            del self.window.analysis_sorts[table]
            self.window._mark_project_dirty()
        return json.dumps({"ok": True})

    @Slot(str, int, int, result=str)
    def animalPage(self, table: str, offset: int, limit: int) -> str:
        try:
            return json.dumps(
                web_animal.page(self.window, table, offset, limit), ensure_ascii=False
            )
        except (ValueError, TypeError, KeyError) as exc:
            return json.dumps({"error": str(exc)})

    @Slot(int, int, result=str)
    def assignmentPage(self, offset: int, limit: int) -> str:
        try:
            return json.dumps(
                web_assignments.assignment_page(self.window, offset, limit), ensure_ascii=False
            )
        except ValueError as exc:
            return json.dumps({"error": str(exc)})

    @Slot(str, result=str)
    def saveAssignments(self, payload: str) -> str:
        try:
            web_assignments.save_assignments(self.window, json.loads(payload))
            self._batch_changed()
            return json.dumps({"ok": True})
        except (ValueError, TypeError, KeyError) as exc:
            return json.dumps({"error": str(exc)})

    @Slot(str, str, result=str)
    def action(self, name: str, payload: str) -> str:
        w = self.window
        actions = {
            "choose_files": w.choose_files,
            "choose_folder": w.choose_folder,
            "import": w.import_selected_files,
            "cancel": w.cancel_import,
            "export_csv": w.export_data_csv,
            "export_excel": w.export_data_excel,
            "export_detailed_csv": w.export_csv,
            "export_detailed_excel": w.export_excel,
            "open_project": w.open_project,
            "save_project": w.save_project,
            "save_project_as": w.save_project_as,
            "check_sources": w.check_source_files,
            "clear": w.clear_selection,
        }
        try:
            if len(payload) > 65536:
                raise ValueError("Action arguments are too large.")
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError("Invalid action arguments.")
            if name in actions:
                is_export = name.startswith("export_")
                if (
                    (data and (not is_export or set(data) != {"folder_name"}))
                    or self._native_action_open
                    or not self._buttons()[name].isEnabled()
                ):
                    raise ValueError("Action is unavailable while the current operation is active.")
                # Native pickers may enter a nested Qt event loop.
                self._native_action_open = True
                try:
                    actions[name](**data)
                finally:
                    self._native_action_open = False
            elif name in ("options", "set_options"):
                if w._is_working():
                    raise ValueError("Wait for the current operation to finish.")
                if set(data) - {"extensions", "recursive"}:
                    raise ValueError("Invalid file options.")
                if "extensions" in data and (
                    not isinstance(data["extensions"], str) or len(data["extensions"]) > 1024
                ):
                    raise ValueError("Invalid file extensions.")
                if "recursive" in data and type(data["recursive"]) is not bool:
                    raise ValueError("Invalid subfolder option.")
                if "extensions" in data:
                    w.extensions.setText(data["extensions"])
                if "recursive" in data:
                    w.recursive.setChecked(data["recursive"])
            elif name == "set_workflow":
                workflow = data.get("workflow")
                choices = ("import", "review", "export", "project")
                if workflow not in choices:
                    raise ValueError("Invalid workflow.")
                w.workflow.setCurrentIndex(choices.index(workflow))
            elif name == "set_preferences":
                settings = self._settings
                if "mode" in data:
                    if data["mode"] not in ("split", "batch", "detail"):
                        raise ValueError("Invalid workspace mode.")
                    settings.setValue("workspace/mode", data["mode"])
                if "split" in data:
                    split = data["split"]
                    if (
                        isinstance(split, bool)
                        or not isinstance(split, (int, float))
                        or not 0.15 <= split <= 0.85
                    ):
                        raise ValueError("Invalid workspace split.")
                    settings.setValue("workspace/split", split)
            elif name == "batch_view":
                if data.get("view") not in ("sessions", "data", "phase", "phases"):
                    raise ValueError("Invalid batch view.")
                w.batch_tabs.setCurrentIndex(1 if data.get("view") in ("phase", "phases") else 0)
            elif name == "select":
                if not isinstance(data.get("path"), str):
                    raise ValueError("Invalid file selection.")
                path = Path(data["path"])
                if path not in w.selected_files:
                    raise ValueError("File is not in the current selection.")
                w._active_batch().select_path(path)
            elif name == "sort":
                if data.get("view") not in ("sessions", "data", "phase", "phases"):
                    raise ValueError("Invalid batch view.")
                if type(data.get("column")) is not int or type(data.get("descending")) is not bool:
                    raise ValueError("Invalid sort.")
                view = w.phase_overview if data.get("view") in ("phase", "phases") else w.overview
                column = data["column"]
                if data.get("view") == "data":
                    from trial_cruncher.compact_results import DATA_COLUMNS

                    if not 0 <= column < len(DATA_COLUMNS) + 2:
                        raise ValueError("Invalid sort column.")
                    w._compact_sort = (column, data["descending"])
                    self._batch_changed()
                    return json.dumps({"ok": True})
                if not 0 <= column < view.model.columnCount():
                    raise ValueError("Invalid sort column.")
                order = (
                    Qt.SortOrder.DescendingOrder
                    if data.get("descending")
                    else Qt.SortOrder.AscendingOrder
                )
                view.table.sortByColumn(column, order)
            elif name in ("filter", "reset_filters"):
                if data.get("view") not in ("sessions", "data", "phase", "phases"):
                    raise ValueError("Invalid batch view.")
                if set(data) - {
                    "view",
                    "search",
                    "program",
                    "quality",
                    "status",
                    "phase",
                    "condition",
                    "inclusion",
                    "layout",
                }:
                    raise ValueError("Invalid filter.")
                if "search" in data and (
                    not isinstance(data["search"], str) or len(data["search"]) > 4096
                ):
                    raise ValueError("Invalid search.")
                view = w.phase_overview if data.get("view") in ("phase", "phases") else w.overview
                if name == "reset_filters":
                    view.clear_filters()
                else:
                    self._filter(view, data)
            else:
                raise ValueError("Unknown action.")
            if name in ("batch_view", "sort", "reset_filters", "filter"):
                self._batch_changed()
            self._notify()
            return json.dumps({"ok": True})
        except (ValueError, TypeError, KeyError) as exc:
            return json.dumps({"error": str(exc)})

    def _filter(self, view, data):
        options = (
            {
                "program": (view.program, True),
                "quality": (view.quality, False),
            }
            if view is self.window.overview
            else {
                "status": (view.status_filter, False),
                "phase": (view.phase_filter, True),
                "condition": (view.condition_filter, True),
                "inclusion": (view.inclusion_filter, True),
                "layout": (view.column_view, False),
            }
        )
        updates = []
        for key in data.keys() - {"view", "search"}:
            if key not in options:
                raise ValueError("Unknown filter for this view.")
            combo, by_value = options[key]
            value = data[key]
            if value is not None and not isinstance(value, str):
                raise ValueError("Invalid filter value.")
            index = combo.findData(value) if by_value else combo.findText(value or "")
            if index < 0:
                raise ValueError("Filter selection is no longer available.")
            updates.append((combo, index))
        if "search" in data:
            view.search.setText(data["search"])
        for combo, index in updates:
            combo.setCurrentIndex(index)
