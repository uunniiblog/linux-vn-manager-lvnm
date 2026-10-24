import os
import signal
import json
import config
import subprocess
import logging
import re
import threading
import atexit
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from model.game_card import GameCard, GameScope
from execution_manager import ExecutionManager
from system_utils import SystemUtils
from launchers.launcher_base_game import LauncherBaseGame

logger = logging.getLogger(__name__)

class LauncherWineGame(LauncherBaseGame):
    _dpi_registry_key = r"HKCU\Control Panel\Desktop"
    #PREFIXES_DATA = Path(config.PREFIXES_DATA)
    #GAME_DATA = Path(config.GAMES_DATA)

    def __init__(self, name: str, card_override: GameCard = None, is_steam=False):
        super().__init__(name, card_override)
        self.is_steam = is_steam
        self.umu_path = None
        self.is_proton = False
        self.network_isolation_fds = ()

    def prepare_environment(self):
        """Builds the environment and the final command list."""
        self.env = SystemUtils.get_clean_env()

        # Clean app image env variables
        self.scrub_appimage_environment()

        if self.is_steam:
            logging.info("Steam launch detected: Remvoing LC_ALL...")
            # Adjust this since it fucks with jp paths
            self.env.pop("LC_ALL")
            
        self.env["WINEPREFIX"] = self.prefix_info["path"]
        self.env["PWD"] = self.prefix_info["path"]

        if "wineconsole" in self.game.name or "util-bash" in self.game.name:
            self.game_dir = str(Path(self.prefix_info["path"]))
        else:
            self.game_dir = str(Path(self.game.path).parent)
        
        # Add user-defined environment variables
        for key, val in self.game.envvar.items():
            self.env[key] = val
            
        # Handle DLL Overrides
        if self.game.dlloverride:
            overrides = ";".join([f"{k}={v}" for k, v in self.game.dlloverride.items()])
            existing = self.env.get("WINEDLLOVERRIDES", "")
            self.env["WINEDLLOVERRIDES"] = f"{existing};{overrides}".strip(";")

        # Determine runner
        runner_path = Path(self.prefix_info["runner"])
        is_proton = self.prefix_info.get("type") == "proton"

        logger.debug(f"is_proton: {is_proton}")
        
        if is_proton:
            self.is_proton = True
            self.cmd = self._handle_proton(runner_path)
        else:
            self.is_proton = False
            self.cmd = self._handle_wine(runner_path)

        if not self.cmd:
            raise RuntimeError("Failed to build launch command.")

        # Apply game arguments
        self.cmd = self.apply_game_arguments(self.cmd)
        # Apply pre launch arguments
        self.cmd = self.apply_pre_launch_args(self.cmd)
        # Apply Gamescope Wrapper
        self.cmd = self.apply_gamescope(self.cmd)
        # Disable network access option
        self.cmd = self.apply_network_isolation(self.cmd)

    def apply_network_isolation(self, cmd: list) -> list:
        """Run the final game command without network access when supported."""
        for descriptor in getattr(self, "network_isolation_fds", ()):
            os.close(descriptor)
        self.network_isolation_fds = ()
        
        if not getattr(self.game, "disable_network", False):
            return cmd

        if SystemUtils.get_runtime_type() == "flatpak":
            spawn_env = ExecutionManager._get_verbosity_env(self.env)
            environment = b"\0".join(os.fsencode(f"{key}={value}") for key, value in spawn_env.items()) + b"\0"
            environment_fd = os.memfd_create("lvnm-flatpak-environment", flags=0)
            with os.fdopen(environment_fd, "wb", closefd=False) as environment_file:
                environment_file.write(environment)
            os.lseek(environment_fd, 0, os.SEEK_SET)
            os.set_inheritable(environment_fd, True)
            self.network_isolation_fds = (environment_fd,)
            logger.info(f"Network access disabled for game '{self.game.name}' using Flatpak.")
            return ["flatpak-spawn", "--no-network", "--watch-bus", f"--env-fd={environment_fd}", *cmd]

        firejail = SystemUtils.get_firejail_path()
        if firejail is None:
            logger.warning(f"Network isolation was requested for '{self.game.name}', but Firejail is not installed. Launching without network isolation.")
            return cmd

        logger.info(f"Network access disabled for game '{self.game.name}' using Firejail.")
        return [firejail, "--noprofile", "--net=none", *cmd]

    def run_in_prefix(self, exe_path: str, prefix_name: str):
        """
        Bypasses JSON loading to run an arbitrary executable in a selected prefix.
        Useful for installers or utility stuff.
        Automatically applies global environment variables
        """
        try:
            # Manually fetch prefix info
            self.prefix_info = self._get_prefix_info(prefix_name)
            
            if not self.prefix_info:
                raise ValueError(f"Prefix '{prefix_name}' not found.")

            self.game = GameCard(
                name=f"Util-{exe_path}",
                path=exe_path,
                prefix=prefix_name,
                vndb="",
            )

            # Grab global env vars
            global_env_status = self.settings.get(config.USER_CONF_GLOBAL_VARIABLES, {})
            env_definitions = self.settings.get(config.USER_CONF_ENV_VARIABLE_LIST, config.ENV_VARIABLES)
            
            env_vars = {}
            for var in env_definitions:
                var_id = var.get("id")
                # Only add if the variable is toggled ON in global settings
                if global_env_status.get(var_id):
                    env_vars[var["key"]] = str(var["value"])

            self.game.envvar = env_vars
            
            # Call same logic as run
            self.prepare_environment()

            if self.is_proton:
                self.env["PROTON_VERB"] = "runinprefix"

            # Automatically modify DPI according to monitor's resolution
            dpi_state = self._set_temporary_utility_dpi() if self.settings.get(config.USER_CONF_AUTO_DPI_UTILITIES, False) else None
            if dpi_state:
                cleanup_lock = threading.Lock()
                cleaned_up = False

                def restore_dpi():
                    nonlocal cleaned_up
                    with cleanup_lock:
                        if cleaned_up:
                            return
                        cleaned_up = True
                        self._restore_utility_dpi(*dpi_state)
                        atexit.unregister(restore_dpi)

                atexit.register(restore_dpi)
            try:
                self._log_run_command(Path(self.prefix_info["runner"]))
                self.process = ExecutionManager.run(self.cmd, self.env, wait=False, cwd=self.game_dir)
            except Exception:
                if dpi_state:
                    restore_dpi()
                raise
            if dpi_state:
                threading.Thread(target=self._restore_dpi_after_exit, args=(self.process, restore_dpi), daemon=True, name="lvnm-utility-dpi").start()
            return True
            
        except Exception as e:
            logging.error(f"Run in prefix failed: {e}")
            raise RuntimeError(f"Run in prefix failed: {e}")

    def _utility_registry_command(self, *args):
        if self.is_proton:
            reg_exe = Path(self.prefix_info["path"]) / "drive_c" / "windows" / "system32" / "reg.exe"
            return [self.umu_path, str(reg_exe), *args]
        return [self.env["WINE"], "reg", *args]

    def _query_utility_dpi(self):
        if self.is_proton:
            drive_c = Path(self.prefix_info["path"]) / "drive_c"
            with tempfile.TemporaryDirectory(prefix=".lvnm-dpi-", dir=drive_c) as temp_dir:
                export_path = Path(temp_dir) / "desktop.reg"
                windows_path = f"C:\\{Path(temp_dir).name}\\desktop.reg"
                result = subprocess.run(self._utility_registry_command("export", self._dpi_registry_key, windows_path), env=self.env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                if result.returncode or not export_path.exists():
                    raise RuntimeError("Unable to export the prefix DPI registry key")
                response = export_path.read_text(encoding="utf-16")

            in_desktop_key = False
            for line in response.splitlines():
                if line.startswith("["):
                    in_desktop_key = line.casefold() == r"[HKEY_CURRENT_USER\Control Panel\Desktop]".casefold()
                elif in_desktop_key:
                    match = re.fullmatch(r'"LogPixels"=dword:([0-9a-fA-F]{8})', line)
                    if match:
                        return int(match.group(1), 16)
            return None

        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                self._utility_registry_command("query", self._dpi_registry_key, "/v", "LogPixels"),
                env=self.env, stdout=output, stderr=subprocess.STDOUT, timeout=15
            )
            output.seek(0)
            response = output.read().decode("utf-8", errors="replace")

        if result.returncode:
            return None

        match = re.search(r"\bLogPixels\s+REG_DWORD\s+(0x[0-9a-fA-F]+|\d+)\b", response, re.IGNORECASE)
        if not match:
            raise RuntimeError(f"Unable to read the prefix DPI: {response.strip()}")

        return int(match.group(1), 0)

    def _write_utility_dpi(self, dpi):
        if dpi is None:
            cmd = self._utility_registry_command("delete", self._dpi_registry_key, "/v", "LogPixels", "/f")
        else:
            cmd = self._utility_registry_command("add", self._dpi_registry_key, "/v", "LogPixels", "/t", "REG_DWORD", "/d", str(dpi), "/f")

        subprocess.run(cmd, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=True)

    def _set_temporary_utility_dpi(self):
        """
        Modify DPI for 1440 and 2160p screens.
        Revert after program closes.
        """
        resolution = SystemUtils.get_mainscreen_resolution()
        if not resolution:
            logger.warning("Auto DPI skipped because the primary monitor resolution could not be detected.")
            return None
        if resolution[1] <= 1080:
            return None
        dpi = 144 if resolution[1] < 1440 else 168
        prefix_path = self.prefix_info["path"]

        try:
            original = self._query_utility_dpi()
        except (OSError, subprocess.TimeoutExpired, RuntimeError, UnicodeError) as error:
            logger.warning(f"Auto DPI skipped for prefix '{prefix_path}' because its current DPI could not be read: {error}")
            return None

        try:
            if original == dpi:
                return None
            self._write_utility_dpi(dpi)
            logger.info(f"Temporarily set prefix '{prefix_path}' DPI to {dpi} for {self.game.path}.")
            return prefix_path, original, dpi
        except Exception:
            try:
                self._write_utility_dpi(original)
            except Exception as error:
                logger.error(f"Failed to roll back prefix '{prefix_path}' DPI after setup error: {error}")
            raise

    def _restore_utility_dpi(self, prefix_path, original, temporary):
        try:
            if self._query_utility_dpi() == temporary:
                self._write_utility_dpi(original)
                logger.info(f"Restored prefix '{prefix_path}' DPI after utility exit.")
            else:
                logger.info(f"Prefix '{prefix_path}' DPI changed while the utility was open; keeping the new value.")
        except Exception as error:
            logger.error(f"Failed to restore prefix '{prefix_path}' DPI: {error}")

    def _restore_dpi_after_exit(self, process, restore_dpi):
        try:
            process.wait()
        finally:
            restore_dpi()

    def run_texthooker(self, text_hooker_path: str, prefix_name: str, gamescope: GameScope, target_exe_path: str):
        """
        Bypasses JSON loading to run a texthooker
        """
        try:
            # Manually fetch prefix info
            self.prefix_info = self._get_prefix_info(prefix_name)
            
            if not self.prefix_info:
                raise ValueError(f"Prefix '{prefix_name}' not found.")

            self.game = GameCard(
                name=f"Texthook-{text_hooker_path}",
                path=text_hooker_path,
                prefix=prefix_name,
                vndb="",
                gamescope=gamescope or None
            )
            
            self.prepare_environment()

            # Always add jp locale for proper text rendering
            self.env["LANG"] = "ja_JP.UTF-8"

            exe_filename = os.path.basename(target_exe_path)
            logger.debug(f"Texthooking to target_exe {exe_filename}")

            if self.is_proton:
                logger.debug("Launch texthooker through proton")
                self.env["PROTON_VERB"] = "runinprefix"

                # Run through proton instead of umu
                self.cmd = [self.env["WINE"] if c == self.umu_path else c for c in self.cmd]
                
                if "textractor" in text_hooker_path.lower():
                    logger.info("Textractor detected, auto attaching to game")
                    self.cmd.append(f"-p{exe_filename}")

                # TODO: Eventually change to umu
                # target_pid = self.get_windows_pid(exe_filename)
                # if target_pid:
                #     self.cmd.append(f"-p{target_pid}")
                self._log_run_command(Path(self.prefix_info["runner"]))
                self.process = ExecutionManager.run(self.cmd, self.env, wait=False, cwd=self.game_dir)
            else:
                logger.debug("Launch texthooker through wine")
                if "textractor" in text_hooker_path.lower():
                    logger.info("Textractor detected, auto attaching to game")
                    self.cmd.append(f"-p{exe_filename}")
                self.process = ExecutionManager.run(self.cmd, self.env, wait=False, cwd=self.game_dir)
            
            return True
            
        except Exception as e:
            logging.error(f"run_texthooker failed: {e}")
            raise RuntimeError(f"Error running texthooker: {e}")

    def get_windows_pid(self, exe_name: str) -> str:
        """
        Queries the wine/proton prefix for the PID. 
        Uses the direct wine binary to avoid umu-run container overhead.
        Needed if running texthooker from umu instead of binary
        """
        import re
        try:
            # Skip umu here
            wine_bin = self.env.get("WINE")

            lookup_cmd = [wine_bin, "winedbg", "--command", "info process"]
            
            logger.debug(f"Querying PIDs with: {' '.join(lookup_cmd)}")
            
            result = subprocess.check_output(
                lookup_cmd, 
                env=self.env, 
                stderr=subprocess.STDOUT,
                timeout=5 
            )
            
            decoded_output = result.decode('utf-8', errors='ignore')
            logger.debug(decoded_output)

            # winedbg output: 
            # 00000020 3 'explorer.exe'
            # 000000f4 5 'AnEpic_unwrapped.exe'
            # PIDs in winedbg are HEXADECIMAL. need to convert it.
            
            for line in decoded_output.splitlines():
                if exe_name.lower() in line.lower():
                    # Find the hex PID
                    match = re.search(r'([0-9a-fA-F]+)', line.strip())
                    if match:
                        hex_pid = match.group(1)
                        decimal_pid = str(int(hex_pid, 16))
                        logger.debug(f"Found Windows PID (Hex: {hex_pid} -> Dec: {decimal_pid}) for {exe_name}")
                        return decimal_pid
                        
        except subprocess.TimeoutExpired:
            logger.error("PID lookup timed out")
        except Exception as e:
            logger.error(f"Failed to lookup Windows PID: {e}")
        
        return None
    
    def run(self, is_headless=False):
        """Prepares, logs, and executes the game"""
        self.load_data()
        try:
            # Only prepare if we haven't already
            if not self.cmd or not self.env:
                logger.debug("Calling self.prepare_environment()")
                self.prepare_environment()
        except Exception as e:
            logging.error(f"Preparation failed: {e}")
            raise RuntimeError(f"Preparation failed: {e}")

        if self.game.pre_launch_script_wait and self.game.pre_launch_script.strip():
            self._wait_for_process_then_run_script(self.game.pre_launch_script.strip(), os.path.basename(self.game.path))
        elif self.game.pre_launch_script.strip():
            self.run_external_script(self.game.pre_launch_script.strip())

        self._log_run_command(Path(self.prefix_info["runner"]))
        self.process = self._run_game_process(self.cmd, self.env, wait=False, cwd=self.game_dir, log_callback=self._add_log_line, detached=not is_headless, pass_fds=self.network_isolation_fds)
        # self.process = ExecutionManager.run(self.cmd, self.env, wait=False, cwd=self.game_dir, log_callback=self._add_log_line, detached=not is_headless, pass_fds=self.network_isolation_fds)
        logger.debug(f"Launched PID {self.process.pid} for game {self.game.path}")

        # Apply linux-rt-upscaler
        if self.settings.get(config.USER_CONF_RT_UPSCALER_ENABLED, False) and self.game.rtUpscaler.enabled == "true":
            self._launch_linux_rt_upscaler(os.path.basename(self.game.path))

        return True

    def _handle_wine(self, runner_path: Path) -> list:
        """Specific logic for Wine runners"""
        wine_bin = runner_path / "bin" / "wine"
        if not wine_bin.exists():
            logging.error(f"Wine binary missing at: {wine_bin}")
            return []
            
        self.env["WINE"] = str(wine_bin)
        self.env["PATH"] = f"{wine_bin.parent}:{self.env.get('PATH', '')}"
        
        return [str(wine_bin), self.game.path]

    def _handle_proton(self, runner_path: Path) -> list:
        """Specific logic for Proton runners"""
        self.env["PROTONPATH"] = str(runner_path)
        self.env["GAMEID"] = self.game.umu_gameid
        self.env["STORE"] = self.game.umu_store
        wine_bin = runner_path / "files" / "bin" / "wine"
        self.env["WINE"] = str(wine_bin)

        self.umu_path = SystemUtils.get_tool_path("umu-run")
        
        return [self.umu_path, self.game.path]

    def is_running(self) -> bool:
        """Checks if the specific game is active."""
        # Check the standard process handle first
        if self.process and self.process.poll() is None:
            return True
        
        # Actual check
        return self._is_game_process_in_proc()

    def _is_game_process_in_proc(self) -> bool:
        """
        Scans /proc to see if this specific game's EXE is running.
        """
        exe_name = Path(self.game.path).name
        prefix_path = self.env.get("WINEPREFIX", "")

        try:
            for pid_dir in Path("/proc").iterdir():
                if not pid_dir.name.isdigit():
                    continue
                
                try:
                    with open(pid_dir / "cmdline", "rb") as f:
                        cmdline = f.read().replace(b'\x00', b' ').decode(errors='ignore')
                    
                    if exe_name in cmdline:
                        with open(pid_dir / "environ", "rb") as f:
                            env = f.read()
                            if f"WINEPREFIX={prefix_path}".encode() in env:
                                return True
                                
                except (PermissionError, FileNotFoundError, ProcessLookupError):
                    continue
        except Exception as e:
            logging.error(f"Error scanning /proc: {e}")

        return False

    def stop(self, running_prefix_count = 1):
        """Gracefully attempts to terminate the running game process."""
        if not self.is_running():
            logging.info(f"Game '{self.name}' is not running.")
            return

        try:
            logging.info(f"Stopping game '{self.name}'...")
            self._kill_specific_prefix_processes_by_cmdline()
            runner_path = Path(self.prefix_info["runner"])

            if (running_prefix_count <= 1):
                # Only kill wineserver if 1 game left no not stop other running games in same prefix
                wineserver_bin = runner_path / ("files/bin/wineserver" if self.is_proton else "bin/wineserver")
                logging.debug(f"Calling _kill_wineserver proton {wineserver_bin} {runner_path}")
                self._kill_wineserver(wineserver_bin, runner_path)
        except Exception as e:
            logging.error(f"Error killing process {self.name}: {e}")

    def _kill_specific_prefix_processes(self):
        """Kills only the processes belonging to this specific game."""
        pids = self._get_game_pids()
        logger.debug(f"Killing PIDs for {self.game.name}: {pids}")
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue

    def _kill_specific_prefix_processes_by_cmdline(self):
        """Finds and kills all PIDs asociated to the game or umu."""
        prefix_path = self.env.get("WINEPREFIX", "")
        game_exe_name = Path(self.game.path).name
        if not prefix_path:
            return

        targets = [game_exe_name]
        logger.debug(f"_kill_specific_prefix_processes target {targets}")

        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            try:
                pid = int(pid_dir.name)
                if pid == os.getpid(): continue
                with open(pid_dir / "cmdline", "rb") as f:
                    cmdline = f.read().replace(b'\x00', b' ').decode(errors='ignore')
                    # If the cmdline mentions the game exe or umu
                    if any(t in cmdline for t in targets):
                        logging.debug(f"Killing by Cmdline ({game_exe_name}): {pid}")
                        os.kill(pid, signal.SIGKILL)
            except (PermissionError, FileNotFoundError, ProcessLookupError) as e:
                logger.debug(f"Error killing process {e}")
                continue

    def _kill_wineserver(self, wineserver_bin, runner_path): 
        """ Kills all processes associated with this prefix """
        if wineserver_bin.exists():
            logging.debug("[_kill_wineserver] wineserver_bin exists")
            subprocess.run([str(wineserver_bin), "-k"], env={"WINEPREFIX": self.env["WINEPREFIX"]})
        else:
            # Search for wineserver in the runner path
            logging.debug("[_kill_wineserver] wineserver_bin not found")
            found = list(runner_path.glob("**/bin/wineserver"))
            if found:
                wineserver_bin = found[0]
                subprocess.run([str(wineserver_bin), "-k"], env={"WINEPREFIX": self.env["WINEPREFIX"]})

    def _get_game_pids(self) -> list[int]:
        """Returns all PIDs matching this specific game EXE and this specific prefix."""
        prefix_path = self.env.get("WINEPREFIX", "")
        game_exe_name = Path(self.game.path).name
        target_env = f"WINEPREFIX={prefix_path}".encode()
        
        found_pids = []

        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit(): continue
            try:
                # 1. Check Prefix (Is this process in our WINEPREFIX?)
                with open(pid_dir / "environ", "rb") as f:
                    if target_env not in f.read().split(b'\x00'):
                        continue
                
                # 2. Check Identity (Is this our game EXE or its launcher?)
                with open(pid_dir / "cmdline", "rb") as f:
                    cmdline = f.read().replace(b'\x00', b' ').decode(errors='ignore')
                    # Match the EXE name OR the umu-run process for this specific EXE
                    if game_exe_name in cmdline:
                        found_pids.append(int(pid_dir.name))

            except (PermissionError, FileNotFoundError, ProcessLookupError):
                continue
        return found_pids

    def open_terminal(self, prefix_name: str):
        """Opens the system terminal with the game's environment pre-loaded."""
        # Manually fetch prefix info
        self.prefix_info = self._get_prefix_info(prefix_name)
        logger.debug(f"open_terminal {self.prefix_info}")

        if not self.prefix_info:
            raise ValueError(f"Prefix '{prefix_name}' not found.")

        self.game = GameCard(
            name=f"util-bash",
            path="",
            prefix=prefix_name,
            vndb="",
        )
        
        try:
            # Grab global env vars
            global_env_status = self.settings.get(config.USER_CONF_GLOBAL_VARIABLES, {})
            env_definitions = self.settings.get(config.USER_CONF_ENV_VARIABLE_LIST, config.ENV_VARIABLES)
            
            env_vars = {}
            for var in env_definitions:
                var_id = var.get("id")
                # Only add if the variable is toggled ON in global settings
                if global_env_status.get(var_id):
                    env_vars[var["key"]] = str(var["value"])

            self.game.envvar = env_vars
            
            self.prepare_environment()

            # Maybe useful
            self.env["RUN_GAME"] = " ".join(self.cmd)
            self.env["UMU_LOG"] = "1"

            # Find the user's terminal emulator
            term = SystemUtils.get_default_terminal()
            
            if not term:
                logging.error("Could not find a terminal emulator.")
                return False

            logging.debug(f"Opening {term} in {self.game_dir} with game environment.")
            self.process = ExecutionManager.run(term, self.env, wait=False, cwd=self.game_dir)
            return True
        except Exception as e:
            logging.error(f"Failed to open terminal: {e}")
            raise RuntimeError(f"Failed to open terminal: {e}")
    
    def _add_log_line(self, line):
        """Check for umu's download of steam runtime"""
        super()._add_log_line(line)
        if not self.is_proton:
            return
        if any(message in line for message in ("Setting up Unified Launcher for Windows Games on Linux", "Updating steamrt", "Restoring Runtime Platform")):
            umu_runtime_events.setup_started.emit(self.name)
        elif re.search(r"(?:Using steamrt\d|steamrt\d(?:-arm64)? is up to date)", line):
            umu_runtime_events.setup_finished.emit(self.name)

    def scrub_appimage_environment(self):
        """Remove APPIMAGE ENVIRONMENT when running a game"""
        appimage_vars = [
            "DESKTOP_STARTUP_ID",   # Icon thieft
            "XDG_ACTIVATION_TOKEN", # Wayland's equivalent of startup ID
            "APPDIR",               # Path to the mounted AppImage
            "APPIMAGE",             # Path to the AppImage file
            "ARGV0",                # Original command name
            "OWD"                   # Original Working Directory
        ]
        for var in appimage_vars:
            logger.debug(f"Removing {var}: {self.env.get(var)}")
            self.env.pop(var, None)
        
        if "LD_LIBRARY_PATH" in self.env:
            if SystemUtils.get_runtime_type() == "flatpak":
                logger.debug("Preserving Flatpak LD_LIBRARY_PATH for runtime and graphics extensions: %s",self.env["LD_LIBRARY_PATH"],)
            else:
                logger.debug(f"Removing LD_LIBRARY_PATH: {self.env.get('LD_LIBRARY_PATH')}")
                self.env.pop("LD_LIBRARY_PATH")

    def _log_run_command(self, runner_path: Path):
        """Logs the final configuration right before execution."""
        if SystemUtils.get_runtime_type() == "flatpak":
            gl32_root = Path("/app/lib/i386-linux-gnu/GL")
            gl32_files = list(gl32_root.glob("*/lib/dri/*_dri.so"))
            if gl32_files:
                logger.debug("Flatpak GL32 driver files detected: %s", ", ".join(str(path) for path in gl32_files),)
            else:
                logger.warning("No Flatpak GL32 DRI driver is mounted under %s; ""32-bit OpenGL and DXVK games may fail to launch.", gl32_root,)

        if self.settings.get(config.USER_CONF_LOG_LEVEL, "info").lower() == "debug":
            logging.debug("" + "="*60)
            logging.debug(f"LAUNCHING: {self.name}")
            logging.debug("="*60)
            logging.debug(f"Game Path:   {self.game.path}")
            logging.debug(f"Prefix Path: {self.env['WINEPREFIX']}")
            logging.debug(f"Runner:      {runner_path}")
            
            logging.debug("Environment Variables:")
            for var in self.env:
                logging.debug(f"   {var:<18}: {self.env[var]}")
            
            if self.game.envvar:
                logging.debug("Custom Vars:")
                for k, v in self.game.envvar.items():
                    logging.debug(f"   {k:<18}: {v}")

            logging.debug("Gamescope:")
            logging.debug(f"   Enabled:         {self.game.gamescope.enabled}")
            if self.game.gamescope.enabled.lower() == "true":
                logging.debug(f"   Parameters:      {self.game.gamescope.parameters}")

            logging.debug("Execution Command:")
            logging.debug(f"   {' '.join(self.cmd)}")
            logging.debug("="*60)

# Signal object to send events when umu is downloading steam runtime
class UmuRuntimeEvents(QObject):
    setup_started = Signal(str)
    setup_finished = Signal(str)

umu_runtime_events = UmuRuntimeEvents()