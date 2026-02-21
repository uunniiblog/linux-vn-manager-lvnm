import config
from pathlib import Path
from runner_manager import RunnerManagerInterface

class RunnerManagerProtonGE(RunnerManagerInterface):
    PROTON_RUNNER_DIR = config.PROTON_RUNNERS_DIR
    API_URL = config.PROTONGE_API_URL

    def __init__(self):
        self.PROTON_RUNNER_DIR.mkdir(parents=True, exist_ok=True)

    def get_runner_all_releases(self, page=1, per_page=30):
        """ Fetches all GE-Proton releases from GitHub """
        query_url = f"{self.API_URL}?page={page}&per_page={per_page}"
        print(f"Fetching page {page} of Proton-GE releases...")
        data = RunnerManagerInterface.fetch_json(query_url)
        
        if not data:
            print("No releases found or API error.")
            return []

        print(f"\n--- Available Proton-GE Builds (Page {page}) ---")
        filtered_releases = []
        for release in data:
            tag = release.get("tag_name", "")
            filtered_releases.append({'tag': tag})
        
        return filtered_releases
    
    def get_runner_download(self, release_data, progress_callback=None):
        """ Downloads the .tar.gz for the specific GE tag """
        tag = release_data['tag']
        print(f"Preparing to download {tag}...")
        
        # Fetch metadata to find asset URL
        url = f"{self.API_URL}/tags/{tag}"
        data = RunnerManagerInterface.fetch_json(url)
        if not data:
            return

        # GE asset is simply {tag}.tar.gz
        target_name = f"{tag}.tar.gz"
        assets = {a["name"]: a for a in data.get("assets", [])}

        if target_name not in assets:
            print(f"[Error] Could not find {target_name} in release assets.")
            return

        target_asset = assets[target_name]
        download_url = target_asset["browser_download_url"]
        dest_path = self.PROTON_RUNNER_DIR / target_name
        
        if RunnerManagerInterface.download_file(download_url, dest_path, progress_callback=progress_callback):
            RunnerManagerInterface.extract_tar(dest_path, self.PROTON_RUNNER_DIR, tag, compression="gz")

    def get_release_info(self, release_data):
        """ Lists assets for the specific Proton-GE release """
        tag = release_data['tag']
        print(f"\n--- Release Information for {tag} ---")
        
        url = f"{self.API_URL}/tags/{tag}"
        data = RunnerManagerInterface.fetch_json(url)
        
        if not data:
            print(f"Error: Could not retrieve info for {tag}")
            return

        print(f"GitHub Assets:")
        for asset in data.get("assets", []):
            size_mb = asset.get("size", 0) / (1024 * 1024)
            print(f"  - {asset.get('name'):<45} ({size_mb:.2f} MB)")