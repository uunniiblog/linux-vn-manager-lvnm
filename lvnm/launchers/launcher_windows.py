import logging
import os
import shlex
import subprocess
from pathlib import Path

from execution_manager import ExecutionManager
from launchers.launcher_base_game import LauncherBaseGame
from system_utils import SystemUtils

logger = logging.getLogger(__name__)


class LauncherWindows(LauncherBaseGame):
    """Launch a Windows game directly, without Wine or prefix management."""

    def prepare_environment(self):
        game_path = Path(self.game.path)
        self.env = SystemUtils.get_clean_env()
        self.env.update({key: str(value) for key, value in self.game.envvar.items()})
        self.game_dir = str(game_path.parent)
        self.cmd = self.apply_game_arguments([str(game_path)], posix=False)
        self.cmd = [self._strip_argument_quotes(argument) for argument in self.cmd]
        self.cmd = self.apply_pre_launch_command(self.cmd)

    def apply_pre_launch_command(self, cmd: list[str]) -> list[str]:
        """Prepend a Windows wrapper command to the game command."""
        command = self.game.pre_launch_args.strip()
        if not command:
            return cmd
        return self._split_windows_command(command) + cmd

    @classmethod
    def _split_windows_command(cls, command: str) -> list[str]:
        """Split a user-entered Windows command while preserving backslashes."""
        return [cls._strip_argument_quotes(argument) for argument in shlex.split(command, posix=False)]

    @staticmethod
    def _strip_argument_quotes(argument: str) -> str:
        if len(argument) >= 2 and argument[0] == argument[-1] and argument[0] in ('"', "'"):
            return argument[1:-1]
        return argument

    def run(self, is_headless: bool = False) -> bool:
        self.load_data()
        self.prepare_environment()

        script = self.game.pre_launch_script.strip()
        if script and self.game.pre_launch_script_wait:
            self._wait_for_window_then_run_script(script)
        elif script:
            self.run_external_script(script)

        logger.info(f"Launching Windows game '{self.name}' from {self.game_dir}")
        self.process = ExecutionManager.run_windows(
            self.cmd, self.env, wait=False, cwd=self.game_dir, log_callback=self._add_log_line, detached=not is_headless
        )

        return True

    def _wait_for_window_then_run_script(self, script_path: str):
        """Run a script after the native game creates its first visible window."""
        target_process = Path(self.game.path).name

        def on_found(window_id, title):
            logger.info(f"Running delayed script for '{self.name}' after detecting window '{title}' (WID: {window_id}).")
            self.run_external_script(script_path)

        self._poll_for_window_and_execute(target_process, on_found, cmdline_hint=self.game.path, label="windows_pre_launch_script_wait")

    def is_running(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    def stop(self, running_prefix_count: int = 1):
        if not self.is_running():
            return
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning(f"Game '{self.name}' did not stop gracefully; killing it.")
            self.process.kill()
        except OSError as error:
            logger.warning(f"Could not stop Windows game '{self.name}': {error}")

    def run_external_script(self, script_path: str):
        """Launch a Windows batch, PowerShell, or executable script."""
        try:
            script_command = self._split_windows_command(script_path)
        except ValueError as error:
            logger.error(f"Invalid Windows script command '{script_path}': {error}")
            return None

        if not script_command:
            return None

        extension = Path(script_command[0]).suffix.lower()
        if extension in {".bat", ".cmd"}:
            command_line = subprocess.list2cmdline(script_command)
            command = [self.env.get("COMSPEC") or os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command_line]
        elif extension == ".ps1":
            command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", *script_command]
        else:
            command = script_command

        logger.info(f"Executing Windows script: {subprocess.list2cmdline(command)}")
        try:
            return ExecutionManager.run_windows(command, self.env, wait=False, cwd=self.game_dir, log_callback=self._add_log_line, detached=True)
        except (OSError, subprocess.SubprocessError) as error:
            logger.error(f"Failed to execute Windows script '{script_path}': {error}")
            return None
