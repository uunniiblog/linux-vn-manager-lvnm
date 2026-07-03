from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton,
    QDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy,
    QWidget, QLineEdit, QLabel, QFileDialog, QComboBox,
    QMessageBox
)
from PySide6.QtCore import QSettings, Qt
import config
from settings_manager import SettingsManager
from game_manager import GameManager
from prefix_manager import PrefixManager
from savedata_manager import SavedataManager
import logging

logger = logging.getLogger(__name__)

class SavedataManagementDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manage Savedata files"))
        self.resize(600, 400)

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

        layout = QVBoxLayout(self)
        self.info_label = QLabel(self.tr("When adding the savedata path add the furthermost path that contains the actual save files. If the savedata is inside the same prefix as the game you can also copy the save files to another prefixes."))
        layout.addWidget(self.info_label)

        self.games = GameManager._load_data()

        # Table Setup
        self.table = QTableWidget(len(self.games), 4)
        self.table.setHorizontalHeaderLabels([
            self.tr("Game"),
            self.tr("Savedata Path"),
            self.tr("Prefix"),
            self.tr("Gdrive")
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

        for row, (game_id, game_data) in enumerate(self.games.items()):
            # Column 0: Game name
            name_item = QTableWidgetItem(game_data.get("name", game_id))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)

            # Column 1: Savedata path (line edit + browse button)
            savedata_widget = self._create_savedata_widget(row, game_data)
            self.table.setCellWidget(row, 1, savedata_widget)

            # Column 2: Prefix (label + "Copy to..." button)
            prefix_widget = self._create_prefix_widget(row, game_data)
            self.table.setCellWidget(row, 2, prefix_widget)

            # Enable/disable the copy button as the path changes
            savedata_widget.line_edit.textChanged.connect(lambda text, btn=prefix_widget.copy_button: btn.setEnabled(bool(text.strip())))

            # Column 3: Gdrive - left empty for now
            self.table.setItem(row, 3, QTableWidgetItem(""))

        layout.addWidget(self.table)

        # Restore previous window size
        self._restore_state()

    def _create_savedata_widget(self, row, game_data):
        """Creates a widget with a line edit + browse button for the savedata path."""
        widget = QWidget()
        h_layout = QHBoxLayout(widget)
        h_layout.setContentsMargins(2, 2, 2, 2)

        line_edit = QLineEdit(game_data.get("savedata_path", ""))
        browse_button = QPushButton(self.tr("Browse"))
        browse_button.clicked.connect(lambda: self._browse_savedata_folder(line_edit, game_data))

        # Also persist manual edits (typed directly into the field, not just via Browse)
        line_edit.editingFinished.connect(lambda: self._save_savedata_path(line_edit, game_data))

        h_layout.addWidget(line_edit)
        h_layout.addWidget(browse_button)

        # Keep a reference so we can retrieve the value later (e.g. on save)
        widget.line_edit = line_edit

        return widget

    def _save_savedata_path(self, line_edit, game_data):
        """Persists the savedata path for this game via GameManager."""
        game_name = game_data.get("name")
        new_path = line_edit.text()

        # Keep the in-memory dict in sync too, since other widgets (e.g. the
        game_data["savedata_path"] = new_path

        GameManager.update_game(game_name, {"savedata_path": new_path})

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
        copy_button.clicked.connect(lambda: self._open_copy_to_prefix_dialog(game_data))

        h_layout.addWidget(prefix_label, 1)
        h_layout.addWidget(copy_button, 0)

        widget.prefix_label = prefix_label
        widget.copy_button = copy_button

        return widget

    def _browse_savedata_folder(self, line_edit, game_data):
        folder = QFileDialog.getExistingDirectory(self, self.tr("Select Savedata Folder"), "")
        if folder:
            line_edit.setText(folder)
            self._save_savedata_path(line_edit, game_data)

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

    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        geometry = self.settings.value("SavedataManagementDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        """Overrides the default close event to save geometry before closing."""
        self.settings.setValue("SavedataManagementDialog/geometry", self.saveGeometry())
        super().closeEvent(event)

    def hideEvent(self, event):
        """Fires whenever the dialog is closed, hidden, accepted, or rejected."""
        self.settings.setValue("SavedataManagementDialog/geometry", self.saveGeometry())
        super().hideEvent(event)