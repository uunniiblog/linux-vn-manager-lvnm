import os
import json
import tarfile
import urllib.request
import urllib.error
import config
import re
import logging
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

class RunnerManagerInterface:
    PROTON_DIR = config.PROTON_RUNNERS_DIR
    WINE_DIR = config.WINE_RUNNERS_DIR

    @abstractmethod
    def get_runner_all_releases(self, page=1, per_page=30): pass

    @abstractmethod
    def get_runner_download(self, release_data, progress_callback=None): pass

    @abstractmethod
    def get_release_info(self, release_data): pass

    @staticmethod
    def fetch_json(url):
        """Helper to fetch JSON data from a URL using urllib"""
        try:
            with urllib.request.urlopen(url) as response:
                if response.status == 200:
                    return json.loads(response.read().decode())
        except urllib.error.URLError as e:
            logger.error(f"Failed to connect to GitHub: {e}")
        return None

    @staticmethod
    def download_file(url, dest_path, progress_callback=None):
        """Helper to download a file with a progress bar"""
        try:
            logger.info(f"Downloading: {url}...")
            with urllib.request.urlopen(url) as response:
                total_size = int(response.info().get('Content-Length', 0))
                block_size = 8192
                downloaded = 0
                
                with open(dest_path, 'wb') as f:
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        downloaded += len(buffer)
                        f.write(buffer)
                        
                        if total_size > 0:
                            percent = downloaded * 100 / total_size
                            logger.info(f"\rProgress: [{percent:.1f}%] {downloaded}/{total_size} bytes", end='')

                        # Gui
                        if progress_callback and total_size > 0:
                            percent = int(downloaded * 100 / total_size)
                            progress_callback(percent)

            return True
        except Exception as e:
            logger.error(f"Download failed: {e}")
            if dest_path.exists():
                os.remove(dest_path)
            return False

    @staticmethod
    def extract_tar(tar_path, dest_dir, tag, compression="gz"):
        """Handles extraction and cleanup for .tar.gz (gz) or .tar.xz (xz)"""
        logger.info("Extracting...")
        mode = f"r:{compression}"
        try:
            with tarfile.open(tar_path, mode) as tar:
                members = tar.getmembers()
                root_folder = members[0].name.split('/')[0] if members else f"runner-{tag}"
                tar.extractall(path=dest_dir)
                
            logger.info(f"Success! Runner installed at: {dest_dir / root_folder}")
            if tar_path.exists():
                os.remove(tar_path)
            return True
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return False
    
    @staticmethod
    def is_runner_valid(runner_path):
        """Checks if the runner path exists and is functional"""
        path = Path(runner_path)
        if not path.exists():
            return False
        
        if "wine" in str(path).lower():
            return (path / "bin" / "wine").exists()
            
        return True

    @staticmethod
    def get_local_runners(runner_dir, prefixes_data):
        """Returns a list of folder names in the runners directory"""
        if not runner_dir.exists():
            return []

        runner_usage = {}
        for prefix_name, info in prefixes_data.items():
            runner_path = info.get("runner", "")
            if runner_path:
                # Get the folder name from the end of the path
                folder_name = Path(runner_path).name
                if folder_name not in runner_usage:
                    runner_usage[folder_name] = []
                runner_usage[folder_name].append(prefix_name)

        display_list = []
        for d in runner_dir.iterdir():
            if d.is_dir():
                folder_name = d.name
                prefixes = runner_usage.get(folder_name, [])
                
                if prefixes:
                    # Format: runner-name (prefix1, prefix2)
                    display_list.append(f"{folder_name} ({', '.join(prefixes)})")
                else:
                    display_list.append(folder_name)
        
        return sorted(display_list, reverse=True)

    @staticmethod
    def delete_runner(runner_dir, folder_name):
        """Deletes a runner folder from disk"""
        import shutil
        target = runner_dir / folder_name
        if target.exists() and target.is_dir():
            shutil.rmtree(target)
            return True
        return False

    @staticmethod
    def get_all_installed_runners():
        """Returns a dict mapping 'Runner Name' to its full path"""
        runner_dirs = [config.WINE_RUNNERS_DIR, config.PROTON_RUNNERS_DIR]
        runners = [
            (d.name, str(d))
            for base in runner_dirs
            if base.exists()
            for d in base.iterdir()
            if d.is_dir()
        ]
        runners.sort(key=RunnerManagerInterface._natural_sort_key, reverse=True)
        return dict(runners)
    
    @staticmethod
    def _natural_sort_key(item: tuple[str, str]) -> list:
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', item[0])]