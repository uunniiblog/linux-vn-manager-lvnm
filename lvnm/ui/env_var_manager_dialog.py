from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QPushButton,
    QDialog, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QComboBox,
    QCheckBox, QWidget
)
from PySide6.QtCore import QSettings, Qt
import config
from settings_manager import SettingsManager

class EnvVarManagerDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, env_vars, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manage Environment Variables"))
        self.resize(600, 400)
        self.env_vars = env_vars
        self.global_env_var = SettingsManager().get(config.USER_CONF_GLOBAL_VARIABLES, {})

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

        layout = QVBoxLayout(self)

        # Table Setup
        self.table = QTableWidget(len(self.env_vars), 5)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setMouseTracking(True)

        self.table.setHorizontalHeaderLabels([
            self.tr("Name / Description"), 
            self.tr("Key"), 
            self.tr("Value"),
            self.tr("Prefix Type"),
            self.tr("Global Variable")
        ])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        #header.setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(3, 100)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

        for row, var in enumerate(self.env_vars):
            self.table.setItem(row, 0, QTableWidgetItem(var.get("name", var.get("id", ""))))
            self.table.setItem(row, 1, QTableWidgetItem(var.get("key", "")))
            self.table.setItem(row, 2, QTableWidgetItem(var.get("value", "")))
            self.table.setCellWidget(row, 3, self._create_type_combo(var.get("req", "")))
            self.table.setCellWidget(row, 4, self._create_global_checkbox(self.global_env_var.get(var.get("id", ""), False)))

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
        self.table.setItem(row, 0, QTableWidgetItem(self.tr("New Variable")))
        self.table.setItem(row, 1, QTableWidgetItem("KEY"))
        self.table.setItem(row, 2, QTableWidgetItem("1"))
        self.table.setCellWidget(row, 3, self._create_type_combo(""))
        self.table.setCellWidget(row, 4, self._create_global_checkbox(False))

    def remove_row(self):
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)

    def get_vars(self):
        new_vars = []
        global_vars = {}
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text().strip() if self.table.item(row, 0) else ""
            key = self.table.item(row, 1).text().strip() if self.table.item(row, 1) else ""
            value = self.table.item(row, 2).text().strip() if self.table.item(row, 2) else ""
            req_text = self.table.cellWidget(row, 3).currentText() if self.table.cellWidget(row, 3) else "both"

            req_value = "" if req_text == self.tr("both") else req_text

            is_global = self._get_global_checkbox_state(row)
            
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
                global_vars[safe_id] = is_global

        self._global_states = global_vars
        return new_vars

    def get_global_states(self) -> dict:
        return getattr(self, "_global_states", {})

    def _create_type_combo(self, current_val):
        """Configure the prefix type dropdown"""
        combo = QComboBox()
        combo.addItems([self.tr("both"), "proton", "wine"])
        
        if not current_val:
            combo.setCurrentText(self.tr("both"))
        else:
            combo.setCurrentText(current_val)
        return combo

    def _create_global_checkbox(self, checked: bool) -> QWidget:
        """Wraps a centered checkbox for the Global variable column."""
        container = QWidget()
        cb_layout = QHBoxLayout(container)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        cb_layout.setAlignment(Qt.AlignCenter)
        checkbox = QCheckBox()
        checkbox.setChecked(checked)
        checkbox.setToolTip(self.tr("These environment variables will be automatically selected when adding a new game.\nThey will also be automatically applied from the 'Run in Prefix' dialog."))
        cb_layout.addWidget(checkbox)
        container.checkbox = checkbox
        return container

    def _get_global_checkbox_state(self, row: int) -> bool:
        container = self.table.cellWidget(row, 4)
        if container is not None and hasattr(container, "checkbox"):
            return container.checkbox.isChecked()
        return False

    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        geometry = self.settings.value("EnvVarManagerDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        header_state = self.settings.value("EnvVarManagerDialog/header_state")
        if header_state:
            self.table.horizontalHeader().restoreState(header_state)
            self.table.horizontalHeader().setStretchLastSection(True)

    def closeEvent(self, event):
        """Overrides the default close event to save geometry before closing."""
        self.settings.setValue("EnvVarManagerDialog/geometry", self.saveGeometry())
        self.settings.setValue("EnvVarManagerDialog/header_state", self.table.horizontalHeader().saveState())
        super().closeEvent(event)
    
    def hideEvent(self, event):
        """Fires whenever the dialog is closed, hidden, accepted, or rejected."""
        self.settings.setValue("EnvVarManagerDialog/geometry", self.saveGeometry())
        self.settings.setValue("EnvVarManagerDialog/header_state", self.table.horizontalHeader().saveState())
        super().hideEvent(event)