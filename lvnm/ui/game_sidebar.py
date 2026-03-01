import config
import urllib.parse
import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, 
    QFormLayout, QLineEdit, QCheckBox, QPushButton, 
    QComboBox, QFileDialog, QScrollArea, QFrame, QSizePolicy,
    QMessageBox
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QTimer
from game_manager import GameManager
from game_runner import GameRunner
from prefix_manager import PrefixManager
from model.game_card import GameCard, GameScope
from system_utils import SystemUtils
from ui.prefix_tab import PrefixTab, CreatePrefixDialog
from ui.console_dialog import ConsoleDialog
from vndb_manager import VndbManager, VndbWorker
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class GameSidebar(QFrame):
    VNDB_SITE_URL = config.VNDB_SITE_URL
    EGS_SITE_URL = config.EGS_SITE_URL
    
    # Dictionary to track games running
    active_runners = {}
    runners = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.current_game: Optional[GameCard] = None
        self.prefixes = None
        self.is_running = None
        self.runner = None
        
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
        media_layout = QHBoxLayout(self.media_container)
        media_layout.setContentsMargins(0, 0, 0, 10)
        media_layout.setAlignment(Qt.AlignTop)

        self.lbl_cover = CoverLabel()
        media_layout.addWidget(self.lbl_cover)

        links_col = QVBoxLayout()
        links_col.setAlignment(Qt.AlignTop)
        links_col.setContentsMargins(15, 0, 0, 0)
        
        self.lbl_vndb_link = QLabel()
        self.lbl_vndb_link.setOpenExternalLinks(True)
        self.lbl_vndb_link.setStyleSheet("font-size: 14px;margin-top: 20px")
        
        self.lbl_egs_link = QLabel()
        self.lbl_egs_link.setOpenExternalLinks(True)
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

        # Scrollable Edit Section 
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QVBoxLayout(container)
        
        # General Info
        gen_group = QGroupBox(self.tr("Edit Game"))
        gen_form = QFormLayout(gen_group)
        gen_form.setLabelAlignment(Qt.AlignLeft)
        self.edit_name = QLineEdit()
        self.edit_path = QLineEdit()
        self.btn_path = QPushButton("...")
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
        self.btn_add_prefix = QPushButton("+")
        self.btn_add_prefix.setFixedSize(32, 32)
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
        self.edit_vndb.setPlaceholderText("vndb id example: v11")
        self.edit_umu_store = QLineEdit()
        self.edit_umu_id = QLineEdit()
        self.label_umu_store = QLabel(self.tr("UMU Store:"))
        self.label_umu_id = QLabel(self.tr("UMU ID:"))

        gen_form.addRow(self.tr("Name:"), self.edit_name)
        gen_form.addRow(self.tr("Path:"), path_row)
        gen_form.addRow(self.tr("Prefix:"), prefix_row)
        gen_form.addRow("", self.prefix_warning)
        gen_form.addRow(self.tr("VNDB:"), self.edit_vndb)
        gen_form.addRow(self.label_umu_store, self.edit_umu_store) # Use the stored label
        gen_form.addRow(self.label_umu_id, self.edit_umu_id)       # Use the stored label
        form.addWidget(gen_group)

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
        form.addWidget(self.env_group)

        form.addStretch(1)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Bottom Buttons
        btns = QHBoxLayout()

        # Delete (Left side)
        self.delete_btn = QPushButton(self.tr("Delete"))
        # Styling it red to indicate a destructive action
        self.delete_btn.setStyleSheet("background-color: #c62828; color: white; font-weight: bold;")
        self.delete_btn.clicked.connect(self.delete_game_action)

        # Save & Cancel (Right side)
        self.save_btn = QPushButton(self.tr("Save"))
        self.save_btn.clicked.connect(self.save_data)

        self.cancel_btn = QPushButton(self.tr("Cancel"))
        self.cancel_btn.clicked.connect(lambda: self.on_close())


        # Add them to the layout in the requested order
        btns.addWidget(self.delete_btn)
        btns.addStretch() # This pushes everything after it to the far right
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.save_btn)

        layout.addLayout(btns)

        # Setup a timer to monitor the game process
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.check_active_runners)
        self.monitor_timer.setInterval(1000)
        self.monitor_timer.start()

    def load_game(self, card: GameCard):
        """
        Loaded from GameTab with the data of the game selected
        """
        self.current_game = card

        self.launch_btn.setVisible(True)

        # Check the registry to set the button state correctly
        if self.current_game.name in self.active_runners:
            self.set_ui_stop_state()
        else:
            self.set_ui_start_state()

        # Update Top Header Name
        self.lbl_display_name.setText(card.name)
        self.update_game_cover()

        # Filling General fields
        self.edit_name.setText(card.name)
        self.edit_path.setText(card.path)
        self.edit_vndb.setText(card.vndb)
        self.edit_umu_store.setText(card.umu_store)
        self.edit_umu_id.setText(card.umu_gameid)
        
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
        self.update_umu_visibility(prefix_type)

        # Load Env Vars
        self.refresh_env_vars(prefix_type, card.envvar)

    def refresh_env_vars(self, prefix_type, active_vars):
        # Clear old checkboxes
        for cb in self.env_checkboxes.values():
            cb.deleteLater()
        self.env_checkboxes.clear()

        for var in config.ENV_VARIABLES:
            req = var.get("req")
            if req and req != prefix_type:
                continue
            
            cb = QCheckBox(var.get("name") or var["id"])
            # Check if current game has this specific key/value pair
            if active_vars.get(var["key"]) == var["value"]:
                cb.setChecked(True)
                
            self.env_checkboxes[var["id"]] = cb
            self.env_layout.addWidget(cb)

    def load_create_game(self, card: GameCard):
        """ Loaded from GameTab to create a new entry """
        self.current_game = card

        # Clear Header UI Fields
        self.lbl_display_name.setText(self.tr("New Game"))
        self.media_container.hide() # Hide media for new games by default
        self.launch_btn.setVisible(False)

        # Load Global Settings for Defaults
        user_settings = SettingsManager()
        
        # Clear General UI Fields
        self.launch_btn.setVisible(False)
        self.edit_name.clear()
        self.edit_path.clear()
        self.edit_vndb.clear()
        self.edit_umu_store.clear()
        self.edit_umu_id.clear()
        
        # Apply Gamescope Defaults from Settings or leave empty
        gs_default_enabled = user_settings.get("gamescope_enabled", False)
        gs_default_params = user_settings.get("gamescope_params", "")
        
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

        # Default visibility (UMU hidden for new entries until prefix is picked)
        self.update_umu_visibility("wine")

        # --- Apply Global Winetricks/Env Var Defaults ---
        # We look at the 'global_env_var' dict from settings and find matches in config.ENV_VARIABLES
        global_env_var = user_settings.get("global_env_var", {})
        
        # Create a temp dict to simulate active env vars for the refresh method
        default_env_vars = {}
        
        # This part assumes your config.ENV_VARIABLES entries have an ID 
        # that matches the keys in global_env_var (like 'jp_locale' or 'jp_timezone')
        for var in config.ENV_VARIABLES:
            var_id = var.get("id")
            if global_env_var.get(var_id): # If 'jp_locale' is True in settings
                default_env_vars[var["key"]] = var["value"]

        # Clear Env Var checkboxes
        self.refresh_env_vars("wine", default_env_vars)
    
    def toggle_game(self):
        if not self.current_game:
            return
        
        game_name = self.current_game.name
        if game_name in self.active_runners:
            # Game is running, so we stop it
            self.stop_game(game_name)
            # self.set_ui_start_state()
        else:
            # Game is not running, so we start it
            self.start_game(game_name)
            # self.set_ui_stop_state()

    def stop_game(self, name):
        """
        Calls the runner's stop logic.
        Sends number of games running in same prefix
        """
        runner = self.active_runners.get(name)
        if runner:
            target_prefix_path = runner.prefix_info["path"]
            prefix_count = 0
            for active_runner in self.active_runners.values():
                active_path = active_runner.prefix_info.get("path")
                if active_path == target_prefix_path:
                    prefix_count += 1
            runner.stop(prefix_count)

            # dont update last played timer here, let check_active_runners handle it
            # self.active_runners.pop(name, None)
            # self.current_game.last_played = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
            # update = self.current_game.to_dict()
            # GameManager.update_game(self.current_game.name, update)

    def start_game(self, name):
        """Initializes the runner and starts the process."""

        # Avoid launching same game multiple times
        if name in self.active_runners:
            logger.debug(f"[Debug] {name} is already running. Ignoring launch request.")
            return False

        try:
            runner = GameRunner(name)
            if runner.run():
                self.active_runners[name] = runner
                self.runners[name] = runner
                logger.debug(f"Started {name}. Total running: {len(self.active_runners)}")
                return True
        except Exception as e:
            logger.error(f"Failed to start {name}: {e}")
            return False

    def check_game_status(self):
        """Polls the runner to see if the game is still alive."""
        if self.runner and not self.runner.is_running():
            logger.debug("Game exited naturally. Cleaning up UI...")
            self.monitor_timer.stop()
            self.runner = None
            
            # Reset the button UI state manually
            self.is_running = False
            self.launch_btn.setText(self.tr("Start Game"))
            self.launch_btn.setStyleSheet("background-color: #2e7d32; color: white; height: 40px; font-weight: bold;")

    def browse_path(self):
        # Create the dialog instance
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
        self.current_game.umu_store = self.edit_umu_store.text()
        self.current_game.umu_gameid = self.edit_umu_id.text()
        
        # Env Vars
        new_env = {}
        for var in config.ENV_VARIABLES:
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

    def update_umu_visibility(self, prefix_type):
        is_proton = (prefix_type == "proton")
        self.edit_umu_store.setVisible(is_proton)
        self.edit_umu_id.setVisible(is_proton)
        self.label_umu_store.setVisible(is_proton)
        self.label_umu_id.setVisible(is_proton)

    def on_prefix_changed(self, prefix_name):
        if not prefix_name: 
            return
        
        # Hide warning once a user selects a valid existing prefix
        self.prefix_warning.setVisible(False)
        
        prefix_type = self.prefixes.get(prefix_name, {}).get("type", "wine")
        self.update_umu_visibility(prefix_type)
        
        if self.current_game:
            # Keep current selected shit
            current_ui_vars = {}
            for var in config.ENV_VARIABLES:
                cb = self.env_checkboxes.get(var["id"])
                if cb and cb.isChecked():
                    current_ui_vars[var["key"]] = var["value"]
            
            self.current_game.envvar = current_ui_vars            
            self.refresh_env_vars(prefix_type, self.current_game.envvar)

    def show_saved_feedback(self):
        """ Change Save button to Saved for 1.5 seconds"""
        # Store old style/text
        old_text = self.save_btn.text()
        old_style = self.save_btn.styleSheet()
        
        # Change to "Saved!"
        self.save_btn.setText(self.tr("Saved!"))
        self.save_btn.setStyleSheet("background-color: #4caf50; color: white; font-weight: bold;")
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
            GameManager.delete_game(self.current_game.name)
            
            # Notify the parent tab to refresh the list
            self.on_saved()
            
            # Close the sidebar
            self.on_close()

    def open_create_prefix_dialog(self):        
        created_name = PrefixTab.create_new_prefix_flow(self)
        if created_name:
            self.refresh_prefix_combo()
            
            # Auto-select the newly created prefix
            index = self.combo_prefix.findText(created_name)
            if index >= 0:
                self.combo_prefix.setCurrentIndex(index)

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
        self.vndb_thread = VndbWorker(game_name, vndb_id)
        self.vndb_thread.finished.connect(self.on_vndb_finished)
        self.vndb_thread.start()

    def on_vndb_finished(self, game_name, results):
        if results:
            # Get the jp title
            og_title = VndbManager.get_original_title(results[0])
            
            # Update the JSON with jp title
            game_card = GameManager.get_game(game_name)
            if game_card:
                game_card.ogtitle = og_title
                GameManager.update_game(game_name, game_card.to_dict())

            self.on_metadata_updated(game_name)
            
            # If looking at this game, refresh the cover/links
            if self.current_game and self.current_game.name == game_name:
                self.current_game.ogtitle = og_title
                self.update_game_cover()
                logger.info(f"Background metadata update complete for {game_name}")

    def update_game_cover(self):
        """Updates only the cover and links based on the current VNDB ID."""
        card = self.current_game
        if card and card.vndb and card.vndb.strip():
            self.media_container.show()
            
            display_path = SystemUtils.get_cover_path(card.vndb)
            self.lbl_cover.set_pixmap_from_path(display_path)

            # Update Links
            vndb_url = self.VNDB_SITE_URL.format(vndbid=card.vndb)
            self.lbl_vndb_link.setText(f'<a href="{vndb_url}" style="color: #66b2ff;">VNDB</a>')
            
            jp_encoded_name = urllib.parse.quote(card.ogtitle or card.name)
            egs_url = self.EGS_SITE_URL.format(jpname=jp_encoded_name)
            self.lbl_egs_link.setText(f'<a href="{egs_url}" style="color: #66b2ff;">ErogameScape</a>')
        else:
            self.media_container.hide()
            self.lbl_cover.set_pixmap_from_path(None)

    def check_active_runners(self):
        """Polls ALL active runners. Cleans up those that finished."""
        finished_games = []

        for name, runner in self.active_runners.items():
            logger.debug(f"check_active_runners {name}")
            if not runner.is_running():
                finished_games.append(name)

        for name in finished_games:
            logging.debug(f"[Game {name} exited. Cleaning up...")
            self.active_runners.pop(name)
            # Get the actual GameCard for the game that finished
            game_to_update = GameManager.get_game(name) 
            
            if game_to_update:
                game_to_update.last_played = datetime.today().strftime('%Y-%m-%d %H:%M:%S')                
                GameManager.update_game(name, game_to_update.to_dict())
                # Update last played column
                # self.on_saved()
                if hasattr(self, 'on_metadata_updated'):
                    self.on_metadata_updated(name)
                
                # If the sidebar is currently showing THIS game, sync the UI object
                if self.current_game and self.current_game.name == name:
                    self.current_game.last_played = game_to_update.last_played
                    self.set_ui_start_state()
        
        if self.current_game:
            is_running = self.current_game.name in self.active_runners
            current_text = self.launch_btn.text()
            
            # If the game is running but the button doesn't say "Stop Game", fix it
            if is_running and current_text != self.tr("Stop Game"):
                self.set_ui_stop_state()
                
            # dont think this can ever happen
            # If the game is NOT running but the button doesn't say "Start Game", fix it
            # elif not is_running and current_text != self.tr("Start Game"):
            #     self.set_ui_start_state()
            
    def set_ui_stop_state(self):
        self.launch_btn.setText(self.tr("Stop Game"))
        self.launch_btn.setStyleSheet("background-color: #c62828; color: white; height: 40px; font-weight: bold;")

    def set_ui_start_state(self):
        self.is_running = False
        self.launch_btn.setText(self.tr("Start Game"))
        self.launch_btn.setStyleSheet("background-color: #2e7d32; color: white; height: 40px; font-weight: bold;")

class CoverLabel(QLabel):
    """
    A custom QLabel that automatically scales its pixmap 
    to fit its size while maintaining the aspect ratio.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_pixmap = None
        self.setAlignment(Qt.AlignCenter)
        # Give it a much bigger default starting size (2:3 aspect ratio)
        self.setMinimumSize(240, 360) 
        self.setMaximumSize(540, 810)
        # self.setMinimumSize(135, 202) 
        # self.setMaximumSize(250, 375)
        # self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Maybe do something with this later
        self.setStyleSheet("""
            background-color: None; 
            border-radius: 6px; 
            border: 0px solid #444;
        """)

    def set_pixmap_from_path(self, path):
        if path:
            self.original_pixmap = QPixmap(path)
        else:
            self.original_pixmap = None
        self.update_scaled()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_scaled()

    def update_scaled(self):
        if self.original_pixmap and not self.original_pixmap.isNull():
            # Scale dynamically keeping the entire image visible
            scaled = self.original_pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            super().setPixmap(scaled)
        else:
            super().clear()