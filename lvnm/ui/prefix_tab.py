from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

class PrefixTab(QWidget):
    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(QLabel(self.tr("Prefix View - TODO")))
        main_layout.addStretch()