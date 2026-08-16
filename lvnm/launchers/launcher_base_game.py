import os
import json
import shlex
import logging
import config
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from collections import deque
from model.game_card import GameCard
from execution_manager import ExecutionManager
from emulation_manager import EmulationManager

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
        """Wraps a command with gamescope if enabled on the game card. Shared by all launcher types."""
        if self.game.gamescope.enabled.lower() == "true":
            gs_params = self.game.gamescope.parameters.split()
            return ["gamescope"] + gs_params + ["--"] + cmd
        return cmd

    def run_external_script(self, script_path: str):
        """Executes a script in a fully detached state."""
        if not script_path or not os.path.exists(script_path.split()[0]):
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

    def _add_log_line(self, line):
        """Callback used by ExecutionManager"""
        self.logs.append(f"{datetime.today().strftime('%Y-%m-%d %H:%M:%S')} - {line}")

    def get_full_log(self):
        """Returns the entire buffer as a single string for a UI text box"""
        return "\n".join(self.logs)