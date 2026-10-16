import config
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLineEdit, QLabel, QPushButton, QFileDialog,
    QCheckBox, QGroupBox, QScrollArea, QWidget,
    QComboBox, QMessageBox
)
from PySide6.QtCore import Qt, QSettings
from system_utils import SystemUtils
from prefix_manager import PrefixManager
from regedit_management import RegeditManager
from ui.console_dialog import ConsoleDialog
from platform_profile import CURRENT_PLATFORM, Feature, PlatformProfile
from ui.platform_ui import PlatformUi

logger = logging.getLogger(__name__)

class AdvancedSettingsDialog(QDialog):
    SETTINGS_FILE = config.UI_SETTINGS

    def __init__(self, prefix_type, current_game, parent=None, platform: PlatformProfile = CURRENT_PLATFORM):
        super().__init__(parent)
        self.platform = platform
        self.platform_ui = PlatformUi(platform)
        self.prefix_type = prefix_type
        self.setWindowTitle(self.tr("Advanced Settings {}").format(current_game.name))
        self.setMinimumWidth(450)
        self.resize(550, 600)

        # Load Stored UI settings
        self.settings = QSettings(str(self.SETTINGS_FILE), QSettings.IniFormat)

        self.current_game = current_game

        # Main layout
        self.main_outer_layout = QVBoxLayout(self)
        self.main_scroll = QScrollArea()
        self.main_scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)

        # UMU Fields
        self.edit_umu_store = QLineEdit(getattr(self.current_game, "umu_store", ""))
        self.edit_umu_id = QLineEdit(getattr(self.current_game, "umu_gameid", ""))
        
        self.label_umu_store = QLabel(self.tr("UMU Store:"))
        self.label_umu_id = QLabel(self.tr("UMU ID:"))

        # Proton Visibility Logic
        is_proton = (prefix_type == "proton")
        self.edit_umu_store.setVisible(is_proton)
        self.edit_umu_id.setVisible(is_proton)
        self.label_umu_store.setVisible(is_proton)
        self.label_umu_id.setVisible(is_proton)

        form.addRow(self.label_umu_store, self.edit_umu_store)
        form.addRow(self.label_umu_id, self.edit_umu_id)

        # Pre-launch Arguments
        self.edit_pre_args = QLineEdit(getattr(self.current_game, "pre_launch_args", ""))
        form.addRow(self.tr("Pre-Launch Command:"), self.edit_pre_args)

        # Arguments
        self.edit_arguments = QLineEdit(getattr(self.current_game, "arguments", ""))
        form.addRow(self.tr("Game Arguments:"), self.edit_arguments)

        self.pc98_combos = {}
        if prefix_type == config.EMULATION_PC98:
            pc98_group = QGroupBox(self.tr("PC-98 compatibility overrides"))
            pc98_layout = QFormLayout(pc98_group)
            pc98_definitions = [
                ("model", self.tr("Machine model:"), ["PC-9801VX", "PC-286", "PC-9801VM"]),
                ("base_clock", self.tr("CPU base clock:"), ["2.4576 MHz", "1.9968 MHz"]),
                ("cpu_multiplier", self.tr("CPU clock multiplier:"), ["4", "5", "6", "8", "10", "12", "16", "20", "24", "30", "36", "40", "42"]),
                ("ram_size", self.tr("RAM size (MB):"), ["1", "3", "7", "11", "13", "16", "32", "64", "120", "230"]),
                ("sound_board", self.tr("Sound board:"), ["PC9801-86", "PC9801-26K + 86", "PC9801-26K", "None"]),
                ("gdc", self.tr("GDC:"), ["uPD7220", "uPD72020"]),
            ]
            for field_name, label, values in pc98_definitions:
                combo = QComboBox()
                combo.addItem(self.tr("Core default"), "")
                for value in values:
                    combo.addItem(value, value)
                current_value = getattr(self.current_game.pc98, field_name, "")
                current_index = combo.findData(current_value)
                combo.setCurrentIndex(max(current_index, 0))
                pc98_layout.addRow(label, combo)
                self.pc98_combos[field_name] = combo
            pc98_note = QLabel(self.tr(
                "Leave these at Core default unless a game needs a specific PC-98 model, clock, memory, sound board, or graphics controller."
            ))
            pc98_note.setWordWrap(True)
            pc98_layout.addRow(pc98_note)
            self.scroll_layout.addWidget(pc98_group)

        # Pre-launch Script
        self.edit_pre_script = QLineEdit(getattr(self.current_game, "pre_launch_script", ""))
        self.btn_pre_script = QPushButton("...")
        self.btn_pre_script.clicked.connect(lambda: self.browse_file(self.edit_pre_script))

        pre_script_layout = QHBoxLayout()
        pre_script_layout.addWidget(self.edit_pre_script)
        pre_script_layout.addWidget(self.btn_pre_script)
        form.addRow(self.tr("Pre-Launch Script:"), pre_script_layout)
 
        # Pre-launch Script Wait
        self.chk_pre_script_wait = QCheckBox(self.tr("Wait for game to open before executing script"))
        self.chk_pre_script_wait.setChecked(getattr(self.current_game, "pre_launch_script_wait", False))
        form.addRow("", self.chk_pre_script_wait)

        # Exit Script
        self.edit_exit_script = QLineEdit(getattr(self.current_game, "exit_script", ""))
        self.btn_exit_script = QPushButton("...")
        self.btn_exit_script.clicked.connect(lambda: self.browse_file(self.edit_exit_script))
        
        exit_script_layout = QHBoxLayout()
        exit_script_layout.addWidget(self.edit_exit_script)
        exit_script_layout.addWidget(self.btn_exit_script)
        form.addRow(self.tr("Exit Script:"), exit_script_layout)

        # Registry Keys (Wine/Proton only)
        self.label_registry_path = QLabel(self.tr("Registry Path:"))
        self.edit_registry_path = QLineEdit(getattr(self.current_game, "registry_path", ""))
        self.edit_registry_path.setPlaceholderText(r"HKLM\Software\Key\Rewrite_PLUS")
        self.btn_detect_registry = QPushButton(self.tr("Auto-detect"))
        self.btn_detect_registry.clicked.connect(self._auto_detect_registry_path)
        self.btn_copy_registry = QPushButton(self.tr("Copy to..."))
        self.btn_copy_registry.clicked.connect(self._open_copy_registry_dialog)

        registry_layout = QHBoxLayout()
        registry_layout.addWidget(self.edit_registry_path)
        registry_layout.addWidget(self.btn_detect_registry)
        registry_layout.addWidget(self.btn_copy_registry)
        if prefix_type in ("wine", "proton"):
            self.platform_ui.add_row(form, self.label_registry_path, registry_layout, requires=Feature.REGISTRY_MANAGEMENT)

        # Per-game network isolation
        network_isolation_available = (
            SystemUtils.get_runtime_type() == "flatpak"
            or SystemUtils.get_firejail_path() is not None
        )
        network_help_text = self.tr(
            "Prevents this game from accessing the network. Requires the Flatpak "
            "build of LVNM or Firejail installed on the system."
        )
        self.label_disable_network = QLabel(self.tr("Disable Network:"))
        self.chk_disable_network = QCheckBox()
        self.chk_disable_network.setEnabled(network_isolation_available)
        self.chk_disable_network.setChecked(
            network_isolation_available
            and getattr(self.current_game, "disable_network", False)
        )
        self.lbl_disable_network_help = QLabel(network_help_text)
        self.lbl_disable_network_help.setWordWrap(True)
        network_option_layout = QHBoxLayout()
        network_option_layout.addWidget(self.chk_disable_network)
        network_option_layout.addWidget(self.lbl_disable_network_help, 1)
        if prefix_type in ("wine", "proton"):
            self.platform_ui.add_row(form, self.label_disable_network, network_option_layout, requires=Feature.NETWORK_ISOLATION)

        self.scroll_layout.addLayout(form)

        self.main_scroll.setWidget(self.scroll_content)
        self.main_outer_layout.addWidget(self.main_scroll)

        # Save / Cancel Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton(self.tr("Save"))
        save_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        save_btn.setAutoDefault(False)
        save_btn.setDefault(False)

        cancel_btn = QPushButton(self.tr("Cancel"))
        cancel_btn.setAutoDefault(False)
        
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        self.main_outer_layout.addLayout(btn_layout)

        # Restore previous window size
        self._restore_state()

    def browse_file(self, target_line_edit):
        """Opens file system to select a script."""
        if self.platform.name == "windows":
            file_filter = self.tr("Windows Scripts (*.cmd *.bat *.ps1 *.exe);;All Files (*)")
        else:
            file_filter = self.tr("All Files (*);;Shell Scripts (*.sh)")
        path, _ = QFileDialog.getOpenFileName(
            self, 
            self.tr("Select Script File"),
            "",
            file_filter,
        )
        if path:
            target_line_edit.setText(path)

    def accept(self):
        """Save advanced settings to the in-memory game card."""
        self.current_game.umu_store = self.edit_umu_store.text()
        self.current_game.umu_gameid = self.edit_umu_id.text()
        self.current_game.pre_launch_args = self.edit_pre_args.text()
        if self.platform.supports(Feature.NETWORK_ISOLATION):
            self.current_game.disable_network = self.chk_disable_network.isChecked()
        self.current_game.arguments = self.edit_arguments.text()
        for field_name, combo in self.pc98_combos.items():
            setattr(self.current_game.pc98, field_name, combo.currentData())
        self.current_game.pre_launch_script = self.edit_pre_script.text()
        self.current_game.pre_launch_script_wait = self.chk_pre_script_wait.isChecked()
        self.current_game.exit_script = self.edit_exit_script.text()
        if self.platform.supports(Feature.REGISTRY_MANAGEMENT):
            self.current_game.registry_path = self.edit_registry_path.text().strip()
        super().accept()

    def _auto_detect_registry_path(self):
        try:
            candidates = RegeditManager.find_registry_keys(self.current_game)
        except Exception as exc:
            logger.exception("Registry auto-detection failed")
            QMessageBox.critical(self, self.tr("Registry Detection Failed"), str(exc))
            return

        if not candidates:
            QMessageBox.information(
                self,
                self.tr("Registry Key Not Found"),
                self.tr("No likely registry key was found. You can enter one manually."),
            )
            return

        self.edit_registry_path.setText(candidates[0])
        if len(candidates) > 1:
            self.edit_registry_path.setToolTip(
                self.tr("Other possible keys:\n{0}").format(
                    "\n".join(candidates[1:6])
                )
            )

    def _open_copy_registry_dialog(self):
        registry_path = self.edit_registry_path.text().strip()
        if not registry_path:
            QMessageBox.warning(
                self,
                self.tr("Registry Path Required"),
                self.tr("Enter or auto-detect a registry path first."),
            )
            return

        prefixes = {
            name: data
            for name, data in PrefixManager.get_prefix_json().items()
            if name != self.current_game.prefix and data.get("type") in ("wine", "proton")
        }
        if not prefixes:
            QMessageBox.information(
                self,
                self.tr("No Target Prefix"),
                self.tr("There are no other Wine or Proton prefixes available."),
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Copy Registry Data to Prefix"))
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(self.tr("Target prefix:")))
        combo = QComboBox()
        combo.addItems(sorted(prefixes))
        layout.addWidget(combo)
        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_button = QPushButton(self.tr("Cancel"))
        ok_button = QPushButton(self.tr("OK"))
        cancel_button.clicked.connect(dialog.reject)
        ok_button.clicked.connect(dialog.accept)
        button_row.addWidget(cancel_button)
        button_row.addWidget(ok_button)
        layout.addLayout(button_row)

        if dialog.exec() != QDialog.Accepted:
            return

        console = ConsoleDialog(self)
        console.setWindowTitle(self.tr("Copying Registry Data"))

        cleanup = None
        try:
            cleanup = RegeditManager.queue_registry_copy(
                registry_path,
                self.current_game.prefix,
                combo.currentText(),
                console,
                game=self.current_game,
            )
        except Exception as exc:
            logger.exception("Registry copy failed")
            QMessageBox.critical(self, self.tr("Registry Copy Failed"), str(exc))
            return

        console.start_queue()
        console.exec()
        if cleanup:
            cleanup()

        if not console.completed_successfully:
            return

    def _restore_state(self):
        """Restores the window size and position from the previous session."""
        geometry = self.settings.value("AdvancedSettingsDialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        """Overrides the default close event to save geometry before closing."""
        self.settings.setValue("AdvancedSettingsDialog/geometry", self.saveGeometry())
        super().closeEvent(event)
    
    def hideEvent(self, event):
        """Fires whenever the dialog is closed, hidden, accepted, or rejected."""
        self.settings.setValue("AdvancedSettingsDialog/geometry", self.saveGeometry())
        super().hideEvent(event)
