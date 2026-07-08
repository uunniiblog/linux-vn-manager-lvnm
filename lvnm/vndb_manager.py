import os
import requests
import config
import logging
import concurrent.futures
logger = logging.getLogger(__name__)
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from system_utils import SystemUtils
from settings_manager import SettingsManager

class VndbManager:
    API_URL = config.VNDB_API_URL

    @staticmethod
    def get_covers_dir() -> Path:
        """Always returns the current covers directory from settings."""
        return Path(SettingsManager().get(config.USER_CONF_COVERS_PATH, config.COVERS_DIR))

    @staticmethod
    def fetch_and_store_vn(vndb_id: str = None, name: str = None, current_cover_path: str = ""):
        """
        Queries VNDB for one or more visual novels.
        Downloads covers for all results returned by the API.
        """
        logger.debug(f"fetch_and_store_vn {current_cover_path} {vndb_id}")
        existing_path = SystemUtils.get_cover_path(cover_path=current_cover_path, vndb_id=vndb_id)
        logger.debug(f"existing_path {existing_path}")

        skip_download = bool(existing_path)

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

            logger.info(f"[VNDB] Found {len(results)} results. Processing...")

            for vn in results:
                # Print full raw data for this entry
                logger.debug(f"[VNDB] --- Data for {vn.get('id')} ({vn.get('title')}) ---")
                logger.debug(f"[VNDB] {vn}")

                # Download cover if URL exists and image doesn't
                if vn.get("image") and vn["image"].get("url") and not skip_download:
                    target_path = VndbManager._download_cover(vn["id"], vn["image"]["url"])
                    vn["target_path"] = str(target_path)
                else:
                    logger.debug(f"[VNDB] cover already exists, not downloading")
                    vn["target_path"] = existing_path
            
            return results

        except Exception as e:
            logger.error(f"[VNDB Error] API Request failed: {e}")
            return None

    @staticmethod
    def _download_cover(vn_id: str, url: str):
        """Downloads and saves the image to COVERS_DIR."""
        try:
            VndbManager.get_covers_dir().mkdir(parents=True, exist_ok=True)

            ext = os.path.splitext(url)[1] or ".jpg"
            image_name = Path(url).stem
            target_path = VndbManager.get_covers_dir() / f"{vn_id}-{image_name}_p{ext}"

            if target_path.exists():
                logger.info(f"Cover already exists: {target_path.name}")
                return

            temp_dir = config.TEMP_COVERS
            temp_source_path = temp_dir / f"{vn_id}{ext}"
            if temp_source_path.exists():
                logger.info(f"Found {vn_id} in temp. Moving to permanent storage...")
                SystemUtils.move_file(str(temp_source_path), str(target_path))
                return

            # Only download if we don't already have it
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            with open(target_path, 'wb') as handler:
                handler.write(response.content)
            logger.info(f"Saved downloaded cover: {target_path.name}")
            return target_path
        except Exception as e:
            logger.error(f"[Error] Could not download {url}: {e}")
            return ""

    @staticmethod
    def search_vn_temp(name: str, is_cancelled: callable = None):
        """ Search by name max result 15, DL covers in tmp folder"""
        endpoint = f"{VndbManager.API_URL}/vn"
        payload = {
            "filters": ["search", "=", name],
            "fields": "id, title, titles.lang, titles.title, image.url",
            "results": 15,
            "sort": "searchrank"
        }
        
        try:
            response = requests.post(endpoint, json=payload, timeout=5)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            has_more = data.get("more", False)
            
            temp_dir = config.TEMP_COVERS
            temp_dir.mkdir(parents=True, exist_ok=True)

            session = requests.Session()

            def download_single_image(vn):
                # Respect cancellation mid-pool execution
                if is_cancelled and is_cancelled():
                    return vn

                if vn.get("image") and vn["image"].get("url"):
                    url = vn["image"]["url"]
                    ext = os.path.splitext(url)[1] or ".jpg"
                    target = temp_dir / f"{vn['id']}{ext}"

                    if target.exists():
                        vn["local_temp_path"] = str(target)
                        return vn
                    
                    try:
                        # Use a simple request here; ThreadPoolExecutor handles the concurrency
                        img_res = session.get(url, timeout=5)
                        img_res.raise_for_status()
                        with open(target, 'wb') as f:
                            f.write(img_res.content)
                        vn["local_temp_path"] = str(target)
                    except Exception as e:
                        logger.error(f"Failed to download {url}: {e}")
                return vn
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                # map runs the function across all results in parallel
                list(executor.map(download_single_image, results))
            
            return results, has_more
        except Exception as e:
            logger.error(f"Temp search failed: {e}")
            return [], False

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
        logger.debug(f"If no 'ja' found, return the main title {data.get('title')}")
        return data.get('title')

    @staticmethod
    def fetch_release_images_temp(vndb_id: str, main_cover_url: str = None, is_cancelled: callable = None):
        """
        Fetches all releases for a VN, extracts image URLs, downloads them to TEMP_COVERS.
        Returns a list of local file paths.
        """
        endpoint = f"{VndbManager.API_URL}/release"
        payload = {
            "filters": ["vn", "=", ["id", "=", vndb_id]],
            "fields": "images.url"
        }
        
        try:
            response = requests.post(endpoint, json=payload, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            # Use a set to avoid downloading duplicate images across different releases
            image_urls = set()
            
            # Add the main cover URL if provided
            if main_cover_url:
                image_urls.add(main_cover_url)
                
            for release in data.get("results", []):
                for img in release.get("images", []):
                    if img.get("url"):
                        image_urls.add(img["url"])
            
            temp_dir = config.TEMP_COVERS
            temp_dir.mkdir(parents=True, exist_ok=True)
            session = requests.Session()
            local_paths = []

            def download_image(url):
                if is_cancelled and is_cancelled():
                    return None
                    
                # Extract filename from URL or use a hash
                filename = url.split("/")[-1]
                target = temp_dir / filename
                
                if target.exists():
                    return {"local_path": str(target), "url": url}
                    
                try:
                    img_res = session.get(url, timeout=5)
                    img_res.raise_for_status()
                    with open(target, 'wb') as f:
                        f.write(img_res.content)
                    return {"local_path": str(target), "url": url}
                except Exception as e:
                    logger.error(f"Failed to download release image {url}: {e}")
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(download_image, list(image_urls)))
                
            # Filter out Nones (failed downloads or cancelled)
            local_paths = [p for p in results if p is not None]
            return local_paths

        except Exception as e:
            logger.error(f"[VNDB Error] Release API Request failed: {e}")
            return []

