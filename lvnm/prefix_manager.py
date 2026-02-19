import os
import subprocess
import json
import shutil
import config
from process_logger import ProcessLogger
from pathlib import Path

class PrefixManager:
    BASE_DIR = Path(__file__).parent.resolve()
    CODEC_SH = config.CODEC_SCRIPT
    DATA_ROOT = config.PREFIXES_DIR
    REGISTRY_FILE = config.PREFIXES_DATA

    def __init__(self, name, codecs, runner_path):
        self.name = name
        self.codecs = codecs
        self.runner_path = Path(runner_path)
        self.prefix_path = self.DATA_ROOT / name
        self.env = os.environ.copy()
        self.env["WINEPREFIX"] = str(self.prefix_path)

        try:
            # Determine runner type and configure environment
            if 'proton' in str(self.runner_path).lower():
                self._setup_umu()
            else:
                self._setup_wine()

            # Prepare directory
            self.prefix_path.mkdir(parents=True, exist_ok=True)

            # Create prefix
            self._initialize_prefix()
            
            # Install codecs with vn_winestuff
            if self.codecs:
                self._run_codecs()

            # Save json with current prefixes
            self._save_metadata()
            
            print(f"--- Prefix {self.name} successfully created ---")

        except Exception as e:
            print(f"\n[FATAL ERROR] Creation failed: {e}")
            # Clean up partial prefix if drive_c wasn't even created
            if self.prefix_path.exists() and not (self.prefix_path / "drive_c").exists():
                shutil.rmtree(self.prefix_path)


    def _setup_umu(self):
        """Setup env vars for Proton/UMU"""
        self.env["PROTONPATH"] = str(self.runner_path)
        self.env["GAMEID"] = "umu-default"
        self.env["STORE"] = "none"
        self.env["WINE"] = "umu-run"
        self.runner_command = ["umu-run"]

    def _setup_wine(self):
        """Setup env vars for Standard Wine"""
        wine_bin = self.runner_path / "bin" / "wine"
        if not wine_bin.exists():
            raise FileNotFoundError(f"Wine binary not found at {wine_bin}")
        
        self.env["WINE"] = str(wine_bin)
        self.runner_command = [str(wine_bin)]
        self.env["PATH"] = f"{wine_bin.parent}:{self.env.get('PATH', '')}"

    def _initialize_prefix(self):
        """Builds the prefix using wineboot"""
        print("Initializing prefix (wineboot)...")
        cmd = self.runner_command + ["wineboot", "-u"]
        
        ProcessLogger.run(cmd, self.env)

    def _run_codecs(self):
        """Installs codecs via external script"""
        if not self.CODEC_SH.exists():
            print(f"Warning: Codec script missing at {self.CODEC_SH}")
            return

        print(f"Installing codecs: {self.codecs}")
        cmd = ["sh", str(self.CODEC_SH)] + self.codecs.split()

        ProcessLogger.run(cmd, self.env, suppress_codes=[1])
        print("Codecs installation completed.")

    def _save_metadata(self):
        self.DATA_ROOT.mkdir(parents=True, exist_ok=True)
        registry = {}
        
        if self.REGISTRY_FILE.exists():
            try:
                with open(self.REGISTRY_FILE, "r") as f:
                    registry = json.load(f)
            except json.JSONDecodeError:
                pass

        registry[self.name] = {
            "name": self.name,
            "path": str(self.prefix_path),
            "runner": str(self.runner_path),
            "type": "proton" if "PROTONPATH" in self.env else "wine",
            "codecs": self.codecs,
        }

        with open(self.REGISTRY_FILE, "w") as f:
            json.dump(registry, f, indent=4)
        print(f"Registry updated: {self.REGISTRY_FILE}")

    def delete_prefix(self):
        """Deletes the prefix folder"""
        # TODO: add validation if games with prefix active
        # Remove the directory
        if self.prefix_path.exists():
            shutil.rmtree(self.prefix_path)
            print(f"Deleted folder: {self.prefix_path}")

        # Update the JSON registry
        if self.REGISTRY_FILE.exists():
            with open(self.REGISTRY_FILE, "r") as f:
                registry = json.load(f)
            
            if self.name in registry:
                del registry[self.name]
                with open(self.REGISTRY_FILE, "w") as f:
                    json.dump(registry, f, indent=4)
                print(f"Removed '{self.name}' from registry.")
        
        return True

    def add_fonts(self, fonts_source_path):
        """ Links fonts from a source folder into the Wine prefix """
        target_dir = self.prefix_path / "drive_c" / "windows" / "Fonts"
        source_path = Path(fonts_source_path)
        
        if not source_path.exists():
            print("Source fonts path does not exist.")
            return False

        for font in source_path.iterdir():
            if font.is_file():
                dest = target_dir / font.name
                if not dest.exists():
                    os.symlink(font, dest)
        return True

    @staticmethod
    def get_prefix_info(name):
        """Returns the dictionary for a specific prefix if it exists"""
        if not Path(config.PREFIXES_DATA).exists():
            return None
            
        try:
            with open(config.PREFIXES_DATA, "r") as f:
                registry = json.load(f)
                return registry.get(name)
        except (json.JSONDecodeError, FileNotFoundError):
            return None