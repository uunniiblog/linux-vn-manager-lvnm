import os
import json
import shlex
import logging
import config
import time
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from collections import deque
from model.game_card import GameCard
from execution_manager import ExecutionManager
from emulation_manager import EmulationManager
from settings_manager import SettingsManager
from timetracker.system_utils import SystemUtils as TimeTrackUtils
from timetracker.utils_factory import get_desktop_utils
from timetracker.x11_utils import X11Utils

logger = logging.getLogger(__name__)

class LauncherBaseGame(ABC):
    PREFIXES_DATA = Path(config.PREFIXES_DATA)
    GAME_DATA = Path(config.GAMES_DATA)

    def __init__(self, name: str, card_override: GameCard = None):
        self.name = name
        self.game: GameCard = card_override
        self.prefix_info: dict = None
        self.env: dict = {}
        self.cmd: list = []
        self.process = None
        self.logs = deque(maxlen=2000)
        self.settings = SettingsManager()

    @abstractmethod
    def run(self, is_headless: bool = False) -> bool: ...

    @abstractmethod
    def is_running(self) -> bool: ...

    @abstractmethod
    def stop(self, running_prefix_count: int = 1): ...

    def load_data(self):
        """Loads game and prefix data into the instance."""
        # Only fetch from the json if we didn't provide a card manually
        if not self.game:
            self.game = self._get_game_card(self.name)

        if not self.game:
            raise ValueError(f"Game '{self.name}' not found in registry.")

        self.prefix_info = self._get_prefix_info(self.game.prefix)
        if not self.prefix_info:
            raise ValueError(f"Prefix for {self.name} not found.")
        if not self.game.path or not os.path.isfile(self.game.path):
            raise ValueError(f"Path for {self.name} not found.")

    def _get_game_card(self, name: str):
        if not self.GAME_DATA.exists():
            return None
        with open(self.GAME_DATA, "r", encoding="utf-8") as f:
            data = json.load(f)
            if name in data:
                return GameCard.from_dict(name, data[name])
        return None

    def _get_prefix_info(self, prefix_name: str):
        real = {}
        if self.PREFIXES_DATA.exists():
            with open(self.PREFIXES_DATA, "r", encoding="utf-8") as f:
                real = json.load(f)
        return {**real, **EmulationManager.get_virtual_prefixes()}.get(prefix_name)

    def apply_gamescope(self, cmd: list) -> list:
        """Wraps a command with gamescope if enabled"""
        if self.game.gamescope.enabled.lower() == "true":
            gs_params = self.game.gamescope.parameters.split()
            return ["gamescope"] + gs_params + ["--"] + cmd
        return cmd

    def apply_pre_launch_args(self, cmd: list) -> list:
        """Prepends pre-launch wrapper args."""
        if self.game.pre_launch_args.strip():
            pre_args = shlex.split(self.game.pre_launch_args.strip())
            return pre_args + cmd
        return cmd

    def apply_game_arguments(self, cmd: list) -> list:
        """Appends per-game arguments"""
        if self.game.arguments.strip():
            extra_args = shlex.split(self.game.arguments.strip(), posix=False)
            return cmd + extra_args
        return cmd

    def run_external_script(self, script_path: str):
        """Executes a script in a fully detached state."""
        if not script_path or not os.path.exists(script_path.split()[0]):
            logger.error(f"run_external_script script_path: {script_path}")
            return

        logger.info(f"Executing external script: {script_path}")

        try:
            cmd = ["bash"] + shlex.split(script_path)
            logger.debug(f"run_external_script raw input : '{script_path}'")
            logger.debug(f"run_external_script shlex tokens: {shlex.split(script_path)}")
            logger.debug(f"run_external_script final cmd  : {cmd}")

            # Remove LD_PRELOAD to avoid issues with steam. Should not be needed for scripts
            env = self.env
            env.pop("LD_PRELOAD", None)

            ExecutionManager.run_detached(cmd, env, cwd=getattr(self, "game_dir", None), suppress_stdout=False)
        except Exception as e:
            logger.error(f"Failed to launch script {script_path}: {e}")

    def _wait_for_process_then_run_script(self, script_path: str, target_process: str, cmdline_hint: str = None):
        """Calls _poll_for_window_and_execute to poll until the game window is opened then runs the script"""
        is_proton_wayland = self.env.get("PROTON_ENABLE_WAYLAND") == "1"
        is_x11_utils = isinstance(get_desktop_utils(), X11Utils)

        def on_found(wid, title):
            if wid:
                time.sleep(0.5)
            self.run_external_script(script_path)

        fallback_check = self.is_running if (is_proton_wayland and is_x11_utils) else None
        self._poll_for_window_and_execute(target_process, on_found, cmdline_hint=cmdline_hint, fallback_check=fallback_check, label="pre_launch_script_wait")

    def _launch_linux_rt_upscaler(self, target_process: str, cmdline_hint: str = None):
        """Calls _poll_for_window_and_execute to poll until the game window is opened then run linux-rt-upscaler over its title."""
        upscale_params = self.game.rtUpscaler.parameters

        def on_found(wid, title):
            cmd = ["upscale", "-t", title, "--target-delay", "1"] + shlex.split(upscale_params)
            logger.info(f"_launch_linux_rt_upscaler: Launching linux-rt-upscaler: {shlex.join(cmd)}.")
            ExecutionManager.run_detached(cmd, self.env, cwd=self.game_dir, suppress_stdout=False)

        self._poll_for_window_and_execute(target_process, on_found, cmdline_hint=cmdline_hint, label="launch_linux_rt_upscaler",)

    def _poll_for_window_and_execute(self, target_process: str, on_found, cmdline_hint: str = None, 
            max_attempts: int = 20, poll_interval: float = 2.0, fallback_check=None, label: str = "poll"):
        """Spawns a background thread that polls  for a window owned by target_process, then calls on_found"""
        utils = get_desktop_utils()

        def _poll():
            for attempt in range(1, max_attempts + 1):
                logger.info(f"{label}: Waiting for game process... attempt {attempt}/{max_attempts}")

                if fallback_check:
                    if fallback_check():
                        logger.info(f"{label}: Fallback condition met after {attempt} attempt(s).")
                        time.sleep(2)
                        on_found(None, None)
                        return
                else:
                    pids = TimeTrackUtils.get_pids_by_name(target_process, cmdline_hint=cmdline_hint)
                    if pids:
                        wid, title = utils.find_window_by_pid(pids, target_process)
                        if wid and title:
                            logger.info(f"{label}: Window detected '{title}' (WID: {wid}) after {attempt} attempt(s).")
                            on_found(wid, title)
                            return

                time.sleep(poll_interval)

            logger.error(f"{label}: Game process not found after {max_attempts} attempts. Action NOT executed.")

        threading.Thread(target=_poll, daemon=True, name=label).start()

    def _add_log_line(self, line):
        """Callback used by ExecutionManager"""
        self.logs.append(f"{datetime.today().strftime('%Y-%m-%d %H:%M:%S')} - {line}")

    def get_full_log(self):
        """Returns the entire buffer as a single string for a UI text box"""
        return "\n".join(self.logs)