# Workers to run in a separate thread
class VndbWorker(QThread):
    # Signal that sends (game_name, results_list)
    finished = Signal(str, list)

    def __init__(self, game_name, vndb_id, current_cover_path=""):
        super().__init__()
        self.game_name = game_name
        self.vndb_id = vndb_id
        self.current_cover_path = current_cover_path

    def run(self):
        # Fetch by vndb id individually
        results = VndbManager.fetch_and_store_vn(vndb_id=self.vndb_id, current_cover_path=self.current_cover_path)
        self.finished.emit(self.game_name, results or [])

class VndbSearchWorker(QThread):
    results_ready = Signal(str, list, bool)

    def __init__(self, search_term):
        super().__init__()
        self.search_term = search_term
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        # Fetch using the name parameter
        results, has_more = VndbManager.search_vn_temp(self.search_term, is_cancelled=lambda: self._cancelled)
        if not self._cancelled:
            self.results_ready.emit(self.search_term, results, has_more)

class VndbReleaseImagesWorker(QThread):
    images_ready = Signal(list)

    def __init__(self, vndb_id, main_cover_url=None):
        super().__init__()
        self.vndb_id = vndb_id
        self.main_cover_url = main_cover_url
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        paths = VndbManager.fetch_release_images_temp(
            self.vndb_id, 
            self.main_cover_url,
            is_cancelled=lambda: self._cancelled
        )
        if not self._cancelled:
            self.images_ready.emit(paths)