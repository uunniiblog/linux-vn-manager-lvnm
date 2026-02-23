from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

class GameListItem(QWidget):
    """Custom widget for the game list rows"""
    def __init__(self, game_card, zoom_factor=1.0, parent=None):
        super().__init__(parent)
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
        
        if game_card.coverpath:
            pix = QPixmap(game_card.coverpath)
            scaled = pix.scaled(
                cover_w,
                cover_h,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            # Crop to center so it fills the box without overflow
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

        # --- STEP 1: Add the gap you want HERE ---
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        # This spacing now ONLY controls the gap between the Name and the Sub-Group
        info_layout.setSpacing(int(20 * zoom_factor)) 

        # 1. The Big Name
        self.name_label = QLabel(game_card.name)
        name_font = self.name_label.font()
        name_font.setBold(True)
        name_font.setPointSizeF(11 * zoom_factor)
        self.name_label.setFont(name_font)
        info_layout.addWidget(self.name_label)

        # 2. Sub-Layout for Prefix and Path (The "Tight Group")
        sub_info_layout = QVBoxLayout()
        sub_info_layout.setSpacing(0) # Forces these two to touch
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

        # Add the tight group to the main info column
        info_layout.addLayout(sub_info_layout)

        # 3. The Stretch at the bottom
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

        date_wrapper.addStretch()        # Push from top
        date_wrapper.addWidget(self.date_label)
        date_wrapper.addStretch()        # Push from bottom — centers it
        layout.addLayout(date_wrapper)