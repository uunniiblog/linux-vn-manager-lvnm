import config
import urllib.parse
import logging
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, 
    QFormLayout, QLineEdit, QCheckBox, QPushButton, 
    QComboBox, QFileDialog, QScrollArea, QFrame, QSizePolicy,
    QMessageBox, QDialog, QProgressDialog, QStyle
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QTimer, QSize, QEvent
from ui.prefix_tab import PrefixTab
from ui.timetracker_dialog import TimetrackerDialog
from game_manager import GameManager
from prefix_manager import PrefixManager
from model.game_card import GameCard, GameScope
from system_utils import SystemUtils
from vndb_manager import VndbManager, VndbWorker
from settings_manager import SettingsManager
from savedata_manager import SavedataManager
from game_process_manager import GameProcessManager
from ui.env_var_manager_dialog import EnvVarManagerDialog
from ui.advanced_settings_dialog import AdvancedSettingsDialog
from ui.vndb_autocomplete import VndbAutocompleteLineEdit
from ui.savedata_management_dialog import SavedataManagementDialog
from timetracker.log_manager import LogManager
from pregame_sync_pipeline import PreLaunchSyncPipeline, SavedataSyncStep, TrackingSyncStep

logger = logging.getLogger(__name__)

class GameSidebar(QFrame):
    VNDB_SITE_URL = config.VNDB_SITE_URL
    EGS_SITE_URL = config.EGS_SITE_URL

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.current_game: Optional[GameCard] = None
        self.prefixes = None
        self.is_running = None
        self.runner = None
        self.active_controller = None
        self._pending_pipeline = None
        self._pending_savedata_name = None
        self._pending_tracking_path = None

        self.user_settings = SettingsManager()
        self.timetracker_settings = self.user_settings.get(config.USER_CONF_TIMETRACKER, {})
        self.savedata_settings = self.user_settings.get(config.USER_CONF_SAVEDATA, {})

        # Connect to Game Process Manager
        self.process_manager = GameProcessManager.get_instance()
        self.process_manager.game_started.connect(self.on_game_started_signal)
        self.process_manager.game_stopped.connect(self.on_game_stopped_signal)
        self.process_manager.tracking_updated.connect(self.on_tracking_updated_signal)
        SavedataManager.get_instance().gdrive_sync_failed.connect(self.on_gdrive_sync_failed)
        SavedataManager.get_instance().gdrive_sync_succeeded.connect(self.on_gdrive_sync_succeeded)
        LogManager.get_instance().gdrive_sync_failed.connect(self.on_tracking_sync_failed)
        LogManager.get_instance().gdrive_sync_succeeded.connect(self.on_tracking_sync_succeeded)

        # State tracking for pre-game cloud syncs
        self.game_pending_launch = None
        self.pregame_progress = None
        
        layout = QVBoxLayout(self)
        
        # --- TOP SECTION ---
        top_layout = QVBoxLayout()
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(2)

        # Game Name Row
        self.lbl_display_name = QLabel()
        self.lbl_display_name.setAlignment(Qt.AlignCenter)
        self.lbl_display_name.setWordWrap(True)
        self.lbl_display_name.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 15px;")
        top_layout.addWidget(self.lbl_display_name)

        # Cover and Links Row
        self.media_container = QWidget()
        self.media_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        media_layout = QHBoxLayout(self.media_container)
        media_layout.setContentsMargins(0, 0, 0, 10)
        media_layout.setAlignment(Qt.AlignTop)

        self.lbl_cover = CoverLabel()
        media_layout.addWidget(self.lbl_cover)

        links_col = QVBoxLayout()
        links_col.setAlignment(Qt.AlignTop)
        links_col.setContentsMargins(15, 0, 0, 0)
        
        self.lbl_vndb_link = QLabel()
        self.lbl_vndb_link.linkActivated.connect(SystemUtils.open_url)
        self.lbl_vndb_link.setStyleSheet("font-size: 14px;margin-top: 20px")
        
        self.lbl_egs_link = QLabel()
        self.lbl_egs_link.linkActivated.connect(SystemUtils.open_url)
        self.lbl_egs_link.setStyleSheet("font-size: 14px;")
        
        links_col.addWidget(self.lbl_vndb_link)
        links_col.addWidget(self.lbl_egs_link)
        media_layout.addLayout(links_col)
        media_layout.addStretch() 
        
        top_layout.addWidget(self.media_container)

        # Launch Button Row
        self.launch_btn = QPushButton(self.tr("Start Game"))
        self.launch_btn.setStyleSheet("background-color: #2e7d32; color: white; height: 40px; font-weight: bold;")
        self.launch_btn.clicked.connect(self.toggle_game)
        top_layout.addWidget(self.launch_btn)

        layout.addLayout(top_layout)

        # Sync confirmation label        
        self.lbl_sync_status = QLabel("")
        self.lbl_sync_status.setAlignment(Qt.AlignLeft)
        self.lbl_sync_status.setStyleSheet("color: #4CAF50; font-weight: bold; margin-left: 1em;")
        self.lbl_sync_status.hide()
        layout.addWidget(self.lbl_sync_status)

        # Scrollable Edit Section 
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)

        # Timetracker section only shown if game running and timetracker active
        self.tracking_group = QGroupBox(self.tr("Time Tracking"))
        self.tracking_group.setVisible(False)

        tracking_layout = QFormLayout(self.tracking_group)
        tracking_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        tracking_layout.setLabelAlignment(Qt.AlignLeft)

        self.lbl_session_len = QLabel("00:00:00")
        self.lbl_session_len.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_session_play = QLabel("00:00:00")
        self.lbl_session_play.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_total_play = QLabel("00:00:00")
        self.lbl_total_play.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        tracking_layout.addRow(self.tr("Session Length:"), self.lbl_session_len)
        tracking_layout.addRow(self.tr("Session Playtime:"), self.lbl_session_play)
        tracking_layout.addRow(self.tr("Total Playtime:"), self.lbl_total_play)
        self.track_btn = QPushButton(self.tr("Manually Select Tracking Window"))
        self.track_btn.clicked.connect(self.launch_timetracker_dialog)
        tracking_layout.addRow(self.track_btn)

        form.addWidget(self.tracking_group)
        
        # General Info
        gen_group = QGroupBox(self.tr("Edit Game"))
        self.gen_form = QFormLayout(gen_group)
        self.gen_form.setLabelAlignment(Qt.AlignLeft)
        self.edit_name = VndbAutocompleteLineEdit()
        self.edit_name.vn_selected.connect(self.on_vndb_item_selected)
        self.edit_path = QLineEdit()
        self.btn_path = QPushButton()
        browse_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        self.btn_path.setIcon(browse_icon)
        self.btn_path.setFixedSize(43, 32)
        self.btn_path.clicked.connect(self.browse_path)
        path_row = QHBoxLayout()
        path_row.addWidget(self.edit_path)
        path_row.addWidget(self.btn_path)
        
        # Prefix combo
        self.combo_prefix = QComboBox()
        self.combo_prefix.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.combo_prefix.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_prefix.currentTextChanged.connect(self.on_prefix_changed)

        # Create prefix button
        self.btn_add_prefix = QPushButton()
        add_icon = QIcon.fromTheme("list-add")
        self.btn_add_prefix.setIcon(add_icon)
        self.btn_add_prefix.setFixedSize(43, 32)
        self.btn_add_prefix.clicked.connect(self.open_create_prefix_dialog)

        # Create a horizontal layout to hold both the combo box and the button
        prefix_row = QHBoxLayout()
        prefix_row.setContentsMargins(0, 0, 0, 0)
        prefix_row.setSpacing(5)
        prefix_row.addWidget(self.combo_prefix)
        prefix_row.addWidget(self.btn_add_prefix)

        # Warning label for missing prefix
        self.prefix_warning = QLabel()
        self.prefix_warning.setStyleSheet("color: #ff5555; font-size: 10px; font-weight: bold;")
        self.prefix_warning.setVisible(False)
        self.prefix_warning.setWordWrap(True)
        self.prefix_warning.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.edit_vndb = QLineEdit()
        self.edit_vndb.setPlaceholderText("v11")

        # Save data folder (Only if enabled in settings)
        self.edit_savedata = QLineEdit()
        self.btn_savedata = QPushButton()
        self.btn_savedata.setIcon(browse_icon)
        self.btn_savedata.setFixedSize(43, 32)
        self.btn_savedata.clicked.connect(self.browse_savedata)
        self.edit_savedata.setPlaceholderText("~/.local/share/lvnm/prefixes/protonge1034/drive_c/users/user/AppData/Roaming/Frontwing/GINKA/")
        self.btn_open_svdata = QPushButton()
        self.btn_open_svdata.setIcon(add_icon)
        self.btn_open_svdata.setFixedSize(43, 32)
        self.btn_open_svdata.clicked.connect(self.open_open_savedata_dialog)
        self.savedata_row = QHBoxLayout()  
        self.savedata_row.addWidget(self.edit_savedata)
        self.savedata_row.addWidget(self.btn_savedata)
        self.savedata_row.addWidget(self.btn_open_svdata)

        # Gdrive sync checkbox
        self.gdrive_sync_checkbox = QCheckBox(self.tr("Sync this game's savedata to Google Drive"))

        self.gen_form.addRow(self.tr("Name:"), self.edit_name)
        self.gen_form.addRow(self.tr("Path:"), path_row)
        self.gen_form.addRow(self.tr("Prefix:"), prefix_row)
        self.gen_form.addRow("", self.prefix_warning)
        self.gen_form.addRow(self.tr("VNDB:"), self.edit_vndb)
        self.gen_form.addRow(self.tr("Savedata:"), self.savedata_row)
        self.gen_form.addRow("", self.gdrive_sync_checkbox)
        form.addWidget(gen_group)

        self.update_savedata_visibility()

        # Gamescope
        gs_group = QGroupBox("Gamescope")
        gs_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        gs_form = QFormLayout(gs_group)
        self.gs_enabled = QCheckBox(self.tr("Enable Gamescope"))
        self.gs_params = QLineEdit()
        gs_form.addRow(self.gs_enabled)
        gs_form.addRow(self.tr("Params:"), self.gs_params)
        if not config.GAMESCOPE_INSTALLED:
            self.gs_enabled.setDisabled(True)
            self.gs_params.setDisabled(True)
        form.addWidget(gs_group)

        # Environment Variables
        self.env_group = QGroupBox(self.tr("Environment Variables"))
        self.env_layout = QVBoxLayout(self.env_group)
        self.env_checkboxes = {}
        
        self.env_checkbox_layout = QVBoxLayout()
        self.env_layout.addLayout(self.env_checkbox_layout)

        # Manage environment Button
        self.manage_env_btn = QPushButton(self.tr("Manage Environment Variables"))
        self.manage_env_btn.setFlat(True)
        self.manage_env_btn.setStyleSheet("margin: 5px; padding: 4px 10px;")
        self.manage_env_btn.setCursor(Qt.PointingHandCursor)
        self.manage_env_btn.clicked.connect(self._open_env_manager)
        
        self.env_layout.addWidget(self.manage_env_btn)
        
        form.addWidget(self.env_group)

        # Advanced Settings Button
        self.advanced_btn = QPushButton(self.tr("Advanced Settings"))
        self.advanced_btn.setMinimumHeight(35)
        self.advanced_btn.setStyleSheet("margin: 5px; margin-top: 10px;padding: 4px 10px;")
        self.advanced_btn.setCursor(Qt.PointingHandCursor)
        self.advanced_btn.clicked.connect(self._open_advanced_settings)
        form.addWidget(self.advanced_btn)

        form.addStretch(1)

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Bottom Buttons
        btns = QHBoxLayout()

        # Delete (Left side)
        self.delete_btn = QPushButton(self.tr("Delete"))
        # Styling it red to indicate a destructive action
        self.delete_btn.setStyleSheet("background-color: #c62828; color: white; font-weight: bold;")
        self.delete_btn.clicked.connect(self.delete_game_action)
        # Export
        self.export_btn = QPushButton(self.tr("Export"))
        self.export_btn.clicked.connect(self.export_game_action)

        # Save & Cancel (Right side)
        self.save_btn = QPushButton(self.tr("Save"))
        self.save_btn.setMinimumWidth(100)
        self.save_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.save_btn.clicked.connect(self.save_data)

        self.cancel_btn = QPushButton(self.tr("Cancel"))
        self.cancel_btn.clicked.connect(lambda: self.on_close())


        # Add them to the layout in the requested order
        btns.addWidget(self.delete_btn)
        btns.addWidget(self.export_btn)
        btns.addStretch() # This pushes everything after it to the far right
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.save_btn)

        layout.addLayout(btns)

    def resizeEvent(self, event):
        """
        Try to keep cover at 1/3
        """
        super().resizeEvent(event)
        cover_cap = max(100, (self.height() // 3) - 80)
        self.media_container.setMaximumHeight(cover_cap)

    # SIGNAL HANDLERS
    def on_game_started_signal(self, name):
        if self.current_game and self.current_game.name == name:
            self.set_ui_stop_state()

    def on_game_stopped_signal(self, name):
        """ Triggered by GameProcessManager when ANY game finishes """
        # Notify GameTab list item to refresh last played text
        if hasattr(self, 'on_metadata_updated'):
            self.on_metadata_updated(name)
        
        # If we are currently looking at the game that finished, reset UI
        if self.current_game and self.current_game.name == name:
            game_to_update = GameManager.get_game(name)
            if game_to_update:
                self.current_game.last_played = game_to_update.last_played
                self.current_game.savedata_path = game_to_update.savedata_path
                self.edit_savedata.setText(game_to_update.savedata_path)

                if self.current_game.gdrive:
                    self.show_sync_message(self.tr("Gdrive Syncing..."), "#ffc107", timeout_ms=0)

            self.set_ui_start_state()
            self.reset_tracking_labels()

    def on_tracking_updated_signal(self, name, stats):
        """ Updates UI text only if we are viewing the actively tracked game """
        if self.current_game and self.current_game.name == name:
            self.lbl_session_len.setText(stats.get("session_length", "00:00:00"))
            self.lbl_session_play.setText(stats.get("session_playtime", "00:00:00"))
            self.lbl_total_play.setText(stats.get("total_playtime", "00:00:00"))

    def on_gdrive_sync_failed(self, name, error_message):
        """
        Fires for EVERY savedata Gdrive sync failure. 
        this is only the post-game background-backup case.
        """
        if self._pending_pipeline and name == self._pending_savedata_name:
            return
        QMessageBox.warning(
            self,
            self.tr("Savedata Cloud Sync Failed"),
            self.tr(f"Background save backup failed for '{name}':\n{error_message}\nYou can sync the data manually from settings.")
        )
        if self.current_game and self.current_game.name == name:
            self.show_sync_message(self.tr(f"Gdrive synced error {error_message}"), "#FF0000")

    def on_gdrive_sync_succeeded(self, name, result):
        """Post-game background savedata backup finished"""
        if self._pending_pipeline and name == self._pending_savedata_name:
            return
        logger.info(f"Post-game cloud backup finished for '{name}': {result}")
        if self.current_game and self.current_game.name == name:
            self.show_sync_message(self.tr("Gdrive synced successfully"), "#4CAF50")

    def on_tracking_sync_failed(self, app_name, error_message):
        """Post-game background tracking-log backup failed"""
        if self._pending_pipeline and app_name == self._pending_tracking_path:
            return
        QMessageBox.warning(
            self,
            self.tr("Timetracking Cloud Sync Failed"),
            self.tr(f"Background timetracking backup failed for {app_name}:\n{error_message}")
        )
    
    def on_tracking_sync_succeeded(self, app_name, result):
        """Post-game background tracking-log backup finished."""
        if self._pending_pipeline and app_name == self._pending_tracking_path:
            return
        logger.info(f"Post-game tracking backup finished for '{app_name}': {result}")

    def show_sync_message(self, message: str, color: str, timeout_ms=5000):
        """Displays a success message below the play button for 5 seconds or perma if 0 timeout."""
        self.lbl_sync_status.setText(message)
        self.lbl_sync_status.setStyleSheet(f"color: {color}; font-weight: bold; margin-left: 1em;")
        self.lbl_sync_status.show()
        # Hide if prompted
        if timeout_ms > 0:
            QTimer.singleShot(timeout_ms, self.lbl_sync_status.hide)
        else:
            pass

    def on_vndb_item_selected(self, vn_data):
        """Called when the VndbAutocompleteLineEdit emits a selection."""
        self.edit_vndb.setText(vn_data.get('id', ''))

    def load_game(self, card: GameCard):
        """
        Loaded from GameTab with the data of the game selected
        """
        self.current_game = card

        # Don't preload from global settings in existing game load
        self._create_mode_defaults = None

        self.launch_btn.setVisible(True)

        # Check the registry to set the button state correctly
        if self.process_manager.is_game_running(card.name):
            self.set_ui_stop_state()
        else:
            self.set_ui_start_state()

        # Hide gdrive status text
        self.lbl_sync_status.hide()

        # Update Top Header Name
        self.lbl_display_name.setText(card.name)
        self.update_game_cover()

        # Filling General fields
        self.edit_name.setText(card.name)
        self.edit_path.setText(card.path)
        self.edit_vndb.setText(card.vndb)
        self.edit_savedata.setText(card.savedata_path)
        self.gdrive_sync_checkbox.setChecked(bool(getattr(card, "gdrive", False)))
        self.update_savedata_visibility()

        # Filling Gamescope (using the nested dataclass)
        self.gs_enabled.setChecked(card.gamescope.enabled == "true")
        self.gs_params.setText(card.gamescope.parameters)

        # Load Prefixes
        self.combo_prefix.blockSignals(True)
        self.combo_prefix.clear()
        self.prefixes = PrefixManager.get_prefix_json()
        self.combo_prefix.addItems(self.prefixes.keys())

        if card.prefix in self.prefixes:
            self.combo_prefix.setCurrentText(card.prefix)
            self.prefix_warning.setVisible(False)
        else:
            # Prefix is missing!
            self.combo_prefix.setCurrentIndex(-1) # Set empty
            self.prefix_warning.setText(self.tr(f"⚠ Warning: Prefix '{card.prefix}' not found!"))
            self.prefix_warning.setVisible(True)
        self.combo_prefix.blockSignals(False)

        current_prefix = self.combo_prefix.currentText()
        prefix_type = self.prefixes.get(current_prefix, {}).get("type", "wine")

        # Load Env Vars
        self.refresh_env_vars(prefix_type, card.envvar)

    def refresh_env_vars(self, prefix_type, active_vars):
        """Populates the UI checkboxes using the dynamic list from settings."""

        # Clear old checkboxes
        for cb in self.env_checkboxes.values():
            cb.deleteLater()
        self.env_checkboxes.clear()

        # Get list from user settings or config fallback to default
        env_vars_list = self.user_settings.get(config.USER_CONF_ENV_VARIABLE_LIST, config.ENV_VARIABLES)

        for var in env_vars_list:
            req = var.get("req")
            if req and req != prefix_type:
                continue
            
            cb = QCheckBox(var.get("name") or var["id"])
            tooltip_text = f"{var['key']}={var['value']}"
            cb.setToolTip(tooltip_text)
            # Check if current game has this specific key/value pair
            if active_vars.get(var["key"]) == var["value"]:
                cb.setChecked(True)
                
            self.env_checkboxes[var["id"]] = cb
            self.env_checkbox_layout.addWidget(cb)

    def _open_env_manager(self):
        """Opens the dialog to add/remove/edit environment variables."""
        current_vars = self.user_settings.get(config.USER_CONF_ENV_VARIABLE_LIST, config.ENV_VARIABLES)
        ui_active_vars = {}

        # Save current selected variables
        var_lookup = {v["id"]: v for v in current_vars}
        for var_id, cb in self.env_checkboxes.items():
            if cb.isChecked() and var_id in var_lookup:
                var_def = var_lookup[var_id]
                ui_active_vars[var_def["key"]] = var_def["value"]

        dialog = EnvVarManagerDialog(current_vars, self)
        
        if dialog.exec():
            new_vars = dialog.get_vars()
            self.user_settings.set(config.USER_CONF_ENV_VARIABLE_LIST, new_vars)

            # Clean ghost variables from game database
            new_keys = [var["key"] for var in new_vars]
            GameManager.cleanup_env_vars(new_keys)

            # Sync the in-memory game card to remove deleted keys
            self.current_game.envvar = {
                k: v for k, v in self.current_game.envvar.items() 
                if k in new_keys
            }
            
            active_vars_for_ui = {
                k: v for k, v in ui_active_vars.items()
                if k in new_keys
            }

            # Refresh the current sidebar view using the preserved UI selections
            prefix_name = self.combo_prefix.currentText()
            prefix_type = self.prefixes.get(prefix_name, {}).get("type", "wine")
            
            self.refresh_env_vars(prefix_type, active_vars_for_ui)
            
    def _open_advanced_settings(self):
        if not self.current_game:
            return
            
        # Figure out the current prefix type to pass to the dialog
        prefix_name = self.combo_prefix.currentText()
        prefix_type = self.prefixes.get(prefix_name, {}).get("type", "wine")
        
        dialog = AdvancedSettingsDialog(prefix_type, self.current_game, self)
        
        # Advanced dialog already writes into self.current_game
        # So we call save directly after closing to avoid having to double save
        if dialog.exec():
            self.save_data()

    def load_create_game(self, card: GameCard):
        """ Loaded from GameTab to create a new entry """
        self.current_game = card
        self.set_ui_start_state()

        # Clear Header UI Fields
        self.lbl_display_name.setText(self.tr("New Game"))
        self.media_container.hide() # Hide media for new games by default
        self.launch_btn.setVisible(False)

        # Hide gdrive status text
        self.lbl_sync_status.hide()
        
        # Clear General UI Fields
        self.launch_btn.setVisible(False)
        self.edit_name.clear()
        self.edit_path.clear()
        self.edit_vndb.clear()
        self.edit_savedata.clear()
        self.update_savedata_visibility()
        
        # Apply Gamescope Defaults from Settings or leave empty
        gs_default_enabled = self.user_settings.get(config.USER_CONF_GAMESCOPE_ENABLED, False)
        gs_default_params = self.user_settings.get(config.USER_CONF_GAMESCOPE_PARAMS, "")
        
        self.gs_enabled.setChecked(gs_default_enabled)
        self.gs_params.setText(gs_default_params)

        # Reload Prefixes to an empty selection
        self.combo_prefix.blockSignals(True)
        self.combo_prefix.clear()
        self.prefixes = PrefixManager.get_prefix_json()
        self.combo_prefix.addItems(self.prefixes.keys())
        self.combo_prefix.setCurrentIndex(-1) # No selection initially
        self.prefix_warning.setVisible(False)
        self.combo_prefix.blockSignals(False)

        # Environment variables logic
        global_env_var = self.user_settings.get(config.USER_CONF_GLOBAL_VARIABLES, {})
        env_vars_definitions = self.user_settings.get(config.USER_CONF_ENV_VARIABLE_LIST, config.ENV_VARIABLES)
        default_env_vars = {}
        
        # match keys
        for var in env_vars_definitions:
            var_id = var.get("id")
            if global_env_var.get(var_id):
                default_env_vars[var["key"]] = var["value"]

        self._create_mode_defaults = default_env_vars

        # Clear Env Var checkboxes
        self.refresh_env_vars("wine", default_env_vars)
    
    def toggle_game(self):
        if not self.current_game:
            return
        
        game_name = self.current_game.name
        if self.process_manager.is_game_running(game_name):
            # Game running, stop it
            self.stop_game(game_name)
        else:
            # Game is not running, start it
            self.launch_game(game_name)

    def stop_game(self, name):
        """Call process manager to stop game."""
        self.process_manager.stop_game(name)

    def launch_game(self, name):
        """
        Builds the list of prelaunch cloud sync steps that apply for this
        game, runs them through PreLaunchSyncPipeline, and launches the 
        game once they've all succeeded or the user chose to proceed anyway after a failure.
        """
        try:
            game_to_start = GameManager.get_game(name)
            steps = []
 
            if self.savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False) and game_to_start.gdrive:
                self._pending_savedata_name = name
                steps.append(SavedataSyncStep(
                    name, game_to_start.to_dict(),
                    self.tr("Syncing save data with Google Drive...")
                ))
 
            if self.timetracker_settings.get(config.USER_CONF_TIMETRACKER_GDRIVE_SYNC, False) and self.savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False) and game_to_start.gdrive:
                self._pending_tracking_path = game_to_start.path
                steps.append(TrackingSyncStep(
                    game_to_start.path,
                    self.tr("Syncing time tracking data...")
                ))
 
            if not steps:
                self._execute_game_launch(name)
                return
 
            self._pending_pipeline = PreLaunchSyncPipeline(self, steps)
            self._pending_pipeline.finished.connect(
                lambda proceed, n=name: self._on_pipeline_finished(n, proceed)
            )
            self._pending_pipeline.start()
 
        except Exception as e:
            logger.error(f"Error in launch_game {e}", exc_info=True)
            QMessageBox.critical(self, self.tr("Error"), str(e))

    def _on_pipeline_finished(self, name, proceed):
        """Called once after all pre-launch sync steps."""
        self._pending_pipeline = None
        self._pending_savedata_name = None
        self._pending_tracking_path = None
        if proceed:
            self._execute_game_launch(name)

    def _execute_game_launch(self, name):
        """Call process manager to initialize the runner and starts the process."""
        try:
            self.process_manager.start_game(name, self.timetracker_settings)
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), str(e), exc_info=True)

    def browse_path(self):
        """File system browser"""
        dialog = QFileDialog(self)
        dialog.setWindowTitle(self.tr("Select Game Executable"))

        current_path = self.edit_path.text()
        if current_path:
            dialog.setDirectory(current_path.strip())
        
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setNameFilter("All Files (*);;Executables (*.exe *.sh *.bin)")
        dialog.setViewMode(QFileDialog.Detail)

        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                self.edit_path.setText(selected_files[0])

    def browse_savedata(self):
        """File system browser"""
        dialog = QFileDialog(self)
        current_path = self.edit_path.text()
        if current_path:
            dialog.setDirectory(current_path.strip())
        
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setViewMode(QFileDialog.Detail)

        folder = dialog.getExistingDirectory(self, self.tr("Select Savedata Folder"), "")

        if folder:
            self.edit_savedata.setText(folder)

    def save_data(self):
        """
        Updates the GameCard object and sends it to the manager.
        """
        if not self.current_game:
            return

        # Record if this is a new game before we overwrite the original name
        is_new_game = not self.current_game.name 
        original_name = self.current_game.name
        old_vndb = self.current_game.vndb

        # Gather ALL data from UI into the card object
        self.current_game.name = self.edit_name.text()
        self.current_game.path = self.edit_path.text()
        self.current_game.prefix = self.combo_prefix.currentText()
        self.current_game.vndb = self.edit_vndb.text()
        self.current_game.savedata_path = self.edit_savedata.text()
        self.current_game.gdrive = self.gdrive_sync_checkbox.isChecked()

        if not self.current_game.name:
            logger.warning("Error: game created without name.")
            QMessageBox.critical(
                self,
                self.tr("Error"),
                self.tr(f"A name for the game is needed.")
            )
            return

        if not self.current_game.path or not self.current_game.prefix:
            logger.debug("Trying to edit game without necessary data.")
            reply = QMessageBox.question(
                self, 
                self.tr("Warning"),
                self.tr(self.tr("Prefix or Path data are missing, it can be added later.\n\n Are you sure you want to continue?")),
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                return

        if old_vndb and not self.current_game.vndb:
            logger.info(f"VNDB ID removed for {self.current_game.name}. Clearing cover path.")
            self.current_game.cover_path = ""
        
        # Env Vars
        env_vars_definitions = self.user_settings.get(config.USER_CONF_ENV_VARIABLE_LIST, config.ENV_VARIABLES)
        new_env = {}
        for var in env_vars_definitions:
            cb = self.env_checkboxes.get(var["id"])
            if cb and cb.isChecked():
                new_env[var["key"]] = var["value"]
        self.current_game.envvar = new_env
        
        # Gamescope
        self.current_game.gamescope.enabled = "true" if self.gs_enabled.isChecked() else "false"
        self.current_game.gamescope.parameters = self.gs_params.text()

        # Execute Save
        if is_new_game:
            logger.debug(f"Creating game: {self.current_game.name}")
            GameManager.add_game(
                exe=self.current_game.path,
                name=self.current_game.name,
                prefix=self.current_game.prefix,
                vndb=self.current_game.vndb
            )
            # After adding, we need to save the extra fields (envvars, etc)
            GameManager.update_game(self.current_game.name, self.current_game.to_dict())
            self.launch_btn.setVisible(True)
        else:
            logger.debug(f"Updating game: {original_name}")
            latest_json_card = GameManager.get_game(original_name)
            if latest_json_card:
                # Retain properties changed outside of this general sidebar form
                self.current_game.label = latest_json_card.label
                self.current_game.last_played = latest_json_card.last_played

            GameManager.update_game(original_name, self.current_game.to_dict())

        # Check if we need to fetch VNDB metadata
        new_vndb = self.edit_vndb.text()
        if new_vndb and (new_vndb != old_vndb or not self.current_game.ogtitle):
            logger.debug("Fetching VNDB data")
            self.fetch_vndb_async(self.current_game.name, new_vndb)

        # Finalize UI
        self.update_game_cover()
        self.lbl_display_name.setText(self.current_game.name)
        self.on_saved()
        self.show_saved_feedback()
        self.update_savedata_visibility()

    def on_prefix_changed(self, prefix_name):
        if not prefix_name: 
            return

        # Gdrive reminder
        if self.current_game and self.current_game.gdrive and self.savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False):
            if SavedataManager.is_savedata_inside_prefix(self.current_game.to_dict()):
                QMessageBox.warning(
                    self, self.tr("Prefix Changed"),
                    self.tr(
                        "This game's savedata lives inside its prefix, and Gdrive sync is enabled.\n\n"
                        "Your existing saves won't be deleted. But the game will create fresh saves at the new prefix location.\n\n"
                        "If you want to bring them along use use 'Copy to...' in Manage Savedata before changing the prefix, "
                        "and update the Savedata Path afterward to keep GDrive sync working.\n\n"
                        "Alternatively: Remove the savedata path field from the game to automatically fill it from the actual Gdrive sync info into the new prefix."
                    )
                )
        
        # Hide warning once a user selects a valid existing prefix
        self.prefix_warning.setVisible(False)
        
        prefix_type = self.prefixes.get(prefix_name, {}).get("type", "wine")

        env_vars_definitions = self.user_settings.get(config.USER_CONF_ENV_VARIABLE_LIST, config.ENV_VARIABLES)
        
        if self.current_game:
            if getattr(self, "_create_mode_defaults", None) is not None:
                active_vars = self._create_mode_defaults
            else:
                current_ui_vars = {}
                for var in env_vars_definitions:
                    cb = self.env_checkboxes.get(var["id"])
                    if cb and cb.isChecked():
                        current_ui_vars[var["key"]] = var["value"]
                self.current_game.envvar = current_ui_vars
                active_vars = self.current_game.envvar

            self.refresh_env_vars(prefix_type, active_vars)

    def show_saved_feedback(self):
        """ Change Save button to Saved for 1.5 seconds"""
        # Store old style/text
        old_text = self.save_btn.text()
        old_style = self.save_btn.styleSheet()
        
        # Change to "Saved!"
        self.save_btn.setText(self.tr("Saved!"))
        self.save_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.save_btn.setEnabled(False) # Prevent double-clicking
        
        # Revert after 1.5 seconds
        def restore():
            self.save_btn.setText(old_text)
            self.save_btn.setStyleSheet(old_style)
            self.save_btn.setEnabled(True)
            
        QTimer.singleShot(1500, restore)

    def delete_game_action(self):
        if not self.current_game or not self.current_game.name:
            return

        # Quick confirmation dialog
        reply = QMessageBox.question(
            self, 
            self.tr("Confirm Deletion"),
            self.tr(f"Are you sure you want to delete '{self.current_game.name}'?"),
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Call the manager to remove from JSON
            try:
                GameManager.delete_game(self.current_game.name)
            except RuntimeError as e:
                QMessageBox.critical(self, self.tr("Error"), self.tr(str(e)))
            
            # Notify the parent tab to refresh the list
            self.on_saved()
            
            # Close the sidebar
            self.on_close()

    def export_game_action(self):
        """Call Game Manager to create json data and call file browser to save it"""
        json_data = GameManager.export_game(self.current_game.name)
        if not json_data:
            logger.error("No json data to export")
            return

        dialog = QFileDialog(self)
        dialog.setWindowTitle(self.tr("Export Game"))
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setNameFilter("JSON Files (*.json)")
        dialog.setViewMode(QFileDialog.Detail)
        dialog.selectFile(f"{self.current_game.name}.json")

        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                save_path = selected_files[0]
                if not save_path.endswith(".json"):
                    save_path += ".json"
                try:
                    with open(save_path, 'w', encoding='utf-8') as f:
                        json.dump(json_data, f, indent=4, ensure_ascii=False)
                    logging.info(f"Game '{self.current_game.name}' exported to '{save_path}'")
                except Exception as e:
                    QMessageBox.critical(self, self.tr("Failed to export"), self.tr(str(e)))
                    logging.error(f"Failed to export game: {e}")

    def open_create_prefix_dialog(self):        
        created_name = PrefixTab.create_new_prefix_flow(self)
        if created_name:
            self.refresh_prefix_combo()
            
            # Auto-select the newly created prefix
            index = self.combo_prefix.findText(created_name)
            if index >= 0:
                self.combo_prefix.setCurrentIndex(index)

    def open_open_savedata_dialog(self):
        dialog = SavedataManagementDialog(self)
        dialog.exec()
        updated_card = GameManager.get_game(self.current_game.name)
        if updated_card:
            self.current_game.savedata_path = updated_card.savedata_path
            self.edit_savedata.setText(updated_card.savedata_path)
            self.gdrive_sync_checkbox.setChecked(updated_card.gdrive)
            self.update_savedata_visibility()
            

    def refresh_prefix_combo(self):
        """Refreshes the prefix list and retains the current selection."""
        from prefix_manager import PrefixManager
        
        self.prefixes = PrefixManager.get_prefix_json()
        current_selection = self.combo_prefix.currentText()
        
        # Block signals so clear() doesn't trigger on_prefix_changed and wipe env vars
        self.combo_prefix.blockSignals(True)
        self.combo_prefix.clear()
        
        self.combo_prefix.addItems(self.prefixes.keys())
        
        # Restore previous selection if it still exists
        index = self.combo_prefix.findText(current_selection)
        if index >= 0:
            self.combo_prefix.setCurrentIndex(index)
            
        self.combo_prefix.blockSignals(False)

    def fetch_vndb_async(self, game_name, vndb_id):
        # Create and start the thread
        self.vndb_thread = VndbWorker(game_name, vndb_id, self.current_game.cover_path)
        self.vndb_thread.finished.connect(self.on_vndb_finished)
        self.vndb_thread.start()

    def on_vndb_finished(self, game_name, results):
        logger.debug(f"[on_vndb_finished] fired for '{game_name}', current_game='{self.current_game.name if self.current_game else None}'")
        if results:
            # Get the jp title
            vn_id = results[0].get('id')
            og_title = VndbManager.get_original_title(results[0])
            target_path = results[0].get("target_path")
            
            # Update the JSON with jp title and cover
            game_card = GameManager.get_game(game_name)
            if game_card:
                cover_path = SystemUtils.get_cover_path(cover_path=target_path, vndb_id=vn_id)
                logger.debug(f"[on_vndb_finished] overwriting cover_path '{game_card.cover_path}' -> '{cover_path}'")
                game_card.ogtitle = og_title
                game_card.cover_path = cover_path
                GameManager.update_game(game_name, game_card.to_dict())

            self.on_metadata_updated(game_name)
            
            # If looking at this game, refresh the cover/links
            if self.current_game and self.current_game.name == game_name:
                self.current_game.ogtitle = og_title
                self.current_game.cover_path = game_card.cover_path
                self.update_game_cover()
                logger.info(f"Background metadata update complete for {game_name}")

    def update_game_cover(self):
        """Shows cover if it has, also show links if it has vndb id."""
        card = self.current_game
        has_vndb = card and card.vndb and card.vndb.strip()
        has_cover = card and card.cover_path

        if has_vndb or has_cover:
            self.media_container.show()

            display_path = SystemUtils.get_cover_path(card.cover_path, card.vndb)
            self.lbl_cover.set_pixmap_from_path(display_path)

            if has_vndb:
                vndb_url = self.VNDB_SITE_URL.format(vndbid=card.vndb)
                self.lbl_vndb_link.setText(f'<a href="{vndb_url}" style="color: #66b2ff;">VNDB</a>')
                jp_encoded_name = urllib.parse.quote(card.ogtitle or card.name)
                egs_url = self.EGS_SITE_URL.format(jpname=jp_encoded_name)
                self.lbl_egs_link.setText(f'<a href="{egs_url}" style="color: #66b2ff;">ErogameScape</a>')
            else:
                self.lbl_vndb_link.clear()
                self.lbl_egs_link.clear()
        else:
            self.media_container.hide()
            self.lbl_cover.set_pixmap_from_path(None)

    def launch_timetracker_dialog(self):
        """Logic for the timetracker dialog"""
        name = self.current_game.name
        tracker = self.process_manager.get_tracker(name)
        
        # Create a tracker when there isn't one for the game
        if not tracker or not tracker.tracker:
            logger.warning(f"No active tracker found for {name}. Creating one.")
            tracker = self.process_manager.start_timetracker(name, self.current_game.path, self.timetracker_settings)

        dialog = TimetrackerDialog(tracker.tracker)
        result = dialog.exec()
        
        if result == QDialog.Accepted:
            # Start tracking logic
            selection = dialog.get_selection()
            if selection:
                title, wid = selection
                self.process_manager.start_manual_tracking(name, wid, title)
        elif result == 2:
            # Stop tracking logic
            self.process_manager.stop_tracking(name)
            self.reset_tracking_labels()           

    def connect_tracker_signals(self, controller=None):
        """Safely disconnects from old tracker and connects to a new one when changing sidebars."""
        if self.active_controller:
            try:
                self.active_controller.stats_received.disconnect(self.update_tracking_ui)
            except (TypeError, RuntimeError):
                pass

        self.active_controller = controller

        if self.active_controller:
            self.active_controller.stats_received.connect(self.update_tracking_ui)
        else:
            # If no controller (game not running), reset the UI
            self.reset_tracking_labels()

    def update_savedata_visibility(self):
        """Shows/hides the Savedata rows based on the current setting."""
        savedata_settings = self.user_settings.get(config.USER_CONF_SAVEDATA, {})
        savedata_enabled = savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False)
        gdrive_logged_in = bool(savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_REFRESH_TOKEN, ""))
        has_savedata = self.current_game and self.current_game.savedata_path
        is_visible = savedata_enabled and gdrive_logged_in and bool(has_savedata)

        row, _ = self.gen_form.getLayoutPosition(self.savedata_row)
        self.gen_form.setRowVisible(row, savedata_enabled)
        gdrive_row, _ = self.gen_form.getWidgetPosition(self.gdrive_sync_checkbox)
        self.gdrive_sync_checkbox.setVisible(is_visible)           

    def update_tracking_ui(self, stats):
        """Update the labels with data received from the worker."""
        self.lbl_session_len.setText(stats["session_length"])
        self.lbl_session_play.setText(stats["session_playtime"])
        self.lbl_total_play.setText(stats["total_playtime"])

    def update_timetracker_visibility(self):
        """Dynamically show/hide the time tracker based on game state and settings."""
        is_enabled = self.timetracker_settings.get("timetracking", False)
        should_be_visible = bool(self.is_running and is_enabled)        
        self.tracking_group.setVisible(should_be_visible)
            
    def set_ui_stop_state(self):
        self.is_running = True
        self.launch_btn.setText(self.tr("Stop Game"))
        self.launch_btn.setStyleSheet("background-color: #c62828; color: white; height: 40px; font-weight: bold;")
        self.update_timetracker_visibility()

    def set_ui_start_state(self):
        self.is_running = False
        self.launch_btn.setText(self.tr("Start Game"))
        self.launch_btn.setStyleSheet("background-color: #2e7d32; color: white; height: 40px; font-weight: bold;")
        self.update_timetracker_visibility()

    def reset_tracking_labels(self):
        self.lbl_session_len.setText("00:00:00")
        self.lbl_session_play.setText("00:00:00")
        self.lbl_total_play.setText("00:00:00")

    def eventFilter(self, obj, event):
        """Close autocomplete popup if clicked somewhere outside"""
        if event.type() == QEvent.MouseButtonPress:
            if self.autocomplete_list.isVisible():
                # Check if the click occurred inside the list or the edit box
                click_pos = event.globalPos()
                list_geo = self.autocomplete_list.geometry()
                edit_geo = self.edit_name.geometry()
                # Map edit box geometry to global coordinates for comparison
                edit_global_rect = self.edit_name.mapToGlobal(self.edit_name.rect().topLeft())
                
                # If the click is outside both the list and the edit box, hide
                if not list_geo.contains(click_pos) and \
                not self.edit_name.rect().contains(self.edit_name.mapFromGlobal(click_pos)):
                    self.autocomplete_list.hide()
                    
        return super().eventFilter(obj, event)
    
    def _on_app_state_changed(self, state):
        if state != Qt.ApplicationActive:
            self.autocomplete_list.hide()

