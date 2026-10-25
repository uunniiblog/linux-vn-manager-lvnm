import os
import json
import csv
import io
import config
import logging
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from settings_manager import SettingsManager
from emulation_manager import EmulationManager
from gdrive_manager import GdriveManager
from PySide6.QtCore import QThread, Signal, QObject

logger = logging.getLogger(__name__)

class LogManager(QObject):
    _instance = None

    # Signals for the UI
    gdrive_sync_succeeded = Signal(object, dict)
    gdrive_sync_failed = Signal(object, str)

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

    def get_sessions(self, app_name):
        """Return the stored sessions for an app in CSV order."""
        log_file = self.get_app_file(app_name)
        if not log_file.exists():
            return []
        try:
            with log_file.open("r", encoding="utf-8", newline="") as file:
                return list(csv.DictReader(file, delimiter=";"))
        except (OSError, UnicodeError, csv.Error) as error:
            raise RuntimeError(f"Could not read tracking sessions: {error}") from error

    def delete_log_file(self, app_name):
        """Delete an app's complete tracking log and its cached title."""
        log_file = self.get_app_file(app_name)
        try:
            log_file.unlink()
        except FileNotFoundError as error:
            raise ValueError("The selected log file no longer exists. Refresh the list and try again.") from error
        except OSError as error:
            raise RuntimeError(f"Could not delete tracking log: {error}") from error

        if self.metadata_file.exists():
            try:
                cache = json.loads(self.metadata_file.read_text(encoding="utf-8"))
                if app_name in cache:
                    del cache[app_name]
                    self.metadata_file.write_text(json.dumps(cache, indent=4, ensure_ascii=False), encoding="utf-8")
            except (OSError, ValueError) as error:
                logger.warning(f"Could not update tracking app cache after deleting log file: {error}")

    def delete_session(self, app_name, row_index, expected_row=None):
        """Remove one session while preserving every other CSV line exactly."""
        log_file = self.get_app_file(app_name)
        try:
            original = log_file.read_bytes()
            rows = list(csv.DictReader(io.StringIO(original.decode("utf-8")), delimiter=";"))
            lines = original.splitlines(keepends=True)
            if len(lines) != len(rows) + 1:
                raise ValueError("This log contains multiline records and cannot be safely edited.")
            if row_index < 0 or row_index >= len(rows) or expected_row is not None and rows[row_index] != expected_row:
                raise ValueError("The selected session changed. Refresh the list and try again.")

            updated = b"".join(lines[:row_index + 1] + lines[row_index + 2:])
            with tempfile.NamedTemporaryFile(mode="wb", dir=log_file.parent, prefix=f".{log_file.name}.", delete=False) as temporary:
                temporary.write(updated)
                temporary_path = Path(temporary.name)
            try:
                os.replace(temporary_path, log_file)
            finally:
                temporary_path.unlink(missing_ok=True)

            if self.metadata_file.exists():
                try:
                    cache = json.loads(self.metadata_file.read_text(encoding="utf-8"))
                    if app_name in cache:
                        remaining_rows = rows[:row_index] + rows[row_index + 1:]
                        if remaining_rows:
                            latest = max(remaining_rows, key=lambda row: row.get("Timestamp_End") or "")
                            cache[app_name]["last_title"] = latest.get("Title") or app_name
                        else:
                            del cache[app_name]
                        self.metadata_file.write_text(json.dumps(cache, indent=4, ensure_ascii=False), encoding="utf-8")
                except (OSError, ValueError) as error:
                    logger.warning(f"Could not update tracking app cache after deleting a session: {error}")
        except (OSError, UnicodeError, csv.Error) as error:
            raise RuntimeError(f"Could not delete tracking session: {error}") from error

    def update_sessions(self, app_name, changes):
        """Replace selected CSV rows together while preserving unchanged lines."""
        if not changes:
            return
        log_file = self.get_app_file(app_name)
        try:
            original = log_file.read_bytes()
            rows = list(csv.DictReader(io.StringIO(original.decode("utf-8")), delimiter=";"))
            lines = original.splitlines(keepends=True)
            columns = self.header.strip().split(";")
            if len(lines) != len(rows) + 1:
                raise ValueError("This log contains multiline records and cannot be safely edited.")

            changed_indices = set()
            for row_index, expected_row, updated_row in changes:
                if row_index in changed_indices or row_index < 0 or row_index >= len(rows) or rows[row_index] != expected_row:
                    raise ValueError("A tracking entry changed. Refresh the list and try again.")
                if set(updated_row) != set(columns) or updated_row.get("App") != app_name:
                    raise ValueError("The app column cannot be changed in this log.")
                if any(not isinstance(value, str) or any(character in value for character in ";\r\n") for value in updated_row.values()):
                    raise ValueError("Tracking entries cannot contain semicolons or line breaks.")
                changed_indices.add(row_index)

                original_line = lines[row_index + 1]
                ending = b"\r\n" if original_line.endswith(b"\r\n") else b"\n" if original_line.endswith(b"\n") else b""
                content = ";".join(updated_row[column] for column in columns)
                lines[row_index + 1] = content.encode("utf-8") + ending
                rows[row_index] = updated_row

            with tempfile.NamedTemporaryFile(mode="wb", dir=log_file.parent, prefix=f".{log_file.name}.", delete=False) as temporary:
                temporary.write(b"".join(lines))
                temporary_path = Path(temporary.name)
            try:
                os.replace(temporary_path, log_file)
            finally:
                temporary_path.unlink(missing_ok=True)

            if self.metadata_file.exists():
                try:
                    cache = json.loads(self.metadata_file.read_text(encoding="utf-8"))
                    if app_name in cache and rows:
                        latest = max(rows, key=lambda row: row.get("Timestamp_End") or "")
                        cache[app_name]["last_title"] = latest.get("Title") or app_name
                        self.metadata_file.write_text(json.dumps(cache, indent=4, ensure_ascii=False), encoding="utf-8")
                except (OSError, ValueError) as error:
                    logger.warning(f"Could not update tracking app cache after editing sessions: {error}")
        except (OSError, UnicodeError, csv.Error) as error:
            raise RuntimeError(f"Could not update tracking sessions: {error}") from error

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
                appended = self._replace_last_session(log_file, line.encode("utf-8"))
                if appended:
                    self._update_last_played_cache(app_name, session_data['title'])
            
            return log_file
        except Exception as e:
            logger.error(f"Error saving logging session {e}")
            return None

    @staticmethod
    def _replace_last_session(log_file: Path, line: bytes):
        """Replace the last CSV record."""
        with open(log_file, "r+b") as file:
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            if file_size == 0:
                file.write(line)
                return True
            file.seek(file_size - 1)
            has_trailing_newline = file.read(1) == b"\n"
            scan_end = file_size - 1 if has_trailing_newline else file_size
            line_start = 0

            while scan_end > 0:
                chunk_start = max(0, scan_end - 4096)
                file.seek(chunk_start)
                newline_index = file.read(scan_end - chunk_start).rfind(b"\n")
                if newline_index >= 0:
                    line_start = chunk_start + newline_index + 1
                    break
                scan_end = chunk_start

            newline_position = file_size - 1 if has_trailing_newline else line_start - 1
            if newline_position > 0:
                file.seek(newline_position - 1)
                if file.read(1) == b"\r":
                    line = line[:-1] + b"\r\n"

            file.seek(line_start)
            previous_line = file.read(file_size - line_start).rstrip(b"\r\n")
            if line_start == 0 or previous_line.split(b";", 1)[0] != line.split(b";", 1)[0]:
                # The active session was removed, so append instead of replacing another session.
                file.seek(0, os.SEEK_END)
                if not has_trailing_newline:
                    file.write(b"\n")
                file.write(line)
                return True

            file.seek(line_start)
            file.write(line)
            file.truncate()
            return False

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
        elif timeframe == "Current Year":
            start_filter = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

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

    def get_log_name_from_path(self, path_or_game, prefix="", name=""):
        """
        Gets log name
        emulated: {prefix}_{name}
        wine: Extracts Process Name and byte size from file path
        """
        # Extract attributes if a game_card object was passed directly
        if hasattr(path_or_game, "path"):
            path = path_or_game.path
            prefix = getattr(path_or_game, "prefix", "")
            name = getattr(path_or_game, "name", "")
        else:
            path = path_or_game

        if prefix in EmulationManager.get_emulator_prefixes() and name:
            return f"{prefix}_{name}"

        if not path or not os.path.exists(path):
            return ""
        return f"{os.path.basename(path)}_{os.path.getsize(path)}"

    def sync_tracking_to_gdrive(self, game_or_path: str) -> dict:
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

        log_file = self.get_log_name_from_path(game_or_path)
        if log_file is None:
            logger.error(f"Error syncing tracking log to GDrive for '{game_or_path}': log_file is empty. )")
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
            logger.error(f"Error syncing tracking log to GDrive for '{game_or_path}': {e}", exc_info=True)
            raise RuntimeError(f"Error syncing tracking log to GDrive for '{game_or_path}': {e}")


    def start_gdrive_sync(self, game_or_path):
        """
        Runs the tracking-log Gdrive sync for `app_name` in a background thread
        """
        worker_key = getattr(game_or_path, "name", str(game_or_path))

        # Prevent launching duplicate threads for the same app
        if worker_key in self._gdrive_sync_workers:
            logger.warning(f"Tracking sync already in progress for '{app_name}'. Skipping duplicate request.")
            return
 
        worker = TrackingSyncWorker(game_or_path)
        worker.sync_succeeded.connect(self._on_gdrive_sync_succeeded)
        worker.sync_failed.connect(self._on_gdrive_sync_failed)
        worker.finished.connect(lambda: self._gdrive_sync_workers.pop(worker_key, None))
 
        self._gdrive_sync_workers[worker_key] = worker
        worker.start()
 
    def _on_gdrive_sync_succeeded(self, game_or_path, result: dict):
        logger.info(f"Tracking sync completed for '{game_or_path}': {result.get('status')}")
        self.gdrive_sync_succeeded.emit(game_or_path, result)
 
    def _on_gdrive_sync_failed(self, game_or_path, error_message: str):
        self.gdrive_sync_failed.emit(game_or_path, error_message)


class TrackingSyncWorker(QThread):
    """Runs LogManager.sync_tracking_to_gdrive() in a background thread."""
    sync_succeeded = Signal(object, dict)
    sync_failed = Signal(object, str)
 
    def __init__(self, game_or_path):
        super().__init__()
        self.game_or_path = game_or_path
 
    def run(self):
        try:
            manager = LogManager()
            result = manager.sync_tracking_to_gdrive(self.game_or_path)
            self.sync_succeeded.emit(self.game_or_path, result)
        except Exception as e:
            logger.error(f"Error syncing tracking log to GDrive for '{self.game_or_path}': {e}", exc_info=True)
            self.sync_failed.emit(self.game_or_path, str(e))