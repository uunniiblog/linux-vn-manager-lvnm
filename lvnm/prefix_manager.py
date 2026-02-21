import os
import subprocess
import json
import shutil
import config
from pathlib import Path
from model.prefix import Prefix
from execution_manager import ExecutionManager


class PrefixManager:
    CODEC_SH = config.CODEC_SCRIPT
    DATA_ROOT = config.PREFIXES_DIR
    PREFIXES_FILE = config.PREFIXES_DATA

    def __init__(self, name: str):
        self.name = name
        self.prefix_path = self.DATA_ROOT / name
        self.runner_path = None
        self.type = None
        self.codecs = ""
        self.env = os.environ.copy()
        self.env["WINEPREFIX"] = str(self.prefix_path)
        
        # Automatically load data if it exists
        self._load_from_json()

    def _load_from_json(self):
        """Attempts to populate object attributes from the JSON file."""
        info = self.get_prefix_info(self.name)
        if info:
            self.card = Prefix.from_dict(self.name, info)
            self.runner_path = Path(self.card.runner)
            self.type = self.card.type
            self.codecs = self.card.codecs
            self.winetricks = self.card.winetricks
            self._setup_env()
            return True

        print(f"Prefix {self.name} does not exist yet")
        return False

    def _setup_env(self):
        """Configures the environment based on current runner_path and type."""
        if not self.runner_path:
            return

        if self.type == "proton":
            self.env["PROTONPATH"] = str(self.runner_path)
            self.env["GAMEID"] = "umu-default"
            self.env["STORE"] = "none"
            self.runner_command = ["umu-run"]
        else:
            wine_bin = self.runner_path / "bin" / "wine"
            self.env["WINE"] = str(wine_bin)
            self.env["PATH"] = f"{wine_bin.parent}:{self.env.get('PATH', '')}"
            self.runner_command = [str(wine_bin)]

    def create_prefix(self, runner_path: str, codecs: str = "", winetricks: str = ""):
        """Physical creation and initialization of the prefix."""
        print(f"--- Creating Prefix: {self.name} ---")
        self.runner_path = Path(runner_path)
        self.type = "proton" if "proton" in str(self.runner_path).lower() else "wine"
        self.codecs = codecs
        self.winetricks = winetricks
        self._setup_env()

        try:
            self.prefix_path.mkdir(parents=True, exist_ok=True)
            
            print("Initializing prefix (wineboot)...")
            cmd = self.runner_command + ["wineboot", "-u"]
            #ProcessLogger.run(cmd, self.env)
            ExecutionManager.run(cmd, self.env, wait=True)

            if self.codecs:
                self.install_codecs(self.codecs)

            if self.winetricks:
                self.install_winetricks(self.winetricks)

            self._save_metadata()
            print(f"Prefix {self.name} ready.")
            return True

        except Exception as e:
            print(f"[Error] Creation failed: {e}")
            # Clean up if it's a 'zombie' prefix (dir exists but no drive_c)
            if self.prefix_path.exists() and not (self.prefix_path / "drive_c").exists():
                shutil.rmtree(self.prefix_path)
            return False

    def install_codecs(self, codecs_list: str):
        """Installs or updates codecs in an existing prefix."""
        if not self.CODEC_SH.exists():
            print(f"Warning: Codec script missing at {self.CODEC_SH}")
            return False

        print(f"Installing codecs into {self.name}: {codecs_list}")
        cmd = ["sh", str(self.CODEC_SH)] + codecs_list.split()

        #ProcessLogger.run(cmd, self.env, suppress_codes=[1])
        ExecutionManager.run(cmd, self.env, wait=True, suppress_codes=[1])
        
        # Update local state and save
        new_codecs = set(self.codecs.split()) | set(codecs_list.split())
        self.codecs = " ".join(sorted(new_codecs))
        self._save_metadata()
        return True

    def install_winetricks(self, winetricks_list: str):
        """Installs winetricks components into the prefix."""
        winetricks_bin = shutil.which("winetricks")
        if not winetricks_bin:
            print("[Error] winetricks not found in PATH.")
            return False

        print(f"Installing winetricks into {self.name}: {winetricks_list}")
        cmd = [winetricks_bin, "-q", "--unattended"] + winetricks_list.split()

        ExecutionManager.run(cmd, self.env, wait=True)
        
        # Update local state and save
        new_tricks = set(self.winetricks.split()) | set(winetricks_list.split())
        self.winetricks = " ".join(sorted(new_tricks))
        self._save_metadata()
        return True

    def add_fonts(self, fonts_source_path: str):
        """Links fonts from a source folder into the Wine prefix."""
        target_dir = self.prefix_path / "drive_c" / "windows" / "Fonts"
        source_path = Path(fonts_source_path)
        
        if not target_dir.exists():
            print(f"Error: Prefix {self.name} doesn't seem to be initialized (no Font dir).")
            return False

        for font in source_path.iterdir():
            if font.is_file():
                dest = target_dir / font.name
                if not dest.exists():
                    os.symlink(font, dest)
        print(f"Fonts linked to {self.name}")
        return True

    def _save_metadata(self):
        """Writes current state to the json file."""
        self.DATA_ROOT.mkdir(parents=True, exist_ok=True)
        json_file = {}
        
        if self.PREFIXES_FILE.exists():
            with open(self.PREFIXES_FILE, "r") as f:
                try:
                    json_file = json.load(f)
                except json.JSONDecodeError: pass

        card = Prefix(
            name=self.name,
            path=str(self.prefix_path),
            runner=str(self.runner_path),
            type=self.type,
            codecs=self.codecs,
            winetricks=self.winetricks
        )
        json_file[self.name] = card.to_dict()

        with open(self.PREFIXES_FILE, "w") as f:
            json.dump(json_file, f, indent=4)

    def delete_prefix(self):
        """Wipes the folder and removes from json."""
        if self.prefix_path.exists():
            shutil.rmtree(self.prefix_path)
            
        if self.PREFIXES_FILE.exists():
            with open(self.PREFIXES_FILE, "r") as f:
                json_file = json.load(f)
            if self.name in json_file:
                del json_file[self.name]
                with open(self.PREFIXES_FILE, "w") as f:
                    json.dump(json_file, f, indent=4)
        return True

    def rename_prefix(self, new_name: str):
        """Renames the prefix folder and updates the json entry."""
        if self.get_prefix_info(new_name):
            print(f"Error: A prefix named '{new_name}' already exists in the json_file.")
            return False

        from game_manager import GameManager
        old_name = self.name
        old_path = self.prefix_path
        new_path = self.DATA_ROOT / new_name

        try:
            # Rename directory
            if old_path.exists():
                old_path.rename(new_path)
                print(f"Directory renamed: {old_path.name} -> {new_path.name}")
            else:
                print(f"[Debug] Physical path {old_path} not found, updating json_file only.")

            # Update variables
            self.name = new_name
            self.prefix_path = new_path
            self.env["WINEPREFIX"] = str(new_path)

            # Rewrite json file
            if self.PREFIXES_FILE.exists():
                with open(self.PREFIXES_FILE, "r") as f:
                    try:
                        json_file = json.load(f)
                    except json.JSONDecodeError:
                        json_file = {}

                if old_name in json_file:
                    # Extract the old data and update the specific fields
                    prefix_data = json_file.pop(old_name)
                    prefix_data["name"] = new_name
                    prefix_data["path"] = str(new_path)
                    
                    # Insert under the new key
                    json_file[new_name] = prefix_data

                    with open(self.PREFIXES_FILE, "w") as f:
                        json.dump(json_file, f, indent=4)
                    
                    print(f"json_file updated: '{old_name}' is now '{new_name}'")
                    
                    # Update games to new prefix name
                    GameManager.update_prefix_references(old_name, new_name)

            return True

        except Exception as e:
            print(f"[Error] Failed to rename prefix: {e}")
            return False

    @staticmethod
    def get_prefix_info(name: str):
        if not Path(config.PREFIXES_DATA).exists():
            return None
        with open(config.PREFIXES_DATA, "r") as f:
            return json.load(f).get(name)