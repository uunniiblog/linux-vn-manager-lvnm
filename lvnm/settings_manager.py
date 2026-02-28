import json
import os
import logging
import config
from pathlib import Path

logger = logging.getLogger(__name__)

class SettingsManager:
    _instance = None
    _settings = {}
    SETTINGS_FILE = config.USER_SETTINGS

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._load_from_disk()
        return cls._instance

    def _load_from_disk(self):
        """Internal method to load disk data into memory ONCE."""
        if self.SETTINGS_FILE.exists():
            try:
                with open(self.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    self._settings = json.load(f)
                logger.info("Settings loaded into memory.")
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")
                self._settings = {}
        else:
            self._settings = {}

    def get(self, key, default=None):
        """Fast RAM-based lookup."""
        return self._settings.get(key, default)

    def set(self, key, value):
        """Update memory and trigger a save."""
        self._settings[key] = value
        self._save_to_disk()

    def _save_to_disk(self):
        """Persist memory state to disk."""
        try:
            self.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")