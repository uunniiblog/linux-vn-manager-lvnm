import config
import logging
logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, 
                            QListWidget, QPushButton, QDialog, QMessageBox, QFormLayout,
                            QLineEdit, QFileDialog, QCheckBox, QScrollArea, QFrame, 
                            QPlainTextEdit, QGridLayout, QComboBox, QSizePolicy, QMenu)
from PySide6.QtCore import Qt, QProcess, QSettings
from datetime import datetime
from prefix_manager import PrefixManager
from game_manager import GameManager
from ui.console_dialog import ConsoleDialog
from system_utils import SystemUtils
from runner_manager import RunnerManagerInterface
from game_runner import GameRunner

class PrefixTab(QWidget):
    def __init__(self):
        super().__init__()
        self.prefixes_data = []
        main_layout = QVBoxLayout(self)

        # GroupBox prefixes
        prefix_group = QGroupBox(self.tr("Prefixes"))
        group_layout = QVBoxLayout(prefix_group)
        
        self.prefixes_list = QListWidget()
        group_layout.addWidget(self.prefixes_list)
        main_layout.addWidget(prefix_group)

        # Row 1 Buttons
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton(self.tr("Create Prefix"))
        self.edit_btn = QPushButton(self.tr("Edit Prefix"))
        self.del_btn = QPushButton(self.tr("Delete Prefix"))
        
        btn_layout.addWidget(self.edit_btn, stretch=2)
        btn_layout.addWidget(self.add_btn, stretch=2)
        btn_layout.addWidget(self.del_btn, stretch=1)
        main_layout.addLayout(btn_layout)

        # Visual Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #444;") # Optional: match your dark theme
        main_layout.addWidget(separator)

        # Row 2 Buttons
        btn_layout_2 = QHBoxLayout()
        self.regedit_btn = QPushButton(self.tr("Regedit"))
        self.winecfg_btn = QPushButton(self.tr("Winecfg"))
        self.console_btn = QPushButton(self.tr("wineboot cmd"))
        self.bash_btn = QPushButton(self.tr("Bash"))
        
        btn_layout_2.addWidget(self.regedit_btn)
        btn_layout_2.addWidget(self.winecfg_btn)
        btn_layout_2.addWidget(self.console_btn)
        btn_layout_2.addWidget(self.bash_btn)
        main_layout.addLayout(btn_layout_2)

        # Signals
        self.edit_btn.clicked.connect(self.on_edit)
        self.add_btn.clicked.connect(self.on_add)
        self.del_btn.clicked.connect(self.on_delete)
        self.prefixes_list.itemDoubleClicked.connect(self.on_edit)

        self.regedit_btn.clicked.connect(lambda: self.run_utility("regedit"))
        self.winecfg_btn.clicked.connect(lambda: self.run_utility("winecfg"))
        self.console_btn.clicked.connect(lambda: self.run_utility("wineconsole"))
        self.bash_btn.clicked.connect(self.run_bash_utility)

        self.prefixes_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.prefixes_list.customContextMenuRequested.connect(self.open_context_menu)

        self.refresh_list()

    def refresh_list(self):
        self.prefixes_list.clear()
        self.prefixes_data = PrefixManager.get_prefix_json()
        self.game_data = GameManager.list_games()

        prefix_usage = {}
        for game_name, game_card in self.game_data.items():
            p_name = game_card.prefix
            if p_name:
                if p_name not in prefix_usage:
                    prefix_usage[p_name] = []
                prefix_usage[p_name].append(game_name)

        sorted_prefix_names = sorted(
            self.prefixes_data.keys(),
            key=lambda name: self.prefixes_data[name].get('update_date', ''),
            reverse=True
        )

        display_list = []
        for prefix_name in sorted_prefix_names:
            games = prefix_usage.get(prefix_name, [])
            
            if games:
                display_list.append(f"{prefix_name} ({', '.join(games)})")
            else:
                display_list.append(prefix_name)
        
        self.prefixes_list.addItems(display_list)

    def on_delete(self):
        prefix_str = self.get_selected_prefix()
        
        prefix = PrefixManager(prefix_str)
        confirm = QMessageBox.question(self, self.tr("Delete?"), 
                                     f"{self.tr('Delete Prefix')} {prefix_str}?")
        
        if confirm == QMessageBox.Yes:
            prefix.delete_prefix()
            self.refresh_list()

    def on_edit(self):
        prefix_str = self.get_selected_prefix()
        prefix = PrefixManager(prefix_str)

        dialog = EditPrefixDialog(prefix, self)
        if dialog.exec():
            data = dialog.get_data()
            fonts_path = data.get("fonts", None)
            console = ConsoleDialog(self)
            has_tasks = False

            # Check if path exists
            if prefix.check_prefix_exists() is False:
                logger.error("[Error] Prefix Path doesn't exist")
                QMessageBox.critical(self, self.tr("Error"), self.tr("Prefix Path does not exist"))
                return
            
            # Handle Renaming first
            if data["name"] != prefix.name:
                success = prefix.rename_prefix(data["name"])
                if not success:
                    QMessageBox.warning(self, self.tr("Rename Failed"), 
                                      self.tr("Could not rename prefix. Name might already exist."))
                    return

            # Handle path
            if data["path"] != prefix.prefix_path:
                prefix.prefix_path = data["path"]

            # Handle Codecs
            if data["codecs"]:
                prefix.install_codecs(data["codecs"], executor=console)
                has_tasks = True

            # Handle Winetricks
            if data["winetricks"]:
                prefix.install_winetricks(data["winetricks"], executor=console)
                has_tasks = True

            # Handle Fonts
            if fonts_path and prefix.fonts == False:
                prefix.add_fonts(fonts_path, executor=console)
                has_tasks = True

            if has_tasks:
                #console.set_header_info(prefix.prefix_path, prefix.runner_path)
                #console.show()
                console.start_queue()
                console.exec()
            else:
                logger.debug("No changes in prefix")

            # Update the date and metadata one last time
            prefix.card.update_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            prefix._save_metadata()
            
            self.refresh_list()

    def on_add(self):
        created_name = self.create_new_prefix_flow(self)
        if created_name:
            self.refresh_list()
            
    @staticmethod
    def create_new_prefix_flow(parent_widget):
        dialog = CreatePrefixDialog(parent_widget)
        if dialog.exec():
            data = dialog.get_data()
            name = data["name"]
            fonts_path = data.get("fonts", None)            
            
            # Check if it already exists in JSON
            if PrefixManager.get_prefix_info(name):
                QMessageBox.warning(parent_widget, parent_widget.tr("Error"), parent_widget.tr(f"Prefix '{name}' already exists."))
                return None
                
            # Instantiate Manager
            prefix = PrefixManager(name)
            
            # Prepare the Console
            console = ConsoleDialog(parent_widget)
            console.setWindowTitle(parent_widget.tr(f"Creating Prefix: {name}"))
            
            # Add tasks to queue
            success = prefix.create_prefix(
                runner_path=data["runner_path"], 
                codecs=data["codecs"], 
                winetricks=data["winetricks"], 
                executor=console
            )
            
            if success:
                if fonts_path:
                    prefix.add_fonts(fonts_path, executor=console)
                if prefix.type == "wine":
                    prefix.install_dxvk(executor=console)
                    
                console.start_queue()
                console.exec()
                return name
            else:
                QMessageBox.warning(parent_widget, parent_widget.tr("Error"), parent_widget.tr("Failed to prepare prefix creation."))
                return None
        return None

    def get_selected_prefix(self):
        """Helper to get the raw prefix name from the list selection"""
        current = self.prefixes_list.currentItem()
        if not current:
            return None
        # Split to handle the "PrefixName (Game1, Game2)" display format
        return current.text().split(" (")[0]

    def run_utility(self, command: str):
        prefix_name = self.get_selected_prefix()
        if not prefix_name:
            logger.debug("No prefix selected for utility.")
            return
        runner = GameRunner("UtilityMode")
        runner.run_in_prefix(command, prefix_name)

    def run_bash_utility(self):
        prefix_name = self.get_selected_prefix()
        if not prefix_name:
            logger.debug("No prefix selected for utility.")
            return
        runner = GameRunner("UtilityMode")
        runner.open_terminal(prefix_name)
    
    def open_context_menu(self, position):
        """Creates and shows the right-click menu for prefixes"""
        item = self.prefixes_list.itemAt(position)
        if not item:
            return

        prefix_name = self.get_selected_prefix()
        menu = QMenu(self)

        # Management Actions
        act_edit = menu.addAction(self.tr("Edit Prefix"))
        act_del = menu.addAction(self.tr("Delete Prefix"))
        menu.addSeparator()

        # Utility Actions
        act_regedit = menu.addAction(self.tr("Open Regedit"))
        act_winecfg = menu.addAction(self.tr("Open Winecfg"))
        act_cmd = menu.addAction(self.tr("Open Windows Cmd"))
        act_bash = menu.addAction(self.tr("Open Bash Terminal"))

        # Execute Menu
        action = menu.exec(self.prefixes_list.viewport().mapToGlobal(position))

        # Handle Choices
        if action == act_edit:
            self.on_edit()
        elif action == act_del:
            self.on_delete()
        elif action == act_regedit:
            self.run_utility("regedit")
        elif action == act_winecfg:
            self.run_utility("winecfg")
        elif action == act_cmd:
            self.run_utility("wineconsole")
        elif action == act_bash:
            self.run_bash_utility()
    
    def refresh_active_tab(self):
        """Forces the currently visible sub-tab to reload its data"""
        self.refresh_list()

    
class EditPrefixDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, prefix_manager, parent=None):
        super().__init__(parent)
        self.manager = prefix_manager
        self.setWindowTitle(self.tr(f"Edit Prefix: {self.manager.name}"))
        self.resize(500, 600)
        self.user_settings = SystemUtils.load_settings()

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

        self.layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Name Field
        self.name_edit = QLineEdit(self.manager.name)
        form_layout.addRow(self.tr("Name:"), self.name_edit)

        # Path Field
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit(str(self.manager.prefix_path))
        self.path_btn = QPushButton(self.tr("Browse..."))
        self.path_btn.clicked.connect(self.browse_path)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.path_btn)
        form_layout.addRow(self.tr("Path:"), path_layout)

        # Read Only Info
        self.runner_label = QLabel(str(self.manager.runner_path))
        self.type_label = QLabel(self.manager.type.capitalize())
        # Safe access to update_date from the card
        update_date = getattr(self.manager.card, 'update_date', self.tr("Never"))
        self.date_label = QLabel(update_date)

        form_layout.addRow(self.tr("Runner:"), self.runner_label)
        form_layout.addRow(self.tr("Type:"), self.type_label)
        form_layout.addRow(self.tr("Last Updated:"), self.date_label)

        self.layout.addLayout(form_layout)

        # Font checkbox
        self.font_checkbox = QCheckBox(self.tr("Symlink fonts into prefix"))
        self.font_checkbox.setChecked(bool(self.manager.fonts))
        if self.manager.fonts:
            # Not gonna bother unlinking fonts from prefixes for now
            self.font_checkbox.setDisabled(True)
        self.layout.addWidget(self.font_checkbox)

        # Codecs Section
        self.codec_boxes = {}
        self.layout.addWidget(self.create_check_group(
            self.tr("Codecs"), 
            config.CODEC_LIST, 
            self.manager.codecs.split(),
            self.codec_boxes
        ))

        # Winetricks Section
        self.trick_boxes = {}
        self.layout.addWidget(self.create_check_group(
            self.tr("Winetricks"), 
            config.WINETRICKS_LIST, 
            self.manager.winetricks.split() if hasattr(self.manager, 'winetricks') else [],
            self.trick_boxes
        ))

        # Buttons
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton(self.tr("Save"))
        self.cancel_btn = QPushButton(self.tr("Cancel"))
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        self.layout.addLayout(btn_layout)

        self._restore_state()

    def create_check_group(self, title, data_list, installed_list, storage_dict):
        """Helper to create the scrollable checkbox groups"""
        group = QGroupBox(title)
        vbox = QVBoxLayout(group)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        container = QWidget()
        # Use a Grid Layout for fixed columns
        grid_layout = QGridLayout(container)
        grid_layout.setAlignment(Qt.AlignTop) # Keeps items at the top

        for index, item in enumerate(data_list):
            cb = QCheckBox(item['id'])
            
            # Check if already installed
            is_installed = item['id'] in installed_list
            cb.setChecked(is_installed)
            if is_installed:
                cb.setEnabled(False)
            
            storage_dict[item['id']] = cb
            
            # Calculate grid position:
            # Row: 0, 0, 1, 1, 2, 2...
            # Column: 0, 1, 0, 1, 0, 1...
            row = index // 2
            col = index % 2
            grid_layout.addWidget(cb, row, col)

        scroll.setWidget(container)
        vbox.addWidget(scroll)
        group.setMinimumHeight(150)
        return group

    def browse_path(self):
        current_path = self.path_edit.text().strip()
        new_dir = QFileDialog.getExistingDirectory(
            parent = self,
            caption = self.tr("Select Prefix Directory"),
            dir = current_path
        )
        if new_dir:
            self.path_edit.setText(new_dir)

    def browse_path_qt(self):
        dialog = QFileDialog(self)
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setWindowTitle(self.tr("Select Prefix Directory"))
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setViewMode(QFileDialog.Detail)
        
        current_path = self.path_edit.text().strip()
        if current_path:
            dialog.setDirectory(current_path)

        if dialog.exec():
            selected = dialog.selectedFiles()
            if selected:
                self.path_edit.setText(selected[0])

    def get_data(self):
        """Returns the current state of the UI fields"""
        new_codecs = [id for id, cb in self.codec_boxes.items() if cb.isChecked() and cb.isEnabled()]
        new_tricks = [id for id, cb in self.trick_boxes.items() if cb.isChecked() and cb.isEnabled()]
        
        data = {
            "name": self.name_edit.text(),
            "path": self.path_edit.text(),
            "codecs": " ".join(new_codecs),
            "winetricks": " ".join(new_tricks)
        }

        if self.font_checkbox.isChecked():
            data["fonts"] = self.user_settings.get("font_folder", "")

        return data

    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        # Use a unique key for this specific dialog
        geometry = self.settings.value("EditPrefixDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        """Overrides the default close event to save geometry before closing."""
        self.settings.setValue("EditPrefixDialog/geometry", self.saveGeometry())
        super().closeEvent(event)

    def hideEvent(self, event):
        """Fires whenever the dialog is closed, hidden, accepted, or rejected."""
        self.settings.setValue("EditPrefixDialog/geometry", self.saveGeometry())
        super().hideEvent(event)

class CreatePrefixDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Create New Prefix"))
        self.resize(500, 600)
        self.user_settings = SystemUtils.load_settings()

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

        self.layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # --- Name Field ---
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._update_path_label)
        form_layout.addRow(self.tr("Name:"), self.name_edit)

        # --- Path Field (Read-only dynamic label) ---
        self.path_label = QLabel(str(config.PREFIXES_DIR / "..."))
        self.path_label.setStyleSheet("color: gray;")
        form_layout.addRow(self.tr("Path:"), self.path_label)

        # --- Runner Selection ---
        self.runner_combo = QComboBox() 
        self.runner_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.available_runners = RunnerManagerInterface.get_all_installed_runners()
        self.runner_combo.addItems(self.available_runners)
        form_layout.addRow(self.tr("Runner:"), self.runner_combo)

        self.layout.addLayout(form_layout)

        # --- Font checkbox ---
        self.font_checkbox = QCheckBox(self.tr("Symlink fonts into prefix"))
        self.font_checkbox.setChecked(bool(self.user_settings.get("font_folder", "")))
        self.layout.addWidget(self.font_checkbox)

        # --- Codecs Section ---
        self.codec_boxes = {}
        self.layout.addWidget(self.create_check_group(
            self.tr("Codecs"), config.CODEC_LIST, [], self.codec_boxes
        ))

        # --- Winetricks Section ---
        self.trick_boxes = {}
        self.layout.addWidget(self.create_check_group(
            self.tr("Winetricks"), config.WINETRICKS_LIST, [], self.trick_boxes
        ))

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        self.create_btn = QPushButton(self.tr("Create Prefix"))
        self.cancel_btn = QPushButton(self.tr("Cancel"))
        
        self.create_btn.clicked.connect(self.validate_and_accept)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.create_btn)
        self.layout.addLayout(btn_layout)

        self._restore_state()

    def _update_path_label(self, text):
        """Updates the path preview label as the user types"""
        if text.strip():
            self.path_label.setText(str(config.PREFIXES_DIR / text.strip()))
        else:
            self.path_label.setText(str(config.PREFIXES_DIR / "..."))

    def create_check_group(self, title, data_list, installed_list, storage_dict):
        """Reused helper from Edit dialog"""
        group = QGroupBox(title)
        vbox = QVBoxLayout(group)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        grid_layout = QGridLayout(container)
        grid_layout.setAlignment(Qt.AlignTop)

        for index, item in enumerate(data_list):
            cb = QCheckBox(item['id'])
            storage_dict[item['id']] = cb
            row = index // 2
            col = index % 2
            grid_layout.addWidget(cb, row, col)

        scroll.setWidget(container)
        vbox.addWidget(scroll)
        group.setMinimumHeight(150)
        return group

    def validate_and_accept(self):
        """Ensures obligatory fields are filled"""
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, self.tr("Error"), self.tr("Prefix Name is required."))
            return
        if not self.runner_combo.currentText():
            QMessageBox.warning(self, self.tr("Error"), self.tr("A Runner must be selected."))
            return
        self.accept()

    def get_data(self):
        selected_runner_name = self.runner_combo.currentText()
        new_codecs = [id for id, cb in self.codec_boxes.items() if cb.isChecked()]
        new_tricks = [id for id, cb in self.trick_boxes.items() if cb.isChecked()]
        
        data = {
            "name": self.name_edit.text().strip(),
            "runner_path": self.available_runners[selected_runner_name],
            "codecs": " ".join(new_codecs),
            "winetricks": " ".join(new_tricks)
        }

        if self.font_checkbox.isChecked():
            data["fonts"] = self.user_settings.get("font_folder", "")

        return data

    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        # Use a unique key for this specific dialog
        geometry = self.settings.value("CreatePrefixDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        """Overrides the default close event to save geometry before closing."""
        self.settings.setValue("CreatePrefixDialog/geometry", self.saveGeometry())
        super().closeEvent(event)
    
    def hideEvent(self, event):
        """Fires whenever the dialog is closed, hidden, accepted, or rejected."""
        self.settings.setValue("CreatePrefixDialog/geometry", self.saveGeometry())
        super().hideEvent(event)
