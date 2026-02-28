import argparse
import config

class CliHandler:
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            description="",
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        self._setup_args()

    def _setup_args(self):      
        # Version flag
        self.parser.add_argument(
            "-v", "--version", 
            action="version", 
            version=f"lvnm {config.VERSION}",
            help="Show the application version and exit."
        )

        # Headless running
        self.parser.add_argument(
            "-r", "--run",
            metavar="gamename",
            help="The name of the game to launch in background mode."
        )

        # Steam mode flag
        self.parser.add_argument(
            "--steam",
            action="store_true",
            help="Apply Steam-specific environment scrubbing (fixes Japanese paths and overlay issues)."
        )

    def parse(self):
        return self.parser.parse_args()