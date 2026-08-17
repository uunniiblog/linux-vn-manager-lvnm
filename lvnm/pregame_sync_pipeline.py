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

    def start(self, on_success: Callable[[], None], on_failure: Callable[[str], None], on_cancelled: Callable[[str], None]) -> None:
        ...


class SavedataSyncStep:
    """Syncs a game's savedata folder with Google Drive before launch."""

    def __init__(self, name: str, game_data: dict, label: str, conflict_prompt=None):
        self.name = name
        self.game_data = game_data
        self.label = label
        self.conflict_prompt = conflict_prompt
        self._on_success = None
        self._on_failure = None
        self._on_cancelled = None

    def start(self, on_success, on_failure, on_cancelled=None):
        self._on_success = on_success
        self._on_failure = on_failure
        self._on_cancelled = on_cancelled
        self._run_sync(conflict_resolution="defer")

    def _run_sync(self, conflict_resolution):
        manager = SavedataManager.get_instance()
        manager.gdrive_sync_succeeded.connect(self._handle_succeeded)
        manager.gdrive_sync_failed.connect(self._handle_failed)
        manager.start_gdrive_sync(self.name, self.game_data, conflict_resolution=conflict_resolution)

    def _handle_succeeded(self, name, result):
        if name != self.name:
            return  # Some other game's background sync finishing
        self._disconnect()

        deferred = result.get("deferred_conflicts") or []
        if deferred and self.conflict_prompt is not None:
            resolution = self.conflict_prompt(deferred)
            if resolution == "cancel":
                self._on_cancelled()
                return
            if resolution in ("prefer_local", "prefer_remote"):
                self._run_sync(conflict_resolution=resolution)
                return
            # resolution == "defer": Launch without syncing these

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

    def __init__(self, game, label: str):
        self.game = game
        self.label = label
        self._on_success = None
        self._on_failure = None

    def start(self, on_success, on_failure, on_cancelled=None):
        self._on_success = on_success
        self._on_failure = on_failure
        manager = LogManager.get_instance()
        manager.gdrive_sync_succeeded.connect(self._handle_succeeded)
        manager.gdrive_sync_failed.connect(self._handle_failed)
        manager.start_gdrive_sync(self.game)

    def _handle_succeeded(self, game, result):
        if game != self.game:
            return
        self._disconnect()
        self._on_success()

    def _handle_failed(self, game, error_message):
        if game != self.game:
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
        step.start(on_success=self._on_step_succeeded, on_failure=self._on_step_failed, on_cancelled=self._on_step_cancelled)

    def _on_step_succeeded(self):
        self._index += 1
        self._run_next()

    def _on_step_failed(self, error_message: str):
        self.progress.close()
        reply = QMessageBox.question(
            self._parent,
            self.tr("Sync Failed"),
            self.tr(
                "Cloud sync failed:\n\n{}\n\n"
                "Do you want to launch the game anyway using local data?"
            ).format(error_message),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        self.finished.emit(reply == QMessageBox.Yes)

    def _on_step_cancelled(self):
        self.progress.close()
        self.finished.emit(False)

class ManualSyncPipeline(PreLaunchSyncPipeline):
    """
    A sync pipeline variant for manual triggers. 
    """
    def _on_step_failed(self, error_message: str):
        self.progress.close()        
        QMessageBox.critical(
            self._parent,
            self.tr("Sync Failed"),
            self.tr("Cloud sync failed:\n\n{}").format(error_message)
        )
        
        # Emit False since the sync sequence failed/cancelled
        self.finished.emit(False)