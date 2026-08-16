import shlex
import config
import re
from pathlib import Path
from system_utils import SystemUtils
from execution_manager import ExecutionManager
from launchers.launcher_base_game import LauncherBaseGame

PS3_TITLE_ID_PATTERN = re.compile(r"^[A-Z]{4}\d{5}$")

class LauncherEmulatorGame(LauncherBaseGame):
    def prepare_environment(self):
        self.env = SystemUtils.get_clean_env()

        # Add user-defined environment variables
        for key, val in self.game.envvar.items():
            self.env[key] = val

        emulator_path = self.prefix_info["path"]
        emulator_type = self.prefix_info["type"]
        extra_args = shlex.split(self.prefix_info.get("config", ""))

        # RPCS3 settings
        if emulator_type == config.EMULATION_PS3:
            extra_args = ["--no-gui"] + extra_args
            game_path = self._resolve_ps3_boot_arg(self.game.path)

        self.cmd = [emulator_path] + extra_args + [self.game.path]
        self.game_dir = str(Path(emulator_path).parent)

        self.cmd = self.apply_gamescope(self.cmd)

    def run(self, is_headless=False):
        self.load_data()
        self.prepare_environment()
        self.process = ExecutionManager.run(self.cmd, self.env, wait=False,cwd=self.game_dir, log_callback=self._add_log_line,detached=not is_headless)
        return True

    def is_running(self):
        if self.process and self.process.poll() is None:
            return True
        return False

    def stop(self, running_prefix_count=1):
        if self.process:
            self.process.terminate()

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
        if not self.game.path:
            raise ValueError(f"Path for {self.name} not found.")
    
    def _resolve_ps3_boot_arg(self, game_path: str) -> str:
        """'BLJM61043' -> '%RPCS3_GAMEID%:BLJM61043'"""
        stripped = game_path.strip()
        if PS3_TITLE_ID_PATTERN.match(stripped):
            return f"%RPCS3_GAMEID%:{stripped}"
        return game_path