import atexit
import json
import logging
import os
import socket
import threading
import time
from pathlib import Path
from timetracker.desktop_utils_interface import DesktopUtilsInterface
from timetracker.system_utils import SystemUtils as TimeTrackUtils

logger = logging.getLogger(__name__)

class HyprlandUtils(DesktopUtilsInterface):
    """Native Hyprland window tracking through the compositor IPC sockets."""

    _instance = None
    _instance_lock = threading.Lock()
    RECONNECT_DELAY = 1.0
    SOCKET_TIMEOUT = 1.5
    MAX_REPLY_SIZE = 16 * 1024 * 1024

    def __new__(cls, *args, **kwargs):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, socket_dir=None, requester=None, start_listener=True, cache_ttl=0.5):
        if self._initialized:
            return

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._event_socket = None
        self._event_thread = None
        self._events_connected = False
        self._event_error_logged = False
        self._windows = {}
        self._active_window_id = None
        self._cache_timestamp = 0.0
        self._cache_ttl = cache_ttl
        self._requester = requester

        try:
            self._socket_dir = Path(socket_dir) if socket_dir else self._resolve_socket_dir()
            self._command_socket_path = self._socket_dir / ".socket.sock"
            self._event_socket_path = self._socket_dir / ".socket2.sock"

            if requester is None and not self._command_socket_path.is_socket():
                raise RuntimeError(f"Hyprland IPC command socket was not found: {self._command_socket_path}")

            if not self._refresh_windows(force=True):
                raise RuntimeError("Hyprland IPC returned no valid window snapshot")
            if not self._refresh_active():
                raise RuntimeError("Hyprland IPC returned no valid active-window snapshot")

            self._initialized = True
            if start_listener:
                self._event_thread = threading.Thread(
                    target=self._event_loop,
                    daemon=True,
                    name="lvnm-hyprland-events",
                )
                self._event_thread.start()
            atexit.register(self.shutdown)
        except Exception:
            self._release_singleton()
            raise

    @staticmethod
    def _resolve_socket_dir():
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        instance_signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        if not runtime_dir or not instance_signature:
            raise RuntimeError("Hyprland IPC environment variables are unavailable")
        return Path(runtime_dir) / "hypr" / instance_signature

    @staticmethod
    def _normalize_address(address):
        value = str(address or "").strip().lower()
        if not value or value in {"0", "0x0"}:
            return None
        return value if value.startswith("0x") else f"0x{value}"

    def _request_json(self, command):
        if self._requester is not None:
            response = self._requester(command)
            return json.loads(response) if isinstance(response, (str, bytes, bytearray)) else response

        chunks = []
        total_size = 0
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as ipc_socket:
            ipc_socket.settimeout(self.SOCKET_TIMEOUT)
            ipc_socket.connect(str(self._command_socket_path))
            ipc_socket.sendall(f"j/{command}".encode("utf-8"))

            while True:
                chunk = ipc_socket.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                total_size += len(chunk)
                if total_size > self.MAX_REPLY_SIZE:
                    raise RuntimeError("Hyprland IPC reply exceeded the maximum supported size")
                try:
                    return json.loads(b"".join(chunks).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue

        if not chunks:
            raise RuntimeError(f"Hyprland IPC returned an empty response for {command}")
        return json.loads(b"".join(chunks).decode("utf-8"))

    @staticmethod
    def _decode_windows(payload):
        if not isinstance(payload, list):
            raise ValueError("Hyprland clients response is not a list")

        windows = {}
        for client in payload:
            if not isinstance(client, dict) or not client.get("mapped", True):
                continue

            size = client.get("size") or [0, 0]
            if not isinstance(size, list) or len(size) < 2:
                continue
            if int(size[0] or 0) < 100 or int(size[1] or 0) < 100:
                continue

            wid = HyprlandUtils._normalize_address(client.get("address"))
            if not wid:
                continue

            windows[wid] = {
                "pid": int(client.get("pid") or 0),
                "name": str(client.get("title") or client.get("initialTitle") or "Unknown"),
                "class": str(client.get("class") or ""),
                "initial_class": str(client.get("initialClass") or ""),
                "xwayland": bool(client.get("xwayland", False)),
            }
        return windows

    def _refresh_windows(self, force=False):
        now = time.monotonic()
        with self._lock:
            if not force and now - self._cache_timestamp < self._cache_ttl:
                return True

        try:
            windows = self._decode_windows(self._request_json("clients"))
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
            logger.error(f"Could not refresh Hyprland window snapshot: {error}")
            with self._lock:
                self._windows = {}
                self._cache_timestamp = now
            return False

        with self._lock:
            self._windows = windows
            self._cache_timestamp = now
        return True

    def _refresh_active(self):
        try:
            payload = self._request_json("activewindow")
            if not isinstance(payload, dict):
                raise ValueError("Hyprland activewindow response is not an object")
            active_id = self._normalize_address(payload.get("address"))
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
            logger.error(f"Could not refresh Hyprland active window: {error}")
            with self._lock:
                self._active_window_id = None
            return False

        with self._lock:
            self._active_window_id = active_id
        return True

    def _event_loop(self):
        while not self._stop_event.is_set():
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as event_socket:
                    event_socket.settimeout(0.5)
                    event_socket.connect(str(self._event_socket_path))
                    with self._lock:
                        self._event_socket = event_socket
                        self._events_connected = True
                        self._event_error_logged = False

                    # Connect first and then snapshot so events occurring during
                    # the refresh remain queued and are applied afterwards.
                    self._refresh_windows(force=True)
                    self._refresh_active()
                    self._consume_events(event_socket)
            except OSError as error:
                if not self._stop_event.is_set():
                    if self._event_error_logged:
                        logger.debug(f"Hyprland event socket is still unavailable: {error}")
                    else:
                        logger.warning(f"Hyprland event socket disconnected: {error}")
                        self._event_error_logged = True
            finally:
                with self._lock:
                    self._event_socket = None
                    self._events_connected = False

            self._stop_event.wait(self.RECONNECT_DELAY)

    def _consume_events(self, event_socket):
        buffer = b""
        while not self._stop_event.is_set():
            try:
                chunk = event_socket.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                return

            buffer += chunk
            while b"\n" in buffer:
                raw_line, buffer = buffer.split(b"\n", 1)
                self._handle_event(raw_line.decode("utf-8", errors="replace"))

    def _handle_event(self, line):
        event_name, separator, data = line.partition(">>")
        if not separator:
            return

        if event_name == "activewindowv2":
            with self._lock:
                self._active_window_id = self._normalize_address(data)
        elif event_name == "closewindow":
            wid = self._normalize_address(data)
            with self._lock:
                self._windows.pop(wid, None)
                if self._active_window_id == wid:
                    self._active_window_id = None
        elif event_name in {"openwindow", "windowtitle", "windowtitlev2"}:
            self._refresh_windows(force=True)

    def _ensure_windows_current(self):
        with self._lock:
            events_connected = self._events_connected
        if not events_connected:
            self._refresh_windows()

    def get_all_window_ids(self):
        self._ensure_windows_current()
        with self._lock:
            return list(self._windows.keys())

    def get_window_name(self, wid):
        self._ensure_windows_current()
        wid = self._normalize_address(wid)
        with self._lock:
            return self._windows.get(wid, {}).get("name", "Unknown")

    def get_window_pid(self, wid):
        self._ensure_windows_current()
        wid = self._normalize_address(wid)
        with self._lock:
            return self._windows.get(wid, {}).get("pid", 0)

    def get_active_window_id(self):
        with self._lock:
            events_connected = self._events_connected
        if not events_connected:
            self._refresh_active()
        with self._lock:
            return self._active_window_id

    def find_window_by_pid(self, target_pid, target_process_path):
        self._refresh_windows(force=True)
        with self._lock:
            windows = {wid: dict(info) for wid, info in self._windows.items()}

        if isinstance(target_pid, (list, set, tuple)):
            target_pids = {str(pid) for pid in target_pid}
        else:
            target_pids = {str(target_pid)}

        filename = os.path.basename(target_process_path).lower()
        for wid, info in windows.items():
            logger.debug(f"Hyprland Window -> WID: {wid} | PID: {info.get('pid', 0)} | CLASS: {info.get('class', '')} | INITIAL_CLASS: {info.get('initial_class', '')} | NAME: {info.get('name', '')}")
            if str(info.get("pid")) in target_pids:
                return wid, info.get("name")

        trusted_classes = {"gamescope", "steam_app_default", filename}
        candidates = []
        for wid, info in windows.items():
            window_classes = {
                info.get("class", "").lower(),
                info.get("initial_class", "").lower(),
            }
            if any(
                window_class in trusted_classes
                or window_class.startswith("steam_app_")
                or window_class.endswith(".exe")
                for window_class in window_classes
            ):
                candidates.append((wid, info))

        for wid, info in candidates:
            command_line = TimeTrackUtils.get_full_cmdline(str(info.get("pid", 0)))
            if filename in command_line.lower():
                logger.debug(f"Validated {filename} inside Hyprland window wrapper")
                return wid, info.get("name")

        return None, None

    def shutdown(self):
        if not getattr(self, "_initialized", False):
            return

        self._stop_event.set()
        with self._lock:
            event_socket = self._event_socket
        if event_socket is not None:
            try:
                event_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                event_socket.close()
            except OSError:
                pass

        event_thread = self._event_thread
        if event_thread and event_thread.is_alive() and event_thread is not threading.current_thread():
            event_thread.join(timeout=2)

        with self._lock:
            self._windows = {}
            self._active_window_id = None
            self._events_connected = False
        self._initialized = False
        self._release_singleton()

    def _release_singleton(self):
        with type(self)._instance_lock:
            if type(self)._instance is self:
                type(self)._instance = None

    def __del__(self):
        try:
            self.shutdown()
        except Exception:
            pass
