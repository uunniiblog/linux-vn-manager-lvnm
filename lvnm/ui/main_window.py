from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QStackedWidget, QSplitter,
    QApplication
)
import config
from PySide6.QtCore import Qt, QSettings, QByteArray, QTimer
from ui.game_tab import GameTab
from ui.gamepad.shell import GamepadShell
from ui.gamepad.toggle_switch import ToggleSwitch
from ui.theme_manager import ThemeManager
from sdl_gamepad_backend import SDLGamepadBackend

class MainWindow(QMainWindow):
    SETTINGS_FILE = config.UI_SETTINGS
    UI_MODE_KEY = "uiMode"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LVNM - {config.VERSION}")
        self.resize(1200, 800)

        # Load stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)
        saved_mode = self.settings.value(self.UI_MODE_KEY, "desktop")
        if saved_mode not in ("desktop", "gamepad"):
            saved_mode = "desktop"

        self.theme_manager = ThemeManager(self.settings)

        self.gamepad_backend = SDLGamepadBackend(self)

        # Root stack keeps the existing desktop UI and controller UI separate
        self.ui_stack = QStackedWidget()
        self.setCentralWidget(self.ui_stack)

        self.desktop_shell = QWidget()
        layout = QHBoxLayout(self.desktop_shell)
        layout.setContentsMargins(0, 0, 0, 0)

        # Splitter
        self.splitter = QSplitter(Qt.Horizontal)

        # LEFT SIDEBAR
        sidebar_container = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 8)
        sidebar_layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(120)

                
        # Sidebar items
        self.sidebar.addItem(self.tr("Games"))
        self.sidebar.addItem(self.tr("Prefixes"))
        self.sidebar.addItem(self.tr("Runners"))
        self.sidebar.addItem(self.tr("Statistics"))
        self.sidebar.addItem(self.tr("Settings"))
        sidebar_layout.addWidget(self.sidebar, 1)

        self.gamepad_mode_button = ToggleSwitch(self.tr("Enable Gamepad UI"))
        self.gamepad_mode_button.setObjectName("uiModeToggle")
        self.gamepad_mode_button.toggled.connect(self._on_desktop_mode_toggled)
        sidebar_layout.addWidget(self.gamepad_mode_button, 0, Qt.AlignHCenter)

        # RIGHT CONTENT AREA
        self.content_stack = QStackedWidget()
        for _ in range(5):
            self.content_stack.addWidget(QWidget())
        # self.content_stack.addWidget(GameTab())
        # self.content_stack.addWidget(PrefixTab())
        # self.content_stack.addWidget(RunnerTab())
        # self.content_stack.addWidget(StatsTab(self.theme_manager))
        # self.content_stack.addWidget(SettingsTab(self.theme_manager))

        # Add widgets to the splitter
        self.splitter.addWidget(sidebar_container)
        self.splitter.addWidget(self.content_stack)
        
        # Avoid full collapsed
        self.splitter.setCollapsible(0, False) # Index 0 (sidebar) won't hide
        self.splitter.setCollapsible(1, False) # Index 1 (content) won't hide

        # Add splitter to the main layout
        layout.addWidget(self.splitter)

        self.gamepad_shell = GamepadShell(self.gamepad_backend)
        self.gamepad_shell.desktop_requested.connect(
            lambda: self.set_ui_mode("desktop")
        )
        self.ui_stack.addWidget(self.desktop_shell)
        self.ui_stack.addWidget(self.gamepad_shell)

        # Connect signals
        #self.sidebar.currentRowChanged.connect(self.content_stack.setCurrentIndex)
        self.sidebar.currentRowChanged.connect(self.on_sidebar_change)
        if saved_mode == "desktop":
            self.sidebar.setCurrentRow(0)

        self.restore_ui_state()

        self.set_ui_mode(saved_mode)

        # Apply initial theme
        self.theme_manager.update_theme()

        # Give Qt time to present the window before SDL library/device probing.
        QTimer.singleShot(100, self.gamepad_backend.start)

    def restore_ui_state(self):
        """Restores window size and splitter positions."""
        # Restore window geometry (position and size)
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        # Restore Splitter state (sidebar width)
        splitter_state = self.settings.value("mainSplitter")
        if splitter_state:
            # We cast to QByteArray because QSettings sometimes returns it as a different type
            self.splitter.restoreState(QByteArray(splitter_state))

    def on_sidebar_change(self, index):

        # Load widget when selected
        current_widget = self.content_stack.widget(index)

        if type(current_widget) is QWidget:
            new_tab = None
            if index == 0:
                new_tab = GameTab()
            elif index == 1:
                from ui.prefix_tab import PrefixTab
                new_tab = PrefixTab()
            elif index == 2:
                from ui.runner_tab import RunnerTab
                new_tab = RunnerTab()
            elif index == 3:
                from ui.stats_tab import StatsTab
                new_tab = StatsTab(self.theme_manager)
            elif index == 4:
                from ui.settings_tab import SettingsTab
                new_tab = SettingsTab(self.theme_manager)

            if new_tab:
                # Remove the placeholder and insert the real tab
                self.content_stack.removeWidget(current_widget)
                self.content_stack.insertWidget(index, new_tab)
                current_widget = new_tab

        # Switch to new tab
        self.content_stack.setCurrentIndex(index)
        widget = self.content_stack.widget(index)

        # Call refresh_active_tab method in each tab
        if hasattr(current_widget, 'refresh_active_tab'):
            current_widget.refresh_active_tab()

    def set_ui_mode(self, mode):
        """Switch shells and persist the user's preferred interface."""
        is_gamepad = mode == "gamepad"
        self.gamepad_mode_button.blockSignals(True)
        self.gamepad_mode_button.setChecked(is_gamepad)
        self.gamepad_mode_button.blockSignals(False)
        self.gamepad_mode_button.sync_visual_state()
        self.gamepad_shell.mode_button.blockSignals(True)
        self.gamepad_shell.mode_button.setChecked(is_gamepad)
        self.gamepad_shell.mode_button.blockSignals(False)
        self.gamepad_shell.mode_button.sync_visual_state()
        self.ui_stack.setCurrentWidget(self.gamepad_shell if is_gamepad else self.desktop_shell)
        self.settings.setValue(self.UI_MODE_KEY, mode)

        if is_gamepad:
            self.gamepad_shell.activate()
        else:
            if self.sidebar.currentRow() < 0:
                self.sidebar.setCurrentRow(0)
            self.sidebar.setFocus(Qt.OtherFocusReason)
            current_widget = self.content_stack.currentWidget()
            if hasattr(current_widget, 'refresh_active_tab'):
                current_widget.refresh_active_tab()

    def _on_desktop_mode_toggled(self, checked):
        if checked:
            self.set_ui_mode("gamepad")

    def closeEvent(self, event):
        """
        Triggered when the user closes the window.
        Save the state before exiting
        """
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("mainSplitter", self.splitter.saveState())
        self.gamepad_backend.stop()

        super().closeEvent(event)

    def update_sidebar_font(self):
        app_font = QApplication.instance().font()
        app_font.setPointSizeF(app_font.pointSizeF() * 1.5)
        self.sidebar.setFont(app_font)
