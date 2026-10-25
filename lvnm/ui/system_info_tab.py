import logging
import config
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QFormLayout, QFrame, QGroupBox, QLabel, QScrollArea, QVBoxLayout, QWidget
from platform_profile import CURRENT_PLATFORM, Feature, PlatformProfile
from system_utils import SystemUtils
from ui.platform_ui import PlatformUi

logger = logging.getLogger(__name__)

class SystemInfoTab(QWidget):
    def __init__(self, platform: PlatformProfile = CURRENT_PLATFORM):
        super().__init__()
        self.platform_ui = PlatformUi(platform)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(self._build_sysinfo_group())
        layout.addStretch()
        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

        self._start_background_checks()

    def _build_sysinfo_group(self):
        sysinfo_group = QGroupBox(self.tr("System Info"))
        sysinfo_layout = QFormLayout(sysinfo_group)
        sysinfo_layout.setLabelAlignment(Qt.AlignLeft)

        runtime = SystemUtils.get_runtime_type()
        version_label = config.VERSION

        if runtime == "appimage":
            version_label += "  📦 AppImage"
        elif runtime == "flatpak":
            version_label += "  📦 Flatpak"
        elif runtime == "windows":
            version_label += "  Windows"
        else:
            version_label += "  (native)"

        self._sysinfo_values = {}
        self._add_value(sysinfo_layout, self.tr("LVNM Version:"), "app_version", version_label)
        self._add_value(sysinfo_layout, self.tr("OS:"), "os")
        self._add_value(sysinfo_layout, self.tr("Kernel:"), "kernel")
        self._add_value(sysinfo_layout, self.tr("Desktop:"), "desktop")
        self._add_value(sysinfo_layout, self.tr("CPU:"), "cpu")
        self._add_value(sysinfo_layout, self.tr("GPU:"), "gpu")
        self._add_value(sysinfo_layout, self.tr("Vulkan Support:"), "vulkan_support", requires=Feature.WINE_CONFIGURATION)
        self._add_value(sysinfo_layout, self.tr("Gamescope:"), "gamescope", requires=Feature.GAMESCOPE)
        self._add_value(sysinfo_layout, self.tr("linux-rt-upscaler:"), "upscale", requires=Feature.RT_UPSCALER)
        self._add_value(sysinfo_layout, self.tr("Umu-run:"), "umu_run", requires=Feature.WINE_CONFIGURATION)
        self._add_value(sysinfo_layout, self.tr("Winetricks:"), "winetricks", requires=Feature.WINE_CONFIGURATION)

        for pkg in SystemUtils.GSTREAMER_PACKAGES:
            self._add_value(sysinfo_layout, f"{pkg}:", f"gstreamer:{pkg}", requires=Feature.WINE_CONFIGURATION)

        return sysinfo_group

    def _add_value(self, form: QFormLayout, label: str, key: str, value: str = "…", requires: Feature | None = None):
        value_label = QLabel(value)
        if self.platform_ui.add_row(form, QLabel(label), value_label, requires=requires):
            self._sysinfo_values[key] = value_label

    def check(self, val):
        return "✅" if val else "❌"

    def check_with_version(self, installed: bool, version: str | None) -> str:
        mark = self.check(installed)
        if installed and version:
            return f"{mark}  (v{version})"
        return mark

    def _start_background_checks(self):
        self._system_info_worker = SystemInfoWorker()
        self._system_info_worker.results_ready.connect(self._on_system_info_ready)
        self._system_info_worker.start()

    def _on_system_info_ready(self, system_info, software_info):
        if not system_info and not software_info:
            for key, label in self._sysinfo_values.items():
                if key != "app_version":
                    label.setText("?")
            return

        system_values = {
            "os": system_info.get("os", "?"),
            "kernel": system_info.get("kernel", "?"),
            "desktop": (
                f'{system_info.get("desktop_environment", "?")} - '
                f'{system_info.get("session_type", "?")}'
            ),
            "cpu": system_info.get("cpu", "?"),
            "gpu": system_info.get("gpu", "?"),
        }
        for key, value in system_values.items():
            self._sysinfo_values[key].setText(str(value))

        software_values = {
            "vulkan_support": self.check(software_info.get("vulkan_support")),
            "gamescope": self.check_with_version(
                software_info.get("gamescope"), software_info.get("gamescope_version")
            ),
            "upscale": self.check_with_version(
                software_info.get("upscale"), software_info.get("upscale_version")
            ),
            "umu_run": self.check_with_version(
                software_info.get("umu_run"), software_info.get("umu_run_version")
            ),
            "winetricks": self.check_with_version(
                software_info.get("winetricks"), software_info.get("winetricks_version")
            ),
        }
        for key, value in software_values.items():
            if key in self._sysinfo_values:
                self._sysinfo_values[key].setText(value)

        gstreamer = software_info.get("gstreamer_packages", {})
        for pkg in SystemUtils.GSTREAMER_PACKAGES:
            key = f"gstreamer:{pkg}"
            if key in self._sysinfo_values:
                self._sysinfo_values[key].setText(self.check(gstreamer.get(pkg)))


class SystemInfoWorker(QThread):
    results_ready = Signal(dict, dict)

    def run(self):
        try:
            system_info = SystemUtils.get_system_info()
            software_info = SystemUtils.get_software_support()
            self.results_ready.emit(system_info, software_info)
        except Exception:
            logger.exception("Failed to load system information")
            self.results_ready.emit({}, {})
