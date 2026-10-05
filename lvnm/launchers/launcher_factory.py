import logging
import config
from platform_profile import IS_WINDOWS
from model.game_card import GameCard
from game_manager import GameManager
from prefix_manager import PrefixManager
from launchers.launcher_base_game import LauncherBaseGame

logger = logging.getLogger(__name__)

def create_launcher(name: str, card_override: GameCard = None, is_steam: bool = False) -> LauncherBaseGame:
    """Decide how to run the games"""
    game = card_override or GameManager.get_game(name)
    if not game:
        raise ValueError(f"Game '{name}' not found in registry.")

    if IS_WINDOWS:
        from launchers.launcher_windows import LauncherWindows
        return LauncherWindows(name, card_override)

    prefix_info = PrefixManager.resolve_prefix_info(game.prefix)

    logger.debug(f"prefix_info {prefix_info}")
    runner_type = prefix_info.get("type", "wine")

    if runner_type == config.NATIVE:
        from launchers.launcher_native_game import LauncherNativeGame
        logger.debug(f"create_launcher: '{name}' -> LauncherNativeGame")
        return LauncherNativeGame(name, card_override)

    if runner_type.startswith("emulation-"):
        from launchers.launcher_emulator_game import LauncherEmulatorGame
        logger.debug(f"create_launcher: '{name}' -> LauncherEmulatorGame ({runner_type})")
        return LauncherEmulatorGame(name, card_override)

    if runner_type in ("wine", "proton"):
        from launchers.launcher_wine_game import LauncherWineGame
        logger.debug(f"create_launcher: '{name}' -> LauncherWineGame ({runner_type})")
        return LauncherWineGame(name, card_override, is_steam=is_steam)

    raise ValueError(f"Unsupported prefix type '{runner_type}' for game '{name}'.")
