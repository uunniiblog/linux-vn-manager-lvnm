import hashlib
import logging
import re
import shutil
from pathlib import Path

import config

logger = logging.getLogger(__name__)


class Pc98Manager:
    """Create an isolated RetroArch/NP2kai profile managed by LVNM."""

    FLOPPY_EXTENSIONS = frozenset({
        ".d88", ".88d", ".d98", ".98d", ".fdi", ".xdf", ".hdm", ".dup", ".2hd", ".tfd", ".nfd", ".hd4", ".hd5", ".hd9",
        ".fdd", ".h01", ".hdb", ".ddb", ".dd6", ".dcp", ".dcu", ".flp", ".img", ".ima", ".bin", ".fim", ".scp", ".hfe"
    })
    HARD_DISK_EXTENSIONS = frozenset({".thd", ".nhd", ".hdi", ".vhd", ".slh", ".sln", ".hdn", ".hdd"})
    CD_EXTENSIONS = frozenset({".cue", ".iso", ".ccd", ".mds", ".nrg"})
    CMD_MAX_BYTES = 1023
    DISK_MARKER_PATTERN = re.compile(
        r"(?:[\s._-]*[\[(]\s*(?:disk|disc)\s*(?:\d+\s+of\s+\d+|[a-z]|\d+)\s*[\])])|"
        r"(?:[\s._-]+(?:disk|disc)[\s._-]*(?:\d+\s+of\s+\d+|[a-z]|\d+))",
        re.IGNORECASE
    )

    CORE_OPTION_KEYS = {
        "model": "np2kai_model",
        "base_clock": "np2kai_clk_base",
        "cpu_multiplier": "np2kai_clk_mult",
        "ram_size": "np2kai_ExMemory",
        "sound_board": "np2kai_SNDboard",
        "gdc": "np2kai_gdc",
    }

    @staticmethod
    def bundled_backend_available() -> bool:
        return config.PC98_BUNDLED_RETROARCH.is_file() and config.PC98_BUNDLED_CORE.is_file()

    @staticmethod
    def get_managed_system_path_default() -> str:
        """Use LVNM's managed folder only when Flatpak or it already contains files."""
        managed_path = config.PC98_SYSTEM_DIR / "np2kai"
        if Pc98Manager.bundled_backend_available() and config.PC98_BUNDLED_FONT.is_file():
            return str(managed_path)
        try:
            if managed_path.is_dir() and any(managed_path.iterdir()):
                return str(managed_path)
        except OSError:
            pass
        return ""

    @staticmethod
    def resolve_game_media(game) -> str:
        """Return the selected media or an automatically generated NP2kai command file."""
        selected = Path(game.path).expanduser()
        if not selected.is_absolute():
            selected = Path.cwd() / selected
        selected = selected.resolve()
        extension = selected.suffix.lower()

        if extension == ".cmd":
            return str(selected)

        if extension == ".m3u":
            media = Pc98Manager._read_m3u(selected)
            return Pc98Manager._write_media_command(game.name, selected, media)

        if extension in Pc98Manager.FLOPPY_EXTENSIONS:
            floppy_images = Pc98Manager._find_floppy_set(selected)
            if len(floppy_images) == 1:
                return str(selected)
            return Pc98Manager._write_media_command(game.name, selected, floppy_images)

        if extension in Pc98Manager.HARD_DISK_EXTENSIONS:
            cd_image = Pc98Manager._find_single_companion(selected, Pc98Manager.CD_EXTENSIONS, "CD images")
            if cd_image is None:
                return str(selected)
            return Pc98Manager._write_media_command(game.name, selected, [selected, cd_image])

        if extension in Pc98Manager.CD_EXTENSIONS:
            hard_disk = Pc98Manager._find_single_companion(selected, Pc98Manager.HARD_DISK_EXTENSIONS, "hard disk images")
            floppy_images = Pc98Manager._find_companion_floppy_set(selected)
            if hard_disk is None and not floppy_images:
                raise ValueError(
                    f"The PC-98 CD image '{selected.name}' needs a bootable hard disk or floppy image in the same folder. "
                    "Add the required media or use a manually configured .cmd file."
                )
            media = floppy_images + ([hard_disk] if hard_disk else []) + [selected]
            return Pc98Manager._write_media_command(game.name, selected, media)

        return str(selected)

    @staticmethod
    def _read_m3u(playlist: Path) -> list[Path]:
        media = []
        for raw_line in playlist.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if len(line) >= 2 and line.startswith('"') and line.endswith('"'):
                line = line[1:-1]
            path = Path(line).expanduser()
            if not path.is_absolute():
                path = playlist.parent / path
            path = path.resolve()
            if not path.is_file():
                raise ValueError(f"The PC-98 playlist '{playlist.name}' references missing media: {line}")
            media.append(path)
        if not media:
            raise ValueError(f"The PC-98 playlist '{playlist.name}' does not contain any media files.")
        return media

    @staticmethod
    def _find_floppy_set(selected: Path) -> list[Path]:
        family, has_disk_marker = Pc98Manager._media_family(selected)
        if not has_disk_marker:
            return [selected]

        candidates = [path.resolve() for path in selected.parent.iterdir() if path.is_file() and path.suffix.lower() in Pc98Manager.FLOPPY_EXTENSIONS]
        matching = [path for path in candidates if Pc98Manager._media_family(path)[0] == family]
        return sorted(matching, key=Pc98Manager._natural_sort_key) or [selected]

    @staticmethod
    def _find_companion_floppy_set(selected: Path) -> list[Path]:
        # A BIN beside a CUE is normally the CD track payload, despite BIN also being a valid floppy extension in NP2kai.
        candidates = [
            path.resolve() for path in selected.parent.iterdir()
            if path.is_file() and path.suffix.lower() in Pc98Manager.FLOPPY_EXTENSIONS and path.suffix.lower() != ".bin"
        ]
        if not candidates:
            return []

        selected_family, _ = Pc98Manager._media_family(selected)
        matching = [path for path in candidates if Pc98Manager._media_family(path)[0] == selected_family]
        if matching:
            return sorted(matching, key=Pc98Manager._natural_sort_key)

        groups = {}
        for path in candidates:
            family, _ = Pc98Manager._media_family(path)
            groups.setdefault(family, []).append(path)
        if len(groups) == 1:
            return sorted(next(iter(groups.values())), key=Pc98Manager._natural_sort_key)
        raise ValueError(f"Several floppy sets were found next to '{selected.name}'. Create a .cmd file to select the correct boot media.")

    @staticmethod
    def _find_single_companion(selected: Path, extensions: frozenset[str], description: str) -> Path | None:
        candidates = [
            path.resolve() for path in selected.parent.iterdir()
            if path.is_file() and path.suffix.lower() in extensions and path.resolve() != selected
        ]
        if not candidates:
            return None

        selected_family, _ = Pc98Manager._media_family(selected)
        matching = [path for path in candidates if Pc98Manager._media_family(path)[0] == selected_family]
        if len(matching) == 1:
            return matching[0]
        if len(matching) > 1:
            raise ValueError(f"Several matching {description} were found next to '{selected.name}'. Create a .cmd file to select the correct media.")
        if len(candidates) == 1:
            return candidates[0]
        raise ValueError(f"Several {description} were found next to '{selected.name}'. Create a .cmd file to select the correct media.")

    @staticmethod
    def _media_family(path: Path) -> tuple[str, bool]:
        normalized = Pc98Manager.DISK_MARKER_PATTERN.sub("", path.stem)
        normalized = re.sub(r"[\s._-]+", " ", normalized).strip().casefold()
        return normalized, normalized != re.sub(r"[\s._-]+", " ", path.stem).strip().casefold()

    @staticmethod
    def _natural_sort_key(path: Path) -> list[tuple[int, int | str]]:
        parts = re.split(r"(\d+)", path.name.casefold())
        return [(0, int(part)) if part.isdigit() else (1, part) for part in parts]

    @staticmethod
    def _write_media_command(game_name: str, selected: Path, media: list[Path]) -> str:
        resolved_media = []
        for path in media:
            resolved = path.resolve()
            if '"' in str(resolved) or "\n" in str(resolved) or "\r" in str(resolved):
                raise ValueError(f"NP2kai cannot safely load a media path containing quotes or line breaks: {resolved}")
            if resolved not in resolved_media:
                resolved_media.append(resolved)

        command = "np2kai" + "".join(f' "{path}"' for path in resolved_media) + "\n"
        if len(command.encode("utf-8")) > Pc98Manager.CMD_MAX_BYTES:
            raise ValueError("The automatically generated NP2kai media command is too long. Shorten the media filenames or create a manual .cmd file.")

        media_dir = config.PC98_DIR / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        media_id = hashlib.sha256(f"{game_name}\0{selected}".encode("utf-8")).hexdigest()[:16]
        command_path = media_dir / f"{media_id}.cmd"
        if not command_path.exists() or command_path.read_text(encoding="utf-8") != command:
            command_path.write_text(command, encoding="utf-8")
        logger.info(f"Using generated NP2kai media command for '{game_name}': {command_path}")
        return str(command_path)

    @staticmethod
    def build_launch_args(game, core_path: str, system_path: str | None = None) -> list[str]:
        config.PC98_DIR.mkdir(parents=True, exist_ok=True)
        if not system_path:
            raise ValueError("Select a PC-98 BIOS/font system folder in Emulation settings before launching the game.")
            
        np2kai_system_dir = Path(system_path).expanduser()
        if not np2kai_system_dir.is_absolute():
            np2kai_system_dir = Path.cwd() / np2kai_system_dir
        np2kai_system_dir.mkdir(parents=True, exist_ok=True)
        retroarch_system_dir = Pc98Manager._get_retroarch_system_dir(np2kai_system_dir)
        saves_dir = config.PC98_DIR / "saves"
        states_dir = config.PC98_DIR / "states"
        options_dir = config.PC98_DIR / "options"
        profiles_dir = config.PC98_DIR / "profiles"
        saves_dir.mkdir(parents=True, exist_ok=True)
        states_dir.mkdir(parents=True, exist_ok=True)
        options_dir.mkdir(parents=True, exist_ok=True)
        profiles_dir.mkdir(parents=True, exist_ok=True)

        bundled_font = config.PC98_BUNDLED_FONT
        target_font = np2kai_system_dir / "font.bmp"
        original_font = np2kai_system_dir / "font.rom"
        if bundled_font.is_file() and not target_font.exists() and not original_font.exists():
            shutil.copy2(bundled_font, target_font)

        profile_id = hashlib.sha256(game.name.encode("utf-8")).hexdigest()[:16]
        options_path = options_dir / f"{profile_id}.opt"
        option_lines = []
        pc98_settings = getattr(game, "pc98", None)
        if pc98_settings:
            for field_name, option_key in Pc98Manager.CORE_OPTION_KEYS.items():
                value = getattr(pc98_settings, field_name, "").strip()
                if value:
                    escaped_value = value.replace('"', '\\"')
                    option_lines.append(f'{option_key} = "{escaped_value}"')
        options_path.write_text("\n".join(option_lines) + ("\n" if option_lines else ""), encoding="utf-8")

        retroarch_config = profiles_dir / f"{profile_id}.cfg"
        config_lines = [
            f'libretro_directory = "{Path(core_path).parent}"',
            f'libretro_info_path = "{Path(core_path).parent}"',
            f'system_directory = "{retroarch_system_dir}"',
            f'savefile_directory = "{saves_dir}"',
            f'savestate_directory = "{states_dir}"',
            f'core_options_path = "{options_path}"',
            'config_save_on_exit = "false"',
            'input_exit_emulator = "nul"',
            'menu_driver = "rgui"',
            'menu_show_core_updater = "false"',
        ]
        retroarch_config.write_text("\n".join(config_lines) + "\n", encoding="utf-8")
        return ["--config", str(retroarch_config), "-L", core_path]

    @staticmethod
    def _get_retroarch_system_dir(np2kai_system_dir: Path) -> Path:
        """Expose any selected BIOS folder under the np2kai name required by the core."""
        if np2kai_system_dir.name == "np2kai":
            return np2kai_system_dir.parent

        path_id = hashlib.sha256(str(np2kai_system_dir).encode("utf-8")).hexdigest()[:16]
        system_root = config.PC98_DIR / "system-links" / path_id
        system_root.mkdir(parents=True, exist_ok=True)
        np2kai_link = system_root / "np2kai"
        if not np2kai_link.exists():
            np2kai_link.symlink_to(np2kai_system_dir, target_is_directory=True)
        return system_root
