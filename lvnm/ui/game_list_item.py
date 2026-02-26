from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QMenu
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, Signal
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
        self.zoom = zoom_factor
        self.game_card = game_card

        # Layouts 
        margin = int(5 * zoom_factor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(int(8 * zoom_factor))

        # Column 1: Cover Placeholder
        self.cover_w = int(90 * zoom_factor)
        self.cover_h = self.cover_w * 3 // 2
        self.cover = QLabel()
        self.cover.setFixedSize(self.cover_w, self.cover_h)
        self.cover.setAlignment(Qt.AlignCenter) 
        self.cover.setStyleSheet("background-color: #333; border-radius: 4px; border: 1px solid #444;")
        layout.addWidget(self.cover)

        # Column 2: Info Labels
        info_layout = QVBoxLayout()
        info_layout.setSpacing(int(20 * zoom_factor)) 

        self.name_label = QLabel() # Empty for now
        name_font = self.name_label.font()
        name_font.setBold(True)
        name_font.setPointSizeF(11 * zoom_factor)
        self.name_label.setFont(name_font)
        info_layout.addWidget(self.name_label)

        sub_info_layout = QVBoxLayout()
        sub_info_layout.setSpacing(0)
        
        self.prefix_label = QLabel()
        self.prefix_label.setStyleSheet("color: #888;")
        self.path_label = QLabel()
        self.path_label.setStyleSheet("color: #666;")
        self.path_label.setWordWrap(True)
        
        sub_info_layout.addWidget(self.prefix_label)
        sub_info_layout.addWidget(self.path_label)
        info_layout.addLayout(sub_info_layout)
        info_layout.addStretch(1)
        layout.addLayout(info_layout, stretch=1)

        # Column 3: Date
        self.date_label = QLabel()
        self.date_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.date_label)

        # --- INITIAL DATA FILL ---
        self.update_ui(game_card)

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

        act_open = menu.addAction(self.tr("Open Sidebar"))
        act_browse = menu.addAction(self.tr("Browse Files"))
        act_regedit = menu.addAction(self.tr("Open Regedit"))
        act_winecfg = menu.addAction(self.tr("Open Winecfg"))
        act_cmd = menu.addAction(self.tr("Open windows cmd"))
        act_bash = menu.addAction(self.tr("Open Bash Terminal"))
        act_dup = menu.addAction(self.tr("Duplicate"))
        menu.addSeparator()
        act_del = menu.addAction(self.tr("Delete"))

        action = menu.exec(event.globalPos())

        if action == act_run_stop:
            if is_running:
                self.requestStop.emit(self.game_card)
            else:
                self.requestRun.emit(self.game_card)
        
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
            
        elif action == act_del:
            self.delete_game(self.game_card.name)

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
