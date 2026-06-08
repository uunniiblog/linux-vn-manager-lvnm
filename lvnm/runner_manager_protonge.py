import config
import logging
from pathlib import Path
from runner_manager import RunnerManagerInterface
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class RunnerManagerProtonGE(RunnerManagerInterface):
    API_URL = config.PROTONGE_API_URL

    def __init__(self):
        self.user_settings = SettingsManager()

    @property
    def PROTON_RUNNER_DIR(self) -> Path:
        """
        Dynamically retrieves the Proton runners directory.
        """
        # Fetch from JSON settings, fallback to the hardcoded config path
        path_val = self.user_settings.get(config.USER_CONF_PROTON_RUNNERS_PATH, config.PROTON_RUNNERS_DIR)
        return Path(path_val)

    def get_runner_all_releases(self, page=1, per_page=30):
        """ Fetches all GE-Proton releases from GitHub """
        query_url = f"{self.API_URL}?page={page}&per_page={per_page}"
        logger.info(f"Fetching page {page} of Proton-GE releases...")
        data = RunnerManagerInterface.fetch_json(query_url)
        
        if not data:
            logger.error(f"No data found for {query_url}")
            return []

        filtered_releases = []
        for release in data:
            tag = release.get("tag_name", "")
            filtered_releases.append({'tag': tag})
        
        return filtered_releases
    
    def get_runner_download(self, release_data, progress_callback=None):
        """ Downloads the .tar.gz for the specific GE tag """
        tag = release_data['tag']
        logger.info(f"Preparing to download {tag}...")
        
        # Fetch metadata to find asset URL
        url = f"{self.API_URL}/tags/{tag}"
        data = RunnerManagerInterface.fetch_json(url)
        if not data:
            raise ValueError(f"No data found in {url}")

        # GE asset is simply {tag}.tar.gz
        target_name = f"{tag}.tar.gz"
        assets = {a["name"]: a for a in data.get("assets", [])}

        if target_name not in assets:
            logger.error(f"Could not find {target_name} in release assets.")
            raise ValueError(f"Could not find {target_name} in release assets.")

        target_asset = assets[target_name]
        download_url = target_asset["browser_download_url"]
        dest_path = self.PROTON_RUNNER_DIR / target_name
        
        if RunnerManagerInterface.download_file(download_url, dest_path, progress_callback=progress_callback):
            logger.info(f"Runner {dest_path} downloaded sucessfully.")
            return dest_path
        
        logger.error("Error downloading protonge runner.")
        raise RuntimeError("Error downloading protonge runner.")

    def get_release_info(self, release_data):
        """ Lists assets for the specific Proton-GE release """
        tag = release_data['tag']
        logger.info(f"--- Release Information for {tag} ---")
        
        url = f"{self.API_URL}/tags/{tag}"
        data = RunnerManagerInterface.fetch_json(url)
        
        if not data:
            logger.error(f"Could not retrieve info for {tag}")
            return

        logger.info(f"GitHub Assets:")
        for asset in data.get("assets", []):
            size_mb = asset.get("size", 0) / (1024 * 1024)
            logger.info(f"  - {asset.get('name'):<45} ({size_mb:.2f} MB)")