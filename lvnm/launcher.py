import ctypes
import ctypes.util
from prefix_manager import PrefixManager
from runner_manager_kron4ek import RunnerManagerKron4ek
from runner_manager_protonge import RunnerManagerProtonGE

def main():
    set_process_name("launcher")

    make_prefix = PrefixManager("pruebaWine", "wmp11 quartz2", "/home/uni/.local/share/lutris/runners/wine/wine-11.0-amd64-wow64")
    make_prefix = PrefixManager("pruebaProton", "wmp11 quartz2", "/home/uni/.local/share/lutris/runners/proton/GE-Proton10-25/")

    runnerManager = RunnerManagerKron4ek()
    releases = runnerManager.get_runner_all_releases(4, 3)
    test_release = releases[0]
    print(test_release)
    runnerManager.get_release_info(test_release)
    runnerManager.get_runner_download(test_release, "wow64")

    runnerProtonManager = RunnerManagerProtonGE()
    releases = runnerProtonManager.get_runner_all_releases(4, 3)
    test_release = releases[0]
    print(test_release)
    runnerProtonManager.get_release_info(test_release)
    runnerProtonManager.get_runner_download(test_release)
    

def set_process_name(name):
    libc = ctypes.CDLL(ctypes.util.find_library('c'))
    byte_name = name.encode('utf-8')[:15]
    libc.prctl(15, byte_name, 0, 0, 0)

if __name__ == "__main__":
    main()