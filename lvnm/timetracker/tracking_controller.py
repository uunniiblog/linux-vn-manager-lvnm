import os
import logging
from PySide6.QtCore import QObject, QTimer
from timetracker.system_utils import SystemUtils
from timetracker.tracker_service import TrackerService

logger = logging.getLogger(__name__)

class TrackingController(QObject):
    def __init__(self, main_window, process_path, save_interval=3, afk_timer=0):
        super().__init__()
        self.window = main_window
        self.tracker = TrackerService()
        self.auto_timer = None
        self.target_process = None
        self.target_process = os.path.basename(process_path)
        self.save_interval = save_interval
        self.afk_timer = afk_timer

    def start_auto_tracking(self):
        logger.info(f"Auto-tracking enabled for: {self.target_process}")
        logger.debug("Looking for PID...")

        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self._attempt_auto_launch)
        self.auto_timer.start(2000)

    def _attempt_auto_launch(self):
        utils = self.tracker.desktop_utils
        pid = SystemUtils.get_pid_by_name(self.target_process)
        
        if not pid:
            logger.error("PID not found")
            return 

        logger.debug(f"Detected PID: {pid}. Looking for KWin window...")
        
        wid, title = utils.find_window_by_pid(pid)
        logger.debug(f"wid {wid}, title {title}")
        
        if title and wid:
            self.auto_timer.stop()
            logger.info(f"Success! Found Window: {title}")
            self.tracker.start_tracking(wid, title, self.target_process, save_interval=self.save_interval, afk_timer=self.afk_timer)

    def stop_tracking(self):
        logger.info(f"Stopping tracking for {self.target_process}")
        self.tracker.stop_tracking()