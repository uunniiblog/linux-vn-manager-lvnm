import os
import signal
import json
import config
import subprocess
import shutil
import shlex
import threading
import time
import logging
from pathlib import Path
from datetime import datetime
from collections import deque
from model.game_card import GameCard, GameScope
from execution_manager import ExecutionManager
from system_utils import SystemUtils
from settings_manager import SettingsManager
from timetracker.utils_factory import get_desktop_utils
from timetracker.system_utils import SystemUtils as TimeTrackUtils
from timetracker.x11_utils import X11Utils

logger = logging.getLogger(__name__)

class GameRunner:
    PREFIXES_DATA = Path(config.PREFIXES_DATA)
    GAME_DATA = Path(config.GAMES_DATA)

    def __init__(self, name: str, card_override: GameCard = None, is_steam=False):
        self.settings = SettingsManager()
        self.name = name
        self.game: GameCard = card_override
        self.prefix_info: dict = None
        self.env: dict = {}
        self.cmd: list = []
        self.is_steam = is_steam
        self.logs = deque(maxlen=2000)
        self.umu_path = None
        
        # Track running
        self.process = None 

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
        is_proton = "proton" in str(runner_path).lower()

        logger.debug(f"is_proton: {is_proton}")
        
        if is_proton:
            self.is_proton = True
            self.cmd = self._handle_proton(runner_path)
        else:
            self.is_proton = False
            self.cmd = self._handle_wine(runner_path)

        if not self.cmd:
            raise RuntimeError("Failed to build launch command.")

        if self.game.arguments.strip():
            extra_args = shlex.split(self.game.arguments.strip(), posix=False)
            self.cmd += extra_args

        # Apply pre launch arguments
        if self.game.pre_launch_args.strip():
            # self.cmd = [self.game.pre_launch_args.strip()] + self.cmd
            pre_args = shlex.split(self.game.pre_launch_args.strip())
            self.cmd = pre_args + self.cmd

        # Apply Gamescope Wrapper
        if self.game.gamescope.enabled.lower() == "true":
            gs_params = self.game.gamescope.parameters.split()
            self.cmd = ["gamescope"] + gs_params + ["--"] + self.cmd

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

            self._log_run_command(Path(self.prefix_info["runner"]))
            self.process = ExecutionManager.run(self.cmd, self.env, wait=False, cwd=self.game_dir)
            return True
            
        except Exception as e:
            logging.error(f"Run in prefix failed: {e}")
            raise RuntimeError(f"Run in prefix failed: {e}")

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
                self.prepare_environment()
        except Exception as e:
            logging.error(f"Preparation failed: {e}")
            raise RuntimeError(f"Preparation failed: {e}")

        if self.game.pre_launch_script_wait and self.game.pre_launch_script.strip():
            self._wait_for_game_then_run_script(self.game.pre_launch_script.strip())
        elif self.game.pre_launch_script.strip():
            self.run_external_script(self.game.pre_launch_script.strip())

        self._log_run_command(Path(self.prefix_info["runner"]))
        self.process = ExecutionManager.run(self.cmd, self.env, wait=False, cwd=self.game_dir, log_callback=self._add_log_line, detached=not is_headless)
        logger.debug(f"Launched PID {self.process.pid} for game {self.game.path}")

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

    def _get_game_card(self, name: str):
        if not GameRunner.GAME_DATA.exists():
            return None
        with open(GameRunner.GAME_DATA, "r", encoding="utf-8") as f:
            data = json.load(f)
            if name in data:
                return GameCard.from_dict(name, data[name])
        return None

    def _get_prefix_info(self, prefix_name: str):
        if not GameRunner.PREFIXES_DATA.exists():
            return None
        with open(GameRunner.PREFIXES_DATA, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(prefix_name)

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
    
    def run_external_script(self, script_path: str):
        """
        Executes a script in a fully detached state.
        """
        if not script_path or not os.path.exists(script_path.split()[0]):
            return

        logger.info(f"Executing external script: {script_path}")
        
        try:
            # Launch detached
            cmd = ["bash"] + shlex.split(script_path)
            logger.debug(f"run_external_script raw input : '{script_path}'")
            logger.debug(f"run_external_script shlex tokens: {shlex.split(script_path)}")
            logger.debug(f"run_external_script final cmd  : {cmd}")

            # Remove LD_PRELOAD to avoid issues with steam. Should not be needed for scripts
            env = self.env
            env.pop("LD_PRELOAD", None)

            subprocess.Popen(
                cmd,
                env=env,
                cwd=self.game_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
        except Exception as e:
            logger.error(f"Failed to launch script {script_path}: {e}")

    def _wait_for_game_then_run_script(self, script_path: str):
        """
        Spawns a background thread that polls until the game window is detected before calling run_external_script
        20 attemps to grab the pid and window id. If wayland game and x11 utils then use /proc fallback
        """
        utils = get_desktop_utils()
        process = os.path.basename(self.game.path)
        is_proton_wayland = self.env.get("PROTON_ENABLE_WAYLAND") == "1"
        def _is_game_running_poll():
            max_attempts = 20
            for attempt in range(1, max_attempts + 1):
                logger.info(f"_wait_for_game_then_run_script: Waiting for game process... attempt {attempt}/{max_attempts}")
                if is_proton_wayland and isinstance(utils, X11Utils):
                    if self.is_running():
                        logger.info(f"_wait_for_game_then_run_script: Game process detected after {attempt} attempt(s).")
                        time.sleep(2)
                        self.run_external_script(script_path)
                        return
                else:
                    pid = TimeTrackUtils.get_pid_by_name(process)
                    if pid:
                        wid, title = utils.find_window_by_pid(pid, process)
                        if wid and title:
                            logger.info(f"_wait_for_game_then_run_script: Window detected  '{title}' (WID: {wid}). after {attempt} attempt(s). Launching script.")
                            # headroom
                            time.sleep(0.5)                        
                            self.run_external_script(script_path)
                            return

                time.sleep(2)
            logger.error(f"_wait_for_game_then_run_script: Game process not found after {max_attempts} attempts. Script NOT launched.")

        t = threading.Thread(target=_is_game_running_poll, daemon=True, name="pre_launch_script_wait")
        t.start()
    
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
            logger.debug(f"Removing LD_LIBRARY_PATH: {self.env.get('LD_LIBRARY_PATH')}")
            self.env.pop("LD_LIBRARY_PATH")
        return var
    
    def _add_log_line(self, line):
        """Callback used by ExecutionManager"""
        self.logs.append(f"{datetime.today().strftime('%Y-%m-%d %H:%M:%S')} - {line}")

    def get_full_log(self):
        """Returns the entire buffer as a single string for a UI text box"""
        return "\n".join(self.logs)

    def _log_run_command(self, runner_path: Path):
        """Logs the final configuration right before execution."""
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