import logging

from platform_profile import IS_WINDOWS
from system_utils import SystemUtils

logger = logging.getLogger(__name__)

def get_desktop_utils():
    """
    Detects the current Desktop Environment.
    Returns an INSTANCE of the correct utility class.
    """
    logger.info("Detecting current Desktop Environment")

    if IS_WINDOWS:
        from timetracker.windows_utils import WindowsUtils
        logger.info("Using native WindowsUtils")
        return WindowsUtils()

    if SystemUtils.is_desktop_environment("KDE"):
        from timetracker.kde_utils import KdeUtils
        logger.info("Using KdeUtils")
        return KdeUtils()
    elif SystemUtils.is_gnome_desktop():
        from timetracker.gnome_utils import GnomeUtils
        try:
            logger.info("Using GnomeUtils")
            return GnomeUtils()
        except RuntimeError as error:
            from timetracker.x11_utils import X11Utils
            logger.warning(f"GNOME native window tracking is unavailable: {error}")
            logger.info("Falling back to X11Utils for XWayland windows")
            return X11Utils()
    elif SystemUtils.is_desktop_environment("HYPRLAND"):
        from timetracker.hyprland_utils import HyprlandUtils
        try:
            logger.info("Using HyprlandUtils")
            return HyprlandUtils()
        except RuntimeError as error:
            from timetracker.x11_utils import X11Utils
            logger.warning(f"Hyprland native window tracking is unavailable: {error}")
            logger.info("Falling back to X11Utils for XWayland windows")
            return X11Utils()
    elif SystemUtils.is_desktop_environment("GAMESCOPE"):
        from timetracker.gamescope_utils import GamescopeUtils
        logger.info("Using GamescopeUtils")
        return GamescopeUtils()
    else:
        from timetracker.x11_utils import X11Utils
        logger.info("Using X11Utils")
        return X11Utils()
