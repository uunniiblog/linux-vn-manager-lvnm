import logging
import ntpath
from timetracker.desktop_utils_interface import DesktopUtilsInterface
from timetracker.win32_api import Win32Api

logger = logging.getLogger(__name__)

class WindowsUtils(DesktopUtilsInterface):
    """Native Win32 window discovery used by automatic and manual tracking."""

    MINIMUM_WINDOW_SIZE = 100

    def __init__(self, api=None):
        self.api = api or Win32Api()

    def get_all_window_ids(self):
        window_ids = []
        for wid in self.api.enum_windows():
            try:
                if not self.api.is_window_visible(wid):
                    continue
                if self.api.is_window_cloaked(wid):
                    continue
                if not self.api.get_window_title(wid):
                    continue
                rect = self.api.get_window_rect(wid)
                if rect is None:
                    continue
                left, top, right, bottom = rect
                if (
                    right - left < self.MINIMUM_WINDOW_SIZE
                    or bottom - top < self.MINIMUM_WINDOW_SIZE
                ):
                    continue
                window_ids.append(wid)
            except OSError as error:
                logger.debug(f"Could not inspect Windows window {wid}: {error}")
        return window_ids

    def get_window_name(self, wid):
        return self.api.get_window_title(int(wid)) or "Unknown"

    def get_window_pid(self, wid):
        return self.api.get_window_pid(int(wid))

    def get_active_window_id(self):
        return self.api.get_foreground_window()

    def find_window_by_pid(self, target_pid, target_process_path):
        if isinstance(target_pid, (list, set, tuple)):
            target_pids = {int(pid) for pid in target_pid if str(pid).isdigit()}
        else:
            target_pids = {int(target_pid)} if str(target_pid).isdigit() else set()

        window_ids = self.get_all_window_ids()
        for wid in window_ids:
            if self.get_window_pid(wid) in target_pids:
                return wid, self.get_window_name(wid)

        # Some launchers replace themselves or create a child process. Fall
        # back to comparing the executable behind each top-level window.
        target_name = ntpath.basename(str(target_process_path)).casefold()
        if target_name:
            for wid in window_ids:
                pid = self.get_window_pid(wid)
                image_path = self.api.get_process_image_path(pid)
                if ntpath.basename(image_path).casefold() == target_name:
                    return wid, self.get_window_name(wid)

        return None, None
