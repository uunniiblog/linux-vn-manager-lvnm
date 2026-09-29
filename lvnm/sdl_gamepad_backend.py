
import ctypes
import ctypes.util
import logging
from dataclasses import dataclass
from PySide6.QtCore import QObject, QTimer, Signal

logger = logging.getLogger(__name__)

SDL_INIT_GAMEPAD = 0x00002000
AXIS_THRESHOLD = 16_000

@dataclass(frozen=True)
class _ButtonBinding:
    index: int
    action: str
    repeat: bool = False

BUTTON_BINDINGS = (
    _ButtonBinding(0, "accept"),
    _ButtonBinding(1, "back"),
    _ButtonBinding(2, "primary_action"),
    _ButtonBinding(3, "secondary_action"),
    _ButtonBinding(4, "view"),
    _ButtonBinding(6, "menu"),
    _ButtonBinding(9, "previous_tab"),
    _ButtonBinding(10, "next_tab"),
    _ButtonBinding(11, "navigate_up", True),
    _ButtonBinding(12, "navigate_down", True),
    _ButtonBinding(13, "navigate_left", True),
    _ButtonBinding(14, "navigate_right", True),
)

class SDLGamepadBackend(QObject):
    """Poll one SDL gamepad and emit semantic, UI-friendly actions."""

    action_pressed = Signal(str)
    connection_changed = Signal(bool, str)
    error_changed = Signal(str)

    def __init__(self, parent=None, poll_interval_ms=16):
        super().__init__(parent)
        self._sdl = None
        self._api_version = 0
        self._gamepad = None
        self._gamepad_name = ""
        self._error = ""
        self._button_state: dict[int, bool] = {}
        self._direction_state: dict[str, bool] = {}
        self._repeat_action = ""

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(poll_interval_ms)
        self._poll_timer.timeout.connect(self._poll)

        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(1000)
        self._scan_timer.timeout.connect(self._ensure_gamepad)

        self._repeat_delay = QTimer(self)
        self._repeat_delay.setSingleShot(True)
        self._repeat_delay.setInterval(350)
        self._repeat_delay.timeout.connect(self._begin_repeat)

        self._repeat_timer = QTimer(self)
        self._repeat_timer.setInterval(110)
        self._repeat_timer.timeout.connect(self._emit_repeat)

    @property
    def available(self) -> bool:
        return self._sdl is not None

    @property
    def connected(self) -> bool:
        return self._gamepad is not None

    @property
    def gamepad_name(self) -> str:
        return self._gamepad_name

    @property
    def error(self) -> str:
        return self._error

    def start(self):
        if self._poll_timer.isActive():
            return
        if not self._load_sdl():
            return
        if not self._initialize_sdl():
            self._sdl = None
            return
        self._ensure_gamepad()
        self._poll_timer.start()
        self._scan_timer.start()

    def stop(self):
        self._poll_timer.stop()
        self._scan_timer.stop()
        self._stop_repeat()
        self._close_gamepad()
        if self._sdl is not None:
            try:
                self._sdl.SDL_QuitSubSystem(SDL_INIT_GAMEPAD)
            except (AttributeError, OSError):
                pass

    def _set_error(self, message: str):
        if message == self._error:
            return
        self._error = message
        if message:
            logger.warning("SDL gamepad backend: %s", message)
        self.error_changed.emit(message)

    def _load_sdl(self) -> bool:
        for version, names in (
            (3, ("SDL3", "libSDL3.so.0", "libSDL3.so")),
            (2, ("SDL2", "libSDL2-2.0.so.0", "libSDL2.so")),
        ):
            # Direct soname loading is effectively instant. find_library can
            # invoke external tools and is slow in some AppImage environments,
            # so keep it only as a fallback.
            candidates = list(names[1:])
            for candidate in candidates:
                try:
                    self._sdl = ctypes.CDLL(candidate)
                    self._api_version = version
                    self._configure_functions()
                    self._set_error("")
                    return True
                except (OSError, AttributeError):
                    self._sdl = None

            discovered = ctypes.util.find_library(names[0])
            if discovered and discovered not in candidates:
                try:
                    self._sdl = ctypes.CDLL(discovered)
                    self._api_version = version
                    self._configure_functions()
                    self._set_error("")
                    return True
                except (OSError, AttributeError):
                    self._sdl = None

        self._set_error("SDL 3 or SDL 2 could not be loaded")
        return False

    def _configure_functions(self):
        self._sdl.SDL_GetError.restype = ctypes.c_char_p
        self._sdl.SDL_QuitSubSystem.argtypes = [ctypes.c_uint32]
        self._sdl.SDL_PumpEvents.argtypes = []

        if self._api_version == 3:
            self._sdl.SDL_InitSubSystem.argtypes = [ctypes.c_uint32]
            self._sdl.SDL_InitSubSystem.restype = ctypes.c_bool
            self._sdl.SDL_GetGamepads.argtypes = [ctypes.POINTER(ctypes.c_int)]
            self._sdl.SDL_GetGamepads.restype = ctypes.POINTER(ctypes.c_uint32)
            self._sdl.SDL_OpenGamepad.argtypes = [ctypes.c_uint32]
            self._sdl.SDL_OpenGamepad.restype = ctypes.c_void_p
            self._sdl.SDL_CloseGamepad.argtypes = [ctypes.c_void_p]
            self._sdl.SDL_GamepadConnected.argtypes = [ctypes.c_void_p]
            self._sdl.SDL_GamepadConnected.restype = ctypes.c_bool
            self._sdl.SDL_GetGamepadName.argtypes = [ctypes.c_void_p]
            self._sdl.SDL_GetGamepadName.restype = ctypes.c_char_p
            self._sdl.SDL_GetGamepadButton.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self._sdl.SDL_GetGamepadButton.restype = ctypes.c_bool
            self._sdl.SDL_GetGamepadAxis.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self._sdl.SDL_GetGamepadAxis.restype = ctypes.c_int16
            self._sdl.SDL_UpdateGamepads.argtypes = []
            self._sdl.SDL_free.argtypes = [ctypes.c_void_p]
        else:
            self._sdl.SDL_InitSubSystem.argtypes = [ctypes.c_uint32]
            self._sdl.SDL_InitSubSystem.restype = ctypes.c_int
            self._sdl.SDL_NumJoysticks.restype = ctypes.c_int
            self._sdl.SDL_IsGameController.argtypes = [ctypes.c_int]
            self._sdl.SDL_IsGameController.restype = ctypes.c_int
            self._sdl.SDL_GameControllerOpen.argtypes = [ctypes.c_int]
            self._sdl.SDL_GameControllerOpen.restype = ctypes.c_void_p
            self._sdl.SDL_GameControllerClose.argtypes = [ctypes.c_void_p]
            self._sdl.SDL_GameControllerGetAttached.argtypes = [ctypes.c_void_p]
            self._sdl.SDL_GameControllerGetAttached.restype = ctypes.c_int
            self._sdl.SDL_GameControllerName.argtypes = [ctypes.c_void_p]
            self._sdl.SDL_GameControllerName.restype = ctypes.c_char_p
            self._sdl.SDL_GameControllerGetButton.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self._sdl.SDL_GameControllerGetButton.restype = ctypes.c_uint8
            self._sdl.SDL_GameControllerGetAxis.argtypes = [ctypes.c_void_p, ctypes.c_int]
            self._sdl.SDL_GameControllerGetAxis.restype = ctypes.c_int16
            self._sdl.SDL_GameControllerUpdate.argtypes = []

    def _initialize_sdl(self) -> bool:
        result = self._sdl.SDL_InitSubSystem(SDL_INIT_GAMEPAD)
        succeeded = bool(result) if self._api_version == 3 else result == 0
        if not succeeded:
            self._set_error(self._last_sdl_error() or "SDL gamepad initialization failed")
        return succeeded

    def _last_sdl_error(self) -> str:
        error = self._sdl.SDL_GetError() if self._sdl is not None else None
        return error.decode(errors="replace") if error else ""

    def _ensure_gamepad(self):
        if self._sdl is None:
            return

        # SDL discovers hotplug events through its event pump. LVNM polls
        # controller state rather than consuming SDL events, so explicitly
        # pump the queue before checking the device list.
        self._sdl.SDL_PumpEvents()
        if self._gamepad is not None:
            if self._is_attached():
                return
            self._close_gamepad()

        # Refresh SDL's device state before enumerating. This is particularly
        # important when the application started before a controller was
        # connected.
        if self._api_version == 3:
            self._sdl.SDL_UpdateGamepads()
        else:
            self._sdl.SDL_GameControllerUpdate()

        handle = self._open_first_gamepad()
        if not handle:
            return

        self._gamepad = handle
        self._gamepad_name = self._read_gamepad_name() or "SDL Gamepad"
        self._button_state.clear()
        self._direction_state.clear()
        self._set_error("")
        self.connection_changed.emit(True, self._gamepad_name)

    def _open_first_gamepad(self):
        if self._api_version == 3:
            count = ctypes.c_int(0)
            gamepads = self._sdl.SDL_GetGamepads(ctypes.byref(count))
            if not gamepads:
                return None
            try:
                for index in range(count.value):
                    handle = self._sdl.SDL_OpenGamepad(gamepads[index])
                    if handle:
                        return handle
            finally:
                self._sdl.SDL_free(gamepads)
            return None

        for index in range(max(0, self._sdl.SDL_NumJoysticks())):
            if self._sdl.SDL_IsGameController(index):
                handle = self._sdl.SDL_GameControllerOpen(index)
                if handle:
                    return handle
        return None

    def _is_attached(self) -> bool:
        if self._api_version == 3:
            return bool(self._sdl.SDL_GamepadConnected(self._gamepad))
        return bool(self._sdl.SDL_GameControllerGetAttached(self._gamepad))

    def _read_gamepad_name(self) -> str:
        if self._api_version == 3:
            value = self._sdl.SDL_GetGamepadName(self._gamepad)
        else:
            value = self._sdl.SDL_GameControllerName(self._gamepad)
        return value.decode(errors="replace") if value else ""

    def _close_gamepad(self):
        if self._gamepad is None:
            return
        if self._api_version == 3:
            self._sdl.SDL_CloseGamepad(self._gamepad)
        else:
            self._sdl.SDL_GameControllerClose(self._gamepad)
        self._gamepad = None
        old_name = self._gamepad_name
        self._gamepad_name = ""
        self._button_state.clear()
        self._direction_state.clear()
        self._stop_repeat()
        self.connection_changed.emit(False, old_name)

    def _poll(self):
        if self._gamepad is None:
            return
        self._sdl.SDL_PumpEvents()
        if not self._is_attached():
            self._close_gamepad()
            return

        if self._api_version == 3:
            self._sdl.SDL_UpdateGamepads()
            get_button = self._sdl.SDL_GetGamepadButton
            get_axis = self._sdl.SDL_GetGamepadAxis
        else:
            self._sdl.SDL_GameControllerUpdate()
            get_button = self._sdl.SDL_GameControllerGetButton
            get_axis = self._sdl.SDL_GameControllerGetAxis

        active_repeat_action = ""
        for binding in BUTTON_BINDINGS:
            pressed = bool(get_button(self._gamepad, binding.index))
            was_pressed = self._button_state.get(binding.index, False)
            if pressed and not was_pressed:
                self.action_pressed.emit(binding.action)
            self._button_state[binding.index] = pressed
            if pressed and binding.repeat:
                active_repeat_action = binding.action

        left_x = int(get_axis(self._gamepad, 0))
        left_y = int(get_axis(self._gamepad, 1))
        left_trigger = int(get_axis(self._gamepad, 4))
        right_trigger = int(get_axis(self._gamepad, 5))
        axis_directions = {
            "navigate_left": left_x < -AXIS_THRESHOLD,
            "navigate_right": left_x > AXIS_THRESHOLD,
            "navigate_up": left_y < -AXIS_THRESHOLD,
            "navigate_down": left_y > AXIS_THRESHOLD,
            "previous_section": left_trigger > AXIS_THRESHOLD,
            "next_section": right_trigger > AXIS_THRESHOLD,
        }
        for action, pressed in axis_directions.items():
            was_pressed = self._direction_state.get(action, False)
            if pressed and not was_pressed:
                self.action_pressed.emit(action)
            self._direction_state[action] = pressed
            if pressed:
                active_repeat_action = action

        self._update_repeat(active_repeat_action)

    def _update_repeat(self, action: str):
        if action == self._repeat_action:
            return
        self._stop_repeat()
        if action:
            self._repeat_action = action
            self._repeat_delay.start()

    def _begin_repeat(self):
        if self._repeat_action:
            self._repeat_timer.start()

    def _emit_repeat(self):
        if self._repeat_action:
            self.action_pressed.emit(self._repeat_action)

    def _stop_repeat(self):
        self._repeat_delay.stop()
        self._repeat_timer.stop()
        self._repeat_action = ""
