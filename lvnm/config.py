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

# URLS
KRON4EK_API_URL = "https://api.github.com/repos/Kron4ek/Wine-Builds/releases"
PROTONGE_API_URL = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases"


# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
WINE_RUNNERS_DIR.mkdir(parents=True, exist_ok=True)
PROTON_RUNNERS_DIR.mkdir(parents=True, exist_ok=True)
PREFIXES_DIR.mkdir(parents=True, exist_ok=True)
