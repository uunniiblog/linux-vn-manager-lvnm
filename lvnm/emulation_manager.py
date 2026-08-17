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

        return virtual_prefixes

    @staticmethod
    def get_prefix_info(display_name: str) -> dict:
        return EmulationManager.get_virtual_prefixes().get(display_name)

    @staticmethod
    def get_emulator_prefixes() -> list[str]:
        """Returns a list of display names ['PSX', 'PS2', 'PS3', 'PSP', 'Switch']."""
        return [display_name for display_name, _, _, _ in EMULATOR_DEFINITIONS]