import ctypes
import ctypes.util
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTranslator, QLocale
from ui.main_window import MainWindow

# Remove later:
import time
from prefix_manager import PrefixManager
from runner_manager_kron4ek import RunnerManagerKron4ek
from runner_manager_protonge import RunnerManagerProtonGE
from game_manager import GameManager
from game_runner import GameRunner
from system_utils import SystemUtils


def main():
    sys_data = SystemUtils.get_system_info()
    software = SystemUtils.get_software_support()
    print(sys_data)
    print(software)

    # istoria_session = GameRunner("Carnival")

    # if istoria_session.run():
    #     print("Launching...")
        
    #     # Keep program alive to keep game alive
    #     try:
    #         while istoria_session.is_running():
    #             print("game running...")
    #             time.sleep(1) # Wait and keep checking
    #     except KeyboardInterrupt:
    #         print("\nShutting down...")
    #         istoria_session.stop()
    #     print(f"Game exited with code: {istoria_session.process.returncode}")
    

    app = QApplication(sys.argv)
    
    # TODO
    translator = QTranslator()
    if translator.load(QLocale.system(), "lvnm", "_", "locale"):
        app.installTranslator(translator)

    set_process_name("launcher")

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