from PySide6.QtWidgets import (QWidget, QVBoxLayout, QComboBox, 
                               QLabel, QGroupBox, QFormLayout,
                               QHBoxLayout, QLineEdit, QPushButton,
                               QCheckBox, QFileDialog, QScrollArea, QFrame)
from system_utils import SystemUtils
import config
import logging
from logging_manager import setup_logging
logger = logging.getLogger(__name__)

class SettingsTab(QWidget):
    CONFIG_FILE = config.USER_SETTINGS

    def __init__(self, theme_manager):
        super().__init__()
        self.theme_manager = theme_manager

        # Load existing settings
        self.user_settings = SystemUtils.load_settings()

        # Main layout for the entire tab
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        # Container widget to hold all stuff
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(20, 20, 20, 20) # Add breathing room around the edges
        main_layout.setSpacing(20) # Space between the different sections
        
        # ==========================================
        # Functional Settings
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
        
        # Gamescope Global Settings
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
        
        # Save Data Management (Disabled for now)
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
        
        # Global Winetricks
        wt_layout = QHBoxLayout()
        global_env_var = self.user_settings.get("global_env_var", {}) # Get the dict or empty dict

        self.wt_jp_locale = QCheckBox(self.tr("Japanese Locale"))
        # Read from nested dict: global_env_var -> jp_locale
        self.wt_jp_locale.setChecked(global_env_var.get("jp_locale", False))

        self.wt_jp_timezone = QCheckBox(self.tr("Japanese Timezone"))
        # Read from nested dict: global_env_var -> jp_timezone
        self.wt_jp_timezone.setChecked(global_env_var.get("jp_timezone", False))

        wt_layout.addWidget(self.wt_jp_locale)
        wt_layout.addWidget(self.wt_jp_timezone)
        settings_layout.addRow(QLabel(self.tr("Global Env variables:")), wt_layout)

        # Log Level
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "ERROR"])
        self.log_level_combo.setFixedWidth(200)
        
        # Set current index based on saved setting (default to INFO)
        current_log = self.user_settings.get("log_level", "INFO").upper()
        log_map = {"DEBUG": 0, "INFO": 1, "ERROR": 2}
        self.log_level_combo.setCurrentIndex(log_map.get(current_log, 1))
        
        self.log_level_combo.currentIndexChanged.connect(self.change_log_level)
        settings_layout.addRow(QLabel(self.tr("Debug Level:")), self.log_level_combo)

        main_layout.addWidget(settings_group)

        # ==========================================
        # Appearance Settings
        appearance_group = QGroupBox(self.tr("Appearance"))
        appearance_layout = QFormLayout(appearance_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([self.tr("System Default"), self.tr("Light"), self.tr("Dark")])
        self.theme_combo.setFixedWidth(200) # Keep it from stretching across the whole screen
        
        # Sync combo with current setting
        current = self.theme_manager.get_theme_mode()
        mapping = {"auto": 0, "light": 1, "dark": 2}
        self.theme_combo.setCurrentIndex(mapping.get(current, 0))
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        
        # Add to form layout (Label on left, Combo on right)
        appearance_layout.addRow(QLabel(self.tr("Theme:")), self.theme_combo)
        
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["70%", "80%", "90%", "100%", "110%", "125%", "135%", "150%", "175%"])
        self.zoom_combo.setFixedWidth(200)

        # Set current index based on saved setting
        current_zoom = self.user_settings.get("ui_zoom", 1.0)
        zoom_map = {
            0.7: 0, 0.8: 1, 0.9: 2, 1.0: 3, 1.1: 4, 
            1.25: 5, 1.35: 6, 1.5: 7, 1.75: 8
        }
        self.zoom_combo.setCurrentIndex(zoom_map.get(current_zoom, 2))

        self.zoom_combo.currentIndexChanged.connect(self.change_zoom)
        appearance_layout.addRow(QLabel(self.tr("UI Zoom:")), self.zoom_combo)

        main_layout.addWidget(appearance_group)

        # ==========================================
        # System Info 
        sysinfo_group = QGroupBox(self.tr("System Info"))
        sysinfo_layout = QFormLayout(sysinfo_group)
        
        # Fetch data
        sys_data = SystemUtils.get_system_info()
        software = SystemUtils.get_software_support()
        
        sysinfo_layout.addRow(QLabel(self.tr("LVNM Version:")), QLabel(sys_data.get('app_version')))
        sysinfo_layout.addRow(QLabel(self.tr("OS:")), QLabel(sys_data.get('os')))
        sysinfo_layout.addRow(QLabel(self.tr("Kernel:")), QLabel(sys_data.get('kernel')))
        sysinfo_layout.addRow(QLabel(self.tr("Desktop:")), QLabel(f"{sys_data.get('desktop_environment')} - {sys_data.get('session_type')}"))
        sysinfo_layout.addRow(QLabel(self.tr("CPU:")), QLabel(sys_data.get('cpu')))
        sysinfo_layout.addRow(QLabel(self.tr("GPU:")), QLabel(sys_data.get('gpu')))
        
        # Software Support (Fixed the TypeError by converting to string/icon)
        sysinfo_layout.addRow(QLabel(self.tr("Vulkan Support:")), QLabel(self.check(software.get('vulkan_support'))))
        sysinfo_layout.addRow(QLabel(self.tr("Gamescope:")), QLabel(self.check(software.get('gamescope'))))
        sysinfo_layout.addRow(QLabel(self.tr("Umu-run:")), QLabel(self.check(software.get('umu_run'))))
        sysinfo_layout.addRow(QLabel(self.tr("Winetricks:")), QLabel(self.check(software.get('winetricks'))))

        # GStreamer Section
        gst_packages = software.get('gstreamer_packages', {})
        for pkg, installed in gst_packages.items():
            sysinfo_layout.addRow(QLabel(f"  {pkg}:"), QLabel(self.check(installed)))
        
        main_layout.addWidget(sysinfo_group)
        
        main_layout.addStretch()

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

        # ==========================================
        # Connect Signals for Auto-Save
        self.font_btn.clicked.connect(self.browse_font_folder)
        self.font_edit.textChanged.connect(lambda t: self.save_setting("font_folder", t))
        
        self.gs_checkbox.stateChanged.connect(lambda s: self.save_setting("gamescope_enabled", bool(s)))
        self.gs_params.textChanged.connect(lambda t: self.save_setting("gamescope_params", t))
        
        self.ogop_checkbox.stateChanged.connect(lambda s: self.save_setting("one_game_one_prefix", bool(s)))
        self.wt_jp_locale.stateChanged.connect(
            lambda s: self.save_nested_setting("global_env_var", "jp_locale", bool(s))
        )
        self.wt_jp_timezone.stateChanged.connect(
            lambda s: self.save_nested_setting("global_env_var", "jp_timezone", bool(s))
        )

    def change_theme(self, index):
        mapping = {0: "auto", 1: "light", 2: "dark"}
        new_mode = mapping[index]        
        self.theme_manager.settings.setValue("theme_mode", new_mode)        
        self.theme_manager.update_theme()

    def check(self, val): 
        return "✅" if val else "❌"

    def browse_font_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("Select Font Folder"), "")
        if folder:
            self.font_edit.setText(folder) # This triggers textChanged, which auto-saves

    def save_setting(self, key, value):
        """Updates the local dictionary and flushes it to the JSON file."""
        self.user_settings[key] = value
        SystemUtils.save_settings(self.user_settings)

    def save_nested_setting(self, parent_key, child_key, value):
        """Updates a nested dictionary setting and saves to disk."""
        # Ensure the parent dictionary exists
        if parent_key not in self.user_settings or not isinstance(self.user_settings[parent_key], dict):
            self.user_settings[parent_key] = {}
        
        # Update the child value
        self.user_settings[parent_key][child_key] = value
        
        # Flush to JSON
        SystemUtils.save_settings(self.user_settings)

    def change_zoom(self, index):
        mapping = {
            0: 0.7, 1: 0.8, 2: 0.9, 3: 1.0, 4: 1.1, 
            5: 1.25, 6: 1.35, 7: 1.5, 8: 1.75
        }
        new_zoom = mapping[index]
        # Save the setting
        self.save_setting("ui_zoom", new_zoom)        
        SystemUtils.apply_ui_zoom(new_zoom)
        self.theme_manager.update_theme()

    def change_log_level(self, index):
        mapping = {0: "DEBUG", 1: "INFO", 2: "ERROR"}
        new_level = mapping[index]
        
        self.save_setting("log_level", new_level)        
        config.LOG_LEVEL = new_level
        setup_logging(new_level)
