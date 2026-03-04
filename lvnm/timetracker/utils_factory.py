import os
import logging
from timetracker.kde_utils import KdeUtils
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
        logger.info("Gaming mode test")
    elif "GNOME" in de.upper():
        logger.info("Using GnomeUtils")
        # return GnomeUtils()

    # Give error if no supported DE
    raise RuntimeError(
        f"Unsupported Desktop Environment: '{de}'. "
        "This application currently only supports KDE via KWin Scripting API."
    )
        
