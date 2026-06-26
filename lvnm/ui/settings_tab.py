from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, 
    QLabel, QGroupBox, QFormLayout,
    QHBoxLayout, QLineEdit, QPushButton,
    QCheckBox, QFileDialog, QScrollArea, QFrame,
    QGridLayout, QMessageBox, QStyle, QSizePolicy
)
import threading
from ui.env_var_manager_dialog import EnvVarManagerDialog
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from system_utils import SystemUtils
import config
import logging
from settings_manager import SettingsManager
from game_manager import GameManager
from logging_manager import setup_logging
from prefix_manager import PrefixManager
from game_process_manager import GameProcessManager

logger = logging.getLogger(__name__)

class SettingsTab(QWidget):
    CONFIG_FILE = config.USER_SETTINGS

    update_available_signal = Signal(str, str)

    def __init__(self, theme_manager):
        super().__init__()
        self.update_available_signal.connect(self._on_update_found)

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
        main_layout.addWidget(self._build_directories_group())
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
        settings_layout.setLabelAlignment(Qt.AlignLeft)
        
        # Font Folder
        font_layout = QHBoxLayout()
        self.font_edit = QLineEdit(self.user_settings.get(config.USER_CONF_FONT_FOLDER, ""))
        self.font_edit.setPlaceholderText(self.tr("Select folder to symlink fonts..."))
        self.font_btn = QPushButton(self.tr("Browse..."))
        font_layout.addWidget(self.font_edit)
        font_layout.addWidget(self.font_btn)
        settings_layout.addRow(QLabel(self.tr("Font Folder:")), font_layout)
        
        # Gamescope
        gs_layout = QHBoxLayout()
        self.gs_checkbox = QCheckBox(self.tr("Enable"))
        self.gs_checkbox.setChecked(self.user_settings.get(config.USER_CONF_GAMESCOPE_ENABLED, False))
        self.gs_params = QLineEdit(self.user_settings.get(config.USER_CONF_GAMESCOPE_PARAMS, ""))
        self.gs_params.setPlaceholderText(self.tr("Parameters (e.g., -W 1920 -H 1080)"))
        if not config.GAMESCOPE_INSTALLED:
            self.gs_checkbox.setDisabled(True)
            self.gs_params.setDisabled(True)
        gs_layout.addWidget(self.gs_checkbox)
        gs_layout.addWidget(self.gs_params)
        settings_layout.addRow(QLabel(self.tr("Gamescope:")), gs_layout)
        
        # Save Data Management TODO
        # save_layout = QHBoxLayout()
        # self.save_checkbox = QCheckBox(self.tr("Enable"))
        # self.save_edit = QLineEdit(self.user_settings.get(config.USER_CONF_SAVE_DATA_FOLDER, ""))
        # self.save_edit.setPlaceholderText(self.tr("Main folder for save files..."))
        # self.save_btn = QPushButton(self.tr("Browse..."))
        # save_layout.addWidget(self.save_checkbox)
        # save_layout.addWidget(self.save_edit)
        # save_layout.addWidget(self.save_btn)
        # self.save_checkbox.setEnabled(False)
        # self.save_edit.setEnabled(False)
        # self.save_btn.setEnabled(False)
        # settings_layout.addRow(QLabel(self.tr("Save Management:")), save_layout)
        
        # One Game One Prefix TODO
        # self.ogop_checkbox = QCheckBox(self.tr("Enable"))
        # self.ogop_checkbox.setChecked(self.user_settings.get(config.USER_CONF_ONE_GAME_PREFIX, False))
        # self.ogop_checkbox.setEnabled(False)
        # settings_layout.addRow(QLabel(self.tr("One Game One Prefix:")), self.ogop_checkbox)
        
        # Global Env Variables
        env_label = QLabel(self.tr("Global Env variables:"))
        env_label.setToolTip(self.tr("These environment variables will be automatically selected when adding a new game.\n They will also be automatically applied from the 'Run in Prefix' dialog."))
        settings_layout.addRow(
            env_label,
            self._build_env_var_widget()
        )

        # --- Added SteamGridDB API Key Section ---
        sgdb_container = QHBoxLayout()
        self.sgdb_key_edit = QLineEdit()
        self.sgdb_key_edit.setPlaceholderText(self.tr("Enter your API key..."))
        self.sgdb_key_edit.setEchoMode(QLineEdit.Password) 
        self.sgdb_key_edit.setText(self.user_settings.get(config.USER_CONF_SGDB_API_KEY, ""))
        self.sgdb_key_edit.textChanged.connect(
            lambda text: self.save_setting(config.USER_CONF_SGDB_API_KEY, text)
        )

        sgdb_link = QLabel('<a href="https://www.steamgriddb.com/profile/preferences/api" style="color: #3498db; text-decoration: none;">🔗 Get Key</a>')
        sgdb_link = QLabel('Get Key: <a href="https://www.steamgriddb.com/profile/preferences/api"> https://www.steamgriddb.com/profile/preferences/api </a>')
        sgdb_link.linkActivated.connect(SystemUtils.open_url)
        sgdb_link.setToolTip(self.tr("Open SteamGridDB API settings in browser"))

        sgdb_container.addWidget(self.sgdb_key_edit, 1)
        sgdb_container.addWidget(sgdb_link)
        
        settings_layout.addRow(self.tr("SteamGridDB API Key:"), sgdb_container)

        # Log Level
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "ERROR"])
        self.log_level_combo.setFixedWidth(200)
        current_log = self.user_settings.get(config.USER_CONF_LOG_LEVEL, "INFO").upper()
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
        
        self.manage_env_btn = QPushButton(self.tr("Manage Environment Variables"))
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
        appearance_layout.setLabelAlignment(Qt.AlignLeft)
        
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
        current_zoom = self.user_settings.get(config.USER_CONF_UI_ZOOM, 1.0)
        zoom_map = {0.7: 0, 0.8: 1, 0.9: 2, 1.0: 3, 1.1: 4, 1.25: 5, 1.35: 6, 1.5: 7, 1.75: 8}
        self.zoom_combo.setCurrentIndex(zoom_map.get(current_zoom, 2))
        self.zoom_combo.currentIndexChanged.connect(self.change_zoom)
        appearance_layout.addRow(QLabel(self.tr("UI Zoom:")), self.zoom_combo)

        return appearance_group

    def _build_timetracking_group(self):
        timetracker_group = QGroupBox(self.tr("Timetracker"))
        timetracker_layout = QFormLayout(timetracker_group)
        timetracker_layout.setLabelAlignment(Qt.AlignLeft)

        tt_settings = self.user_settings.get(config.USER_CONF_TIMETRACKER, {})

        # Warning Message
        self.tt_warning_label = QLabel(self.tr("In Desktops other than KDE it only works through XWayland. Check github for details."))
        self.tt_warning_label.setStyleSheet("color: #888; font-style: italic; margin-bottom: 5px;")
        self.tt_warning_label.setWordWrap(True)
        timetracker_layout.addRow(self.tt_warning_label)

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
        self.afk_label_suffix = QLabel(self.tr("minutes (requires swayidle)"))
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
        self.save_interval_edit.setText(str(tt_settings.get(config.USER_CONF_TIMETRACKER_PERIODIC_SAVE, 0)))
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

        self.tt_dependent_widgets = [
            self.tt_warning_label,
            self.afk_timer_edit,
            self.afk_label_prefix,
            self.afk_label_suffix,
            self.save_interval_edit,
            self.save_label_prefix,
            self.save_label_suffix,
            self.timetracking_autostart,
            self.autostart_label
        ]

        # Connect the checkbox signal
        self.timetracking_enable.toggled.connect(self._on_timetracking_toggled)
        
        # Set initial state
        self._on_timetracking_toggled(self.timetracking_enable.isChecked())

        return timetracker_group

    def _build_texthooking_group(self):
        texthooker_group = QGroupBox(self.tr("Texthooker"))
        texthooker_layout = QFormLayout(texthooker_group)
        texthooker_layout.setLabelAlignment(Qt.AlignLeft)

        # Retrieve current settings
        th_settings = self.user_settings.get(config.USER_CONF_TEXTHOOKER, {})

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

    def _build_directories_group(self):
        directories_group = QGroupBox(self.tr("Directories"))
        directories_layout = QFormLayout(directories_group)
        directories_layout.setLabelAlignment(Qt.AlignLeft)

        self.folder_label = QLabel(self.tr("Folder configuration paths. Changing the folder will move all current files in the folder to the new selected folder.\nUse an empty folder if modifying them. Restart the application after changing any of them."))
        self.folder_label.setStyleSheet("color: #888; font-style: italic; margin-bottom: 5px;")
        self.folder_label.setWordWrap(True)
        directories_layout.addRow(self.folder_label)

        game_manager = GameProcessManager.get_instance()
        is_game_running = len(game_manager.active_runners) > 0
        self.folder_widgets = []
        self.folder_inputs = []

        folder_settings = [
            (self.tr("Prefixes Dir:"), config.USER_CONF_PREFIXES_PATH, config.PREFIXES_DIR),
            (self.tr("Wine Runners Dir:"), config.USER_CONF_WINE_RUNNERS_PATH, config.WINE_RUNNERS_DIR),
            (self.tr("Proton Runners Dir:"), config.USER_CONF_PROTON_RUNNERS_PATH, config.PROTON_RUNNERS_DIR),
            (self.tr("Covers Dir:"), config.USER_CONF_COVERS_PATH, config.COVERS_DIR),
            (self.tr("Timetrack Logs Dir:"), config.USER_CONF_LOGS_PATH, config.LOG_DIR),
        ]

        BROWSE_WIDTH = 120
        TRASH_WIDTH = 36
        LAYOUT_SPACING = 6
        
        for label_text, key, default_val in folder_settings:
            layout = QHBoxLayout()
            layout.setSpacing(LAYOUT_SPACING)
            
            current_val = self.user_settings.get(key, str(default_val))
            
            edit = QLineEdit(current_val)
            edit.setPlaceholderText(self.tr("Select folder..."))
            edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            btn = QPushButton(self.tr("Browse..."))

            # Disable if a game is already running
            edit.setEnabled(not is_game_running)
            btn.setEnabled(not is_game_running)
            
            layout.addWidget(edit, stretch=1)

            # Add a trash button exclusively for the Covers directory row
            if key == config.USER_CONF_COVERS_PATH:
                self.covers_edit = edit

                btn.setFixedWidth(BROWSE_WIDTH)
                layout.addWidget(btn)

                self.covers_delete_btn = QPushButton()
                self.covers_delete_btn.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
                self.covers_delete_btn.setToolTip(self.tr("Delete all covers in this folder"))
                self.covers_delete_btn.setEnabled(not is_game_running)
                self.covers_delete_btn.setFixedSize(TRASH_WIDTH, TRASH_WIDTH)

                layout.addWidget(self.covers_delete_btn)
                self.folder_widgets.append(self.covers_delete_btn)

            else:
                btn.setFixedWidth(BROWSE_WIDTH + LAYOUT_SPACING + TRASH_WIDTH)
                layout.addWidget(btn)

            directories_layout.addRow(QLabel(label_text), layout)
            
            # Store references so we can connect their signals later
            self.folder_inputs.append((key, edit, btn))
            self.folder_widgets.extend([edit, btn])

        return directories_group

    def _build_sysinfo_group(self):
        sysinfo_group = QGroupBox(self.tr("System Info"))
        sysinfo_layout = QFormLayout(sysinfo_group)
        sysinfo_layout.setLabelAlignment(Qt.AlignLeft)
        
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
            sysinfo_layout.addRow(QLabel(f"{pkg}:"), QLabel(self.check(installed)))
        
        return sysinfo_group

    def _build_about_group(self):
        about_group = QGroupBox(self.tr("About"))
        about_layout = QFormLayout(about_group)
        about_layout.setLabelAlignment(Qt.AlignLeft)

        self.version_label_val = QLabel(config.VERSION)
        about_layout.addRow(QLabel(self.tr("LVNM version:")), self.version_label_val)
        
        github_label = QLabel(f'<a href="{config.GIT_URL}">{config.GIT_URL}</a>')
        github_label.linkActivated.connect(SystemUtils.open_url)
        about_layout.addRow(QLabel(self.tr("Github:")), github_label)

        wineprefixes_label = QLabel(f'<a href="{config.WINEPREFIX_URL}">{config.WINEPREFIX_URL}</a>')
        wineprefixes_label.linkActivated.connect(SystemUtils.open_url)

        about_layout.addRow(QLabel(self.tr("Wineprefixes guide:")), wineprefixes_label)

        threading.Thread(target=self._check_for_updates, daemon=True).start()

        return about_group

    # ==========================================
    # Real Methods

    def _connect_signals(self):
        self.font_btn.clicked.connect(self.browse_font_folder)
        self.font_edit.textChanged.connect(lambda t: self.save_setting(config.USER_CONF_FONT_FOLDER, t))
        self.gs_checkbox.stateChanged.connect(lambda s: self.save_setting(config.USER_CONF_GAMESCOPE_ENABLED, bool(s)))
        self.gs_params.textChanged.connect(lambda t: self.save_setting("gamescope_params", t))
        # self.ogop_checkbox.stateChanged.connect(lambda s: self.save_setting("one_game_one_prefix", bool(s)))
        self.timetracking_enable.stateChanged.connect(lambda s: self.save_nested_setting("timetracker", "timetracking", bool(s)))
        self.afk_timer_edit.textChanged.connect(lambda t: self.save_nested_setting("timetracker", config.USER_CONF_TIMETRACKER_AFK_TIMER, int(t) if t else 0))
        self.save_interval_edit.textChanged.connect(lambda t: self.save_nested_setting("timetracker", config.USER_CONF_TIMETRACKER_PERIODIC_SAVE, int(t) if t else 0))
        self.timetracking_autostart.stateChanged.connect(lambda s: self.save_nested_setting("timetracker", config.USER_CONF_TIMETRACKER_AUTOSTART, bool(s)))
        self.texthooker_btn.clicked.connect(self.browse_texthooker_path)
        self.texthooker_enable.stateChanged.connect(lambda s: self.save_nested_setting(config.USER_CONF_TEXTHOOKER, "enabled", bool(s)))
        self.texthooker_edit.textChanged.connect(lambda t: self.save_nested_setting(config.USER_CONF_TEXTHOOKER, "path", t))

        # Connect signals for dynamic folder inputs
        for key, edit_widget, btn_widget in self.folder_inputs:
            self._connect_folder_signal(key, edit_widget, btn_widget)

        self.covers_delete_btn.clicked.connect(self._on_delete_covers_clicked)

        gp_manager = GameProcessManager.get_instance()
        gp_manager.game_started.connect(lambda: self._set_folders_enabled(False))
        gp_manager.game_stopped.connect(lambda: self._check_should_re_enable_folders())

    def _connect_folder_signal(self, key, edit_widget, btn_widget):
        """Helper to bind signals without loop closure issues."""
        btn_widget.clicked.connect(lambda: self.browse_directory_for_widget(edit_widget, key))
        edit_widget.textChanged.connect(lambda t: self.save_setting(key, t))
        
    def _on_delete_covers_clicked(self):
        """Show confirmation dialog then delete all cover images in the selected folder."""
        folder_path = self.covers_edit.text().strip()
        if not folder_path:
            QMessageBox.warning(self, self.tr("No Folder"), self.tr("No covers folder is currently set."))
            return

        reply = QMessageBox.question(
            self,
            self.tr("Delete Covers"),
            self.tr(
                f"This will permanently delete all .jpg and .png files in:\n{folder_path}\n\n"
                "This action cannot be undone. Continue?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                cover_extensions = ["*.jpg", "*.png", "*.JPG", "*.PNG"]
                SystemUtils.delete_covers_in_folder(folder_path, cover_extensions)
            except RuntimeError as e:
                QMessageBox.critical(
                    self,
                    self.tr("Error"),
                    self.tr(str(e))
                )
        
    def browse_directory_for_widget(self, edit_widget, key):
        """Browse directory for folders, ask confirm and move files"""
        old_path = edit_widget.text()        
        new_path = QFileDialog.getExistingDirectory(
            self, 
            self.tr(f"Select Folder for {key}"), 
            old_path # Open dialog at the current location
        )

        if new_path and new_path != old_path:
            reply = QMessageBox.question(
                self,
                self.tr("Move files?"),
                self.tr(f"Do you want to move your data from:\n{old_path}\n\nto:\n\n{new_path}? \n\nNot moving the data will reset all the data for the new folder."),
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                success = SystemUtils.move_directory_contents(old_path, new_path)
                if success:
                    if key in [config.USER_CONF_WINE_RUNNERS_PATH, config.USER_CONF_PROTON_RUNNERS_PATH, config.USER_CONF_PREFIXES_PATH]:
                        PrefixManager.relocate_metadata_paths(old_path, new_path)
                else:
                    QMessageBox.warning(self, self.tr("Error"), self.tr("Failed to move some files. Check logs."))

            edit_widget.setText(new_path)

    def _set_folders_enabled(self, enabled: bool):
        """Disables or enables all folder selection widgets."""
        for widget in self.folder_widgets:
            widget.setEnabled(enabled)
        
        if not enabled:
            self.folder_label.setText(self.tr("Folder configuration is locked while a game is running."))
        else:
            self.folder_label.setText(self.tr("Folder configuration paths. Changing the folder will move all current files in the folder to the new selected folder.\nUse an empty folder if modifying them. Restart the application after changing any of them."))

    def _check_should_re_enable_folders(self):
        """Checks if all games are closed before re-enabling inputs."""
        if len(GameProcessManager.get_instance().active_runners) == 0:
            self._set_folders_enabled(True)
    
    def _on_timetracking_toggled(self, checked):
        """Helper to enable/disable all timetracking sub-widgets"""
        for widget in self.tt_dependent_widgets:
            widget.setEnabled(checked)

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
        self.save_setting(config.USER_CONF_UI_ZOOM, new_zoom)        
        SystemUtils.apply_ui_zoom(new_zoom)
        self.theme_manager.update_theme()

    def change_log_level(self, index):
        mapping = {0: "DEBUG", 1: "INFO", 2: "ERROR"}
        new_level = mapping[index]
        self.save_setting(config.USER_CONF_LOG_LEVEL, new_level)        
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

    def _check_for_updates(self):
        """Background thread search update"""
        tag, url = SystemUtils.get_latest_release_info()
        if tag and url:
            current = config.VERSION.lstrip('v')
            latest = tag.lstrip('v')
            if latest != current:
                self.update_available_signal.emit(tag, url)

    def _on_update_found(self, tag, url):
        """Updates the UI label with the link to the new release"""
        new_text = f'{config.VERSION} <a href="{url}" font-weight: bold;"> Newest version available: {tag} </a>'
        self.version_label_val.setText(new_text)

    def save_setting(self, key, value):
        try:
            self.user_settings.set(key, value)
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(str(e))
            )

    def save_nested_setting(self, parent_key, child_key, value):
        try:
            parent_dict = self.user_settings.get(parent_key, {})
            if not isinstance(parent_dict, dict):
                parent_dict = {}
            parent_dict[child_key] = value
            self.user_settings.set(parent_key, parent_dict)
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(str(e))
            )