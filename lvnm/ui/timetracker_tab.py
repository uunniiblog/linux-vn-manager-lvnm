import logging
import config
from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget
)
from gdrive_manager import GdriveManager
from platform_profile import CURRENT_PLATFORM, PlatformProfile
from system_utils import SystemUtils
from timetracker.system_utils import SystemUtils as TimeTrackerSystemUtils
from ui.settings_page import SettingsPage

logger = logging.getLogger(__name__)

class TimetrackerTab(SettingsPage):
    def __init__(self, platform: PlatformProfile = CURRENT_PLATFORM):
        super().__init__()
        self.platform = platform

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(self._build_timetracking_group())
        layout.addStretch()
        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

        self.timetracking_enable.stateChanged.connect(lambda state: self.save_nested_setting(config.USER_CONF_TIMETRACKER, "timetracking", bool(state)))
        self._bind_text_setting(
            self.afk_timer_edit, config.USER_CONF_TIMETRACKER_AFK_TIMER,
            parent_key=config.USER_CONF_TIMETRACKER, convert=self._int_or_zero
        )
        self._bind_text_setting(
            self.save_interval_edit, config.USER_CONF_TIMETRACKER_PERIODIC_SAVE,
            parent_key=config.USER_CONF_TIMETRACKER, convert=self._int_or_zero
        )
        self.timetracking_autostart.stateChanged.connect(lambda state: self.save_nested_setting(config.USER_CONF_TIMETRACKER, config.USER_CONF_TIMETRACKER_AUTOSTART, bool(state)))
        self.timetracking_sync.stateChanged.connect(lambda state: self.save_nested_setting(config.USER_CONF_TIMETRACKER, config.USER_CONF_TIMETRACKER_GDRIVE_SYNC, bool(state)))

    def _build_timetracking_group(self):
        timetracker_group = QGroupBox(self.tr("Timetracker"))
        timetracker_layout = QFormLayout(timetracker_group)
        timetracker_layout.setLabelAlignment(Qt.AlignLeft)

        tt_settings = self.user_settings.get(config.USER_CONF_TIMETRACKER, {})
        self.tt_dependent_widgets = []

        # Warning Message
        if self.platform.name != "windows":
            tracking_help = self.tr(
                "Native Wayland tracking is supported on KDE, Hyprland, and GNOME "
                "with the LVNM Shell extension. Other desktops use XWayland."
            )
            self.tt_warning_label = QLabel(tracking_help)
            self.tt_warning_label.setStyleSheet("color: #888; font-style: italic; margin-bottom: 5px;")
            self.tt_warning_label.setWordWrap(True)
            timetracker_layout.addRow(self.tt_warning_label)
            self.tt_dependent_widgets.append(self.tt_warning_label)

        if SystemUtils.is_gnome_desktop():
            self.gnome_extension_message = QLabel(self.tr(
                "GNOME native Wayland tracking requires the LVNM Shell extension. "
                "After installing or updating it, log out and log back in to restart the session."
            ))
            self.gnome_extension_message.setWordWrap(True)
            self.gnome_extension_install_btn = QPushButton(self.tr("Install / Update GNOME Extension"))
            self.gnome_extension_install_btn.setCursor(Qt.PointingHandCursor)
            self.gnome_extension_install_btn.clicked.connect(self._install_gnome_extension)

            gnome_extension_layout = QVBoxLayout()
            gnome_extension_layout.addWidget(self.gnome_extension_message)
            gnome_extension_layout.addWidget(self.gnome_extension_install_btn, 0, Qt.AlignLeft)
            timetracker_layout.addRow(QLabel(self.tr("GNOME integration:")), gnome_extension_layout)

        # Enable Checkbox
        self.timetracking_enable = QCheckBox(self.tr("Enable"))
        self.timetracking_enable.setChecked(tt_settings.get("timetracking", False))
        timetracker_layout.addRow(QLabel(self.tr("Enable timetracking:")), self.timetracking_enable)

        # AFK Idle Timer
        afk_layout = QHBoxLayout()
        self.afk_timer_edit = QLineEdit()
        self.afk_timer_edit.setValidator(QIntValidator(0, 999))
        self.afk_timer_edit.setFixedWidth(60)
        self.afk_timer_edit.setText(str(tt_settings.get(config.USER_CONF_TIMETRACKER_AFK_TIMER, 0)))
        if self.platform.name == "windows":
            afk_suffix = self.tr("minutes")
        else:
            afk_suffix = self.tr("minutes (requires swayidle)")
        self.afk_label_suffix = QLabel(afk_suffix)
        afk_layout.addWidget(self.afk_timer_edit)
        afk_layout.addWidget(self.afk_label_suffix)
        afk_layout.addStretch()
        
        self.afk_label_prefix = QLabel(self.tr("AFK Idle Timer:"))
        timetracker_layout.addRow(self.afk_label_prefix, afk_layout)

        # Periodic Save Interval
        save_interval_layout = QHBoxLayout()
        self.save_interval_edit = QLineEdit()
        self.save_interval_edit.setValidator(QIntValidator(1, 999))
        self.save_interval_edit.setFixedWidth(60)
        self.save_interval_edit.setText(str(tt_settings.get(config.USER_CONF_TIMETRACKER_PERIODIC_SAVE, 3)))
        self.save_label_suffix = QLabel(self.tr("minutes"))
        save_interval_layout.addWidget(self.save_interval_edit)
        save_interval_layout.addWidget(self.save_label_suffix)
        save_interval_layout.addStretch()
        
        self.save_label_prefix = QLabel(self.tr("Periodic Save Interval:"))
        timetracker_layout.addRow(self.save_label_prefix, save_interval_layout)

        # Auto Start timetracking
        self.timetracking_autostart = QCheckBox(self.tr("Automatically Start Time Tracking When Game Launches"))
        self.timetracking_autostart.setChecked(tt_settings.get(config.USER_CONF_TIMETRACKER_AUTOSTART, False))
        self.autostart_label = QLabel(self.tr("Auto Start"))
        timetracker_layout.addRow(self.autostart_label, self.timetracking_autostart)

        # Gdrive sync timetracking
        self.timetracking_sync = QCheckBox(self.tr("Automatically sync timetracker files for games with Gdrive savedata sync enabled"))
        self.timetracking_sync.setChecked(tt_settings.get(config.USER_CONF_TIMETRACKER_GDRIVE_SYNC, False))
        self.tt_sync_label = QLabel(self.tr("Gdrive sync"))
        timetracker_layout.addRow(self.tt_sync_label, self.timetracking_sync)

        self.tt_dependent_widgets.extend([
            self.afk_timer_edit,
            self.afk_label_prefix,
            self.afk_label_suffix,
            self.save_interval_edit,
            self.save_label_prefix,
            self.save_label_suffix,
            self.timetracking_autostart,
            self.autostart_label,
        ])

        # Connect the checkbox signal
        self.timetracking_enable.toggled.connect(self._on_timetracking_toggled)
        
        # Set initial state
        self._on_timetracking_toggled(self.timetracking_enable.isChecked())

        return timetracker_group

    def _install_gnome_extension(self):
        """Install or update the bundled GNOME Shell extension."""
        self.gnome_extension_install_btn.setEnabled(False)
        try:
            TimeTrackerSystemUtils.install_gnome_shell_extension()
        except RuntimeError as error:
            logger.error(f"Failed to install GNOME Shell extension: {error}")
            QMessageBox.critical(
                self,
                self.tr("GNOME Extension Installation Failed"),
                self.tr("The GNOME Shell extension could not be installed:\n{}").format(error),
            )
        else:
            QMessageBox.information(
                self,
                self.tr("GNOME Extension Installed"),
                self.tr(
                    "The LVNM GNOME Shell extension was installed successfully. "
                    "Log out and log back in to restart your GNOME session before using native Wayland tracking."
                ),
            )
        finally:
            self.gnome_extension_install_btn.setEnabled(True)

    @staticmethod
    def _int_or_zero(text):
        return int(text) if text else 0

    def _on_timetracking_toggled(self, checked):
        """Helper to enable/disable all timetracking sub-widgets"""
        for widget in self.tt_dependent_widgets:
            widget.setEnabled(checked)

        self._update_timetracking_sync_state()

    def _update_timetracking_sync_state(self):
        """Evaluates both TT and GDrive state to enable/disable the sync checkbox."""
        is_tt_enabled = self.timetracking_enable.isChecked()
        is_gdrive_connected = GdriveManager.is_logged_in()        
        can_enable = is_tt_enabled and is_gdrive_connected
        self.timetracking_sync.setEnabled(can_enable)
        self.tt_sync_label.setEnabled(can_enable)

    def refresh_active_tab(self):
        self._update_timetracking_sync_state()

