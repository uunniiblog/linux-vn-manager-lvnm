import os
from pathlib import Path

VERSION = 'v0.0.1'
GIT_URL = ''
LOG_LEVEL = "debug"

# Paths
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = Path.home() / ".local" / "share" / "lvnm" 
WINE_RUNNERS_DIR = DATA_DIR / "runners" / "wine"
PROTON_RUNNERS_DIR = DATA_DIR / "runners" / "proton"
PREFIXES_DIR = DATA_DIR / "prefixes"

# Files
CODEC_SCRIPT = BASE_DIR / "vn_winestuff" / "codec.sh"
PREFIXES_DATA = DATA_DIR / ".prefixes.json"
GAMES_DATA = DATA_DIR / ".games.json"
UI_SETTINGS = DATA_DIR / ".ui.config"
USER_SETTINGS = DATA_DIR / ".userconf.json"

# URLS
KRON4EK_API_URL = "https://api.github.com/repos/Kron4ek/Wine-Builds/releases"
PROTONGE_API_URL = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases"

# Codec List
CODEC_LIST = [
    {"id": "wmp11", "name": ""},
    {"id": "quartz2", "name": ""},
    {"id": "mf", "name": ""},
    {"id": "quartz_dx", "name": ""},
    {"id": "mciqtz32", "name": ""},
    {"id": "xaudio29", "name": ""},
    {"id": "dgvoodoo2", "name": ""}
]

# Env Variable list
ENV_VARIABLES = [
    {
        "id": "jp_locale",
        "name": "Japanese Locale (JP)",
        "key": "LANG",
        "value": "ja_JP.UTF-8"
    },
    {
        "id": "jp_timezone",
        "name": "Tokyo Timezone",
        "key": "TZ",
        "value": "Asia/Tokyo"
    },
    {
        "id": "disable_umu_update",
        "name": "Disable umu runtime update",
        "key": "UMU_RUNTIME_UPDATE",
        "value": "0",
        "req": "proton"
    },
    {
        "id": "enable_proton_gst",
        "name": "Old proton-ge gstreamer implementation",
        "key": "PROTON_MEDIA_USE_GST",
        "value": "1",
        "req": "proton"
    },
    {
        "id": "winepulse_fast_polling",
        "name": "Winepulse Fast Polling (Reduce Crackling). Req proton-ge 10.30+",
        "key": "WINEPULSE_FAST_POLLING",
        "value": "1",
        "req": "proton"
    },
    {
        "id": "pulse_latency_msec",
        "name": "Winepulse Latency (Reduce Crackling)+",
        "key": "PULSE_LATENCY_MSEC",
        "value": "120"
    },
    {
        "id": "proton_use_wined3d",
        "name": "Enable WINED3D",
        "key": "PROTON_USE_WINED3D",
        "value": "1",
        "req": "proton"
    },
    {
        "id": "enable_wayland",
        "name": "Enables the Wayland driver",
        "key": "PROTON_ENABLE_WAYLAND",
        "value": "1",
        "req": "proton"
    }
]

# Winetricks
WINETRICKS_LIST = [
    {"id": "vcrun2012", "name": "Visual C++ 2012"},
    {"id": "vcrun2022", "name": "Visual C++ 2015-2022"},
    {"id": "wmp9", "name": "Windows Media Player 9"},
    {"id": "d3dx9", "name": "DirectX 9"}
]


# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
WINE_RUNNERS_DIR.mkdir(parents=True, exist_ok=True)
PROTON_RUNNERS_DIR.mkdir(parents=True, exist_ok=True)
PREFIXES_DIR.mkdir(parents=True, exist_ok=True)
