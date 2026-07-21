import sys
import os
import signal
import logging
import setproctitle
import ssl
import certifi
from logging_manager import setup_logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTranslator, QLocale
import config
from ui.main_window import MainWindow
from system_utils import SystemUtils
from cli_handler import CliHandler
from cli_controller import CliController
from settings_manager import SettingsManager


def install_translator(app, settings):
    language = settings.get(config.USER_CONF_LANGUAGE, "")
    locale = QLocale(language) if language else QLocale.system()

    translator = QTranslator(app)
    if translator.load(locale, "lvnm", "_", str(config.LOCALE_DIR)):
        app.installTranslator(translator)
        return translator
    return None

def main():
    setproctitle.setproctitle("linux-vn-manager-lvnm")
    settings = SettingsManager()

    if SystemUtils.get_runtime_type() == "appimage":
        # Force system CA bundle instead of PyInstaller's bundled one
        cert_path = certifi.where()
        os.environ['SSL_CERT_FILE'] = cert_path
        os.environ['REQUESTS_CA_BUNDLE'] = cert_path
    
    # QFileDialog native system integration
    os.environ["QT_QPA_PLATFORMTHEME"] = "xdgdesktopportal"

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

    translator = install_translator(app, settings)

    # Load UI size
    zoom = settings.get("ui_zoom", 1.0) # Default to 1.0
    SystemUtils.apply_ui_zoom(zoom)

    logger = logging.getLogger(__name__)
    logger.debug(sys.argv)

    # Launch UI
    if len(sys.argv) == 1:
        SystemUtils.print_diagnostic_report()
        window = MainWindow()
        window.show()
    else:
        controller = CliController()
        controller.handle_args(args)
    
    exit_code = app.exec()
    logging.shutdown()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()