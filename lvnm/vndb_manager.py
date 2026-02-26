import os
import requests
import config
import logging
logger = logging.getLogger(__name__)
from PySide6.QtCore import QThread, Signal
from system_utils import SystemUtils

class VndbManager:
    API_URL = config.VNDB_API_URL
    COVERS_DIR = config.COVERS_DIR

    @staticmethod
    def fetch_and_store_vn(vndb_id: str = None, name: str = None):
        """
        Queries VNDB for one or more visual novels.
        Downloads covers for all results returned by the API.
        """

        existing_path = SystemUtils.get_cover_path(vndb_id)
        # if existing_path:
        #     logger.info(f"[VNDB] Local cover found at {existing_path}. Skipping API call.")
        #     return []

        endpoint = f"{VndbManager.API_URL}/vn"
        
        # Build filters based on provided parameters
        if vndb_id:
            filters = ["id", "=", vndb_id]
        elif name:
            filters = ["search", "=", name]
        else:
            logger.error("[VNDB] Error: No search criteria provided.")
            return None

        payload = {
            "filters": filters,
            "fields": "id, title, titles.lang, titles.title, titles.latin, released, languages, image.url, description, rating, votecount"
        }

        try:
            logger.info(f"[VNDB] calling {endpoint} payload {payload}")
            response = requests.post(endpoint, json=payload, timeout=5)
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if not results:
                logger.info(f"[VNDB] No results found for ID: {vndb_id} / Name: {name}")
                return []

            logger.info(f"\n[VNDB] Found {len(results)} results. Processing...")

            for vn in results:
                # Print full raw data for this entry
                logger.debug(f"\n [VNDB] --- Data for {vn.get('id')} ({vn.get('title')}) ---")
                logger.debug(f"[VNDB] {vn}")

                # Download cover if URL exists and image doesn't
                if vn.get("image") and vn["image"].get("url") and not existing_path:
                    VndbManager._download_cover(vn["id"], vn["image"]["url"])
            
            return results

        except Exception as e:
            logger.error(f"[VNDB Error] API Request failed: {e}")
            return None

    @staticmethod
    def _download_cover(vn_id: str, url: str):
        """Downloads and saves the image to COVERS_DIR."""
        try:
            VndbManager.COVERS_DIR.mkdir(parents=True, exist_ok=True)

            ext = os.path.splitext(url)[1] or ".jpg"
            target_path = VndbManager.COVERS_DIR / f"{vn_id}{ext}"

            # Only download if we don't already have it
            if not target_path.exists():
                img_data = requests.get(url, timeout=5).content
                with open(target_path, 'wb') as handler:
                    handler.write(img_data)
                logger.info(f"Saved cover: {target_path.name}")
            else:
                logger.info(f"Cover already exists: {target_path.name}")

        except Exception as e:
            logger.error(f"[Error] Could not download {url}: {e}")

    @staticmethod
    def get_original_title(data):
        """
        Extracts the Japanese title from the titles array.
        """
        if 'titles' not in data:
            logger.debug(f"data.get('title') {data.get('title')}")
            return data.get('title') # Fallback to main title

        # Look for the Japanese entry
        for t in data['titles']:
            if t.get('lang') == 'ja':
                logger.debug(f"[VNDB] found original title {t.get('title')}")
                return t.get('title')

        # If no 'ja' found, return the main title
        logger.debug(f"If no 'ja' found, return the main title {data.get['title']}")
        return data.get('title')

class VndbWorker(QThread):
    # Signal that sends (game_name, results_list)
    finished = Signal(str, list)

    def __init__(self, game_name, vndb_id):
        super().__init__()
        self.game_name = game_name
        self.vndb_id = vndb_id

    def run(self):
        # This runs in a separate thread
        results = VndbManager.fetch_and_store_vn(vndb_id=self.vndb_id)
        self.finished.emit(self.game_name, results or [])