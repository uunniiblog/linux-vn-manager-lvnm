from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QTreeWidget,
    QTreeWidgetItem, QStackedWidget, QSplitter,
    QApplication
)
from PySide6.QtCore import Qt, QSettings, QByteArray
import config
from ui.game_tab import GameTab
from ui.theme_manager import ThemeManager
from ui.platform_ui import PlatformUi
from platform_profile import CURRENT_PLATFORM, Feature, PlatformProfile

class MainWindow(QMainWindow):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, platform: PlatformProfile = CURRENT_PLATFORM):
        super().__init__()
        self.platform = platform
        self.platform_ui = PlatformUi(platform)
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
        self.sidebar = QTreeWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(180)
        self.sidebar.setHeaderHidden(True)
        self.sidebar.setRootIsDecorated(True)
        self.sidebar.setIndentation(18)
                
        self.tab_definitions = [
            (self.tr("Games"), lambda: GameTab(platform=self.platform), None),
            (self.tr("Prefixes"), self._create_prefix_tab, Feature.PREFIXES),
            (self.tr("Runners"), self._create_runner_tab, Feature.RUNNERS),
            (self.tr("Statistics"), self._create_stats_tab, None),
            (self.tr("Settings"), self._create_settings_tab, None),
        ]
        self.tab_definitions = [
            definition for definition in self.tab_definitions
            if self.platform_ui.supported(definition[2])
        ]

        # Settings subtabs
        self.settings_subtabs = [
            (self.tr("Timetracker"), self._create_timetracker_tab),
            (self.tr("Savedata"), self._create_savedata_tab),
        ]

        if self.platform_ui.supported(Feature.EMULATION):
            self.settings_subtabs.append((self.tr("Emulation"), self._create_emulation_tab))
        self.settings_subtabs.append((self.tr("System Info"), self._create_system_info_tab))
        self.settings_subtabs.append((self.tr("About"), self._create_about_tab))

        for index, (label, _, _) in enumerate(self.tab_definitions):
            item = QTreeWidgetItem(self.sidebar, [label])
            item.setData(0, Qt.UserRole, index)
            if label == self.tr("Settings"):
                for subtab_index, (subtab_label, _) in enumerate(self.settings_subtabs, start=len(self.tab_definitions)):
                    child = QTreeWidgetItem(item, [subtab_label])
                    child.setData(0, Qt.UserRole, subtab_index)
                item.setExpanded(True)

        # RIGHT CONTENT AREA
        self.content_stack = QStackedWidget()
        self._loaded_pages = set()
        for _ in range(len(self.tab_definitions) + len(self.settings_subtabs)):
            self.content_stack.addWidget(QWidget())

        # Add widgets to the splitter
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.content_stack)
        self.splitter.setSizes([240, 960])
        
        # Avoid full collapsed
        self.splitter.setCollapsible(0, False) # Index 0 (sidebar) won't hide
        self.splitter.setCollapsible(1, False) # Index 1 (content) won't hide

        # Add splitter to the main layout
        layout.addWidget(self.splitter)

        # Connect signals
        self.sidebar.currentItemChanged.connect(self.on_sidebar_change)
        self.sidebar.setCurrentItem(self.sidebar.topLevelItem(0))

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

    def on_sidebar_change(self, item, previous=None):
        if item is None:
            return
        index = item.data(0, Qt.UserRole)

        # Load widget when selected
        current_widget = self.content_stack.widget(index)

        if index not in self._loaded_pages:
            if 0 <= index < len(self.tab_definitions):
                new_tab = self.tab_definitions[index][1]()
            else:
                new_tab = self.settings_subtabs[index - len(self.tab_definitions)][1]()

            if new_tab:
                # Remove the placeholder and insert the real tab
                self.content_stack.removeWidget(current_widget)
                current_widget.deleteLater()
                self.content_stack.insertWidget(index, new_tab)
                current_widget = new_tab
                self._loaded_pages.add(index)

        # Switch to new tab
        self.content_stack.setCurrentIndex(index)
        # Call refresh_active_tab method in each tab
        if hasattr(current_widget, 'refresh_active_tab'):
            current_widget.refresh_active_tab()

    @staticmethod
    def _create_prefix_tab():
        from ui.prefix_tab import PrefixTab
        return PrefixTab()

    @staticmethod
    def _create_runner_tab():
        from ui.runner_tab import RunnerTab
        return RunnerTab()

    def _create_stats_tab(self):
        from ui.stats_tab import StatsTab
        return StatsTab(self.theme_manager)

    def _create_settings_tab(self):
        from ui.settings_tab import SettingsTab
        return SettingsTab(self.theme_manager, platform=self.platform)

    def _create_timetracker_tab(self):
        from ui.timetracker_tab import TimetrackerTab
        return TimetrackerTab(platform=self.platform)

    def _create_savedata_tab(self):
        from ui.savedata_tab import SavedataTab
        return SavedataTab(platform=self.platform)

    def _create_emulation_tab(self):
        from ui.emulation_tab import EmulationTab
        return EmulationTab()

    def _create_system_info_tab(self):
        from ui.system_info_tab import SystemInfoTab
        return SystemInfoTab(platform=self.platform)

    def _create_about_tab(self):
        from ui.about_tab import AboutTab
        return AboutTab(platform=self.platform)

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

        subtab_font = self.sidebar.font()
        subtab_font.setPointSizeF(subtab_font.pointSizeF() * 0.88)
        for index in range(self.sidebar.topLevelItemCount()):
            item = self.sidebar.topLevelItem(index)
            for child_index in range(item.childCount()):
                item.child(child_index).setFont(0, subtab_font)
