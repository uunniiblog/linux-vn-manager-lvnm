import config
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, 
    QLabel, QGroupBox, QFormLayout,
    QHBoxLayout, QLineEdit, QPushButton,
    QCheckBox, QFileDialog, QScrollArea, QFrame,
    QGridLayout, QMessageBox, QStyle, QSizePolicy,
    QRadioButton, QButtonGroup
)
from ui.env_var_manager_dialog import EnvVarManagerDialog
from ui.settings_page import SettingsPage
from PySide6.QtCore import Qt
from system_utils import SystemUtils
from execution_manager import ExecutionManager
from game_manager import GameManager
from logging_manager import setup_logging
from prefix_manager import PrefixManager
from game_process_manager import GameProcessManager
from platform_profile import CURRENT_PLATFORM, Feature, PlatformProfile
from ui.platform_ui import PlatformUi

logger = logging.getLogger(__name__)

class SettingsTab(SettingsPage):
    CONFIG_FILE = config.USER_SETTINGS

    def __init__(self, theme_manager, platform: PlatformProfile = CURRENT_PLATFORM):
        super().__init__()

        self.platform = platform
        self.platform_ui = PlatformUi(platform)
        self.theme_manager = theme_manager
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
        main_layout.addWidget(self._build_directories_group())
        self.texthooking_group = self._build_texthooking_group()
        self.platform_ui.add_widget(main_layout, self.texthooking_group, requires=Feature.WINE_CONFIGURATION)
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
        self.platform_ui.add_row(settings_layout, QLabel(self.tr("Font Folder:")), font_layout, requires=Feature.WINE_CONFIGURATION)
        
        # Gamescope
        gs_layout = QHBoxLayout()
        self.gs_checkbox = QCheckBox(self.tr("Enable"))
        gs_enabled = self.user_settings.get(config.USER_CONF_GAMESCOPE_ENABLED, False)
        if gs_enabled and not config.GAMESCOPE_INSTALLED:
            self.user_settings.set(config.USER_CONF_GAMESCOPE_ENABLED, False)
        self.gs_checkbox.setChecked(gs_enabled and config.GAMESCOPE_INSTALLED)
        self.gs_params = QLineEdit(self.user_settings.get(config.USER_CONF_GAMESCOPE_PARAMS, ""))
        self.gs_params.setPlaceholderText(self.tr("Parameters (e.g., -W 1920 -H 1080)"))
        if not config.GAMESCOPE_INSTALLED:
            self.gs_checkbox.setDisabled(True)
            self.gs_params.setDisabled(True)
        gs_layout.addWidget(self.gs_checkbox)
        gs_layout.addWidget(self.gs_params)
        self.platform_ui.add_row(settings_layout, QLabel(self.tr("Gamescope:")), gs_layout, requires=Feature.GAMESCOPE)

        # linux-rt-upscaler
        upscaler_layout = QHBoxLayout()
        self.upscaler_checkbox = QCheckBox(self.tr("Enable"))
        self.upscaler_checkbox.setChecked(self.user_settings.get(config.USER_CONF_RT_UPSCALER_ENABLED, False))
        self.upscaler_params = QLineEdit(self.user_settings.get(config.USER_CONF_RT_UPSCALER_PARAMS, ""))
        self.upscaler_params.setPlaceholderText(self.tr("Parameters (e.g., --profile 1080p --crop-top 19)"))
        self.upscaler_gui_btn = QPushButton(self.tr("Open GUI"))
        self.upscaler_gui_btn.setToolTip(self.tr("Open the linux-rt-upscaler configuration interface"))
        if not config.RT_UPSCALING_INSTALLED:
            self.upscaler_checkbox.setDisabled(True)
            self.upscaler_checkbox.setCheckable(False)
            self.upscaler_params.setDisabled(True)
            self.upscaler_gui_btn.setDisabled(True)
        upscaler_layout.addWidget(self.upscaler_checkbox)
        upscaler_layout.addWidget(self.upscaler_params)
        upscaler_layout.addWidget(self.upscaler_gui_btn)
        self.platform_ui.add_row(settings_layout, QLabel(self.tr("linux-rt-upscaler:")), upscaler_layout, requires=Feature.RT_UPSCALER)
        
        # Global Env Variables
        env_label = QLabel(self.tr("Environment variables:"))
        self.manage_env_btn = QPushButton(self.tr("Manage Environment Variables"))
        self.manage_env_btn.setCursor(Qt.PointingHandCursor)
        self.manage_env_btn.clicked.connect(self._open_env_manager)
        env_btn_layout = QHBoxLayout()
        env_btn_layout.addWidget(self.manage_env_btn)
        env_btn_layout.addStretch()
        self.platform_ui.add_row(settings_layout, env_label, env_btn_layout, requires=Feature.WINE_CONFIGURATION)

        auto_dpi_layout = QHBoxLayout()
        self.auto_dpi_checkbox = QCheckBox(self.tr("Enable"))
        self.auto_dpi_checkbox.setChecked(self.user_settings.get(config.USER_CONF_AUTO_DPI_UTILITIES, False))
        auto_dpi_description = QLabel(self.tr("Launching Wine Utilities tools will automatically increase prefix's DPI in high resolution monitors for better visibility"))
        auto_dpi_description.setWordWrap(True)
        auto_dpi_layout.addWidget(self.auto_dpi_checkbox)
        auto_dpi_layout.addWidget(auto_dpi_description, 1)
        self.platform_ui.add_row(settings_layout, QLabel(self.tr("Winetools Auto DPI:")), auto_dpi_layout, requires=Feature.WINE_CONFIGURATION)

        # Added SteamGridDB API Key Section
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

        # Game sidebar name autocomplete
        autocomplete_layout = QHBoxLayout()
        self.name_autocomplete_group = QButtonGroup(self)
        self.name_autocomplete_buttons = {}
        current_autocomplete = self.user_settings.get(config.USER_CONF_NAME_AUTOCOMPLETE, "vndb")
        if current_autocomplete not in ("vndb", "sgdb", "none"):
            current_autocomplete = "vndb"

        for label, source in (
            ("VNDB", "vndb"),
            ("SteamGridDB", "sgdb"),
            (self.tr("None"), "none"),
        ):
            button = QRadioButton(label)
            button.setChecked(source == current_autocomplete)
            self.name_autocomplete_group.addButton(button)
            self.name_autocomplete_buttons[source] = button
            autocomplete_layout.addWidget(button)

        autocomplete_layout.addStretch()
        settings_layout.addRow(self.tr("Name autocomplete:"), autocomplete_layout)

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

        self.log_wine_traces = QCheckBox(self.tr("Show game logs in application logs"))
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
            new_global_states = dialog.get_global_states()

            self.user_settings.set(config.USER_CONF_ENV_VARIABLE_LIST, new_vars)
            self.user_settings.set(config.USER_CONF_GLOBAL_VARIABLES, new_global_states)

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
            (self.tr("Prefixes Dir:"), config.USER_CONF_PREFIXES_PATH, config.PREFIXES_DIR, Feature.PREFIXES),
            (self.tr("Wine Runners Dir:"), config.USER_CONF_WINE_RUNNERS_PATH, config.WINE_RUNNERS_DIR, Feature.RUNNERS),
            (self.tr("Proton Runners Dir:"), config.USER_CONF_PROTON_RUNNERS_PATH, config.PROTON_RUNNERS_DIR, Feature.RUNNERS),
            (self.tr("Covers Dir:"), config.USER_CONF_COVERS_PATH, config.COVERS_DIR, None),
            (self.tr("Timetrack Logs Dir:"), config.USER_CONF_LOGS_PATH, config.LOG_DIR, None),
        ]
        folder_settings = [
            definition for definition in folder_settings
            if self.platform_ui.supported(definition[3])
        ]

        BROWSE_WIDTH = 120
        TRASH_WIDTH = 36
        LAYOUT_SPACING = 6
        
        for label_text, key, default_val, _ in folder_settings:
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

    # ==========================================
    # Real Methods

    def _connect_signals(self):
        self.font_btn.clicked.connect(self.browse_font_folder)
        self._bind_text_setting(self.font_edit, config.USER_CONF_FONT_FOLDER)
        self._bind_text_setting(self.sgdb_key_edit, config.USER_CONF_SGDB_API_KEY)
        for source, button in self.name_autocomplete_buttons.items():
            button.toggled.connect(
                lambda checked, value=source: checked
                and self.save_setting(config.USER_CONF_NAME_AUTOCOMPLETE, value)
            )
        self.log_level_combo.currentIndexChanged.connect(self.change_log_level)
        self.log_to_file_checkbox.stateChanged.connect(lambda s: self.save_setting(config.USER_CONF_LOG_TO_FILE, bool(s)))
        self.log_wine_traces.stateChanged.connect(lambda s: self.save_setting(config.USER_CONF_LOGS_WINE, bool(s)))
        self.gs_checkbox.stateChanged.connect(lambda s: self.save_setting(config.USER_CONF_GAMESCOPE_ENABLED, bool(s)))
        self.auto_dpi_checkbox.stateChanged.connect(lambda s: self.save_setting(config.USER_CONF_AUTO_DPI_UTILITIES, bool(s)))
        self._bind_text_setting(self.gs_params, config.USER_CONF_GAMESCOPE_PARAMS)
        self.upscaler_checkbox.stateChanged.connect(lambda s: self.save_setting(config.USER_CONF_RT_UPSCALER_ENABLED, bool(s)))
        self._bind_text_setting(self.upscaler_params, config.USER_CONF_RT_UPSCALER_PARAMS)
        self.upscaler_gui_btn.clicked.connect(self._open_upscaler_gui)
        self.texthooker_btn.clicked.connect(self.browse_texthooker_path)
        self.texthooker_enable.stateChanged.connect(lambda s: self.save_nested_setting(config.USER_CONF_TEXTHOOKER, "enabled", bool(s)))
        self._bind_text_setting(self.texthooker_edit, "path", parent_key=config.USER_CONF_TEXTHOOKER)

        # Connect signals for dynamic folder inputs
        for key, edit_widget, btn_widget in self.folder_inputs:
            self._connect_folder_signal(key, edit_widget, btn_widget)

        self.covers_delete_btn.clicked.connect(self._on_delete_covers_clicked)

        gp_manager = GameProcessManager.get_instance()
        gp_manager.game_started.connect(lambda: self._set_folders_enabled(False))
        gp_manager.game_stopped.connect(lambda: self._check_should_re_enable_folders())

    def _open_upscaler_gui(self):
        """Open the bundled or system linux-rt-upscaler GUI."""
        try:
            ExecutionManager.run(["upscale-gui"], SystemUtils.get_clean_env(), wait=False, detached=True)
        except OSError as error:
            logger.error("Failed to open linux-rt-upscaler GUI: %s", error)
            QMessageBox.warning(self, self.tr("Unable to Open GUI"),
                self.tr("linux-rt-upscaler GUI could not be started:\n{}").format(error))

    def _connect_folder_signal(self, key, edit_widget, btn_widget):
        """Helper to bind signals without loop closure issues."""
        btn_widget.clicked.connect(lambda: self.browse_directory_for_widget(edit_widget, key))
        self._bind_text_setting(edit_widget, key)

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
            self.flush_pending_text_settings()

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

    def browse_font_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("Select Font Folder"), "")
        if folder:
            self.font_edit.setText(folder)
            self.flush_pending_text_settings()
    
    def browse_texthooker_path(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            self.tr("Select Texthooker Executable"), 
            "", 
            self.tr("Executables (*.exe);;All Files (*)")
        )
        if file_path:
            self.texthooker_edit.setText(file_path)
            self.flush_pending_text_settings()
