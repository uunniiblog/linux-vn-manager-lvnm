import sys
import time
import uuid
import tempfile
import os
import atexit
import signal
import threading
import logging
from PySide6.QtDBus import QDBusInterface, QDBusConnection
from PySide6.QtCore import QObject, Slot, QCoreApplication
from timetracker.system_utils import SystemUtils as TimeTrackUtils
from timetracker.desktop_utils_interface import DesktopUtilsInterface

logger = logging.getLogger(__name__)

class KwinNotifier(QObject):
    """Receives push events from the persistent KWin script via DBus."""
    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self.active_window_id = None
        self.window_cache = {}  # {id: {"pid":, "class":, "name":}}

    def process_events(self):
        """Flushes the Qt event queue so pending DBus calls are executed."""
        # Force pending Qt signals sitting in the DBus event queue to execute synchronously.
        QCoreApplication.processEvents()

    @Slot(str)
    def ActiveWindowChanged(self, window_id):
        """DBus slot triggered when KWin changes focus to a different window."""
        with self._lock:
            # Empty string from KWin signifies no window is currently focused.
            self.active_window_id = window_id or None
            name = self.window_cache.get(window_id, {}).get("name", "Unknown")
            logger.debug(f"[KWinScript] ActiveWindowChanged window_id={window_id} name={name}")

    @Slot(str, str, str, str)
    def WindowAdded(self, wid, pid, w_class, name):
        """DBus slot triggered when a new window is created and meets size criteria."""
        logger.debug(f"[KWinScript] WindowAdded wid={wid} pid={pid} class={w_class} name={name}")
        with self._lock:
            self.window_cache[wid] = {"pid": pid, "class": w_class, "name": name}

    @Slot(str)
    def WindowRemoved(self, wid):
        """DBus slot triggered when a window is closed in KWin."""
        with self._lock:
            # Safely remove window metadata without throwing KeyError if missing.
            info = self.window_cache.pop(wid, None)
            name = info.get("name", "Unknown") if info else "Unknown"
            logger.debug(f"[KWinScript] WindowRemoved window_id={wid} name={name}")

    @Slot(str, str)
    def WindowCaptionChanged(self, wid, name):
        """DBus slot triggered when an existing window updates its title."""
        logger.debug(f"[KWinScript] WindowCaptionChanged wid={wid} name={name}")
        with self._lock:
            if wid in self.window_cache:
                self.window_cache[wid]["name"] = name

    def get_active(self):
        """Retrieves the currently active window ID safely after processing pending events."""
        self.process_events()
        with self._lock:
            return self.active_window_id

    def get_all_ids(self):
        """Logs all cached window states and returns a list of active window IDs."""
        self.process_events()
        with self._lock:
            return list(self.window_cache.keys())

    def get_window(self, wid):
        """Returns metadata dictionary (PID, Class, Name) for a specific window ID."""
        self.process_events()
        with self._lock:
            # Return a copy to avoid external code modifying internal cache state.
            return dict(self.window_cache.get(wid, {}))

    def snapshot(self):
        """Generates a thread-safe shallow copy of the full window cache."""
        self.process_events()
        with self._lock:
            return dict(self.window_cache)


