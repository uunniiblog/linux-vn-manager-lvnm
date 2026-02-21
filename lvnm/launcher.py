import ctypes
import ctypes.util
import time
from prefix_manager import PrefixManager
from runner_manager_kron4ek import RunnerManagerKron4ek
from runner_manager_protonge import RunnerManagerProtonGE
from game_manager import GameManager
from game_runner import GameRunner


def main():
    set_process_name("launcher")

    # GameManager.add_game("/media/pepega/STRED4TB/VNs/水葬銀貨のイストリア/install/水葬銀貨のイストリア/水葬銀貨のイストリア.exe", "Istoria", "wine10.20-wow64-prueba2", "v20471")
    # GameManager.update_game("Istoria", {
    #     "envvar": {"LANG": "ja_JP.UTF-8", "TZ": "Asia/Tokyo"}
    # })

    # prefix = PrefixManager("wine10.20-wow64-prueba")
    # prefix.rename_prefix("wine10.20-wow64")

    prefix = PrefixManager("wineamd64")
    prefix.delete_prefix()
    prefix.create_prefix(
        runner_path="/home/uni/.local/share/lvnm/runners/wine/wine-10.17-amd64", 
        codecs="wmp11 quartz2"
    )

    # # prefix.delete_prefix()
    # GameManager.update_game("Istoria", {
    #     "vndb": "v12345",
    #     "envvar": {"LANG": "ja_JP.UTF-8", "TZ": "Asia/Tokyo"},
    #     "prefix": "pruebaWine"
    # })

    istoria_session = GameRunner("Istoria")

    if istoria_session.run():
        print("Launching...")
        
        # Keep program alive to keep game alive
        try:
            while istoria_session.is_running():
                print("game running...")
                time.sleep(1) # Wait and keep checking
        except KeyboardInterrupt:
            print("\nShutting down...")
            istoria_session.stop()
        
        # After the game closes, check the exit code
        print(f"Game exited with code: {istoria_session.process.returncode}")

    # make_prefix = PrefixManager("Nitroplusnew", "", "/home/uni/.local/share/lvnm/runners/proton/GE-Proton10-24")

    # runnerManager = RunnerManagerKron4ek()
    # releases = runnerManager.get_runner_all_releases(4, 3)
    # test_release = releases[0]
    # print(test_release)
    # runnerManager.get_release_info(test_release)
    # runnerManager.get_runner_download(test_release, "wow64")

    # runnerProtonManager = RunnerManagerProtonGE()
    # releases = runnerProtonManager.get_runner_all_releases(4, 3)
    # test_release = releases[0]
    # print(test_release)
    # runnerProtonManager.get_release_info(test_release)
    # runnerProtonManager.get_runner_download(test_release)

    
    # GameManager.add_game("/media/pepega/STRED4TB/VNs/水葬銀貨のイストリア/install/水葬銀貨のイストリア/水葬銀貨のイストリア.exe", "Istoria", "pruebaWine", "v20471")
    # GameManager.add_game("/media/pepega/WD4TB/VNsDownloaded/Kishin Houkou Demonbane PC (2019)/Demonbane.exe", "Demonbane", "pruebaProton", "v231")
    # gamelist = GameManager.list_games("Demon")
    # GameManager.delete_game("Demonbane")
    # games = GameManager.list_games()
    # print(games)

    # GameManager.update_game("Istoria", {"gamescope": {"enabled": "true"}})

    # gamelist = GameManager.list_games()
    # print(gamelist)
    # # GameManager.delete_game("Demonbane")
    # # GameManager.delete_game("Istoria")
    # gamelist = GameManager.list_games()
    # print(gamelist)

def set_process_name(name):
    libc = ctypes.CDLL(ctypes.util.find_library('c'))
    byte_name = name.encode('utf-8')[:15]
    libc.prctl(15, byte_name, 0, 0, 0)

if __name__ == "__main__":
    main()