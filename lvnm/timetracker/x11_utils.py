import os
import logging
from Xlib import display, X, Xatom, error
from timetracker.system_utils import SystemUtils as TimeTrackUtils
from timetracker.desktop_utils_interface import DesktopUtilsInterface

logger = logging.getLogger(__name__)

class X11Utils(DesktopUtilsInterface):
    def __init__(self):
        try:
            self.display = display.Display()
            self.root = self.display.screen().root
        except Exception as e:
            logger.error(f"Could not connect to X server: {e}")
            raise

        # Pre-fetch X11 Atoms (properties) to avoid querying them by string every time
        self.NET_CLIENT_LIST = self.display.get_atom('_NET_CLIENT_LIST')
        self.NET_ACTIVE_WINDOW = self.display.get_atom('_NET_ACTIVE_WINDOW')
        self.NET_WM_NAME = self.display.get_atom('_NET_WM_NAME')
        self.NET_WM_PID = self.display.get_atom('_NET_WM_PID')
        self.UTF8_STRING = self.display.get_atom('UTF8_STRING')
        self.WM_CLASS = self.display.get_atom('WM_CLASS')

    def get_all_window_ids(self):
        """Gets all window IDs currently managed by the Window Manager."""
        try:
            prop = self.root.get_full_property(self.NET_CLIENT_LIST, X.AnyPropertyType)
            filtered_ids = []
            for wid in prop.value:
                try:
                    win = self._get_window_obj(wid)
                    geom = win.get_geometry()
                    if geom.width >= 100 and geom.height >= 100:
                        filtered_ids.append(wid)
                except error.XError as e:
                    logger.error(f"get_all_window_ids {e}")
                    continue
            
            return filtered_ids
        except error.XError as e:
            logger.error(f"Xlib error fetching client list: {e}")
        return []

    def get_active_window_id(self):
        """Gets the Window ID of the currently focused window."""
        try:
            prop = self.root.get_full_property(self.NET_ACTIVE_WINDOW, X.AnyPropertyType)
            if prop and prop.value and len(prop.value) > 0:
                return prop.value[0]
        except error.XError as e:
            logger.error(f"Xlib error fetching active window: {e}")
        return None

    def get_window_name(self, wid):
        """Gets the title of a specific Window ID."""
        try:
            win = self._get_window_obj(wid)
            
            # Use EWMH _NET_WM_NAME
            prop = win.get_full_property(self.NET_WM_NAME, self.UTF8_STRING)
            if prop and prop.value:
                logger.debug(f"_NET_WM_NAME {prop.value.decode('utf-8', 'ignore')}")
                return prop.value.decode('utf-8', 'ignore')
                
        except error.XError as e:
            logger.error(f"get_window_name - {e}")
            pass
        return "Unknown"

    def get_window_pid(self, wid):
        """Gets the PID of the process that created the window."""
        try:
            win = self._get_window_obj(wid)
            prop = win.get_full_property(self.NET_WM_PID, X.AnyPropertyType)
            if prop and prop.value and len(prop.value) > 0:
                return int(prop.value[0])
        except error.XError:
            pass
        return 0

    def find_window_by_pid(self, target_pid, target_process_path):
        """
        Returns (window_id, window_title) for a specific PID and process path.
        Includes handling for Gamescope/Wine/Proton wrappers.
        """
        target_pid = str(target_pid)
        filename = os.path.basename(target_process_path).lower()
        all_ids = self.get_all_window_ids()

        # Gather all candidates that match the class heuristics
        for wid in all_ids:
            w_name = self.get_window_name(wid)
            w_pid = str(self.get_window_pid(wid))
            logger.debug(f"{wid} - {w_pid} - {w_name}")

            # First check directly by pid
            if w_pid == target_pid:
                return wid, w_name

            # Second check for gamescope/wrappers via cmdline
            try:
                # If gamescope wrapper check by cmdline since gamescope passes the path of the game as argument
                w_cmdline = TimeTrackUtils.get_full_cmdline(w_pid)
                if filename in w_cmdline.lower():
                    logger.debug(f"Validated {filename} inside window {w_name}")
                    return wid, w_name
            except Exception as e:
                logger.error(f"Could not read cmdline for pid {w_pid}: {e}")
                pass

        return None, None


    def _get_window_class(self, wid):
        """Helper method to get the resource class like 'steam_app_default'"""
        try:
            win = self._get_window_obj(wid)
            prop = win.get_full_property(self.WM_CLASS, Xatom.STRING)
            if prop and prop.value:
                val = prop.value
                if isinstance(val, bytes):
                    val = val.decode('utf-8', 'ignore')
                # Split by null byte, filter out empty strings, return the last one (Class)
                parts = [p for p in val.split('\x00') if p]
                if parts:
                    return parts[-1]
        except error.XError:
            pass
        return ""

    def _get_window_obj(self, wid):
        """Helper to convert an integer ID to an Xlib Window object."""
        if isinstance(wid, int):
            return self.display.create_resource_object('window', wid)
        return wid