import time
import datetime
import config
import logging
from PySide6.QtCore import QThread, Signal
from timetracker.kde_utils import KdeUtils
from timetracker.system_utils import SystemUtils
from timetracker.log_manager import LogManager

logger = logging.getLogger(__name__)

class TrackerWorker(QThread):
    log_message = Signal(str)

    def __init__(self, window_id, app_name, process_name, desktop_utils, refresh_interval=60, save_interval=3, afk_timer=0):
        super().__init__()

        self.app_name = app_name
        self.utils = desktop_utils
        self.target_window_id = window_id
        self.process_name = process_name

        # Find executable
        if self.target_window_id and not self.process_name:
            active_pid = self.utils.get_window_pid(self.target_window_id)
            self.process_name = SystemUtils.get_app_name_from_pid(active_pid)
            logger.debug(f'self.process_name {self.process_name}')
        
        if not self.target_window_id:
            logger.error(f"Could not find Application window ID for: {app_name}")
            return

        # Initialize the LogManager
        self.logger = LogManager(config.LOG_DIR)

        self.refresh_interval = int(refresh_interval)
        self.save_interval = int(save_interval) * 60
        self.afk_timer = int(afk_timer) * 60
        
        self.running = True
        self.session_line_exists = False

        # Internal counters
        self.total_playtime = 0
        self.session_playtime = 0
        self.session_start = datetime.datetime.now()
        

    def is_window_open(self):
        """
        Checks if any open window matches the target window id.
        If not search by process name until new PID is found.
        """
        try:
            # Get all IDs again
            all_ids = self.utils.get_all_window_ids()
            if self.target_window_id in all_ids:
                return True

            # Looks up if new PID exists
            new_pid = SystemUtils.get_pid_by_name(self.process_name)
            #print(f'new_pid {new_pid}')
            if new_pid:
                new_wid = self.utils.find_window_by_pid(new_pid)
                # print(f'new_wid {new_wid}')
                if new_wid and new_wid[0]:
                    self.target_window_id = str(new_wid[0])
                    return True

            return False
        except Exception as e:
            logger.error(f"Error checking window status: {e}")
            return False

    def is_game_focused(self):
        """ Checks if target ID is focused """
        if not self.target_window_id:
            return False

        active_id = self.utils.get_active_window_id()
        #print(f"active_id: {active_id}")
        #print(f"self.target_window_id: {self.target_window_id}")
        return str(active_id) == str(self.target_window_id)

    def run(self):
        """ Main loop logic to calculate active window focus """
        # Load previous total playtime
        # Scan daily logs for this specific app's history
        self.total_playtime = self.logger.get_total_app_playtime(self.process_name)
        logger.debug(f"Starting tracking for: {self.app_name} - {self.process_name} - {self.target_window_id}")
        logger.debug(f"Starting playtime: {self.logger.format_duration(self.total_playtime)}")

        # Launch swayidle afk detection
        if self.afk_timer > 0:
            SystemUtils.start_afk_daemon(self.afk_timer)

        was_afk = False

        last_tick = time.monotonic()
        last_log_update = last_tick
        last_save_time = last_tick

        # Check if windows exists
        last_existence_check = 0 
        window_currently_open = True

        # Accumulator for sub-second precision
        accumulator = 0.0

        while self.running:
            now = time.monotonic()
            delta = now - last_tick
            last_tick = now
            accumulator += delta

            # Existence Check (Every 4.5 seconds)
            if now - last_existence_check >= 4.5:
                is_open = self.is_window_open()
                
                if window_currently_open and not is_open:
                    logger.debug(f"'{self.process_name}' closed. Waiting for restart...")
                    window_currently_open = False
                elif not window_currently_open and is_open:
                    logger.debug(f"'{self.process_name}' detected again with new ID {self.target_window_id}. Resuming tracking.")
                    window_currently_open = True

                # AFK check
                is_afk, idle_time = SystemUtils.get_afk_status()

                if is_afk and not was_afk:
                    self.log_message.emit("Status: AFK (Tracking paused)")
                    was_afk = True
                elif not is_afk and was_afk:
                    self.log_message.emit("Status: Resumed (Back from AFK)")
                    was_afk = False
                
                last_existence_check = now
                
            # Increment timer every second if focused and not AFK
            if accumulator >= 1.0:
                seconds_passed = int(accumulator)

                if window_currently_open and not is_afk:
                    if self.is_game_focused():
                        self.total_playtime += seconds_passed
                        self.session_playtime += seconds_passed

                # Keep the fractional remainder
                accumulator -= seconds_passed

            # UI logging
            if self.refresh_interval > 0 and (now - last_log_update) >= self.refresh_interval and window_currently_open and not is_afk:
                logger.debug(f"Session playtime: {self.logger.format_duration(self.session_playtime)}")
                logger.debug(f"Total playtime: {self.logger.format_duration(self.total_playtime)}")
                last_log_update = now

            # Periodic Save
            if self.save_interval > 0 and (now - last_save_time) >= self.save_interval and window_currently_open and not is_afk:
                self._trigger_log_save()
                last_save_time = now

            # Small sleep to reduce CPU usage
            time.sleep(0.1)

        # Stop swayidle
        SystemUtils.stop_afk_daemon()
        # Persist session on exit
        self._trigger_log_save(is_final=True)

    def _trigger_log_save(self, is_final=False):
        now = datetime.datetime.now()
        
        # Prepare the data packet for the LogManager
        session_data = {
            'start': self.session_start,
            'end': now,
            'duration': int((now - self.session_start).total_seconds()),
            'active_time': self.session_playtime,
            'app': self.process_name,
            'title': self.app_name,
            'status': "Manual",
            'tags': ""
        }

        # Save to file
        log_file = self.logger.save_session(session_data, is_update=self.session_line_exists)
        self.session_line_exists = True
            
        if is_final:
            session_length = int((now - self.session_start).total_seconds())
            logger.info(f"Session Length: {self.logger.format_duration(session_length)} Session Playtime: {self.logger.format_duration(self.session_playtime)} Total Playtime: {self.logger.format_duration(self.total_playtime)}")
            logger.info(f"Final session saved to {log_file.name}")
        else:
            logger.info(f"Progress autosaved to {log_file.name}")

    def stop(self):
        self.running = False
