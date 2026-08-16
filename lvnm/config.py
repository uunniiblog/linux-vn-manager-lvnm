from pathlib import Path
import tempfile

VERSION = 'v0.5.2'
GIT_URL = 'https://github.com/uunniiblog/linux-vn-manager-lvnm'

# Paths
BASE_DIR = Path(__file__).parent.resolve()
LOCALE_DIR = BASE_DIR / "locale"
DATA_DIR = Path.home() / ".local" / "share" / "lvnm" 
WINE_RUNNERS_DIR = DATA_DIR / "runners" / "wine"
# PROTON_RUNNERS_DIR = DATA_DIR / "runners" / "proton"
PROTON_RUNNERS_DIR =  Path.home() / ".local" / "share" / "Steam" / "compatibilitytools.d"
DXVK_DIR = DATA_DIR / "runners" / "dxvk"
PREFIXES_DIR = DATA_DIR / "prefixes"
COVERS_DIR = DATA_DIR / "covers"
LOG_DIR = DATA_DIR / "tracking"

# Files
CODEC_SCRIPT = BASE_DIR / "vn_winestuff" / "codec.sh"
PREFIXES_DATA = DATA_DIR / ".prefixes.json"
GAMES_DATA = DATA_DIR / ".games.json"
UI_SETTINGS = DATA_DIR / ".ui.config"
USER_SETTINGS = DATA_DIR / ".userconf.json"
LAST_PLAYED_METADATA = LOG_DIR / ".last_played.json"
AFK_FILE = Path(tempfile.gettempdir()) / "lvnm" / "lvnm_afk_detection_file"
TEMP_COVERS = Path(tempfile.gettempdir()) / "lvnm" / "search"
GSYNC_METADATA = DATA_DIR / ".gsync_metadata.json"

# URLS
LVNM_API_URL = "https://api.github.com/repos/uunniiblog/linux-vn-manager-lvnm/releases"
KRON4EK_API_URL = "https://api.github.com/repos/Kron4ek/Wine-Builds/releases"
PROTONGE_API_URL = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases"
DXVK_API_URL = "https://api.github.com/repos/doitsujin/dxvk/releases/latest"
VNDB_API_URL = "https://api.vndb.org/kana"
SGDB_API_URL = "https://www.steamgriddb.com/api/v2"
STEAM_STORE_API_URL = "https://store.steampowered.com/api/storesearch/"
STEAM_CDN = "https://cdn.akamai.steamstatic.com/steam/apps"
VNDB_SITE_URL = "https://vndb.org/{vndbid}"
EGS_SITE_URL = "https://erogamescape.dyndns.org/~ap2/ero/toukei_kaiseki/kensaku.php?category=game&word_category=name&word={jpname}"
WINEPREFIX_URL = "https://www.vnwiki.xyz/linux/wineprefixes.html"
GDRIVE_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
GDRIVE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GDRIVE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GDRIVE_SCOPES = "https://www.googleapis.com/auth/drive.file"

# Codec List
CODEC_LIST = [
    {"id": "wmp11", "name": ""},
    {"id": "quartz2", "name": ""},
    {"id": "mf", "name": ""},
    {"id": "lavfilters", "name": ""},
    {"id": "quartz_dx", "name": ""},
    {"id": "mciqtz32", "name": ""},
    {"id": "xaudio29", "name": ""}
]

