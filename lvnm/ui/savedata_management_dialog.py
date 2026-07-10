import logging
import config
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton,
    QDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy,
    QWidget, QLineEdit, QLabel, QFileDialog, QComboBox,
    QMessageBox, QCheckBox, QStyle, QDialogButtonBox
)
from PySide6.QtCore import QSettings, Qt, QObject, QEvent
from settings_manager import SettingsManager
from game_manager import GameManager
from prefix_manager import PrefixManager
from savedata_manager import SavedataManager
from pregame_sync_pipeline import ManualSyncPipeline, SavedataSyncStep, TrackingSyncStep

logger = logging.getLogger(__name__)

class SavedataManagementDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manage Savedata files"))
        self.resize(600, 400)

        self._pending_pipeline = None

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

        layout = QVBoxLayout(self)
        self.info_label = QLabel(self.tr("When adding the savedata path add the furthermost path that contains the actual save files. If the savedata is inside the same prefix as the game you can also copy the save files to another prefixes."))
        self.info_label2 = QLabel(self.tr("Enable Gdrive sync individually per game case where you need it. If changing prefix of a game or savedata folder with gdrive sync make sure first to copy the saves to the new prefix first to avoid data sync corruption."))
        self.info_label.setWordWrap(True)
        self.info_label2.setWordWrap(True)
        layout.addWidget(self.info_label)
        layout.addWidget(self.info_label2)

        layout.addSpacing(15)

        # Search Bar
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText(self.tr("Search games..."))        
        self.search_edit.setMinimumWidth(200) 
        self.search_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.search_edit.textChanged.connect(self._filter_table)
        
        search_layout.addWidget(self.search_edit)
        search_layout.addStretch()
        layout.addLayout(search_layout)

        layout.addSpacing(10)

        unsorted_games = GameManager._load_data()
        sorted_items = sorted(
            unsorted_games.items(), 
            key=lambda x: x[1].get("last_played", ""), 
            reverse=True
        )
        self.games = dict(sorted_items)

        # Table Setup
        self.table = QTableWidget(len(self.games), 4)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setMouseTracking(True)
        self.table.setHorizontalHeader(HoverHeaderView(Qt.Horizontal, self.table))

        self.table.setHorizontalHeaderLabels([
            self.tr("Game"),
            self.tr("Savedata Path"),
            self.tr("Prefix"),
            self.tr("Gdrive Sync")
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(1, 250)
        self.table.setColumnWidth(2, 150)

        self.table.setSortingEnabled(False)

        for row, (game_id, game_data) in enumerate(self.games.items()):
            # Column 0: Game name
            name_item = QTableWidgetItem(game_data.get("name", game_id))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)

            # Column 1: Savedata path (line edit + browse button)
            path_sort_item = SortableItem()
            path_sort_item.setData(Qt.UserRole, game_data.get("savedata_path", ""))
            savedata_widget = self._create_savedata_widget(row, game_data, path_sort_item)
            self.table.setCellWidget(row, 1, savedata_widget)
            self.table.setItem(row, 1, path_sort_item)

            # Column 2: Prefix (label + "Copy to..." button)
            prefix_widget = self._create_prefix_widget(row, game_data)
            self.table.setCellWidget(row, 2, prefix_widget)
            prefix_sort_item = SortableItem()
            prefix_sort_item.setData(Qt.UserRole, game_data.get("prefix", ""))
            self.table.setItem(row, 2, prefix_sort_item)
            prefix_widget.sort_item = prefix_sort_item

            # Column 3: Gdrive - left empty for now
            gdrive_sort_item = SortableItem()
            gdrive_sort_item.setData(Qt.UserRole, bool(game_data.get("gdrive", False)))
            gdrive_widget = self._create_gdrive_widget(row, game_data, gdrive_sort_item)
            self.table.setCellWidget(row, 3, gdrive_widget)
            self.table.setItem(row, 3, gdrive_sort_item)

            # Enable/disable the copy button as the path changes
            savedata_widget.line_edit.textChanged.connect(lambda text, btn=prefix_widget.copy_button: btn.setEnabled(
                    bool(text.strip()) and SavedataManager.is_savedata_inside_prefix({**game_data, "savedata_path": text.strip()})))
            # savedata_widget.line_edit.textChanged.connect(lambda text, cb=gdrive_widget.checkbox: cb.setEnabled(bool(text.strip())))

        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setSortingEnabled(True)

        layout.addWidget(self.table)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Close)
        self.button_box.rejected.connect(self.accept)
        layout.addWidget(self.button_box)

        # Restore previous window size
        self._restore_state()

    def _filter_table(self, text):
        """Filters the table rows based on the game name."""
        search_text = text.lower()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                # Hide the row if the search string is not found in the name
                is_visible = search_text in item.text().lower()
                self.table.setRowHidden(row, not is_visible)
    
    def _create_savedata_widget(self, row, game_data, path_item):
        """Creates a widget with a line edit + browse button for the savedata path."""
        widget = QWidget()
        h_layout = QHBoxLayout(widget)
        h_layout.setContentsMargins(2, 2, 2, 2)

        line_edit = QLineEdit(game_data.get("savedata_path", ""))

        browse_button = QPushButton()
        browse_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        browse_button.setIcon(browse_icon)
        browse_button.clicked.connect(lambda: self._browse_savedata_folder(line_edit, game_data, path_item))

        auto_detect_button = QPushButton(self.tr("Auto Detect"))
        auto_detect_button.setToolTip(self.tr("Attemps to find the savedata folder automatically"))
        auto_detect_button.clicked.connect(lambda: self._auto_detect_savedata_folder(line_edit, game_data, path_item))

        # Also persist manual edits
        line_edit.editingFinished.connect(lambda: self._save_savedata_path(line_edit, game_data, path_item))

        h_layout.addWidget(line_edit)
        h_layout.addWidget(browse_button)
        h_layout.addWidget(auto_detect_button)

        # Keep a reference so we can retrieve the value later (e.g. on save)
        widget.line_edit = line_edit

        return widget

    def _save_savedata_path(self, line_edit, game_data, path_item=None):
        """Persists the savedata path for this game via GameManager."""
        game_name = game_data.get("name")
        new_path = line_edit.text()
        game_data["savedata_path"] = new_path
        GameManager.update_game(game_name, {"savedata_path": new_path})

        if path_item:
            path_item.setData(Qt.UserRole, new_path)

    def _create_prefix_widget(self, row, game_data):
        """Creates a widget with the current prefix label + a 'Copy to...' button."""
        widget = QWidget()
        h_layout = QHBoxLayout(widget)
        h_layout.setContentsMargins(2, 2, 2, 2)

        prefix_label = QLabel(game_data.get("prefix", ""))
        prefix_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        copy_button = QPushButton(self.tr("Copy to..."))
        copy_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        copy_button.setEnabled(bool(game_data.get("savedata_path", "")))
        is_inside = SavedataManager.is_savedata_inside_prefix(game_data)
        copy_button.setEnabled(is_inside)
        copy_button.clicked.connect(lambda: self._open_copy_to_prefix_dialog(game_data))

        h_layout.addWidget(prefix_label, 1)
        h_layout.addWidget(copy_button, 0)

        widget.prefix_label = prefix_label
        widget.copy_button = copy_button

        return widget

    def _browse_savedata_folder(self, line_edit, game_data, path_item=None):
        dialog = QFileDialog(self)
        dialog.setWindowTitle(self.tr("Select Savedata Folder"))
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, False)

        current_path = game_data.get("savedata_path", "")
        if current_path:
            dialog.setDirectory(current_path)
        
        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                folder = selected_files[0]
                line_edit.setText(folder)
                self._save_savedata_path(line_edit, game_data, path_item)

    def _open_copy_to_prefix_dialog(self, game_data):
        """Opens a small dialog to pick a prefix and copy the savedata into it."""
        prefixes = PrefixManager.get_prefix_json()
        if not prefixes:
            logging.warning("No prefixes found. Cannot open copy-to-prefix dialog.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Copy Savedata to Prefix"))

        outer_layout = QVBoxLayout(dialog)

        combo = QComboBox()
        combo.addItems(sorted(prefixes.keys()))

        # Preselect the game's current prefix if it's in the list
        current_prefix = game_data.get("prefix", "")
        if current_prefix in prefixes:
            combo.setCurrentText(current_prefix)

        ok_button = QPushButton(self.tr("OK"))
        ok_button.clicked.connect(lambda: self._confirm_copy_to_prefix(dialog, game_data, combo))

        # Center the combo box + button in the dialog
        center_row = QHBoxLayout()
        center_row.addStretch()
        center_row.addWidget(combo)
        center_row.addWidget(ok_button)
        center_row.addStretch()

        outer_layout.addStretch()
        outer_layout.addLayout(center_row)
        outer_layout.addStretch()

        dialog.exec()

    def _confirm_copy_to_prefix(self, dialog, game_data, combo):
        """Called when OK is pressed in the copy-to-prefix dialog."""
        selected_prefix = combo.currentText()
        self._try_copy_savedata(game_data, selected_prefix, overwrite=False)
        dialog.accept()
    
    def _try_copy_savedata(self, game_data, selected_prefix, overwrite):
        """Attempts the copy; if savedata already exists at the destination, asks the user to confirm before overwriting."""
        try:
            SavedataManager.copy_savedata_to_prefix(game_data, selected_prefix, overwrite=overwrite)
        except FileExistsError:
            answer = QMessageBox.question(
                self,
                self.tr("Savedata Already Exists"),
                self.tr(
                    "Savedata for '{0}' already exists in prefix '{1}'.\n\n"
                    "Overwrite it?"
                ).format(game_data.get("name", ""), selected_prefix),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if answer == QMessageBox.Yes:
                self._try_copy_savedata(game_data, selected_prefix, overwrite=True)
        except Exception as e:
            logging.error(f"Copy to prefix failed: {e}")
            QMessageBox.critical(self, self.tr("Error"), str(e))

    def _auto_detect_savedata_folder(self, line_edit, game_data, path_item=None):
        """Tries to auto-detect the savedata folder; fills the field on success, warns otherwise."""
        detected_path = SavedataManager.auto_detect_savedata_folder(game_data)
        if detected_path:
            line_edit.setText(detected_path)
            self._save_savedata_path(line_edit, game_data, path_item)
        else:
            QMessageBox.warning(
                self,
                self.tr("Savedata Not Found"),
                self.tr("Couldn't auto-detect the savedata folder for '{0}'. Fill it in manually.")
                    .format(game_data.get("name", ""))
            )

    def _create_gdrive_widget(self, row, game_data, gdrive_item):
        """Creates a checkbox gdrive sync flag and a sync now button."""
        widget = QWidget()
        h_layout = QHBoxLayout(widget)
        h_layout.setContentsMargins(2, 2, 2, 2)

        checkbox = QCheckBox()
        checkbox.setChecked(bool(game_data.get("gdrive", False)))
        #checkbox.setEnabled(bool(game_data.get("savedata_path", "")))
        checkbox.stateChanged.connect(lambda state, gd=game_data: self._save_gdrive_flag(gd, bool(state), gdrive_item))

        sync_button = QPushButton(self.tr("Sync Now"))
        sync_button.setEnabled(checkbox.isChecked())
        sync_button.clicked.connect(lambda: self._sync_gdrive(game_data))
        checkbox.stateChanged.connect(lambda state, btn=sync_button: btn.setEnabled(bool(state)))

        h_layout.addStretch()
        h_layout.addWidget(checkbox)
        h_layout.addWidget(sync_button)
        h_layout.addStretch()

        widget.checkbox = checkbox
        widget.sync_button = sync_button

        return widget

    def _save_gdrive_flag(self, game_data, enabled, gdrive_item=None):
        """Persists the gdrive flag for this game via GameManager."""
        game_name = game_data.get("name")
        game_data["gdrive"] = enabled
        GameManager.update_game(game_name, {"gdrive": enabled})
        if gdrive_item:
            gdrive_item.setData(Qt.UserRole, enabled)

    def _update_gdrive_widget_enabled(self, gdrive_widget, has_path):
        """Keeps both the checkbox and sync button correctly enabled as the savedata path changes."""
        #gdrive_widget.checkbox.setEnabled(has_path)
        gdrive_widget.sync_button.setEnabled(has_path and gdrive_widget.checkbox.isChecked())

    def _sync_gdrive(self, game_data):
        """Handles the Gdrive sync button via SavedataManager."""
        try:
            steps = []

            steps.append(SavedataSyncStep(game_data['name'], game_data, self.tr("Syncing save data with Google Drive...")))
            steps.append(TrackingSyncStep(game_data['path'], self.tr("Syncing time tracking data...")))
            
            self._pending_pipeline = ManualSyncPipeline(self, steps)
            self._pending_pipeline.finished.connect(lambda proceed: setattr(self, '_pending_pipeline', None))
            self._pending_pipeline.start()
        except Exception as e:
            logging.error(f"Gdrive sync failed for '{game_data.get('name', '')}': {e}", exc_info=True)
            QMessageBox.critical(self, self.tr("Gdrive Sync Failed"), str(e))

    def resizeEvent(self, event):
        """Called automatically when the dialog is resized."""
        super().resizeEvent(event)
        
        # Update the maximum width to be 25% (1/4) of the current window width
        # We use max(200, ...) to ensure it never goes below the minimum width
        new_max_width = int(self.width() * 0.25)
        self.search_edit.setMaximumWidth(max(200, new_max_width))
    
    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        geometry = self.settings.value("SavedataManagementDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        header_state = self.settings.value("SavedataManagementDialog/header_state")
        if header_state:
            self.table.setSortingEnabled(False)
            self.table.horizontalHeader().restoreState(header_state)
            self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
            self.table.setSortingEnabled(True)

    def closeEvent(self, event):
        """Overrides the default close event to save geometry before closing."""
        self.settings.setValue("SavedataManagementDialog/geometry", self.saveGeometry())
        self.settings.setValue("SavedataManagementDialog/header_state", self.table.horizontalHeader().saveState())
        super().closeEvent(event)

    def hideEvent(self, event):
        """Fires whenever the dialog is closed, hidden, accepted, or rejected."""
        self.settings.setValue("SavedataManagementDialog/geometry", self.saveGeometry())
        self.settings.setValue("SavedataManagementDialog/header_state", self.table.horizontalHeader().saveState())
        super().hideEvent(event)

class SortableItem(QTableWidgetItem):
    def __lt__(self, other):
        self_data = self.data(Qt.UserRole)
        other_data = other.data(Qt.UserRole)
        # Handle None / mixed types gracefully
        if self_data is None:
            self_data = ""
        if other_data is None:
            other_data = ""
        return str(self_data).lower() < str(other_data).lower()

class HoverHeaderView(QHeaderView):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        pos = event.position().x() if hasattr(event, "position") else event.x()
        index = self.logicalIndexAt(int(pos))
        if index != -1:
            section_start = self.sectionPosition(index)
            section_end = section_start + self.sectionSize(index)
            near_border = abs(pos - section_start) < 10 or abs(pos - section_end) < 10
            if not near_border:
                self.setCursor(Qt.PointingHandCursor)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.unsetCursor()