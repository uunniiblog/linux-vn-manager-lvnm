import struct
import os
import logging
import zlib
import shutil
import binascii
from pathlib import Path

class SteamManager:
    @staticmethod
    def get_shortcuts_paths():
        """ Try to find steam paths """
        paths = set() 
        base_paths = [
            Path.home() / ".steam/steam/userdata",
            Path.home() / ".local/share/Steam/userdata",
            Path.home() / ".var/app/com.valvesoftware.Steam/.steam/steam/userdata"
        ]
        for base in base_paths:
            if base.exists():
                real_base = base.resolve()
                for user_dir in real_base.iterdir():
                    if user_dir.is_dir() and user_dir.name.isdigit():
                        vdf_path = user_dir / "config" / "shortcuts.vdf"
                        paths.add(vdf_path)
        return list(paths)

    @staticmethod
    def _read_string(data, offset):
        """Reads a null-terminated string from binary data."""
        end = data.find(b'\x00', offset)
        return data[offset:end].decode('utf-8', errors='replace'), end + 1

    @staticmethod
    def _parse_binary_vdf(data):
        """Parses Steam's binary shortcuts.vdf into a list of dicts."""
        shortcuts = []
        if not data or len(data) < 11: # Minimal size for header + footer
            return shortcuts
            
        try:
            offset = 0
            # Header: \x00 + "shortcuts" + \x00
            if data[offset] != 0: return []
            name, offset = SteamManager._read_string(data, offset + 1)
            
            while offset < len(data) and data[offset] != 8: # 0x08 marks end of list
                # Start of a shortcut object (\x00 + index + \x00)
                if data[offset] != 0: break
                index_str, offset = SteamManager._read_string(data, offset + 1)
                
                shortcut = {}
                while offset < len(data) and data[offset] != 8:
                    type_byte = data[offset]
                    offset += 1
                    key, offset = SteamManager._read_string(data, offset)
                    
                    if type_byte == 1: # String
                        val, offset = SteamManager._read_string(data, offset)
                        shortcut[key] = val
                    elif type_byte == 2: # Integer
                        val = struct.unpack("<I", data[offset:offset+4])[0]
                        shortcut[key] = val
                        offset += 4
                
                offset += 1 # Skip the closing 0x08 of the shortcut object
                shortcuts.append(shortcut)
        except Exception as e:
            logging.error(f"Error parsing Steam VDF: {e}")
            
        return shortcuts

    @staticmethod
    def _to_binary_vdf(shortcuts):
        """Serializes a list of shortcut dicts back to Steam's binary format."""
        def write_string(key, value):
            return b'\x01' + key.encode('utf-8') + b'\x00' + value.encode('utf-8') + b'\x00'
        
        def write_int(key, value):
            return b'\x02' + key.encode('utf-8') + b'\x00' + struct.pack("<I", value)

        data = b'\x00shortcuts\x00'
        for i, s in enumerate(shortcuts):
            appid = SteamManager._generate_appid(s.get("Exe", ""), s.get("AppName", ""))

            data += b'\x00' + str(i).encode('utf-8') + b'\x00'

            data += write_int("appid", appid)
            data += write_string("AppName", s.get("AppName", ""))
            data += write_string("Exe", s.get("Exe", ""))
            data += write_string("StartDir", s.get("StartDir", ""))
            data += write_string("icon", s.get("icon", ""))
            data += write_string("LaunchOptions", s.get("LaunchOptions", ""))
            data += write_int("AllowDesktopConfig", s.get("AllowDesktopConfig", 1))
            data += write_int("AllowOverlay", s.get("AllowOverlay", 1))
            data += write_int("OpenVR", s.get("OpenVR", 0))
            data += write_int("Devkit", s.get("Devkit", 0))

            # End of this shortcut
            data += b'\x08' 

        # End of file
        data += b'\x08\x08' 
        return data

    @staticmethod
    def _generate_appid(exe, name):
        """Generates the unique 32-bit ID Steam uses for grid images."""
        unique_id = exe + name
        return binascii.crc32(unique_id.encode('utf-8')) | 0x80000000

    @staticmethod
    def set_game_cover(vdf_path, exe, name, icon_path):
        """Copies the icon_path to the Steam grid folder with the correct ID."""
        if not icon_path or not os.path.exists(icon_path):
            return
            
        # The grid folder is in the same 'config' parent as shortcuts.vdf
        grid_dir = vdf_path.parent / "grid"
        grid_dir.mkdir(parents=True, exist_ok=True)
        
        vdf_exe = f'"{exe}"'
        appid = SteamManager._generate_appid(vdf_exe, name)

        ext = os.path.splitext(icon_path)[1] or ".png"

        # Add vertical cover
        target_vertical = grid_dir / f"{appid}p{ext}"
        # target_horizontal = grid_dir / f"{appid}{ext}"
        
        try:
            shutil.copy2(icon_path, target_vertical)
            logging.info(f"Cover art set for {name} (ID: {appid} Path: {target_vertical})")
        except Exception as e:
            logging.error(f"Failed to copy cover art: {e}")

    @staticmethod
    def add_non_steam_game(name, exe, start_dir, icon, options=""):
        vdf_paths = SteamManager.get_shortcuts_paths()
        if not vdf_paths:
            return False

        vdf_exe = f'"{exe}"'
        vdf_start_dir = f'"{start_dir}"'
        
        for path in vdf_paths:
            existing_shortcuts = []
            if path.exists():
                with open(path, "rb") as f:
                    existing_shortcuts = SteamManager._parse_binary_vdf(f.read())

            # Check if game already exists (by Name or Exe)
            found = False
            for s in existing_shortcuts:
                if s.get("AppName") == name:
                    s["Exe"] = vdf_exe
                    s["StartDir"] = vdf_start_dir
                    s["icon"] = icon
                    s["LaunchOptions"] = options
                    found = True
                    break
            
            if not found:
                # Add new entry
                existing_shortcuts.append({
                    "AppName": name,
                    "Exe": vdf_exe,
                    "StartDir": vdf_start_dir,
                    "icon": icon,
                    "LaunchOptions": options
                })
            
            # Write merged data back
            binary_data = SteamManager._to_binary_vdf(existing_shortcuts)
            SteamManager.set_game_cover(path, exe, name, icon)
            try:
                with open(path, "wb") as f:
                    f.write(binary_data)
                logging.info(f"Updated Steam shortcuts at {path}")
            except Exception as e:
                logging.error(f"Failed to write to {path}: {e}")
                
        return True