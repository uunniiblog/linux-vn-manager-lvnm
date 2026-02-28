from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, 
    QListWidget, QStackedWidget, QSplitter,
    QApplication
)
from PySide6.QtCore import Qt, QSettings, QByteArray
import config
from ui.game_tab import GameTab
from ui.prefix_tab import PrefixTab
from ui.runner_tab import RunnerTab
from ui.stats_tab import StatsTab
from ui.settings_tab import SettingsTab
from ui.theme_manager import ThemeManager

class MainWindow(QMainWindow):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LVNM - {config.VERSION}")
        self.resize(1200, 800)

        # Load stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

        self.theme_manager = ThemeManager(self.settings)

        # Main Container
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Splitter
        self.splitter = QSplitter(Qt.Horizontal)

        # LEFT SIDEBAR
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(120)

                
        # Sidebar items
        self.sidebar.addItem(self.tr("Games"))
        self.sidebar.addItem(self.tr("Prefixes"))
        self.sidebar.addItem(self.tr("Runners"))
        self.sidebar.addItem(self.tr("Statistics"))
        self.sidebar.addItem(self.tr("Settings"))

        # RIGHT CONTENT AREA
        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(GameTab())
        self.content_stack.addWidget(PrefixTab())
        self.content_stack.addWidget(RunnerTab())
        self.content_stack.addWidget(StatsTab())
        self.content_stack.addWidget(SettingsTab(self.theme_manager))

        # Add widgets to the splitter
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.content_stack)
        
        # Avoid full collapsed
        self.splitter.setCollapsible(0, False) # Index 0 (sidebar) won't hide
        self.splitter.setCollapsible(1, False) # Index 1 (content) won't hide

        # Add splitter to the main layout
        layout.addWidget(self.splitter)

        # Connect signals
        #self.sidebar.currentRowChanged.connect(self.content_stack.setCurrentIndex)
        self.sidebar.currentRowChanged.connect(self.on_sidebar_change)
        self.sidebar.setCurrentRow(0)

        self.restore_ui_state()

        # Apply initial theme
        self.theme_manager.update_theme() 

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
        self.content_stack.setCurrentIndex(index)
        widget = self.content_stack.widget(index)

        # Here we refresh stuff on sidebar changes
        if isinstance(widget, RunnerTab):
            widget.refresh_active_tab()
        elif isinstance(widget, PrefixTab):
            widget.refresh_active_tab()
        elif isinstance(widget, GameTab):
            widget.refresh_active_tab()

    def closeEvent(self, event):
        """
        Triggered when the user closes the window.
        Save the state before exiting
        """
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("mainSplitter", self.splitter.saveState())
        
        super().closeEvent(event)

    def update_sidebar_font(self):
        app_font = QApplication.instance().font()
        app_font.setPointSizeF(app_font.pointSizeF() * 1.5)
        self.sidebar.setFont(app_font)
    
    