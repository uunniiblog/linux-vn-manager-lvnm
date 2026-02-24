import config
import logging
logger = logging.getLogger(__name__)
from pathlib import Path
from runner_manager import RunnerManagerInterface

class RunnerManagerKron4ek(RunnerManagerInterface):
    WINE_RUNNERS_PATH = config.WINE_RUNNERS_DIR
    API_URL = config.KRON4EK_API_URL

    def __init__(self):
        self.WINE_RUNNERS_PATH.mkdir(parents=True, exist_ok=True)

    def get_runner_all_releases(self, page=1, per_page=30):
        """ Fetches wine releases and identifies arch availability """
        query_url = f"{self.API_URL}?page={page}&per_page={per_page}"
        logger.info(f"Fetching page {page} of Kron4ek releases...")
        data = self.fetch_json(query_url)
        
        if not data: return []

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
            return

        # Fetch asset details
        url = f"{self.API_URL}/tags/{tag}"
        data = self.fetch_json(url)
        if not data: return

        suffix = "amd64-wow64" if arch == "wow64" else "amd64"
        # Only search for vanilla builds
        target_name = f"wine-{tag}-{suffix}.tar.xz"
        assets = {a["name"]: a for a in data.get("assets", [])}

        if target_name not in assets:
            logger.error(f"Could not find {target_name} in release assets.")
            return

        target_asset = assets[target_name]
        dest_path = self.WINE_RUNNERS_PATH / target_name
        
        if self.download_file(target_asset["browser_download_url"], dest_path, progress_callback=progress_callback):
            self.extract_tar(dest_path, self.WINE_RUNNERS_PATH, tag, compression="xz")

    def get_release_info(self, release_data):
        """ Lists all assets for a specific Kron4ek release """
        tag = release_data['tag']
        logger.info(f"\n--- Release Information for {tag} ---")
        url = f"{self.API_URL}/tags/{tag}"
        data = self.fetch_json(url)
        if not data: return

        for asset in data.get("assets", []):
            size_mb = asset.get("size", 0) / (1024 * 1024)
            logger.info(f"  - {asset.get('name'):<45} ({size_mb:.2f} MB)")