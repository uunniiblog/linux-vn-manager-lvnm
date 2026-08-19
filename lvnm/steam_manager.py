import struct
import os
import logging
import zlib
import shutil
import binascii
from pathlib import Path

logger = logging.getLogger(__name__)

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
    def _parse_object(data, offset):
        """
        Parses a binary VDF object
        Field types:
          0x00 -> nested object (e.g. "tags"), parsed recursively
          0x01 -> null-terminated string
          0x02 -> little-endian uint32
        """
        obj = {}
        while offset < len(data) and data[offset] != 0x08:
            type_byte = data[offset]
            offset += 1
            key, offset = SteamManager._read_string(data, offset)

            if type_byte == 0x00:  # Nested object, e.g. "tags"
                value, offset = SteamManager._parse_object(data, offset)
            elif type_byte == 0x01:  # String
                value, offset = SteamManager._read_string(data, offset)
            elif type_byte == 0x02:  # Integer
                value = struct.unpack("<I", data[offset:offset + 4])[0]
                offset += 4
            else:
                # Unknown type. Don't guess - guessing wrong desyncs every
                # byte after this and silently destroys the rest of the file.
                raise ValueError(
                    f"Unknown VDF field type 0x{type_byte:02x} for key '{key}' "
                    f"at offset {offset}"
                )
            obj[key] = value

        offset += 1  # consume this object's closing 0x08
        return obj, offset

    @staticmethod
    def _parse_binary_vdf(data):
        """Parses Steam's binary shortcuts.vdf into a list of dicts."""
        shortcuts = []
        if not data or len(data) < 11: # Minimal size for header + footer
            return shortcuts

        try:
            offset = 0
            # Header: \x00 + "shortcuts" + \x00
            if data[offset] != 0:
                return []
            _, offset = SteamManager._read_string(data, offset + 1)

            while offset < len(data) and data[offset] != 0x08:  # 0x08 marks end of list
                # Start of a shortcut object (\x00 + index + \x00)
                if data[offset] != 0:
                    break
                _, offset = SteamManager._read_string(data, offset + 1)

                shortcut, offset = SteamManager._parse_object(data, offset)
                shortcuts.append(shortcut)
        except Exception as e:
            logging.error(f"Error parsing Steam VDF: {e}")
            raise

        return shortcuts

    @staticmethod
    def _write_value(key, value):
        """Serializes a single key/value pair to binary VDF"""
        if isinstance(value, dict):
            body = b'\x00' + key.encode('utf-8') + b'\x00'
            for sub_key, sub_value in value.items():
                body += SteamManager._write_value(sub_key, sub_value)
            body += b'\x08'
            return body
        if isinstance(value, int):  # covers bool too (bool is an int subclass)
            return b'\x02' + key.encode('utf-8') + b'\x00' + struct.pack("<I", int(value))
        # Default: string
        return b'\x01' + key.encode('utf-8') + b'\x00' + str(value).encode('utf-8') + b'\x00'

    @staticmethod
    def _to_binary_vdf(shortcuts):
        """Serializes a list of shortcut dicts back to Steam's binary format."""
        data = b'\x00shortcuts\x00'
        for i, s in enumerate(shortcuts):
            entry = dict(s)  # don't mutate the caller's dict

            # appid is always derived, and always first, to match Steam's
            # own layout and keep the value consistent with Exe/AppName.
            entry["appid"] = SteamManager._generate_appid(
                entry.get("Exe", ""), entry.get("AppName", "")
            )
            entry.setdefault("AppName", "")
            entry.setdefault("Exe", "")
            entry.setdefault("StartDir", "")
            entry.setdefault("icon", "")
            entry.setdefault("LaunchOptions", "")
            entry.setdefault("AllowDesktopConfig", 1)
            entry.setdefault("AllowOverlay", 1)
            entry.setdefault("OpenVR", 0)
            entry.setdefault("Devkit", 0)
            entry.setdefault("tags", {})

            data += b'\x00' + str(i).encode('utf-8') + b'\x00'
            for key, value in entry.items():
                data += SteamManager._write_value(key, value)
            data += b'\x08'  # End of this shortcut

        # End of file
        data += b'\x08\x08'
        return data

    @staticmethod
    def _generate_appid(exe, name):
        """Generates the unique 32-bit ID Steam uses for grid images."""
        unique_id = exe + name
        return binascii.crc32(unique_id.encode('utf-8')) | 0x80000000

    @staticmethod
    def set_game_cover(vdf_path, exe, name, icon_path, layout_path):
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
        
        try:
            shutil.copy2(icon_path, target_vertical)
            logging.info(f"Cover art set for {name} (ID: {appid} Path: {target_vertical})")
        except Exception as e:
            logging.error(f"Failed to copy cover art: {e}")

        # Add horizontal cover
        if layout_path:
            ext_h = os.path.splitext(layout_path)[1] or ".png"
            # Normal Horizontal Grid used in recent games/lists
            target_horizontal = grid_dir / f"{appid}{ext_h}" 
            # Hero Background used as the banner
            target_hero = grid_dir / f"{appid}_hero{ext_h}"
            try:
                shutil.copy2(layout_path, target_horizontal)
                shutil.copy2(layout_path, target_hero)
                logging.info(f"Horizontal layouts set for {name} Path: {target_horizontal} {target_hero}")
            except Exception as e:
                logging.error(f"Failed to copy horizontal layout art: {e}")

    @staticmethod
    def add_non_steam_game(name, exe, start_dir, icon_path, layout_path, options=""):
        vdf_paths = SteamManager.get_shortcuts_paths()
        if not vdf_paths:
            return False

        vdf_exe = f'"{exe}"'
        vdf_start_dir = f'"{start_dir}"'
        
        for path in vdf_paths:
            existing_shortcuts = []
            raw_data = None
            if path.exists():
                logger.debug(f"Processing VDF file: {path}")
                raw_data = path.read_bytes()
                try:
                    existing_shortcuts = SteamManager._parse_binary_vdf(raw_data)
                except Exception:
                    logging.error(f"Refusing to modify {path}: could not safely parse the existing shortcuts.vdf")
                    continue

            # Check if game already exists (by Name or Exe)
            found = False
            for s in existing_shortcuts:
                if s.get("AppName") == name:
                    logger.debug(f"Game '{name}' already exists. Updating existing entry attributes.")
                    s["Exe"] = vdf_exe
                    s["StartDir"] = vdf_start_dir
                    s["icon"] = icon_path
                    s["LaunchOptions"] = options
                    found = True
                    break
            
            if not found:
                # Add new entry
                logger.debug(f"Appending new non-Steam game '{name}' to library list.")
                existing_shortcuts.append({
                    "AppName": name,
                    "Exe": vdf_exe,
                    "StartDir": vdf_start_dir,
                    "icon": icon_path,
                    "LaunchOptions": options
                })

            # Back up the previous file before touching it
            if raw_data is not None:
                try:
                    backup_path = path.with_suffix(path.suffix + ".bak")
                    backup_path.write_bytes(raw_data)
                except Exception as e:
                    logging.warning(f"Could not create backup of {path}: {e}")

            # Write merged data back
            binary_data = SteamManager._to_binary_vdf(existing_shortcuts)
            SteamManager.set_game_cover(path, exe, name, icon_path, layout_path)
            try:
                with open(path, "wb") as f:
                    f.write(binary_data)
                logging.info(f"Updated Steam shortcuts at {path}")
            except Exception as e:
                logging.error(f"Failed to write to {path}: {e}")
                
        return True