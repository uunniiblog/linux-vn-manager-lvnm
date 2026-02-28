import struct
import os
import logging
from pathlib import Path

class SteamManager:
    @staticmethod
    def get_shortcuts_paths():
        paths = []
        base_paths = [
            Path.home() / ".steam/steam/userdata",
            Path.home() / ".local/share/Steam/userdata",
            Path.home() / ".var/app/com.valvesoftware.Steam/.steam/steam/userdata"
        ]
        for base in base_paths:
            if base.exists():
                for user_dir in base.iterdir():
                    if user_dir.is_dir() and user_dir.name.isdigit():
                        vdf_path = user_dir / "config" / "shortcuts.vdf"
                        paths.append(vdf_path)
        return paths

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
            data += b'\x00' + str(i).encode('utf-8') + b'\x00'
            # Essential Steam fields
            data += write_string("AppName", s.get("AppName", ""))
            data += write_string("Exe", s.get("Exe", ""))
            data += write_string("StartDir", s.get("StartDir", ""))
            data += write_string("icon", s.get("icon", ""))
            data += write_string("LaunchOptions", s.get("LaunchOptions", ""))
            # Default settings to make it look like a real non-steam game
            data += write_int("AllowDesktopConfig", s.get("AllowDesktopConfig", 1))
            data += write_int("AllowOverlay", s.get("AllowOverlay", 1))
            data += write_int("OpenVR", s.get("OpenVR", 0))
            data += write_int("Devkit", s.get("Devkit", 0))
            data += b'\x08' # End of this shortcut
        data += b'\x08\x08' # End of file
        return data

    @staticmethod
    def add_non_steam_game(name, exe, start_dir, icon, options=""):
        vdf_paths = SteamManager.get_shortcuts_paths()
        if not vdf_paths:
            return False
        
        for path in vdf_paths:
            existing_shortcuts = []
            if path.exists():
                with open(path, "rb") as f:
                    existing_shortcuts = SteamManager._parse_binary_vdf(f.read())

            # Check if game already exists (by Name or Exe)
            found = False
            for s in existing_shortcuts:
                if s.get("AppName") == name:
                    # Update existing entry
                    s["Exe"] = f'"{exe}"'
                    s["StartDir"] = f'"{start_dir}"'
                    s["icon"] = icon
                    s["LaunchOptions"] = options
                    found = True
                    break
            
            if not found:
                # Add new entry
                existing_shortcuts.append({
                    "AppName": name,
                    "Exe": f'"{exe}"',
                    "StartDir": f'"{start_dir}"',
                    "icon": icon,
                    "LaunchOptions": options
                })
            
            # Write merged data back
            binary_data = SteamManager._to_binary_vdf(existing_shortcuts)
            try:
                with open(path, "wb") as f:
                    f.write(binary_data)
                logging.info(f"Updated Steam shortcuts at {path}")
            except Exception as e:
                logging.error(f"Failed to write to {path}: {e}")
                
        return True