import os
import logging
from timetracker.desktop_utils_interface import DesktopUtilsInterface
from timetracker.system_utils import SystemUtils

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
        return SystemUtils.get_app_name_from_pid(int(pid_str))
       
    def get_window_pid(self, pid_str):
        return pid_str

    def find_window_by_pid(self, target_pid, target_process_path):
        target_pid_str = str(target_pid)
        
        # Check if the process folder exists in /proc
        if os.path.exists(f"/proc/{target_pid_str}"):
            logger.debug(f"{target_pid_str} exists")
            name = self.get_window_name(target_pid_str)
            return target_pid_str, name
        
        return None, None
        
        return None, None

    def find_window_id_by_title(self, target_title):
        return None