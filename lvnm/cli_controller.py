import sys
import time
import signal
from datetime import datetime
from PySide6.QtCore import QObject, QCoreApplication, QTimer
from game_runner import GameRunner
from game_manager import GameManager
from settings_manager import SettingsManager
from timetracker.tracking_controller import TrackingController
import logging

logger = logging.getLogger(__name__)

class CliController(QObject):
    def __init__(self):
        self.user_settings = SettingsManager()
        self.timetracker_settings = self.user_settings.get("timetracker", {})
        self.tracking = None
        super().__init__()
    
    def handle_args(self, args):
        if args.run:
            self.headless_run(args.run, args.steam)
            return

    def headless_run(self, game, is_steam=False):
        runner = GameRunner(game, is_steam=is_steam)
        runner.load_data()
        
        if not runner.is_running():

            app = QCoreApplication.instance() or QCoreApplication(sys.argv)

            def cleanup_and_exit(signum, frame):
                runner.stop()
                self.update_game(game)
                sys.exit(0)

            logger.info(f"Launching {game} headless mode...")
            signal.signal(signal.SIGINT, cleanup_and_exit)  # Ctrl+C
            signal.signal(signal.SIGTERM, cleanup_and_exit) # Standard kill / app close

            runner.run(is_headless=True)

            # Start tracking
            if self.timetracker_settings.get("timetracking", False):
                save_interval = self.timetracker_settings.get("log_periodic_save", 0)
                afk_timer = self.timetracker_settings.get("afk_timer", 0)
                logger.debug(f"calling tracking controller with process {runner.game.path}")
                self.tracking = TrackingController(self, runner.game.path, save_interval=save_interval, afk_timer=afk_timer)
                self.tracking.start_auto_tracking()

            self.monitor_timer = QTimer()
            def check_game_status():
                if not runner.is_running():
                    logger.info("Game exited, stopping event loop.")
                    app.quit()

            self.monitor_timer.timeout.connect(check_game_status)
            self.monitor_timer.start(1000)
            
            app.exec()

            # while runner.is_running():
            #     time.sleep(1)
            
            # Just in case something is still running in the background
            runner.stop()
            self.tracking.stop_tracking()
            self.update_game(game)
            logger.info(f"{game} exited with code {runner.process.returncode}")
        else:
            logger.info(f"{game} is already running")

        logging.shutdown()
        sys.exit(0)

    def update_game(self, game):
        game_to_update = GameManager.get_game(game) 
        if game_to_update:
            game_to_update.last_played = datetime.today().strftime('%Y-%m-%d %H:%M:%S')                
            GameManager.update_game(game, game_to_update.to_dict())
