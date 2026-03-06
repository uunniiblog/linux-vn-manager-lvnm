import time
import subprocess
import uuid
import tempfile
import os
import logging
from PySide6.QtDBus import QDBusInterface, QDBusConnection
from timetracker.system_utils import SystemUtils as TimeTrackUtils
from timetracker.desktop_utils_interface import DesktopUtilsInterface
from system_utils import SystemUtils as MainSysUtils

logger = logging.getLogger(__name__)

class KdeUtils(DesktopUtilsInterface):
    def __init__(self):
        self.bus = QDBusConnection.sessionBus()

        self.kwin_iface = QDBusInterface(
            "org.kde.KWin", 
            "/Scripting", 
            "org.kde.kwin.Scripting", 
            self.bus
        )

        if not self.kwin_iface.isValid():
            logger.error("Could not connect to KWin DBus interface")

        # Local cache to prevent redundant KWin calls
        self._window_cache = {} # Format: {id: {"name": str, "pid": str}}
        self._last_cache_update = 0
        self._cache_ttl = 1.0 # Cache valid for 1 second
        self.clean_env = MainSysUtils.get_clean_env()
        self.session_type = MainSysUtils.get_session_type()

    def _refresh_cache(self):
        """Fetches all window data from KWin in one single pass."""
        now = time.time()
        if now - self._last_cache_update < self._cache_ttl:
            return

        # JS that returns ID, PID, and Name for all windows at once
        js_code = """
        workspace.windowList().forEach(w => {
            print('DATA:' + w.internalId + '|' + w.pid + '|' + w.resourceClass + '|' + w.caption);
        });
        """

        raw_out = self._run_kwin_script(js_code)
        new_cache = {}

        for line in raw_out.splitlines():
            if "DATA:" in line:
                try:
                    # [id, pid, class, caption]
                    parts = line.split("DATA:")[-1].strip().split('|', 3)
                    if len(parts) == 4:
                        wid, pid, w_class, name = parts
                        new_cache[wid] = {"pid": pid, "class": w_class, "name": name}
                        logger.debug(f"KWin Cache -> WID: {wid} | PID: {pid} | CLASS: {w_class} | NAME: {name}")
                except: 
                    logger.error(f"Failed to parse KWin line: {line} Error: {e}")
                    continue

        self._window_cache = new_cache
        self._last_cache_update = now

    def _run_kwin_script(self, js_code):
        """ Helper to execute JS and get journal output."""
        script_name = f"tracker-{uuid.uuid4().hex[:8]}"
        start_time = "-2s"
        temp_path = None
        script_id = -1

        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tf:
                tf.write(js_code)
                temp_path = tf.name

            msg = self.kwin_iface.call("loadScript", temp_path, script_name)
            script_id = msg.arguments()[0]

            start_time = time.strftime('%Y-%m-%d %H:%M:%S')

            script_obj_path = f"/Scripting/Script{script_id}"
            script_run_iface = QDBusInterface(
                "org.kde.KWin", 
                script_obj_path, 
                "org.kde.kwin.Script", 
                self.bus
            )
            script_run_iface.call("run")

            # Short delay
            time.sleep(0.05)

            if self.session_type == "x11":
                unit = "plasma-kwin_x11.service"
            else:
                unit = "plasma-kwin_wayland.service"
            
            journaltext = subprocess.check_output([
                "journalctl", "--since", start_time, "--user",
                "-u", unit, "--output=cat", "-q" # -q for quiet/faster
            ], text=True, env=self.clean_env)

            # logger.debug(f"journaltext {journaltext}")

            return journaltext
        finally:
            if temp_path: os.remove(temp_path)
            if script_id != -1:
                try: self.kwin_iface.call("unloadScript", script_name)
                except: pass

    def get_active_window_id(self):
        """ Gets current KWin ID of focused window."""
        #logger.debug("get_active_window_id")
        js = "print('ACT:' + workspace.activeWindow.internalId);"
        out = self._run_kwin_script(js)
        for line in reversed(out.splitlines()):
            if "ACT:" in line: return line.split("ACT:")[-1].strip()
        return None

    def get_all_window_ids(self):
        """ Gets all windows ids"""
        #logger.debug("get_all_window_ids")
        self._refresh_cache()
        return list(self._window_cache.keys())

    def get_window_name(self, wid):
        """ Gets name of a Window ID"""
        #logger.debug("get_window_name")
        self._refresh_cache()
        return self._window_cache.get(wid, {}).get("name", "Unknown")

    def get_window_pid(self, wid):
        """ Gets pid of a Window ID"""
        #logger.debug("get_window_pid")
        self._refresh_cache()
        return self._window_cache.get(wid, {}).get("pid", "0")

    def find_window_id_by_title(self, target_title):
        """ Gets window ID of a window name."""
        # Escaping the title for JS
        safe_title = target_title.replace('"', '\\"')
        
        # KWin Script: Filters the window list and returns the internal ID
        script = f"""
        (function() {{
            var windows = workspace.windowList();
            var foundId = null;

            for (var i = 0; i < windows.length; i++) {{
                var w = windows[i];
                
                // Skip non-normal windows (panels, desktops, etc)
                if (!w.normalWindow) continue;
                
                // Check for exact caption match
                if (w.caption === "{safe_title}") {{
                    foundId = w.internalId;
                    break;
                }}
            }}
            print("SEARCH_RESULT:" + foundId);
        }})();
        """

        #logger.debug(f'find_window_id_by_title script: {script}')
        
        result = self._run_kwin_script(script)
        #logger.debug(f'find_window_id_by_title result {result}')
        for line in result.splitlines():
            if "SEARCH_RESULT:" in line:
                val = line.split("SEARCH_RESULT:")[1].strip()
                return val if val != "null" else None
        return None

    def find_window_by_pid(self, target_pid, target_process_path):
        """
        Returns (window_id, window_title) for a specific PID and process path.
        """
        self._refresh_cache()
        target_pid = str(target_pid)
        filename = os.path.basename(target_process_path).lower()
        
        # Games opened by wine or proton have one of these three classes given by kwin
        trusted_classes = ['gamescope', 'steam_app_default', filename]
        
        candidates = [
            (wid, info) for wid, info in self._window_cache.items()
            if info.get('class', '').lower() in trusted_classes 
            or info.get('class', '').lower().endswith('.exe')
        ]

        # Double check in our list in case of multiple games
        for wid, info in candidates:
            w_pid = str(info.get('pid'))
            
            # First check directly by pid
            if w_pid == target_pid:
                return wid, info.get('name')

            # Second check for gamescope/wrappers
            # If gamescope wrapper check by cmdline since gamescope passes the path of the game as argument
            w_cmdline = TimeTrackUtils.get_full_cmdline(w_pid)
            if filename in w_cmdline.lower():
                logger.debug(f"Validated {filename} inside wrapper {info.get('class')}")
                return wid, info.get('name')

        return None, None
