import logging
import sys
import time
import signal
import config
from datetime import datetime
from PySide6.QtCore import QObject, QCoreApplication, QTimer, QEventLoop
from launchers.launcher_factory import create_launcher
from game_manager import GameManager
from settings_manager import SettingsManager
from timetracker.tracking_controller import TrackingController
from savedata_manager import SavedataManager
from timetracker.log_manager import LogManager
from pregame_sync_pipeline import PreLaunchSyncPipeline, SavedataSyncStep, TrackingSyncStep
from ui.savedata_conflict_prompt import prompt_savedata_conflict

logger = logging.getLogger(__name__)

class CliController(QObject):
    def __init__(self):
        super().__init__()
        self.user_settings = SettingsManager()
        self.timetracker_settings = self.user_settings.get(config.USER_CONF_TIMETRACKER, {})
        self.savedata_settings = self.user_settings.get(config.USER_CONF_SAVEDATA, {})
        self.tracking = None
        self._is_exiting = False
    
    def handle_args(self, args):
        if args.run:
            self.headless_run(args.run, args.steam)
            
        elif args.timetrack:
            self.headless_timetracker(args.timetrack)
        
        logging.shutdown()
        sys.exit(0)

    def headless_run(self, game, is_steam=False):
        runner = create_launcher(game, is_steam=is_steam)
        runner.load_data()
        
        if not runner.is_running():
            game_card = GameManager.get_game(game)
            tracking_enabled = self.timetracker_settings.get("timetracking", False)
            if not self._sync_before_launch(game, game_card, "pre-launch", tracking_enabled=tracking_enabled):
                logger.info(f"Launch of '{game}' cancelled during pre-launch sync.")
                return

            app = QCoreApplication.instance() or QCoreApplication(sys.argv)

            def kill_handler(signum, frame):
                logger.info(f"Received Signal {signum}. Forcing shutdown!")
                if self._is_exiting:
                    logger.info("Cleanup/Sync already in progress. Deferring termination to let cloud sync complete.")
                    return
                
                self._is_exiting = True
                self.cleanup_exit(game, runner)
                sys.exit(0)

            logger.info(f"Launching {game} headless mode...")
            signal.signal(signal.SIGINT, kill_handler)  # Ctrl+C
            signal.signal(signal.SIGTERM, kill_handler) # Standard kill / app close

            runner.run(is_headless=True)

            # Start tracking
            if tracking_enabled:
                save_interval = self.timetracker_settings.get(config.USER_CONF_TIMETRACKER_PERIODIC_SAVE, 0)
                afk_timer = self.timetracker_settings.get(config.USER_CONF_TIMETRACKER_AFK_TIMER, 0)
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

            # Normal termination path (if the game was closed cleanly via in-game menus)
            if not self._is_exiting:
                self._is_exiting = True
                self.cleanup_exit(game, runner)

            logger.info(f"{game} exited with code {runner.process.returncode}")
        else:
            logger.info(f"{game} is already running")

    def update_game(self, game):
        game_to_update = GameManager.get_game(game)
        if game_to_update:
            SavedataManager.try_auto_detect_savedata(game, game_to_update)
            game_to_update.last_played = datetime.today().strftime('%Y-%m-%d %H:%M:%S')                
            GameManager.update_game(game, game_to_update.to_dict())
            self._sync_after_exit(game, game_to_update)

    def cleanup_exit(self, game, runner):
        logger.info(f"Closing {game}...")
        
        # Stop tracking if active
        if hasattr(self, 'tracking') and self.tracking:
            self.tracking.stop_tracking()
        
        runner.stop()
        self.update_game(game)

        if runner.game.exit_script.strip():
            runner.run_external_script(runner.game.exit_script.strip())
            
    def headless_timetracker(self, game_name):
        logger.info(f"headless_timetracker for {game_name}")
        game_card = GameManager.get_game(game_name)
        
        if not game_card:
            logger.error(f"{game_name} Not found. It must be added to the application first.")
            return

        tracking_enabled = self.timetracker_settings.get("timetracking", False)
        if not self._sync_before_launch(game_name, game_card, "pre-tracking", tracking_enabled=tracking_enabled):
            logger.info(f"Launch of '{game_name}' cancelled during pre-launch sync.")
            return

        runner = create_launcher(game_name, card_override=game_card)
        runner.game = game_card

        def kill_handler(signum, frame):
            logger.info(f"Received Signal {signum}. Forcing shutdown!")
            if self._is_exiting:
                logger.info("Cleanup/Sync already in progress. Deferring termination to let cloud sync complete.")
                return

            self._is_exiting = True
            if self.tracking:
                self.tracking.stop_tracking()
                
            self.update_game(game_name)
            sys.exit(0)

        app = QCoreApplication.instance() or QCoreApplication(sys.argv)
        signal.signal(signal.SIGINT, kill_handler)  # Ctrl+C
        signal.signal(signal.SIGTERM, kill_handler) # Standard kill / app close


        logger.debug(f"{game_name} found. Starting tracking")

        # Start tracking, 
        # Save automatically every minute unless specified otherwise in the application
        save_interval = self.timetracker_settings.get(config.USER_CONF_TIMETRACKER_PERIODIC_SAVE, 1)
        afk_timer = self.timetracker_settings.get(config.USER_CONF_TIMETRACKER_AFK_TIMER, 0)
        logger.debug(f"calling tracking controller with process {game_card.path}")
        self.tracking = TrackingController(self, game_card.path, save_interval=save_interval, afk_timer=afk_timer)
        self.tracking.start_auto_tracking()

        self.game_has_started = False
        self.timeout_counter = 0

        def check_game_status():
            is_running = runner.is_running()
            if is_running:
                if not self.game_has_started:
                    logger.info(f"Game process '{game_card.path}' detected! Tracking initialized.")
                    self.game_has_started = True
            else:
                if self.game_has_started:
                    logger.info("Game exited, stopping event loop.")
                    app.quit()
                else:
                    # The game hasn't started yet. give it 45 seconds
                    self.timeout_counter += 1
                    if self.timeout_counter > 45:
                        logger.error(f"Timed out waiting for '{game_card.path}' to launch. Exiting.")
                        app.quit()


        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(check_game_status)
        self.monitor_timer.start(1000)

        app.exec()

        # Normal termination path
        if not self._is_exiting:
            self._is_exiting = True
            self.tracking.stop_tracking()
            self.update_game(game_name)

    def _sync_savedata_to_cloud(self, game: str, game_data: dict):
        logger.info(f"Syncing save data with Google Drive for '{game}'...")
        try:
            SavedataManager.sync_savedata_to_gdrive(game_data)
            logger.info(f"Google Drive save sync completed successfully for '{game}'.")
        except Exception as e:
            logger.error(f"Google Drive save sync failed for '{game}': {e}. Proceeding with local saves.", exc_info=True)

    def _sync_tracking_to_cloud(self, game: str, path: str):
        if not self.tracking_file:
            return
        logger.info(f"Syncing time tracking data with Google Drive for '{game}'")
        try:
            LogManager().sync_tracking_to_gdrive(path)
            logger.info(f"Google Drive tracking sync completed successfully for '{game}'")
        except Exception as e:
            logger.error(f"Google Drive tracking sync failed for '{game}': {e}. Proceeding with local tracking data.", exc_info=True)

    def _sync_before_launch(self, game: str, game_card, phase: str, tracking_enabled: bool = True):
        """Pre launch sync."""
        if not (game_card.gdrive and self.savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False)):
            return True

        self._sync_savedata_to_cloud(game, game_card.to_dict())
        steps = [SavedataSyncStep(
            game, game_card.to_dict(), f"Syncing save data with Google Drive...",
            conflict_prompt=lambda conflicts: prompt_savedata_conflict(None, game, conflicts)
        )]

        if tracking_enabled and self.timetracker_settings.get(config.USER_CONF_TIMETRACKER_GDRIVE_SYNC, False):
            self.tracking_file = LogManager().get_log_name_from_path(game_card)
            steps.append(TrackingSyncStep(game_card.path, f"Syncing time tracking data..."))

        return self._run_sync_pipeline_blocking(steps)

    def _sync_after_exit(self, game: str, game_card):
        """Post-game sync."""
        if not (game_card.gdrive and self.savedata_settings.get(config.USER_CONF_SAVEDATA_ENABLED, False)):
            return

        self._sync_savedata_to_cloud(game, game_card.to_dict())

        if self.tracking and self.timetracker_settings.get(config.USER_CONF_TIMETRACKER_GDRIVE_SYNC, False):
            self._sync_tracking_to_cloud(game, game_card.path)

    def _run_sync_pipeline_blocking(self, steps) -> bool:
        """
        Runs a PreLaunchSyncPipeline and blocks via a nested Qt event loop
        until it finishes, so the game doesn't launch until sync (and any
        conflict prompt) has fully resolved
        """
        if not steps:
            return True
        loop = QEventLoop()
        outcome = {"proceed": True}

        def on_finished(proceed):
            outcome["proceed"] = proceed
            loop.quit()

        pipeline = PreLaunchSyncPipeline(None, steps)
        pipeline.finished.connect(on_finished)
        pipeline.start()
        loop.exec()
        return outcome["proceed"]