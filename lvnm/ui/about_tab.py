import config
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QScrollArea, QVBoxLayout, QWidget
from platform_profile import CURRENT_PLATFORM, Feature, PlatformProfile
from system_utils import SystemUtils
from ui.platform_ui import PlatformUi

class AboutTab(QWidget):
    def __init__(self, platform: PlatformProfile = CURRENT_PLATFORM):
        super().__init__()
        self.platform_ui = PlatformUi(platform)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(self._build_about_group())
        layout.addStretch()
        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

        self._update_check_worker = UpdateCheckWorker()
        self._update_check_worker.results_ready.connect(self._on_update_check_ready)
        self._update_check_worker.start()

    def _build_about_group(self):
        about_group = QGroupBox(self.tr("About"))
        about_layout = QFormLayout(about_group)
        about_layout.setLabelAlignment(Qt.AlignLeft)

        self.version_label_val = QLabel(config.VERSION)
        self.version_label_val.linkActivated.connect(SystemUtils.open_url)
        about_layout.addRow(QLabel(self.tr("LVNM version:")), self.version_label_val)

        github_label = QLabel(f'<a href="{config.GIT_URL}">{config.GIT_URL}</a>')
        github_label.linkActivated.connect(SystemUtils.open_url)
        about_layout.addRow(QLabel(self.tr("Github:")), github_label)

        github_wiki_label = QLabel(f'<a href="{config.GIT_WIKI_URL}">{config.GIT_WIKI_URL}</a>')
        github_wiki_label.linkActivated.connect(SystemUtils.open_url)
        about_layout.addRow(QLabel(self.tr("Github Wiki:")), github_wiki_label)

        wineprefixes_label = QLabel(f'<a href="{config.WINEPREFIX_URL}">{config.WINEPREFIX_URL}</a>')
        wineprefixes_label.linkActivated.connect(SystemUtils.open_url)
        self.platform_ui.add_row(about_layout, QLabel(self.tr("Wineprefixes guide:")), wineprefixes_label, requires=Feature.WINE_CONFIGURATION)
        return about_group

    def _on_update_check_ready(self, tag, url):
        if tag and url and tag.lstrip("v") != config.VERSION.lstrip("v"):
            self.version_label_val.setText(f'{config.VERSION} <a href="{url}">{self.tr("Newest version available:")} {tag}</a>')

class UpdateCheckWorker(QThread):
    results_ready = Signal(str, str)

    def run(self):
        tag, url = SystemUtils.get_latest_release_info()
        if tag and url:
            self.results_ready.emit(tag, url)
