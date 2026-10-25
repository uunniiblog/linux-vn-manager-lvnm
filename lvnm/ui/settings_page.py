from PySide6.QtWidgets import QApplication, QHBoxLayout, QLineEdit, QMessageBox, QToolButton, QWidget
from gdrive_manager import GdriveManager
from settings_manager import SettingsManager

class SettingsPage(QWidget):
    """Shared utilities between settings pages"""

    def __init__(self):
        super().__init__()
        self.user_settings = SettingsManager()
        self._pending_text_save = False
        self._gdrive_cache_dirty = False
        QApplication.instance().aboutToQuit.connect(self.flush_pending_text_settings)

    def _create_secret_field(self, initial_value=""):
        """
        Creates a password-style QLineEdit with a toggle button to reveal/hide the text.
        Returns (line_edit, container_layout)
        """
        line_edit = QLineEdit(initial_value)
        line_edit.setEchoMode(QLineEdit.Password)

        toggle_btn = QToolButton()
        toggle_btn.setCheckable(True)
        toggle_btn.setText("👁")
        toggle_btn.setToolTip(self.tr("Show/Hide"))
        toggle_btn.setFixedWidth(28)
        toggle_btn.toggled.connect(lambda checked, e=line_edit: e.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password))

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(line_edit)
        row.addWidget(toggle_btn)

        return line_edit, row

    def _bind_text_setting(self, edit_widget, key, parent_key=None, convert=None, reset_gdrive_cache=False):
        """Keep text settings current in memory and batch disk writes."""
        def changed(text):
            value = convert(text) if convert else text
            if parent_key:
                self.save_nested_setting(parent_key, key, value, deferred=True)
            else:
                self.save_setting(key, value, deferred=True)
            if reset_gdrive_cache:
                self._gdrive_cache_dirty = True

        edit_widget.textChanged.connect(changed)
        edit_widget.editingFinished.connect(self.flush_pending_text_settings)

    def _finish_text_save(self):
        self._pending_text_save = False
        if self._gdrive_cache_dirty:
            self._gdrive_cache_dirty = False
            GdriveManager.reset_service_cache()

    def flush_pending_text_settings(self):
        if not self._pending_text_save:
            return
        self.user_settings.flush()
        self._finish_text_save()

    def hideEvent(self, event):
        self.flush_pending_text_settings()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.flush_pending_text_settings()
        super().closeEvent(event)

    def save_setting(self, key, value, deferred=False):
        try:
            if deferred:
                self.user_settings.set_deferred(key, value)
                self._pending_text_save = True
            else:
                self.user_settings.set(key, value)
                if self._pending_text_save:
                    self._finish_text_save()
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr(str(e)))

    def save_nested_setting(self, parent_key, child_key, value, deferred=False):
        try:
            parent_dict = self.user_settings.get(parent_key, {})
            if not isinstance(parent_dict, dict):
                parent_dict = {}
            updated_parent = dict(parent_dict)
            updated_parent[child_key] = value
            if deferred:
                self.user_settings.set_deferred(parent_key, updated_parent)
                self._pending_text_save = True
            else:
                self.user_settings.set(parent_key, updated_parent)
                if self._pending_text_save:
                    self._finish_text_save()
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr(str(e)))
