import logging
import os
import signal
from pathlib import Path

import config
from execution_manager import ExecutionManager
from launchers.launcher_base_game import LauncherBaseGame
from system_utils import SystemUtils

logger = logging.getLogger(__name__)


class LauncherNativeGame(LauncherBaseGame):
    """Launch a native Linux executable without Wine or an emulator."""

    FLATPAK_ENVIRONMENT_VARIABLES = (
        "APPDIR",
        "APPIMAGE",
        "ARGV0",
        "LD_LIBRARY_PATH",
        "LOCPATH",
        "GST_PLUGIN_PATH",
        "GST_PLUGIN_SYSTEM_PATH",
        "PYTHONHOME",
        "PYTHONPATH",
    )

    HOST_XDG_PATHS = {
        "XDG_CONFIG_HOME": ("HOST_XDG_CONFIG_HOME", ".config"),
        "XDG_DATA_HOME": ("HOST_XDG_DATA_HOME", ".local/share"),
        "XDG_CACHE_HOME": ("HOST_XDG_CACHE_HOME", ".cache"),
        "XDG_STATE_HOME": ("HOST_XDG_STATE_HOME", ".local/state"),
    }

    def prepare_environment(self):
        game_path = Path(self.game.path)
        if not os.access(game_path, os.X_OK):
            raise ValueError(f"Native game is not executable: {game_path}")

        self.env = SystemUtils.get_clean_env()
        self.game_dir = str(game_path.parent)

        for key, value in self.game.envvar.items():
            self.env[key] = value

        self.cmd = [str(game_path)]
        self.cmd = self.apply_game_arguments(self.cmd, posix=True)
        self.cmd = self.apply_pre_launch_args(self.cmd)
        self.cmd = self.apply_gamescope(self.cmd)

        if SystemUtils.get_runtime_type() == "flatpak":
            self.cmd = self._wrap_flatpak_host_command(self.cmd)

    def run(self, is_headless: bool = False) -> bool:
        self.load_data()
        self.prepare_environment()
        self._detached_process = not is_headless

        executable_name = os.path.basename(self.game.path)
        if self.game.pre_launch_script_wait and self.game.pre_launch_script.strip():
            self._wait_for_process_then_run_script(
                self.game.pre_launch_script.strip(),
                executable_name,
                cmdline_hint=self.game.path,
            )
        elif self.game.pre_launch_script.strip():
            self.run_external_script(self.game.pre_launch_script.strip())

        self._log_run_command()
        self.process = self._run_game_process(
            self.cmd,
            self.env,
            wait=False,
            cwd=self.game_dir,
            log_callback=self._add_log_line,
            detached=self._detached_process,
        )

        if (
            self.settings.get(config.USER_CONF_RT_UPSCALER_ENABLED, False)
            and self.game.rtUpscaler.enabled == "true"
        ):
            self._launch_linux_rt_upscaler(
                executable_name,
                cmdline_hint=self.game.path,
            )

        return True

    def is_running(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    def stop(self, running_prefix_count: int = 1):
        if not self.process or self.process.poll() is not None:
            return

        try:
            if getattr(self, "_detached_process", False):
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            else:
                self.process.terminate()
        except ProcessLookupError:
            pass

    def _wrap_flatpak_host_command(self, cmd: list) -> list:
        """Run the complete native command, including wrappers, on the host."""
        for variable in self.FLATPAK_ENVIRONMENT_VARIABLES:
            self.env.pop(variable, None)

        home = self.env.get("HOME", str(Path.home()))
        for variable, (host_variable, default_path) in self.HOST_XDG_PATHS.items():
            self.env[variable] = self.env.pop(
                host_variable,
                str(Path(home) / default_path),
            )
        self.env["XDG_CONFIG_DIRS"] = "/etc/xdg"
        self.env["XDG_DATA_DIRS"] = "/usr/local/share:/usr/share"

        host_cmd = [
            "flatpak-spawn",
            "--host",
            "--watch-bus",
            f"--directory={self.game_dir}",
        ]
        for key, value in self.game.envvar.items():
            host_cmd.append(f"--env={key}={value}")

        # The directory is already applied to the host process. The local cwd
        # only needs to be a path visible from inside the LVNM sandbox.
        self.game_dir = home
        logger.info("Using host command for native game: %s", self.game.path)
        return host_cmd + cmd

    def _log_run_command(self):
        logger.debug("=" * 60)
        logger.debug("LAUNCHING NATIVE GAME: %s", self.name)
        logger.debug("Game Path: %s", self.game.path)
        logger.debug("Working Directory: %s", Path(self.game.path).parent)
        logger.debug("Execution Command: %s", " ".join(self.cmd))
        logger.debug("=" * 60)
