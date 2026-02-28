import sys
import time
import signal
from datetime import datetime
from PySide6.QtCore import QObject, QTimer
from game_runner import GameRunner
from game_manager import GameManager
import logging

logger = logging.getLogger(__name__)

class CliController(QObject):
    def __init__(self):
        super().__init__()
    
    def handle_args(self, args):
        if args.run:
            self.headless_run(args.run, args.steam)
            return

    def headless_run(self, game, is_steam=False):
        runner = GameRunner(game, is_steam=is_steam)
        runner.load_data()
        
        if not runner.is_running():

            def cleanup_and_exit(signum, frame):
                runner.stop()
                self.update_game(game)
                sys.exit(0)

            logger.info(f"Launching {game} headless mode...")
            signal.signal(signal.SIGINT, cleanup_and_exit)  # Ctrl+C
            signal.signal(signal.SIGTERM, cleanup_and_exit) # Standard kill / app close

            runner.run(is_headless=True)
            
            while runner.is_running():
                time.sleep(1)
            
            # Just in case something is still running in the background
            runner.stop()
            self.update_game(game)
            logger.info(f"{game} exited with code {runner.process.returncode}")
        else:
            logger.info(f"{game} is already running")

        sys.exit(0)

    def update_game(self, game):
        game_to_update = GameManager.get_game(game) 
        if game_to_update:
            game_to_update.last_played = datetime.today().strftime('%Y-%m-%d %H:%M:%S')                
            GameManager.update_game(game, game_to_update.to_dict())
