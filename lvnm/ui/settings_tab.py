from PySide6.QtWidgets import (QWidget, QVBoxLayout, QComboBox, 
                               QLabel, QGroupBox, QFormLayout)
from system_utils import SystemUtils

class SettingsTab(QWidget):
    def __init__(self, theme_manager):
        super().__init__()
        self.theme_manager = theme_manager
        
        # Main layout for the entire tab
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20) # Add breathing room around the edges
        main_layout.setSpacing(20) # Space between the different sections
        
        # --- SECTION 1: Appearance ---
        appearance_group = QGroupBox(self.tr("Appearance"))
        appearance_layout = QFormLayout(appearance_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([self.tr("System Default"), self.tr("Light"), self.tr("Dark")])
        self.theme_combo.setFixedWidth(200) # Keep it from stretching across the whole screen
        
        # Sync combo with current setting
        current = self.theme_manager.get_theme_mode()
        mapping = {"auto": 0, "light": 1, "dark": 2}
        self.theme_combo.setCurrentIndex(mapping.get(current, 0))
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        
        # Add to form layout (Label on left, Combo on right)
        appearance_layout.addRow(QLabel(self.tr("Theme:")), self.theme_combo)
        
        main_layout.addWidget(appearance_group)

        # --- SECTION 2: System Info ---
        sysinfo_group = QGroupBox(self.tr("System Info"))
        sysinfo_layout = QFormLayout(sysinfo_group)
        
        # Fetch data
        sys_data = SystemUtils.get_system_info()
        software = SystemUtils.get_software_support()
        
        sysinfo_layout.addRow(QLabel(self.tr("LVNM Version:")), QLabel(sys_data.get('app_version')))
        sysinfo_layout.addRow(QLabel(self.tr("OS:")), QLabel(sys_data.get('os')))
        sysinfo_layout.addRow(QLabel(self.tr("Kernel:")), QLabel(sys_data.get('kernel')))
        sysinfo_layout.addRow(QLabel(self.tr("Desktop:")), QLabel(f"{sys_data.get('desktop_environment')} - {sys_data.get('session_type')}"))
        sysinfo_layout.addRow(QLabel(self.tr("CPU:")), QLabel(sys_data.get('cpu')))
        sysinfo_layout.addRow(QLabel(self.tr("GPU:")), QLabel(sys_data.get('gpu')))
        
        # Software Support (Fixed the TypeError by converting to string/icon)
        sysinfo_layout.addRow(QLabel(self.tr("Vulkan Support:")), QLabel(self.check(software.get('vulkan_support'))))
        sysinfo_layout.addRow(QLabel(self.tr("Gamescope:")), QLabel(self.check(software.get('gamescope'))))
        sysinfo_layout.addRow(QLabel(self.tr("Umu-run:")), QLabel(self.check(software.get('umu_run'))))
        sysinfo_layout.addRow(QLabel(self.tr("Winetricks:")), QLabel(self.check(software.get('winetricks'))))

        # GStreamer Section
        gst_packages = software.get('gstreamer_packages', {})
        for pkg, installed in gst_packages.items():
            sysinfo_layout.addRow(QLabel(f"  {pkg}:"), QLabel(self.check(installed)))
        
        main_layout.addWidget(sysinfo_group)
        
        main_layout.addStretch()

    def change_theme(self, index):
        mapping = {0: "auto", 1: "light", 2: "dark"}
        new_mode = mapping[index]
        
        # 1. Save to disk
        self.theme_manager.settings.setValue("theme_mode", new_mode)
        
        # 2. Tell manager to refresh the UI immediately
        self.theme_manager.update_theme()

    def check(self, val): 
        return "✅" if val else "❌"