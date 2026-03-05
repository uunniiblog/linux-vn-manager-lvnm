import psutil
import logging
from timetracker.desktop_utils_interface import DesktopUtilsInterface

logger = logging.getLogger(__name__)

class GamescopeUtils(DesktopUtilsInterface):
    def __init__(self):
        """
        Since Gamescope focuses one game at a time, if the PID exists
        we consider it the 'active window'. We return the PID as the Window ID.
        """
        pass

    def get_all_window_ids(self):
        return []

    def get_active_window_id(self):
        return "GAMESCOPE_ACTIVE" 

    def get_window_name(self, pid_str):
        try:
            return psutil.Process(int(pid_str)).name()
        except (psutil.NoSuchProcess, ValueError):
            return "Unknown"

    def get_window_pid(self, pid_str):
        return pid_str

    def find_window_by_pid(self, target_pid, target_process_path):
        try:
            process = psutil.Process(int(target_pid))
            if process.is_running():
                # Returning (Window ID, Title)
                return str(target_pid), process.name()
        except psutil.NoSuchProcess:
            pass
        
        return None, None

    def find_window_id_by_title(self, target_title):
        return None