"""
================================================================================
KWIN JAVASCRIPT SCRIPT
================================================================================
This script is injected directly into KDE's KWin Compositor via DBus Scripting.
It listens natively inside KWin workspace events and sends DBus signals back
to our Python application in real-time.

What it does:
1. Filters out small system popups/tooltips (width/height < 100px).
2. Enumerates existing open windows upon startup and reports them back.
3. Listens to window creation (windowAdded), destruction (windowRemoved),
   focus change (windowActivated), and title changes (captionChanged).
================================================================================
"""
_KWIN_SCRIPT_JS = """
print("TIMETRACKER_SCRIPT_ALIVE");

function report(msg) {
    print("[TIMETRACKER_JS] " + msg);
}

function emitAdded(w) {
    if (!w) return;
    try {
        var wWidth = w.frameGeometry ? w.frameGeometry.width : (w.width || 0);
        var wHeight = w.frameGeometry ? w.frameGeometry.height : (w.height || 0);
        if (wWidth < 100 || wHeight < 100) return;

        var windowId = w.internalId ? ("" + w.internalId) : "";
        var processId = w.pid ? ("" + w.pid) : "";
        var resClass = w.resourceClass ? String(w.resourceClass) : "";
        var cap = w.caption ? String(w.caption) : "";

        callDBus("%(service)s", "%(path)s", "", "WindowAdded", windowId, processId, resClass, cap);
    } catch (e) {
        report("ERROR in emitAdded: " + e);
    }
    
    try {
        w.captionChanged.connect(function() {
            var windowId = w.internalId ? ("" + w.internalId) : "";
            var cap = w.caption ? String(w.caption) : "";
            callDBus("%(service)s", "%(path)s", "", "WindowCaptionChanged", windowId, cap);
        });
    } catch (e) {}
}

try {
    var winList = (typeof workspace.windowList === "function") ? workspace.windowList() : workspace.windows;
    if (winList) {
        report("Initial window count: " + winList.length);
        for (var i = 0; i < winList.length; i++) {
            emitAdded(winList[i]);
        }
    } else {
        report("Could not retrieve window list from workspace");
    }
} catch (e) {
    report("FATAL ERROR initial windowList enumeration: " + e);
}

try {
    workspace.windowAdded.connect(function(w) {
        report("windowAdded event fired");
        emitAdded(w);
    });
} catch (e) {
    report("ERROR connecting windowAdded: " + e);
}

try {
    workspace.windowRemoved.connect(function(w) {
        if (!w) return;
        var windowId = w.internalId ? ("" + w.internalId) : "";
        callDBus("%(service)s", "%(path)s", "", "WindowRemoved", windowId);
    });
} catch (e) {
    report("ERROR connecting windowRemoved: " + e);
}

try {
    workspace.windowActivated.connect(function(w) {
        var windowId = (w && w.internalId) ? ("" + w.internalId) : "";
        callDBus("%(service)s", "%(path)s", "", "ActiveWindowChanged", windowId);
    });
} catch (e) {
    report("ERROR connecting windowActivated: " + e);
}
"""

