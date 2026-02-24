import ctypes
import ctypes.util
import sys
import os
import signal
import logging
from logging_manager import setup_logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTranslator, QLocale
from ui.main_window import MainWindow
from system_utils import SystemUtils

def main():
    set_process_name("linux-vn-manager-lvnm")
    settings = SystemUtils.load_settings()

    # Close with ctrl c in terminal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    log_level = settings.get("log_level", "info")
    setup_logging(log_level)
    
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
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

def set_process_name(name):
    libc = ctypes.CDLL(ctypes.util.find_library('c'))
    byte_name = name.encode('utf-8')[:15]
    libc.prctl(15, byte_name, 0, 0, 0)

if __name__ == "__main__":
    main()