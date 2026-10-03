"""KDE Plasma taskbar audio integration for Flatpak-launched Wine games.

Why this workaround exists
--------------------------
Plasma normally associates an audio stream with a taskbar window by comparing
their process IDs. For a game running inside Flatpak, PulseAudio/PipeWire reports
the PID from the sandbox namespace while KWin reports the PID from the host
namespace. Those numbers describe the same process but do not compare equal, so
Plasma cannot attach its "playing audio" badge to the game window.

Plasma has a second matching path based on application metadata. It can associate
a window with a desktop entry through `StartupWMClass`, then associate an audio
stream with that entry when the stream's `application.name` equals the entry's
`Name`. This module creates that missing metadata bridge.

Launch lifecycle
----------------
1. Before launching the game, create a temporary desktop entry under the host's
   ~/.local/share/applications directory. Plain Wine windows use the executable
   name as their WM class; umu/Proton windows use `steam_app_default`.
2. After launch, poll the active sink inputs. The game stream is identified from
   the sandbox process tree and the `NSpid` values exposed for its host process.
   Its `WINEPREFIX` is a final fallback for detached Wine/umu children.
3. Read the stream's exact `application.name` and rewrite the entry so that:

       StartupWMClass=<the game window's WM_CLASS>
       Name=<the audio stream's application.name>

   Plasma can then match window -> desktop entry -> audio stream and display the
   badge even though PID matching failed.
4. Keep the entry only while the game is running, then remove it on exit so these
   generated entries do not accumulate or interfere when switching between Wine
   and Proton.

The integration enables itself only for KDE sessions running the Flatpak build.
Its launcher object must provide `game.path`, `process`, `is_proton`,
`is_running()`, and `_get_game_pids()`.
"""
import logging
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from system_utils import SystemUtils
from timetracker.system_utils import SystemUtils as TimeTrackUtils

logger = logging.getLogger(__name__)

_APP_ID = "io.github.uunniiblog.lvnm"
_PULSE_PROP_RE = re.compile(r'^\s*(application\.name|application\.process\.id)\s*=\s*"(.*)"\s*$')