# Env Variable list
ENV_VARIABLES = [
    {
        "id": "jp_locale",
        "name": "Japanese Locale",
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
    {
        "id": "winedebug_level",
        "name": "Winedebug Log level",
        "key": "WINEDEBUG",
        "value": "-all,err+all,fixme+all",
    },
    {
        "id": "run_in_prefix",
        "name": "Proton Verb Run in prefix (Two games same prefix)",
        "key": "PROTON_VERB",
        "value": "runinprefix",
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
    {
        "id": "sdl_video_x11",
        "name": "SDL_VIDEODRIVER X11",
        "key": "SDL_VIDEODRIVER",
        "value": "x11",
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
    {"id": "d3dx9", "name": "DirectX 9"},
    {"id": "wsh57", "name": "Windows scripting host (SRPG Studio)"},
]

# User config variable names
USER_CONF_ENV_VARIABLE_LIST = "env_variables_list"
USER_CONF_GLOBAL_VARIABLES = "global_env_var"
USER_CONF_FONT_FOLDER = "font_folder"
USER_CONF_GAMESCOPE_ENABLED = "gamescope_enabled"
USER_CONF_GAMESCOPE_PARAMS = "gamescope_params"
USER_CONF_RT_UPSCALER_ENABLED = "rt_upscaler_enabled"
USER_CONF_RT_UPSCALER_PARAMS = "rt_upscaler_params"
USER_CONF_SAVE_DATA_FOLDER = "save_folder"
USER_CONF_ONE_GAME_PREFIX = "one_game_one_prefix"
USER_CONF_LOG_LEVEL = "log_level"
USER_CONF_UI_ZOOM = "ui_zoom"
USER_CONF_TIMETRACKER = "timetracker"
USER_CONF_SAVEDATA = "savedata_management"
USER_CONF_TEXTHOOKER = "texthooker"
USER_CONF_SORT_BY_LIST = "list_sort_by"
USER_CONF_TIMETRACKER_PERIODIC_SAVE = "log_periodic_save"
USER_CONF_TIMETRACKER_AFK_TIMER = "afk_timer"
USER_CONF_TIMETRACKER_AUTOSTART = "autostart"
USER_CONF_TIMETRACKER_GDRIVE_SYNC = "sync_tracking"
USER_CONF_SAVED_LABELS = "saved_labels"
USER_CONF_COVERS_PATH = "covers_dir"
USER_CONF_WINE_RUNNERS_PATH = "wine_runners_dir"
USER_CONF_PROTON_RUNNERS_PATH = "proton_runners_dir"
USER_CONF_PREFIXES_PATH = "prefixes_dir"
USER_CONF_LOGS_PATH = "logs_dir"
USER_CONF_SGDB_API_KEY = "sgdb_api_key"
USER_CONF_SAVEDATA_AUTO_DETECT = "auto_detect_save"
USER_CONF_SAVEDATA_ENABLED = "enabled"
USER_CONF_SAVEDATA_GDRIVE_CLIENT_ID = "gdrive_client_id"
USER_CONF_SAVEDATA_GDRIVE_CLIENT_SECRET = "gdrive_client_secret"
USER_CONF_SAVEDATA_GDRIVE_REFRESH_TOKEN = "gdrive_refresh_token"
USER_CONF_SAVEDATA_GDRIVE_ALL_GAMES = "gdrive_all_games"
USER_CONF_LOG_TO_FILE = "log_to_file"
USER_CONF_LOGS_WINE = "log_wine"
USER_CONF_LANGUAGE = "language"
USER_CONF_EMULATION = "emulation_management"
USER_CONF_EMULATION_PSX_PATH = "psx_path"
USER_CONF_EMULATION_PSX_CONFIG = "psx_config"
USER_CONF_EMULATION_PS2_PATH = "ps2_path"
USER_CONF_EMULATION_PS2_CONFIG = "ps2_config"
USER_CONF_EMULATION_PS3_PATH = "ps3_path"
USER_CONF_EMULATION_PS3_CONFIG = "ps3_config"
USER_CONF_EMULATION_SWITCH_PATH = "switch_path"
USER_CONF_EMULATION_SWITCH_CONFIG = "switch_config"

# Emulation
EMULATION_PSX = "emulation-psx"
EMULATION_PS2 = "emulation-ps2"
EMULATION_PS3 = "emulation-ps3"
EMULATION_SWITCH = "emulation-switch"

# Available UI languages ("" = follow system locale)
LANGUAGES = [
    {"code": "", "name": "System"},
    {"code": "en", "name": "English"},
    {"code": "de", "name": "Deutsch"},
]

# User config
GAMESCOPE_INSTALLED = False
VULKAN_INSTALLED = False
UMU_RUN_INSTALLED = False
WINETRICKS_INSTALLED = False
RT_UPSCALING_INSTALLED = False

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
WINE_RUNNERS_DIR.mkdir(parents=True, exist_ok=True)
# PROTON_RUNNERS_DIR.mkdir(parents=True, exist_ok=True) # Don't create in case steam not installed
PREFIXES_DIR.mkdir(parents=True, exist_ok=True)
COVERS_DIR.mkdir(parents=True, exist_ok=True)
DXVK_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)