from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox

class BoundedComboBox(QComboBox):
    """Keep long game lists within the window and show a vertical scrollbar."""

    def __init__(self, parent=None, max_height_ratio=0.7, theme_color_provider=None):
        super().__init__(parent)
        self.max_height_ratio = max_height_ratio
        self.theme_color_provider = theme_color_provider
        self.setStyleSheet("QComboBox { combobox-popup: 0; }")

    def showPopup(self):
        top_level = self.window()
        if top_level is not None and top_level.height() > 0:
            reference_height = top_level.height()
        else:
            screen = QApplication.primaryScreen()
            reference_height = screen.availableGeometry().height() if screen else 600

        max_popup_height = int(reference_height * self.max_height_ratio)
        self.setMaxVisibleItems(max(self.count(), 1))

        view = self.view()
        view.setMaximumHeight(max_popup_height)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        view.setStyleSheet("""
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        popup = view.parentWidget()
        if popup is not None:
            popup.setMaximumHeight(max_popup_height)

        super().showPopup()
