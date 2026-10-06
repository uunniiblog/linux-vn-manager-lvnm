import logging

import config
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)

# Display name shown in the prefix combo, path setting key, config setting key, runner type
EMULATOR_DEFINITIONS = [
    ("PSX", config.USER_CONF_EMULATION_PSX_PATH, config.USER_CONF_EMULATION_PSX_CONFIG, config.EMULATION_PSX),
    ("PS2", config.USER_CONF_EMULATION_PS2_PATH, config.USER_CONF_EMULATION_PS2_CONFIG, config.EMULATION_PS2),
    ("PS3", config.USER_CONF_EMULATION_PS3_PATH, config.USER_CONF_EMULATION_PS3_CONFIG, config.EMULATION_PS3),
    ("PSP", config.USER_CONF_EMULATION_PSP_PATH, config.USER_CONF_EMULATION_PSP_CONFIG, config.EMULATION_PSP),
    ("Switch", config.USER_CONF_EMULATION_SWITCH_PATH, config.USER_CONF_EMULATION_SWITCH_CONFIG, config.EMULATION_SWITCH),
]

EMULATOR_DISPLAY_NAMES = frozenset(display_name for display_name, _, _, _ in EMULATOR_DEFINITIONS)
PC98_DISPLAY_NAME = "PC-98"

class EmulationManager:
    """Create fake virtual prefixes for any emulator that has a path configured in Settings."""

    @staticmethod
    def get_virtual_prefixes() -> dict:
        settings = SettingsManager()
        emulation_settings = settings.get(config.USER_CONF_EMULATION, {})

        virtual_prefixes = {}
        for display_name, path_key, cli_key, runner_type in EMULATOR_DEFINITIONS:
            path = emulation_settings.get(path_key, "").strip()
            if not path:
                # Not configured don't show it as a selectable prefix
                continue

            virtual_prefixes[display_name] = {
                "type": runner_type,
                "path": path,
                "config": emulation_settings.get(cli_key, "").strip(),
                "virtual": True,
            }

        use_bundled = emulation_settings.get(config.USER_CONF_EMULATION_PC98_USE_BUNDLED, False)
        custom_path = emulation_settings.get(config.USER_CONF_EMULATION_PC98_PATH, "").strip()
        custom_core = emulation_settings.get(config.USER_CONF_EMULATION_PC98_CORE_PATH, "").strip()
        system_path = emulation_settings.get(config.USER_CONF_EMULATION_PC98_SYSTEM_PATH, str(config.PC98_SYSTEM_DIR / "np2kai")).strip()
        if use_bundled and config.PC98_BUNDLED_RETROARCH.is_file() and config.PC98_BUNDLED_CORE.is_file():
            virtual_prefixes[PC98_DISPLAY_NAME] = {
                "type": config.EMULATION_PC98,
                "path": str(config.PC98_BUNDLED_RETROARCH),
                "core": str(config.PC98_BUNDLED_CORE),
                "system_path": system_path,
                "config": emulation_settings.get(config.USER_CONF_EMULATION_PC98_CONFIG, "").strip(),
                "bundled": True,
                "virtual": True,
            }
        elif custom_path and custom_core:
            virtual_prefixes[PC98_DISPLAY_NAME] = {
                "type": config.EMULATION_PC98,
                "path": custom_path,
                "core": custom_core,
                "system_path": system_path,
                "config": emulation_settings.get(config.USER_CONF_EMULATION_PC98_CONFIG, "").strip(),
                "bundled": False,
                "virtual": True,
            }

        return virtual_prefixes

    @staticmethod
    def get_prefix_info(display_name: str) -> dict:
        return EmulationManager.get_virtual_prefixes().get(display_name)

    @staticmethod
    def get_emulator_prefixes() -> list[str]:
        """Returns a list of display names, including PC-98."""
        return list(EMULATOR_DISPLAY_NAMES | {PC98_DISPLAY_NAME})
    
    @staticmethod
    def is_emulated_game(game_card) -> bool:
        """Unused: True if this game's prefix is a virtual emulator prefix"""
        return game_card.prefix in EMULATOR_DISPLAY_NAMES or game_card.prefix == PC98_DISPLAY_NAME
