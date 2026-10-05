"""Central operating-system capabilities used by the UI and backends."""
import os
import sys
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

class Feature(Enum):
    ADVANCED_SETTINGS = auto()
    PREFIXES = auto()
    RUNNERS = auto()
    WINE_CONFIGURATION = auto()
    REGISTRY_MANAGEMENT = auto()
    NETWORK_ISOLATION = auto()
    GAMESCOPE = auto()
    RT_UPSCALER = auto()
    STEAM_SHORTCUTS = auto()
    DESKTOP_SHORTCUTS = auto()
    TIMETRACKING = auto()
    SAVEDATA = auto()
    GDRIVE = auto()

@dataclass(frozen=True)
class PlatformProfile:
    name: str
    features: frozenset[Feature]

    def supports(self, feature: Feature) -> bool:
        return feature in self.features

IS_WINDOWS = sys.platform == "win32"

_COMMON_FEATURES = frozenset({
    Feature.ADVANCED_SETTINGS,
    Feature.DESKTOP_SHORTCUTS,
    Feature.TIMETRACKING,
    Feature.SAVEDATA,
    Feature.GDRIVE,
})

WINDOWS_PROFILE = PlatformProfile("windows", _COMMON_FEATURES)
LINUX_PROFILE = PlatformProfile("linux", _COMMON_FEATURES | frozenset({
    Feature.PREFIXES,
    Feature.RUNNERS,
    Feature.WINE_CONFIGURATION,
    Feature.REGISTRY_MANAGEMENT,
    Feature.NETWORK_ISOLATION,
    Feature.GAMESCOPE,
    Feature.RT_UPSCALER,
    Feature.STEAM_SHORTCUTS,
}))

CURRENT_PLATFORM = WINDOWS_PROFILE if IS_WINDOWS else LINUX_PROFILE

def get_data_dir() -> Path:
    """Return a stable writable data location without changing Linux installs."""
    if IS_WINDOWS:
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return root / "LVNM"
    return Path.home() / ".local" / "share" / "lvnm"
