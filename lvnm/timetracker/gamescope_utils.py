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
        if isinstance(target_pid, (list, set, tuple)):
            candidates = [str(p) for p in target_pid]
        else:
            candidates = [str(target_pid)]
        
        # Check if the process folder exists in /proc       
        for pid_str in candidates:
            if os.path.exists(f"/proc/{pid_str}"):
                logger.debug(f"{pid_str} exists")
                name = self.get_window_name(pid_str)
                return pid_str, name
        
        return None, None        