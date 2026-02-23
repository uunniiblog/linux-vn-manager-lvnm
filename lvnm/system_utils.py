import os
import platform
import subprocess
import shutil
import json
import config
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

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
    def get_system_info() -> dict:
        """Gathers core system, OS, and hardware information."""
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
                result = subprocess.run(["lspci"], capture_output=True, text=True)
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
        support = {
            "vulkan_support": SystemUtils._check_vulkan(),
            "gamescope": bool(shutil.which("gamescope")),
            "umu_run": bool(shutil.which("umu-run")),
            "winetricks": bool(shutil.which("winetricks")),
            "gstreamer_packages": {}
        }

        # Check all GStreamer packages
        for pkg in SystemUtils.GSTREAMER_PACKAGES:
            support["gstreamer_packages"][pkg] = SystemUtils._is_package_installed(pkg)

        return support

    @staticmethod
    def _check_vulkan() -> bool:
        """Checks if Vulkan is supported on the system."""
        # vulkaninfo is the most reliable quick check if installed
        if shutil.which("vulkaninfo"):
            try:
                # If vulkaninfo runs without error, Vulkan is working
                result = subprocess.run(["vulkaninfo"], capture_output=True, env=os.environ)
                return result.returncode == 0
            except Exception:
                pass
        
        # Fallback: check if the Vulkan loader library exists
        try:
            result = subprocess.run(["ldconfig", "-p"], capture_output=True, text=True)
            return "libvulkan.so" in result.stdout
        except Exception:
            return False

    @staticmethod
    def _is_package_installed(pkg_name: str) -> bool:
        """Dynamically checks package managers for installed packages."""
        try:
            # Arch Linux (pacman)
            if shutil.which("pacman"):
                result = subprocess.run(["pacman", "-Qq", pkg_name], capture_output=True)
                return result.returncode == 0
            
            # Debian/Ubuntu (dpkg)
            elif shutil.which("dpkg"):
                result = subprocess.run(["dpkg", "-s", pkg_name], capture_output=True)
                return result.returncode == 0
            
            # Fedora/RHEL (rpm)
            elif shutil.which("rpm"):
                result = subprocess.run(["rpm", "-q", pkg_name], capture_output=True)
                return result.returncode == 0
        except Exception:
            pass
            
        return False

    @staticmethod
    def print_diagnostic_report():
        """Helper to print a nicely formatted console report."""
        print("="*50)
        print(" LVNM SYSTEM DIAGNOSTICS")
        print("="*50)
        
        sys_info = SystemUtils.get_system_info()
        print("\n--- System Information ---")
        print(f"App Version : {sys_info['app_version']}")
        print(f"OS          : {sys_info['os']}")
        print(f"Kernel      : {sys_info['kernel']}")
        print(f"Desktop     : {sys_info['desktop_environment']} ({sys_info['session_type']})")
        print(f"CPU         : {sys_info['cpu']}")
        print(f"GPU         : {sys_info['gpu']}")

        software = SystemUtils.get_software_support()
        print("\n--- Software & Compatibility ---")
        print(f"Vulkan Support : {'✅ Yes' if software['vulkan_support'] else '❌ No'}")
        print(f"Gamescope      : {'✅ Installed' if software['gamescope'] else '❌ Missing'}")
        print(f"Umu-run        : {'✅ Installed' if software['umu_run'] else '❌ Missing'}")
        print(f"Winetricks     : {'✅ Installed' if software['winetricks'] else '❌ Missing'}")

        print("\n--- GStreamer Packages ---")
        for pkg, installed in software['gstreamer_packages'].items():
            status = "✅" if installed else "❌"
            print(f"{status} {pkg}")
        print("="*50)
    
    @staticmethod
    def load_settings() -> dict:
        """Loads user settings from the JSON file."""
        if os.path.exists(config.USER_SETTINGS):
            try:
                with open(config.USER_SETTINGS, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading settings: {e}")
        return {}

    @staticmethod
    def save_settings(data: dict):
        """Saves user settings to the JSON file."""
        try:
            # Ensure the directory exists before saving
            os.makedirs(os.path.dirname(config.USER_SETTINGS), exist_ok=True)
            with open(config.USER_SETTINGS, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error writing settings: {e}")

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

    @staticmethod
    def browse_files(path: str):
        if not path:
            print("[Error] Game has no path to browse to.")
            return

        # Get the directory containing the file
        folder_path = os.path.dirname(os.path.abspath(path))

        if os.path.exists(folder_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
        else:
            print(f"[Error] Path does not exist: {folder_path}")

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