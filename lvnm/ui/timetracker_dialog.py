from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QCheckBox, QLabel
from PySide6.QtCore import Qt
from timetracker.system_utils import SystemUtils
import logging

logger = logging.getLogger(__name__)

class TimetrackerDialog(QDialog):
    def __init__(self, tracker_service, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Manual Tracking Selection"))
        self.setMinimumWidth(400)
        
        self.tracker = tracker_service
        self.selected_window = None # Stores (title, wid)
        self.window_map = {} # Maps title string -> wid

        self.setup_ui()
        self.refresh_list()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10) 
        # Set small spacing between rows
        layout.setSpacing(10)

        select_label = QLabel(self.tr("Select Game Window:"))
        layout.addWidget(select_label)

        combo_row = QHBoxLayout()
        combo_row.setSpacing(5) # tight space between combo and button
        self.window_combo = QComboBox()
        
        self.refresh_btn = QPushButton(self.tr("Refresh"))
        self.refresh_btn.clicked.connect(self.refresh_list)
        
        combo_row.addWidget(self.window_combo, 1)
        combo_row.addWidget(self.refresh_btn)
        layout.addLayout(combo_row)

        self.wine_check = QCheckBox(self.tr("Only Show Wine/Proton Processes"))
        self.wine_check.setChecked(False)
        self.wine_check.stateChanged.connect(self.refresh_list)
        layout.addWidget(self.wine_check)

        layout.addSpacing(10) 
        self.attach_btn = QPushButton(self.tr("Attach Tracking"))
        self.attach_btn.setStyleSheet("height: 35px; font-weight: bold; background-color: #3d5afe; color: white; border-radius: 4px;")
        self.attach_btn.clicked.connect(self.on_attach)
        layout.addWidget(self.attach_btn)

        self.stop_btn = QPushButton(self.tr("Stop Current tracking"))
        self.stop_btn.setStyleSheet("height: 35px; font-weight: bold; background-color: #3d5afe; color: white; border-radius: 4px;")
        self.stop_btn.clicked.connect(self.on_stop)
        layout.addWidget(self.stop_btn)

        layout.addStretch(1)

    def refresh_list(self):
        """Refresh combo list"""
        self.window_combo.clear()
        self.window_map.clear()
        
        utils = self.tracker.desktop_utils
        windows = SystemUtils.get_window_list(utils, self.wine_check.isChecked())
        
        for title, wid in windows:
            if title:
                self.window_combo.addItem(title)
                self.window_map[title] = wid

    def on_attach(self):
        """Send back current selected wid and title to the sidebar"""
        title = self.window_combo.currentText()
        wid = self.window_map.get(title)
        
        if title and wid:
            self.selected_window = (title, wid)
            self.accept()

    def on_stop(self):
        """Stop current selected tracking"""
        self.done(2)

    def get_selection(self):
        """Returns (title, wid) or None"""
        return self.selected_window