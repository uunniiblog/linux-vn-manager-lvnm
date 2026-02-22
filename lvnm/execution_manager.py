import sys
import subprocess
import threading
import config

class ExecutionManager:
    @staticmethod
    def _get_verbosity_env(base_env: dict) -> dict:
        """Augments environment variables based on config.LOG_LEVEL."""
        env = base_env.copy()
        level = getattr(config, "LOG_LEVEL", "info").lower()

        if level == "debug":
            # Show everything
            env["UMU_LOG"] = "1"
            # everything else default should be good ? TODO
        
        elif level == "info":
            # Show only errors and major fixmes
            if "WINEDEBUG" not in env:
                env["WINEDEBUG"] = "-all,err+all"
            env["UMU_LOG"] = "0"
            env["STEAM_LINUX_RUNTIME_VERBOSE"] = "0"
            
        elif level == "none":
            # Reduce logging as much as possible
            env["WINEDEBUG"] = "-all"
            env["UMU_LOG"] = "0"
            env["STEAM_LINUX_RUNTIME_VERBOSE"] = "0"
            env["PRESSURE_VESSEL_VERBOSE"] = "0"
            env["G_MESSAGES_DEBUG"] = ""
            
        return env

    @staticmethod
    def run(cmd, env, wait=True, check=True, suppress_codes=None, cwd=None):
        """
        Executes a command with automatic verbosity management.
        
        Args:
            cmd (list): Command to run.
            env (dict): Base environment.
            wait (bool): If True, blocks until finished. If False, returns Popen object.
            check (bool): If True and wait is True, raises error on non-zero exit.
            suppress_codes (list): List of exit codes to treat as success
            cwd: Sets the current directory before the child is executed (useful for some VNs)
        """
        if suppress_codes is None:
            suppress_codes = []

        # Apply automatic verbosity overrides
        final_env = ExecutionManager._get_verbosity_env(env)

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
            cwd=cwd
        )

        # Handle Logging (Threaded to prevent pipe clogs)
        def log_reader(pipe):
            try:
                for line in pipe:
                    # Even with env variables, we keep sys.stdout.write 
                    # so the output appears in our terminal
                    sys.stdout.write(line)
                    sys.stdout.flush()
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