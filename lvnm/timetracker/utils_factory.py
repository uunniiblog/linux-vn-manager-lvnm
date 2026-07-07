import os
import logging
from timetracker.kde_utils import KdeUtils
from timetracker.x11_utils import X11Utils
from timetracker.gamescope_utils import GamescopeUtils
# from timetracker.gnome_utils import GnomeUtils

logger = logging.getLogger(__name__)

def get_desktop_utils():
    """
    Detects the current Desktop Environment.
    Returns an INSTANCE of the correct utility class.
    """
    # Get DE name and normalize to uppercase
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()

    logger.info(f"Current Desktop Environment: {de}")

    if "KDE" in de.upper():
        logger.info("Using KdeUtils")
        return KdeUtils()
    elif "GAMESCOPE" in de.upper():
        logger.info("Using GamescopeUtils")
        return GamescopeUtils()
    else:
        logger.info("Using X11Utils")
        return X11Utils()
        
