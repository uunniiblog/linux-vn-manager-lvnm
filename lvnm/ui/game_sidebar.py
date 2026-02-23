import config
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, 
    QFormLayout, QLineEdit, QCheckBox, QPushButton, 
    QComboBox, QFileDialog, QScrollArea, QFrame, QSizePolicy,
    QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from game_manager import GameManager
from game_runner import GameRunner
from prefix_manager import PrefixManager
from model.game_card import GameCard, GameScope
from system_utils import SystemUtils

class GameSidebar(QFrame):
    # Dictionary to track multiple games running
    active_runners = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.current_game: Optional[GameCard] = None
        self.prefixes = None
        self.is_running = None
        self.runner = None
        
        layout = QVBoxLayout(self)
        
        # Launch Section
        self.launch_btn = QPushButton(self.tr("Start Game"))
        self.launch_btn.setStyleSheet("background-color: #2e7d32; color: white; height: 40px; font-weight: bold;")
        self.launch_btn.clicked.connect(self.toggle_game)
        layout.addWidget(self.launch_btn)

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
        
        self.combo_prefix = QComboBox()
        self.combo_prefix.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.combo_prefix.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.combo_prefix.currentTextChanged.connect(self.on_prefix_changed)

        # Warning label for missing prefix
        self.prefix_warning = QLabel()
        self.prefix_warning.setStyleSheet("color: #ff5555; font-size: 10px; font-weight: bold;")
        self.prefix_warning.setVisible(False)
        self.prefix_warning.setWordWrap(True)
        self.prefix_warning.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.edit_vndb = QLineEdit()
        self.edit_umu_store = QLineEdit()
        self.edit_umu_id = QLineEdit()
        self.label_umu_store = QLabel(self.tr("UMU Store:"))
        self.label_umu_id = QLabel(self.tr("UMU ID:"))

        gen_form.addRow(self.tr("Name:"), self.edit_name)
        gen_form.addRow(self.tr("Path:"), path_row)
        gen_form.addRow(self.tr("Prefix:"), self.combo_prefix)
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
            self._set_ui_stop_state()
        else:
            self._set_ui_start_state()

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
            
            cb = QCheckBox(var["id"])
            # Check if current game has this specific key/value pair
            if active_vars.get(var["key"]) == var["value"]:
                cb.setChecked(True)
                
            self.env_checkboxes[var["id"]] = cb
            self.env_layout.addWidget(cb)

    def load_create_game(self, card: GameCard):
        """ Loaded from GameTab to create a new entry """
        self.current_game = card

        # Load Global Settings for Defaults
        user_settings = SystemUtils.load_settings()
        
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
        # We look at the 'global_wt' dict from settings and find matches in config.ENV_VARIABLES
        global_wt = user_settings.get("global_wt", {})
        
        # Create a temp dict to simulate active env vars for the refresh method
        default_env_vars = {}
        
        # This part assumes your config.ENV_VARIABLES entries have an ID 
        # that matches the keys in global_wt (like 'jp_locale' or 'jp_timezone')
        for var in config.ENV_VARIABLES:
            var_id = var.get("id")
            if global_wt.get(var_id): # If 'jp_locale' is True in settings
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
            self._set_ui_start_state()
        else:
            # Game is not running, so we start it
            self.start_game(game_name)
            self._set_ui_stop_state()

    def stop_game(self, name):
        """Calls the runner's stop logic."""
        runner = self.active_runners.get(name)
        if runner:
            runner.stop()
            # dont update last played timer here, let check_active_runners handle it
            # self.active_runners.pop(name, None)
            # self.current_game.last_played = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
            # update = self.current_game.to_dict()
            # GameManager.update_game(self.current_game.name, update)

    def start_game(self, name):
        """Initializes the runner and starts the process."""
        try:
            runner = GameRunner(name)
            if runner.run():
                self.active_runners[name] = runner
                print(f"Started {name}. Total running: {len(self.active_runners)}")
        except Exception as e:
            print(f"Failed to start {name}: {e}")

    def check_game_status(self):
        """Polls the runner to see if the game is still alive."""
        if self.runner and not self.runner.is_running():
            print("Game exited naturally. Cleaning up UI...")
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

        original_name = self.current_game.name

        # Gather environment variables from checkboxes
        new_env = {}
        for var in config.ENV_VARIABLES:
            cb = self.env_checkboxes.get(var["id"])
            if cb and cb.isChecked():
                new_env[var["key"]] = var["value"]

        # Update the dataclass
        self.current_game.name = self.edit_name.text()
        self.current_game.path = self.edit_path.text()
        self.current_game.prefix = self.combo_prefix.currentText()
        self.current_game.vndb = self.edit_vndb.text()
        self.current_game.umu_store = self.edit_umu_store.text()
        self.current_game.umu_gameid = self.edit_umu_id.text()
        self.current_game.envvar = new_env
        
        # Update Gamescope 
        self.current_game.gamescope.enabled = "true" if self.gs_enabled.isChecked() else "false"
        self.current_game.gamescope.parameters = self.gs_params.text()

        updates = self.current_game.to_dict()
        
        if not original_name:
            # CREATE MODE
            GameManager.add_game(
                exe=self.current_game.path,
                name=self.current_game.name,
                prefix=self.current_game.prefix,
                vndb=self.current_game.vndb
            )

            # Update to save env vars & gamescope TODO: do in one method only
            GameManager.update_game(self.current_game.name, updates)
            self.launch_btn.setVisible(True)
        else:
            # --- UPDATE MODE ---
            GameManager.update_game(original_name, updates)
        
        self.on_saved()
        self.show_saved_feedback()
        # self.on_close()

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

    def check_active_runners(self):
        """Polls ALL active runners. Cleans up those that finished."""
        finished_games = []

        for name, runner in self.active_runners.items():
            print(f"{datetime.today().strftime('%Y-%m-%d %H:%M:%S')} - check_active_runners {name}")
            if not runner.is_running():
                finished_games.append(name)

        for name in finished_games:
            print(f"{datetime.today().strftime('%Y-%m-%d %H:%M:%S')} - Game {name} exited. Cleaning up...")
            self.active_runners.pop(name)
            # Get the actual GameCard for the game that finished
            game_to_update = GameManager.get_game(name) 
            
            if game_to_update:
                game_to_update.last_played = datetime.today().strftime('%Y-%m-%d %H:%M:%S')                
                GameManager.update_game(name, game_to_update.to_dict())
                # Update last played column
                self.on_saved()
                
                # If the sidebar is currently showing THIS game, sync the UI object
                if self.current_game and self.current_game.name == name:
                    self.current_game.last_played = game_to_update.last_played
                    self._set_ui_start_state()
            
    def _set_ui_stop_state(self):
        self.launch_btn.setText(self.tr("Stop Game"))
        self.launch_btn.setStyleSheet("background-color: #c62828; color: white; height: 40px; font-weight: bold;")

    def _set_ui_start_state(self):
        self.is_running = False
        self.launch_btn.setText(self.tr("Start Game"))
        self.launch_btn.setStyleSheet("background-color: #2e7d32; color: white; height: 40px; font-weight: bold;")