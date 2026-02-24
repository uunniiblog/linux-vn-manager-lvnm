import config
import logging
logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget, 
                             QListWidgetItem, QSplitter, QLineEdit, QFormLayout,
                             QPushButton, QComboBox, QFileDialog, QDialog)
from PySide6.QtCore import Qt, QSettings, QByteArray
from PySide6.QtGui import QKeySequence, QShortcut
from game_manager import GameManager
from game_runner import GameRunner
from prefix_manager import PrefixManager
from ui.game_list_item import GameListItem
from ui.game_sidebar import GameSidebar
from model.game_card import GameCard
from system_utils import SystemUtils

class GameTab(QWidget):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self):
        super().__init__()
        self.card = None
        self.zoom = SystemUtils.load_settings().get("ui_zoom", 1.0)
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

        # Add to layout
        top_controls_layout.addWidget(self.btn_run_in_prefix)
        top_controls_layout.addWidget(self.search_bar, stretch=1)
        list_layout.addLayout(top_controls_layout)

        # Mid layout: Game list
        self.game_list = QListWidget()
        self.game_list.itemClicked.connect(self.on_game_selected)
        list_layout.addWidget(self.game_list)

        # Bottom Button: Add Game
        self.btn_add_game = QPushButton(self.tr("Add Game"))
        self.btn_add_game.clicked.connect(self.on_add_game_clicked)
        list_layout.addWidget(self.btn_add_game)
        
        # Right Side: Sidebar
        self.sidebar = GameSidebar(self)
        self.sidebar.setVisible(False)
        self.sidebar.on_close = self.close_sidebar
        self.sidebar.on_saved = self.refresh_list

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
        new_zoom = SystemUtils.load_settings().get("ui_zoom", 1.0)
        if new_zoom != self.zoom:
            self.zoom = new_zoom
            self.refresh_list()

    def refresh_list(self):
        """Clears and repopulates the game list, filtered by the search bar."""
        self.game_list.clear()
        
        # Get query from search bar
        query = self.search_bar.text() if hasattr(self, 'search_bar') else None
        games_dict = GameManager.list_games(name_query=query)
        game_cards = list(games_dict.values())
        game_cards.sort(
            key=lambda card: card.last_played if card.last_played else "0000-00-00 00:00:00", 
            reverse=True
        )
        
        for card in game_cards:
            item = QListWidgetItem(self.game_list)
            widget = GameListItem(card, zoom_factor=self.zoom)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, card)
            widget.doubleClicked.connect(self.on_game_launch_requested)
            widget.requestOpen.connect(self.on_game_selected_from_card)
            widget.requestRun.connect(self.on_game_launch_requested)
            widget.requestStop.connect(self.on_game_stop_requested)
            widget.requestRefresh.connect(self.refresh_list)
            self.game_list.addItem(item)
            self.game_list.setItemWidget(item, widget)

    def on_game_selected(self, item):
        self.card = item.data(Qt.UserRole)
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
        self.btn_run.clicked.connect(self.run_executable)
        
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

    def run_executable(self):
        """ Run executable in prefix bypassing game card creation """
        # TODO: a way to cancel and add jp locale
        exe_path = self.edit_path.text().strip()
        prefix_name = self.combo_prefix.currentText()

        if not exe_path or not prefix_name:
            logger.debug("Please select both an executable and a prefix.")
            return

        logger.debug(f"Running in Prefix: {exe_path} in {prefix_name}")

        # Create a temporary GameCard in memory
        dummy_card = GameCard(
            name="Temp_Installer",
            path=exe_path,
            prefix=prefix_name,
            vndb="",
            umu_store="",
            umu_gameid=""
        )

        try:
            # Instantiate GameRunner with our dummy card
            runner = GameRunner(name="Ad-Hoc Installer", card_override=dummy_card)
            
            # runner.run() handles the environment, paths, and ExecutionManager calls
            if runner.run():
                logger.debug("Running in prefix launched successfully.")
            else:
                logger.debug("Failed to launch process.")
        except Exception as e:
            logger.error(f"[Error] Failed to run in prefix: {e}")

        # Close the dialog
        self.accept()
