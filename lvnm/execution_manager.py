import sys
import subprocess
import threading
import config
import logging
from settings_manager import SettingsManager

settings = SettingsManager()
logger = logging.getLogger(__name__)

class ExecutionManager:
    
    @staticmethod
    def _get_verbosity_env(base_env: dict) -> dict:
        """Augments environment variables based LOG_LEVEL."""
        env = base_env.copy()
        log_level = settings.get("log_level", "info").upper()

        if log_level == "DEBUG":
            # Show everything
            env["UMU_LOG"] = "1"
            # everything else default should be good ? TODO
        
        elif log_level == "INFO":
            # Show only errors and major fixmes
            if "WINEDEBUG" not in env:
                env["WINEDEBUG"] = "-all,err+all,fixme+all"
            env["UMU_LOG"] = "0"
            env["STEAM_LINUX_RUNTIME_VERBOSE"] = "0"
            
        elif log_level == "ERROR":
            env["WINEDEBUG"] = "-all,err+all"
            env["UMU_LOG"] = "0"
            env["STEAM_LINUX_RUNTIME_VERBOSE"] = "0"
            env["PRESSURE_VESSEL_VERBOSE"] = "0"
            env["G_MESSAGES_DEBUG"] = ""
            
        return env

    @staticmethod
    def run(cmd, env, wait=True, check=True, suppress_codes=None, cwd=None, log_callback=None, detached=True):
        """
        Executes a command with automatic verbosity management.
        
        Args:
            cmd (list): Command to run.
            env (dict): Base environment.
            wait (bool): If True, blocks until finished. If False, returns Popen object.
            check (bool): If True and wait is True, raises error on non-zero exit.
            suppress_codes (list): List of exit codes to treat as success
            cwd: Sets the current directory before the child is executed (useful for some VNs)
            log_callback: Callback to store the log in gamerunner.
            detached: hopefully this helps
        """
        if suppress_codes is None:
            suppress_codes = []

        # if env.get("LD_LIBRARY_PATH") and "/tmp/.mount_" in env["LD_LIBRARY_PATH"]:
        #     logger.debug("Cleaning leaked AppImage path from LD_LIBRARY_PATH")
        #     env.pop("LD_LIBRARY_PATH", None)

        # Apply automatic verbosity overrides
        final_env = ExecutionManager._get_verbosity_env(env)

        logger.info(f"Executing: {' '.join(cmd)}")
        logger.debug(f"running in cwd {cwd}")

        # Start Process
        # We merge stderr into stdout for cleaner unified logging
        proc = subprocess.Popen(
            cmd,
            env=final_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=cwd,
            encoding='utf-8',
            errors='replace',
            start_new_session=detached
        )

        # Handle Logging (Threaded to prevent pipe clogs)
        def log_reader(pipe):
            try:
                for line in pipe:
                    clean_line = line.strip()
                    logging.info(clean_line)
                    if log_callback:
                        log_callback(clean_line)
            except Exception as e:
                logger.error(f"Log Thread Error: {e}")
            finally:
                pipe.close()

        logger_thread = threading.Thread(target=log_reader, args=(proc.stdout,), daemon=True)
        logger_thread.start()

        # Return or Wait
        if not wait:
            return proc # Returns the handle for GameRunner to track

        proc.wait()

        if check and proc.returncode != 0 and proc.returncode not in suppress_codes:
            raise subprocess.CalledProcessError(proc.returncode, cmd)

        return proc.returncode