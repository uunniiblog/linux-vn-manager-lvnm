import os
import json
import csv
import config
import logging
from pathlib import Path
from datetime import datetime, timedelta
from settings_manager import SettingsManager
from gdrive_manager import GdriveManager
from PySide6.QtCore import QThread, Signal, QObject

logger = logging.getLogger(__name__)

class LogManager(QObject):
    _instance = None

    # Signals for the UI
    gdrive_sync_succeeded = Signal(str, dict)
    gdrive_sync_failed = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.user_settings = SettingsManager()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.header = "Timestamp_Start;Timestamp_End;Duration;ActiveTime;App;Title;Status;Tags\n"
        self.metadata_file = config.LAST_PLAYED_METADATA
        self._gdrive_sync_workers = {}

    @classmethod
    def get_instance(cls):
        """Singleton class used for the Gdrive sync/signal API."""
        if cls._instance is None:
            cls._instance = LogManager()
        return cls._instance

    @property
    def log_dir(self) -> Path:
        """Dynamically retrieves the logs directory from settings."""
        path_val = self.user_settings.get(config.USER_CONF_LOGS_PATH, config.LOG_DIR)
        return Path(path_val)
        
    def format_duration(self, seconds):
        """Converts seconds to H:MM:SS."""
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}:{m:02d}:{s:02d}"

    def get_app_file(self, app_name):
        """
        Returns the path for logs/{app_name}.csv
        Sanitizes the app name to prevent invalid filenames.
        """
        # Remove invalid characters for filenames
        safe_name = "".join(c for c in app_name if c.isalnum() or c in (' ', '.', '_', '-')).strip()
        if not safe_name:
            safe_name = "unknown_app"
            
        return self.log_dir / f"{safe_name}.csv"

    def save_session(self, session_data, is_update=False):
        """
        Saves or updates a log entry in the specific app's file.
        session_data: dict containing all columns
        is_update: If True, replaces the last line in the file
        """
        app_name = session_data['app']
        log_file = self.get_app_file(app_name)
        
        # Prepare the line
        line = (
            f"{session_data['start'].strftime('%Y-%m-%d %H:%M:%S')};"
            f"{session_data['end'].strftime('%Y-%m-%d %H:%M:%S')};"
            f"{self.format_duration(session_data['duration'])};"
            f"{self.format_duration(session_data['active_time'])};"
            f"{session_data['app']};"
            f"{session_data['title']};"
            f"{session_data['status']};"
            f"{session_data['tags']}\n"
        )

        try:
            # Ensure file and header exist
            if not log_file.exists() or log_file.stat().st_size == 0:
                log_file.write_text(self.header, encoding="utf-8")

            if not is_update:
                # Append new session
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(line)
                self._update_last_played_cache(app_name, session_data['title'])
            else:
                # Overwrite the last line (Periodic Save)
                content = log_file.read_text(encoding="utf-8").splitlines()
                if len(content) > 1: # Don't overwrite header
                    content[-1] = line.strip()
                    log_file.write_text("\n".join(content) + "\n", encoding="utf-8")
                else:
                    # Fallback if file was somehow cleared
                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(line)
            
            return log_file
        except Exception as e:
            logger.error(f"Error saving logging session {e}")
            return None

    def get_total_app_playtime(self, app_name):
        """
        Scans the specific app's log to find total playtime.
        """
        total_seconds = 0
        log_file = self.get_app_file(app_name)
        
        if not log_file.exists():
            return 0

        try:
            lines = log_file.read_text(encoding="utf-8").splitlines()
            for line in lines[1:]: # Skip header
                parts = line.split(";")
                if len(parts) >= 5:
                    total_seconds += self._duration_to_seconds(parts[3])
        except Exception as e:
            logger.error(f"Error Reading total playtime: {e}")
            
        return total_seconds

    def get_all_tracked_apps(self):
        """Returns a unique list of App names based on the CSV files present."""
        apps = set()
        for log_file in self.log_dir.glob("*.csv"):
            try:
                # Read just the first data line to get the actual App name from the file
                # This ensures we get the exact case/formatting stored in the CSV
                with open(log_file, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f, delimiter=';')
                    first_row = next(reader, None)
                    if first_row and 'App' in first_row:
                        apps.add(first_row['App'])
            except Exception: 
                continue
                
        return sorted(list(apps))

    def get_stats_for_app(self, combined_name):
        """Returns total_seconds and a dict of {date: hours} for the individual graph."""
        total_seconds = 0
        daily_data = {}

        # Extract actual process name
        target_process = self._extract_process(combined_name)
        if not target_process:
            return 0, {}

        log_file = self.get_app_file(target_process)
        if not log_file.exists():
            return 0, {}

        try:
            with open(log_file, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    active_time_str = row.get('ActiveTime', '0:0:0')
                    seconds = self._duration_to_seconds(active_time_str)
                    total_seconds += seconds

                    # Group by date for the graph
                    try:
                        date_str = row['Timestamp_Start'].split(' ')[0]
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        # Add hours to that specific date
                        daily_data[date_obj] = daily_data.get(date_obj, 0.0) + (seconds / 3600.0)
                    except (KeyError, ValueError):
                        continue
        except Exception as e:
            logger.error(f"ERROR Error reading {log_file}: {e}")

        return total_seconds, daily_data

    def _update_last_played_cache(self, app_name, title):
        """Updates the timestamp in the hidden JSON cache."""
        cache = {}
        if self.metadata_file.exists():
            try:
                cache = json.loads(self.metadata_file.read_text(encoding="utf-8"))
            except Exception: pass
        
        cache[app_name] = {
            "time": datetime.now().isoformat(),
            "last_title": title
        }
        
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=4, ensure_ascii=False)

    def get_apps_sorted_by_latest(self):
        """Returns app names sorted by their last played timestamp."""
        if not self.metadata_file.exists():
            return self.get_all_tracked_apps()

        try:
            cache = json.loads(self.metadata_file.read_text(encoding="utf-8"))
            # Sort keys by their ISO timestamp values in reverse (newest first)
            sorted_apps = sorted(cache.items(), key=lambda x: x[1]['time'], reverse=True)
            return [f"{data['last_title']} - {app}" for app, data in sorted_apps]
        except Exception as e:
            logger.error(f"Error getting apps {e}")
            return self.get_all_tracked_apps()

    def _extract_process(self, combined_name):
        """Helper to get process from title formatted as 'Title - Process'"""
        if not combined_name: return ""
        if " - " in combined_name:
            return combined_name.rsplit(" - ", 1)[-1].strip()
        return combined_name.strip()

    def _duration_to_seconds(self, duration_str):
        """Converts H:M:S string (e.g. '0:01:12' or '01:02:03') to total seconds."""
        if not duration_str or duration_str == "None":
            return 0
        try:
            parts = list(map(int, duration_str.split(':')))
            if len(parts) == 3: # H:M:S
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            elif len(parts) == 2: # M:S
                return parts[0] * 60 + parts[1]
            return 0
        except (ValueError, TypeError):
            return 0

    def get_global_summary(self, timeframe="All Time"):
        """Aggregates all apps for the summary table across all app files."""
        summary = {} # {app_name: seconds}
        titles = {}  # {app_name: latest_title}
        now = datetime.now()
        
        start_filter = None
        if timeframe == "Today":
            start_filter = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif timeframe == "Last 7 Days":
            start_filter = now - timedelta(days=7)
        elif timeframe == "Last 30 Days":
            start_filter = now - timedelta(days=30)

        # Iterate through every app CSV file
        for log_file in self.log_dir.glob("*.csv"):
            try:
                with log_file.open(mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f, delimiter=';')
                    for row in reader:
                        try:
                            start_dt = datetime.strptime(row['Timestamp_Start'], '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            continue # Skip row if date is mangled
                            
                        if start_filter and start_dt < start_filter:
                            continue
                        
                        app = row.get('App')
                        if not app: continue
                        
                        seconds = self._duration_to_seconds(row.get('ActiveTime', '0:0:0'))
                        summary[app] = summary.get(app, 0) + seconds
                        
                        # Store title (will end up being the last one read from the file)
                        if row.get('Title'):
                            titles[app] = row['Title']
            except Exception as e: 
                logger.error(f"LOG ERROR Processing summary for {log_file.name}: {e}")
                continue

        # Return list of tuples: (app_name, total_seconds, latest_title), sorted by total_seconds
        sorted_data = sorted(summary.items(), key=lambda x: x[1], reverse=True)
        return [(app, seconds, titles.get(app, app)) for app, seconds in sorted_data]

    def get_log_name_from_path(self, path):
        """Extracts Process Name and byte size from file path"""
        if not path or not os.path.exists(path):
            return ""
        return f"{os.path.basename(path)}_{os.path.getsize(path)}"

    def sync_tracking_to_gdrive(self, app_name: str) -> dict:
        """
        Syncs a single time-tracking CSV log file with Google Drive.
        If the remote file is newer, it downloads it. 
        If the local file is newer (or only exists locally), it uploads it.
        """
        savedata_settings = SettingsManager().get(config.USER_CONF_SAVEDATA, {})
        timetracker_settings = self.user_settings.get(config.USER_CONF_TIMETRACKER, {})

        if not savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False) or not timetracker_settings.get(config.USER_CONF_TIMETRACKER_GDRIVE_SYNC, False):
            logger.info("sync_tracking_to_gdrive skipped")
            return {"status": "skipped", "reason": "not configured"}

        log_file = self.get_log_name_from_path(app_name)
        if log_file is None:
            logger.error(f"Error syncing tracking log to GDrive for '{app_name}': log_file is empty. )")
            return {"status": "skipped", "reason": "log_file is empty"}

        logger.debug(f"Starting sync for {log_file}")
        local_path = self.get_app_file(log_file)
        filename = local_path.name
        
        try:
            # Ensure the 'Timetracking' root folder exists in Drive
            root_id = GdriveManager.get_root_folder_id()
            timetracker_folder_id = GdriveManager.find_folder("Timetracking", parent_id=root_id)
            if not timetracker_folder_id:
                timetracker_folder_id = GdriveManager.create_folder("Timetracking", parent_id=root_id)
                
            # Get remote files in the Timetracking folder
            remote_files, _ = GdriveManager.build_remote_tree(timetracker_folder_id)
            remote_meta = remote_files.get(filename)
            
            local_exists = local_path.exists() and local_path.stat().st_size > 0
            
            if local_exists and remote_meta:
                local_mtime = local_path.stat().st_mtime
                remote_time_str = remote_meta["modifiedTime"].replace("Z", "+00:00")
                remote_mtime = datetime.fromisoformat(remote_time_str).timestamp()
                
                if local_mtime > remote_mtime + 1:
                    GdriveManager.upload_file(local_path, timetracker_folder_id, existing_file_id=remote_meta["id"])
                    result = {"status": "uploaded"}
                elif remote_mtime > local_mtime + 1:
                    GdriveManager.download_file(remote_meta["id"], local_path, remote_mtime)
                    result = {"status": "downloaded"}
                else:
                    result = {"status": "skipped", "reason": "in_sync"}
                    
            elif local_exists and not remote_meta:
                GdriveManager.upload_file(local_path, timetracker_folder_id)
                result = {"status": "uploaded"}
                
            elif not local_exists and remote_meta:
                remote_time_str = remote_meta["modifiedTime"].replace("Z", "+00:00")
                remote_mtime = datetime.fromisoformat(remote_time_str).timestamp()
                GdriveManager.download_file(remote_meta["id"], local_path, remote_mtime)
                result = {"status": "downloaded"}
                
            else:
                result = {"status": "skipped", "reason": "no_data"}

            logger.info(f"Tracking sync for '{log_file}' completed with status: {result.get('status')}")
            return result
        except Exception as e:
            logger.error(f"Error syncing tracking log to GDrive for '{app_name}': {e}", exc_info=True)
            raise RuntimeError(f"Error syncing tracking log to GDrive for '{app_name}': {e}")


    def start_gdrive_sync(self, app_name: str):
        """
        Runs the tracking-log Gdrive sync for `app_name` in a background thread
        """
        # Prevent launching duplicate threads for the same app
        if app_name in self._gdrive_sync_workers:
            logger.warning(f"Tracking sync already in progress for '{app_name}'. Skipping duplicate request.")
            return
 
        worker = TrackingSyncWorker(app_name)
        worker.sync_succeeded.connect(self._on_gdrive_sync_succeeded)
        worker.sync_failed.connect(self._on_gdrive_sync_failed)
        worker.finished.connect(lambda: self._gdrive_sync_workers.pop(app_name, None))
 
        self._gdrive_sync_workers[app_name] = worker
        worker.start()
 
    def _on_gdrive_sync_succeeded(self, app_name: str, result: dict):
        logger.info(f"Tracking sync completed for '{app_name}': {result.get('status')}")
        self.gdrive_sync_succeeded.emit(app_name, result)
 
    def _on_gdrive_sync_failed(self, app_name: str, error_message: str):
        self.gdrive_sync_failed.emit(app_name, error_message)


class TrackingSyncWorker(QThread):
    """Runs LogManager.sync_tracking_to_gdrive() in a background thread."""
    sync_succeeded = Signal(str, dict)
    sync_failed = Signal(str, str)
 
    def __init__(self, app_name: str):
        super().__init__()
        self.app_name = app_name
 
    def run(self):
        try:
            manager = LogManager()
            result = manager.sync_tracking_to_gdrive(self.app_name)
            self.sync_succeeded.emit(self.app_name, result)
        except Exception as e:
            logger.error(f"Error syncing tracking log to GDrive for '{self.app_name}': {e}", exc_info=True)
            self.sync_failed.emit(self.app_name, str(e))