import shlex
from pathlib import Path

from system_utils import SystemUtils
from execution_manager import ExecutionManager

from launchers.launcher_base_game import LauncherBaseGame


class LauncherEmulatorGame(LauncherBaseGame):
    def prepare_environment(self):
        self.env = SystemUtils.get_clean_env()

        # Add user-defined environment variables
        for key, val in self.game.envvar.items():
            self.env[key] = val

        emulator_path = self.prefix_info["path"]
        extra_args = shlex.split(self.prefix_info.get("config", ""))
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