"""Select the time-tracker system backend for the current platform."""

from platform_profile import IS_WINDOWS

if IS_WINDOWS:
    from timetracker.windows_system_utils import WindowsSystemUtils as SystemUtils
else:
    from timetracker.linux_system_utils import LinuxSystemUtils as SystemUtils

__all__ = ["SystemUtils"]
