from __future__ import annotations

import config
import json
import logging
import shutil
import os
import tempfile
from PySide6.QtCore import QThread, Signal, QObject
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timezone
from prefix_manager import PrefixManager
from settings_manager import SettingsManager
from gdrive_manager import GdriveManager
from game_manager import GameManager

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

    # More than 70% files deleted safeguard
    DELETION_SAFETY_THRESHOLD = 0.7
    # # Uploaded alongside savedata files with savedata path info
    SYNC_LOCATION_METADATA_FILENAME = ".lvnm_savedata_location.json"
    SECONDARY_SOURCE_FOLDER = ".lvnm_sources"
    LOCATION_REFERENCE_METADATA_KEY = "__location_references__"
    CONFLICT_PREFER_LOCAL = "prefer_local"
    CONFLICT_PREFER_REMOTE = "prefer_remote"

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

    @staticmethod
    def get_savedata_config(game_data: dict) -> dict:
        config_data = game_data.get("savedata")
        if isinstance(config_data, dict):
            mode = config_data.get("mode", "folders")
            return {
                "version": 1,
                "mode": mode if mode in {"folders", "files"} else "folders",
                "folders": list(config_data.get("folders", [])),
                "file_groups": list(config_data.get("file_groups", [])),
            }

        legacy_path = game_data.get("savedata_path", "")
        return {
            "version": 1,
            "mode": "folders",
            "folders": [{"path": legacy_path, "excluded": [], "source_id": "primary"}] if legacy_path else [],
            "file_groups": [],
        }

    @staticmethod
    def _active_sources(savedata_config: dict) -> list[dict]:
        key = "file_groups" if savedata_config.get("mode") == "files" else "folders"
        return savedata_config.get(key, [])

    @staticmethod
    def has_savedata(game_data: dict) -> bool:
        savedata_config = SavedataManager.get_savedata_config(game_data)
        mode = savedata_config.get("mode")
        return any(SavedataManager._source_root(source, mode) for source in SavedataManager._active_sources(savedata_config))

    @staticmethod
    def _source_root(source: dict, mode: str) -> str:
        return str(source.get("root" if mode == "files" else "path", ""))

    @staticmethod
    def _source_cloud_prefix(source: dict) -> str:
        source_id = str(source.get("source_id", "primary"))
        if not source_id or not all(character.isalnum() or character in "_-" for character in source_id):
            raise ValueError(f"Invalid savedata source ID: {source_id}")
        return "" if source_id == "primary" else f"{SavedataManager.SECONDARY_SOURCE_FOLDER}/{source_id}"

    @staticmethod
    def _safe_relative_path(value: str) -> Path:
        rel_path = Path(value)
        if not value or rel_path.is_absolute() or ".." in rel_path.parts:
            raise ValueError(f"Invalid savedata relative path: {value}")
        return rel_path

    @staticmethod
    def _cloud_path(source: dict, rel_path: str) -> str:
        prefix = SavedataManager._source_cloud_prefix(source)
        return f"{prefix}/{rel_path}" if prefix else rel_path

    @staticmethod
    def _source_relative_cloud_path(source: dict, cloud_path: str) -> str | None:
        prefix = SavedataManager._source_cloud_prefix(source)
        if not prefix:
            if cloud_path.startswith(f"{SavedataManager.SECONDARY_SOURCE_FOLDER}/"):
                return None
            return cloud_path
        prefix_with_separator = f"{prefix}/"
        return cloud_path[len(prefix_with_separator):] if cloud_path.startswith(prefix_with_separator) else None

    @staticmethod
    def _is_managed_relative_path(source: dict, mode: str, rel_path: str) -> bool:
        if mode == "files":
            return rel_path in {Path(path).as_posix() for path in source.get("files", [])}
        return rel_path not in {Path(path).as_posix() for path in source.get("excluded", [])}

    @staticmethod
    def _local_target_for_cloud_path(savedata_config: dict, cloud_path: str) -> Path | None:
        mode = savedata_config.get("mode", "folders")
        for source in SavedataManager._active_sources(savedata_config):
            rel_path = SavedataManager._source_relative_cloud_path(source, cloud_path)
            if rel_path is None or not SavedataManager._is_managed_relative_path(source, mode, rel_path):
                continue
            root_value = SavedataManager._source_root(source, mode)
            if not root_value:
                continue
            root = Path(root_value)
            return root / SavedataManager._safe_relative_path(rel_path)
        return None

    @staticmethod
    def collect_managed_files(savedata_config: dict) -> dict[str, Path]:
        mode = savedata_config.get("mode", "folders")
        managed_files = {}
        source_ids = [str(source.get("source_id", "primary")) for source in SavedataManager._active_sources(savedata_config)]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Savedata source IDs must be unique.")
        for source in SavedataManager._active_sources(savedata_config):
            root_value = SavedataManager._source_root(source, mode)
            if not root_value:
                continue
            root = Path(root_value)
            if mode == "files":
                candidates = [SavedataManager._safe_relative_path(path) for path in source.get("files", [])]
            else:
                candidates = [path.relative_to(root) for path in root.rglob("*") if path.is_file()] if root.is_dir() else []

            for relative in candidates:
                rel_path = relative.as_posix()
                if not SavedataManager._is_managed_relative_path(source, mode, rel_path):
                    continue
                local_path = root / relative
                try:
                    local_path.resolve().relative_to(root.resolve())
                except ValueError:
                    logger.warning(f"Skipping savedata file outside its configured root: {local_path}")
                    continue
                if local_path.is_file():
                    managed_files[SavedataManager._cloud_path(source, rel_path)] = local_path
        return managed_files

    def start_gdrive_sync(self, name: str, game_data: dict, conflict_resolution: str = "defer"):
        """Runs the Gdrive sync in a background thread so it doesn't block the UI."""
        if not self.savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False):
            return

        # Safety guard: Prevent launching duplicate threads for the same game
        if name in self._gdrive_sync_workers:
            logger.warning(f"Gdrive sync already in progress for '{name}'. Skipping duplicate request.")
            return

        worker = GdriveSyncWorker(game_data, conflict_resolution=conflict_resolution)
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
        Copies all managed savedata sources into their equivalent locations
        inside the target prefix.

        Only works for savedata that lives inside the game's current prefix
        Raises an exception if the savedata path is not actually inside the original prefix.
        """
        game_name = game_data.get("name", "")
        original_prefix_name = game_data.get("prefix", "")

        savedata_config = SavedataManager.get_savedata_config(game_data)
        if not SavedataManager.has_savedata(game_data):
            logging.error(f"No savedata path set for '{game_name}'. Cannot copy.")
            raise ValueError(f"No savedata path set for '{game_name}'.")

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

        copy_plan = []
        mode = savedata_config.get("mode", "folders")
        managed_files = SavedataManager.collect_managed_files(savedata_config)
        for source in SavedataManager._active_sources(savedata_config):
            root_value = SavedataManager._source_root(source, mode)
            if not root_value:
                continue
            source_root = Path(os.path.abspath(root_value))
            if not source_root.exists():
                raise FileNotFoundError(f"Savedata path does not exist: {source_root}")
            try:
                root_relative = source_root.relative_to(original_prefix_path)
            except ValueError:
                raise ValueError(f"Savedata path is not inside the original prefix: {source_root}")
            destination_root = target_prefix_path / SavedataManager._remap_user_segment(root_relative, target_prefix_path)
            prefix = SavedataManager._source_cloud_prefix(source)
            for cloud_path, local_path in managed_files.items():
                relative = SavedataManager._source_relative_cloud_path(source, cloud_path)
                if relative is not None and (prefix or not cloud_path.startswith(f"{SavedataManager.SECONDARY_SOURCE_FOLDER}/")):
                    copy_plan.append((local_path, destination_root / relative))

        if not overwrite and any(destination.exists() for _, destination in copy_plan):
            raise FileExistsError(f"Savedata for '{game_name}' already exists in prefix '{prefix_name}'.")

        try:
            for source, destination in copy_plan:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)

            logging.info(f"Copied savedata for '{game_name}' to prefix '{prefix_name}'")
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
        prefix_info = PrefixManager.get_prefix_info(prefix_name)

        if not prefix_info:
            logging.warning(f"Prefix '{prefix_name}' not found for '{game_name}'. Cannot search prefix.")
            return None

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
                        candidates.append((found_dir, True))
                    elif found_dir.is_dir() and SavedataManager._is_fuzzy_name_match(found_dir.name, target_names):
                        candidates.append((found_dir, False))

        if not candidates:
            logger.debug(f"No savedata folder found in prefix for '{game_name}'.")
            return None

        # Prefer the most deeply nested match (most specific location)
        # Prefer exact matches over fuzzy
        candidates.sort(key=lambda c: (c[1], len(c[0].parts)), reverse=True)
        best_match = candidates[0][0]
        logger.debug(f"Found savedata folder in prefix: {best_match}")
        return str(best_match)

    @staticmethod
    def _is_fuzzy_name_match(folder_name: str, target_names: set[str], min_len: int = 4) -> bool:
        """
        Loose containment match for when a game's name doesn't exactly match its
        savedata folder
        """
        folder_name = folder_name.lower()
        if len(folder_name) < min_len:
            return False
        for target in target_names:
            if len(target) < min_len:
                continue
            if target in folder_name or folder_name in target:
                return True
        return False

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
            game_card.savedata = game_card.savedata.from_dict(None, detected_path)
            return True

        logger.warning(f"Could not auto-detect savedata folder for '{name}'.")
        return False

    @staticmethod
    def is_savedata_inside_prefix(game_data: dict) -> bool:
        """Checks whether every configured savedata source lives inside the game's prefix."""
        prefix_name = game_data.get("prefix", "")
        savedata_config = SavedataManager.get_savedata_config(game_data)
        sources = SavedataManager._active_sources(savedata_config)
        if not sources or not prefix_name:
            return False
        prefix_info = PrefixManager.get_prefix_info(prefix_name)
        if not prefix_info:
            return False
        prefix_path = Path(os.path.abspath(prefix_info.get("path", "")))
        mode = savedata_config.get("mode", "folders")
        for source in sources:
            root = SavedataManager._source_root(source, mode)
            if not root:
                return False
            try:
                Path(os.path.abspath(root)).relative_to(prefix_path)
            except ValueError:
                return False
        return True

    @staticmethod
    def _compute_portable_path_reference(game_data: dict, path: str) -> dict | None:
        src = Path(os.path.abspath(path))
        prefix_info = PrefixManager.get_prefix_info(game_data.get("prefix", ""))
        if prefix_info:
            prefix_path = Path(os.path.abspath(prefix_info.get("path", "")))
            try:
                return {"kind": "prefix", "rel_path": src.relative_to(prefix_path).as_posix()}
            except ValueError:
                pass

        game_path = game_data.get("path", "")
        if game_path:
            install_dir = Path(os.path.abspath(game_path)).parent
            try:
                return {"kind": "install", "rel_path": src.relative_to(install_dir).as_posix()}
            except ValueError:
                pass
        return None

    @staticmethod
    def _compute_portable_location_reference(game_data: dict) -> dict | None:
        """
        Describes all savedata sources relative to the prefix or install folder
        so another device can reconstruct the same selection.
        """
        savedata_config = SavedataManager.get_savedata_config(game_data)
        mode = savedata_config.get("mode", "folders")
        portable_sources = []
        for source in SavedataManager._active_sources(savedata_config):
            root = SavedataManager._source_root(source, mode)
            if not root:
                continue
            location = SavedataManager._compute_portable_path_reference(game_data, root)
            if location is None:
                logger.warning(f"Savedata source is not in the prefix or game folder: {root}")
                return None
            portable_source = {"source_id": source.get("source_id", "primary"), "location": location}
            if mode == "files":
                portable_source["files"] = list(source.get("files", []))
            else:
                portable_source["excluded"] = list(source.get("excluded", []))
            portable_sources.append(portable_source)
        return {"version": 2, "mode": mode, "sources": portable_sources} if portable_sources else None

    @staticmethod
    def _resolve_portable_path(game_data: dict, reference: dict) -> Path | None:
        """
        Resolves game's savedata path in local prefix from _compute_portable_location_reference
        """
        kind = reference.get("kind")
        rel_path = reference.get("rel_path")
        if not kind or not rel_path:
            return None
        relative = SavedataManager._safe_relative_path(str(rel_path))

        if kind == "prefix":
            prefix_info = PrefixManager.get_prefix_info(game_data.get("prefix", ""))
            if not prefix_info:
                logger.error("_resolve_portable_location: no prefix set for game")
                raise ValueError("_resolve_portable_location: no prefix set for game")

            prefix_path = Path(os.path.abspath(prefix_info.get("path", "")))
            remapped = SavedataManager._remap_user_segment(relative, prefix_path)
            return prefix_path / remapped

        if kind == "install":
            game_path = game_data.get("path", "")
            if not game_path:
                return None
            return Path(os.path.abspath(game_path)).parent / relative

        return None

    @staticmethod
    def _resolve_portable_location(game_data: dict, reference: dict) -> dict | None:
        # Version 1 metadata represented a single directory directly.
        if "version" not in reference:
            path = SavedataManager._resolve_portable_path(game_data, reference)
            if path is None:
                return None
            return {
                "version": 1,
                "mode": "folders",
                "folders": [{"path": str(path), "excluded": [], "source_id": "primary"}],
                "file_groups": [],
            }

        mode = reference.get("mode", "folders")
        resolved = {"version": 1, "mode": mode, "folders": [], "file_groups": []}
        for source in reference.get("sources", []):
            root = SavedataManager._resolve_portable_path(game_data, source.get("location", {}))
            if root is None:
                return None
            if mode == "files":
                resolved["file_groups"].append({
                    "root": str(root),
                    "files": list(source.get("files", [])),
                    "source_id": source.get("source_id", "primary"),
                })
            else:
                resolved["folders"].append({
                    "path": str(root),
                    "excluded": list(source.get("excluded", [])),
                    "source_id": source.get("source_id", "primary"),
                })
        return resolved

    @staticmethod
    def _upload_location_reference(folder_id: str, existing_location_meta: dict | None, game_data: dict):
        """
        Refreshes the portable location hint in Drive after a successful sync.
        """
        reference = SavedataManager._compute_portable_location_reference(game_data)
        if reference is None:
            logger.warning(f"Could not upload savedata location hint for '{game_data.get('name', '')}")
            return

        game_name = game_data.get("name", "")
        last_uploaded = SavedataManager._get_last_uploaded_location_reference(game_name)
        if reference == last_uploaded and existing_location_meta is not None:
            # Unchanged
            return  

        try:
            tmp_dir = Path(tempfile.mkdtemp())
            tmp_path = tmp_dir / SavedataManager.SYNC_LOCATION_METADATA_FILENAME
            tmp_path.write_text(json.dumps(reference), encoding="utf-8")
            GdriveManager.upload_file(
                tmp_path, folder_id,
                existing_file_id=existing_location_meta["id"] if existing_location_meta else None
            )
            tmp_path.unlink(missing_ok=True)
            tmp_dir.rmdir()
            SavedataManager._save_last_uploaded_location_reference(game_name, reference)
        except Exception as e:
            logger.warning(f"Could not upload savedata location hint for '{game_data.get('name', '')}': {e}")

    @staticmethod
    def get_savedata_config_from_gdrive(game_data: dict) -> dict | None:
        """
        Restores the savedata source configuration from Drive when the game has
        no local configuration yet.
        """
        game_name = game_data.get("name", "")
        if SavedataManager.has_savedata(game_data):
            return None

        root_folder_id = GdriveManager.get_root_folder_id()
        folder_id = GdriveManager.find_folder(game_name, parent_id=root_folder_id)
        if folder_id is None:
            logger.debug("get_savedata_path_from_gdrive: No cloud data for this game yet")
            return None

        remote_files, _ = GdriveManager.build_remote_tree(folder_id)
        location_meta = remote_files.get(SavedataManager.SYNC_LOCATION_METADATA_FILENAME)
        if location_meta is None:
            logger.warning("get_savedata_path_from_gdrive: no savedata path in gdrive.")
            return None

        try:
            tmp_dir = Path(tempfile.mkdtemp())
            tmp_path = tmp_dir / SavedataManager.SYNC_LOCATION_METADATA_FILENAME
            GdriveManager.download_file(location_meta["id"], tmp_path, 0)
            reference = json.loads(tmp_path.read_text(encoding="utf-8"))
            tmp_path.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except Exception as e:
            logger.warning(f"get_savedata_path_from_gdrive: Could not read savedata savedata location hint for '{game_name}': {e}")
            return None

        predicted_config = SavedataManager._resolve_portable_location(game_data, reference)
        if predicted_config is None:
            logger.warning("get_savedata_config_from_gdrive: savedata configuration could not be resolved")
            return None

        logger.info(f"Resolved savedata configuration for '{game_name}' from cloud hint")
        return predicted_config

    @staticmethod
    def get_savedata_path_from_gdrive(game_data: dict) -> str | None:
        """Compatibility wrapper returning the first restored source root."""
        savedata_config = SavedataManager.get_savedata_config_from_gdrive(game_data)
        if savedata_config is None:
            return None
        sources = SavedataManager._active_sources(savedata_config)
        return SavedataManager._source_root(sources[0], savedata_config.get("mode")) if sources else None

    @staticmethod
    def sync_savedata_to_gdrive(game_data: dict, max_workers: int = 10, conflict_resolution: str = "defer") -> dict:
        """
        Bidirectionally syncs a game's managed savedata files with Drive,
        preserving source namespaces and propagating deletions:
        - Present on both sides: newer mtime wins.
        - Present on only one side: if it was in the last-synced manifest,
        it was deleted on the other side -> delete it here too.
        Otherwise it's genuinely new -> copy it over.
        - If first sync and no savedata path defined it creates the savedata path fetched from
        GDrive relative to the prefix/game location.
        - If first sync and newer mtime than what already exists in gdrive ask/defer files.
        Returns {"uploaded": [...], "downloaded": [...], "deleted_local": [...],
                "deleted_remote": [...], "skipped": [...], "deferred_conflicts": [...],
                "restored_savedata_config": dict | None}
        """
        savedata_settings = SettingsManager().get(config.USER_CONF_SAVEDATA, {})
        if not savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False):
            return False

        game_name = game_data.get("name", "")
        savedata_config = SavedataManager.get_savedata_config(game_data)
        savedata_was_already_set = SavedataManager.has_savedata(game_data)
        predicted_config = None

        if not game_data.get("gdrive", False):
            raise ValueError(f"Gdrive sync is not enabled for '{game_name}'.")

        if not savedata_was_already_set:
            predicted_config = SavedataManager.get_savedata_config_from_gdrive(game_data)
            if predicted_config is None:
                raise ValueError(f"No savedata path set for '{game_name}'.")

            savedata_config = predicted_config
            game_data["savedata"] = predicted_config
            sources = SavedataManager._active_sources(predicted_config)
            primary_path = SavedataManager._source_root(sources[0], predicted_config.get("mode")) if sources else ""
            game_data["savedata_path"] = primary_path
            GameManager.update_game(game_name, {"savedata": predicted_config})

        mode = savedata_config.get("mode", "folders")
        for source in SavedataManager._active_sources(savedata_config):
            root_value = SavedataManager._source_root(source, mode)
            if not root_value:
                continue
            root = Path(root_value)
            if savedata_was_already_set and not root.exists():
                raise FileNotFoundError(
                    f"Configured savedata path for '{game_name}' does not exist: {root}. "
                    f"If the game was moved, update the savedata path in settings before syncing."
                )
            if not savedata_was_already_set:
                root.mkdir(parents=True, exist_ok=True)

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

        # Exclude the reserved filename from regular sync
        existing_location_meta = remote_files.pop(SavedataManager.SYNC_LOCATION_METADATA_FILENAME, None)

        local_files_by_rel = SavedataManager.collect_managed_files(savedata_config)
        remote_files = {
            rel_path: metadata for rel_path, metadata in remote_files.items()
            if SavedataManager._local_target_for_cloud_path(savedata_config, rel_path) is not None
        }
        manifest = {
            rel_path: mtime for rel_path, mtime in manifest.items()
            if SavedataManager._local_target_for_cloud_path(savedata_config, rel_path) is not None
        }

        all_rel_paths = set(local_files_by_rel.keys()) | set(remote_files.keys()) | set(manifest.keys())

        upload_plan = []
        download_plan = []
        delete_local_plan = []
        delete_remote_plan = []
        skipped = []
        deferred_conflicts = []

        for rel_path in all_rel_paths:
            local_file = local_files_by_rel.get(rel_path)
            remote_meta = remote_files.get(rel_path)
            was_known = rel_path in manifest
            rel_dir = "/".join(rel_path.split("/")[:-1])

            # Present on both sides
            if local_file is not None and remote_meta is not None:
                local_mtime = local_file.stat().st_mtime
                remote_mtime = datetime.fromisoformat(remote_meta["modifiedTime"]).timestamp()

                if not was_known and local_mtime > remote_mtime + 1:
                    # Ambiguous: never synced from this device, and looks newer than Drive.
                    if conflict_resolution == SavedataManager.CONFLICT_PREFER_LOCAL:
                        target_parent_id = GdriveManager.ensure_folder_path(folder_id, rel_dir, remote_folders)
                        upload_plan.append((local_file, target_parent_id, remote_meta["id"], rel_path))
                    elif conflict_resolution == SavedataManager.CONFLICT_PREFER_REMOTE:
                        download_plan.append((remote_meta["id"], local_file, remote_mtime, rel_path))
                    else:
                        deferred_conflicts.append({"rel_path": rel_path, "local_mtime": local_mtime, "remote_mtime": remote_mtime})
                elif local_mtime > remote_mtime + 1:
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
                    local_target = SavedataManager._local_target_for_cloud_path(savedata_config, rel_path)
                    download_plan.append((remote_meta["id"], local_target, remote_mtime, rel_path))
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
                deleted_local.append(next((rel for rel, path in local_files_by_rel.items() if path == local_file), str(local_file)))
            except Exception as e:
                logger.warning(f"Failed to delete local file '{local_file}': {e}")

        # Deferred
        deferred_rel_paths = {c["rel_path"] for c in deferred_conflicts}

        # Rebuild manifest
        new_manifest = {}
        for rel, local_file in SavedataManager.collect_managed_files(savedata_config).items():
            if rel in deferred_rel_paths:
                # Deferred conflicts are left out so they keep showing up as ambiguous until resolved
                continue
            new_manifest[rel] = local_file.stat().st_mtime
        SavedataManager._save_sync_manifest(game_name, new_manifest)
        SavedataManager._upload_location_reference(folder_id, existing_location_meta, game_data)

        logger.info(
            f"Gdrive sync for '{game_name}': {len(uploaded)} uploaded, {len(downloaded)} downloaded, "
            f"{len(deleted_local)} deleted locally, {len(deleted_remote)} deleted remotely, "
            f"{len(skipped)} unchanged, {len(deferred_conflicts)} deffered. "
            f"restored_savedata_config: {predicted_config is not None}"
        )
        return {
            "uploaded": uploaded, "downloaded": downloaded,
            "deleted_local": deleted_local, "deleted_remote": deleted_remote,
            "skipped": skipped, "deferred_conflicts": deferred_conflicts,
            "restored_savedata_config": predicted_config,
            "get_savedata_path_from_gdrive": game_data.get("savedata_path") if predicted_config is not None else None,
        }

    @staticmethod
    def _get_last_uploaded_location_reference(game_name: str) -> dict | None:
        all_metadata = SavedataManager._load_gsync_metadata()
        return all_metadata.get(SavedataManager.LOCATION_REFERENCE_METADATA_KEY, {}).get(game_name)

    @staticmethod
    def _save_last_uploaded_location_reference(game_name: str, reference: dict):
        all_metadata = SavedataManager._load_gsync_metadata()
        refs = all_metadata.setdefault(SavedataManager.LOCATION_REFERENCE_METADATA_KEY, {})
        refs[game_name] = reference
        SavedataManager._save_gsync_metadata(all_metadata)

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
        Clears the sync manifest for a game whenever its savedata configuration
        changes so the next sync cannot infer deletions from the old selection.
        """
        all_metadata = SavedataManager._load_gsync_metadata()
        changed = False
        if game_name in all_metadata:
            all_metadata.pop(game_name)
            changed = True
        refs = all_metadata.get(SavedataManager.LOCATION_REFERENCE_METADATA_KEY, {})
        if game_name in refs:
            refs.pop(game_name, None)
            changed = True
        if changed:
            SavedataManager._save_gsync_metadata(all_metadata)
            logger.info(f"Reset Gdrive sync manifest for '{game_name}' (savedata configuration changed).")

class GdriveSyncWorker(QThread):
    """
    Runs SavedataManager.sync_savedata_to_gdrive() in a background thread
    """
    sync_succeeded = Signal(str, dict)
    sync_failed = Signal(str, str)

    def __init__(self, game_data: dict, conflict_resolution: str = "defer"):
        super().__init__()
        self.game_data = game_data
        self.conflict_resolution = conflict_resolution

    def run(self):
        game_name = self.game_data.get("name", "")
        try:
            result = SavedataManager.sync_savedata_to_gdrive(self.game_data, conflict_resolution=self.conflict_resolution)
            self.sync_succeeded.emit(game_name, result)
        except Exception as e:
            logger.error(f"Gdrive sync failed for '{game_name}': {e}", exc_info=True)
            self.sync_failed.emit(game_name, str(e))

class SyncSafetyError(Exception):
    """Raised when a sync would delete an unexpectedly large portion of previously-known files."""
    pass
