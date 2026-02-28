import os
import signal
import json
import config
import subprocess
import shutil
import logging
logger = logging.getLogger(__name__)
from pathlib import Path
from datetime import datetime
from collections import deque
from model.game_card import GameCard
from execution_manager import ExecutionManager
from system_utils import SystemUtils
settings = SystemUtils.load_settings()

class GameRunner:
    PREFIXES_DATA = Path(config.PREFIXES_DATA)
    GAME_DATA = Path(config.GAMES_DATA)
    LOG_LEVEL = settings.get("log_level", "info")

    def __init__(self, name: str, card_override: GameCard = None, is_steam=False):
        self.name = name
        self.game: GameCard = card_override
        self.prefix_info: dict = None
        self.env: dict = {}
        self.cmd: list = []
        self.is_steam = is_steam
        self.logs = deque(maxlen=10000)
        
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
            raise ValueError(f"Prefix '{self.game.prefix}' (required for {self.name}) not found.")

    def prepare_environment(self):
        """Builds the environment and the final command list."""
        self.env = os.environ.copy()

        if self.is_steam:
            logging.info("Steam launch detected: removing LC_ALL...")
            # remove this since it fucks with locale for jp paths
            self.env.pop("LC_ALL", None)

        self.env["WINEPREFIX"] = self.prefix_info["path"]
        self.env["PWD"] = self.prefix_info["path"]

        if "wineconsole" or "util-bash" in self.game.name: 
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
        
        if is_proton:
            self.is_proton = True
            self.cmd = self._handle_proton(runner_path)
        else:
            self.is_proton = False
            self.cmd = self._handle_wine(runner_path)

        if not self.cmd:
            raise RuntimeError("Failed to build launch command.")

        # Apply Gamescope Wrapper
        if self.game.gamescope.enabled.lower() == "true":
            gs_params = self.game.gamescope.parameters.split()
            self.cmd = ["gamescope"] + gs_params + ["--"] + self.cmd

    def run_in_prefix(self, exe_path: str, prefix_name: str, env_vars: dict = None):
        """
        Bypasses JSON loading to run an arbitrary executable in a selected prefix.
        Useful for installers or utility stuff
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

            if env_vars:
                self.game.envvar = env_vars
            
            # Call same logic as run
            self.prepare_environment()
            self._log_run_command(Path(self.prefix_info["runner"]))
            self.process = ExecutionManager.run(self.cmd, self.env, wait=False, cwd=self.game_dir)
            return True
            
        except Exception as e:
            logging.error(f"Run in prefix failed: {e}")
            return False
    
    def run(self, is_headless=False):
        """Prepares, logs, and executes the game"""
        self.load_data()
        try:
            # Only prepare if we haven't already
            if not self.cmd or not self.env:
                self.prepare_environment()
        except Exception as e:
            logging.error(f"Preparation failed: {e}")
            return False

        self._log_run_command(Path(self.prefix_info["runner"]))
        self.process = ExecutionManager.run(self.cmd, self.env, wait=False, cwd=self.game_dir, log_callback=self._add_log_line, detached=not is_headless)

        logging.debug(f"self.process {self.process}")
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
        
        return ["umu-run", self.game.path]

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
        # return len(self._get_game_pids()) > 0

    def _is_game_process_in_proc(self) -> bool:
        """
        Scans /proc to see if this specific game's EXE is running.
        """
        # Get the filename (e.g., 'Demonbane.exe')
        exe_name = Path(self.game.path).name
        prefix_path = self.env.get("WINEPREFIX", "")

        try:
            for pid_dir in Path("/proc").iterdir():
                if not pid_dir.name.isdigit():
                    continue
                
                try:
                    # To be 100% sure, we check if the process belongs 
                    # to our prefix AND matches our EXE name
                    with open(pid_dir / "cmdline", "rb") as f:
                        cmdline = f.read().replace(b'\x00', b' ').decode(errors='ignore')
                    
                    if exe_name in cmdline:
                        # Optional: Verify it's the correct prefix to avoid false positives 
                        # if the user has the same game open in two different prefixes
                        with open(pid_dir / "environ", "rb") as f:
                            env = f.read()
                            if f"WINEPREFIX={prefix_path}".encode() in env:
                                return True
                                
                except (PermissionError, FileNotFoundError, ProcessLookupError):
                    continue
        except Exception as e:
            logging.error(f"Error scanning /proc: {e}")

        return False

    def _is_prefix_active(self) -> bool:
        """
        Check if any process is still running in the Wine prefix by scanning /proc.
        Unusued maybe useful later
        """
        prefix_path = self.env.get("WINEPREFIX", "")
        if not prefix_path:
            return False

        try:
            target = f"WINEPREFIX={prefix_path}".encode()
            for pid_dir in Path("/proc").iterdir():
                if not pid_dir.name.isdigit():
                    continue
                
                try:
                    environ_data = (pid_dir / "environ").read_bytes().split(b'\x00')
                    if target in environ_data:
                        logger.debug(f"target {target} in environ for game {self.game}")
                        return True
                except (PermissionError, FileNotFoundError, ProcessLookupError):
                    continue
        except Exception as e:
            logging.error(f"is_prefix_active error: {e}")

        return False

    def stop(self, running_prefix_count = 1):
        """Gracefully attempts to terminate the running game process."""
        if not self.is_running():
            logging.error(f"Game '{self.name}' is not running.")
            return

        try:
            logging.info(f"Stopping game '{self.name}'...")
            # pgid = os.getpgid(self.process.pid)
            # os.killpg(pgid, signal.SIGKILL)
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
            self.prepare_environment()
            logger.debug(self.name)

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
            return False
    
    def _add_log_line(self, line):
        """Callback used by ExecutionManager"""
        self.logs.append(f"{datetime.today().strftime('%Y-%m-%d %H:%M:%S')} - {line}")

    def get_full_log(self):
        """Returns the entire buffer as a single string for a UI text box"""
        return "\n".join(self.logs)

    def _log_run_command(self, runner_path: Path):
        """Logs the final configuration right before execution."""
        if GameRunner.LOG_LEVEL.lower() == "debug":
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