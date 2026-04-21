from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, 
    QLabel, QGroupBox, QFormLayout,
    QHBoxLayout, QLineEdit, QPushButton,
    QCheckBox, QFileDialog, QScrollArea, QFrame,
    QGridLayout
)
from ui.env_var_manager_dialog import EnvVarManagerDialog
from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from system_utils import SystemUtils
import config
import logging
from settings_manager import SettingsManager
from game_manager import GameManager
from logging_manager import setup_logging

logger = logging.getLogger(__name__)

class SettingsTab(QWidget):
    CONFIG_FILE = config.USER_SETTINGS

    def __init__(self, theme_manager):
        super().__init__()
        self.theme_manager = theme_manager
        self.user_settings = SettingsManager()
        self.global_env_checkboxes = {}

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)
        
        main_layout.addWidget(self._build_settings_group())
        main_layout.addWidget(self._build_appearance_group())
        main_layout.addWidget(self._build_timetracking_group())
        main_layout.addWidget(self._build_texthooking_group())
        main_layout.addWidget(self._build_sysinfo_group())
        main_layout.addWidget(self._build_about_group())
        main_layout.addStretch()

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

        self._connect_signals()

    # ==========================================
    # Interface methods

    def _build_settings_group(self):
        settings_group = QGroupBox(self.tr("Settings"))
        settings_layout = QFormLayout(settings_group)    
        
        # Font Folder
        font_layout = QHBoxLayout()
        self.font_edit = QLineEdit(self.user_settings.get("font_folder", ""))
        self.font_edit.setPlaceholderText(self.tr("Select folder to symlink fonts..."))
        self.font_btn = QPushButton(self.tr("Browse..."))
        font_layout.addWidget(self.font_edit)
        font_layout.addWidget(self.font_btn)
        settings_layout.addRow(QLabel(self.tr("Font Folder:")), font_layout)
        
        # Gamescope
        gs_layout = QHBoxLayout()
        self.gs_checkbox = QCheckBox(self.tr("Enable"))
        self.gs_checkbox.setChecked(self.user_settings.get("gamescope_enabled", False))
        self.gs_params = QLineEdit(self.user_settings.get("gamescope_params", ""))
        self.gs_params.setPlaceholderText(self.tr("Parameters (e.g., -W 1920 -H 1080)"))
        if not config.GAMESCOPE_INSTALLED:
            self.gs_checkbox.setDisabled(True)
            self.gs_params.setDisabled(True)
        gs_layout.addWidget(self.gs_checkbox)
        gs_layout.addWidget(self.gs_params)
        settings_layout.addRow(QLabel(self.tr("Gamescope:")), gs_layout)
        
        # Save Data Management
        save_layout = QHBoxLayout()
        self.save_checkbox = QCheckBox(self.tr("Enable"))
        self.save_edit = QLineEdit(self.user_settings.get("save_folder", ""))
        self.save_edit.setPlaceholderText(self.tr("Main folder for save files..."))
        self.save_btn = QPushButton(self.tr("Browse..."))
        save_layout.addWidget(self.save_checkbox)
        save_layout.addWidget(self.save_edit)
        save_layout.addWidget(self.save_btn)
        self.save_checkbox.setEnabled(False)
        self.save_edit.setEnabled(False)
        self.save_btn.setEnabled(False)
        settings_layout.addRow(QLabel(self.tr("Save Management:")), save_layout)
        
        # One Game One Prefix
        self.ogop_checkbox = QCheckBox(self.tr("Enable"))
        self.ogop_checkbox.setChecked(self.user_settings.get("one_game_one_prefix", False))
        self.ogop_checkbox.setEnabled(False)
        settings_layout.addRow(QLabel(self.tr("One Game One Prefix:")), self.ogop_checkbox)
        
        # Global Env Variables
        settings_layout.addRow(
            QLabel(self.tr("Global Env variables:")),
            self._build_env_var_widget()
        )

        # Log Level
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "ERROR"])
        self.log_level_combo.setFixedWidth(200)
        current_log = self.user_settings.get("log_level", "INFO").upper()
        log_map = {"DEBUG": 0, "INFO": 1, "ERROR": 2}
        self.log_level_combo.setCurrentIndex(log_map.get(current_log, 1))
        self.log_level_combo.currentIndexChanged.connect(self.change_log_level)
        settings_layout.addRow(QLabel(self.tr("Log Level:")), self.log_level_combo)

        return settings_group

    def get_env_variables_list(self):
        """Fetches the custom list or falls back to default config."""
        vars_list = self.user_settings.get(config.USER_CONF_ENV_VARIABLE_LIST, None)
        if vars_list is None:
            vars_list = config.ENV_VARIABLES
            self.user_settings.set(config.USER_CONF_ENV_VARIABLE_LIST, vars_list)
        return vars_list
    
    def _build_env_var_widget(self):
        """Builds the collapsible env var checkbox grid."""
        self.env_var_container = QWidget()
        self.env_var_main_layout = QVBoxLayout(self.env_var_container)
        self.env_var_main_layout.setContentsMargins(0, 0, 0, 0)
        self.env_var_main_layout.setSpacing(4)

        # Widget to hold the dynamic grid
        self.env_grid_widget = QWidget()
        self.env_var_main_layout.addWidget(self.env_grid_widget)

        # Control Buttons Layer
        btn_layout = QHBoxLayout()
        self.env_expand_btn = QPushButton(self.tr("Show more..."))
        self.env_expand_btn.setFlat(True)
        self.env_expand_btn.setStyleSheet("text-align: left; color: palette(link); padding: 4px 10px;")
        self.env_expand_btn.setCursor(Qt.PointingHandCursor)
        self.env_expand_btn.clicked.connect(self._toggle_env_extra)
        
        self.manage_env_btn = QPushButton(self.tr("Manage Variables"))
        self.manage_env_btn.setFlat(True)
        self.manage_env_btn.setStyleSheet("text-align: left; margin-left: 5px; color: palette(link); padding: 4px 10px;")
        self.manage_env_btn.setCursor(Qt.PointingHandCursor)
        self.manage_env_btn.clicked.connect(self._open_env_manager)

        btn_layout.addWidget(self.env_expand_btn)
        btn_layout.addWidget(self.manage_env_btn)
        btn_layout.addStretch()
        
        self.env_var_main_layout.addLayout(btn_layout)

        # Populate the grid initially
        self._refresh_env_grid()

        return self.env_var_container

    def _open_env_manager(self):
        """Opens the dialog to add/remove/edit environment variables."""

        is_expanded = (
            hasattr(self, '_extra_checkboxes') and
            bool(self._extra_checkboxes) and
            self._extra_checkboxes[0].isVisible()
        )

        current_vars = self.get_env_variables_list()
        dialog = EnvVarManagerDialog(current_vars, self)
        if dialog.exec():
            new_vars = dialog.get_vars()
            self.user_settings.set(config.USER_CONF_ENV_VARIABLE_LIST, new_vars)

            # Clean ghost variables
            current_keys = [var["key"] for var in new_vars]
            GameManager.cleanup_env_vars(current_keys)

            # Refresh
            self._refresh_env_grid()
            if is_expanded:
                self._toggle_env_extra()

    def _refresh_env_grid(self):
        """Rebuilds the checkbox grid dynamically based on settings."""
        # Clear existing layout safely
        if self.env_grid_widget.layout():
            QWidget().setLayout(self.env_grid_widget.layout()) 

        grid = QGridLayout(self.env_grid_widget)
        grid.setHorizontalSpacing(30)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)

        global_env_var = self.user_settings.get(config.USER_CONF_GLOBAL_VARIABLES, {})
        self.global_env_checkboxes = {}
        self._extra_checkboxes = []
        vars_list = self.get_env_variables_list()

        for i, var in enumerate(vars_list):
            var_id = var["id"]
            cb = QCheckBox(self.tr(var.get("name") or var_id))
            cb.setToolTip(f"{var['key']}={var['value']}")
            cb.setChecked(global_env_var.get(var_id, False))
            cb.stateChanged.connect(
                lambda s, vid=var_id: self.save_nested_setting(config.USER_CONF_GLOBAL_VARIABLES, vid, bool(s))
            )
            self.global_env_checkboxes[var_id] = cb
            grid.addWidget(cb, i // 2, i % 2)
            
            # Hide items beyond the first row (2 items)
            if i >= 2:
                cb.setVisible(False)
                self._extra_checkboxes.append(cb)

        # Reset button visibility state
        self._toggle_env_extra(force_hide=True)

    def _add_env_rows(self, vars_list, target_layout, global_env_var):
        """Populates a layout with env var checkboxes, two per row."""
        grid = QGridLayout()
        grid.setHorizontalSpacing(30)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 0)  # columns only as wide as needed
        grid.setColumnStretch(1, 0)
        
        for i, var in enumerate(vars_list):
            var_id = var["id"]
            cb = QCheckBox(self.tr(var.get("name") or var_id))
            cb.setToolTip(f"{var['key']}={var['value']}")
            cb.setChecked(global_env_var.get(var_id, False))
            cb.stateChanged.connect(
                lambda s, vid=var_id: self.save_nested_setting(config.USER_CONF_GLOBAL_VARIABLES, vid, bool(s))
            )
            self.global_env_checkboxes[var_id] = cb
            grid.addWidget(cb, i // 2, i % 2)  # row, col

        target_layout.addLayout(grid)

    def _build_appearance_group(self):
        appearance_group = QGroupBox(self.tr("Appearance"))
        appearance_layout = QFormLayout(appearance_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([self.tr("System Default"), self.tr("Light"), self.tr("Dark")])
        self.theme_combo.setFixedWidth(200)
        current = self.theme_manager.get_theme_mode()
        mapping = {"auto": 0, "light": 1, "dark": 2}
        self.theme_combo.setCurrentIndex(mapping.get(current, 0))
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        appearance_layout.addRow(QLabel(self.tr("Theme:")), self.theme_combo)
        
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["70%", "80%", "90%", "100%", "110%", "125%", "135%", "150%", "175%"])
        self.zoom_combo.setFixedWidth(200)
        current_zoom = self.user_settings.get("ui_zoom", 1.0)
        zoom_map = {0.7: 0, 0.8: 1, 0.9: 2, 1.0: 3, 1.1: 4, 1.25: 5, 1.35: 6, 1.5: 7, 1.75: 8}
        self.zoom_combo.setCurrentIndex(zoom_map.get(current_zoom, 2))
        self.zoom_combo.currentIndexChanged.connect(self.change_zoom)
        appearance_layout.addRow(QLabel(self.tr("UI Zoom:")), self.zoom_combo)

        return appearance_group

    def _build_timetracking_group(self):
        timetracker_group = QGroupBox(self.tr("Timetracker"))
        timetracker_layout = QFormLayout(timetracker_group)

        tt_settings = self.user_settings.get("timetracker", {})

        # Warning Message
        warning_label = QLabel(self.tr("Timetracking only works in KDE 6 Desktop and Gamescope session."))
        warning_label.setStyleSheet("color: #888; font-style: italic; margin-bottom: 5px;")
        warning_label.setWordWrap(True)
        timetracker_layout.addRow(warning_label)

        # Enable Checkbox
        self.timetracking_enable = QCheckBox(self.tr("Enable"))
        self.timetracking_enable.setChecked(tt_settings.get("timetracking", False))
        timetracker_layout.addRow(QLabel(self.tr("Enable timetracking:")), self.timetracking_enable) 

        # AFK Idle Timer
        afk_layout = QHBoxLayout()
        self.afk_timer_edit = QLineEdit()
        self.afk_timer_edit.setValidator(QIntValidator(0, 999))
        self.afk_timer_edit.setFixedWidth(60)
        self.afk_timer_edit.setText(str(tt_settings.get("afk_timer", 0)))
        afk_layout.addWidget(self.afk_timer_edit)
        afk_layout.addWidget(QLabel(self.tr("minutes (requires swayidle)")))
        afk_layout.addStretch()
        timetracker_layout.addRow(QLabel(self.tr("AFK Idle Timer:")), afk_layout)

        # Periodic Save Interval
        save_interval_layout = QHBoxLayout()
        self.save_interval_edit = QLineEdit()
        self.save_interval_edit.setValidator(QIntValidator(1, 999))
        self.save_interval_edit.setFixedWidth(60)
        self.save_interval_edit.setText(str(tt_settings.get("log_periodic_save", 0)))
        save_interval_layout.addWidget(self.save_interval_edit)
        save_interval_layout.addWidget(QLabel(self.tr("minutes")))
        save_interval_layout.addStretch()
        timetracker_layout.addRow(QLabel(self.tr("Periodic Save Interval:")), save_interval_layout)

        # Auto Start timetracking
        self.timetracking_autostart = QCheckBox(self.tr("Automatically Start Time Tracking When Game Launches"))
        self.timetracking_autostart.setChecked(tt_settings.get("autostart", False))
        timetracker_layout.addRow(QLabel(self.tr("Auto Start")), self.timetracking_autostart) 

        return timetracker_group

    def _build_texthooking_group(self):
        texthooker_group = QGroupBox(self.tr("Texthooker"))
        texthooker_layout = QFormLayout(texthooker_group)

        # Retrieve current settings
        th_settings = self.user_settings.get("texthooker", {})

        # Enable Checkbox
        self.texthooker_enable = QCheckBox(self.tr("Enable"))
        self.texthooker_enable.setChecked(th_settings.get("enabled", False))
        texthooker_layout.addRow(QLabel(self.tr("Enable texthooking:")), self.texthooker_enable)

        # Texthooker Path 
        path_layout = QHBoxLayout()
        self.texthooker_edit = QLineEdit(th_settings.get("path", ""))
        self.texthooker_edit.setPlaceholderText(self.tr("Select texthooker executable (e.g., Textractor.exe)..."))
        
        self.texthooker_btn = QPushButton(self.tr("Browse..."))
        
        path_layout.addWidget(self.texthooker_edit)
        path_layout.addWidget(self.texthooker_btn)
        
        texthooker_layout.addRow(QLabel(self.tr("Texthooker Path:")), path_layout)

        return texthooker_group

    def _build_sysinfo_group(self):
        sysinfo_group = QGroupBox(self.tr("System Info"))
        sysinfo_layout = QFormLayout(sysinfo_group)
        
        sys_data = SystemUtils.get_system_info()
        software = SystemUtils.get_software_support()
        runtime = SystemUtils.get_runtime_type()
        version_label = sys_data.get('app_version')

        if runtime == "appimage":
            version_label += "  📦 AppImage"
        else:
            version_label += "  (native)"

        sysinfo_layout.addRow(QLabel(self.tr("LVNM Version:")), QLabel(version_label))
        sysinfo_layout.addRow(QLabel(self.tr("OS:")), QLabel(sys_data.get('os')))
        sysinfo_layout.addRow(QLabel(self.tr("Kernel:")), QLabel(sys_data.get('kernel')))
        sysinfo_layout.addRow(QLabel(self.tr("Desktop:")), QLabel(f"{sys_data.get('desktop_environment')} - {sys_data.get('session_type')}"))
        sysinfo_layout.addRow(QLabel(self.tr("CPU:")), QLabel(sys_data.get('cpu')))
        sysinfo_layout.addRow(QLabel(self.tr("GPU:")), QLabel(sys_data.get('gpu')))
        sysinfo_layout.addRow(QLabel(self.tr("Vulkan Support:")), QLabel(self.check(software.get('vulkan_support'))))
        sysinfo_layout.addRow(QLabel(self.tr("Gamescope:")), QLabel(self.check(software.get('gamescope'))))
        sysinfo_layout.addRow(QLabel(self.tr("Umu-run:")), QLabel(self.check(software.get('umu_run'))))
        sysinfo_layout.addRow(QLabel(self.tr("Winetricks:")), QLabel(self.check(software.get('winetricks'))))

        for pkg, installed in software.get('gstreamer_packages', {}).items():
            sysinfo_layout.addRow(QLabel(f"  {pkg}:"), QLabel(self.check(installed)))
        
        return sysinfo_group

    def _build_about_group(self):
        about_group = QGroupBox(self.tr("About"))
        about_layout = QFormLayout(about_group)
        about_layout.addRow(QLabel(self.tr("LVNM version:")), QLabel(config.VERSION))
        github_label = QLabel(f'<a href="{config.GIT_URL}">{config.GIT_URL}</a>')
        github_label.setOpenExternalLinks(True)
        about_layout.addRow(QLabel(self.tr("Github:")), github_label)
        wineprefixes_label = QLabel(f'<a href="{config.WINEPREFIX_URL}">{config.WINEPREFIX_URL}</a>')
        wineprefixes_label.setOpenExternalLinks(True)
        about_layout.addRow(QLabel(self.tr("Wineprefixes guide:")), wineprefixes_label)
        return about_group

    # ==========================================
    # Real Methods

    def _connect_signals(self):
        self.font_btn.clicked.connect(self.browse_font_folder)
        self.font_edit.textChanged.connect(lambda t: self.save_setting("font_folder", t))
        self.gs_checkbox.stateChanged.connect(lambda s: self.save_setting("gamescope_enabled", bool(s)))
        self.gs_params.textChanged.connect(lambda t: self.save_setting("gamescope_params", t))
        self.ogop_checkbox.stateChanged.connect(lambda s: self.save_setting("one_game_one_prefix", bool(s)))
        self.timetracking_enable.stateChanged.connect(lambda s: self.save_nested_setting("timetracker", "timetracking", bool(s)))
        self.afk_timer_edit.textChanged.connect(lambda t: self.save_nested_setting("timetracker", "afk_timer", int(t) if t else 0))
        self.save_interval_edit.textChanged.connect(lambda t: self.save_nested_setting("timetracker", "log_periodic_save", int(t) if t else 0))
        self.timetracking_autostart.stateChanged.connect(lambda s: self.save_nested_setting("timetracker", "autostart", bool(s)))
        self.texthooker_btn.clicked.connect(self.browse_texthooker_path)
        self.texthooker_enable.stateChanged.connect(lambda s: self.save_nested_setting("texthooker", "enabled", bool(s)))
        self.texthooker_edit.textChanged.connect(lambda t: self.save_nested_setting("texthooker", "path", t))

    def _toggle_env_extra(self, force_hide=False):
        """Toggles the visibility of checkboxes beyond the first row."""
        if not hasattr(self, '_extra_checkboxes') or not self._extra_checkboxes:
            self.env_expand_btn.setVisible(False)
            return

        self.env_expand_btn.setVisible(True)
        expanded = True if force_hide else self._extra_checkboxes[0].isVisible()

        for cb in self._extra_checkboxes:
            cb.setVisible(not expanded)
            
        self.env_expand_btn.setText(
            self.tr("Show less") if not expanded else self.tr("Show more...")
        )

    def change_theme(self, index):
        mapping = {0: "auto", 1: "light", 2: "dark"}
        self.theme_manager.settings.setValue("theme_mode", mapping[index])        
        self.theme_manager.update_theme()

    def change_zoom(self, index):
        mapping = {0: 0.7, 1: 0.8, 2: 0.9, 3: 1.0, 4: 1.1, 5: 1.25, 6: 1.35, 7: 1.5, 8: 1.75}
        new_zoom = mapping[index]
        self.save_setting("ui_zoom", new_zoom)        
        SystemUtils.apply_ui_zoom(new_zoom)
        self.theme_manager.update_theme()

    def change_log_level(self, index):
        mapping = {0: "DEBUG", 1: "INFO", 2: "ERROR"}
        new_level = mapping[index]
        self.save_setting("log_level", new_level)        
        config.LOG_LEVEL = new_level
        setup_logging(new_level)

    def check(self, val): 
        return "✅" if val else "❌"

    def browse_font_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("Select Font Folder"), "")
        if folder:
            self.font_edit.setText(folder)
    
    def browse_texthooker_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            self.tr("Select Texthooker Executable"), 
            "", 
            self.tr("Executables (*.exe);;All Files (*)")
        )
        if file_path:
            self.texthooker_edit.setText(file_path)

    def save_setting(self, key, value):
        self.user_settings.set(key, value)

    def save_nested_setting(self, parent_key, child_key, value):
        parent_dict = self.user_settings.get(parent_key, {})
        if not isinstance(parent_dict, dict):
            parent_dict = {}
        parent_dict[child_key] = value
        self.user_settings.set(parent_key, parent_dict)