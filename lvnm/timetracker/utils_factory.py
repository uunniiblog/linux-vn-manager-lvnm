import logging
from system_utils import SystemUtils
from timetracker.kde_utils import KdeUtils
from timetracker.gnome_utils import GnomeUtils
from timetracker.x11_utils import X11Utils
from timetracker.gamescope_utils import GamescopeUtils

logger = logging.getLogger(__name__)

def get_desktop_utils():
    """
    Detects the current Desktop Environment.
    Returns an INSTANCE of the correct utility class.
    """
    logger.info("Detecting current Desktop Environment")

    if SystemUtils.is_desktop_environment("KDE"):
        logger.info("Using KdeUtils")
        return KdeUtils()
    elif SystemUtils.is_gnome_desktop():
        try:
            logger.info("Using GnomeUtils")
            return GnomeUtils()
        except RuntimeError as error:
            logger.warning(f"GNOME native window tracking is unavailable: {error}")
            logger.info("Falling back to X11Utils for XWayland windows")
            return X11Utils()
    elif SystemUtils.is_desktop_environment("GAMESCOPE"):
        logger.info("Using GamescopeUtils")
        return GamescopeUtils()
    else:
        logger.info("Using X11Utils")
        return X11Utils()
        
