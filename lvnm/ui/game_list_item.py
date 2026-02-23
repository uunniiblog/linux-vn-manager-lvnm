from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

class GameListItem(QWidget):
    """Custom widget for the game list rows"""
    def __init__(self, game_card, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Column 1: Cover Placeholder (Rectangular)
        self.cover = QLabel()
        self.cover.setFixedSize(60, 85)
        self.cover.setStyleSheet("background-color: #333; border-radius: 4px;")
        if game_card.coverpath:
            pix = QPixmap(game_card.coverpath)
            self.cover.setPixmap(pix.scaled(60, 85, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        layout.addWidget(self.cover)

        # Column 2: Name and Prefix
        info_layout = QVBoxLayout()
        self.name_label = QLabel(game_card.name)
        self.name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.prefix_label = QLabel(game_card.prefix)
        self.prefix_label.setStyleSheet("color: #888; font-size: 11px;")
        
        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.prefix_label)
        layout.addLayout(info_layout)
        layout.addStretch()

        # Column 3: Last Played
        last_played = game_card.last_played if game_card.last_played else self.tr("Never")
        self.date_label = QLabel(last_played)
        self.date_label.setStyleSheet("color: #aaa; font-style: italic;")
        layout.addWidget(self.date_label)