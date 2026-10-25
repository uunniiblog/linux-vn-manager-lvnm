import re
from datetime import datetime
from PySide6.QtCore import QDateTime, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout, 
    QHeaderView, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox, 
    QPushButton, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)
from game_process_manager import GameProcessManager
from ui.bounded_combo_box import BoundedComboBox

class TrackingEntriesTab(QWidget):
    COLUMNS = ("Timestamp_Start", "Timestamp_End", "Duration", "ActiveTime", "App", "Title", "Status", "Tags")

    def __init__(self, log_manager, on_changed, parent=None, process_manager=None):
        super().__init__(parent)
        self.log_manager = log_manager
        self.on_changed = on_changed
        self.process_manager = process_manager or GameProcessManager.get_instance()
        self.process_manager.game_started.connect(self._update_mutation_state)
        self.process_manager.game_stopped.connect(self._update_mutation_state)

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.app_combo = BoundedComboBox(max_height_ratio=0.7)
        self._last_app = None
        self._loaded_app = None
        self._dirty = False
        self.app_combo.currentIndexChanged.connect(self._app_changed)
        self.app_combo.activated.connect(self._app_activated)
        controls.addWidget(self.app_combo, 1)
        self.refresh_btn = QPushButton(self.tr("Refresh"))
        self.refresh_btn.clicked.connect(self.refresh_apps)
        controls.addWidget(self.refresh_btn)
        layout.addLayout(controls)

        self.column_labels = [
            self.tr("Start"), self.tr("End"), self.tr("Duration"), self.tr("Active Time"),
            self.tr("App"), self.tr("Title"), self.tr("Status"), self.tr("Tags")
        ]
        self.entries_scroll = QScrollArea()
        self.entries_scroll.setWidgetResizable(True)
        self.entries_content = QWidget()
        self.entries_layout = QVBoxLayout(self.entries_content)
        self.entries_layout.setContentsMargins(8, 8, 8, 8)
        self.entries_layout.setSpacing(18)
        self.entries_scroll.setWidget(self.entries_content)
        self.day_tables = []
        self._selected_table = None
        layout.addWidget(self.entries_scroll, 1)

        actions = QHBoxLayout()
        self.add_btn = QPushButton(self.tr("Add Entry"))
        self.delete_btn = QPushButton(self.tr("Delete Selected"))
        self.delete_log_btn = QPushButton(self.tr("Delete Log File"))
        self.save_btn = QPushButton(self.tr("Save"))
        self.save_btn.setMinimumWidth(140)
        self.save_btn.setStyleSheet("""
            QPushButton:enabled {
                background-color: #2e7d32;
                border: 1px solid #43a047;
                color: white;
                font-weight: bold;
            }
            QPushButton:enabled:hover { background-color: #388e3c; }
            QPushButton:enabled:pressed { background-color: #1b5e20; }
        """)
        self.delete_btn.setEnabled(False)
        self.delete_log_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.add_btn.clicked.connect(self.add_entry)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.delete_log_btn.clicked.connect(self.delete_log_file)
        self.save_btn.clicked.connect(self.save_changes)
        actions.addWidget(self.add_btn)
        actions.addWidget(self.delete_btn)
        actions.addWidget(self.delete_log_btn)
        actions.addStretch()
        actions.addWidget(self.save_btn)
        layout.addLayout(actions)
        self._update_mutation_state()

    def _games_running(self):
        return bool(self.process_manager.active_runners)

    def _update_mutation_state(self, _name=None):
        editable = not self._games_running()
        self.add_btn.setEnabled(editable)
        self.delete_btn.setEnabled(editable and self._selected_entry() is not None)
        app = self.selected_app()
        self.delete_log_btn.setEnabled(editable and bool(app and self.log_manager.get_app_file(app).is_file()))
        self.save_btn.setEnabled(editable and self._dirty)
        edit_triggers = QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed
        for table in self.day_tables:
            table.setEditTriggers(edit_triggers if editable else QAbstractItemView.NoEditTriggers)
        explanation = self.tr("Stop all running games to change tracking entries.") if not editable else ""
        for button in (self.add_btn, self.delete_btn, self.delete_log_btn, self.save_btn):
            button.setToolTip(explanation)

    def selected_app(self):
        return self.app_combo.currentData()

    def _app_activated(self, index):
        if self.app_combo.itemData(index) is not None:
            return
        app = self._choose_new_app()
        if app is None and self._last_app is not None:
            previous_index = self.app_combo.findData(self._last_app)
            if previous_index >= 0:
                self.app_combo.setCurrentIndex(previous_index)

    def _choose_new_app(self):
        app, accepted = QInputDialog.getText(self, self.tr("New App"), self.tr("App name:"))
        if not accepted:
            return None
        app = app.strip()
        if not app or any(character in app for character in ";\r\n"):
            QMessageBox.warning(self, self.tr("Invalid Game"), self.tr("Enter an app name without semicolons or line breaks."))
            return None
        index = self.app_combo.findData(app)
        if index < 0:
            index = self.app_combo.count() - 1
            self.app_combo.insertItem(index, app, app)
        self.app_combo.setCurrentIndex(index)
        return app

    def refresh_apps(self):
        if not self._resolve_pending_changes():
            return
        selected = self.selected_app()
        tracked = set(self.log_manager.get_all_tracked_apps())
        labels = self.log_manager.get_apps_sorted_by_latest()
        self.app_combo.blockSignals(True)
        self.app_combo.clear()
        seen = set()
        for label in labels:
            app = self.log_manager._extract_process(label)
            if app in tracked and app not in seen:
                self.app_combo.addItem(label, app)
                seen.add(app)
        for app in sorted(tracked - seen, key=str.casefold):
            self.app_combo.addItem(app, app)

        if selected and self.app_combo.findData(selected) < 0:
            self.app_combo.addItem(selected, selected)
        self.app_combo.addItem(self.tr("New app..."), None)
        index = self.app_combo.findData(selected) if selected else (0 if tracked else -1)
        if index >= 0:
            self.app_combo.setCurrentIndex(index)
        self.app_combo.blockSignals(False)
        self.refresh_entries()

    def refresh_entries(self):
        self._clear_entries()
        app = self.selected_app()
        self._loaded_app = app
        self._dirty = False
        self.save_btn.setEnabled(False)
        self._update_mutation_state()
        if not app:
            self._update_delete_button()
            return
        self._last_app = app
        try:
            sessions = self.log_manager.get_sessions(app)
        except RuntimeError as error:
            QMessageBox.critical(self, self.tr("Tracking Error"), str(error))
            return

        groups = {}
        for row_index, row in sorted(enumerate(sessions), key=lambda entry: entry[1].get("Timestamp_Start") or "", reverse=True):
            day = (row.get("Timestamp_Start") or "").split(" ")[0] or self.tr("Unknown date")
            groups.setdefault(day, []).append((row_index, row))
        for day, entries in groups.items():
            self._add_day_table(day, entries)
        self.entries_content.setMinimumWidth(max((table.minimumWidth() for table in self.day_tables), default=0) + 16)
        self.entries_layout.addStretch()
        self._update_delete_button()

    def _clear_entries(self):
        self.day_tables = []
        self._selected_table = None
        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

    def _add_day_table(self, day, entries):
        section = QWidget()
        section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(6)
        heading = QLabel(f"📅 {day}")
        heading.setStyleSheet("font-weight: bold; color: #3498db;")
        section_layout.addWidget(heading)

        table = QTableWidget(len(entries), len(self.COLUMNS))
        table.setHorizontalHeaderLabels(self.column_labels)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda position, table=table: self._show_entry_context_menu(table, position))
        edit_triggers = QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed
        table.setEditTriggers(edit_triggers if not self._games_running() else QAbstractItemView.NoEditTriggers)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        for table_row, (row_index, row) in enumerate(entries):
            for column, key in enumerate(self.COLUMNS):
                item = QTableWidgetItem(row.get(key) or "")
                if column == 0:
                    item.setData(Qt.UserRole, (row_index, row))
                if key == "App":
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(table_row, column, item)
        table.resizeColumnsToContents()
        table.resizeRowsToContents()
        table.setMinimumWidth(table.verticalHeader().width() + sum(table.columnWidth(column) for column in range(table.columnCount())) + 8)
        table.setFixedHeight(table.horizontalHeader().height() + sum(table.rowHeight(row) for row in range(table.rowCount())) + 8)
        table.itemSelectionChanged.connect(lambda table=table: self._table_selection_changed(table))
        table.itemChanged.connect(self._entry_changed)
        section_layout.addWidget(table)
        self.entries_layout.addWidget(section)
        self.day_tables.append(table)

    def _table_selection_changed(self, table):
        if table.selectedItems():
            self._selected_table = table
            for other in self.day_tables:
                if other is not table:
                    other.blockSignals(True)
                    other.clearSelection()
                    other.blockSignals(False)
        elif self._selected_table is table:
            self._selected_table = None
        self._update_delete_button()

    def _show_entry_context_menu(self, table, position):
        if self._games_running():
            return
        item = table.itemAt(position)
        if item is None:
            return
        table.selectRow(item.row())
        menu = QMenu(table)
        delete_action = menu.addAction(self.tr("Delete Entry"))
        if menu.exec(table.viewport().mapToGlobal(position)) == delete_action:
            self.delete_selected()

    def _selected_entry(self):
        if self._selected_table is None:
            return None
        row = self._selected_table.currentRow()
        item = self._selected_table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item and self._selected_table.selectedItems() else None

    def _update_delete_button(self):
        self.delete_btn.setEnabled(not self._games_running() and self._selected_entry() is not None)

    def _app_changed(self):
        if not self._resolve_pending_changes():
            self.app_combo.blockSignals(True)
            self.app_combo.setCurrentIndex(self.app_combo.findData(self._loaded_app))
            self.app_combo.blockSignals(False)
            return
        self.refresh_entries()

    def _resolve_pending_changes(self):
        if not self._dirty:
            return True
        answer = QMessageBox.question(
            self, self.tr("Unsaved Tracking Entries"), self.tr("Save your changes to the tracking entries?"),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self.save_changes()
        self._dirty = False
        self.save_btn.setEnabled(False)
        self.refresh_entries()
        return True

    def _changed_rows(self):
        changes = []
        for table in self.day_tables:
            for table_row in range(table.rowCount()):
                row_index, original = table.item(table_row, 0).data(Qt.UserRole)
                updated = {key: table.item(table_row, column).text() for column, key in enumerate(self.COLUMNS)}
                if updated != original:
                    changes.append((row_index, original, updated))
        return changes

    def _entry_changed(self, item):
        table = item.tableWidget()
        table.resizeColumnToContents(item.column())
        table.setMinimumWidth(table.verticalHeader().width() + sum(table.columnWidth(column) for column in range(table.columnCount())) + 8)
        self.entries_content.setMinimumWidth(max((day_table.minimumWidth() for day_table in self.day_tables), default=0) + 16)
        self._dirty = bool(self._changed_rows())
        self.save_btn.setEnabled(not self._games_running() and self._dirty)

    def _validate_row(self, row):
        for label in ("Timestamp_Start", "Timestamp_End"):
            try:
                parsed = datetime.strptime(row[label], "%Y-%m-%d %H:%M:%S")
                if parsed.strftime("%Y-%m-%d %H:%M:%S") != row[label]:
                    raise ValueError
            except ValueError:
                raise ValueError(f"{label} must use YYYY-MM-DD HH:MM:SS.") from None
        start = datetime.strptime(row["Timestamp_Start"], "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(row["Timestamp_End"], "%Y-%m-%d %H:%M:%S")
        if end < start:
            raise ValueError("End time must be after start time.")
        for label in ("Duration", "ActiveTime"):
            if not re.fullmatch(r"\d+:[0-5]\d:[0-5]\d", row[label]):
                raise ValueError(f"{label} must use H:MM:SS.")
        if self.log_manager._duration_to_seconds(row["ActiveTime"]) > self.log_manager._duration_to_seconds(row["Duration"]):
            raise ValueError("Active time cannot exceed duration.")
        if any(any(character in value for character in ";\r\n") for value in row.values()):
            raise ValueError("Entries cannot contain semicolons or line breaks.")
        if row["App"] != self._loaded_app:
            raise ValueError("The app column cannot be changed in this log.")

    def save_changes(self):
        if self._games_running():
            return False
        changes = self._changed_rows()
        if not changes:
            self._dirty = False
            self.save_btn.setEnabled(False)
            return True
        try:
            for _, _, row in changes:
                self._validate_row(row)
            self.log_manager.update_sessions(self._loaded_app, changes)
        except (RuntimeError, ValueError) as error:
            QMessageBox.warning(self, self.tr("Could Not Save Entries"), str(error))
            return False
        saved_app = self._loaded_app
        scroll_position = (self.entries_scroll.horizontalScrollBar().value(), self.entries_scroll.verticalScrollBar().value())
        self._dirty = False
        self.save_btn.setEnabled(False)
        self.on_changed()
        if self.selected_app() == saved_app:
            QTimer.singleShot(0, lambda: self._restore_scroll_position(saved_app, scroll_position, 3))
        return True

    def _restore_scroll_position(self, app, position, attempts):
        if self.selected_app() != app:
            return
        horizontal = self.entries_scroll.horizontalScrollBar()
        vertical = self.entries_scroll.verticalScrollBar()
        if attempts and (horizontal.maximum() < position[0] or vertical.maximum() < position[1]):
            QTimer.singleShot(0, lambda: self._restore_scroll_position(app, position, attempts - 1))
            return
        horizontal.setValue(position[0])
        vertical.setValue(position[1])

    def add_entry(self):
        if self._games_running():
            return
        if not self._resolve_pending_changes():
            return
        app = self.selected_app() or self._choose_new_app()
        if not app:
            return
        label = self.app_combo.currentText()
        title = label.rsplit(" - ", 1)[0] if " - " in label and label != app else app
        dialog = AddTrackingSessionDialog(app, title, self.log_manager, self)
        if dialog.exec() != QDialog.Accepted:
            return
        if self._games_running():
            return
        if self.log_manager.save_session(dialog.session_data) is None:
            QMessageBox.critical(self, self.tr("Tracking Error"), self.tr("Could not save the tracking entry."))
            return
        self.on_changed()

    def delete_selected(self):
        if self._games_running():
            return
        selection = self._selected_entry()
        if selection is None:
            return
        if not self._resolve_pending_changes():
            return
        if self._selected_entry() is None:
            row_index = selection[0]
            try:
                selection = (row_index, self.log_manager.get_sessions(self.selected_app())[row_index])
            except (RuntimeError, IndexError):
                QMessageBox.warning(self, self.tr("Tracking Error"), self.tr("The selected entry changed. Refresh the list and try again."))
                return
        answer = QMessageBox.question(
            self, self.tr("Delete Tracking Entry"), self.tr("Delete this tracking entry?"), QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return
        if self._games_running():
            return
        try:
            row_index, row = selection
            self.log_manager.delete_session(self.selected_app(), row_index, row)
        except (RuntimeError, ValueError) as error:
            QMessageBox.critical(self, self.tr("Tracking Error"), str(error))
            return
        self.on_changed()

    def delete_log_file(self):
        if self._games_running():
            return
        app = self.selected_app()
        log_file = self.log_manager.get_app_file(app) if app else None
        if log_file is None or not log_file.is_file():
            self.delete_log_btn.setEnabled(False)
            return
        answer = QMessageBox.question(
            self, self.tr("Delete Tracking Log"),
            f"{self.tr('Delete the entire log file and all its entries?')}\n{log_file.name}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if answer != QMessageBox.Yes or not self._resolve_pending_changes():
            return
        if self._games_running():
            return
        try:
            self.log_manager.delete_log_file(app)
        except (RuntimeError, ValueError) as error:
            QMessageBox.critical(self, self.tr("Tracking Error"), str(error))
            return
        self._last_app = None
        self.app_combo.blockSignals(True)
        self.app_combo.setCurrentIndex(-1)
        self.app_combo.blockSignals(False)
        self.on_changed()

class AddTrackingSessionDialog(QDialog):
    def __init__(self, app_name, title, log_manager, parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.log_manager = log_manager
        self.session_data = None
        self.setWindowTitle(self.tr("Add Tracking Entry"))

        layout = QVBoxLayout(self)
        form = QFormLayout()
        now = QDateTime.currentDateTime()
        self.start_edit = QDateTimeEdit(now.addSecs(-3600))
        self.end_edit = QDateTimeEdit(now)
        for edit in (self.start_edit, self.end_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.active_edit = QLineEdit("1:00:00")
        self.active_edit.setPlaceholderText(self.tr("Hours:minutes:seconds"))
        self.title_edit = QLineEdit(title)
        self.tags_edit = QLineEdit()
        form.addRow(self.tr("Start:"), self.start_edit)
        form.addRow(self.tr("End:"), self.end_edit)
        form.addRow(self.tr("Active time:"), self.active_edit)
        form.addRow(self.tr("Title:"), self.title_edit)
        form.addRow(self.tr("Tags:"), self.tags_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        start = self.start_edit.dateTime().toPython()
        end = self.end_edit.dateTime().toPython()
        duration = int((end - start).total_seconds())
        active_text = self.active_edit.text().strip()
        if duration < 0 or not re.fullmatch(r"\d+:[0-5]\d:[0-5]\d", active_text):
            QMessageBox.warning(self, self.tr("Invalid Entry"), self.tr("Choose a valid time range and enter active time as H:MM:SS."))
            return

        active_seconds = self.log_manager._duration_to_seconds(active_text)
        if active_seconds > duration:
            QMessageBox.warning(self, self.tr("Invalid Entry"), self.tr("Active time cannot exceed the time between start and end."))
            return

        title = self.title_edit.text().strip() or self.app_name
        tags = self.tags_edit.text().strip()
        if any(character in value for value in (title, tags) for character in ";\r\n"):
            QMessageBox.warning(self, self.tr("Invalid Entry"), self.tr("Title and tags cannot contain semicolons or line breaks."))
            return

        self.session_data = {
            "start": start, "end": end, "duration": duration, "active_time": active_seconds,
            "app": self.app_name, "title": title, "status": "Manual", "tags": tags
        }
        super().accept()