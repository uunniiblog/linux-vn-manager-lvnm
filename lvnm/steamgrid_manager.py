import os
import requests
import config
import logging
import concurrent.futures
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class SteamGridDbManager:
    SGDB_API_URL = config.SGDB_API_URL
    STEAM_STORE_API_URL = config.STEAM_STORE_API_URL
    STEAM_CDN = config.STEAM_CDN

    @staticmethod
    def _get_api_key() -> str:
        return SettingsManager().get(config.USER_CONF_SGDB_API_KEY, "")

    @staticmethod
    def _headers(api_key: str = "") -> dict:
        key = api_key or SteamGridDbManager._get_api_key()
        return {"Authorization": f"Bearer {key}"}

    @staticmethod
    def search_games(name: str, api_key: str = "") -> list:
        """
        Searches SteamGridDB for games matching the given name.
        Returns a list of dicts: [{id, name, types, verified}, ...]
        """
        if not name:
            return []

        url = f"{SteamGridDbManager.SGDB_API_URL}/search/autocomplete/{requests.utils.quote(name)}"
        try:
            response = requests.get(url, headers=SteamGridDbManager._headers(api_key), timeout=5)
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                return data.get("data", [])
            logger.warning(f"[SGDB] Search returned no success for '{name}'")
            return []
        except Exception as e:
            logger.error(f"[SGDB] Search failed for '{name}': {e}")
            return []

    @staticmethod
    def fetch_grids_temp(game_id: int, api_key: str = "", is_cancelled: callable = None) -> list:
        """
        Fetches vertical cover images (grids, 600x900) for a SteamGridDB game ID.
        Downloads thumbs to TEMP_COVERS. Returns list of dicts:
        [{local_path, full_url, thumb_url, style, author}, ...]
        """
        url = f"{SteamGridDbManager.SGDB_API_URL}/grids/game/{game_id}"
        params = {}
        return SteamGridDbManager._fetch_and_download(
            url, params, api_key, prefix="sgdb_grid", is_cancelled=is_cancelled
        )

    @staticmethod
    def fetch_heroes_temp(game_id: int, api_key: str = "", is_cancelled: callable = None) -> list:
        """
        Fetches horizontal hero/banner images (1920x620) for a SteamGridDB game ID.
        Downloads thumbs to TEMP_COVERS. Returns list of dicts:
        [{local_path, full_url, thumb_url, style, author}, ...]
        """
        url = f"{SteamGridDbManager.SGDB_API_URL}/heroes/game/{game_id}"
        return SteamGridDbManager._fetch_and_download(
            url, {}, api_key, prefix="sgdb_hero", is_cancelled=is_cancelled
        )

    @staticmethod
    def fetch_steam_assets_temp(game_id: int, game_name: str, api_key: str = "", is_cancelled: callable = None) -> list:
        """
        Fetches original Steam store assets by pulling them from Steam's CDN.
        Requires the SGDB game to have a linked Steam App ID.
        Returns list of dicts:
        [{local_path, full_url, thumb_url, style, author}, ...]
        """
        steam_app_id = SteamGridDbManager.get_steam_app_id(game_name)
        if not steam_app_id:
            logger.info(f"[SGDB] No Steam App ID found for '{game_name}', skipping Steam assets.")
            return []

        BASE = f"{SteamGridDbManager.STEAM_CDN}/{steam_app_id}"
        ASSETS = [
            ("header",  f"{BASE}/header.jpg",             "Steam Header"),
            ("capsule", f"{BASE}/library_600x900.jpg",    "Steam Capsule"),
            ("hero",    f"{BASE}/library_hero.jpg",       "Steam Hero"),
            ("logo",    f"{BASE}/logo.png",               "Steam Logo"),
        ]

        temp_dir = config.TEMP_COVERS
        temp_dir.mkdir(parents=True, exist_ok=True)
        session = requests.Session()

        results = []
        for asset_type, url, style_label in ASSETS:
            if is_cancelled and is_cancelled():
                break

            ext = os.path.splitext(url)[1] or ".jpg"
            filename = f"steam_{steam_app_id}_{asset_type}{ext}"
            target = temp_dir / filename

            if not target.exists():
                try:
                    img_res = session.get(url, timeout=10)
                    img_res.raise_for_status()
                    with open(target, "wb") as f:
                        f.write(img_res.content)
                except Exception as e:
                    logger.warning(f"[SGDB] Steam asset '{asset_type}' not available: {e}")
                    continue  # Some games won't have all asset types

            results.append({
                "local_path": str(target),
                "full_url": url,
                "thumb_url": url,
                "width": 0,
                "height": 0,
                "style": style_label,
                "author": "Steam (original)",
            })

        return results

    @staticmethod
    def _fetch_and_download(url: str, params: dict, api_key: str, prefix: str, is_cancelled: callable = None) -> list:
        """
        Calls a SteamGridDB image endpoint, downloads thumbs to TEMP_COVERS,
        returns a list of result dicts with local_path attached.
        """
        try:
            response = requests.get(
                url,
                headers=SteamGridDbManager._headers(api_key),
                params=params,
                timeout=5
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                logger.warning(f"[SGDB] Endpoint {url} returned success=false")
                return []

            results = data.get("data", [])
            if not results:
                return []

            temp_dir = config.TEMP_COVERS
            temp_dir.mkdir(parents=True, exist_ok=True)
            session = requests.Session()

            def download_thumb(item):
                if is_cancelled and is_cancelled():
                    return None

                thumb_url = item.get("thumb") or item.get("url")
                full_url = item.get("url", "")
                if not thumb_url:
                    return None

                filename = f"{prefix}_{item['id']}{os.path.splitext(thumb_url)[1] or '.jpg'}"
                target = temp_dir / filename

                if not target.exists():
                    try:
                        img_res = session.get(thumb_url, timeout=5)
                        img_res.raise_for_status()
                        with open(target, "wb") as f:
                            f.write(img_res.content)
                    except Exception as e:
                        logger.error(f"[SGDB] Failed to download thumb {thumb_url}: {e}")
                        return None

                return {
                    "local_path": str(target),
                    "full_url": full_url,
                    "thumb_url": thumb_url,
                    "style": item.get("style", ""),
                    "width": item.get("width", 0),
                    "height": item.get("height", 0),
                    "author": item.get("author", {}).get("name", ""),
                }

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                downloaded = list(executor.map(download_thumb, results))

            return [d for d in downloaded if d is not None]

        except Exception as e:
            logger.error(f"[SGDB] Request to {url} failed: {e}")
            return []

    @staticmethod
    def download_full_image(full_url: str, game_id_str: str, role: str) -> str:
        """
        Downloads the full-resolution image from full_url and saves it to dest_path.
        Used at save time instead of using the thumbnail.
        """
        try:
            ext = Path(full_url).suffix or ".jpg"
            suffix = "_p" if role == "vertical" else "_h"

            covers_dir = Path(SettingsManager().get(config.USER_CONF_COVERS_PATH, config.COVERS_DIR))
            dest = covers_dir / f"{game_id_str}{suffix}{ext}"

            response = requests.get(full_url, timeout=10)
            response.raise_for_status()

            with open(dest, "wb") as f:
                f.write(response.content)
            logger.info(f"[SGDB] Downloaded full image to {dest}")
            return str(dest)

        except Exception as e:
            logger.error(f"[SGDB] Failed to download full image {full_url}: {e}")
            return ""

    @staticmethod
    def get_steam_app_id(game_name: str) -> str | None:
        """
        Searches the Steam store by name and returns the first matching App ID.
        Uses Steam's public search API, no key required.
        """
        # Split on ' / ' and try each part, shortest/simplest first
        candidates = [part.strip() for part in game_name.split(" / ") if part.strip()]
        # Also try the full name as a fallback
        if game_name not in candidates:
            candidates.append(game_name)

        for term in candidates:
            try:
                response = requests.get(
                    SteamGridDbManager.STEAM_STORE_API_URL,
                    params={"term": term, "l": "english", "cc": "US"},
                    timeout=5,
                )
                response.raise_for_status()
                data = response.json()
                items = data.get("items", [])
                logger.debug(f"[SGDB] Steam search '{term}' → {len(items)} results")
                if items:
                    app_id = str(items[0]["id"])
                    logger.info(f"[SGDB] Matched '{term}' → Steam App ID {app_id}")
                    return app_id
            except Exception as e:
                logger.error(f"[SGDB] Steam store search failed for '{game_name}': {e}")
                return None


# Workers
class SteamGridDbSearchWorker(QThread):
    """Searches SteamGridDB by game name. Emits a list of game dicts."""
    results_ready = Signal(list)

    def __init__(self, search_term: str, api_key: str = ""):
        super().__init__()
        self.search_term = search_term
        self.api_key = api_key
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        results = SteamGridDbManager.search_games(self.search_term, self.api_key)
        if not self._cancelled:
            self.results_ready.emit(results)


class SteamGridDbImagesWorker(QThread):
    """
    Fetches vertical grids and horizontal heroes for a given SteamGridDB game ID.
    Emits two lists: (grid_results, hero_results) where each item is a dict with
    local_path, full_url, style, author, etc.
    """
    images_ready = Signal(list, list)

    def __init__(self, game_id: int, game_name: str, api_key: str = ""):
        super().__init__()
        self.game_id = game_id
        self.game_name = game_name  
        self.api_key = api_key
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        grids = SteamGridDbManager.fetch_grids_temp(
            self.game_id, self.api_key, is_cancelled=lambda: self._cancelled
        )
        heroes = SteamGridDbManager.fetch_heroes_temp(
            self.game_id, self.api_key, is_cancelled=lambda: self._cancelled
        )
        steam = SteamGridDbManager.fetch_steam_assets_temp(
            self.game_id, self.game_name, self.api_key, is_cancelled=lambda: self._cancelled
        )
        if not self._cancelled:
            self.images_ready.emit(grids, heroes + steam)