import os
import json
import config
from pathlib import Path
from model.game_card import GameCard
from process_logger import ProcessLogger
# import subprocess # Depending on how ProcessLogger is implemented

class GameRunner:
    PREFIXES_DATA = Path(config.PREFIXES_DATA)
    GAME_DATA = Path(config.GAMES_DATA)
    LOG_LEVEL = config.LOG_LEVEL

    def __init__(self, name: str):
        self.name = name
        self.game: GameCard = None
        self.prefix_info: dict = None
        self.env: dict = {}
        self.cmd: list = []
        
        # The "worker" reference to track the running process
        self.process = None 

        # Attempt to load data immediately upon instantiation
        self._load_data()

    def _load_data(self):
        """Loads game and prefix data into the instance."""
        self.game = self._get_game_card(self.name)
        if not self.game:
            raise ValueError(f"Game '{self.name}' not found in registry.")

        self.prefix_info = self._get_prefix_info(self.game.prefix)
        if not self.prefix_info:
            raise ValueError(f"Prefix '{self.game.prefix}' (required for {self.name}) not found.")

    def prepare(self):
        """Builds the environment and the final command list."""
        self.env = os.environ.copy()
        self.env["WINEPREFIX"] = self.prefix_info["path"]
        
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
            self.cmd = self._handle_proton(runner_path)
        else:
            self.cmd = self._handle_wine(runner_path)

        if not self.cmd:
            raise RuntimeError("Failed to build launch command.")

        # Apply Gamescope Wrapper
        if self.game.gamescope.enabled.lower() == "true":
            gs_params = self.game.gamescope.parameters.split()
            self.cmd = ["gamescope"] + gs_params + ["--"] + self.cmd

    def run(self):
        """Prepares, logs, and executes the game, keeping a reference to the worker."""
        try:
            # Only prepare if we haven't already
            if not self.cmd or not self.env:
                self.prepare()
        except Exception as e:
            print(f"[Error] Preparation failed: {e}")
            return False

        self._log_run_command(Path(self.prefix_info["runner"]))

        self.process = ProcessLogger.run(self.cmd, self.env)
        print(f"self.process {self.process}")
        return True

    def is_running(self) -> bool:
        """Checks if the game process is currently active."""
        # TODO

    def stop(self):
        """Gracefully attempts to terminate the running game process."""
        if self.is_running():
            print(f"Stopping game '{self.name}'...")
            self.process.terminate()
            # self.process.kill() # Use kill() if terminate() is too weak
        else:
            print(f"Game '{self.name}' is not currently running.")

    def _handle_wine(self, runner_path: Path) -> list:
        """Specific logic for Wine runners"""
        wine_bin = runner_path / "bin" / "wine"
        if not wine_bin.exists():
            print(f"[Error] Wine binary missing at: {wine_bin}")
            return []
            
        self.env["WINE"] = str(wine_bin)
        self.env["PATH"] = f"{wine_bin.parent}:{self.env.get('PATH', '')}"
        
        return [str(wine_bin), self.game.path]

    def _handle_proton(self, runner_path: Path) -> list:
        """Specific logic for Proton runners"""
        self.env["PROTONPATH"] = str(runner_path)
        self.env["GAMEID"] = self.game.umu_gameid
        self.env["STORE"] = self.game.umu_store

        if GameRunner.LOG_LEVEL.lower() != "debug":
            self.env["STEAM_LINUX_RUNTIME_VERBOSE"] = "0"
            self.env["G_MESSAGES_DEBUG"] = ""
            self.env["PRESSURE_VESSEL_VERBOSE"] = "0"
        
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

    def _log_run_command(self, runner_path: Path):
        """Logs the final configuration right before execution."""
        if GameRunner.LOG_LEVEL.lower() == "debug":
            print("\n" + "="*60)
            print(f"LAUNCHING: {self.name}")
            print("="*60)
            print(f"Game Path:   {self.game.path}")
            print(f"Prefix Path: {self.env['WINEPREFIX']}")
            print(f"Runner:      {runner_path}")
            
            print("\nEnvironment Variables:")
            for var in self.env:
                print(f"   {var:<18}: {self.env[var]}")
            
            if self.game.envvar:
                print("Custom Vars:")
                for k, v in self.game.envvar.items():
                    print(f"   {k:<18}: {v}")

            print("\nGamescope:")
            print(f"   Enabled:         {self.game.gamescope.enabled}")
            if self.game.gamescope.enabled.lower() == "true":
                print(f"   Parameters:      {self.game.gamescope.parameters}")

            print("\nExecution Command:")
            print(f"   {' '.join(self.cmd)}")
            print("="*60 + "\n")