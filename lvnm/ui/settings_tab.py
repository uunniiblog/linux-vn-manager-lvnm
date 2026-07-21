from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, 
    QLabel, QGroupBox, QFormLayout,
    QHBoxLayout, QLineEdit, QPushButton,
    QCheckBox, QFileDialog, QScrollArea, QFrame,
    QGridLayout, QMessageBox, QStyle, QSizePolicy,
    QToolButton, QProgressBar, QDialog, QApplication
)
import threading
from ui.env_var_manager_dialog import EnvVarManagerDialog
from ui.savedata_management_dialog import SavedataManagementDialog
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
from gdrive_manager import GdriveManager, GdriveDeviceFlowWorker

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
        main_layout.addWidget(self._build_savedata_group())
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
        
        # Global Env Variables
        env_label = QLabel(self.tr("Global Env variables:"))
        env_label.setToolTip(self.tr("These environment variables will be automatically selected when adding a new game.\n They will also be automatically applied from the 'Run in Prefix' dialog."))
        settings_layout.addRow(
            env_label,
            self._build_env_var_widget()
        )

        # --- Added SteamGridDB API Key Section ---
        sgdb_container = QHBoxLayout()
        initial_key = self.user_settings.get(config.USER_CONF_SGDB_API_KEY, "")
        self.sgdb_key_edit, secret_layout = self._create_secret_field(initial_key)
        self.sgdb_key_edit.setPlaceholderText(self.tr("Enter your API key..."))
        sgdb_container.addLayout(secret_layout, 1)

        sgdb_link = QLabel('<a href="https://www.steamgriddb.com/profile/preferences/api" style="color: #3498db; text-decoration: none;">🔗 Get Key</a>')
        sgdb_link = QLabel('Get Key: <a href="https://www.steamgriddb.com/profile/preferences/api"> https://www.steamgriddb.com/profile/preferences/api </a>')
        sgdb_link.linkActivated.connect(SystemUtils.open_url)
        sgdb_link.setToolTip(self.tr("Open SteamGridDB API settings in browser"))

        sgdb_container.addWidget(sgdb_link)
        
        settings_layout.addRow(self.tr("SteamGridDB API Key:"), sgdb_container)

        # Log Level + File Logging
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "ERROR"])
        self.log_level_combo.setFixedWidth(200)
        current_log = self.user_settings.get(config.USER_CONF_LOG_LEVEL, "INFO").upper()
        log_map = {"DEBUG": 0, "INFO": 1, "ERROR": 2}
        self.log_level_combo.setCurrentIndex(log_map.get(current_log, 1))

        self.log_to_file_checkbox = QCheckBox(self.tr("Write logging to file"))
        self.log_to_file_checkbox.setChecked(self.user_settings.get(config.USER_CONF_LOG_TO_FILE, False))
        self.log_to_file_checkbox.setToolTip(
            self.tr("Writes application logs to ~/.local/share/lvnm/timetracker_test.log\n"
                    "Requires an app restart to take effect.")
        )

        self.log_wine_traces = QCheckBox(self.tr("Show Wine logs in application logs"))
        self.log_wine_traces.setChecked(self.user_settings.get(config.USER_CONF_LOGS_WINE, True))
        self.log_wine_traces.setToolTip(
            self.tr("Show Wine logs in system logs and write to file if enabled.\nRegardless of this setting you can right click show logs for any game.")
        )

        log_row = QHBoxLayout()
        log_row.addWidget(self.log_level_combo)
        log_row.addWidget(self.log_to_file_checkbox)
        log_row.addWidget(self.log_wine_traces)
        log_row.addStretch()
        settings_layout.addRow(QLabel(self.tr("Log Level:")), log_row)

        return settings_group

    def _on_language_changed(self, index):
        code = self.language_combo.itemData(index)
        self.user_settings.set(config.USER_CONF_LANGUAGE, code)
        QMessageBox.information(
            self,
            self.tr("Language Changed"),
            self.tr("The language change will take effect after restarting the application.")
        )

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

        # Language
        self.language_combo = QComboBox()
        self.language_combo.setFixedWidth(200)
        current_lang = self.user_settings.get(config.USER_CONF_LANGUAGE, "")
        for i, lang in enumerate(config.LANGUAGES):
            self.language_combo.addItem(lang["name"], lang["code"])
            if lang["code"] == current_lang:
                self.language_combo.setCurrentIndex(i)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        appearance_layout.addRow(QLabel(self.tr("Language:")), self.language_combo)
        
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

    def _build_savedata_group(self):
        savedata_group = QGroupBox(self.tr("Savedata Management"))
        savedata_layout = QFormLayout(savedata_group)
        savedata_layout.setLabelAlignment(Qt.AlignLeft)

        # Retrieve current settings
        savedata_settings = self.user_settings.get(config.USER_CONF_SAVEDATA, {})

        # Enable Checkbox
        self.savedata_enable = QCheckBox(self.tr("Enable"))
        self.savedata_enable.setChecked(savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False))
        savedata_layout.addRow(QLabel(self.tr("Savedata management:")), self.savedata_enable)

        # Auto detect checkbox
        auto_detect_label = QLabel(self.tr("Auto Detect Save:"))
        auto_detect_label.setToolTip(self.tr("Automatically tries to auto detect the save data folder for the game after closing the game if it hasn't been set"))
        self.auto_detect_save = QCheckBox(self.tr("Enable"))
        self.auto_detect_save.setChecked(savedata_settings.get(config.USER_CONF_SAVEDATA_AUTO_DETECT, False))
        self.auto_detect_save.setToolTip(self.tr("Automatically tries to auto detect the save data folder for the game after closing the game if it hasn't been set"))
        savedata_layout.addRow(auto_detect_label, self.auto_detect_save)

        # Savedata dialog
        self.manage_savedata_btn = QPushButton(self.tr("Manage Savedata"))
        self.manage_savedata_btn.setFlat(True)
        self.manage_savedata_btn.setStyleSheet("text-align: left; margin-left: 5px; color: palette(link); padding: 4px 10px; margin-top: 0.7em")
        self.manage_savedata_btn.setCursor(Qt.PointingHandCursor)
        self.manage_savedata_btn.clicked.connect(self._open_savedata_manager)

        manage_row = QHBoxLayout()
        manage_row.setContentsMargins(0, 0, 0, 0)
        manage_row.addWidget(self.manage_savedata_btn)
        manage_row.addStretch()
        savedata_layout.addRow(manage_row)

        # Separator for Gdrive section
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 15, 0, 5)

        gdrive_section_title = QLabel(self.tr("Google Drive Options"))
        gdrive_section_title.setStyleSheet("font-weight: bold;color: palette(link);")

        trailing_line = QFrame()
        trailing_line.setFrameShape(QFrame.Shape.HLine)
        trailing_line.setFrameShadow(QFrame.Shadow.Sunken)
        trailing_line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        trailing_line.setStyleSheet("color: rgba(255, 255, 255, 0.1); margin-left: 1em; color: palette(mid);border: none;min-height: 1px;max-height: 1px;")

        header_layout.addWidget(gdrive_section_title)
        header_layout.addWidget(trailing_line)
        savedata_layout.addRow(header_widget)

        # Auto enable Gsync games checkbox
        all_gdrive_label = QLabel(self.tr("Automatically enable:"))
        all_gdrive_label.setToolTip(self.tr("Recommended to enable the sync from the start in secondary devices. Will autofetch and create the savedata folder and avoid conflicts"))
        self.all_gdrive_ckbox = QCheckBox(self.tr("Automatically enables GDrive Sync for all new games (Recommended)"))
        self.all_gdrive_ckbox.setChecked(savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_ALL_GAMES, False))
        self.all_gdrive_ckbox.setToolTip(self.tr("Recommended to enable the sync from the start in secondary devices. Will autofetch and create the savedata folder and avoid conflicts"))
        savedata_layout.addRow(all_gdrive_label, self.all_gdrive_ckbox)

        # Gdrive Client ID
        gdrive_id_label = QLabel(self.tr("Gdrive Client ID:"))
        self.gdrive_client_id_edit, gdrive_id_row = self._create_secret_field(savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_ID, ""))
        savedata_layout.addRow(gdrive_id_label, gdrive_id_row)

        # Gdrive Client Secret
        gdrive_secret_label = QLabel(self.tr("Gdrive Client Secret:"))
        self.gdrive_client_secret_edit, gdrive_secret_row = self._create_secret_field(savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_SECRET, ""))
        savedata_layout.addRow(gdrive_secret_label, gdrive_secret_row)

        # Gdrive status + single toggling button (Sign in <-> Log out)
        status_label = QLabel(self.tr("Gdrive Account:"))

        self.gdrive_status_dot = QLabel("●")
        self.gdrive_status_dot.setFixedWidth(14)

        self.gdrive_status_text = QLabel()

        self.gdrive_auth_btn = QPushButton()
        self.gdrive_auth_btn.setFlat(True)
        self.gdrive_auth_btn.setStyleSheet("text-align: left; color: palette(link); padding: 4px 10px;")
        self.gdrive_auth_btn.setCursor(Qt.PointingHandCursor)
        self.gdrive_auth_btn.clicked.connect(self._on_gdrive_auth_clicked)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.addWidget(self.gdrive_status_dot)
        status_row.addWidget(self.gdrive_status_text)
        status_row.addWidget(self.gdrive_auth_btn)
        status_row.addStretch()
        savedata_layout.addRow(status_label, status_row)

        self._update_gdrive_ui_state()

        # Widgets that only make sense when savedata management is enabled
        self.savedata_dependent_widgets = [
            auto_detect_label,
            self.auto_detect_save,
            gdrive_id_label,
            self.gdrive_client_id_edit,
            gdrive_secret_label,
            self.gdrive_client_secret_edit,
            status_label,
            self.gdrive_status_dot,
            self.gdrive_status_text,
            self.gdrive_auth_btn,
            self.manage_savedata_btn,
            all_gdrive_label,
            self.all_gdrive_ckbox
        ]

        # Connect the checkbox signal
        self.savedata_enable.toggled.connect(self._on_savedata_toggled)

        # Set initial state
        self._on_savedata_toggled(self.savedata_enable.isChecked())

        return savedata_group


    def _open_savedata_manager(self):
        """Opens the dialog to manage savedata."""

        dialog = SavedataManagementDialog(self)
        if dialog.exec():
            log.debug("Save data closed")

    def _create_secret_field(self, initial_value=""):
        """Creates a password-style QLineEdit with a toggle button to reveal/hide the text.
        Returns (line_edit, container_layout)."""
        line_edit = QLineEdit(initial_value)
        line_edit.setEchoMode(QLineEdit.Password)

        toggle_btn = QToolButton()
        toggle_btn.setCheckable(True)
        toggle_btn.setText("👁")
        toggle_btn.setToolTip(self.tr("Show/Hide"))
        toggle_btn.setFixedWidth(28)
        toggle_btn.toggled.connect(
            lambda checked, e=line_edit: e.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(line_edit)
        row.addWidget(toggle_btn)

        return line_edit, row

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

        self._set_folders_enabled(not is_game_running)

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
        self.sgdb_key_edit.textChanged.connect(lambda text: self.save_setting(config.USER_CONF_SGDB_API_KEY, text))
        self.log_level_combo.currentIndexChanged.connect(self.change_log_level)
        self.log_to_file_checkbox.stateChanged.connect(lambda s: self.save_setting(config.USER_CONF_LOG_TO_FILE, bool(s)))
        self.log_wine_traces.stateChanged.connect(lambda s: self.save_setting(config.USER_CONF_LOGS_WINE, bool(s)))
        self.gs_checkbox.stateChanged.connect(lambda s: self.save_setting(config.USER_CONF_GAMESCOPE_ENABLED, bool(s)))
        self.gs_params.textChanged.connect(lambda t: self.save_setting("gamescope_params", t))
        self.timetracking_enable.stateChanged.connect(lambda s: self.save_nested_setting(config.USER_CONF_TIMETRACKER, "timetracking", bool(s)))
        self.afk_timer_edit.textChanged.connect(lambda t: self.save_nested_setting(config.USER_CONF_TIMETRACKER, config.USER_CONF_TIMETRACKER_AFK_TIMER, int(t) if t else 0))
        self.save_interval_edit.textChanged.connect(lambda t: self.save_nested_setting(config.USER_CONF_TIMETRACKER, config.USER_CONF_TIMETRACKER_PERIODIC_SAVE, int(t) if t else 0))
        self.timetracking_autostart.stateChanged.connect(lambda s: self.save_nested_setting(config.USER_CONF_TIMETRACKER, config.USER_CONF_TIMETRACKER_AUTOSTART, bool(s)))
        self.timetracking_sync.stateChanged.connect(lambda s: self.save_nested_setting(config.USER_CONF_TIMETRACKER, config.USER_CONF_TIMETRACKER_GDRIVE_SYNC, bool(s)))
        self.texthooker_btn.clicked.connect(self.browse_texthooker_path)
        self.texthooker_enable.stateChanged.connect(lambda s: self.save_nested_setting(config.USER_CONF_TEXTHOOKER, "enabled", bool(s)))
        self.texthooker_edit.textChanged.connect(lambda t: self.save_nested_setting(config.USER_CONF_TEXTHOOKER, "path", t))
        self.savedata_enable.stateChanged.connect(lambda s: self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_ENABLED, bool(s)))
        self.auto_detect_save.stateChanged.connect(lambda s: self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_AUTO_DETECT, bool(s)))
        self.gdrive_client_id_edit.textChanged.connect(lambda t: self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_ID, t.strip()))
        self.gdrive_client_secret_edit.textChanged.connect(lambda t: self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_SECRET, t.strip()))
        self.all_gdrive_ckbox.stateChanged.connect(lambda s: self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_GDRIVE_ALL_GAMES, bool(s)))

        # Reset gdrive if credentials changed, maybe using new acc or something
        self.gdrive_client_id_edit.textChanged.connect(lambda t: (self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_ID, t),GdriveManager.reset_service_cache()))
        self.gdrive_client_secret_edit.textChanged.connect(lambda t: (self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_SECRET, t),GdriveManager.reset_service_cache()))

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
                "This will permanently delete all .jpg and .png files in:\n{}\n\n"
                "This action cannot be undone. Continue?"
            ).format(folder_path),
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
            self.tr("Select Folder for {}").format(key),
            old_path # Open dialog at the current location
        )

        if new_path and new_path != old_path:
            reply = QMessageBox.question(
                self,
                self.tr("Move files?"),
                self.tr("Do you want to move your data from:\n{old_path}\n\nto:\n\n{new_path}? \n\nNot moving the data will reset all the data for the new folder.").format(old_path=old_path, new_path=new_path),
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

        self._update_timetracking_sync_state()

    def _update_timetracking_sync_state(self):
        """Evaluates both TT and GDrive state to enable/disable the sync checkbox."""
        is_tt_enabled = self.timetracking_enable.isChecked()
        is_gdrive_connected = GdriveManager.is_logged_in()        
        can_enable = is_tt_enabled and is_gdrive_connected
        self.timetracking_sync.setEnabled(can_enable)
        self.tt_sync_label.setEnabled(can_enable)

    def _on_savedata_toggled(self, checked):
        """Helper to enable/disable all savedata sub-widgets"""
        for widget in self.savedata_dependent_widgets:
            widget.setEnabled(checked)
        if checked:
            self._update_gdrive_ui_state()

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

    def _sign_in_gdrive(self):
        """Starts the Google Drive device-flow sign-in using the configured client id/secret."""
        client_id = self.gdrive_client_id_edit.text().strip()
        client_secret = self.gdrive_client_secret_edit.text().strip()

        if not client_id or not client_secret:
            QMessageBox.warning(
                self,
                self.tr("Missing Credentials"),
                self.tr("Please enter both the Google Client ID and Client Secret before signing in.")
            )
            return

        self.gdrive_worker = GdriveDeviceFlowWorker(client_id, client_secret)

        self._gdrive_dialog = QDialog(self)
        self._gdrive_dialog.setWindowTitle(self.tr("Sign in to Google Drive"))
        self._gdrive_dialog.resize(400, 250)
        layout = QVBoxLayout(self._gdrive_dialog)

        self._gdrive_status_label = QLabel(self.tr("Requesting device code..."))
        layout.addWidget(self._gdrive_status_label)

        self._gdrive_code_label = QLabel("")
        self._gdrive_copy_btn = QPushButton(self.tr("Copy"))
        self._gdrive_copy_btn.clicked.connect(self._copy_gdrive_code)

        code_row = QHBoxLayout()
        code_row.addWidget(self._gdrive_code_label)
        code_row.addWidget(self._gdrive_copy_btn)
        code_row.addStretch()
        layout.addLayout(code_row)

        self._gdrive_link_label = QLabel("")
        self._gdrive_link_label.linkActivated.connect(SystemUtils.open_url)
        layout.addWidget(self._gdrive_link_label)

        progress = QProgressBar()
        progress.setRange(0, 0)  # indeterminate spinner
        layout.addWidget(progress)

        self.gdrive_worker.device_code_ready.connect(self._on_gdrive_device_code_ready)
        self.gdrive_worker.login_success.connect(self._on_gdrive_login_success)
        self.gdrive_worker.login_failed.connect(self._on_gdrive_login_failed)
        self.gdrive_worker.login_timeout.connect(self._on_gdrive_login_timeout)

        self._gdrive_dialog.finished.connect(self._cancel_gdrive_worker)

        self.gdrive_worker.start()
        self._gdrive_dialog.exec()
        self._update_gdrive_ui_state() 

    def _copy_gdrive_code(self):
        code = getattr(self, "_gdrive_user_code", "")
        if code:
            QApplication.clipboard().setText(code)

    def _cancel_gdrive_worker(self):
        if hasattr(self, "gdrive_worker") and self.gdrive_worker.isRunning():
            self.gdrive_worker.cancel()

    def _on_gdrive_device_code_ready(self, device_info):
        user_code = device_info.get("user_code", "")
        verification_url = device_info.get("verification_url", "")

        self._gdrive_status_label.setText(self.tr("Enter this code at the link below:"))
        self._gdrive_user_code = user_code

        self._gdrive_code_label.setText(f"<b style='font-size: 18px;'>{user_code}</b>")
        self._gdrive_link_label.setText(f'<a href="{verification_url}" style="color: #3498db;">🔗 {verification_url}</a>')

    def _on_gdrive_login_success(self, token_data):
        GdriveManager.save_credentials(token_data)
        self._gdrive_dialog.accept()
        self._update_gdrive_ui_state()
        QMessageBox.information(self, self.tr("Connected"), self.tr("Successfully signed in to Google Drive."))

    def _on_gdrive_login_failed(self, error_message):
        self._gdrive_dialog.reject()
        QMessageBox.critical(self, self.tr("Sign-in Failed"), error_message)

    def _on_gdrive_login_timeout(self):
        self._gdrive_dialog.reject()
        QMessageBox.warning(self, self.tr("Timed Out"), self.tr("Sign-in timed out. Please try again."))

    def _on_gdrive_auth_clicked(self):
        """Routes to sign-in or logout depending on current state."""
        if GdriveManager.is_logged_in():
            self._logout_gdrive()
            self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_GDRIVE_ALL_GAMES, False)
        else:
            self._sign_in_gdrive()

    def _logout_gdrive(self):
        client_id = self.gdrive_client_id_edit.text().strip()
        client_secret = self.gdrive_client_secret_edit.text().strip()
        GdriveManager.logout(client_id, client_secret)
        self._update_gdrive_ui_state()

    def _update_gdrive_ui_state(self):
        """Updates the status dot/text and toggles the auth button between Sign in / Log out."""
        connected = GdriveManager.is_logged_in()

        if connected:
            self.gdrive_status_dot.setStyleSheet("color: #4caf50;")
            self.gdrive_status_text.setText(self.tr("Connected"))
            self.gdrive_auth_btn.setText(self.tr("Log out"))
            self.all_gdrive_ckbox.setEnabled(True)
        else:
            self.gdrive_status_dot.setStyleSheet("color: #888888;")
            self.gdrive_status_text.setText(self.tr("Not connected"))
            self.gdrive_auth_btn.setText(self.tr("Sign in to Google Drive"))
            self.all_gdrive_ckbox.setEnabled(False)
            self.all_gdrive_ckbox.setChecked(False)

        self._update_timetracking_sync_state()

    def _on_update_found(self, tag, url):
        """Updates the UI label with the link to the new release"""
        new_text = f'{config.VERSION} <a href="{url}" font-weight: bold;"> {self.tr("Newest version available:")} {tag} </a>'
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