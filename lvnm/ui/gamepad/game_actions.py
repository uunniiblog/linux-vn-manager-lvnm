import json
import logging
import config
from pathlib import Path
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox
from game_manager import GameManager
from game_process_manager import GameProcessManager
from launchers.launcher_wine_game import LauncherWineGame
from pregame_sync_pipeline import PreLaunchSyncPipeline, SavedataSyncStep, TrackingSyncStep
from settings_manager import SettingsManager
from system_utils import SystemUtils
from ui.game_list_item import LogViewerDialog
from ui.savedata_conflict_prompt import prompt_savedata_conflict

logger = logging.getLogger(__name__)

class GamepadGameActions(QObject):
    """Run game operations while keeping the gamepad pages presentation-only."""

    changed = Signal()
    deleted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.host = parent
        self.process_manager = GameProcessManager.get_instance()
        settings = SettingsManager()
        self.timetracker_settings = settings.get(config.USER_CONF_TIMETRACKER, {})
        self.savedata_settings = settings.get(config.USER_CONF_SAVEDATA, {})
        self._pipeline = None
        self._log_windows = []

    def toggle_game(self, card):
        if self.process_manager.is_game_running(card.name):
            self.process_manager.stop_game(card.name)
            return
        self.launch_game(card)

    def launch_game(self, card):
        """Use the same cloud-sync pipeline as the desktop sidebar."""
        try:
            fresh_card = GameManager.get_game(card.name) or card
            steps = []
            if self.savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False) and fresh_card.gdrive:
                steps.append(SavedataSyncStep(
                    fresh_card.name,
                    fresh_card.to_dict(),
                    self.tr("Syncing save data with Google Drive..."),
                    conflict_prompt=lambda conflicts: prompt_savedata_conflict(
                        self.host, fresh_card.name, conflicts
                    ),
                ))
            if self.timetracker_settings.get( config.USER_CONF_TIMETRACKER_GDRIVE_SYNC, False) and self.savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False) and fresh_card.gdrive:
                steps.append(TrackingSyncStep(fresh_card, self.tr("Syncing time tracking data...")))

            if not steps:
                self._execute_launch(fresh_card.name)
                return

            self._pipeline = PreLaunchSyncPipeline(self.host, steps)
            self._pipeline.finished.connect(lambda proceed, name=fresh_card.name: self._finish_pipeline(name, proceed))
            self._pipeline.start()
        except Exception as exc:
            logger.exception("Could not launch %s", card.name)
            QMessageBox.critical(self.host, self.tr("Error"), str(exc))

    def _finish_pipeline(self, name, proceed):
        self._pipeline = None
        if proceed:
            self._execute_launch(name)

    def _execute_launch(self, name):
        try:
            self.process_manager.start_game(name, self.timetracker_settings)
        except Exception as exc:
            logger.exception("Could not launch %s", name)
            QMessageBox.critical(self.host, self.tr("Error"), str(exc))

    def show_logs(self, card):
        window = LogViewerDialog(card.name, self.host)
        window.setAttribute(Qt.WA_DeleteOnClose)
        window.show()
        window.raise_()
        window.activateWindow()
        self._log_windows.append(window)
        window.destroyed.connect(lambda _object=None, current=window: self._discard_log_window(current))

    def _discard_log_window(self, window):
        if window in self._log_windows:
            self._log_windows.remove(window)

    def browse_files(self, card):
        try:
            SystemUtils.browse_files(card.path)
        except (ValueError, RuntimeError) as exc:
            QMessageBox.critical(self.host, self.tr("Error"), str(exc))

    def open_texthooker(self, card):
        settings = SettingsManager().get(config.USER_CONF_TEXTHOOKER, {})
        path = settings.get("path")
        if not path:
            QMessageBox.critical(
                self.host, self.tr("Error"),
                self.tr("Texthooker path missing. Set it up in settings."),
            )
            return
        try:
            LauncherWineGame("texthook").run_texthooker(
                path, card.prefix, gamescope=card.gamescope,
                target_exe_path=card.path,
            )
        except RuntimeError as exc:
            QMessageBox.critical(self.host, self.tr("Error"), str(exc))

    def run_wine_utility(self, card, command):
        try:
            LauncherWineGame("UtilityMode").run_in_prefix(command, card.prefix)
        except RuntimeError as exc:
            QMessageBox.critical(self.host, self.tr("Error"), str(exc))

    def open_bash(self, card):
        try:
            LauncherWineGame("UtilityMode").open_terminal(card.prefix)
        except RuntimeError as exc:
            QMessageBox.critical(self.host, self.tr("Error"), str(exc))

    def desktop_shortcut(self, card):
        try:
            SystemUtils.create_desktop_shortcut(card.name, card.cover_path)
        except FileNotFoundError:
            path, _ = QFileDialog.getSaveFileName(
                self.host,
                self.tr("Save shortcut as"),
                str(Path.home() / f"lvnm-{card.name}.desktop"),
                self.tr("Desktop Entry (*.desktop)"),
            )
            if not path:
                return
            if not path.endswith(".desktop"):
                path += ".desktop"
            try:
                SystemUtils.create_desktop_shortcut(card.name, card.cover_path, target_path=path)
            except RuntimeError as exc:
                QMessageBox.critical(self.host, self.tr("Error"), str(exc))
        except RuntimeError as exc:
            QMessageBox.critical(self.host, self.tr("Error"), str(exc))

    def steam_shortcut(self, card):
        try:
            SystemUtils.add_to_steam(card)
        except RuntimeError as exc:
            QMessageBox.critical(self.host, self.tr("Error"), str(exc))

    def duplicate(self, card):
        try:
            if GameManager.duplicate_game(card.name):
                self.changed.emit()
        except RuntimeError as exc:
            QMessageBox.critical(self.host, self.tr("Error"), str(exc))

    def delete(self, card):
        reply = QMessageBox.question(
            self.host,
            self.tr("Confirm Deletion"),
            self.tr("Are you sure you want to delete '{}'?").format(card.name),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            GameManager.delete_game(card.name)
            self.deleted.emit()
            self.changed.emit()
        except RuntimeError as exc:
            QMessageBox.critical(self.host, self.tr("Error"), str(exc))

    def export(self, card):
        data = GameManager.export_game(card.name)
        if not data:
            return
        path, _ = QFileDialog.getSaveFileName(
            self.host,
            self.tr("Export Game"),
            f"{card.name}.json",
            self.tr("JSON Files (*.json)"),
        )
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as output:
                json.dump(data, output, indent=4, ensure_ascii=False)
        except OSError as exc:
            QMessageBox.critical(self.host, self.tr("Failed to export"), str(exc))
