import os
from pathlib import Path

VERSION = 'v0.0.1'
GIT_URL = ''

# Paths
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = Path.home() / ".local" / "share" / "lvnm" 
WINE_RUNNERS_DIR = DATA_DIR / "runners" / "wine"
PROTON_RUNNERS_DIR = DATA_DIR / "runners" / "proton"
DXVK_DIR = DATA_DIR / "runners" / "dxvk"
PREFIXES_DIR = DATA_DIR / "prefixes"
COVERS_DIR = DATA_DIR / "covers"

# Files
CODEC_SCRIPT = BASE_DIR / "vn_winestuff" / "codec.sh"
PREFIXES_DATA = DATA_DIR / ".prefixes.json"
GAMES_DATA = DATA_DIR / ".games.json"
UI_SETTINGS = DATA_DIR / ".ui.config"
USER_SETTINGS = DATA_DIR / ".userconf.json"

# URLS
KRON4EK_API_URL = "https://api.github.com/repos/Kron4ek/Wine-Builds/releases"
PROTONGE_API_URL = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases"
DXVK_API_URL = "https://api.github.com/repos/doitsujin/dxvk/releases/latest"
VNDB_API_URL = "https://api.vndb.org/kana"
VNDB_SITE_URL = "https://vndb.org/{vndbid}"
EGS_SITE_URL = "https://erogamescape.dyndns.org/~ap2/ero/toukei_kaiseki/kensaku.php?category=game&word_category=name&word={jpname}"

# Codec List
CODEC_LIST = [
    {"id": "wmp11", "name": ""},
    {"id": "quartz2", "name": ""},
    {"id": "mf", "name": ""},
    {"id": "lavfilters", "name": ""},
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
        "id": "Enable DXVK",
        "key": "WINEDLLOVERRIDES",
        "value": "d3d11,d3d10,d3d9,dxgi=n,b",
        "req": "wine"
    },
    {
        "id": "proton_use_wined3d",
        "name": "Proton Use WineD3D (Disable DXVK)",
        "key": "PROTON_USE_WINED3D",
        "value": "1",
        "req": "proton"
    },
    {
        "id": "enable_proton_gst",
        "name": "Old proton-ge Gstreamer implementation",
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
        "name": "Winepulse Latency (Reduce Crackling)",
        "key": "PULSE_LATENCY_MSEC",
        "value": "120"
    },
    # {
    #     "id": "Disable DXVK",
    #     "key": "WINEDLLOVERRIDES",
    #     "value": "d3d11,d3d10,d3d9,dxgi=b",
    #     "req": "wine"
    # },
    {
        "id": "disable_umu_update",
        "name": "Disable UMU runtime update",
        "key": "UMU_RUNTIME_UPDATE",
        "value": "0",
        "req": "proton"
    },
    {
        "id": "enable_wayland",
        "name": "Enables the Wayland driver",
        "key": "PROTON_ENABLE_WAYLAND",
        "value": "1",
        "req": "proton"
    },
    # {
    #     "id": "run_in_prefix",
    #     "name": "Proton Verb Run in prefix (Two games same prefix)",
    #     "key": "PROTON_VERB",
    #     "value": "runinprefix",
    #     "req": "proton"
    # },
    {
        "id": "proton_verb_run",
        "name": "Proton Verb Run (Two games same prefix)",
        "key": "PROTON_VERB",
        "value": "run",
        "req": "proton"
    },
    {
        "id": "pressure_vessel_shell_after",
        "name": "PRESSURE Vessel after (Run Terminal same memory as game)",
        "key": "PRESSURE_VESSEL_SHELL",
        "value": "after",
        "req": "proton"
    },
    {
        "id": "mangohud",
        "name": "Mangohud",
        "key": "MANGOHUD",
        "value": "1",
    },
    {
        "id": "dxvk_hud",
        "name": "DXVK HUD",
        "key": "DXVK_HUD",
        "value": "full",
    },
    {
        "id": "proton_log",
        "name": "Proton Log",
        "key": "PROTON_LOG",
        "value": "1",
        "req": "proton"
    },

]

# Winetricks
WINETRICKS_LIST = [
    {"id": "vcrun2012", "name": "Visual C++ 2012"},
    {"id": "vcrun2022", "name": "Visual C++ 2015-2022"},
    {"id": "cjkfonts", "name": "bunch of fonts"},
    {"id": "amstream", "name": "amstream"},
    {"id": "devenum", "name": "devenum"},
    {"id": "quartz", "name": "quartz"},
    {"id": "xact", "name": "xact"},
    # wmp10 and 9 only work in 32 bit
    # {"id": "wmp10", "name": "Windows Media Player 10"},
    # {"id": "wmp9", "name": "Windows Media Player 9"},
    {"id": "d3dx9", "name": "DirectX 9"},
    {"id": "wsh57", "name": "Windows scripting host (SRPG Studio)"},
]

# User config
GAMESCOPE_INSTALLED = False
VULKAN_INSTALLED = False
UMU_RUN_INSTALLED = False
WINETRICKS_INSTALLED = False

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
WINE_RUNNERS_DIR.mkdir(parents=True, exist_ok=True)
PROTON_RUNNERS_DIR.mkdir(parents=True, exist_ok=True)
PREFIXES_DIR.mkdir(parents=True, exist_ok=True)
COVERS_DIR.mkdir(parents=True, exist_ok=True)
