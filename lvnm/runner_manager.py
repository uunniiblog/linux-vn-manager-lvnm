import os
import json
import tarfile
import urllib.request
import urllib.error
import config
from abc import ABC, abstractmethod
from pathlib import Path

class RunnerManagerInterface:
    PROTON_DIR = config.PROTON_RUNNERS_DIR
    WINE_DIR = config.WINE_RUNNERS_DIR

    @abstractmethod
    def get_runner_all_releases(self): pass

    @abstractmethod
    def get_runner_download(self, tag): pass

    @abstractmethod
    def get_release_info(self, tag): pass

    @staticmethod
    def fetch_json(url):
        """Helper to fetch JSON data from a URL using urllib"""
        try:
            with urllib.request.urlopen(url) as response:
                if response.status == 200:
                    return json.loads(response.read().decode())
        except urllib.error.URLError as e:
            print(f"[Error] Failed to connect to GitHub: {e}")
        return None

    @staticmethod
    def download_file(url, dest_path):
        """Helper to download a file with a progress bar"""
        try:
            print(f"Downloading: {url}...")
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
                            print(f"\rProgress: [{percent:.1f}%] {downloaded}/{total_size} bytes", end='')

            return True
        except Exception as e:
            print(f"\n[Error] Download failed: {e}")
            if dest_path.exists():
                os.remove(dest_path)
            return False

    @staticmethod
    def extract_tar(tar_path, dest_dir, tag, compression="gz"):
        """Handles extraction and cleanup for .tar.gz (gz) or .tar.xz (xz)"""
        print(f"\nExtracting...")
        mode = f"r:{compression}"
        try:
            with tarfile.open(tar_path, mode) as tar:
                members = tar.getmembers()
                root_folder = members[0].name.split('/')[0] if members else f"runner-{tag}"
                tar.extractall(path=dest_dir)
                
            print(f"Success! Runner installed at: {dest_dir / root_folder}")
            if tar_path.exists():
                os.remove(tar_path)
            return True
        except Exception as e:
            print(f"[Error] Extraction failed: {e}")
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