class TaskbarAudioEntry:
    def __init__(self, launcher):
        self.launcher = launcher

    def _is_enabled(self) -> bool:
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
        return (
            SystemUtils.get_runtime_type() == "flatpak"
            and "KDE" in desktop
            and hasattr(self.launcher, "_get_game_pids")
            and hasattr(self.launcher, "is_proton")
        )

    # Paths
    @staticmethod
    def _host_applications_dir() -> Path:
        # In Flatpak, XDG_DATA_HOME points at ~/.var/app/<id>/data, which Plasma does
        # not read. The real home is reachable via --filesystem=home.
        return Path.home() / ".local" / "share" / "applications"

    def _taskbar_entry_path(self) -> Path:
        slug = re.sub(
            r"[^a-z0-9]+", "-", Path(self.launcher.game.path).name.lower()
        ).strip("-")
        return self._host_applications_dir() / f"lvnm-wine-{slug}.desktop"

    def _taskbar_wm_class(self) -> str:
        """Return the WM class used by the game window."""
        if self.launcher.is_proton:
            return "steam_app_default"
        return Path(self.launcher.game.path).name

    # Entry file
    @staticmethod
    def _desktop_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("\n", " ").replace("\r", " ")

    @staticmethod
    def _read_taskbar_entry(path: Path):
        """Returns (name or None, learned flag)."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None, False
        name = re.search(r"^Name=(.*)$", text, re.M)
        learned = re.search(r"^X-LVNM-Learned=true$", text, re.M) is not None
        return (name.group(1) if name else None), learned

    def _write_taskbar_entry(self, path: Path, wm_class: str, stream_name: str, learned: bool):
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={self._desktop_escape(stream_name)}\n"
            f"Exec=flatpak run {_APP_ID}\n"
            f"StartupWMClass={self._desktop_escape(wm_class)}\n"
            "NoDisplay=true\n"
            f"X-LVNM-Learned={'true' if learned else 'false'}\n"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)  # atomic, so Plasma sees a single change
        logger.debug(f"Wrote taskbar entry {path} (Name={stream_name!r}, learned={learned})")

    # Stream lookup
    @staticmethod
    def _expand_descendant_pids(root_pids: set[int]) -> set[int]:
        """Include child processes spawned by Wine/umu inside the sandbox."""
        descendants = set(root_pids)
        children_by_parent: dict[int, set[int]] = {}

        for status_path in Path("/proc").glob("[0-9]*/status"):
            try:
                pid = int(status_path.parent.name)
                ppid = None
                with status_path.open("r", encoding="utf-8", errors="replace") as status:
                    for line in status:
                        if line.startswith("PPid:"):
                            ppid = int(line.split()[1])
                            break
                if ppid is not None:
                    children_by_parent.setdefault(ppid, set()).add(pid)
            except (OSError, ValueError, IndexError):
                continue

        pending = list(root_pids)
        while pending:
            parent = pending.pop()
            for child in children_by_parent.get(parent, ()):
                if child not in descendants:
                    descendants.add(child)
                    pending.append(child)

        return descendants

    def _pid_uses_game_prefix(self, pid: int) -> bool:
        """Whether a stream process belongs to this launch's Wine prefix."""
        prefix = self.launcher.env.get("WINEPREFIX")
        if not prefix:
            return False
        try:
            with open(f"/proc/{pid}/environ", "rb") as environ:
                return os.fsencode(f"WINEPREFIX={prefix}") in environ.read().split(b"\0")
        except (OSError, PermissionError):
            return False

    def _get_game_namespace_pids(self) -> set[int]:
        """Return every PID assigned to the game across host/container namespaces."""
        game_path = self.launcher.game.path
        executable_name = os.path.basename(game_path)
        # umu wrappers retain the native Linux path, while the final Wine process
        # commonly exposes a translated command line such as S:\path\game.exe.
        # Search both forms so the final process and its innermost NSpid are found.
        host_pids = set(
            TimeTrackUtils.get_pids_by_name(
                executable_name,
                cmdline_hint=game_path,
            )
        )
        host_pids.update(TimeTrackUtils.get_pids_by_name(executable_name))
        namespace_pids: set[int] = set()

        for host_pid in host_pids:
            try:
                result = subprocess.run(
                    [
                        "flatpak-spawn",
                        "--host",
                        "cat",
                        f"/proc/{host_pid}/status",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                for line in result.stdout.splitlines():
                    if line.startswith("NSpid:"):
                        mapped_pids = tuple(int(pid) for pid in line.split()[1:])
                        namespace_pids.update(mapped_pids)
                        break
            except (OSError, ValueError, subprocess.SubprocessError) as e:
                logger.debug(
                    "Taskbar audio probe: could not read namespace PIDs for host PID %s: %s",
                    host_pid,
                    e,
                )

        if namespace_pids:
            logger.debug(
                "Taskbar audio probe: host process lookup found namespace PIDs %s",
                sorted(namespace_pids),
            )
        return namespace_pids

    def _find_stream_app_name(self, game_pids: set):
        """application.name of the sink input owned by one of our (sandbox) PIDs."""
        game_pids = self._expand_descendant_pids(game_pids)
        logger.debug(
            "Taskbar audio probe: looking for game/descendant PIDs %s",
            sorted(game_pids),
        )
        try:
            out = subprocess.run(
                ["pactl", "list", "sink-inputs"],
                env={**os.environ, "LC_ALL": "C"},
                capture_output=True, text=True, timeout=3,
            ).stdout
        except (OSError, subprocess.SubprocessError) as e:
            logger.debug(f"pactl unavailable: {e}")
            return None

        for block in out.split("Sink Input #")[1:]:
            props = {}
            for line in block.splitlines():
                m = _PULSE_PROP_RE.match(line)
                if m:
                    props[m.group(1)] = m.group(2)
            pid = props.get("application.process.id", "")
            logger.debug(
                "Taskbar audio probe: sink input PID=%s application.name=%r binary=%r",
                pid,
                props.get("application.name"),
                props.get("application.process.binary"),
            )
            stream_pid = int(pid) if pid.isdigit() else None
            pid_match = stream_pid is not None and stream_pid in game_pids
            prefix_match = (
                stream_pid is not None
                and not pid_match
                and self._pid_uses_game_prefix(stream_pid)
            )
            if pid_match or prefix_match:
                logger.debug(
                    "Taskbar audio probe: matched stream application.name=%r to PID=%s via %s",
                    props.get("application.name"),
                    pid,
                    "process tree" if pid_match else "WINEPREFIX",
                )
                return props.get("application.name")
        return None

    def _cleanup_taskbar_entry_after_exit(self, path: Path):
        """Keep the entry while the game runs, then remove it from the host."""
        while self.launcher.is_running():
            time.sleep(1)
        self._remove_entry(path)

    @staticmethod
    def _remove_entry(path: Path):
        try:
            path.unlink(missing_ok=True)
            logger.debug("Removed taskbar audio entry %s", path)
        except OSError as e:
            logger.warning("Could not remove taskbar audio entry %s: %s", path, e)

    def _learn_stream_name(self, path: Path, wm_class: str, timeout: float = 900):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(3)
            if not self.launcher.is_running():
                return
            pids = set(self.launcher._get_game_pids())
            pids.update(self._get_game_namespace_pids())
            if not pids:
                process = self.launcher.process
                if process is not None and process.poll() is not None:
                    return  # game ended before it ever played audio
                continue
            name = self._find_stream_app_name(pids)
            if name:
                self._write_taskbar_entry(path, wm_class, name, learned=True)
                logger.info(f"Learned audio stream name {name!r} for {wm_class}")
                return

    # Public hooks
    def prepare(self):
        """Call right before launching. Creates the entry if it does not exist yet."""
        if not self._is_enabled():
            return
        try:
            wm_class = self._taskbar_wm_class()
            path = self._taskbar_entry_path()
            name, learned = self._read_taskbar_entry(path)
            if name is None:
                # Placeholder until the real stream name is learned.
                name = Path(wm_class).stem
                learned = False
            # Refresh StartupWMClass even when switching an existing game between
            # Wine and Proton before a stale entry has been cleaned up.
            self._write_taskbar_entry(path, wm_class, name, learned)
        except Exception as e:
            logger.warning(f"Could not prepare taskbar audio entry: {e}")

    def started(self):
        """Call right after launching. No-op once the name has been learned."""
        if not self._is_enabled():
            return
        try:
            wm_class = self._taskbar_wm_class()
            path = self._taskbar_entry_path()
            _, learned = self._read_taskbar_entry(path)
            if not learned:
                threading.Thread(
                    target=self._learn_stream_name, args=(path, wm_class), daemon=True
                ).start()
            threading.Thread(
                target=self._cleanup_taskbar_entry_after_exit,
                args=(path,),
                daemon=True,
                name="taskbar-audio-entry-cleanup",
            ).start()
        except Exception as e:
            logger.warning(f"Could not start stream-name learning: {e}")

    def launch_failed(self):
        """Remove a prepared entry when process creation fails."""
        if not self._is_enabled():
            return
        self._remove_entry(self._taskbar_entry_path())
