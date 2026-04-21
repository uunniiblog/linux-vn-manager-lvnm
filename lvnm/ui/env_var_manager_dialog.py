from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton,
    QDialog, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QComboBox
)
from PySide6.QtCore import QSettings
import config
from settings_manager import SettingsManager

class EnvVarManagerDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, env_vars, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manage Environment Variables"))
        self.resize(600, 400)
        self.env_vars = env_vars

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

        layout = QVBoxLayout(self)

        # Table Setup
        self.table = QTableWidget(len(self.env_vars), 4)
        self.table.setHorizontalHeaderLabels([
            self.tr("Name / Description"), 
            self.tr("Key"), 
            self.tr("Value"),
            self.tr("Prefix Type")
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

        for row, var in enumerate(self.env_vars):
            self.table.setItem(row, 0, QTableWidgetItem(var.get("name", var.get("id", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(var.get("key", "")))
            self.table.setItem(row, 2, QTableWidgetItem(var.get("value", "")))
            self.table.setCellWidget(row, 3, self._create_type_combo(var.get("req", "")))

        # Buttons
        btn_layout = QHBoxLayout()
        add_btn = QPushButton(self.tr("Add Variable"))
        remove_btn = QPushButton(self.tr("Remove Selected"))
        save_btn = QPushButton(self.tr("Save"))
        cancel_btn = QPushButton(self.tr("Cancel"))

        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)

        layout.addWidget(self.table)
        layout.addLayout(btn_layout)

        # Connections
        add_btn.clicked.connect(self.add_row)
        remove_btn.clicked.connect(self.remove_row)
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        # Restore previous window size
        self._restore_state()

    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem("New Variable"))
        self.table.setItem(row, 1, QTableWidgetItem("KEY"))
        self.table.setItem(row, 2, QTableWidgetItem("1"))
        self.table.setCellWidget(row, 3, self._create_type_combo(""))

    def remove_row(self):
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)

    def get_vars(self):
        new_vars = []
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text().strip() if self.table.item(row, 0) else ""
            key = self.table.item(row, 1).text().strip() if self.table.item(row, 1) else ""
            value = self.table.item(row, 2).text().strip() if self.table.item(row, 2) else ""
            req_text = self.table.cellWidget(row, 3).currentText() if self.table.cellWidget(row, 3) else "both"

            req_value = "" if req_text == self.tr("both") else req_text
            
            if key and value:
                # Generate a ID based on the key/name
                safe_id = name.lower().replace(" ", "_") if name else key.lower()
                var_dict = {
                    "id": safe_id,
                    "name": name,
                    "key": key,
                    "value": value
                }
                if req_value:
                    var_dict["req"] = req_value
                new_vars.append(var_dict)

        return new_vars

    def _create_type_combo(self, current_val):
        """Configure the prefix type dropdown"""
        combo = QComboBox()
        combo.addItems([self.tr("both"), "proton", "wine"])
        
        if not current_val:
            combo.setCurrentText(self.tr("both"))
        else:
            combo.setCurrentText(current_val)
        return combo

    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        geometry = self.settings.value("EnvVarManagerDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        """Overrides the default close event to save geometry before closing."""
        self.settings.setValue("EnvVarManagerDialog/geometry", self.saveGeometry())
        super().closeEvent(event)
    
    def hideEvent(self, event):
        """Fires whenever the dialog is closed, hidden, accepted, or rejected."""
        self.settings.setValue("EnvVarManagerDialog/geometry", self.saveGeometry())
        super().hideEvent(event)