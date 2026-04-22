import os
import logging
from PySide6.QtCore import QObject, QTimer, Signal
from timetracker.system_utils import SystemUtils
from timetracker.tracker_service import TrackerService

logger = logging.getLogger(__name__)

class TrackingController(QObject):
    stats_received = Signal(dict)

    def __init__(self, main_window, process_path, save_interval=3, afk_timer=0):
        super().__init__()
        self.window = main_window # TODO: maybe raise visual error if tracking failed
        self.tracker = TrackerService()
        self.auto_timer = None
        self.target_process = os.path.basename(process_path)
        self.log_file_name = f"{os.path.basename(process_path)}_{os.path.getsize(process_path)}"
        self.save_interval = save_interval
        self.afk_timer = afk_timer
        self.launch_attemps = 0

    def start_auto_tracking(self):
        logger.info(f"Auto-tracking enabled for: {self.target_process}")
        logger.debug("Looking for PID...")
        self.launch_attemps = 0

        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self._attempt_auto_launch)
        self.auto_timer.start(2000)

    def _attempt_auto_launch(self):
        if self.launch_attemps > 20:
            logger.error(f"Could not find {self.target_process} after 20 attempts. Timetracker DISABLED")
            self.auto_timer.stop()
            return

        self.launch_attemps += 1
        logger.debug(f"_attempt_auto_launch {self.launch_attemps}/20...")
        
        utils = self.tracker.desktop_utils
        pid = SystemUtils.get_pid_by_name(self.target_process)
        
        if not pid:
            logger.warning(f"PID not found. Attempt {self.launch_attemps}/20...")
            return 

        logger.debug(f"Detected PID: {pid}. Looking for Window ID...")
        
        wid, title = utils.find_window_by_pid(pid, self.target_process)
        logger.debug(f"wid {wid}, title {title}")

        
        if title and wid:
            self.auto_timer.stop()
            logger.info(f"Success! Found Window: {title}")
            self.tracker.start_tracking(wid, title, self.target_process, log_file=self.log_file_name, save_interval=self.save_interval, afk_timer=self.afk_timer)
            if self.tracker.worker:
                self.tracker.worker.stats_updated.connect(self.stats_received.emit)

    def stop_tracking(self):
        logger.info(f"Stopping tracking for {self.target_process}")
        
        # Stop timer
        if self.auto_timer:
            self.auto_timer.stop()
            self.auto_timer.deleteLater()
            self.auto_timer = None
        
        if self.tracker and self.tracker.worker:
            try:
                self.tracker.worker.stats_updated.disconnect()
            except (TypeError, RuntimeError):
                pass

        self.tracker.stop_tracking()

    def start_manual_tracking(self, wid, title):
        logger.info(f"Start Manual tracking for {wid}")
        # self.tracker = TrackerService()
        self.tracker.start_tracking(wid, title, None, log_file=self.log_file_name, save_interval=self.save_interval, afk_timer=self.afk_timer)
        if self.tracker.worker:
            self.tracker.worker.stats_updated.connect(self.stats_received.emit)
