from PySide6.QtWidgets import ( 
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
    QFrame, QMenu, QDialog, QPlainTextEdit, QPushButton, QApplication
)
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, Signal, QTimer
from game_manager import GameManager
from system_utils import SystemUtils
from ui.game_sidebar import GameSidebar
from game_runner import GameRunner

class GameListItem(QWidget):
    """Custom widget for the game list rows"""

    doubleClicked = Signal(object)
    requestOpen = Signal(object)
    requestRun = Signal(object)
    requestStop = Signal(object)
    requestRefresh = Signal(object)

    def __init__(self, game_card, zoom_factor=1.0, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.zoom = zoom_factor
        self.game_card = game_card
        self.selected = False
        self._hovered = False
        self.hover_bg = "rgba(255, 255, 255, 18)"   # default: dark-mode tint

        # Layouts 
        margin = int(5 * zoom_factor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(int(8 * zoom_factor))

        # Column 1: Cover
        self.cover_w = int(90 * zoom_factor)
        self.cover_h = self.cover_w * 3 // 2
        self.cover = QLabel()
        self.cover.setFixedSize(self.cover_w, self.cover_h)
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setObjectName("gameItemCover")
        layout.addWidget(self.cover)

        # Column 2: Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(int(20 * zoom_factor))

        self.name_label = QLabel()
        self.name_label.setObjectName("gameItemName")
        name_font = self.name_label.font()
        name_font.setBold(True)
        name_font.setPointSizeF(11 * zoom_factor)
        self.name_label.setFont(name_font)
        info_layout.addWidget(self.name_label)

        sub_info_layout = QVBoxLayout()
        sub_info_layout.setSpacing(0)

        self.prefix_label = QLabel()
        self.prefix_label.setObjectName("gameItemPrefix")

        self.path_label = QLabel()
        self.path_label.setObjectName("gameItemPath")
        self.path_label.setWordWrap(True)

        sub_info_layout.addWidget(self.prefix_label)
        sub_info_layout.addWidget(self.path_label)
        info_layout.addLayout(sub_info_layout)
        info_layout.addStretch(1)
        layout.addLayout(info_layout, stretch=1)

        # Column 3: Date
        self.date_label = QLabel()
        self.date_label.setObjectName("gameItemDate")
        self.date_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.date_label)

        # --- INITIAL DATA FILL ---
        self.update_ui(game_card)

    def enterEvent(self, event):
        if not self.selected:
            self._set_hover_state(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hover_state(False)
        super().leaveEvent(event)

    def _set_hover_state(self, is_hovered: bool):
        self._hovered = is_hovered
        # Set a dynamic property that the CSS can see
        self.setProperty("hovered", is_hovered)
        
        # This "re-polishes" the widget to force the CSS to update immediately
        self.style().unpolish(self)
        self.style().polish(self)

    def update_ui(self, game_card):
        """The 'Hot-Swap' method that updates only the data-driven parts."""
        self.game_card = game_card
        
        # Update Text
        display_name = game_card.name
        self.name_label.setText(display_name)
        self.prefix_label.setText(game_card.prefix)
        self.path_label.setText(game_card.path)
        
        last_played = game_card.last_played if game_card.last_played else self.tr("Never")
        self.date_label.setText(last_played)

        # Update Cover
        local_cover = SystemUtils.get_cover_path(game_card.vndb)
        if local_cover:
            pix = QPixmap(local_cover)
            if not pix.isNull():
                scaled = pix.scaled(
                    self.cover_w, self.cover_h,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation
                )
                x = (scaled.width() - self.cover_w) // 2
                y = (scaled.height() - self.cover_h) // 2
                self.cover.setPixmap(scaled.copy(x, y, self.cover_w, self.cover_h))
        else:
            self.cover.clear()

    def mouseDoubleClickEvent(self, event):
        """ catches the double-click anywhere on the row """
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.game_card)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        """Creates and shows the right-click menu"""
        menu = QMenu(self)
        
        is_running = self.game_card.name in GameSidebar.active_runners
        if is_running:
            act_run_stop = menu.addAction(self.tr("Stop Game"))
        else:
            act_run_stop = menu.addAction(self.tr("Run Game"))

        act_log = menu.addAction(self.tr("Show Logs"))
        act_open = menu.addAction(self.tr("Open Sidebar"))
        act_browse = menu.addAction(self.tr("Browse Files"))
        menu.addSeparator()
        act_regedit = menu.addAction(self.tr("Open Regedit"))
        act_winecfg = menu.addAction(self.tr("Open Winecfg"))
        act_cmd = menu.addAction(self.tr("Open windows cmd"))
        act_bash = menu.addAction(self.tr("Open Bash Terminal"))
        menu.addSeparator()
        act_shortcut = menu.addAction(self.tr("Desktop Shortcut"))
        act_steam = menu.addAction(self.tr("Steam Shortcut"))
        menu.addSeparator()
        act_refresh = menu.addAction(self.tr("Refresh List"))
        act_dup = menu.addAction(self.tr("Duplicate"))
        act_del = menu.addAction(self.tr("Delete"))

        action = menu.exec(event.globalPos())

        if action == act_run_stop:
            if is_running:
                self.requestStop.emit(self.game_card)
            else:
                self.requestRun.emit(self.game_card)
        
        elif action == act_log:
            self.show_log(self.game_card.name)

        elif action == act_open:
            self.requestOpen.emit(self.game_card)

        elif action == act_browse:
            self.browse_game(self.game_card.path)

        elif action == act_regedit:
            self.run_in_prefix("regedit")

        elif action == act_winecfg:
            self.run_in_prefix("winecfg")

        elif action == act_cmd:
            self.run_in_prefix("wineconsole")

        elif action == act_bash:
            self.run_bash()
            
        elif action == act_dup:
            self.duplicate_game(self.game_card.name)

        elif action == act_refresh:
            self.requestRefresh.emit(self.game_card)
            
        elif action == act_del:
            self.delete_game(self.game_card.name)

        elif action == act_shortcut:
            self.shortcut()

        elif action == act_steam:
            SystemUtils.add_to_steam(self.game_card)

    def show_log(self, name):
        self.log_dialog = LogViewerDialog(name)       
        self.log_dialog.show()
        self.log_dialog.raise_()
        self.log_dialog.activateWindow()

    def duplicate_game(self, name):
        if GameManager.duplicate_game(name):
            self.requestRefresh.emit(self.game_card)

    def delete_game(self, name):
        if GameManager.delete_game(name):
            self.requestRefresh.emit(self.game_card)

    def browse_game(self, path):
        SystemUtils.browse_files(path)

    def run_in_prefix(self, command: str):
        runner = GameRunner("UtilityMode")
        runner.run_in_prefix(command, self.game_card.prefix)

    def run_bash(self):
        runner = GameRunner("UtilityMode")
        runner.open_terminal(self.game_card.prefix)

    def shortcut(self):
        SystemUtils.create_desktop_shortcut(self.game_card.name, self.game_card.vndb)


class LogViewerDialog(QDialog):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr(f"Execution Logs: {name}"))
        self.resize(800, 600)
        self.setModal(False)
        self.runner = None
        self.name = name
        self.history_buffer = ""
        
        layout = QVBoxLayout(self)
        
        self.text_area = QPlainTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setLineWrapMode(QPlainTextEdit.NoWrap)
        
        # Terminal styling
        self.text_area.setStyleSheet("""
            background-color: #1e1e1e; 
            color: #d4d4d4; 
            font-family: 'Monospace', 'Courier New';
        """)
        
        layout.addWidget(self.text_area)

        # Timer for live updates
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_logs)
        self.timer.start(1000)
        
        # Initial fill
        self.update_logs()

    def update_logs(self):
        new_runner = GameSidebar.runners.get(self.name)

        # Detect game restarts
        if new_runner and new_runner != self.runner:
            self.history_buffer += self.text_area.toPlainText() 
            self.history_buffer += "\n\n\n--- New Instance Started --- \n\n\n"
            
            # Switch to the new runner
            self.runner = new_runner

        if not self.runner:
            return
            
        # Get the logs
        active_logs = self.runner.get_full_log()
        full_display_content = self.history_buffer + active_logs
        
        # Update
        if getattr(self, "_last_rendered", "") != full_display_content:
            scrollbar = self.text_area.verticalScrollBar()
            at_bottom = scrollbar.value() == scrollbar.maximum()
            self.text_area.setPlainText(full_display_content)
            self._last_rendered = full_display_content
            
            if at_bottom:
                scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        self.timer.stop()
        event.accept()