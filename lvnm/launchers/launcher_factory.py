import json
import logging
from pathlib import Path

import config
from model.game_card import GameCard
from game_manager import GameManager
from emulation_manager import EmulationManager
from launchers.launcher_base_game import LauncherBaseGame
from launchers.launcher_wine_game import LauncherWineGame
from launchers.launcher_emulator_game import LauncherEmulatorGame

logger = logging.getLogger(__name__)

PREFIXES_DATA = Path(config.PREFIXES_DATA)

def create_launcher(name: str, card_override: GameCard = None, is_steam: bool = False) -> LauncherBaseGame:
    """Decide how to run the games"""
    game = card_override or GameManager.get_game(name)
    if not game:
        raise ValueError(f"Game '{name}' not found in registry.")

    prefix_info = _get_prefix_info(game.prefix)
    logger.debug(f"prefix_info {prefix_info}")
    runner_type = prefix_info.get("type", "wine")

    if runner_type.startswith("emulation-"):
        logger.debug(f"create_launcher: '{name}' -> LauncherEmulatorGame ({runner_type})")
        return LauncherEmulatorGame(name, card_override)

    logger.debug(f"create_launcher: '{name}' -> LauncherWineGame ({runner_type})")
    return LauncherWineGame(name, card_override, is_steam=is_steam)


def _get_prefix_info(prefix_name: str) -> dict:
    real = {}
    if PREFIXES_DATA.exists():
        with open(PREFIXES_DATA, "r", encoding="utf-8") as f:
            real = json.load(f)
    return {**real, **EmulationManager.get_virtual_prefixes()}.get(prefix_name)
