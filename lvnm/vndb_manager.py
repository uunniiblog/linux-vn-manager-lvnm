import os
import requests
import config
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
        if existing_path:
            print(f"[VNDB] Local cover found at {existing_path}. Skipping API call.")
            return []

        endpoint = f"{VndbManager.API_URL}/vn"
        
        # Build filters based on provided parameters
        if vndb_id:
            filters = ["id", "=", vndb_id]
        elif name:
            filters = ["search", "=", name]
        else:
            print("[VNDB] Error: No search criteria provided.")
            return None

        payload = {
            "filters": filters,
            "fields": (
                "id, title, released, languages, platforms, "
                "image.url, description, rating, votecount"
            )
        }

        try:
            print(f"[VNDB] calling {endpoint} payload {payload}")
            response = requests.post(endpoint, json=payload, timeout=5)
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            if not results:
                print(f"[VNDB] No results found for ID: {vndb_id} / Name: {name}")
                return []

            print(f"\n[VNDB] Found {len(results)} results. Processing...")

            for vn in results:
                # Print full raw data for this entry
                print(f"\n [VNDB] --- Data for {vn.get('id')} ({vn.get('title')}) ---")
                print(f"[VNDB] {vn}")

                # Download cover if URL exists
                if vn.get("image") and vn["image"].get("url"):
                    VndbManager._download_cover(vn["id"], vn["image"]["url"])
            
            return results

        except Exception as e:
            print(f"[VNDB Error] API Request failed: {e}")
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
                print(f"Saved cover: {target_path.name}")
            else:
                print(f"Cover already exists: {target_path.name}")

        except Exception as e:
            print(f"[Error] Could not download {url}: {e}")