import sys
import subprocess

class ProcessLogger:
    # Filter lines not wanted to be logged
    DEFAULT_FILTERS = [
        # "INFO: umu-launcher",
        # "INFO: steamrt3",
        # "ProtonFixes",
        # "WARNING: Executable not found: winecfg",
        # "Proton: Executable is inside wine prefix",
        # "wineserver: using server-side synchronization.",
        # "wine: using kernel-base synchronization."
    ]

    @staticmethod
    def run(cmd, env, check=True, suppress_codes=None):
        """
        Executes a command, filtering stderr against spam filters.
        
        Args:
            cmd (list): The command to execute.
            env (dict): Environment variables.
            check (bool): Whether to raise CalledProcessError on failure.
            suppress_codes (list): List of exit codes to treat as success (e.g., [1]).
        """
        if suppress_codes is None:
            suppress_codes = []

        # stdout=None inherits the parent's stdout (prints directly to console)
        # stderr=subprocess.PIPE captures error stream for filtering
        with subprocess.Popen(cmd, env=env, stdout=None, stderr=subprocess.PIPE, text=True) as proc:
            
            # Read stderr line by line in real-time
            for line in proc.stderr:
                if not any(spam in line for spam in ProcessLogger.DEFAULT_FILTERS):
                    sys.stderr.write(line)
            
            proc.wait()

            # Handle exit codes
            if proc.returncode != 0:
                if proc.returncode in suppress_codes:
                    return
                
                if check:
                    raise subprocess.CalledProcessError(proc.returncode, cmd)
                    
            print(f"proc.returncode {proc.returncode}")
            return proc.returncode