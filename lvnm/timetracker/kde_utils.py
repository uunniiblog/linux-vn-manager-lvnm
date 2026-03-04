import dbus
import time
import subprocess
import uuid
import tempfile
import os
import logging
from timetracker.system_utils import SystemUtils
from timetracker.desktop_utils_interface import DesktopUtilsInterface

logger = logging.getLogger(__name__)

class KdeUtils(DesktopUtilsInterface):
    def __init__(self):
        self.bus = dbus.SessionBus()
        self.kwin_scripting = self.bus.get_object("org.kde.KWin", "/Scripting")
        self.kwin_iface = dbus.Interface(self.kwin_scripting, "org.kde.kwin.Scripting")

        # Local cache to prevent redundant KWin calls
        self._window_cache = {} # Format: {id: {"name": str, "pid": str}}
        self._last_cache_update = 0
        self._cache_ttl = 1.0 # Cache valid for 1 second

    def _refresh_cache(self):
        """Fetches all window data from KWin in one single pass."""
        now = time.time()
        if now - self._last_cache_update < self._cache_ttl:
            return

        # JS that returns ID, PID, and Name for all windows at once
        js_code = """
        workspace.windowList().forEach(w => {
            print('DATA:' + w.internalId + '|' + w.pid + '|' + w.caption);
        });
        """

        raw_out = self._run_kwin_script(js_code)
        new_cache = {}

        for line in raw_out.splitlines():
            if "DATA:" in line:
                try:
                    parts = line.split("DATA:")[-1].split('|')
                    if len(parts) >= 3:
                        wid, pid, name = parts[0], parts[1], parts[2]
                        new_cache[wid] = {"pid": pid, "name": name}
                except: continue

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

            script_id = self.kwin_iface.loadScript(temp_path, script_name, signature='ss')
            start_time = time.strftime('%Y-%m-%d %H:%M:%S')

            run_obj = self.bus.get_object("org.kde.KWin", f"/Scripting/Script{script_id}")
            dbus.Interface(run_obj, "org.kde.kwin.Script").run()

            # Short delay
            time.sleep(0.05)

            return subprocess.check_output([
                "journalctl", "--since", start_time, "--user",
                "-u", "plasma-kwin_wayland.service",
                "--output=cat", "-q" # -q for quiet/faster
            ], text=True)
        finally:
            if temp_path: os.remove(temp_path)
            if script_id != -1:
                try: self.kwin_iface.unloadScript(script_name)
                except: pass

    def get_active_window_id(self):
        """ Gets current KWin ID of focused window."""
        js = "print('ACT:' + workspace.activeWindow.internalId);"
        out = self._run_kwin_script(js)
        for line in reversed(out.splitlines()):
            if "ACT:" in line: return line.split("ACT:")[-1].strip()
        return None

    def get_all_window_ids(self):
        """ Gets all windows ids"""
        self._refresh_cache()
        return list(self._window_cache.keys())

    def get_window_name(self, wid):
        """ Gets name of a Window ID"""
        self._refresh_cache()
        return self._window_cache.get(wid, {}).get("name", "Unknown")

    def get_window_pid(self, wid):
        """ Gets pid of a Window ID"""
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

    def find_window_by_pid(self, target_pid):
        """Returns (window_id, window_title) for a specific PID."""
        self._refresh_cache()
        target_pid = str(target_pid)
        
        for wid, info in self._window_cache.items():
            if str(info.get('pid')) == target_pid:
                return wid, info.get('name')

        # If it doesn't find window by pid search by process. Useful for gamescope
        target_exe = SystemUtils.get_exe_name_from_cmdline(target_pid)
        #logger.debug(f'target_exe {target_exe}')
        return self.find_window_by_process_name(target_exe)

        logger.error("No match found in find_window_by_pid")
        return None, None

    def find_window_by_process_name(self, target_exe):
        """
        TODO: improve this shit
        Finds the window by looking for the target_pid's presence 
        in the command lines of window-owning processes.
        """

        self._refresh_cache()
    
        # Filter valid PIDs from cache
        window_owner_pids = {
            str(info.get('pid')) for info in self._window_cache.values() 
            if info.get('pid') and str(info.get('pid')) not in ('0', '')
        }

        target_exe_lower = target_exe.lower()
        bridge_pid = None

        # logger.debug(f"Searching across {len(window_owner_pids)} window-owning PIDs: {window_owner_pids}")

        for w_pid in window_owner_pids:
            # logger.debug(f'w_pid {w_pid}')
            w_cmdline = SystemUtils.get_full_cmdline(w_pid)
            
            if target_exe_lower in w_cmdline.lower():
                bridge_pid = w_pid
                break 
        
        if bridge_pid:
            for wid, info in self._window_cache.items():
                if str(info.get('pid')) == bridge_pid:
                    logger.debug(f"Deep match: Found {target_exe} linked to Window '{info.get('name')}' (PID {bridge_pid})")
                    return wid, info.get('name')

        return None, None
