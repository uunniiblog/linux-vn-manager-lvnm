import config
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget
)
from gdrive_manager import GdriveDeviceFlowWorker, GdriveManager
from platform_profile import CURRENT_PLATFORM, PlatformProfile
from system_utils import SystemUtils
from ui.savedata_management_dialog import SavedataManagementDialog
from ui.settings_page import SettingsPage

class SavedataTab(SettingsPage):
    def __init__(self, platform: PlatformProfile = CURRENT_PLATFORM):
        super().__init__()
        self.platform = platform

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        layout.addWidget(self._build_savedata_group())
        layout.addWidget(self._build_gdrive_group())
        layout.addStretch()
        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

        self.savedata_enable.toggled.connect(self._on_savedata_toggled)
        self._on_savedata_toggled(self.savedata_enable.isChecked())

        self.savedata_enable.stateChanged.connect(lambda state: self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_ENABLED, bool(state)))
        self.auto_detect_save.stateChanged.connect(lambda state: self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_AUTO_DETECT, bool(state)))
        self._bind_text_setting(
            self.gdrive_client_id_edit, config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_ID, parent_key=config.USER_CONF_SAVEDATA,
            convert=str.strip, reset_gdrive_cache=True
        )
        self._bind_text_setting(
            self.gdrive_client_secret_edit, config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_SECRET, parent_key=config.USER_CONF_SAVEDATA,
            convert=str.strip, reset_gdrive_cache=True
        )
        self.all_gdrive_ckbox.stateChanged.connect(lambda state: self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_GDRIVE_ALL_GAMES, bool(state)))

    def _build_savedata_group(self):
        savedata_group = QGroupBox(self.tr("Savedata Management"))
        savedata_layout = QFormLayout(savedata_group)
        savedata_layout.setLabelAlignment(Qt.AlignLeft)

        # Retrieve current settings
        savedata_settings = self.user_settings.get(config.USER_CONF_SAVEDATA, {})

        # Enable Checkbox
        self.savedata_enable = QCheckBox(self.tr("Enable"))
        self.savedata_enable.setChecked(savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False))
        savedata_layout.addRow(QLabel(self.tr("Savedata management:")), self.savedata_enable)

        # Auto detect checkbox
        auto_detect_label = QLabel(self.tr("Auto Detect Save:"))
        auto_detect_tip = self.tr("Automatically tries to auto detect the save data folder for the game after closing the game if it hasn't been set")
        auto_detect_label.setToolTip(auto_detect_tip)
        self.auto_detect_save = QCheckBox(self.tr("Enable"))
        self.auto_detect_save.setChecked(savedata_settings.get(config.USER_CONF_SAVEDATA_AUTO_DETECT, False))
        self.auto_detect_save.setToolTip(auto_detect_tip)
        savedata_layout.addRow(auto_detect_label, self.auto_detect_save)

        # Savedata dialog
        self.manage_savedata_btn = QPushButton(self.tr("Manage Savedata"))
        self.manage_savedata_btn.setCursor(Qt.PointingHandCursor)
        self.manage_savedata_btn.clicked.connect(self._open_savedata_manager)
        manage_row = QHBoxLayout()
        manage_row.addWidget(self.manage_savedata_btn)
        manage_row.addStretch()
        savedata_layout.addRow(QLabel(self.tr("Manage savedata:")), manage_row)

        self.savedata_dependent_widgets = [auto_detect_label, self.auto_detect_save, self.manage_savedata_btn]
        return savedata_group

    def _build_gdrive_group(self):
        gdrive_group = QGroupBox(self.tr("Google Drive Options"))
        gdrive_layout = QFormLayout(gdrive_group)
        gdrive_layout.setLabelAlignment(Qt.AlignLeft)
        savedata_settings = self.user_settings.get(config.USER_CONF_SAVEDATA, {})

        # Guide link
        gdrive_guide_label = QLabel(f'Google cloud setup guide: <a href="{config.GDRIVE_SETUP_GUIDE}"> {config.GDRIVE_SETUP_GUIDE} </a>')
        gdrive_guide_label.linkActivated.connect(SystemUtils.open_url)
        gdrive_guide_label.setStyleSheet("color: #888; font-style: italic; margin-bottom: 5px;")
        gdrive_guide_label.setWordWrap(True)
        gdrive_layout.addRow(gdrive_guide_label)

        # Auto enable Gsync games checkbox
        all_gdrive_label = QLabel(self.tr("Automatically enable:"))
        all_gdrive_tip = self.tr(
            "Recommended to enable the sync from the start in secondary devices. "
            "Will autofetch and create the savedata folder and avoid conflicts"
        )
        all_gdrive_label.setToolTip(all_gdrive_tip)
        self.all_gdrive_ckbox = QCheckBox(self.tr("Automatically enables GDrive Sync for all new games (Recommended)"))
        self.all_gdrive_ckbox.setChecked(savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_ALL_GAMES, False))
        self.all_gdrive_ckbox.setToolTip(all_gdrive_tip)
        gdrive_layout.addRow(all_gdrive_label, self.all_gdrive_ckbox)

        # Gdrive Client ID
        gdrive_id_label = QLabel(self.tr("Gdrive Client ID:"))
        self.gdrive_client_id_edit, gdrive_id_row = self._create_secret_field(savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_ID, ""))
        gdrive_layout.addRow(gdrive_id_label, gdrive_id_row)

        # Gdrive Client Secret
        gdrive_secret_label = QLabel(self.tr("Gdrive Client Secret:"))
        self.gdrive_client_secret_edit, gdrive_secret_row = self._create_secret_field(savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_SECRET, ""))
        gdrive_layout.addRow(gdrive_secret_label, gdrive_secret_row)

        # Gdrive status + single toggling button (Sign in <-> Log out)
        status_label = QLabel(self.tr("Gdrive Account:"))

        self.gdrive_status_dot = QLabel("●")
        self.gdrive_status_dot.setFixedWidth(14)

        self.gdrive_status_text = QLabel()

        self.gdrive_auth_btn = QPushButton()
        self.gdrive_auth_btn.setFlat(True)
        self.gdrive_auth_btn.setStyleSheet("text-align: left; color: palette(link); padding: 4px 10px;")
        self.gdrive_auth_btn.setCursor(Qt.PointingHandCursor)
        self.gdrive_auth_btn.clicked.connect(self._on_gdrive_auth_clicked)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.addWidget(self.gdrive_status_dot)
        status_row.addWidget(self.gdrive_status_text)
        status_row.addWidget(self.gdrive_auth_btn)
        status_row.addStretch()
        gdrive_layout.addRow(status_label, status_row)

        self._update_gdrive_ui_state()

        # Widgets that only make sense when savedata management is enabled
        self.savedata_dependent_widgets.extend([
            gdrive_id_label,
            self.gdrive_client_id_edit,
            gdrive_secret_label,
            self.gdrive_client_secret_edit,
            status_label,
            self.gdrive_status_dot,
            self.gdrive_status_text,
            self.gdrive_auth_btn,
            all_gdrive_label,
            self.all_gdrive_ckbox
        ])

        return gdrive_group

    def _open_savedata_manager(self):
        """Opens the dialog to manage savedata."""

        dialog = SavedataManagementDialog(self, platform=self.platform)
        dialog.exec()

    def _on_savedata_toggled(self, checked):
        """Helper to enable/disable all savedata sub-widgets"""
        for widget in self.savedata_dependent_widgets:
            widget.setEnabled(checked)
        if checked:
            self._update_gdrive_ui_state()

    def refresh_active_tab(self):
        self._update_gdrive_ui_state()
        if not self.savedata_enable.isChecked():
            self._on_savedata_toggled(False)

    def _sign_in_gdrive(self):
        """Starts the Google Drive device-flow sign-in using the configured client id/secret."""
        self.flush_pending_text_settings()
        client_id = self.gdrive_client_id_edit.text().strip()
        client_secret = self.gdrive_client_secret_edit.text().strip()

        if not client_id or not client_secret:
            QMessageBox.warning(
                self,
                self.tr("Missing Credentials"),
                self.tr("Please enter both the Google Client ID and Client Secret before signing in.")
            )
            return

        self.gdrive_worker = GdriveDeviceFlowWorker(client_id, client_secret)

        self._gdrive_dialog = QDialog(self)
        self._gdrive_dialog.setWindowTitle(self.tr("Sign in to Google Drive"))
        self._gdrive_dialog.resize(400, 250)
        layout = QVBoxLayout(self._gdrive_dialog)

        self._gdrive_status_label = QLabel(self.tr("Requesting device code..."))
        layout.addWidget(self._gdrive_status_label)

        self._gdrive_code_label = QLabel("")
        self._gdrive_copy_btn = QPushButton(self.tr("Copy"))
        self._gdrive_copy_btn.clicked.connect(self._copy_gdrive_code)

        code_row = QHBoxLayout()
        code_row.addWidget(self._gdrive_code_label)
        code_row.addWidget(self._gdrive_copy_btn)
        code_row.addStretch()
        layout.addLayout(code_row)

        self._gdrive_link_label = QLabel("")
        self._gdrive_link_label.linkActivated.connect(SystemUtils.open_url)
        layout.addWidget(self._gdrive_link_label)

        progress = QProgressBar()
        progress.setRange(0, 0)  # indeterminate spinner
        layout.addWidget(progress)

        self.gdrive_worker.device_code_ready.connect(self._on_gdrive_device_code_ready)
        self.gdrive_worker.login_success.connect(self._on_gdrive_login_success)
        self.gdrive_worker.login_failed.connect(self._on_gdrive_login_failed)
        self.gdrive_worker.login_timeout.connect(self._on_gdrive_login_timeout)

        self._gdrive_dialog.finished.connect(self._cancel_gdrive_worker)

        self.gdrive_worker.start()
        self._gdrive_dialog.exec()
        self._update_gdrive_ui_state() 

    def _copy_gdrive_code(self):
        code = getattr(self, "_gdrive_user_code", "")
        if code:
            QApplication.clipboard().setText(code)

    def _cancel_gdrive_worker(self):
        if hasattr(self, "gdrive_worker") and self.gdrive_worker.isRunning():
            self.gdrive_worker.cancel()

    def _on_gdrive_device_code_ready(self, device_info):
        user_code = device_info.get("user_code", "")
        verification_url = device_info.get("verification_url", "")

        self._gdrive_status_label.setText(self.tr("Enter this code at the link below:"))
        self._gdrive_user_code = user_code

        self._gdrive_code_label.setText(f"<b style='font-size: 18px;'>{user_code}</b>")
        self._gdrive_link_label.setText(f'<a href="{verification_url}" style="color: #3498db;">🔗 {verification_url}</a>')

    def _on_gdrive_login_success(self, token_data):
        GdriveManager.save_credentials(token_data)
        self._gdrive_dialog.accept()
        self._update_gdrive_ui_state()
        QMessageBox.information(self, self.tr("Connected"), self.tr("Successfully signed in to Google Drive."))

    def _on_gdrive_login_failed(self, error_message):
        self._gdrive_dialog.reject()
        QMessageBox.critical(self, self.tr("Sign-in Failed"), error_message)

    def _on_gdrive_login_timeout(self):
        self._gdrive_dialog.reject()
        QMessageBox.warning(self, self.tr("Timed Out"), self.tr("Sign-in timed out. Please try again."))

    def _on_gdrive_auth_clicked(self):
        """Routes to sign-in or logout depending on current state."""
        if GdriveManager.is_logged_in():
            self._logout_gdrive()
            self.save_nested_setting(config.USER_CONF_SAVEDATA, config.USER_CONF_SAVEDATA_GDRIVE_ALL_GAMES, False)
        else:
            self._sign_in_gdrive()

    def _logout_gdrive(self):
        client_id = self.gdrive_client_id_edit.text().strip()
        client_secret = self.gdrive_client_secret_edit.text().strip()
        GdriveManager.logout(client_id, client_secret)
        self._update_gdrive_ui_state()

    def _update_gdrive_ui_state(self):
        """Updates the status dot/text and toggles the auth button between Sign in / Log out."""
        connected = GdriveManager.is_logged_in()

        if connected:
            self.gdrive_status_dot.setStyleSheet("color: #4caf50;")
            self.gdrive_status_text.setText(self.tr("Connected"))
            self.gdrive_auth_btn.setText(self.tr("Log out"))
            self.all_gdrive_ckbox.setEnabled(True)
        else:
            self.gdrive_status_dot.setStyleSheet("color: #888888;")
            self.gdrive_status_text.setText(self.tr("Not connected"))
            self.gdrive_auth_btn.setText(self.tr("Sign in to Google Drive"))
            self.all_gdrive_ckbox.setEnabled(False)
            self.all_gdrive_ckbox.setChecked(False)
