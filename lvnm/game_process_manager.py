import logging
import config
from datetime import datetime
from PySide6.QtCore import QObject, Signal, QTimer
from game_manager import GameManager
from game_runner import GameRunner
from timetracker.tracking_controller import TrackingController

logger = logging.getLogger(__name__)

class GameProcessManager(QObject):
    """ Manager handling all active game processes and time trackers """
    
    _instance = None
    
    # Signals to communicate with the UI
    game_started = Signal(str)
    game_stopped = Signal(str)
    tracking_updated = Signal(str, dict)

    @classmethod
    def get_instance(cls):
        # Singleton class
        if cls._instance is None:
            cls._instance = GameProcessManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.active_runners = {}
        self.runners_logs = {}
        self.active_trackers = {}

        # Polling loop to check if games were closed
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self._check_active_runners)
        self.monitor_timer.start(1000)

    def is_game_running(self, name: str) -> bool:
        """Check if game is currently running"""
        return name in self.active_runners

    def start_game(self, name: str, timetracker_settings: dict) -> bool:
        """Initializes the runner and starts the process."""
        if name in self.active_runners:
            logger.info(f"{name} is already running. Ignoring launch request.")
            raise RuntimeError("Game is already running.")

        try:
            game_card = GameManager.get_game(name)
            runner = GameRunner(name)
            if runner.run():
                self.active_runners[name] = runner
                logger.debug(f"Started {name}. Total running: {len(self.active_runners)}")

                # Initialize Time tracking if enabled
                if timetracker_settings.get("timetracking", False) and timetracker_settings.get(config.USER_CONF_TIMETRACKER_AUTOSTART, False):
                    self.start_timetracker(name, game_card.path, timetracker_settings)

                # Notify the UI
                self.game_started.emit(name)
                return True
        except Exception as e:
            logger.error(f"Failed to start {name}: {e}")
            raise RuntimeError(f"Could not start {name}: {str(e)}")
            
        raise RuntimeError("The game runner failed to execute.")

    def stop_game(self, name: str):
        runner = self.active_runners.get(name)
        if runner:
            # Calculate how many games are running in the exact same prefix
            target_prefix_path = runner.prefix_info.get("path")
            prefix_count = sum(
                1 for r in self.active_runners.values() 
                if r.prefix_info.get("path") == target_prefix_path
            )
            runner.stop(prefix_count)

    def start_timetracker(self, name: str, exe_path: str, timetracker_settings: dict) -> TrackingController:
        """Creates a tracker manually if one doesn't exist."""
        if name in self.active_trackers:
            return self.active_trackers[name]
            
        save_interval = timetracker_settings.get(config.USER_CONF_TIMETRACKER_PERIODIC_SAVE, 0)
        afk_timer = timetracker_settings.get(config.USER_CONF_TIMETRACKER_AFK_TIMER, 0)
        
        tracking = TrackingController(None, exe_path, save_interval=save_interval, afk_timer=afk_timer)
        
        # Route tracking stats to signal
        tracking.stats_received.connect(lambda stats, n=name: self.tracking_updated.emit(n, stats))
        
        # Start tracking if autostart
        if timetracker_settings.get(config.USER_CONF_TIMETRACKER_AUTOSTART, False):
            tracking.start_auto_tracking()
            
        self.active_trackers[name] = tracking
        return tracking

    def get_tracker(self, name: str):
        return self.active_trackers.get(name)

    def start_manual_tracking(self, name: str, wid, title):
        tracker = self.active_trackers.get(name)
        if tracker:
            tracker.stop_tracking()
            tracker.start_manual_tracking(wid, title)

    def stop_tracking(self, name: str):
        tracker = self.active_trackers.get(name)
        if tracker:
            logger.debug(f"Stopping background tracking for {name}")
            tracker.stop_tracking()
            self.active_trackers.pop(name, None)

    def _check_active_runners(self):
        """Polls ALL active runners. Cleans up those that finished."""
        finished_games = []
        for name, runner in self.active_runners.items():
            # logger.debug(f"check_active_runners {name}")
            if not runner.is_running():
                finished_games.append(name)

        for name in finished_games:
            logging.debug(f"[Game {name} exited. Cleaning up...]")
            
            runner = self.active_runners.pop(name, None)
            if runner:
                self.runners_logs[name] = runner.get_full_log()
                runner.logs.clear()
                if runner.game.exit_script.strip():
                    runner.run_external_script(runner.game.exit_script.strip())

            self.stop_tracking(name)

            game_to_update = GameManager.get_game(name) 
            if game_to_update:
                game_to_update.last_played = datetime.today().strftime('%Y-%m-%d %H:%M:%S')      
                GameManager.update_game(name, game_to_update.to_dict())
            
            # Notify UI
            self.game_stopped.emit(name)