class CoverLabel(QLabel):
    """
    A custom QLabel that automatically scales its pixmap 
    to fit its size while maintaining the aspect ratio.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_pixmap = None
        self.setAlignment(Qt.AlignCenter)

        # Minimum visible size (portrait 2:3 ratio)
        self.setMinimumSize(80, 120)
        # No artificial maximum — let the layout + resizeEvent cap it
        self.setMaximumSize(16_777_215, 16_777_215)

        # Expanding horizontally so it fills the HBoxLayout column
        # Preferred vertically so the layout uses heightForWidth instead of over-allocating space.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.setStyleSheet("""
            background-color: transparent;
            border-radius: 6px;
            border: 0px solid #444;
        """)

    # aspect-ratio plumbing
    def hasHeightForWidth(self) -> bool:
        """Tell Qt: my height depends on my width (aspect ratio)."""
        return (
            self.original_pixmap is not None
            and not self.original_pixmap.isNull()
        )

    def heightForWidth(self, width: int) -> int:
        """Return the correct portrait height for the given width."""
        if self.original_pixmap and not self.original_pixmap.isNull():
            ratio = self.original_pixmap.height() / self.original_pixmap.width()
            return int(width * ratio)
        return super().heightForWidth(width)

    def sizeHint(self) -> QSize:
        w = max(self.minimumWidth(), self.width())
        if self.original_pixmap and not self.original_pixmap.isNull():
            return QSize(w, self.heightForWidth(w))
        return super().sizeHint()

    # pixmap management
    def set_pixmap_from_path(self, path):
        if path:
            self.original_pixmap = QPixmap(path)
        else:
            self.original_pixmap = None
        # Recalculate the layout after a new image is loaded
        self.updateGeometry()
        self.update_scaled()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_scaled()

    def update_scaled(self):
        if self.original_pixmap and not self.original_pixmap.isNull():
            scaled = self.original_pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            super().setPixmap(scaled)
        else:
            super().clear()
