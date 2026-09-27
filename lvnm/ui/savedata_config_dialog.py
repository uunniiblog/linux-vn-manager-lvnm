import copy
import uuid
from pathlib import Path

import config
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSplitter, QTabWidget, QVBoxLayout, QWidget
)

from savedata_manager import SavedataManager


class SavedataConfigDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, game_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Configure Savedata"))
        self.resize(700, 450)
        self.game_data = game_data
        self.savedata_config = copy.deepcopy(SavedataManager.get_savedata_config(game_data))
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.folder_list = QListWidget()
        self.excluded_list = QListWidget()
        self.file_list = QListWidget()
        self.tabs.addTab(self._create_folder_tab(), self.tr("Folders"))
        self.tabs.addTab(self._create_file_tab(), self.tr("Specific Files"))
        self.tabs.setCurrentIndex(1 if self.savedata_config.get("mode") == "files" else 0)
        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_config()
        self._restore_state()

    def _create_folder_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.folder_splitter = QSplitter(Qt.Vertical)

        folder_panel = QWidget()
        folder_layout = QVBoxLayout(folder_panel)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.addWidget(QLabel(self.tr("Savedata Folders")))
        folder_layout.addWidget(self.folder_list)
        folder_buttons = QHBoxLayout()
        add_folder_button = QPushButton(self.tr("Add Folder"))
        remove_folder_button = QPushButton(self.tr("Remove Folder"))
        add_folder_button.clicked.connect(self._add_folder)
        remove_folder_button.clicked.connect(self._remove_selected_folders)
        folder_buttons.addWidget(add_folder_button)
        folder_buttons.addWidget(remove_folder_button)
        folder_buttons.addStretch()
        folder_layout.addLayout(folder_buttons)

        excluded_panel = QWidget()
        excluded_layout = QVBoxLayout(excluded_panel)
        excluded_layout.setContentsMargins(0, 0, 0, 0)
        excluded_layout.addWidget(QLabel(self.tr("Excluded Files for Selected Folder")))
        excluded_layout.addWidget(self.excluded_list)
        excluded_buttons = QHBoxLayout()
        add_excluded_button = QPushButton(self.tr("Add Excluded Files"))
        remove_excluded_button = QPushButton(self.tr("Remove Exclusion"))
        add_excluded_button.clicked.connect(self._add_excluded_files)
        remove_excluded_button.clicked.connect(self._remove_selected_exclusions)
        excluded_buttons.addWidget(add_excluded_button)
        excluded_buttons.addWidget(remove_excluded_button)
        excluded_buttons.addStretch()
        excluded_layout.addLayout(excluded_buttons)

        self.folder_splitter.addWidget(folder_panel)
        self.folder_splitter.addWidget(excluded_panel)
        self.folder_splitter.setStretchFactor(0, 1)
        self.folder_splitter.setStretchFactor(1, 1)
        layout.addWidget(self.folder_splitter)
        self.folder_list.currentItemChanged.connect(self._show_selected_folder_exclusions)
        return widget

    def _create_file_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(self.file_list)
        buttons = QHBoxLayout()
        add_button = QPushButton(self.tr("Add Files"))
        remove_button = QPushButton(self.tr("Remove"))
        add_button.clicked.connect(self._add_files)
        remove_button.clicked.connect(lambda: self._remove_selected(self.file_list))
        buttons.addWidget(add_button)
        buttons.addWidget(remove_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        return widget

    def _load_config(self):
        for folder in self.savedata_config.get("folders", []):
            self._add_folder_item(folder)
        for group in self.savedata_config.get("file_groups", []):
            root = Path(group.get("root", ""))
            for relative in group.get("files", []):
                item = QListWidgetItem(str(root / relative))
                item.setData(Qt.UserRole, group.get("source_id", "primary"))
                self.file_list.addItem(item)
        if self.folder_list.count():
            self.folder_list.setCurrentRow(0)

    def _add_folder_item(self, folder):
        excluded = list(folder.get("excluded", []))
        text = self.tr("{0} ({1} excluded)").format(folder.get("path", ""), len(excluded))
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, copy.deepcopy(folder))
        self.folder_list.addItem(item)

    def _initial_directory(self):
        game_path = self.game_data.get("path", "")
        return str(Path(game_path).parent) if game_path else ""

    def _add_folder(self):
        path = QFileDialog.getExistingDirectory(self, self.tr("Select Savedata Folder"), self._initial_directory())
        if not path:
            return
        existing = {
            self.folder_list.item(index).data(Qt.UserRole).get("path")
            for index in range(self.folder_list.count())
        }
        if path in existing:
            return
        source_id = "primary" if self.folder_list.count() == 0 else uuid.uuid4().hex
        self._add_folder_item({"path": path, "excluded": [], "source_id": source_id})
        self.folder_list.setCurrentRow(self.folder_list.count() - 1)

    def _show_selected_folder_exclusions(self, current, previous=None):
        self.excluded_list.clear()
        if current is None:
            return
        self.excluded_list.addItems(current.data(Qt.UserRole).get("excluded", []))

    def _add_excluded_files(self):
        folder_item = self.folder_list.currentItem()
        if folder_item is None:
            return
        folder = folder_item.data(Qt.UserRole)
        root = Path(folder.get("path", ""))
        dialog = QFileDialog(self, self.tr("Select Files to Exclude"), str(root))
        dialog.setFileMode(QFileDialog.ExistingFiles)
        if not dialog.exec():
            return

        excluded = set(folder.get("excluded", []))
        for selected in dialog.selectedFiles():
            try:
                excluded.add(Path(selected).resolve().relative_to(root.resolve()).as_posix())
            except ValueError:
                QMessageBox.warning(
                    self,
                    self.tr("Invalid File"),
                    self.tr("Excluded files must be inside the selected folder.")
                )
        self._set_folder_exclusions(folder_item, sorted(excluded))

    def _remove_selected_exclusions(self):
        folder_item = self.folder_list.currentItem()
        if folder_item is None:
            return
        removed = {item.text() for item in self.excluded_list.selectedItems()}
        folder = folder_item.data(Qt.UserRole)
        excluded = [path for path in folder.get("excluded", []) if path not in removed]
        self._set_folder_exclusions(folder_item, excluded)

    def _set_folder_exclusions(self, folder_item, excluded):
        folder = folder_item.data(Qt.UserRole)
        folder["excluded"] = excluded
        folder_item.setData(Qt.UserRole, folder)
        folder_item.setText(self.tr("{0} ({1} excluded)").format(folder.get("path", ""), len(excluded)))
        self._show_selected_folder_exclusions(folder_item)

    def _remove_selected_folders(self):
        self._remove_selected(self.folder_list)
        if self.folder_list.currentItem() is None and self.folder_list.count():
            self.folder_list.setCurrentRow(0)
        self._show_selected_folder_exclusions(self.folder_list.currentItem())

    def _add_files(self):
        dialog = QFileDialog(self, self.tr("Select Savedata Files"), self._initial_directory())
        dialog.setFileMode(QFileDialog.ExistingFiles)
        if not dialog.exec():
            return
        existing = {self.file_list.item(index).text() for index in range(self.file_list.count())}
        for path in dialog.selectedFiles():
            if path not in existing:
                self.file_list.addItem(path)
                existing.add(path)

    @staticmethod
    def _remove_selected(widget):
        for item in widget.selectedItems():
            widget.takeItem(widget.row(item))

    def result_config(self):
        if self.tabs.currentIndex() == 0:
            folders = [self.folder_list.item(index).data(Qt.UserRole) for index in range(self.folder_list.count())]
            return {"version": 1, "mode": "folders", "folders": folders, "file_groups": []}

        previous_ids = {
            group.get("root", ""): group.get("source_id", "primary")
            for group in self.savedata_config.get("file_groups", [])
        }
        grouped = {}
        for index in range(self.file_list.count()):
            path = Path(self.file_list.item(index).text())
            grouped.setdefault(str(path.parent), []).append(path.name)
        groups = []
        for index, (root, files) in enumerate(grouped.items()):
            source_id = previous_ids.get(root, "primary" if index == 0 else uuid.uuid4().hex)
            groups.append({"root": root, "files": sorted(set(files)), "source_id": source_id})
        return {"version": 1, "mode": "files", "folders": [], "file_groups": groups}

    def _restore_state(self):
        geometry = self.settings.value("SavedataConfigDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value("SavedataConfigDialog/folder_splitter_state")
        if splitter_state:
            self.folder_splitter.restoreState(splitter_state)

    def _save_state(self):
        self.settings.setValue("SavedataConfigDialog/geometry", self.saveGeometry())
        self.settings.setValue("SavedataConfigDialog/folder_splitter_state", self.folder_splitter.saveState())

    def closeEvent(self, event):
        self._save_state()
        super().closeEvent(event)

    def hideEvent(self, event):
        self._save_state()
        super().hideEvent(event)
