from __future__ import annotations

import config
import logging
import requests
import threading
import time
import io
import os
import json
from googleapiclient.discovery import build_from_document
from datetime import datetime, timezone
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.http import MediaIoBaseDownload
from PySide6.QtCore import QThread, Signal
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)

ROOT_FOLDER_NAME = "LVNM"
GDRIVE_FOLDER_MIMETYPE = "application/vnd.google-apps.folder"

class GdriveManager:
    _root_folder_id = None
    _thread_local = threading.local()

    # access token cache
    _cached_access_token = None
    _cached_token_expiry = 0  # unix timestamp
    _token_lock = threading.Lock()

    @staticmethod
    def request_device_code(client_id: str) -> dict:
        """
        Kicks off the device flow. Returns a dict with:
        device_code, user_code, verification_url, interval, expires_in
        """
        logger.debug("request_device_code")
        resp = requests.post(config.GDRIVE_DEVICE_CODE_URL, data={
            "client_id": client_id,
            "scope": config.GDRIVE_SCOPES,
        })
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def poll_once(client_id: str, client_secret: str, device_code: str) -> dict | None:
        """
        Performs a single poll against the token endpoint.
        Returns the token dict on success, None if still pending,
        raises RuntimeError on a hard failure (denied, expired, etc.)
        """
        resp = requests.post(config.GDRIVE_TOKEN_URL, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
        data = resp.json()

        if "access_token" in data:
            return data

        error = data.get("error")
        if error in ("authorization_pending", "slow_down"):
            return None

        raise RuntimeError(data.get("error_description", error or "Unknown error"))

    @staticmethod
    def save_credentials(token_data: dict):
        """Persists the refresh_token via SettingsManager."""
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            logger.error("No refresh_token in token response; cannot save credentials.")
            return

        settings = SettingsManager()
        savedata_settings = settings.get(config.USER_CONF_SAVEDATA, {})
        savedata_settings[config.USER_CONF_SAVEDATA_GDRIVE_REFRESH_TOKEN] = refresh_token
        settings.set(config.USER_CONF_SAVEDATA, savedata_settings)
        logger.info("Google Drive credentials saved.")

    @staticmethod
    def is_logged_in() -> bool:
        """True if a refresh_token is stored."""
        savedata_settings = SettingsManager().get(config.USER_CONF_SAVEDATA, {})
        return bool(savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_REFRESH_TOKEN))

    @staticmethod
    def get_refresh_token() -> str:
        savedata_settings = SettingsManager().get(config.USER_CONF_SAVEDATA, {})
        return savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_REFRESH_TOKEN, "")

    @staticmethod
    def logout(client_id: str = "", client_secret: str = ""):
        """Revokes the refresh_token with Google (best-effort) and clears it locally."""
        logger.debug("logout")
        refresh_token = GdriveManager.get_refresh_token()
        if refresh_token:
            try:
                requests.post(config.GDRIVE_REVOKE_URL, params={"token": refresh_token})
            except Exception as e:
                logger.warning(f"Failed to revoke Google token remotely: {e}")

        settings = SettingsManager()
        savedata_settings = settings.get(config.USER_CONF_SAVEDATA, {})
        savedata_settings.pop(config.USER_CONF_SAVEDATA_GDRIVE_REFRESH_TOKEN, None)
        settings.set(config.USER_CONF_SAVEDATA, savedata_settings)
        GdriveManager.reset_service_cache()
        GdriveManager.invalidate_token_cache()
        logger.info("Logged out of Google Drive.")

    @staticmethod
    def _get_access_token() -> str:
        """
        Returns a cached access token if still valid, otherwise refreshes it once.
        Thread-safe: if multiple threads call this concurrently while the token
        is expired/missing, only ONE actually hits the network; the rest wait
        on the lock and then reuse the result.
        """
        logger.debug("_get_access_token")
        now = time.time()

        # Token still valid, no lock needed for the common case
        if GdriveManager._cached_access_token and now < GdriveManager._cached_token_expiry:
            return GdriveManager._cached_access_token

        with GdriveManager._token_lock:
            # Re-check after acquiring the lock another thread may have already refreshed it while we were waiting.
            now = time.time()
            if GdriveManager._cached_access_token and now < GdriveManager._cached_token_expiry:
                return GdriveManager._cached_access_token

            client_id, client_secret = GdriveManager.get_client_credentials()
            refresh_token = GdriveManager.get_refresh_token()
            if not refresh_token:
                raise RuntimeError("Not logged in to Google Drive.")

            resp = requests.post(config.GDRIVE_TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            data = resp.json()

            GdriveManager._cached_access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            GdriveManager._cached_token_expiry = time.time() + expires_in - 60

            logger.debug("Refreshed Google Drive access token.")
            return GdriveManager._cached_access_token

    @staticmethod
    def invalidate_token_cache():
        """Force a fresh refresh next call."""
        logger.debug("invalidate_token_cache")
        GdriveManager._cached_access_token = None
        GdriveManager._cached_token_expiry = 0
    
    @staticmethod
    def get_client_credentials() -> tuple[str, str]:
        """Reads the stored Google client id/secret from settings."""
        savedata_settings = SettingsManager().get(config.USER_CONF_SAVEDATA, {})
        client_id = savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_ID, "").strip()
        client_secret = savedata_settings.get(config.USER_CONF_SAVEDATA_GDRIVE_CLIENT_SECRET, "").strip()
        return client_id, client_secret

    @staticmethod
    def _get_drive_service():
        """
        Returns a Drive service scoped to the current thread. 
        They all share the SAME access token via _get_access_token()
        """
        logger.debug("_get_drive_service")
        access_token = GdriveManager._get_access_token()

        cached_token = getattr(GdriveManager._thread_local, "token", None)
        service = getattr(GdriveManager._thread_local, "service", None)

        # Rebuild this thread's service only if it doesn't have one yet,
        # or if the shared token has been refreshed since it built its own.
        if service is not None and cached_token == access_token:
            return service

        creds = Credentials(token=access_token)

        schema_path = Path(__file__).parent / "assets" / "drive_v3.json"
        with open(schema_path, "r", encoding="utf-8") as f:
            drive_schema = json.load(f)

        service = build_from_document(drive_schema, credentials=creds)
        GdriveManager._thread_local.service = service
        GdriveManager._thread_local.token = access_token
        return service

    @staticmethod
    def reset_service_cache():
        logger.debug("reset_service_cache")
        GdriveManager._thread_local.service = None
        GdriveManager._thread_local.token = None

    @staticmethod
    def find_folder(name: str, parent_id: str = None) -> str | None:
        """Searches Drive for a folder with the given name Returns its ID."""
        logger.debug(f"find_folder name: '{name}' parent_id: '{parent_id}'")
        service = GdriveManager._get_drive_service()
        query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = service.files().list(q=query, spaces="drive", fields="files(id, name)").execute()
        files = results.get("files", [])
        return files[0]["id"] if files else None

    @staticmethod
    def create_folder(name: str, parent_id: str = None) -> str:
        """Creates a folder in Drive and returns its ID."""
        logger.debug(f"create_folder name: '{name}' parent_id: '{parent_id}'")
        service = GdriveManager._get_drive_service()
        metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            metadata["parents"] = [parent_id]

        folder = service.files().create(body=metadata, fields="id").execute()
        logger.info(f"Created Drive folder '{name}' ({folder['id']})")
        return folder["id"]

    @staticmethod
    def upload_file(local_path: Path, parent_id: str, existing_file_id: str = None):
        """
        Uploads (or updates) a file, preserving the local file's mtime as
        Drive's modifiedTime so future syncs can compare against it directly.
        """
        service = GdriveManager._get_drive_service()
        local_mtime = datetime.fromtimestamp(local_path.stat().st_mtime, tz=timezone.utc)
        mtime_str = local_mtime.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        media = MediaFileUpload(str(local_path), resumable=False)

        if existing_file_id:
            service.files().update(
                fileId=existing_file_id,
                body={"modifiedTime": mtime_str},
                media_body=media
            ).execute()
            logger.debug(f"Updated file '{local_path}' (changed) in Drive")
        else:
            metadata = {"name": local_path.name, "parents": [parent_id], "modifiedTime": mtime_str}
            service.files().create(body=metadata, media_body=media, fields="id").execute()
            logger.debug(f"Uploaded new file '{local_path}' to Drive")

    @staticmethod
    def get_root_folder_id() -> str:
        """Finds or creates the top-level 'LVNM' folder, caching its ID."""
        if GdriveManager._root_folder_id:
            return GdriveManager._root_folder_id

        folder_id = GdriveManager.find_folder(ROOT_FOLDER_NAME)
        if not folder_id:
            folder_id = GdriveManager.create_folder(ROOT_FOLDER_NAME)

        GdriveManager._root_folder_id = folder_id
        return folder_id

    @staticmethod
    def build_remote_tree(folder_id: str, prefix: str = "") -> tuple[dict, dict]:
        """
        Recursively walks a Drive folder. Returns:
        - file_map: {relative_path: {"id":..., "modifiedTime":..., "size":...}}
        - folder_map: {relative_path: folder_id}
        relative_path uses "/" as separator (matches Path.as_posix()).
        """
        logger.debug(f"build_remote_tree folder_id: '{folder_id}' prefix: '{prefix}'")
        service = GdriveManager._get_drive_service()
        query = f"'{folder_id}' in parents and trashed = false"

        file_map = {}
        folder_map = {}
        page_token = None

        while True:
            results = service.files().list(
                q=query, spaces="drive",
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
                pageToken=page_token
            ).execute()

            for f in results.get("files", []):
                rel_path = f"{prefix}/{f['name']}" if prefix else f["name"]

                if f["mimeType"] == GDRIVE_FOLDER_MIMETYPE:
                    folder_map[rel_path] = f["id"]
                    sub_files, sub_folders = GdriveManager.build_remote_tree(f["id"], rel_path)
                    file_map.update(sub_files)
                    folder_map.update(sub_folders)
                else:
                    file_map[rel_path] = f

            page_token = results.get("nextPageToken")
            if not page_token:
                break

        return file_map, folder_map

    @staticmethod
    def ensure_folder_path(root_folder_id: str, relative_dir: str, folder_map: dict) -> str:
        """
        Ensures nested folders exist on Drive for relative_dir (e.g. "sub/nested"),
        creating any missing segments. Updates folder_map in place so repeated
        calls for files in the same subfolder don't recreate it.
        Returns the folder_id of the deepest folder.
        """
        logger.debug(f"ensure_folder_path root_folder_id: '{root_folder_id}' relative_dir: '{relative_dir}' folder_map: '{folder_map}'")
        if not relative_dir:
            return root_folder_id

        if relative_dir in folder_map:
            return folder_map[relative_dir]

        parts = relative_dir.split("/")
        current_parent_id = root_folder_id
        current_path = ""

        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else part
            if current_path in folder_map:
                current_parent_id = folder_map[current_path]
                continue

            new_folder_id = GdriveManager.create_folder(part, parent_id=current_parent_id)
            folder_map[current_path] = new_folder_id
            current_parent_id = new_folder_id

        return current_parent_id

    @staticmethod
    def download_file(file_id: str, local_path: Path, remote_mtime: float):
        """
        Downloads a Drive file to local_path atomically (via a temp file + rename),
        then sets the local file's mtime to match remote_mtime so future diffs
        compare correctly. Atomic so a kill mid-download can't leave a corrupted
        save file at the real path.
        """
        logger.debug(f"download_file file_id: '{file_id}' local_path: '{local_path}' remote_mtime: '{remote_mtime}'")
        service = GdriveManager._get_drive_service()
        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = local_path.with_name(local_path.name + ".part")

        request = service.files().get_media(fileId=file_id)
        with io.FileIO(str(tmp_path), "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        os.replace(tmp_path, local_path)
        os.utime(local_path, (remote_mtime, remote_mtime))
        logger.debug(f"Downloaded '{local_path}' from Drive")

    @staticmethod
    def delete_file(file_id: str):
        """
        Moves a file to Drive's Trash rather than permanently deleting it,
        giving a ~30-day recovery window if a deletion turns out to be wrong.
        """
        logger.debug(f"delete_file file_id: '{file_id}'")
        service = GdriveManager._get_drive_service()
        service.files().update(fileId=file_id, body={"trashed": True}).execute()
        logger.debug(f"Trashed Drive file {file_id}")


class GdriveDeviceFlowWorker(QThread):
    """
    Background poller for the device flow. Runs request_device_code() first
    (emitted via device_code_ready), then polls until success/timeout/error.
    """
    device_code_ready = Signal(dict)   # user_code, verification_url, etc.
    login_success = Signal(dict)       # full token response
    login_failed = Signal(str)         # error message
    login_timeout = Signal()

    def __init__(self, client_id: str, client_secret: str, timeout_seconds: int = 60):
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout_seconds = timeout_seconds
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            device_info = GdriveManager.request_device_code(self.client_id)
        except Exception as e:
            self.login_failed.emit(f"Failed to start sign-in: {e}")
            return

        self.device_code_ready.emit(device_info)

        device_code = device_info["device_code"]
        interval = device_info.get("interval", 5)
        elapsed = 0

        while elapsed < self.timeout_seconds:
            if self._cancelled:
                return

            self.msleep(interval * 1000)
            elapsed += interval

            try:
                token_data = GdriveManager.poll_once(self.client_id, self.client_secret, device_code)
            except Exception as e:
                self.login_failed.emit(str(e))
                return

            if token_data:
                self.login_success.emit(token_data)
                return

        self.login_timeout.emit()

    