import os
import re
import glob
import sys
import platform
import subprocess
import shutil
import filecmp
import json
import config
import logging
import urllib.request
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from steam_manager import SteamManager
from settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class SystemUtils:
    
    GSTREAMER_PACKAGES = [
        "gstreamer", 
        "gst-plugins-ugly", 
        "gst-plugins-good", 
        "gst-plugins-base-libs", 
        "gst-plugins-base", 
        "gst-plugins-bad", 
        "gst-plugins-bad-libs", 
        "gst-plugin-pipewire", 
        "gst-libav"
    ]

    @staticmethod
    def get_clean_env():
        clean_env = os.environ.copy()

        # Restore original LD_LIBRARY_PATH if saved, otherwise strip _MEI and .mount_ AppImage paths
        if "LD_LIBRARY_PATH_ORIG" in clean_env:
            clean_env["LD_LIBRARY_PATH"] = clean_env.pop("LD_LIBRARY_PATH_ORIG")
        elif "LD_LIBRARY_PATH" in clean_env:
            paths = clean_env["LD_LIBRARY_PATH"].split(":")
            clean_paths = [p for p in paths if not any(
                seg in p for seg in ("/tmp/_MEI", "/tmp/.mount_")
            )]
            if clean_paths:
                clean_env["LD_LIBRARY_PATH"] = ":".join(clean_paths)
            else:
                clean_env.pop("LD_LIBRARY_PATH", None)

        clean_env.pop("PYTHONHOME", None)
        clean_env.pop("PYTHONPATH", None)
        clean_env.pop("_PYI_ARCHIVE_FILE", None)

        appdir = os.environ.get("APPDIR")
        if appdir:
            bundled_tools = str(Path(appdir) / "usr" / "bin" / "tools")
            bundled_libs = str(Path(appdir) / "usr" / "lib")
            
            # Add tools to PATH so winetricks finds cabextract
            clean_env["PATH"] = f"{bundled_tools}:{clean_env.get('PATH', '')}"
            
            # Add libs to LD_LIBRARY_PATH so cabextract finds libmspack
            clean_env["LD_LIBRARY_PATH"] = f"{bundled_libs}:{clean_env.get('LD_LIBRARY_PATH', '')}"

        return clean_env

    @staticmethod
    def get_system_info() -> dict:
        """Gathers core system, OS, and hardware information."""
        clean_env = SystemUtils.get_clean_env()

        info = {
            "app_version": getattr(config, "VERSION", "Unknown"),
            "os": "Unknown Linux",
            "kernel": platform.release(),
            "desktop_environment": os.environ.get("XDG_CURRENT_DESKTOP", "Unknown"),
            "session_type": os.environ.get("XDG_SESSION_TYPE", "Unknown"),
            "cpu": "Unknown CPU",
            "gpu": "Unknown GPU"
        }

        # Get OS Name
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        info["os"] = line.split("=")[1].strip().strip('"')
                        break
        except FileNotFoundError:
            pass

        # Get CPU Model
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        info["cpu"] = line.split(":")[1].strip()
                        break
        except FileNotFoundError:
            pass

        # Get GPU Model (requires pciutils/lspci)
        if shutil.which("lspci"):
            try:
                result = subprocess.run(["lspci"], capture_output=True, text=True, env=clean_env)
                gpus = [
                    line.split(":")[-1].strip() 
                    for line in result.stdout.split("\n") 
                    if "VGA compatible controller" in line or "3D controller" in line
                ]
                if gpus:
                    info["gpu"] = " | ".join(gpus)
            except Exception:
                pass

        return info

    @staticmethod
    def get_software_support() -> dict:
        """Checks for necessary binaries, tools, and libraries."""
        clean_env = SystemUtils.get_clean_env()
        appdir = os.environ.get("APPDIR")

        # When running as AppImage, bundled tools are always available (unless build failed)
        # Fall back to system check when running from source/dev
        if appdir:
            tools_dir = Path(appdir) / "usr" / "bin" / "tools"
            umu_available = (tools_dir / "umu-run").exists()
            winetricks_available = (tools_dir / "winetricks").exists()
        else:
            umu_available = bool(shutil.which("umu-run"))
            winetricks_available = bool(shutil.which("winetricks"))

        support = {
            "vulkan_support": SystemUtils._check_vulkan(clean_env),
            "gamescope": bool(shutil.which("gamescope")),
            "umu_run": umu_available,
            "winetricks": winetricks_available,
            "gstreamer_packages": {}
        }

        # Update the config module variables
        mapping = {
            "gamescope": "GAMESCOPE_INSTALLED",
            "vulkan_support": "VULKAN_INSTALLED",
            "umu_run": "UMU_RUN_INSTALLED",
            "winetricks": "WINETRICKS_INSTALLED"
        }

        for support_key, config_var in mapping.items():
            is_supported = support.get(support_key, False)
            setattr(config, config_var, is_supported)

        # Check all GStreamer packages
        for pkg in SystemUtils.GSTREAMER_PACKAGES:
            support["gstreamer_packages"][pkg] = SystemUtils._is_package_installed(pkg)

        return support

    @staticmethod
    def _check_vulkan(env=None) -> bool:
        if env is None:
            env = SystemUtils.get_clean_env()
        if shutil.which("vulkaninfo"):
            try:
                result = subprocess.run(["vulkaninfo"], capture_output=True, env=env)
                return result.returncode == 0
            except Exception:
                pass
        try:
            result = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True, env=env)
            return "libvulkan.so" in result.stdout
        except Exception:
            return False


    @staticmethod
    def _is_package_installed(pkg_name: str, env=None) -> bool:
        if env is None:
            env = SystemUtils.get_clean_env()
        try:
            if shutil.which("pacman"):
                result = subprocess.run(["pacman", "-Qq", pkg_name], capture_output=True, env=env)
                return result.returncode == 0
            elif shutil.which("dpkg"):
                result = subprocess.run(["dpkg", "-s", pkg_name], capture_output=True, env=env)
                return result.returncode == 0
            elif shutil.which("rpm"):
                result = subprocess.run(["rpm", "-q", pkg_name], capture_output=True, env=env)
                return result.returncode == 0
        except Exception:
            pass
        return False

    @staticmethod
    def print_diagnostic_report():
        """Helper to print a nicely formatted console report."""
        logger.debug("="*50)
        logger.debug(" LVNM SYSTEM DIAGNOSTICS")
        logger.debug("="*50)
        
        sys_info = SystemUtils.get_system_info()
        logger.debug("--- System Information ---")
        logger.debug(f"App Version : {sys_info['app_version']}")
        logger.debug(f"OS          : {sys_info['os']}")
        logger.debug(f"Kernel      : {sys_info['kernel']}")
        logger.debug(f"Desktop     : {sys_info['desktop_environment']} ({sys_info['session_type']})")
        logger.debug(f"CPU         : {sys_info['cpu']}")
        logger.debug(f"GPU         : {sys_info['gpu']}")

        software = SystemUtils.get_software_support()
        logger.debug("--- Software & Compatibility ---")
        logger.debug(f"Vulkan Support : {'✅ Yes' if software['vulkan_support'] else '❌ No'}")
        logger.debug(f"Gamescope      : {'✅ Installed' if software['gamescope'] else '❌ Missing'}")
        logger.debug(f"Umu-run        : {'✅ Installed' if software['umu_run'] else '❌ Missing'}")
        logger.debug(f"Winetricks     : {'✅ Installed' if software['winetricks'] else '❌ Missing'}")

        logger.debug("--- GStreamer Packages ---")
        for pkg, installed in software['gstreamer_packages'].items():
            status = "✅" if installed else "❌"
            logger.debug(f"{status} {pkg}")
        logger.debug("="*50)

    @staticmethod
    def get_latest_release_info() -> tuple[str, str]:
        """Fetches the latest official release tag and URL from GitHub."""
        try:
            # The /latest endpoint automatically filters out pre-releases like 'Continuous Build'
            api_url = config.LVNM_API_URL + "/latest"
            req = urllib.request.Request(api_url)
            
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                logger.debug(f"Newest LVNM version {data.get("tag_name")}")
                return data.get("tag_name"), data.get("html_url")
        except Exception as e:
            logger.error(f"Update check failed: {e}")
            return None, None

    @staticmethod
    def move_directory_contents(old_path, new_path):
        """Moves all files and folders from old_path to new_path."""
        old_dir = Path(old_path)
        new_dir = Path(new_path)

        if not old_dir.exists() or not old_dir.is_dir():
            logger.info(f"Source directory {old_dir} does not exist. Nothing to move.")
            return True

        if old_dir.resolve() == new_dir.resolve():
            logger.info("Old and new paths are the exact same. Skipping move.")
            return True

        try:
            for item in old_dir.iterdir():
                target_path = new_dir / item.name
                if target_path.exists():
                    logger.warning(f"Target {target_path} already exists. Skipping")
                    continue

                # Move the item (file or folder)
                shutil.move(str(item), str(target_path))
                logger.debug(f"Moved {str(item)} to {str(target_path)}")

            logger.info(f"Successfully moved contents from {old_dir} to {new_dir}")
            return True
        except Exception as e:
            logger.error(f"Critical error moving files from {old_dir} to {new_dir}: {e}")
            return False
    
    @staticmethod
    def move_file(old_file, target_path):
        shutil.move(str(old_file), str(target_path))

    @staticmethod
    def rename_folder(old_path, new_path) -> bool:
        try:
            if old_path.exists():
                if new_path.exists():
                    logger.error(f"Target folder {new_path} already exists on disk.")
                    return False
                
                shutil.move(str(old_path), str(new_path))
                logger.info(f"Folder renamed from {old_path} to {new_path}")
                return True
        except Exception as e:
            logger.error(f"Physical folder rename failed: {e}")
            return False

    @staticmethod
    def get_extension(filename: str) -> str:
        """Returns the extension (including dot) from a path or URL."""
        return Path(filename).suffix

    @staticmethod
    def get_runtime_type() -> str:
        """Returns the runtime environment type."""
        if os.environ.get("APPDIR"):
            return "appimage"
        return "dev"

    @staticmethod
    def apply_ui_zoom(zoom_factor: float):
        """
        Applies a global font-based zoom to the entire application.
        1.0 = Normal, 1.2 = 20% larger, etc.
        """
        app = QApplication.instance()
        if not app:
            return

        # Fetch the current global font
        font = app.font()
        
        # Determine a reasonable base size if none is set (usually 9 or 10)
        # We use pointSizeF to allow for smooth fractional scaling
        base_size = 10 
        font.setPointSizeF(base_size * zoom_factor)
        
        # Apply it globally. All widgets will resize their layouts to fit this text.
        app.setFont(font)

        # from ui.main_window import MainWindow
        # # Then find the MainWindow instance and update sidebar
        # from ui.main_window import MainWindow
        # for widget in app.topLevelWidgets():
        #     if isinstance(widget, MainWindow):
        #         widget.update_sidebar_font()
        #         break

    @staticmethod
    def browse_files(path: str):
        if not path:
            logger.error("[Error] Path does not exist.")
            return

        # Get the directory containing the file
        if os.path.isdir(path):
            folder_path = os.path.abspath(path)
        else:
            folder_path = os.path.dirname(os.path.abspath(path))

        if os.path.exists(folder_path):
            runtime = SystemUtils.get_runtime_type()
            if runtime == "appimage":
                # running from appimage
                clean_env = SystemUtils.get_clean_env()
                clean_env.pop("LD_LIBRARY_PATH", None)
                logger.debug("browse_files using xdg-open")
                subprocess.Popen(["xdg-open", folder_path], env=clean_env)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
        else:
            logger.error(f"[Error] Path does not exist: {folder_path}")

    @staticmethod
    def get_cover_path(cover_path: str = "", vndb_id: str = "") -> str:
        """
        Searches for a cover image matching cover_path or the VNDB ID in the covers directory.
        Returns the absolute path as a string if found, otherwise an empty string.
        """
        if cover_path and Path(cover_path).exists():
            return cover_path

        if not vndb_id:
            return ""

        settings = SettingsManager()
        covers_dir = Path(settings.get(config.USER_CONF_COVERS_PATH, config.COVERS_DIR))
        if not covers_dir.exists():
            return ""

        # Search for any file extension matching the VNDB ID
        matches = list(covers_dir.glob(f"{vndb_id}*_p.*"))
        if not matches:
            # fallback check for original naming without _p to not break current covers
            matches = list(covers_dir.glob(f"{vndb_id}.*"))
        
        if matches:
            return str(matches[0].absolute())
        
        return ""

    @staticmethod
    def save_image_to_covers(temp_path: str, vndb_id: str, role: str) -> str:
        """
        Image saving for Vertical Covers and Horizontal Layouts.
        - role "vertical" -> suffix '_p'
        - role "horizontal" -> suffix '_horizontal'
        Returns the final absolute path as a string.
        """
        if not temp_path or not vndb_id:
            return ""

        temp_file = Path(temp_path)
        if not temp_file.exists():
            logging.warning(f"Temp image not found at: {temp_path}")
            return ""

        dest_dir = Path(SettingsManager().get(config.USER_CONF_COVERS_PATH, config.COVERS_DIR))
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Determine suffix based on role
        suffix = "_p" if role == "vertical" else "_horizontal"
        image_name = Path(temp_path).stem
        final_filename = f"{vndb_id}-{image_name}{suffix}{temp_file.suffix}"
        final_path = dest_dir / final_filename

        try:
            shutil.copy2(temp_path, final_path)
            return str(final_path)
        except Exception as e:
            logging.error(f"Failed to copy image to covers folder: {e}")
            return ""

    @staticmethod
    def delete_covers_in_folder(folder_path: str, extensions: dict):
        """Delete all files in folder"""
        deleted = 0
        for pattern in extensions:
            for file_path in glob.glob(os.path.join(folder_path, pattern)):
                try:
                    os.remove(file_path)
                    deleted += 1
                    logger.debug("Deleted cover: %s", file_path)
                except OSError as exc:
                    logger.error("Failed to delete cover %s: %s", file_path, exc)

    @staticmethod
    def are_files_identical(path1: str, path2: str) -> bool:
        """Checks if two files are bitwise identical."""
        if not path1 or not path2:
            return False
        p1, p2 = Path(path1), Path(path2)
        if not p1.exists() or not p2.exists():
            return False
        return filecmp.cmp(p1, p2, shallow=False)

    @staticmethod
    def get_default_terminal():
        term_options = [
            "x-terminal-emulator", "gnome-terminal", "konsole", 
            "xfce4-terminal", "alacritty", "kitty", "xterm"
        ]
        for t in term_options:
            if shutil.which(t):
                return t

    @staticmethod
    def get_session_type():
        """x11 or wayland"""
        session = os.environ.get("XDG_SESSION_TYPE", "x11").lower()
        logger.debug(f"session_type {session}")
        return session

    @staticmethod
    def get_mainscreen_resolution_xrandr():
        """ Returns main screen resolution"""
        try:
            out = subprocess.check_output(
                ["xrandr", "--listmonitors"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=3,
            )
        except Exception:
            return None

        for line in out.splitlines():
            # 0: +*DP-1 3840/597x2160/336+3200+0  DP-1
            # 1: +DP-2 3200/597x1800/336+0+0  DP-2
            if "*" in line:
                # Extract the WIDTHxHEIGHT before the slash/mm part
                m = re.search(r"(\d+)/\d+x(\d+)/\d+", line)
                if m:
                    logger.debug(f"{int(m.group(1))}, {int(m.group(2))}")
                    return int(m.group(1)), int(m.group(2))
        
        return None

    @staticmethod
    def get_mainscreen_resolution() -> tuple[int, int]:
        """
        Returns the primary monitor's physical resolution by reading
        EDID directly from the kernel sysfs.
        """

        def _get_primary_output_name() -> str | None:
            """Use xrandr --listmonitors to find the primary output name."""
            try:
                out = subprocess.check_output(
                    ["xrandr", "--listmonitors"],
                    stderr=subprocess.DEVNULL, text=True, timeout=3
                )
            except Exception:
                return None
            for line in out.splitlines():
                if "*" in line:
                    return line.strip().split()[-1]  # last token is the output name
            return None

        def _parse_edid_resolution(edid_bytes: bytes) -> tuple[int, int] | None:
            """
            Parse the preferred (native) resolution from EDID binary data.

            EDID spec (section 3.10): bytes 54-71 are the first detailed
            timing descriptor, which encodes the native/preferred resolution.

            byte 56      : H active pixels, low 8 bits
            byte 58 >> 4 : H active pixels, high 4 bits
            byte 59      : V active lines,  low 8 bits
            byte 61 >> 4 : V active lines,  high 4 bits
            """
            if len(edid_bytes) < 72:
                return None

            # Validate EDID header (first 8 bytes must be 00 FF FF FF FF FF FF 00)
            if edid_bytes[:8] != b'\x00\xff\xff\xff\xff\xff\xff\x00':
                return None

            h_active = ((edid_bytes[58] >> 4) << 8) | edid_bytes[56]
            v_active = ((edid_bytes[61] >> 4) << 8) | edid_bytes[59]

            if h_active > 0 and v_active > 0:
                logger.debug(f"h_active: {h_active}, v_active: {v_active}")
                return h_active, v_active
            return None

        def _edid_resolution(output_name: str) -> tuple[int, int] | None:
            """
            Find the EDID file for the given output name in sysfs.
            Kernel exposes EDID at: /sys/class/drm/card<N>-<output>/edid
            e.g. DP-1 → /sys/class/drm/card0-DP-1/edid
            """
            # Glob handles multiple cards (card0, card1, etc.)
            pattern = f"/sys/class/drm/card*-{output_name}/edid"
            matches = glob.glob(pattern)

            for edid_path in matches:
                try:
                    with open(edid_path, "rb") as f:
                        edid_bytes = f.read()
                    if edid_bytes:
                        result = _parse_edid_resolution(edid_bytes)
                        if result:
                            return result
                except OSError:
                    continue
            return None

        primary = _get_primary_output_name()
        if primary:
            result = _edid_resolution(primary)
            if result:
                return result

        return SystemUtils.get_mainscreen_resolution_xrandr()

    @staticmethod
    def get_tool_path(tool_name: str) -> str:
        appdir = os.environ.get("APPDIR")
        if appdir:
            bundled_path = Path(appdir) / "usr" / "bin" / "tools" / tool_name
            if bundled_path.exists():
                logger.debug(f"using {tool_name} bundled {bundled_path}")
                return str(bundled_path)

        logger.debug(f"using {tool_name} from system path")
        return tool_name

    @staticmethod
    def get_launch_command(game_name: str, for_steam: bool = False):
        """
        Determines the correct executable path and arguments depending on 
        whether the app is running as an AppImage, a PyInstaller binary, or from source.
        """
        appimage_path = os.environ.get("APPIMAGE")
        
        if appimage_path:
            logger.debug("get_launch_command - Running as an AppImage")
            exe_cmd = f'"{appimage_path}"'
            args = f'-r "{game_name}"'
        elif getattr(sys, 'frozen', False):
            logger.debug("get_launch_command - Running from compiled py")
            exe_cmd = f'"{sys.executable}"'
            args = f'-r "{game_name}"'
        else:
            logger.debug("get_launch_command - Running from source")
            exe_cmd = f'"{sys.executable}"'
            app_path = os.path.abspath(sys.argv[0])
            args = f'"{app_path}" -r "{game_name}"'

        if for_steam:
            args += " --steam"

        return exe_cmd, args
    
    @staticmethod
    def create_desktop_shortcut(game, cover):
        """Generates a .desktop file on the user's desktop."""
        try:
            # Define paths
            desktop_path = Path(os.path.expanduser("~/Desktop"))
            shortcut_file = desktop_path / f"lvnm-{game}.desktop"
            
            # Get the path to your current executable/script
            exe_cmd, args = SystemUtils.get_launch_command(game)
            exec_cmd = f"{exe_cmd} {args}"
            
            # Get VNDB Icon if available
            icon_path = SystemUtils.get_cover_path(cover) or "applications-games"

            # Create the .desktop content
            content = [
                "[Desktop Entry]",
                "Type=Application",
                f"Name=lvnm-{game}",
                f"Exec={exec_cmd}",
                f"Icon={icon_path}",
                "Terminal=false",  # Set to true if you want to see the logs in a console
                "Categories=Game;",
                f"Comment=Launch {game} via LVNM",
            ]

            # Write the file
            with open(shortcut_file, "w", encoding="utf-8") as f:
                f.write("\n".join(content))

            # Make executable
            os.chmod(shortcut_file, 0o755)
            
            logging.info(f"Shortcut created at: {shortcut_file}")
        except Exception as e:
            logging.error(f"Failed to create shortcut: {e}")

    @staticmethod
    def add_to_steam(game_card):
        exe_cmd, launch_options = SystemUtils.get_launch_command(game_card.name, for_steam=True)
        
        icon_path = SystemUtils.get_cover_path(game_card.cover_path, game_card.vndb) or ""
        layout_path = game_card.layout_path or ""
        game_dir = os.path.dirname(game_card.path)

        success = SteamManager.add_non_steam_game(
            name=f"LVNM: {game_card.name}",
            exe=exe_cmd,
            start_dir=game_dir,
            icon_path=icon_path,
            layout_path=layout_path,
            options=launch_options
        )
        
        if success:
            logging.info(f"Added {game_card.name} to Steam. RESTART Steam to show up.")

    @staticmethod
    def contains_japanese(text):
        # Matches Hiragana, Katakana, and CJK Kanji
        return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text))
        