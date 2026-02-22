import config
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, 
                            QListWidget, QPushButton, QDialog, QMessageBox, QFormLayout,
                            QLineEdit, QFileDialog, QCheckBox, QScrollArea, QFrame, 
                            QPlainTextEdit, QGridLayout, QComboBox)
from PySide6.QtCore import Qt, QProcess, QSettings
from datetime import datetime
from prefix_manager import PrefixManager
from game_manager import GameManager
from ui.console_dialog import ConsoleDialog

class PrefixTab(QWidget):
    def __init__(self):
        super().__init__()
        self.prefixes_data = []
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(QLabel(self.tr("Prefix View - TODO")))

        # GroupBox prefixes
        prefix_group = QGroupBox(self.tr("Prefixes"))
        group_layout = QVBoxLayout(prefix_group)
        
        self.prefixes_list = QListWidget()
        group_layout.addWidget(self.prefixes_list)
        main_layout.addWidget(prefix_group)

        # Buttons
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton(self.tr("Create Prefix"))
        self.edit_btn = QPushButton(self.tr("Edit Prefix"))
        self.del_btn = QPushButton(self.tr("Delete Prefix"))
        
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.del_btn)
        main_layout.addLayout(btn_layout)

        # Signals
        self.edit_btn.clicked.connect(self.on_edit)
        self.add_btn.clicked.connect(self.on_add)
        self.del_btn.clicked.connect(self.on_delete)


        #main_layout.addStretch()

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
        current = self.prefixes_list.currentItem()
        if not current: return
        
        # Select prefix wtihout games
        prefix_str = current.text().split(" (")[0]
        prefix = PrefixManager(prefix_str)
        confirm = QMessageBox.question(self, self.tr("Delete?"), 
                                     f"{self.tr('Delete Prefix')} {prefix_str}?")
        
        if confirm == QMessageBox.Yes:
            prefix.delete_prefix()
            self.refresh_list()

    def on_edit(self):
        current = self.prefixes_list.currentItem()
        if not current:
            print("[Debug] No prefix Selected")
            return

        prefix_str = current.text().split(" (")[0]
        prefix = PrefixManager(prefix_str)

        dialog = EditPrefixDialog(prefix, self)
        if dialog.exec():
            data = dialog.get_data()
            console = ConsoleDialog(self)
            has_tasks = False
            
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

            if has_tasks:
                #console.set_header_info(prefix.prefix_path, prefix.runner_path)
                #console.show()
                console.start_queue()
                console.exec() 

            # Update the date and metadata one last time
            prefix.card.update_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            prefix._save_metadata()
            
            self.refresh_list()

    def on_add(self):
        dialog = CreatePrefixDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            name = data["name"]
            
            # 1. Validation - check if it already exists in JSON
            if PrefixManager.get_prefix_info(name):
                QMessageBox.warning(self, self.tr("Error"), self.tr(f"Prefix '{name}' already exists."))
                return
                
            # 2. Instantiate Manager
            # It will print "Prefix [name] does not exist yet" internally, which is expected!
            prefix = PrefixManager(name)
            
            # 3. Prepare the Console
            console = ConsoleDialog(self)
            console.setWindowTitle(self.tr(f"Creating Prefix: {name}"))
            
            
            # 4. Add tasks to queue
            success = prefix.create_prefix(
                runner_path=data["runner_path"], 
                codecs=data["codecs"], 
                winetricks=data["winetricks"], 
                executor=console
            )
            
            if success:
                # console.set_header_info(str(config.PREFIXES_DIR / name), data["runner_path"])
                # console.show()
                console.start_queue()
                console.exec() # Locks UI, plays the log
            else:
                QMessageBox.warning(self, self.tr("Error"), self.tr("Failed to prepare prefix creation."))

            # 5. Refresh UI List
            self.refresh_list()

    
class EditPrefixDialog(QDialog):
    SETTINGS_FILE = config.SETTINGS_FILE

    def __init__(self, prefix_manager, parent=None):
        super().__init__(parent)
        self.manager = prefix_manager
        self.setWindowTitle(self.tr(f"Edit Prefix: {self.manager.name}"))
        self.resize(500, 600)

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
        new_dir = QFileDialog.getExistingDirectory(self, self.tr("Select Prefix Directory"), self.path_edit.text())
        if new_dir:
            self.path_edit.setText(new_dir)

    def get_data(self):
        """Returns the current state of the UI fields"""
        new_codecs = [id for id, cb in self.codec_boxes.items() if cb.isChecked() and cb.isEnabled()]
        new_tricks = [id for id, cb in self.trick_boxes.items() if cb.isChecked() and cb.isEnabled()]
        
        return {
            "name": self.name_edit.text(),
            "path": self.path_edit.text(),
            "codecs": " ".join(new_codecs),
            "winetricks": " ".join(new_tricks)
        }
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
    SETTINGS_FILE = config.SETTINGS_FILE
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Create New Prefix"))
        self.resize(500, 600)

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
        # Ensure RunnerManagerInterface is imported at the top of the file
        from runner_manager import RunnerManagerInterface 
        self.available_runners = RunnerManagerInterface.get_all_installed_runners()
        self.runner_combo.addItems(self.available_runners.keys())
        form_layout.addRow(self.tr("Runner:"), self.runner_combo)

        self.layout.addLayout(form_layout)

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
        
        return {
            "name": self.name_edit.text().strip(),
            "runner_path": self.available_runners[selected_runner_name],
            "codecs": " ".join(new_codecs),
            "winetricks": " ".join(new_tricks)
        }

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
