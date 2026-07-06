import logging
from typing import Callable, List, Protocol
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QMessageBox, QProgressDialog
from savedata_manager import SavedataManager
from timetracker.log_manager import LogManager

logger = logging.getLogger(__name__)


class SyncStep(Protocol):
    """
    A single pre-launch sync step.

    Implementations own all manager-specific wiring (which signals to listen
    to, how to tell "this" sync apart from an unrelated one). `start()` must
    call exactly one of on_success/on_failure, exactly once.
    """
    label: str

    def start(self, on_success: Callable[[], None], on_failure: Callable[[str], None]) -> None:
        ...


class SavedataSyncStep:
    """Syncs a game's savedata folder with Google Drive before launch."""

    def __init__(self, name: str, game_data: dict, label: str):
        self.name = name
        self.game_data = game_data
        self.label = label
        self._on_success = None
        self._on_failure = None

    def start(self, on_success, on_failure):
        self._on_success = on_success
        self._on_failure = on_failure
        manager = SavedataManager.get_instance()
        manager.gdrive_sync_succeeded.connect(self._handle_succeeded)
        manager.gdrive_sync_failed.connect(self._handle_failed)
        manager.start_gdrive_sync(self.name, self.game_data)

    def _handle_succeeded(self, name, result):
        if name != self.name:
            return  # Some other game's background sync finishing - not ours
        self._disconnect()
        self._on_success()

    def _handle_failed(self, name, error_message):
        if name != self.name:
            return
        self._disconnect()
        self._on_failure(error_message)

    def _disconnect(self):
        manager = SavedataManager.get_instance()
        manager.gdrive_sync_succeeded.disconnect(self._handle_succeeded)
        manager.gdrive_sync_failed.disconnect(self._handle_failed)


class TrackingSyncStep:
    """Syncs a game's time-tracking log with Google Drive before launch."""

    def __init__(self, game_path: str, label: str):
        self.game_path = game_path
        self.label = label
        self._on_success = None
        self._on_failure = None

    def start(self, on_success, on_failure):
        self._on_success = on_success
        self._on_failure = on_failure
        manager = LogManager.get_instance()
        manager.gdrive_sync_succeeded.connect(self._handle_succeeded)
        manager.gdrive_sync_failed.connect(self._handle_failed)
        manager.start_gdrive_sync(self.game_path)

    def _handle_succeeded(self, app_name, result):
        if app_name != self.game_path:
            return
        self._disconnect()
        self._on_success()

    def _handle_failed(self, app_name, error_message):
        if app_name != self.game_path:
            return
        self._disconnect()
        self._on_failure(error_message)

    def _disconnect(self):
        manager = LogManager.get_instance()
        manager.gdrive_sync_succeeded.disconnect(self._handle_succeeded)
        manager.gdrive_sync_failed.disconnect(self._handle_failed)


class PreLaunchSyncPipeline(QObject):
    """
    Runs steps in order before a game launches. Shows a single progress
    dialog across all steps, updating its label per-step. On any step
    failure, asks the user whether to launch anyway or cancel the launch entirely.
    """

    # True -> proceed with launch
    # False -> cancelled
    finished = Signal(bool)  

    def __init__(self, parent, steps: List[SyncStep]):
        super().__init__(parent)
        self._parent = parent
        self._steps = steps
        self._index = 0

        self.progress = QProgressDialog("", None, 0, 0, parent)
        self.progress.setWindowModality(Qt.WindowModal)
        self.progress.setWindowTitle(self.tr("Cloud Sync"))
        self.progress.setWindowFlags(self.progress.windowFlags() & ~Qt.WindowCloseButtonHint)

    def start(self):
        if not self._steps:
            self.finished.emit(True)
            return
        self.progress.show()
        self._run_next()

    def _run_next(self):
        if self._index >= len(self._steps):
            self.progress.close()
            self.finished.emit(True)
            return

        step = self._steps[self._index]
        logger.debug(f"Pre-launch sync step {self._index + 1}/{len(self._steps)}: {step.label}")
        self.progress.setLabelText(step.label)
        step.start(on_success=self._on_step_succeeded, on_failure=self._on_step_failed)

    def _on_step_succeeded(self):
        self._index += 1
        self._run_next()

    def _on_step_failed(self, error_message: str):
        self.progress.close()
        reply = QMessageBox.question(
            self._parent,
            self.tr("Sync Failed"),
            self.tr(
                f"Cloud sync failed:\n\n{error_message}\n\n"
                f"Do you want to launch the game anyway using local data?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        self.finished.emit(reply == QMessageBox.Yes)