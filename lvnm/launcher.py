import sys
import os
import signal
import logging
import setproctitle
from logging_manager import setup_logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTranslator, QLocale
from ui.main_window import MainWindow
from system_utils import SystemUtils
from cli_handler import CliHandler
from cli_controller import CliController
from settings_manager import SettingsManager

def main():
    setproctitle.setproctitle("linux-vn-manager-lvnm")
    settings = SettingsManager()

    # Close with ctrl c in terminal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Log
    log_level = settings.get("log_level", "info")
    setup_logging(log_level)

    # Cli
    cli = CliHandler()
    args = cli.parse()

    # Scale with system scale (?)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    
    # TODO
    translator = QTranslator()
    if translator.load(QLocale.system(), "lvnm", "_", "locale"):
        app.installTranslator(translator)

    # Load UI size
    zoom = settings.get("ui_zoom", 1.0) # Default to 1.0
    SystemUtils.apply_ui_zoom(zoom)

    # Launch UI
    if not args.run:
        logger = logging.getLogger(__name__)
        logger.debug(SystemUtils.print_diagnostic_report())
        window = MainWindow()
        window.show()
    else:
        controller = CliController()
        controller.handle_args(args)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()