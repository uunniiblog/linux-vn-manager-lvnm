import os
import sys
import platform
import subprocess
import shutil
import json
import config
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from steam_manager import SteamManager

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

        # # --- APPIMAGE TEST UMU ---
        # appdir = os.environ.get("APPDIR")
        # if appdir:
        #     logger.debug("--- AppImage Bundled Tools ---")
        #     tools_dir = Path(appdir) / "usr" / "bin" / "tools"
            
        #     bundled_tools = {
        #         'umu-run': ["--version", False],
        #         'winetricks': ["--version", True]
        #     }

        #     # Create a clean environment for the subprocess to prevent GUI popups
        #     test_env = os.environ.copy()
        #     test_env["WINETRICKS_GUI"] = "0"  # Force winetricks to CLI mode

        #     for tool, config in bundled_tools.items():
        #         version_flag, use_shell = config
        #         path = tools_dir / tool
                
        #         if path.exists():
        #             try:
        #                 result = subprocess.run(
        #                     [str(path), version_flag],
        #                     capture_output=True,
        #                     text=True,
        #                     check=True,
        #                     shell=use_shell,
        #                     env=test_env
        #                 )
                        
        #                 # Clean up the output
        #                 version_info = result.stdout.strip().split('\n')[0]
        #                 logger.debug(f"✅ {tool:10} : {version_info}")
        #                 logger.debug(f"    Path: {path}")
        #             except Exception as e:
        #                 logger.debug(f"❌ {tool:10} : Found but failed to execute: {e}")
        #         else:
        #             logger.debug(f"❓ {tool:10} : NOT found in bundled tools folder")
        
        # logger.debug("="*60)

    @staticmethod
    def get_runtime_type() -> str:
        """Returns the runtime environment type: 'appimage', 'flatpak', 'dev', etc."""
        if os.environ.get("APPDIR"):
            return "appimage"
        if os.environ.get("FLATPAK_ID"):
            return "flatpak"
        if os.environ.get("SNAP"):
            return "snap"
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
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
        else:
            logger.error(f"[Error] Path does not exist: {folder_path}")

    @staticmethod
    def get_cover_path(vndb_id: str) -> str:
        """
        Searches for a cover image matching the VNDB ID in the covers directory.
        Returns the absolute path as a string if found, otherwise an empty string.
        """
        if not vndb_id:
            return ""

        covers_dir = Path(config.COVERS_DIR)
        if not covers_dir.exists():
            return ""

        # Search for any file extension matching the VNDB ID
        # glob is used to handle .jpg, .png, .webp, etc.
        matches = list(covers_dir.glob(f"{vndb_id}.*"))
        
        if matches:
            return str(matches[0].absolute())
        
        return ""

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
        
        icon_path = SystemUtils.get_cover_path(game_card.vndb) or ""
        game_dir = os.path.dirname(game_card.path)

        success = SteamManager.add_non_steam_game(
            name=f"LVNM: {game_card.name}",
            exe=exe_cmd,
            start_dir=game_dir,
            icon=icon_path,
            options=launch_options
        )
        
        if success:
            logging.info(f"Added {game_card.name} to Steam. Please RESTART Steam.")
        