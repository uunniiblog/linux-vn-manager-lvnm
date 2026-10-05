"""Native Windows process discovery and idle detection for time tracking."""
import logging
import ntpath
import os
from timetracker.win32_api import Win32Api

logger = logging.getLogger(__name__)

class WindowsSystemUtils:
    _api = None
    _afk_timeout_seconds = 0

    @classmethod
    def _get_api(cls):
        if cls._api is None:
            cls._api = Win32Api()
        return cls._api

    @staticmethod
    def is_wine_or_proton(_pid):
        return False

    @staticmethod
    def get_window_list(utils, only_show_wine=False):
        if not utils or only_show_wine:
            return []

        windows = []
        for wid in utils.get_all_window_ids():
            try:
                title = utils.get_window_name(wid)
                if title:
                    windows.append((title, wid))
            except OSError:
                continue
        return windows

    @classmethod
    def get_pids_by_name(cls, process_name, cmdline_hint=None):
        target_name = ntpath.basename(str(process_name)).casefold()
        if not target_name:
            return []

        target_path = cls._normalise_path(cmdline_hint) if cmdline_hint else ""
        matches = []
        try:
            processes = cls._get_api().enum_processes()
        except OSError as error:
            logger.error(f"Could not enumerate Windows processes: {error}")
            return []

        for process in processes:
            if str(process.get("name", "")).casefold() != target_name:
                continue
            pid = int(process.get("pid") or 0)
            if not pid or pid == os.getpid():
                continue
            if target_path:
                image_path = cls._normalise_path(
                    cls._get_api().get_process_image_path(pid)
                )
                if image_path and image_path != target_path:
                    continue
            matches.append(str(pid))
        return matches

    @classmethod
    def get_pid_by_name(cls, process_name):
        pids = cls.get_pids_by_name(process_name)
        return pids[-1] if pids else None

    @classmethod
    def get_process_name(cls, pid):
        numeric_pid = int(pid)
        image_path = cls._get_api().get_process_image_path(numeric_pid)
        if image_path:
            return ntpath.basename(image_path)

        try:
            for process in cls._get_api().enum_processes():
                if int(process.get("pid") or 0) == numeric_pid:
                    return str(process.get("name") or "Unknown")
        except OSError:
            pass
        return "Unknown"

    @classmethod
    def get_app_name_from_pid(cls, pid):
        return ntpath.basename(cls.get_process_name(pid))

    @classmethod
    def get_full_cmdline(cls, pid):
        return cls._get_api().get_process_image_path(int(pid))

    @staticmethod
    def get_process_environ(_pid):
        return ""

    @staticmethod
    def is_swayidle_installed():
        return False

    @classmethod
    def start_afk_daemon(cls, timeout_seconds):
        cls._afk_timeout_seconds = max(0, int(timeout_seconds))
        return None

    @classmethod
    def stop_afk_daemon(cls):
        cls._afk_timeout_seconds = 0

    @classmethod
    def get_afk_status(cls):
        if cls._afk_timeout_seconds <= 0:
            return False, 0
        try:
            idle_seconds = int(cls._get_api().get_idle_seconds())
        except OSError as error:
            logger.error(f"Could not query Windows idle time: {error}")
            return False, 0
        if idle_seconds < cls._afk_timeout_seconds:
            return False, 0
        return True, idle_seconds

    @staticmethod
    def _normalise_path(path):
        if not path:
            return ""
        return ntpath.normcase(ntpath.normpath(str(path)))
