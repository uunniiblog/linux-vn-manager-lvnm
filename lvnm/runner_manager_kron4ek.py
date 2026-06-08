import config
import logging
from pathlib import Path
from runner_manager import RunnerManagerInterface
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class RunnerManagerKron4ek(RunnerManagerInterface):
    API_URL = config.KRON4EK_API_URL

    def __init__(self):
        self.user_settings = SettingsManager()

    @property
    def WINE_RUNNERS_PATH(self) -> Path:
        """
        Dynamically retrieves the Wine runners directory.
        """
        # Fetch from JSON settings, fallback to the hardcoded config path
        path_val = self.user_settings.get(config.USER_CONF_WINE_RUNNERS_PATH, config.WINE_RUNNERS_DIR)
        return Path(path_val)

    def get_runner_all_releases(self, page=1, per_page=30):
        """ Fetches wine releases and identifies arch availability """
        query_url = f"{self.API_URL}?page={page}&per_page={per_page}"
        logger.info(f"Fetching page {page} of Kron4ek releases...")
        data = self.fetch_json(query_url)
        
        if not data:
            logger.error(f"No data found for {query_url}")
            return []

        filtered_releases = []
        for release in data:
            tag = release.get("tag_name", "")
            if "proton" in tag.lower(): continue

            assets = [a["name"] for a in release.get("assets", [])]
            has_amd64 = any("amd64.tar.xz" in a and "wow64" not in a for a in assets)
            has_wow64 = any("amd64-wow64.tar.xz" in a for a in assets)
            
            if has_amd64 or has_wow64:
                filtered_releases.append({
                    "tag": tag,
                    "has_amd64": has_amd64,
                    "has_wow64": has_wow64
                })
        return filtered_releases

    def get_runner_download(self, release_data, arch="wow64", progress_callback=None):
        """ Downloads the selected arch (wow64/amd64), preferring vanilla builds """
        tag = release_data['tag']
        key = "has_amd64" if arch == "amd64" else "has_wow64"
        if not release_data.get(key):
            logger.error(f"Architecture '{arch}' not available for {tag}.")
            raise ValueError(f"Architecture '{arch}' not available for {tag}.")

        # Fetch asset details
        url = f"{self.API_URL}/tags/{tag}"
        data = self.fetch_json(url)
        if not data:
            raise ValueError(f"No data found in {url}")

        suffix = "amd64-wow64" if arch == "wow64" else "amd64"
        # Only search for vanilla builds
        target_name = f"wine-{tag}-{suffix}.tar.xz"
        assets = {a["name"]: a for a in data.get("assets", [])}

        if target_name not in assets:
            logger.error(f"Could not find {target_name} in release assets.")
            raise ValueError(f"Could not find {target_name} in release assets.")

        target_asset = assets[target_name]
        dest_path = self.WINE_RUNNERS_PATH / target_name
        
        if self.download_file(target_asset["browser_download_url"], dest_path, progress_callback=progress_callback):
            logger.info(f"Runner {dest_path} downloaded sucessfully.")
            return dest_path

        logger.error("Error downloading kron4ek runner.")
        raise RuntimeError("Error downloading kron4ek runner.")

    def get_release_info(self, release_data):
        """ Lists all assets for a specific Kron4ek release """
        tag = release_data['tag']
        logger.info(f"--- Release Information for {tag} ---")
        url = f"{self.API_URL}/tags/{tag}"
        data = self.fetch_json(url)
        if not data: return

        for asset in data.get("assets", []):
            size_mb = asset.get("size", 0) / (1024 * 1024)
            logger.info(f"  - {asset.get('name'):<45} ({size_mb:.2f} MB)")