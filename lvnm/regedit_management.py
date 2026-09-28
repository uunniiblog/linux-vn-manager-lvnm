import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from execution_manager import ExecutionManager
from prefix_manager import PrefixManager

logger = logging.getLogger(__name__)

class RegeditManager:
    """Finds and copies game-specific registry keys between Wine prefixes."""

    _HIVE_FILES = {
        "system.reg": "HKLM",
        "user.reg": "HKCU",
    }
    _ROOT_ALIASES = {
        "HKLM": "HKLM",
        "HKEY_LOCAL_MACHINE": "HKLM",
        "HKCU": "HKCU",
        "HKEY_CURRENT_USER": "HKCU",
        "HKCR": "HKCR",
        "HKEY_CLASSES_ROOT": "HKCR",
        "HKU": "HKU",
        "HKEY_USERS": "HKU",
        "HKCC": "HKCC",
        "HKEY_CURRENT_CONFIG": "HKCC",
    }
    _SECTION_RE = re.compile(r"^\[(.+?)](?:\s+\d+)?$")
    _UNICODE_ESCAPE_RE = re.compile(r"\\x([0-9a-fA-F]{4})")
    _GENERIC_EXE_NAMES = {"game", "start", "launcher", "setup", "install", "config"}

    @classmethod
    def auto_detect_registry_key(cls, game) -> str:
        candidates = cls.find_registry_keys(game)
        return candidates[0] if candidates else ""

    @classmethod
    def find_registry_keys(cls, game) -> list[str]:
        logger.debug(
            f"Registry auto-detect input: game='{getattr(game, 'name', '')}', "
            f"ogtitle='{getattr(game, 'ogtitle', '')}', path='{getattr(game, 'path', '')}', "
            f"prefix='{getattr(game, 'prefix', '')}'"
        )
        prefix_info = PrefixManager.get_prefix_info(game.prefix)
        if not prefix_info:
            raise ValueError(f"Prefix '{game.prefix}' was not found.")

        prefix_path = Path(prefix_info.get("path", ""))
        if not prefix_path.is_dir():
            raise FileNotFoundError(f"Prefix path does not exist: {prefix_path}")

        terms = cls._search_terms(game)
        logger.debug(f"Registry auto-detect search terms: {terms}")
        candidates: dict[str, int] = {}
        for filename, root in cls._HIVE_FILES.items():
            hive_path = prefix_path / filename
            if not hive_path.is_file():
                logger.debug(f"Registry auto-detect hive does not exist: '{hive_path}'")
                continue
            for section, values in cls._read_sections(hive_path):
                if not section.casefold().startswith("software\\"):
                    continue
                score = cls._score_section(section, values, terms)
                if score <= 0:
                    continue
                registry_path = f"{root}\\{cls._unescape_hive_text(section)}"
                candidates[registry_path] = max(score, candidates.get(registry_path, 0))

        sorted_candidates = [
            path
            for path, _score in sorted(
                candidates.items(), key=lambda item: (-item[1], len(item[0]), item[0].casefold())
            )
        ]
        logger.debug(f"Registry auto-detect candidates and scores: {candidates}")
        logger.debug(f"Registry auto-detect sorted candidates: {sorted_candidates}")
        return sorted_candidates

    @staticmethod
    def _search_terms(game) -> dict[str, list[str]]:
        exe_path = Path(str(game.path))
        game_dir = str(exe_path.parent)
        windows_game_dir = game_dir.replace("/", "\\")
        windows_exe_path = str(exe_path).replace("/", "\\")

        path_terms = {
            game_dir,
            windows_game_dir,
            f"Z:{windows_game_dir}",
            str(exe_path),
            windows_exe_path,
            f"Z:{windows_exe_path}",
        }
        identity_values = [
            exe_path.name,
            exe_path.parent.name,
            str(getattr(game, "name", "")),
            str(getattr(game, "ogtitle", "")),
        ]
        if exe_path.stem.casefold() not in RegeditManager._GENERIC_EXE_NAMES:
            identity_values.append(exe_path.stem)

        identity_terms = set()
        for value in identity_values:
            value = value.strip()
            if len(value) < 3:
                continue
            identity_terms.update({value, value.replace(" ", "_"), value.replace(" ", "")})
        return {
            "paths": sorted({term.casefold() for term in path_terms if len(term) >= 4}, key=len, reverse=True),
            "identity": sorted({term.casefold() for term in identity_terms}, key=len, reverse=True),
        }

    @classmethod
    def _read_sections(cls, hive_path: Path):
        current_section = None
        current_values: list[str] = []
        with hive_path.open("r", encoding="utf-8", errors="replace") as hive:
            for raw_line in hive:
                line = raw_line.rstrip("\r\n")
                match = cls._SECTION_RE.match(line)
                if match:
                    if current_section is not None:
                        yield current_section, "\n".join(current_values)
                    current_section = match.group(1)
                    current_values = []
                elif current_section is not None and line and not line.startswith("#"):
                    current_values.append(line)
        if current_section is not None:
            yield current_section, "\n".join(current_values)

    @classmethod
    def _unescape_hive_text(cls, value: str) -> str:
        # Wine escapes backslashes in its on-disk registry files.
        value = cls._UNICODE_ESCAPE_RE.sub(lambda match: chr(int(match.group(1), 16)), value)
        return value.replace("\\\\", "\\")

    @classmethod
    def _normalise_hive_text(cls, value: str) -> str:
        return cls._unescape_hive_text(value).casefold()

    @classmethod
    def _score_section(cls, section: str, values: str, terms: dict[str, list[str]]) -> int:
        normalised_section = cls._normalise_hive_text(section)
        normalised_values = cls._normalise_hive_text(values)
        score = 0

        path_matches = sum(term in normalised_values for term in terms["paths"])
        if path_matches:
            score += 100 + min(path_matches, 4) * 10

        value_identity_matches = sum(term in normalised_values for term in terms["identity"])
        key_identity_matches = sum(term in normalised_section for term in terms["identity"])
        score += min(value_identity_matches, 4) * 15
        score += min(key_identity_matches, 3) * 20

        # Installer metadata is useful, but a dedicated publisher/game key is
        # normally a better migration candidate when both contain the path.
        if "\\uninstall\\" in normalised_section:
            score -= 25
        if normalised_section.startswith("software\\wine\\"):
            score -= 100
        return score

    @classmethod
    def normalise_registry_path(cls, registry_path: str) -> str:
        path = registry_path.strip().replace("/", "\\").rstrip("\\")
        root, separator, subkey = path.partition("\\")
        canonical_root = cls._ROOT_ALIASES.get(root.upper())
        if not canonical_root or not separator or not subkey:
            raise ValueError(
                "Registry path must include a supported root and subkey, "
                r"for example HKLM\Software\Key\Rewrite_PLUS."
            )
        return f"{canonical_root}\\{subkey}"

    @classmethod
    def copy_registry_key(cls, registry_path: str, source_prefix: str, target_prefix: str, game=None) -> None:
        """Copies a registry key synchronously. Prefer queue_registry_copy from UI code."""
        operation = cls._prepare_copy(registry_path, source_prefix, target_prefix, game)
        source = operation["source"]
        target = operation["target"]
        source_host_path = operation["source_host_path"]
        target_host_path = operation["target_host_path"]
        windows_temp_path = operation["windows_temp_path"]

        try:
            ExecutionManager.run(
                source.runner_command + ["reg", "export", operation["registry_path"], windows_temp_path, "/y"],
                operation["source_env"],
                wait=True,
            )
            cls._transfer_export(operation)
            ExecutionManager.run(
                target.runner_command + ["reg", "import", windows_temp_path],
                operation["target_env"],
                wait=True,
            )
            logger.info(
                "Copied registry key '%s' from '%s' to '%s'.",
                operation["registry_path"],
                source_prefix,
                target_prefix,
            )
        finally:
            source_host_path.unlink(missing_ok=True)
            if target_host_path != source_host_path:
                target_host_path.unlink(missing_ok=True)

    @classmethod
    def queue_registry_copy(cls, registry_path: str, source_prefix: str, target_prefix: str, executor, game=None):
        """Adds a non-blocking export/copy/import sequence to a ConsoleDialog."""
        operation = cls._prepare_copy(registry_path, source_prefix, target_prefix, game)
        source = operation["source"]
        target = operation["target"]
        windows_temp_path = operation["windows_temp_path"]

        executor.add_task(
            source.runner_command
            + ["reg", "export", operation["registry_path"], windows_temp_path, "/y"],
            operation["source_env"],
            f"Exporting {operation['registry_path']} from {source_prefix}",
        )
        executor.add_task(
            lambda logger: cls._transfer_export(operation, logger),
            {},
            f"Copying registry export to {target_prefix}",
        )
        executor.add_task(
            target.runner_command + ["reg", "import", windows_temp_path],
            operation["target_env"],
            f"Importing registry data into {target_prefix}",
        )
        executor.add_task(
            lambda logger: cls._cleanup_copy(operation, logger),
            {},
            "Cleaning temporary registry files",
        )
        return lambda: cls._cleanup_copy(operation)

    @classmethod
    def _prepare_copy(cls, registry_path: str, source_prefix: str, target_prefix: str, game=None) -> dict:
        registry_path = cls.normalise_registry_path(registry_path)
        if source_prefix == target_prefix:
            raise ValueError("Source and target prefixes must be different.")

        source = PrefixManager(source_prefix)
        target = PrefixManager(target_prefix)
        if not source.get_prefix_info(source_prefix):
            raise ValueError(f"Prefix '{source_prefix}' was not found.")
        if not target.get_prefix_info(target_prefix):
            raise ValueError(f"Prefix '{target_prefix}' was not found.")
        if source.type not in ("wine", "proton") or target.type not in ("wine", "proton"):
            raise ValueError("Registry data can only be copied between Wine or Proton prefixes.")

        temp_name = f"lvnm-registry-{uuid.uuid4().hex}.reg"
        source_host_path = source.prefix_path / "drive_c" / "windows" / "temp" / temp_name
        target_host_path = target.prefix_path / "drive_c" / "windows" / "temp" / temp_name
        windows_temp_path = rf"C:\windows\temp\{temp_name}"

        source_host_path.parent.mkdir(parents=True, exist_ok=True)
        target_host_path.parent.mkdir(parents=True, exist_ok=True)

        source_env = source.env.copy()
        target_env = target.env.copy()
        # Short Proton utilities must not use the default waitforexitandrun
        # behavior, which can wait for the prefix's Wine server indefinitely.
        if source.type == "proton":
            source_env["PROTON_VERB"] = "runinprefix"
        if target.type == "proton":
            target_env["PROTON_VERB"] = "runinprefix"

        return {
            "registry_path": registry_path,
            "source": source,
            "target": target,
            "source_host_path": source_host_path,
            "target_host_path": target_host_path,
            "windows_temp_path": windows_temp_path,
            "source_env": source_env,
            "target_env": target_env,
            "path_rewrites": cls._build_path_rewrites(game, source.prefix_path),
        }

    @classmethod
    def _transfer_export(cls, operation: dict, console_logger=None) -> None:
        source_path = operation["source_host_path"]
        target_path = operation["target_host_path"]
        if not source_path.is_file():
            raise RuntimeError("Wine reported success but did not create the registry export.")

        rewrites = operation.get("path_rewrites", [])
        if rewrites:
            replacement_count = cls._rewrite_registry_export(source_path, rewrites)
            if console_logger:
                if replacement_count:
                    console_logger(
                        f"Rewrote {replacement_count} registry path reference(s) to use Wine's Z: drive."
                    )
                    for windows_path, host_path in rewrites:
                        console_logger(f"  {windows_path} -> {host_path}")
                else:
                    console_logger("No matching C: game or savedata paths needed rewriting.")
        elif console_logger:
            console_logger("Game is outside the source prefix; registry paths were left unchanged.")

        shutil.copy2(source_path, target_path)
        if console_logger:
            console_logger(f"Copied export to {target_path}")

    @classmethod
    def _build_path_rewrites(cls, game, source_prefix_path: Path) -> list[tuple[str, str]]:
        if game is None:
            logger.debug("Registry path rewrite skipped: no game data was provided")
            return []

        candidate_paths = []
        game_path = str(getattr(game, "path", "")).strip()
        if game_path:
            candidate_paths.append(Path(game_path).parent)

        legacy_savedata_path = str(getattr(game, "savedata_path", "")).strip()
        if legacy_savedata_path:
            candidate_paths.append(Path(legacy_savedata_path))

        savedata = getattr(game, "savedata", None)
        if savedata:
            folders = savedata.get("folders", []) if isinstance(savedata, dict) else getattr(savedata, "folders", [])
            file_groups = savedata.get("file_groups", []) if isinstance(savedata, dict) else getattr(savedata, "file_groups", [])
            for folder in folders:
                path = folder.get("path", "") if isinstance(folder, dict) else getattr(folder, "path", "")
                if str(path).strip():
                    candidate_paths.append(Path(path))
            for group in file_groups:
                root = group.get("root", "") if isinstance(group, dict) else getattr(group, "root", "")
                if str(root).strip():
                    candidate_paths.append(Path(root))

        drive_c = Path(os.path.abspath(source_prefix_path / "drive_c"))
        logger.debug(
            f"Registry path rewrite input: game_path='{getattr(game, 'path', '')}', "
            f"source_prefix='{source_prefix_path}', drive_c='{drive_c}'"
        )
        logger.debug(f"Registry path rewrite candidate paths: {[str(path) for path in candidate_paths]}")
        rewrites = {}
        for candidate in candidate_paths:
            absolute_path = Path(os.path.abspath(candidate))
            try:
                relative_path = absolute_path.relative_to(drive_c)
            except ValueError:
                # logger.debug(f"Registry path rewrite ignored path outside source prefix: '{absolute_path}'")
                continue
            if not relative_path.parts:
                # logger.debug(f"Registry path rewrite ignored drive_c root itself: '{absolute_path}'")
                continue

            windows_path = "C:\\" + "\\".join(relative_path.parts)
            host_path = "Z:" + str(absolute_path).replace("/", "\\")
            rewrites[windows_path.casefold()] = (windows_path, host_path)
            logger.debug(f"Registry path rewrite mapping: '{windows_path}' -> '{host_path}'")

        # Rewrite nested configured paths before their parents.
        sorted_rewrites = sorted(rewrites.values(), key=lambda item: len(item[0]), reverse=True)
        logger.debug(f"Registry path rewrite final mappings: {sorted_rewrites}")
        return sorted_rewrites

    @classmethod
    def _rewrite_registry_export(cls, export_path: Path, rewrites: list[tuple[str, str]]) -> int:
        raw_data = export_path.read_bytes()
        if raw_data.startswith(b"\xff\xfe"):
            bom, encoding = b"\xff\xfe", "utf-16-le"
        elif raw_data.startswith(b"\xfe\xff"):
            bom, encoding = b"\xfe\xff", "utf-16-be"
        elif raw_data.startswith(b"\xef\xbb\xbf"):
            bom, encoding = b"\xef\xbb\xbf", "utf-8"
        else:
            bom, encoding = b"", "utf-8"

        text = raw_data[len(bom):].decode(encoding)
        replacement_count = 0
        for windows_path, host_path in rewrites:
            # REG_SZ values normally escape backslashes, while some Wine
            # versions/tools can emit them literally. Support both forms.
            variants = [
                (windows_path.replace("\\", "\\\\"), host_path.replace("\\", "\\\\"), "\\\\"),
                (windows_path, host_path, "\\"),
            ]
            for old_path, new_path, separator in variants:
                pattern = re.compile(
                    re.escape(old_path)
                    + rf'(?=$|{re.escape(separator)}|[";,\r\n])',
                    re.IGNORECASE,
                )
                text, count = pattern.subn(lambda _match, value=new_path: value, text)
                replacement_count += count

        export_path.write_bytes(bom + text.encode(encoding))
        return replacement_count

    @staticmethod
    def _cleanup_copy(operation: dict, console_logger=None) -> None:
        source_path = operation["source_host_path"]
        target_path = operation["target_host_path"]
        source_path.unlink(missing_ok=True)
        if target_path != source_path:
            target_path.unlink(missing_ok=True)
        if console_logger:
            console_logger("Temporary registry files removed.")
