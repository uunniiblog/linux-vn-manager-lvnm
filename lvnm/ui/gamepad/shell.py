from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from ui.gamepad.game_tab import GamepadGameTab
from ui.gamepad.toggle_switch import ToggleSwitch

class GamepadShell(QWidget):
    """Controller-oriented application shell with controller tab switching."""
    desktop_requested = Signal()

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.setObjectName("gamepadShell")
        self.backend = backend

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        rail = QWidget()
        rail.setObjectName("gamepadRail")
        rail.setFixedWidth(190)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(12, 20, 12, 16)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("gamepadSidebar")
        for text in (self.tr("Games"), self.tr("Prefixes"), self.tr("Runners"), self.tr("Statistics"), self.tr("Settings")):
            self.sidebar.addItem(text)

        self.sidebar.currentRowChanged.connect(self.on_sidebar_change)
        rail_layout.addWidget(self.sidebar, 1)

        self.mode_button = ToggleSwitch(self.tr("Enable Gamepad UI"))
        self.mode_button.setObjectName("gamepadModeToggle")
        self.mode_button.setChecked(True)
        self.mode_button.toggled.connect(self._on_mode_toggled)
        rail_layout.addWidget(self.mode_button, 0, Qt.AlignHCenter)
        layout.addWidget(rail)

        self.content_stack = QStackedWidget()
        for _ in range(5):
            self.content_stack.addWidget(QWidget())
        layout.addWidget(self.content_stack, 1)

        self.setStyleSheet("""
            QWidget#gamepadShell { background: #171619; color: #f3f0f5; }
            QWidget#gamepadGameTab { background: #171619; color: #f3f0f5; }
            QWidget#gamepadGameDetail { background: #171619; color: #f3f0f5; }
            QWidget#gamepadRail { background: #242229; }
            QListWidget#gamepadSidebar {
                background: transparent;
                border: none;
                outline: none;
                font-size: 16px;
            }
            QListWidget#gamepadSidebar::item {
                color: #e5e0e8;
                border-radius: 8px;
                margin: 4px 0;
                padding: 14px;
            }
            QListWidget#gamepadSidebar::item:selected {
                background: #514660;
                color: white;
                border-left: 4px solid #bd8cff;
            }
            QCheckBox#gamepadModeToggle {
                background: transparent;
                color: #f3f0f5;
            }
            QLabel#gamepadTitle {
                background: transparent;
                color: white;
                font-size: 30px;
                font-weight: 800;
            }
            QLabel#gamepadConnection {
                background: transparent;
                color: #bd8cff;
                font-weight: 600;
            }
            QListWidget#gamepadGameGrid {
                border: none;
                outline: none;
                background: transparent;
            }
            QScrollArea#gamepadSectionsScroll {
                border: none;
                background: transparent;
            }
            QScrollArea#gamepadSectionsScroll > QWidget > QWidget {
                background: transparent;
            }
            QPushButton#gamepadLabelHeader {
                min-height: 34px;
                padding: 7px 14px;
                border: 1px solid #343138;
                border-radius: 7px;
                background: #211f24;
                color: #eee9f1;
                font-size: 16px;
                font-weight: 700;
                text-align: left;
            }
            QPushButton#gamepadLabelHeader:focus {
                border: 2px solid #bd8cff;
                background: #332e39;
            }
            QPushButton#gamepadLabelHeader[controllerSelected="true"] {
                border: 2px solid #bd8cff;
                background: #332e39;
            }
            QLabel#gamepadDetailTitle {
                color: white;
                font-size: 27px;
                font-weight: 800;
            }
            QLabel#gamepadDetailCover {
                border: 2px solid #343138;
                border-radius: 8px;
                background: #1d1c20;
                color: #aaa5ae;
            }
            QLabel#gamepadDetailLayoutArt {
                border: 2px solid #343138;
                border-radius: 8px;
                background: #1d1c20;
            }
            QPushButton#gamepadBackButton,
            QPushButton#gamepadPlayButton {
                min-height: 38px;
                padding: 4px 18px;
                font-weight: 700;
            }
            QPushButton#gamepadPlayButton,
            QPushButton[gamepadPlayAction="true"] {
                background: #2d7d38;
                color: white;
            }
            QPushButton#gamepadPlayButton[running="true"],
            QPushButton[gamepadPlayAction="true"][running="true"] {
                background: #b33232;
                color: white;
            }
            QPushButton#gamepadDeleteButton {
                background: #a83232;
                color: white;
            }
            QPushButton[gamepadAction="true"] {
                min-height: 50px;
                font-size: 16px;
                font-weight: 600;
            }
            QPushButton#gamepadPrefixButton,
            QPushButton#gamepadChoiceButton {
                text-align: left;
                padding-left: 12px;
            }
            QWidget#gamepadGameDetail QCheckBox {
                min-height: 28px;
                padding: 4px 6px;
            }
            QWidget#gamepadGameDetail QPushButton:focus,
            QWidget#gamepadGameDetail QPushButton[controllerSelected="true"] {
                border: 3px solid #bd8cff;
            }
            QWidget#gamepadGameDetail QLineEdit:focus,
            QWidget#gamepadGameDetail QComboBox:focus,
            QWidget#gamepadGameDetail QSpinBox:focus,
            QWidget#gamepadGameDetail QLineEdit[controllerSelected="true"],
            QWidget#gamepadGameDetail QComboBox[controllerSelected="true"],
            QWidget#gamepadGameDetail QSpinBox[controllerSelected="true"] {
                border: 3px solid #bd8cff;
                background: #332e39;
            }
            QWidget#gamepadGameDetail QCheckBox:focus,
            QWidget#gamepadGameDetail QCheckBox[controllerSelected="true"] {
                border: 2px solid #bd8cff;
                border-radius: 5px;
                background: #332e39;
            }
            QScrollArea#gamepadActionsScroll {
                border: none;
                background: transparent;
            }
            QListWidget#gamepadPrefixList {
                border: 1px solid #403c45;
                background: #1d1c20;
                outline: none;
                font-size: 17px;
            }
            QListWidget#gamepadPrefixList::item {
                min-height: 38px;
                padding: 10px 14px;
                border-radius: 6px;
            }
            QListWidget#gamepadPrefixList::item:selected {
                color: white;
                background: #514660;
                border: 2px solid #bd8cff;
            }
            QTabBar#gamepadDetailSections::tab {
                min-width: 125px;
                min-height: 40px;
                padding: 7px 18px;
                color: #d8d2dd;
                background: #211f24;
                border: 1px solid #403c45;
                border-bottom: 3px solid transparent;
            }
            QTabBar#gamepadDetailSections::tab:selected {
                color: white;
                border-bottom-color: #bd8cff;
                background: #332e39;
            }
            QLabel#gamepadHints {
                background: transparent;
                color: #aaa5ae;
                padding: 4px;
            }
        """)

        backend.action_pressed.connect(self._on_gamepad_action)

    def _on_mode_toggled(self, checked):
        if not checked:
            self.desktop_requested.emit()

    def activate(self):
        if self.sidebar.currentRow() < 0:
            self.sidebar.setCurrentRow(0)
        else:
            self.on_sidebar_change(self.sidebar.currentRow())
        widget = self.content_stack.currentWidget()
        focus_controller = getattr(widget, "focus_controller", None)
        if focus_controller:
            focus_controller()
        else:
            self.sidebar.setFocus(Qt.OtherFocusReason)

    def on_sidebar_change(self, index):
        if index < 0:
            return
        current_widget = self.content_stack.widget(index)
        if type(current_widget) is QWidget:
            new_tab = self._create_desktop_tab(index)
            if new_tab is not None:
                self.content_stack.removeWidget(current_widget)
                current_widget.deleteLater()
                self.content_stack.insertWidget(index, new_tab)
                current_widget = new_tab

        self.content_stack.setCurrentIndex(index)
        if hasattr(current_widget, "refresh_active_tab"):
            current_widget.refresh_active_tab()

    def _create_desktop_tab(self, index):
        # These pages deliberately remain the existing desktop implementations
        # until controller-specific versions are added.
        if index == 0:
            return GamepadGameTab(self.backend)
        if index == 1:
            from ui.prefix_tab import PrefixTab
            return PrefixTab()
        if index == 2:
            from ui.runner_tab import RunnerTab
            return RunnerTab()
        if index == 3:
            from ui.stats_tab import StatsTab
            return StatsTab(self.window().theme_manager)
        if index == 4:
            from ui.settings_tab import SettingsTab
            return SettingsTab(self.window().theme_manager)
        return None

    def _on_gamepad_action(self, action: str):
        if not self.isVisible():
            return
        if action in ("previous_tab", "next_tab"):
            offset = -1 if action == "previous_tab" else 1
            target = (self.sidebar.currentRow() + offset) % self.sidebar.count()
            self.sidebar.setCurrentRow(target)
            return

        current_widget = self.content_stack.currentWidget()
        handler = getattr(current_widget, "handle_gamepad_action", None)
        if handler:
            handler(action)
