from __future__ import annotations

import config
import json
import logging
import shutil
import os
from pathlib import Path
from datetime import datetime
from prefix_manager import PrefixManager
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class SavedataManager:
    SAVEDATA_FOLDER_NAMES = ["savedata", "UserData", "save"]
    PREFIX_SAVEDATA_SEARCH_DIRS = [
        "drive_c/users/*/Saved Games",
        "drive_c/users/*/Documents",
        "drive_c/users/*/AppData/Roaming",
        "drive_c/users/*/AppData/LocalLow",
        "drive_c/users/*/AppData/Local",
    ]

    @staticmethod
    def copy_savedata_to_prefix(game_data: dict, prefix_name: str, overwrite: bool = False):
        """
        Copies a game's savedata folder into the equivalent location inside
        the target prefix, preserving the folder structure relative to the
        original prefix root.

        Only works for savedata that lives inside the game's current prefix
        Raises an exception if the savedata path is not actually inside the original prefix.
        """
        game_name = game_data.get("name", "")
        savedata_path = game_data.get("savedata_path", "")
        original_prefix_name = game_data.get("prefix", "")

        if not savedata_path:
            logging.error(f"No savedata path set for '{game_name}'. Cannot copy.")
            raise ValueError(f"No savedata path set for '{game_name}'.")

        src = Path(savedata_path)
        if not src.exists():
            logging.error(f"Savedata path does not exist: {src}")
            raise FileNotFoundError(f"Savedata path does not exist: {src}")

        # Resolve the ORIGINAL prefix (the one the savedata currently lives in)
        original_prefix_info = PrefixManager.get_prefix_info(original_prefix_name)
        if not original_prefix_info:
            logging.error(f"Original prefix '{original_prefix_name}' not found for '{game_name}'.")
            raise ValueError(f"Original prefix '{original_prefix_name}' not found.")

        original_prefix_path = Path(os.path.abspath(original_prefix_info.get("path", "")))

        # Resolve the TARGET prefix (where we're copying to)
        target_prefix_info = PrefixManager.get_prefix_info(prefix_name)
        if not target_prefix_info:
            logging.error(f"Target prefix '{prefix_name}' not found. Cannot copy savedata.")
            raise ValueError(f"Target prefix '{prefix_name}' not found.")

        target_prefix_path = Path(target_prefix_info.get("path", "")).resolve()
        logger.debug(f"Target prefix path: {target_prefix_path}")

        if not target_prefix_path.exists():
            logging.error(f"Target prefix path does not exist: {target_prefix_path}")
            raise FileNotFoundError(f"Target prefix path does not exist: {target_prefix_path}")

        # Ensure the savedata path is actually inside the original prefix,
        resolved_src = Path(os.path.abspath(src))
        try:
            rel_path = resolved_src.relative_to(original_prefix_path)
            logger.debug(f"rel_path {rel_path}")
        except ValueError:
            logging.error(
                f"Savedata path '{resolved_src}' is not inside the original prefix "
                f"'{original_prefix_path}'. Cannot copy."
            )
            raise ValueError(f"Savedata path is not inside the original prefix: {original_prefix_name}")

        dest = target_prefix_path / rel_path

        # Check whether the target already has savedata for this game
        if dest.exists() and not overwrite:
            logging.warning(f"Savedata already exists at destination: {dest}")
            raise FileExistsError(
                f"Savedata for '{game_name}' already exists in prefix '{prefix_name}'."
            )

        # Create target dest and copy files
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest)

            logging.info(f"Copied savedata for '{game_name}' to prefix '{prefix_name}' ({dest})")
            return True
        except Exception as e:
            logging.error(f"Failed to copy savedata for '{game_name}' to '{prefix_name}': {e}")
            raise RuntimeError(f"Failed to copy savedata: {e}")

    @staticmethod
    def auto_detect_savedata_folder(game_data: dict) -> str | None:
        """
        Attempts to automatically locate a game's savedata folder.
        Looks inside the game's own install folder (next to the .exe) for
           a folder matching one of SAVEDATA_FOLDER_NAMES.
        Searches common savedata locations inside the game's
           Wine/Proton prefix for a folder named after the game or its executable.
        """
        game_name = game_data.get("name", "")
        game_og_name = game_data.get("ogtitle", "")
        game_path = game_data.get("path", "")
        prefix_name = game_data.get("prefix", "")

        if not game_path:
            logging.warning(f"No game path set for '{game_name}'. Cannot auto-detect savedata.")
            return None

        exe_path = Path(game_path)
        exe_stem = exe_path.stem
        install_dir = exe_path.parent

        # Search next to the game's executable
        if install_dir.exists():
            target_folder_names = {n.lower() for n in SavedataManager.SAVEDATA_FOLDER_NAMES}
            for child in install_dir.iterdir():
                if child.is_dir() and child.name.lower() in target_folder_names:
                    logger.debug(f"Found savedata folder next to exe: {child}")
                    return str(child)

        # Search inside the prefix
        prefix_info = PrefixManager.get_prefix_info(prefix_name)
        if not prefix_info:
            logging.warning(f"Prefix '{prefix_name}' not found for '{game_name}'. Cannot search prefix.")
            return None

        prefix_path = Path(prefix_info.get("path", ""))
        if not prefix_path.exists():
            logging.warning(f"Prefix path does not exist: {prefix_path}")
            return None

        target_names = {game_name.lower(), exe_stem.lower(), game_og_name.lower()}
        target_names.discard("")

        candidates = []

        for pattern in SavedataManager.PREFIX_SAVEDATA_SEARCH_DIRS:
            for base_dir in prefix_path.glob(pattern):
                if not base_dir.is_dir():
                    continue
                for found_dir in base_dir.rglob("*"):
                    if found_dir.is_dir() and found_dir.name.lower() in target_names:
                        candidates.append(found_dir)

        if not candidates:
            logger.debug(f"No savedata folder found in prefix for '{game_name}'.")
            return None

        # Prefer the most deeply nested match (most specific location)
        candidates.sort(key=lambda p: len(p.parts), reverse=True)
        best_match = candidates[0]
        logger.debug(f"Found savedata folder in prefix: {best_match}")
        return str(best_match)

    @staticmethod
    def try_auto_detect_savedata(name: str, game_card) -> bool:
        """
        If auto-detect is enabled in settings and the game has no savedata_path
        set yet, tries to auto-detect it. Updates game_card in place if a path
        is found. Returns True if game_card was modified.
        """
        savedata_settings = SettingsManager().get(config.USER_CONF_SAVEDATA, {})
        if not savedata_settings.get("auto_detect_save", False):
            return False

        if game_card.savedata_path:
            return False

        detected_path = SavedataManager.auto_detect_savedata_folder(game_card.to_dict())
        if detected_path:
            logger.info(f"Auto-detected savedata folder for '{name}': {detected_path}")
            game_card.savedata_path = detected_path
            return True

        logger.warning(f"Could not auto-detect savedata folder for '{name}'.")
        return False

