import config
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, 
    QLineEdit, QLabel, QPushButton, QFileDialog
)
from PySide6.QtCore import Qt, QSettings

class AdvancedSettingsDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, prefix_type, current_game, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Advanced Settings"))
        self.setMinimumWidth(450)        
        self.current_game = current_game

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)


        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)

        # UMU Fields
        self.edit_umu_store = QLineEdit(getattr(self.current_game, "umu_store", ""))
        self.edit_umu_id = QLineEdit(getattr(self.current_game, "umu_gameid", ""))
        
        self.label_umu_store = QLabel(self.tr("UMU Store:"))
        self.label_umu_id = QLabel(self.tr("UMU ID:"))

        # Proton Visibility Logic
        is_proton = (prefix_type == "proton")
        self.edit_umu_store.setVisible(is_proton)
        self.edit_umu_id.setVisible(is_proton)
        self.label_umu_store.setVisible(is_proton)
        self.label_umu_id.setVisible(is_proton)

        form.addRow(self.label_umu_store, self.edit_umu_store)
        form.addRow(self.label_umu_id, self.edit_umu_id)

        # Pre-launch Arguments
        self.edit_pre_args = QLineEdit(getattr(self.current_game, "pre_launch_args", ""))
        form.addRow(self.tr("Pre-Launch Command:"), self.edit_pre_args)

        # Arguments
        self.edit_arguments = QLineEdit(getattr(self.current_game, "arguments", ""))
        form.addRow(self.tr("Game Arguments:"), self.edit_arguments)

        # Pre-launch Script
        self.edit_pre_script = QLineEdit(getattr(self.current_game, "pre_launch_script", ""))
        self.btn_pre_script = QPushButton("...")
        self.btn_pre_script.clicked.connect(lambda: self.browse_file(self.edit_pre_script))
        
        pre_script_layout = QHBoxLayout()
        pre_script_layout.addWidget(self.edit_pre_script)
        pre_script_layout.addWidget(self.btn_pre_script)
        form.addRow(self.tr("Pre-Launch Script:"), pre_script_layout)

        # Exit Script
        self.edit_exit_script = QLineEdit(getattr(self.current_game, "exit_script", ""))
        self.btn_exit_script = QPushButton("...")
        self.btn_exit_script.clicked.connect(lambda: self.browse_file(self.edit_exit_script))
        
        exit_script_layout = QHBoxLayout()
        exit_script_layout.addWidget(self.edit_exit_script)
        exit_script_layout.addWidget(self.btn_exit_script)
        form.addRow(self.tr("Exit Script:"), exit_script_layout)

        layout.addLayout(form)

        # Save / Cancel Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton(self.tr("Save"))
        save_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        cancel_btn = QPushButton(self.tr("Cancel"))
        
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        # Restore previous window size
        self._restore_state()

    def browse_file(self, target_line_edit):
        """Opens file system to select a script."""
        path, _ = QFileDialog.getOpenFileName(
            self, 
            self.tr("Select Script File"), 
            "", 
            "All Files (*);;Shell Scripts (*.sh)"
        )
        if path:
            target_line_edit.setText(path)

    def accept(self):
        """Saves values directly back to the unsaved in-memory game card."""
        self.current_game.umu_store = self.edit_umu_store.text()
        self.current_game.umu_gameid = self.edit_umu_id.text()
        self.current_game.pre_launch_args = self.edit_pre_args.text()
        self.current_game.arguments = self.edit_arguments.text()
        self.current_game.pre_launch_script = self.edit_pre_script.text()
        self.current_game.exit_script = self.edit_exit_script.text()
        super().accept()

    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        geometry = self.settings.value("AdvancedSettingsDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        """Overrides the default close event to save geometry before closing."""
        self.settings.setValue("AdvancedSettingsDialog/geometry", self.saveGeometry())
        super().closeEvent(event)
    
    def hideEvent(self, event):
        """Fires whenever the dialog is closed, hidden, accepted, or rejected."""
        self.settings.setValue("AdvancedSettingsDialog/geometry", self.saveGeometry())
        super().hideEvent(event)