import os
import json
import csv
import config
import logging
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class LogManager:
    def __init__(self, log_dir):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.header = "Timestamp_Start;Timestamp_End;Duration;ActiveTime;App;Title;Status;Tags\n"
        self.metadata_file = config.LAST_PLAYED_METADATA

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

    def get_grouped_logs_for_app(self, combined_name):
        """
        Returns an OrderedDict grouped by date: { "2026-01-18": [rows], "2026-01-17": [rows] }
        """
        from collections import OrderedDict
        from collections import defaultdict
        
        grouped_data = defaultdict(list)
        target_process = self._extract_process(combined_name)
        log_file = self.get_app_file(target_process)

        if not log_file.exists():
            return OrderedDict()

        try:
            lines = log_file.read_text(encoding="utf-8").splitlines()
            if len(lines) > 1:
                for line in lines[1:]: # Skip header
                    parts = line.split(";")
                    if len(parts) >= 5:
                        # parts[0] is Timestamp_Start (e.g., '2026-01-18 14:30:00')
                        date_str = parts[0].split(' ')[0] 
                        grouped_data[date_str].append(parts)
        except Exception as e:
            logger.error(f"ERROR getting grouped logs {e}")
            
        # Sort the dictionary by date descending
        return OrderedDict(sorted(grouped_data.items(), reverse=True))

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