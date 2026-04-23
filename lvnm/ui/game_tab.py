import config
import logging
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, 
    QListWidgetItem, QSplitter, QLineEdit, QFormLayout,
    QPushButton, QComboBox, QFileDialog, QDialog,
    QMenu, QFrame, QLabel
)
from PySide6.QtCore import Qt, QSettings, QByteArray, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QAction, QActionGroup
from game_manager import GameManager
from game_runner import GameRunner
from prefix_manager import PrefixManager
from ui.game_list_item import GameListItem
from ui.game_sidebar import GameSidebar
from ui.import_game_dialog import ImportGameDialog
from model.game_card import GameCard
from settings_manager import SettingsManager
from timetracker.log_manager import LogManager

logger = logging.getLogger(__name__)

class GameTab(QWidget):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self):
        super().__init__()
        self.card = None
        self.user_settings = SettingsManager()
        self.zoom = self.user_settings.get(config.USER_CONF_UI_ZOOM, 1.0)
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

        # Create the Splitter
        self.splitter = QSplitter(Qt.Horizontal)
        
        # Left Side: Game List Container
        self.list_container = QWidget()
        list_layout = QVBoxLayout(self.list_container)

        # Top Layout: Run in Prefix & Search
        top_controls_layout = QHBoxLayout()
        
        # The Button
        self.btn_run_in_prefix = QPushButton(self.tr("Run in prefix"))
        self.btn_run_in_prefix.clicked.connect(self.open_run_dialog)
        
        # The Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(self.tr("Search games..."))
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(self.refresh_list)
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self.search_bar.setFocus)

       # Sort Menu Button 
        self.btn_sort = QPushButton(self.tr("Sort by"))
        self.sort_menu = QMenu(self.btn_sort)
        self.sort_action_group = QActionGroup(self)
        self.sort_action_group.setExclusive(True)

        sort_options = [
            (self.tr("Latest Played"), "latest"),
            (self.tr("Total Playtime"), "playtime"),
            (self.tr("Prefix"), "prefix"),
            (self.tr("Name"), "name")
        ]

        # Load saved sort
        saved_sort = self.user_settings.get(config.USER_CONF_SORT_BY_LIST, "latest")
        for text, data in sort_options:
            action = QAction(text, self.btn_sort)
            action.setCheckable(True)
            action.setData(data)
            
            if data == saved_sort:
                action.setChecked(True)
                
            self.sort_menu.addAction(action)
            self.sort_action_group.addAction(action)

        # Attach the menu to the button
        self.btn_sort.setMenu(self.sort_menu)
        self.sort_action_group.triggered.connect(self.on_sort_changed)

        # Add to layout
        top_controls_layout.addWidget(self.btn_run_in_prefix)
        top_controls_layout.addWidget(self.search_bar, stretch=1)
        top_controls_layout.addWidget(self.btn_sort)
        list_layout.addLayout(top_controls_layout)

        # Mid layout: Game list
        self.game_list = QListWidget()
        self.game_list.itemClicked.connect(self.on_game_selected)
        list_layout.addWidget(self.game_list)

        # Bottom Buttons: Import & Add Game
        bottom_btn_layout = QHBoxLayout()
        bottom_btn_layout.setSpacing(6)

        self.btn_import_game = QPushButton(self.tr("Import"))
        self.btn_import_game.clicked.connect(self.on_import_game_clicked)

        self.btn_add_game = QPushButton(self.tr("Add Game"))
        self.btn_add_game.clicked.connect(self.on_add_game_clicked)

        bottom_btn_layout.addWidget(self.btn_import_game, 15)  # 15% width
        bottom_btn_layout.addWidget(self.btn_add_game, 85)     # 85% width

        list_layout.addLayout(bottom_btn_layout)
        
        # Right Side: Sidebar
        self.sidebar = GameSidebar(self)
        self.sidebar.setVisible(False)
        self.sidebar.on_close = self.close_sidebar
        self.sidebar.on_saved = self.refresh_list
        self.sidebar.on_metadata_updated = self.update_item_metadata

        # Add widgets to the splitter
        self.splitter.addWidget(self.list_container)
        self.splitter.addWidget(self.sidebar)

        self.splitter.setStretchFactor(0, 2) 
        self.splitter.setStretchFactor(1, 1)        
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([800, 400])

        # Save splitter position on resize
        self.splitter.splitterMoved.connect(self.save_splitter_state)

        self.main_layout.addWidget(self.splitter)
        self._restore_state()
        self.refresh_list()

    def refresh_active_tab(self):
        """Forces the currently visible sub-tab to reload its data"""
        if self.card is not None:
            fresh_card = GameManager.get_game(self.card.name)
            if fresh_card:
                self.card = fresh_card
                self.sidebar.load_game(self.card)

        # Reload list if zoom changed
        new_zoom = self.user_settings.get(config.USER_CONF_UI_ZOOM, 1.0)
        if new_zoom != self.zoom:
            self.zoom = new_zoom
            self.refresh_list()

    def on_sort_changed(self, action):
        """Saves the sort preference and refreshes the list"""
        sort_data = action.data()
        self.user_settings.set(config.USER_CONF_SORT_BY_LIST, sort_data)
        self.refresh_list()

    def update_item_metadata(self, game_name):
        """Updates only the widget of a specific game without reloading the whole list."""
        for i in range(self.game_list.count()):
            item = self.game_list.item(i)
            card = item.data(Qt.UserRole)
            if card is None:
                continue

            if card.name == game_name:
                # Get the latest data from the Manager
                updated_card = GameManager.get_game(game_name)
                if not updated_card:
                    return

                # Update the data stored in the item
                item.setData(Qt.UserRole, updated_card)
                widget = self.game_list.itemWidget(item)
                widget.update_ui(updated_card)
                
                logger.debug(f"Targeted UI update for {game_name} complete.")
                return

    def refresh_list(self):
        """Clears and repopulates the game list, grouped by labels."""
        self.game_list.clear()
        self.section_items = {}
        
        query = self.search_bar.text() if hasattr(self, 'search_bar') else None
        games_dict = GameManager.list_games(name_query=query)
        all_cards = list(games_dict.values())
        saved_labels = self.user_settings.get(config.USER_CONF_SAVED_LABELS, [])
        show_headers = len(saved_labels) > 0

        groups = {lbl: [] for lbl in saved_labels}
        groups[""] = []

        # Group games by label
        for card in all_cards:
            lbl = getattr(card, 'label', "") or ""
            
            if lbl in groups:
                # Game matches a known saved label
                groups[lbl].append(card)
            else:
                # Game has no label, or a label that was deleted from settings
                groups[""].append(card)

        # Sort labels alphabetically, move uncategorized at the end
        sorted_labels = sorted([l for l in groups.keys() if l != ""], key=str.lower)
        final_label_order = sorted_labels + [""]

        # Process each group
        sort_pref = self.user_settings.get(config.USER_CONF_SORT_BY_LIST, "latest")
        log_mgr = LogManager()

        for lbl in final_label_order:
            if lbl not in groups: continue

            if show_headers:
                self.section_items[lbl] = []

            # Header
            is_expanded = True # Default if headers are off
            if show_headers:
                header_item = QListWidgetItem(self.game_list)
                # Load if it was expanded
                is_expanded = self.user_settings.get(f"section_expanded_{lbl}", True)

                header_widget = SectionHeader(lbl, is_expanded=is_expanded, zoom_factor=self.zoom)
                header_item.setSizeHint(header_widget.sizeHint())
                header_item.setFlags(Qt.NoItemFlags)
                
                # Connect Header Signals
                header_widget.toggled.connect(lambda state, l=lbl: self.toggle_section(l, state))
                header_widget.deleteRequested.connect(self.delete_label_globally)
                
                self.game_list.addItem(header_item)
                self.game_list.setItemWidget(header_item, header_widget)
            
            group_cards = groups[lbl]
            
            # Sort games within this group based on user preference
            if sort_pref == "name":
                # Alphabetical by name
                group_cards.sort(key=lambda c: c.name.lower())
            elif sort_pref == "prefix":
                # Alphabetical by prefix, then by name
                group_cards.sort(key=lambda c: (c.prefix.lower(), c.name.lower()))
            elif sort_pref == "playtime":
                # Sort by total playtime
                group_cards.sort(key=lambda c: log_mgr.get_total_app_playtime(log_mgr.get_log_name_from_path(c.path)), reverse=True)
            else: 
                # Default: Latest
                group_cards.sort(key=lambda c: c.last_played if c.last_played else "0", reverse=True)

            # Add the Game Items
            for card in group_cards:
                item = QListWidgetItem(self.game_list)
                widget = GameListItem(card, zoom_factor=self.zoom)
                item.setSizeHint(widget.sizeHint())
                item.setData(Qt.UserRole, card)
                
                # Connect signals
                widget.doubleClicked.connect(self.on_game_launch_requested)
                widget.requestOpen.connect(self.on_game_selected_from_card)
                widget.requestRun.connect(self.on_game_launch_requested)
                widget.requestStop.connect(self.on_game_stop_requested)
                widget.requestRefresh.connect(self.refresh_list)
                widget.requestExport.connect(self.on_export_game)
                
                self.game_list.addItem(item)
                self.game_list.setItemWidget(item, widget)
                
                # Register list to its section
                if show_headers:
                    self.section_items[lbl].append(item)
                     # Apply initial collapsed state
                    if not is_expanded:
                        item.setHidden(True)

    def toggle_section(self, label_name, expanded):
        """Hides or shows all QListWidgetItems associated with a label."""
        # Save state
        self.user_settings.set(f"section_expanded_{label_name}", expanded)
        
        if label_name in self.section_items:
            for item in self.section_items[label_name]:
                item.setHidden(not expanded)

    def delete_label_globally(self, label_name):
        """Removes the label from the global list and all games."""
        # Remove from saved labels
        saved_labels = self.user_settings.get(config.USER_CONF_SAVED_LABELS, [])
        if label_name in saved_labels:
            saved_labels.remove(label_name)
            self.user_settings.set(config.USER_CONF_SAVED_LABELS, saved_labels)

        # Remove section state from userconfig
        expansion_key = f"section_expanded_{label_name}"
        self.user_settings.remove(expansion_key)

        # Strip label from every game that has it
        all_games = GameManager.list_games()
        for name, card in all_games.items():
            if getattr(card, 'label', None) == label_name:
                card.label = ""
                GameManager.update_game(name, card.to_dict())
        
        logger.info(f"Deleted label '{label_name}' and updated games.")
        self.refresh_list()

    def on_game_selected(self, item):
        """Load data and open sidebar"""
        self.card = item.data(Qt.UserRole)
        if not self.card:
            return
        self.sidebar.load_game(self.card)
        self.show_sidebar_safely()

    def on_game_selected_from_card(self, card):
        self.card = card
        self.sidebar.load_game(self.card)
        self.show_sidebar_safely()

    def on_add_game_clicked(self):
        """Deselects the list and opens the sidebar empty"""
        self.game_list.clearSelection()
        
        # Create a blank game card to populate the sidebar text fields
        empty_card = GameCard(name="", path="", prefix="", vndb="")
        self.sidebar.load_create_game(empty_card)
        
        self.show_sidebar_safely()

    def on_import_game_clicked(self):
        """Call file browser for json file, calls manager to import"""
        # Open file browser to search for json files
        dialog = QFileDialog(self)
        dialog.setWindowTitle(self.tr("Import Game"))
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setNameFilter("JSON Files (*.json)")
        dialog.setViewMode(QFileDialog.Detail)

        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                import_path = selected_files[0]
                try:
                    logging.debug(f"Loaded import file: '{import_path}'")
                    import_dialog = ImportGameDialog(import_path, parent=self)
                    import_dialog.import_finished.connect(self.refresh_list)
                    result = import_dialog.exec()
                    #self.refresh_list()
                except Exception as e:
                    logging.error(f"Failed to read import file: {e}")

    def show_sidebar_safely(self):
        """ Show sidebar """
        if not self.sidebar.isVisible():
            self.sidebar.setVisible(True)
            if not self.settings.contains("GameTab/Splitter"):
                self.splitter.setSizes([self.width() - 350, 350])

    def close_sidebar(self):
        self.sidebar.setVisible(False)
        self.game_list.clearSelection()

    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        state = self.settings.value("GameTab/Splitter")
        if state:
            self.splitter.restoreState(QByteArray(state))
            self.sidebar.setVisible(False)

    def save_splitter_state(self):
        """Save state immediately when moved"""
        self.settings.setValue("GameTab/Splitter", self.splitter.saveState())

    def open_run_dialog(self):
        """Opens the custom dialog to run a file temporarily"""
        dialog = RunInPrefixDialog(self)
        dialog.exec()

    def on_game_launch_requested(self, game_card):
        """ Handles launching game from double click/menu """
        self.sidebar.load_game(game_card)
        self.show_sidebar_safely()
        self.sidebar.start_game(game_card.name)

    def on_game_stop_requested(self, game_card):
        """ Handles stoping game """
        self.sidebar.stop_game(game_card.name)

    def on_export_game(self, game_card):
        """ Handles stoping game """
        self.sidebar.load_game(game_card)
        self.show_sidebar_safely()
        self.sidebar.export_game_action()

class RunInPrefixDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Run in Prefix"))
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # File Picker
        self.edit_path = QLineEdit()
        self.btn_browse = QPushButton("...")
        self.btn_browse.clicked.connect(self.browse)
        
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.edit_path)
        path_layout.addWidget(self.btn_browse)
        form.addRow(self.tr("Executable:"), path_layout)

        # Prefix Selector
        self.combo_prefix = QComboBox()
        prefixes = PrefixManager.get_prefix_json()
        if prefixes:
            self.combo_prefix.addItems(prefixes.keys())
        form.addRow(self.tr("Prefix:"), self.combo_prefix)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton(self.tr("Cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_run = QPushButton(self.tr("Run"))
        self.btn_run.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self.btn_run.clicked.connect(self.run_in_prefix)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_run)

        layout.addLayout(btn_layout)

    def browse(self):
        # Create the dialog instance
        dialog = QFileDialog(self)
        dialog.setWindowTitle(self.tr("Select Game Executable"))
        
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setNameFilter("All Files (*)")
        dialog.setViewMode(QFileDialog.Detail)      

        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                self.edit_path.setText(selected_files[0])

    def run_in_prefix(self):
        """ Run executable in prefix bypassing game card creation """
        exe_path = self.edit_path.text().strip()
        prefix_name = self.combo_prefix.currentText()

        if not exe_path or not prefix_name:
            logger.debug("Please select both an executable and a prefix.")
            return

        user_settings = SettingsManager()
        global_env_var = user_settings.get(config.USER_CONF_GLOBAL_VARIABLES, {})
        env_vars_definitions = user_settings.get(config.USER_CONF_ENV_VARIABLE_LIST, config.ENV_VARIABLES)
        env_vars = {}

        for var in env_vars_definitions:
            var_id = var.get("id")
            if global_env_var.get(var_id):
                env_vars[var["key"]] = str(var["value"])

        logger.debug(f"Running in Prefix: {exe_path} in {prefix_name}")
        if env_vars:
            logger.debug(f"Applying Global Env Vars: {env_vars}")

        try:
            # Instantiate GameRunner with our dummy card
            runner = GameRunner("Temp_Installer")
            runner.run_in_prefix(exe_path, prefix_name, env_vars=env_vars)
        except Exception as e:
            logger.error(f"[Error] Failed to run in prefix: {e}")

        # Close the dialog
        self.accept()

class SectionHeader(QWidget):
    """A non-clickable visual separator for the list"""
    # Emits True if expanded, False if collapsed
    toggled = Signal(bool)
    # Emits the label name to be deleted
    deleteRequested = Signal(str)

    def __init__(self, title, is_expanded=True, zoom_factor=1.0, parent=None):
        super().__init__(parent)
        self.label_name = title
        self.expanded = is_expanded
        self.zoom = zoom_factor

        # Allow the widget to receive mouse events
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(int(10 * zoom_factor), int(15 * zoom_factor), 10, int(5 * zoom_factor))

        # Expand/Collapse
        self.indicator = QLabel("▼" if is_expanded else "▶")
        self.indicator.setFixedSize(int(20 * zoom_factor), int(20 * zoom_factor))
        self.indicator.setStyleSheet("color: #888888; font-weight: bold;")
        layout.addWidget(self.indicator)
        
        # Label title
        display_text = self.tr("UNCATEGORIZED") if not title else title.upper()
        self.label = QLabel(display_text)
        self.label.setStyleSheet(f"""
            font-weight: bold; 
            font-size: {int(10 * zoom_factor)}pt; 
            letter-spacing: 1px;
        """)
        
        layout.addWidget(self.label)
        
        # Add line separatory
        line = QFrame()

        line.setFrameShape(QFrame.NoFrame)
        thickness = int(10 * zoom_factor) 
        line.setFixedHeight(thickness)
        line.setStyleSheet("""
            background-color: #444444; 
            border: none;
            border-radius: 1px;
        """)
        
        layout.addWidget(line, stretch=1)

    def _toggle_state(self):
        self.expanded = not self.expanded
        self.indicator.setText("▼" if self.expanded else "▶")
        self.toggled.emit(self.expanded)

    def contextMenuEvent(self, event):
        """Right-click to delete the section"""
        if not self.label_name: # Don't allow deleting the 'Uncategorized' label itself
            return

        menu = QMenu(self)
        delete_action = menu.addAction(self.tr(f"Delete Label: {self.label_name}"))
        
        action = menu.exec(event.globalPos())
        if action == delete_action:
            self.deleteRequested.emit(self.label_name)

    def mousePressEvent(self, event):
        """Handle click on any part of the header"""
        if event.button() == Qt.LeftButton:
            self._toggle_state()
        super().mousePressEvent(event)