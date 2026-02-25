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
        self.game_card = game_card

        margin = int(5 * zoom_factor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(int(8 * zoom_factor))

        # Column 1: Cover Placeholder (Rectangular)
        cover_w = int(90 * zoom_factor)
        cover_h = cover_w * 3 // 2  # 2:3 ratio
        self.cover = QLabel()
        # Ensure the label doesn't expand horizontally and break the "vertical" look
        self.cover.setFixedSize(cover_w, cover_h)
        self.cover.setAlignment(Qt.AlignCenter) 
        self.cover.setStyleSheet("""
            background-color: #333; 
            border-radius: 4px;
            border: 1px solid #444;
        """)
        
        # Check for local cover based on VNDB ID
        local_cover = SystemUtils.get_cover_path(game_card.vndb)
        
        display_path = local_cover

        if display_path:
            pix = QPixmap(display_path)
            if not pix.isNull():
                scaled = pix.scaled(
                    cover_w,
                    cover_h,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation
                )
                # Crop logic to ensure it fits the vertical container perfectly
                x = (scaled.width() - cover_w) // 2
                y = (scaled.height() - cover_h) // 2
                cropped = scaled.copy(x, y, cover_w, cover_h)
                self.cover.setPixmap(cropped)
        
        layout.addWidget(self.cover)

        # Column 2: Name, Prefix, Path
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(0)  # Prefix and Path will have 0 gap

        self.name_label = QLabel(game_card.name)
        name_font = self.name_label.font()
        name_font.setBold(True)
        name_font.setPointSizeF(11 * zoom_factor)
        self.name_label.setFont(name_font)
        info_layout.addWidget(self.name_label)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        # This spacing controls the gap between the Name and the Sub-Group
        info_layout.setSpacing(int(20 * zoom_factor)) 

        # The Big Name
        self.name_label = QLabel(game_card.name)
        name_font = self.name_label.font()
        name_font.setBold(True)
        name_font.setPointSizeF(11 * zoom_factor)
        self.name_label.setFont(name_font)
        info_layout.addWidget(self.name_label)

        # Sub-Layout for Prefix and Path
        sub_info_layout = QVBoxLayout()
        sub_info_layout.setSpacing(0)
        sub_info_layout.setContentsMargins(0, 0, 0, 0)

        self.prefix_label = QLabel(game_card.prefix)
        prefix_font = self.prefix_label.font()
        prefix_font.setPointSizeF(9 * zoom_factor)
        self.prefix_label.setFont(prefix_font)
        self.prefix_label.setStyleSheet("color: #888;")
        
        self.path_label = QLabel(game_card.path)
        self.path_label.setWordWrap(True)
        path_font = self.path_label.font()
        path_font.setPointSizeF(9 * zoom_factor)
        self.path_label.setFont(path_font)
        self.path_label.setStyleSheet("color: #666;")

        sub_info_layout.addWidget(self.prefix_label)
        sub_info_layout.addWidget(self.path_label)

        info_layout.addLayout(sub_info_layout)

        # The Stretch at the bottom
        # This keeps the whole block pushed to the top of the list item
        info_layout.addStretch(1)
        layout.addLayout(info_layout, stretch=1)

        # Column 3: Last Played
        date_wrapper = QVBoxLayout()
        date_wrapper.setContentsMargins(0, 0, 0, 0)
        last_played = game_card.last_played if game_card.last_played else self.tr("Never")
        self.date_label = QLabel(last_played)
        date_font = self.date_label.font()
        date_font.setPointSizeF(9 * zoom_factor)
        date_font.setItalic(True)
        self.date_label.setFont(date_font)
        self.date_label.setStyleSheet("color: #aaa;")
        self.date_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        date_wrapper.addStretch()
        date_wrapper.addWidget(self.date_label)
        date_wrapper.addStretch()
        layout.addLayout(date_wrapper)

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
        act_cmd = menu.addAction(self.tr("Open wineconsole"))
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
        print(f"run_in_prefix {command} {self.game_card.prefix}")
        runner = GameRunner("UtilityMode")
        runner.run_in_prefix(command, self.game_card.prefix)
