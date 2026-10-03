import json
import logging
import os
import threading
import time
from PySide6.QtDBus import QDBus, QDBusConnection, QDBusMessage
from timetracker.desktop_utils_interface import DesktopUtilsInterface
from timetracker.system_utils import SystemUtils as TimeTrackUtils

logger = logging.getLogger(__name__)

class GnomeUtils(DesktopUtilsInterface):
    """GNOME Shell window integration supplied by the LVNM shell extension."""

    SERVICE_NAME = "io.github.uunniiblog.lvnm.GnomeWindowTracker"
    OBJECT_PATH = "/io/github/uunniiblog/lvnm/GnomeWindowTracker"
    INTERFACE_NAME = SERVICE_NAME
    PROTOCOL_VERSION = 1

    def __init__(self, bus=None, cache_ttl=0.2):
        self.bus = bus or QDBusConnection.sessionBus()
        self._cache_ttl = cache_ttl
        self._cache_timestamp = 0.0
        self._windows = {}
        self._active_window_id = None
        self._lock = threading.RLock()

        if not self.bus.isConnected():
            raise RuntimeError("GNOME window tracker cannot connect to the session D-Bus")

        version = self._call("Ping")
        if version is None:
            raise RuntimeError("LVNM GNOME Shell extension is not installed, enabled, or reachable")

        try:
            version = int(version)
        except (TypeError, ValueError) as error:
            raise RuntimeError("LVNM GNOME Shell extension returned an invalid version") from error

        if version != self.PROTOCOL_VERSION:
            raise RuntimeError(f"Unsupported LVNM GNOME extension protocol {version}; expected {self.PROTOCOL_VERSION}")

        if not self._refresh(force=True):
            raise RuntimeError("LVNM GNOME Shell extension returned no window snapshot")

    def _call(self, method):
        message = QDBusMessage.createMethodCall(
            self.SERVICE_NAME,
            self.OBJECT_PATH,
            self.INTERFACE_NAME,
            method,
        )
        reply = self.bus.call(message, QDBus.CallMode.Block, 1500)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            logger.debug(f"GNOME extension D-Bus call {method} failed: {reply.errorMessage()}")
            return None

        arguments = reply.arguments()
        return arguments[0] if arguments else None

    @staticmethod
    def _decode_snapshot(raw_snapshot):
        payload = json.loads(raw_snapshot)
        if payload.get("version") != GnomeUtils.PROTOCOL_VERSION:
            raise ValueError("GNOME extension snapshot has an unsupported protocol version")

        raw_windows = payload.get("windows", {})
        if not isinstance(raw_windows, dict):
            raise ValueError("GNOME extension snapshot has an invalid windows field")

        windows = {}
        for raw_id, raw_info in raw_windows.items():
            if not isinstance(raw_info, dict):
                continue

            wid = str(raw_id)
            windows[wid] = {
                "pid": int(raw_info.get("pid") or 0),
                "name": str(raw_info.get("title") or "Unknown"),
                "class": str(raw_info.get("wm_class") or ""),
                "app_id": str(raw_info.get("app_id") or ""),
                "client_type": int(raw_info.get("client_type") or 0),
            }

        active_id = payload.get("active_window_id")
        return windows, str(active_id) if active_id is not None else None

    def _refresh(self, force=False):
        now = time.monotonic()
        with self._lock:
            if not force and now - self._cache_timestamp < self._cache_ttl:
                return True

        raw_snapshot = self._call("GetSnapshot")
        if not isinstance(raw_snapshot, str):
            with self._lock:
                self._windows = {}
                self._active_window_id = None
                self._cache_timestamp = now
            return False

        try:
            windows, active_id = self._decode_snapshot(raw_snapshot)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            logger.error(f"Could not decode GNOME window snapshot: {error}")
            with self._lock:
                self._windows = {}
                self._active_window_id = None
                self._cache_timestamp = now
            return False

        with self._lock:
            self._windows = windows
            self._active_window_id = active_id
            self._cache_timestamp = now
        return True

    def _window(self, wid):
        self._refresh()
        with self._lock:
            return dict(self._windows.get(str(wid), {}))

    def get_all_window_ids(self):
        self._refresh()
        with self._lock:
            return list(self._windows.keys())

    def get_window_name(self, wid):
        return self._window(wid).get("name", "Unknown")

    def get_window_pid(self, wid):
        return self._window(wid).get("pid", 0)

    def get_active_window_id(self):
        self._refresh()
        with self._lock:
            return self._active_window_id

    def find_window_by_pid(self, target_pid, target_process_path):
        self._refresh(force=True)
        with self._lock:
            windows = {wid: dict(info) for wid, info in self._windows.items()}

        if isinstance(target_pid, (list, set, tuple)):
            target_pids = {str(pid) for pid in target_pid}
        else:
            target_pids = {str(target_pid)}

        filename = os.path.basename(target_process_path).lower()

        for wid, info in windows.items():
            logger.debug(f"GNOME Window -> WID: {wid} | PID: {info.get('pid', 0)} | CLASS: {info.get('class', '')} | APP_ID: {info.get('app_id', '')} | NAME: {info.get('name', '')}")
            if str(info.get("pid")) in target_pids:
                return wid, info.get("name")

        trusted_classes = {"gamescope", "steam_app_default", filename}
        candidates = []
        for wid, info in windows.items():
            window_class = info.get("class", "").lower()
            app_id = info.get("app_id", "").lower()
            if (
                window_class in trusted_classes
                or window_class.startswith("steam_app_")
                or window_class.endswith(".exe")
                or filename in app_id
            ):
                candidates.append((wid, info))

        for wid, info in candidates:
            window_pid = str(info.get("pid", 0))
            command_line = TimeTrackUtils.get_full_cmdline(window_pid)
            if filename in command_line.lower():
                logger.debug(f"Validated {filename} inside GNOME window wrapper")
                return wid, info.get("name")

        return None, None

    def shutdown(self):
        """Drop local state; the persistent GNOME extension remains enabled."""
        with self._lock:
            self._windows = {}
            self._active_window_id = None
            self._cache_timestamp = 0.0
