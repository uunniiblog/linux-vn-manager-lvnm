import subprocess
import os
import ntpath
import shutil
import time
import config
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class SystemUtils:
    _afk_process = None

    @staticmethod
    def is_wine_or_proton(pid):
        try:
            env_result = SystemUtils.get_process_environ(pid)
            # print(f'env_result: {env_result}')          
            return ".exe" in env_result
        except Exception as e:
            logger.error(f"[ERROR] is_wine_or_proton failed: {e}")
            return False

    @staticmethod
    def get_window_list(utils, only_show_wine=False):
        """Returns a list of tuples: (title, window_id) using the detected DE utils."""
        if not utils: return []

        window_list = []
        try:
            window_ids = utils.get_all_window_ids()

            for wid in window_ids:
                try:
                    title = utils.get_window_name(wid)
                    if not title:
                        continue

                    if only_show_wine:
                        pid_str = utils.get_window_pid(wid)
                        if pid_str and pid_str.isdigit() and SystemUtils.is_wine_or_proton(int(pid_str)):
                            window_list.append((title, wid))
                    else:
                        window_list.append((title, wid))
                except Exception:
                    continue
        except Exception:
            pass

        return window_list

    @staticmethod
    def get_process_environ(pid):
        """Gets environment variables using ps eww {pid} command"""
        try:
            result = subprocess.check_output(
                ["ps", "eww", str(pid)], 
                stderr=subprocess.DEVNULL, 
                text=True
            )
            return result
        except Exception:
            return ""

    @staticmethod
    def get_pid_by_name(process_name):
        """
        Extracts the filename and searches the process list.
        Matches the logic needed for Wine/Proton backslashes.
        """
        filename = os.path.basename(process_name)
        my_pid = str(os.getpid()) # Get the PID of the tracker itself
        logger.debug(f"my_pid {my_pid}")
        
        try:
            # -f: search full command line
            output = subprocess.check_output(["pgrep", "-f", filename], text=True)
            pids = output.strip().splitlines()
            
            # Filter out our own PID so we don't track ourselves
            valid_pids = [p for p in pids if p != my_pid]
            
            if not valid_pids:
                return None

            # Priority 1: Look for the process with the Windows-style backslash (The Game)
            for pid in reversed(valid_pids):
                try:
                    cmdline = Path(f"/proc/{pid}/cmdline").read_text()
                    if "\\" in cmdline:
                        return pid
                except: continue

            # Priority 2: Return the newest process that isn't us
            return valid_pids[-1]
        except Exception:
            return None

    @staticmethod
    def get_app_name_from_pid(pid):
        """Returns the executable name from a PID."""
        is_wine = SystemUtils.is_wine_or_proton(pid)
        
        name = ""
        if is_wine:
            name = SystemUtils.get_wine_process_name(pid)
        else:
            name = SystemUtils.get_process_name(pid)
            
        # Stip paths
        return ntpath.basename(name)

    @staticmethod
    def get_process_name(pid):
        """Returns the executable name from a PID for native applications."""
        try:
            # Method 1: The most accurate way (resolves symlinks)
            # /proc/{pid}/exe is a symlink to the actual binary
            exe_path = os.readlink(f"/proc/{pid}/exe")
            return os.path.basename(exe_path)
        except (FileNotFoundError, PermissionError, OSError):
            pass

        try:
            # Method 2: Fallback to reading the command line (cmdline)
            with open(f"/proc/{pid}/cmdline", "r") as f:
                # cmdline is null-separated, take the first part
                cmd = f.read().split('\0')[0]
                return os.path.basename(cmd)
        except Exception:
            pass

        return "Unknown"

    @staticmethod
    def get_wine_process_name(pid):
        """Extracts the Windows executable name from a Wine/Proton PID."""
        try:
            with open(f"/proc/{pid}/cmdline", "r") as f:
                # cmdline is separated by null bytes
                cmd_parts = f.read().split('\0')
            
            for part in cmd_parts:
                # Filter out empty strings and look for .exe
                clean_part = part.strip()
                if clean_part.lower().endswith(".exe"):
                    return clean_part
            
            # Fallback to the first argument if no .exe found
            return cmd_parts[0] if cmd_parts else "Unknown"
        except Exception:
            return "Unknown"

    @staticmethod
    def get_exe_name_from_cmdline( pid):
        """Extracts the filename from /proc/pid/cmdline (handles Windows and Linux paths)."""
        try:
            with open(f"/proc/{pid}/cmdline", "r") as f:
                full_path = f.read().split('\0')[0]
                return ntpath.basename(full_path)
        except:
            return None
    
    @staticmethod
    def get_full_cmdline(pid):
        """Gets the full command line for a PID."""
        try:
            with open(f"/proc/{pid}/cmdline", "r") as f:
                return f.read().replace('\0', ' ')
        except:
            return ""

    @staticmethod
    def is_swayidle_installed():
        return shutil.which("swayidle") is not None

    @staticmethod
    def start_afk_daemon(timeout_seconds):
        """Launches the swayidle observer in the background."""
        if not SystemUtils.is_swayidle_installed():
            logger.error("[AFK] swayidle not found. AFK detection disabled.")
            return None

        # Clean up any leftover files
        if config.AFK_FILE.exists():
            config.AFK_FILE.unlink()

        cmd = [
            "swayidle", "-w",
            "timeout", str(timeout_seconds), f"date +%s > {config.AFK_FILE}",
            "resume", f"rm -f {config.AFK_FILE}"
        ]

        try:
            # We use Popen so it runs non-blocking in the background
            SystemUtils._afk_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            logger.info(f"AFK Observer started at Threshold: {timeout_seconds}s")
            return SystemUtils._afk_process
        except Exception as e:
            logger.error(f"[AFK] Failed to start swayidle: {e}")
            return None

    @staticmethod
    def stop_afk_daemon():
        """Kills the background swayidle process."""
        if SystemUtils._afk_process:
            SystemUtils._afk_process.terminate()
            SystemUtils._afk_process.wait()
            SystemUtils._afk_process = None
        
        if config.AFK_FILE.exists():
            config.AFK_FILE.unlink()

    @staticmethod
    def get_afk_status():
        """
        Returns (is_afk, idle_duration_seconds).
        duration is 0 if not AFK.
        """
        if not config.AFK_FILE.exists():
            return False, 0

        try:
            start_time = int(config.AFK_FILE.read_text().strip())
            return True, int(time.time() - start_time)
        except:
            return False, 0