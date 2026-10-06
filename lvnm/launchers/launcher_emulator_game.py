import shlex
import os
import signal
import config
import re
import logging
from pathlib import Path
from system_utils import SystemUtils
from execution_manager import ExecutionManager
from launchers.launcher_base_game import LauncherBaseGame
from pc98_manager import Pc98Manager

logger = logging.getLogger(__name__)

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
        game_path = self.game.path

        if emulator_type == config.EMULATION_PC98:
            extra_args = Pc98Manager.build_launch_args(self.game, self.prefix_info["core"], self.prefix_info.get("system_path")) + extra_args
            game_path = Pc98Manager.resolve_game_media(self.game)
        else:
            self._restore_flatpak_host_xdg_paths()

        self._enable_flatpak_appimage_fallback(emulator_path)

        # RPCS3 settings
        if emulator_type == config.EMULATION_PS3:
            extra_args = ["--no-gui"] + extra_args
            game_path = self._resolve_ps3_boot_arg(self.game.path)

        self.cmd = [emulator_path] + extra_args + [game_path]
        self.game_dir = str(Path(emulator_path).parent)

        # Apply game arguments
        self.cmd = self.apply_game_arguments(self.cmd)
        # Apply pre launch arguments
        self.cmd = self.apply_pre_launch_args(self.cmd)
        # Apply Gamescope Wrapper
        self.cmd = self.apply_gamescope(self.cmd)
        # Apply flatpak-spawn if flatpak
        self.cmd = self._wrap_flatpak_host_command(self.cmd, emulator_path)

    def run(self, is_headless=False):
        self.load_data()
        self.prepare_environment()

        # Script
        if self.game.pre_launch_script_wait and self.game.pre_launch_script.strip():
            self._wait_for_process_then_run_script(self.game.pre_launch_script.strip(), os.path.basename(self.prefix_info["path"]), cmdline_hint=self.game.path)
        elif self.game.pre_launch_script.strip():
            self.run_external_script(self.game.pre_launch_script.strip())

        # Run game
        self._log_run_command()
        self.process = ExecutionManager.run(self.cmd, self.env, wait=False,cwd=self.game_dir, log_callback=self._add_log_line,detached=not is_headless)

        # Apply linux-rt-upscaler
        if self.settings.get(config.USER_CONF_RT_UPSCALER_ENABLED, False) and self.game.rtUpscaler.enabled == "true":
            self._launch_linux_rt_upscaler(os.path.basename(self.prefix_info["path"]), cmdline_hint=self.game.path)

        return True

    def is_running(self):
        if self.process and self.process.poll() is None:
            return True
        return False

    def stop(self, running_prefix_count=1):
        if self.process:
            try:
                pgid = os.getpgid(self.process.pid)
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass

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

    def _log_run_command(self):
        """Logs the final configuration right before execution."""
        logger.debug("" + "="*60)
        logger.debug(f"LAUNCHING:     {self.name}")
        logger.debug("="*60)
        logger.debug(f"Game Path:     {self.game.path}")
        logger.debug(f"Emulator Path: {self.prefix_info["path"]}")
        logger.debug(f"Emulator Type: {self.prefix_info["type"]}")
        
        logger.debug("Environment Variables:")
        for var in self.env:
            logger.debug(f"   {var:<18}: {self.env[var]}")
        
        if self.game.envvar:
            logger.debug("Custom Vars:")
            for k, v in self.game.envvar.items():
                logger.debug(f"   {k:<18}: {v}")

        logger.debug("Gamescope:")
        logger.debug(f"   Enabled:         {self.game.gamescope.enabled}")
        if self.game.gamescope.enabled.lower() == "true":
            logger.debug(f"   Parameters:      {self.game.gamescope.parameters}")

        logger.debug("Execution Command:")
        logger.debug(f"   {' '.join(self.cmd)}")
        logger.debug("="*60)

    def _wrap_flatpak_host_command(self, cmd: list, emulator_path: str) -> list:
        """Run non AppImage emulator commands outside the Flatpak sandbox."""
        if SystemUtils.get_runtime_type() != "flatpak" or self._is_appimage(emulator_path) or getattr(self, "prefix_info", {}).get("bundled", False):
            return cmd

        home = self.env.get("HOME", str(Path.home()))
        emulator = Path(emulator_path)
        host_working_dir = str(emulator.parent) if emulator.is_absolute() else home

        host_cmd = [
            "flatpak-spawn",
            "--host",
            "--watch-bus",
            f"--directory={host_working_dir}",
        ]
        for key, value in self.game.envvar.items():
            host_cmd.append(f"--env={key}={value}")

        self.game_dir = home
        logger.info(f"Using host command for emulator: {emulator_path}")
        return host_cmd + cmd

    def _restore_flatpak_host_xdg_paths(self):
        """Let sandboxed emulators reuse their existing host profiles."""
        if SystemUtils.get_runtime_type() != "flatpak":
            return

        home = self.env.get("HOME")
        if not home:
            logger.warning("Cannot restore host emulator config paths: HOME is not set")
            return

        host_xdg_paths = {
            "XDG_CONFIG_HOME": ("HOST_XDG_CONFIG_HOME", ".config"),
            "XDG_DATA_HOME": ("HOST_XDG_DATA_HOME", ".local/share"),
            "XDG_CACHE_HOME": ("HOST_XDG_CACHE_HOME", ".cache"),
            "XDG_STATE_HOME": ("HOST_XDG_STATE_HOME", ".local/state"),
        }
        for xdg_variable, (host_variable, default_path) in host_xdg_paths.items():
            self.env[xdg_variable] = self.env.get(host_variable) or str(Path(home) / default_path)

        logger.info("Using host XDG directories for emulator configuration and data")

    def _enable_flatpak_appimage_fallback(self, emulator_path: str):
        """Run AppImage emulators without FUSE when LVNM is sandboxed."""
        if SystemUtils.get_runtime_type() != "flatpak" or not self._is_appimage(emulator_path):
            return

        # Flatpak does not expose the FUSE mount helper/device to the sandbox.
        # Extract to a temporary directory and running from there instead.
        self.env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
        logger.info(f"Using AppImage extract-and-run fallback for emulator: {emulator_path}")

    @staticmethod
    def _is_appimage(executable: str) -> bool:
        path = Path(executable)
        if path.suffix.casefold() == ".appimage":
            return True

        try:
            with path.open("rb") as executable_file:
                header = executable_file.read(11)
        except (OSError, TypeError, ValueError):
            return False

        # AppImage embeds "AI" and its format version in the ELF header.
        return (
            len(header) >= 11
            and header[:4] == b"\x7fELF"
            and header[8:10] == b"AI"
            and header[10] in (1, 2)
        )