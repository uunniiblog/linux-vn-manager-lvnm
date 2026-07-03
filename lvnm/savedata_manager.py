from __future__ import annotations

import config
import json
import logging
import shutil
from pathlib import Path
from datetime import datetime
from prefix_manager import PrefixManager

logger = logging.getLogger(__name__)

class SavedataManager:

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

        original_prefix_path = Path(original_prefix_info.get("path", "")).resolve()

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
        resolved_src = src.resolve()
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

