from __future__ import annotations

import config
import json
import logging
import shutil
import os
from PySide6.QtCore import QThread, Signal, QObject
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timezone
from prefix_manager import PrefixManager
from settings_manager import SettingsManager
from gdrive_manager import GdriveManager

logger = logging.getLogger(__name__)

class SavedataManager(QObject):
    _instance = None

    SAVEDATA_FOLDER_NAMES = ["savedata", "UserData", "save"]
    PREFIX_SAVEDATA_SEARCH_DIRS = [
        "drive_c/users/*/Saved Games",
        "drive_c/users/*/Documents",
        "drive_c/users/*/AppData/Roaming",
        "drive_c/users/*/AppData/LocalLow",
        "drive_c/users/*/AppData/Local",
    ]

    DELETION_SAFETY_THRESHOLD = 0.5

    gdrive_sync_succeeded = Signal(str, dict)
    gdrive_sync_failed = Signal(str, str)

    @classmethod
    def get_instance(cls):
        """Singleton instance accessor"""
        if cls._instance is None:
            cls._instance = SavedataManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._gdrive_sync_workers = {}
        self.user_settings = SettingsManager()
        self.savedata_settings = self.user_settings.get(config.USER_CONF_SAVEDATA, {})

    def start_gdrive_sync(self, name: str, game_data: dict):
        """Runs the Gdrive sync in a background thread so it doesn't block the UI."""
        if not self.savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False):
            return

        # Safety guard: Prevent launching duplicate threads for the same game
        if name in self._gdrive_sync_workers:
            logger.warning(f"Gdrive sync already in progress for '{name}'. Skipping duplicate request.")
            return

        worker = GdriveSyncWorker(game_data)
        worker.sync_succeeded.connect(self._on_gdrive_sync_succeeded)
        worker.sync_failed.connect(self._on_gdrive_sync_failed)
        worker.finished.connect(lambda: self._gdrive_sync_workers.pop(name, None))

        self._gdrive_sync_workers[name] = worker  # Retain reference against GC
        worker.start()

    def _on_gdrive_sync_succeeded(self, name: str, result: dict):
        logger.info(f"Gdrive sync completed for '{name}': {result}")
        self.gdrive_sync_succeeded.emit(name, result)

    def _on_gdrive_sync_failed(self, name: str, error_message: str):
        self.gdrive_sync_failed.emit(name, error_message)

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

        # Remap the username segment steamuser <-> real Linux user
        rel_path = SavedataManager._remap_user_segment(rel_path, target_prefix_path)
        logger.debug(f"remapped rel_path: {rel_path}")
        
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
    def _get_prefix_user_dir(prefix_path: Path) -> str | None:
        """
        Returns the single real user folder name under drive_c/users in a prefix
        (excluding 'Public'). Proton prefixes have both 'steamuser' and the real
        username pointing at the same location, so either is fine to use; plain
        Wine prefixes only have the real username. Returns None if not found.
        """
        users_dir = prefix_path / "drive_c" / "users"
        if not users_dir.exists():
            return None

        candidates = [d.name for d in users_dir.iterdir() if d.is_dir() and d.name.lower() != "public"]
        if not candidates:
            return None

        # Prefer 'steamuser' if present (Proton), otherwise just take whichever one exists
        return next((u for u in candidates if u.lower() == "steamuser"), candidates[0])

    @staticmethod
    def _remap_user_segment(rel_path: Path, target_prefix_path: Path) -> Path:
        """
        If rel_path starts with drive_c/users/<username>/..., swaps <username>
        for whatever user folder actually exists in the TARGET prefix.
        """
        parts = rel_path.parts
        if len(parts) < 3 or parts[0] != "drive_c" or parts[1] != "users":
            return rel_path  # not a per-user path, nothing to remap

        target_user = SavedataManager._get_prefix_user_dir(target_prefix_path)
        if not target_user:
            logger.warning(f"No user folder found in target prefix '{target_prefix_path}'; using path as-is.")
            return rel_path

        if target_user != parts[2]:
            logger.info(f"Remapping savedata user segment: '{parts[2]}' -> '{target_user}'")

        return Path(*parts[:2], target_user, *parts[3:])

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
        if game_card.savedata_path or not savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False):
            return False

        detected_path = SavedataManager.auto_detect_savedata_folder(game_card.to_dict())
        if detected_path:
            logger.info(f"Auto-detected savedata folder for '{name}': {detected_path}")
            game_card.savedata_path = detected_path
            return True

        logger.warning(f"Could not auto-detect savedata folder for '{name}'.")
        return False

    @staticmethod
    def is_savedata_inside_prefix(game_data: dict) -> bool:
        """Checks whether the game's savedata_path currently lives inside its own prefix folder."""
        savedata_path = game_data.get("savedata_path", "")
        prefix_name = game_data.get("prefix", "")
        if not savedata_path or not prefix_name:
            return False
        prefix_info = PrefixManager.get_prefix_info(prefix_name)
        if not prefix_info:
            return False
        prefix_path = Path(os.path.abspath(prefix_info.get("path", "")))
        resolved_src = Path(os.path.abspath(savedata_path))
        try:
            resolved_src.relative_to(prefix_path)
            return True
        except ValueError:
            return False

    @staticmethod
    def sync_savedata_to_gdrive(game_data: dict, max_workers: int = 5) -> dict:
        """
        Bidirectionally syncs a game's savedata folder with Drive, preserving
        subfolder structure and propagating deletions:
        - Present on both sides: newer mtime wins.
        - Present on only one side: if it was in the last-synced manifest,
        it was deleted on the other side -> delete it here too.
        Otherwise it's genuinely new -> copy it over.
        Returns {"uploaded": [...], "downloaded": [...], "deleted_local": [...],
                "deleted_remote": [...], "skipped": [...]}
        """
        savedata_settings = SettingsManager().get(config.USER_CONF_SAVEDATA, {})
        if not savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False):
            return False

        game_name = game_data.get("name", "")
        savedata_path = game_data.get("savedata_path", "")

        if not game_data.get("gdrive", False):
            raise ValueError(f"Gdrive sync is not enabled for '{game_name}'.")
        if not savedata_path:
            raise ValueError(f"No savedata path set for '{game_name}'.")

        src = Path(savedata_path)
        if not src.exists():
            raise FileNotFoundError(f"Savedata path does not exist: {src}")

        root_folder_id = GdriveManager.get_root_folder_id()
        folder_id = GdriveManager.find_folder(game_name, parent_id=root_folder_id)
        if folder_id is None:
            # Treat this as a fresh sync environment to prevent accidental mass local deletion.
            folder_id = GdriveManager.create_folder(game_name, parent_id=root_folder_id)
            # Overwrite manifest to be empty; was_known will become False
            manifest = {}
        else:
            manifest = SavedataManager._get_sync_manifest(game_name)

        remote_files, remote_folders = GdriveManager.build_remote_tree(folder_id)

        local_files_by_rel = {
            f.relative_to(src).as_posix(): f
            for f in src.rglob("*") if f.is_file()
        }

        all_rel_paths = set(local_files_by_rel.keys()) | set(remote_files.keys()) | set(manifest.keys())

        upload_plan = []
        download_plan = []
        delete_local_plan = []
        delete_remote_plan = []
        skipped = []

        for rel_path in all_rel_paths:
            local_file = local_files_by_rel.get(rel_path)
            remote_meta = remote_files.get(rel_path)
            was_known = rel_path in manifest
            rel_dir = "/".join(rel_path.split("/")[:-1])

            # Present on both sides
            if local_file is not None and remote_meta is not None:
                local_mtime = local_file.stat().st_mtime
                remote_mtime = datetime.fromisoformat(remote_meta["modifiedTime"]).timestamp()

                if local_mtime > remote_mtime + 1:
                    target_parent_id = GdriveManager.ensure_folder_path(folder_id, rel_dir, remote_folders)
                    upload_plan.append((local_file, target_parent_id, remote_meta["id"], rel_path))
                elif remote_mtime > local_mtime + 1:
                    download_plan.append((remote_meta["id"], local_file, remote_mtime, rel_path))
                else:
                    skipped.append(rel_path)
                continue

            # Local only
            if local_file is not None and remote_meta is None:
                if was_known:
                    # Existed before, now gone from Drive -> deleted remotely -> delete locally too
                    delete_local_plan.append(local_file)
                else:
                    target_parent_id = GdriveManager.ensure_folder_path(folder_id, rel_dir, remote_folders)
                    upload_plan.append((local_file, target_parent_id, None, rel_path))
                continue

            # Remote only
            if local_file is None and remote_meta is not None:
                if was_known:
                    # Existed before, now gone locally -> deleted locally -> delete remotely too
                    delete_remote_plan.append(remote_meta["id"])
                else:
                    remote_mtime = datetime.fromisoformat(remote_meta["modifiedTime"]).timestamp()
                    download_plan.append((remote_meta["id"], src / rel_path, remote_mtime, rel_path))
                continue

        # Safeguard in case of mass wipe
        SavedataManager._check_deletion_safety(len(delete_local_plan), len(manifest), "locally", game_name)
        SavedataManager._check_deletion_safety(len(delete_remote_plan), len(manifest), "from Google Drive", game_name)

        # Concurrent uploads
        uploaded = []
        if upload_plan:
            def do_upload(item):
                local_file, parent_id, existing_id, rel_path = item
                GdriveManager.upload_file(local_file, parent_id, existing_file_id=existing_id)
                return rel_path
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                uploaded = list(executor.map(do_upload, upload_plan))

        # Concurrent downloads
        downloaded = []
        if download_plan:
            def do_download(item):
                file_id, local_target, remote_mtime, rel_path = item
                GdriveManager.download_file(file_id, local_target, remote_mtime)
                return rel_path
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                downloaded = list(executor.map(do_download, download_plan))

        # Concurrent remote deletions
        deleted_remote = []
        if delete_remote_plan:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                list(executor.map(GdriveManager.delete_file, delete_remote_plan))
            deleted_remote = delete_remote_plan

        # Local deletions
        deleted_local = []
        for local_file in delete_local_plan:
            try:
                local_file.unlink()
                deleted_local.append(local_file.relative_to(src).as_posix())
            except Exception as e:
                logger.warning(f"Failed to delete local file '{local_file}': {e}")

        # Rebuild manifest
        new_manifest = {}
        for f in src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(src).as_posix()
                new_manifest[rel] = f.stat().st_mtime
        SavedataManager._save_sync_manifest(game_name, new_manifest)

        logger.info(
            f"Gdrive sync for '{game_name}': {len(uploaded)} uploaded, {len(downloaded)} downloaded, "
            f"{len(deleted_local)} deleted locally, {len(deleted_remote)} deleted remotely, "
            f"{len(skipped)} unchanged."
        )
        return {
            "uploaded": uploaded, "downloaded": downloaded,
            "deleted_local": deleted_local, "deleted_remote": deleted_remote,
            "skipped": skipped
        }

    @staticmethod
    def _check_deletion_safety(delete_count: int, known_count: int, direction: str, game_name: str):
        if known_count == 0 or delete_count == 0:
            return
        ratio = delete_count / known_count
        if ratio >= SavedataManager.DELETION_SAFETY_THRESHOLD:
            raise SyncSafetyError(
                f"Sync aborted for '{game_name}': {delete_count}/{known_count} previously-known files "
                f"would be deleted {direction}. This usually means the savedata path changed, the target "
                f"folder is wrong/empty, or files were removed outside a sync. Verify before retrying."
            )

    @staticmethod
    def _load_gsync_metadata() -> dict:
        """Loads the full gsync metadata file: {game_name: {rel_path: mtime}}"""
        if not config.GSYNC_METADATA.exists():
            return {}
        try:
            with open(config.GSYNC_METADATA, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    @staticmethod
    def _save_gsync_metadata(data: dict):
        """Saves the full gsync metadata file safely."""
        try:
            config.GSYNC_METADATA.parent.mkdir(parents=True, exist_ok=True)
            with open(config.GSYNC_METADATA, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save to {config.GSYNC_METADATA}: {e}")
            raise RuntimeError(f"Failed to save gsync metadata: {e}")

    @staticmethod
    def _get_sync_manifest(game_name: str) -> dict:
        """Returns {rel_path: mtime} as of the end of the last successful sync for this game."""
        all_metadata = SavedataManager._load_gsync_metadata()
        return all_metadata.get(game_name, {})

    @staticmethod
    def _save_sync_manifest(game_name: str, manifest: dict):
        """Updates just this game's manifest within the shared metadata file."""
        all_metadata = SavedataManager._load_gsync_metadata()
        all_metadata[game_name] = manifest
        SavedataManager._save_gsync_metadata(all_metadata)

    @staticmethod
    def reset_sync_manifest(game_name: str):
        """
        Clears the sync manifest for a game. Called whenever savedata_path changes
        so the next sync treats the new location as a fresh environment to avoid file deletion
        """
        all_metadata = SavedataManager._load_gsync_metadata()
        if game_name in all_metadata:
            all_metadata.pop(game_name)
            SavedataManager._save_gsync_metadata(all_metadata)
            logger.info(f"Reset Gdrive sync manifest for '{game_name}' (savedata path changed).")

class GdriveSyncWorker(QThread):
    """
    Runs SavedataManager.sync_savedata_to_gdrive() in a background thread
    """
    sync_succeeded = Signal(str, dict)
    sync_failed = Signal(str, str)

    def __init__(self, game_data: dict):
        super().__init__()
        self.game_data = game_data

    def run(self):
        game_name = self.game_data.get("name", "")
        try:
            result = SavedataManager.sync_savedata_to_gdrive(self.game_data)
            self.sync_succeeded.emit(game_name, result)
        except Exception as e:
            logger.error(f"Gdrive sync failed for '{game_name}': {e}", exc_info=True)
            self.sync_failed.emit(game_name, str(e))

class SyncSafetyError(Exception):
    """Raised when a sync would delete an unexpectedly large portion of previously-known files."""
    pass