class KdeUtils(DesktopUtilsInterface):
    _instance = None
    _instance_lock = threading.Lock()

    # Fixed script identifier
    SCRIPT_NAME = "timetracker-live-notifier"

    def __new__(cls, *args, **kwargs):
        """Enforces thread-safe Singleton instantiation pattern."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        """Sets up DBus connections, registers signals, and injects the KWin tracker."""
        if self._initialized:
            logger.debug("KdeUtils singleton already initialized -- reusing existing instance")
            return
        self._initialized = True

        self.bus = QDBusConnection.sessionBus()

        self.kwin_iface = QDBusInterface(
            "org.kde.KWin",
            "/Scripting",
            "org.kde.kwin.Scripting",
            self.bus
        )

        if not self.kwin_iface.isValid():
            logger.error("Could not connect to KWin DBus interface")

        unique_suffix = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
        self._service_name = f"org.timetracker.Notifier{unique_suffix}"
        self._object_path = f"/Notifier{unique_suffix}"
        self.notifier = KwinNotifier()
        self._script_name = self.SCRIPT_NAME
        self._script_id = -1
        self._started = False

        self.start_event_stream()

        atexit.register(self.shutdown)
        try:
            signal.signal(signal.SIGTERM, lambda signum, frame: self.handle_exit_signal())
            signal.signal(signal.SIGINT, lambda signum, frame: self.handle_exit_signal())
        except (ValueError, RuntimeError):
            pass

    def start_event_stream(self):
        """Unloads zombie scripts, registers Python DBus endpoints, and runs JS script in KWin."""
        if not self.bus.isConnected():
            logger.error("Session DBus is not connected at all")
            return

        # Explicitly unload any prior running instance of this script just in case
        try:
            self.kwin_iface.call("unloadScript", self.SCRIPT_NAME)
        except Exception:
            pass

        registered_service = self.bus.registerService(self._service_name)
        logger.debug(f"registerService({self._service_name}) -> {registered_service}")

        if not registered_service:
            logger.error(f"Failed to register DBus service {self._service_name}: {self.bus.lastError().message()}")
            return

        registered_obj = self.bus.registerObject(self._object_path, self.notifier, QDBusConnection.ExportAllSlots)
        logger.debug(f"registerObject({self._object_path}) -> {registered_obj}")

        if not registered_obj:
            logger.error(f"Failed to register {self._object_path} object: {self.bus.lastError().message()}")
            return

        js_code = _KWIN_SCRIPT_JS % {"service": self._service_name, "path": self._object_path}
        temp_path = None

        try:
            # Write script string to temporary file so KWin DBus loadScript interface can read it.
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as tf:
                tf.write(js_code)
                temp_path = tf.name

            logger.debug(f"KWin script written to {temp_path}")
            msg = self.kwin_iface.call("loadScript", temp_path, self.SCRIPT_NAME)

            if msg.type() == msg.MessageType.ErrorMessage:
                logger.error(f"loadScript DBus call failed: {msg.errorMessage()}")
                return

            args = msg.arguments()
            if not args:
                logger.error(f"loadScript returned no arguments: {msg}")
                return

            # Retrieve script ID assigned by KWin compositor to execute run method on it.
            self._script_id = args[0]
            logger.debug(f"loadScript returned script_id={self._script_id}")

            if self._script_id < 0:
                logger.error("KWin returned invalid script_id -- load failed")
                return

            script_obj_path = f"/Scripting/Script{self._script_id}"
            script_run_iface = QDBusInterface("org.kde.KWin", script_obj_path, "org.kde.kwin.Script", self.bus
            )
            if not script_run_iface.isValid():
                logger.error(f"Script interface at {script_obj_path} is not valid")
                return

            run_msg = script_run_iface.call("run")
            if run_msg.type() == run_msg.MessageType.ErrorMessage:
                logger.error(f"Script.run() failed: {run_msg.errorMessage()}")
                return

            self._started = True
            logger.debug(f"Live window tracking script loaded and running ({self.SCRIPT_NAME})")
        except Exception as e:
            logger.error(f"Exception starting live window tracking script: {e}", exc_info=True)
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def handle_exit_signal(self):
        #self.shutdown()
        sys.exit(0)
    
    def shutdown(self):
        """Stops KWin script execution and unregisters DBus endpoints during exit."""
        if self._started and self._script_name:
            try:
                self.kwin_iface.call("unloadScript", self.SCRIPT_NAME)
                logger.info(f"Unloaded live window tracking script ({self._script_name})")
            except Exception as e:
                logger.error(f"Failed to unload KWin script cleanly: {e}")
            self._started = False

        try:
            self.bus.unregisterObject(self._object_path)
            self.bus.unregisterService(self._service_name)
        except Exception:
            pass

    def __del__(self):
        """Garbage collection destructor ensuring clean shutdown on delete."""
        try:
            self.shutdown()
        except Exception:
            pass

    def get_active_window_id(self):
        """Public method wrapper returning the current active window ID."""
        return self.notifier.get_active()

    def get_all_window_ids(self):
        """Public method wrapper returning all open window IDs."""
        return self.notifier.get_all_ids()

    def get_window_name(self, wid):
        """Public method wrapper returning window title/caption by ID."""
        return self.notifier.get_window(wid).get("name", "Unknown")

    def get_window_pid(self, wid):
        """Public method wrapper returning owner process ID (PID) by window ID."""
        return self.notifier.get_window(wid).get("pid", "0")

    def find_window_by_pid(self, target_pid, target_process_path):
        """Finds a matching window ID using process PID and process executable path."""
        cache = self.notifier.snapshot()
        for wid, info in cache.items():
            logger.debug(f"KWin Cache -> WID: {wid} | PID: {info.get('pid', '')} | CLASS: {info.get('class', '')} | NAME: {info.get('name', '')}")

        # Handle single PIDs or lists
        if isinstance(target_pid, (list, set, tuple)):
            target_pids = {str(p) for p in target_pid}
        else:
            target_pids = {str(target_pid)}

        filename = os.path.basename(target_process_path).lower()

        # Check direct PID matches against our active KWin window cache.
        for wid, info in cache.items():
            if str(info.get('pid')) in target_pids:
                logger.debug(f"Validated {filename} Found window by direct pid.")
                return wid, info.get('name')

        trusted_classes = ['gamescope', 'steam_app_default', filename]
        candidates = [
            (wid, info) for wid, info in cache.items()
            if info.get('class', '').lower() in trusted_classes
            or info.get('class', '').lower().startswith('steam_app_')
            or info.get('class', '').lower().endswith('.exe')
        ]

        # Parse full process command line to handle weird case scenarios.
        for wid, info in candidates:
            w_pid = str(info.get('pid'))
            w_cmdline = TimeTrackUtils.get_full_cmdline(w_pid)
            if filename in w_cmdline.lower():
                logger.debug(f"Validated {filename} inside wrapper {info.get('class')}")
                return wid, info.get('name')

        return None, None