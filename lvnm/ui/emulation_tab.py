import config
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget
)
from pc98_manager import Pc98Manager
from platform_profile import IS_WINDOWS
from system_utils import SystemUtils
from ui.settings_page import SettingsPage

class EmulationTab(SettingsPage):
    def __init__(self):
        super().__init__()

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        note = QLabel(self.tr("Once an emulator is enabled a new virtual prefix with the platform name will be added to the sidebar."))
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(note)
        layout.addWidget(self._build_emulation_group())
        layout.addStretch()

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

    def _build_emulation_group(self):
        emulation_group = QGroupBox(self.tr("Emulation"))
        emulation_layout = QFormLayout(emulation_group)
        emulation_layout.setLabelAlignment(Qt.AlignLeft)

        # Retrieve current settings
        emulation_settings = self.user_settings.get(config.USER_CONF_EMULATION, {})

        linux_path_placeholders = [
            self.tr("/path/to/duckstation.AppImage or duckstation-qt"),
            self.tr("/path/to/pcsx2.AppImage or pcsx2-qt"),
            self.tr("/path/to/rpcs3.AppImage or rpcs3"),
            self.tr("/path/to/emulator.AppImage or process"),
            self.tr("/path/to/emulator.AppImage or process"),
        ]
        windows_path_placeholders = [
            self.tr("C:\\path\\to\\duckstation-qt.exe"),
            self.tr("C:\\path\\to\\pcsx2-qt.exe"),
            self.tr("C:\\path\\to\\rpcs3.exe"),
            self.tr("C:\\path\\to\\emulator.exe"),
            self.tr("C:\\path\\to\\emulator.exe"),
        ]
        path_placeholders = windows_path_placeholders if IS_WINDOWS else linux_path_placeholders
        emulator_definitions = [
            (
                self.tr("PSX"),
                config.USER_CONF_EMULATION_PSX_PATH,
                config.USER_CONF_EMULATION_PSX_CONFIG,
                path_placeholders[0],
            ),
            (
                self.tr("PS2"),
                config.USER_CONF_EMULATION_PS2_PATH,
                config.USER_CONF_EMULATION_PS2_CONFIG,
                path_placeholders[1],
            ),
            (
                self.tr("PS3"),
                config.USER_CONF_EMULATION_PS3_PATH,
                config.USER_CONF_EMULATION_PS3_CONFIG,
                path_placeholders[2],
            ),
            (
                self.tr("PSP"),
                config.USER_CONF_EMULATION_PSP_PATH,
                config.USER_CONF_EMULATION_PSP_CONFIG,
                path_placeholders[3],
            ),
            (
                self.tr("Switch"),
                config.USER_CONF_EMULATION_SWITCH_PATH,
                config.USER_CONF_EMULATION_SWITCH_CONFIG,
                path_placeholders[4],
            ),
        ]

        self.emulation_widgets = {}

        for i, (display_name, path_key, cli_key, path_placeholder) in enumerate(emulator_definitions):
            # if i > 0:
            #     divider = QFrame()
            #     divider.setFrameShape(QFrame.HLine)
            #     divider.setFrameShadow(QFrame.Sunken)
            #     emulation_layout.addRow(divider)

            emulation_layout.addRow(QLabel(f"<b>{display_name}</b>"))

            # Path or Command
            path_row = QHBoxLayout()
            path_edit = QLineEdit(emulation_settings.get(path_key, ""))
            path_edit.setPlaceholderText(path_placeholder)
            browse_btn = QPushButton(self.tr("Browse..."))
            path_row.addWidget(path_edit)
            path_row.addWidget(browse_btn)
            emulation_layout.addRow(QLabel(self.tr("Path or Command:")), path_row)

            # CLI / config parameters
            config_edit = QLineEdit(emulation_settings.get(cli_key, ""))
            config_edit.setPlaceholderText(self.tr("-fullscreen -batch"))
            emulation_layout.addRow(QLabel(self.tr("Config:")), config_edit)

            browse_btn.clicked.connect(lambda _checked=False, e=path_edit: self.browse_emulator_path(e))
            self._bind_text_setting(path_edit, path_key, parent_key=config.USER_CONF_EMULATION)
            self._bind_text_setting(config_edit, cli_key, parent_key=config.USER_CONF_EMULATION)

            self.emulation_widgets[path_key] = path_edit
            self.emulation_widgets[cli_key] = config_edit

        emulation_layout.addRow(QLabel(f"<b>{self.tr('PC-98 (NP2kai)')}</b>"))
        pc98_note = QLabel(self.tr(
            "The flatpak build includes a small RetroArch frontend, NP2kai core, and a freely distributable japanese font. "
            "For the better compatatibility include your own bios and font files in the configured folder below. "
            "Multi disk games can use an UTF-8 .m3u playlist. "
            "Press F12 for NP2kai's menu. Press F1 for retroarch menu."
        ))
        pc98_note.setWordWrap(True)
        pc98_note.setStyleSheet("color: #888; font-style: italic;")
        emulation_layout.addRow(pc98_note)

        is_flatpak = SystemUtils.get_runtime_type() == "flatpak"
        use_bundled = QCheckBox(self.tr("Use the flatpak bundled RetroArch and NP2kai core"))
        use_bundled.setChecked(is_flatpak and emulation_settings.get(config.USER_CONF_EMULATION_PC98_USE_BUNDLED, False))
        use_bundled.setEnabled(is_flatpak)
        emulation_layout.addRow(use_bundled)

        pc98_path_row = QHBoxLayout()
        pc98_path_edit = QLineEdit(emulation_settings.get(config.USER_CONF_EMULATION_PC98_PATH, ""))
        pc98_path_edit.setPlaceholderText(self.tr("C:\\path\\to\\retroarch.exe") if IS_WINDOWS else self.tr("/path/to/retroarch or retroarch"))
        pc98_path_btn = QPushButton(self.tr("Browse..."))
        pc98_path_row.addWidget(pc98_path_edit)
        pc98_path_row.addWidget(pc98_path_btn)
        pc98_path_label = QLabel(self.tr("Custom RetroArch:"))
        emulation_layout.addRow(pc98_path_label, pc98_path_row)

        pc98_core_row = QHBoxLayout()
        pc98_core_edit = QLineEdit(emulation_settings.get(config.USER_CONF_EMULATION_PC98_CORE_PATH, ""))
        pc98_core_edit.setPlaceholderText(self.tr("C:\\path\\to\\np2kai_libretro.dll") if IS_WINDOWS else self.tr("/path/to/np2kai_libretro.so"))
        pc98_core_btn = QPushButton(self.tr("Browse..."))
        pc98_core_row.addWidget(pc98_core_edit)
        pc98_core_row.addWidget(pc98_core_btn)
        pc98_core_label = QLabel(self.tr("Custom NP2kai core:"))
        emulation_layout.addRow(pc98_core_label, pc98_core_row)

        default_system_path = Pc98Manager.get_managed_system_path_default()
        pc98_system_row = QHBoxLayout()
        pc98_system_path = QLineEdit(emulation_settings.get(config.USER_CONF_EMULATION_PC98_SYSTEM_PATH, default_system_path))
        pc98_system_path.setPlaceholderText(self.tr("Select the folder containing NP2kai BIOS/font files"))
        pc98_system_btn = QPushButton(self.tr("Browse..."))
        pc98_system_row.addWidget(pc98_system_path)
        pc98_system_row.addWidget(pc98_system_btn)
        emulation_layout.addRow(QLabel(self.tr("BIOS/font system folder:")), pc98_system_row)

        pc98_config_edit = QLineEdit(emulation_settings.get(config.USER_CONF_EMULATION_PC98_CONFIG, ""))
        pc98_config_edit.setPlaceholderText(self.tr("Optional extra RetroArch arguments"))
        emulation_layout.addRow(QLabel(self.tr("Extra arguments:")), pc98_config_edit)

        def update_pc98_custom_state(checked):
            for widget in (pc98_path_label, pc98_path_edit, pc98_path_btn, pc98_core_label, pc98_core_edit, pc98_core_btn):
                widget.setEnabled(not checked)

        update_pc98_custom_state(use_bundled.isChecked())
        use_bundled.toggled.connect(update_pc98_custom_state)
        use_bundled.toggled.connect(lambda checked: self.save_nested_setting(config.USER_CONF_EMULATION, config.USER_CONF_EMULATION_PC98_USE_BUNDLED, checked))
        pc98_path_btn.clicked.connect(lambda: self.browse_emulator_path(pc98_path_edit))
        pc98_core_btn.clicked.connect(lambda: self.browse_pc98_core_path(pc98_core_edit))
        pc98_system_btn.clicked.connect(lambda: self.browse_pc98_system_folder(pc98_system_path))
        self._bind_text_setting(pc98_path_edit, config.USER_CONF_EMULATION_PC98_PATH, parent_key=config.USER_CONF_EMULATION)
        self._bind_text_setting(pc98_core_edit, config.USER_CONF_EMULATION_PC98_CORE_PATH, parent_key=config.USER_CONF_EMULATION)
        self._bind_text_setting(pc98_system_path, config.USER_CONF_EMULATION_PC98_SYSTEM_PATH, parent_key=config.USER_CONF_EMULATION)
        self._bind_text_setting(pc98_config_edit, config.USER_CONF_EMULATION_PC98_CONFIG, parent_key=config.USER_CONF_EMULATION)
        self.emulation_widgets[config.USER_CONF_EMULATION_PC98_PATH] = pc98_path_edit
        self.emulation_widgets[config.USER_CONF_EMULATION_PC98_CORE_PATH] = pc98_core_edit
        self.emulation_widgets[config.USER_CONF_EMULATION_PC98_SYSTEM_PATH] = pc98_system_path
        self.emulation_widgets[config.USER_CONF_EMULATION_PC98_CONFIG] = pc98_config_edit

        return emulation_group

    def browse_emulator_path(self, target_edit):
        name_filter = self.tr("Executables (*.exe);;All Files (*)") if IS_WINDOWS else self.tr("Executables (*.AppImage);;All Files (*)")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Select Emulator Executable"),
            "",
            name_filter
        )
        if file_path:
            target_edit.setText(file_path)
            self.flush_pending_text_settings()

    def browse_pc98_core_path(self, target_edit):
        name_filter = self.tr("Libretro cores (*.dll);;All Files (*)") if IS_WINDOWS else self.tr("Libretro cores (*.so);;All Files (*)")
        file_path, _ = QFileDialog.getOpenFileName(self, self.tr("Select NP2kai Core"), "", name_filter)
        if file_path:
            target_edit.setText(file_path)
            self.flush_pending_text_settings()

    def browse_pc98_system_folder(self, target_edit):
        current_path = target_edit.text().strip()
        folder = QFileDialog.getExistingDirectory(self, self.tr("Select PC-98 BIOS/font Folder"), current_path)
        if folder:
            target_edit.setText(folder)
            self.flush_pending_text_settings()
