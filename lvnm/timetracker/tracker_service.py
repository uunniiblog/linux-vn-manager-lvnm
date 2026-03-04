import logging
from PySide6.QtCore import QObject, Signal
from timetracker.tracker_worker import TrackerWorker
from timetracker.utils_factory import get_desktop_utils

logger = logging.getLogger(__name__)

class TrackerService(QObject):

    def __init__(self):
        super().__init__()
        self.worker = None
        try:
            self.desktop_utils = get_desktop_utils()
        except RuntimeError as e:
            logger.error(f"TrackerService Critical Startup Error: {e}")
            self.desktop_utils = None

    def start_tracking(self, wid, app_name, process_name, refresh_timer=10, save_interval=3, afk_timer=0):
        if not self.desktop_utils:
            logger.error("Desktop utilities not initialized.")
            return
            
        # Stop existing worker if any
        if self.worker and self.worker.isRunning():
            self.stop_tracking()

        self.worker = TrackerWorker(wid, app_name, process_name, self.desktop_utils, refresh_timer, save_interval, afk_timer)

        if not self.worker.is_window_open():
            logger.error(f"Window '{app_name}' not found. Start the app before tracking.")
            self.tracking_finished.emit()
            return 

        self.worker.start()

    def stop_tracking(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
