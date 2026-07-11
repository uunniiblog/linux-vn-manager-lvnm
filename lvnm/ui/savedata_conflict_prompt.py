import logging
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)

def _format_age(mtime: float) -> str:
    """Turns a unix timestamp into a short how long ago string"""
    delta = datetime.now().timestamp() - mtime
    if delta < 60:
        return "just now"
    minutes = delta / 60
    if minutes < 60:
        return f"{int(minutes)} min ago"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f} hr ago"
    return f"{hours / 24:.1f} days ago"

def prompt_savedata_conflict(parent, game_name: str, conflicts: list[dict]) -> str:
    """
    Shows a conflict-resolution prompt for save files that look newer locally
    than on Google Drive, but have never been synced from this device before.
    Returns one of: "prefer_local", "prefer_remote", "defer", "cancel".
    """
    max_shown = 8
    lines = [
        f"<b>{c['rel_path']}</b> &nbsp; (this device: {_format_age(c['local_mtime'])}, "
        f"cloud: {_format_age(c['remote_mtime'])})"
        for c in conflicts[:max_shown]
    ]
    if len(conflicts) > max_shown:
        lines.append(f"...and {len(conflicts) - max_shown} more")
    file_list = "<br>".join(lines)
    logger.info(f"Conflicts for {game_name}: {file_list}")

    box = QMessageBox(parent)
    box.setWindowTitle("Save Conflict Detected")
    box.setIcon(QMessageBox.Warning)
    box.setTextFormat(Qt.RichText)
    box.setText(
        f"<b>'{game_name}'</b> has save file(s) that look newer than what's on Google Drive, "
        f"but this device has never synced them before:<br><br>{file_list}<br><br>"
        f"This can mean real new progress on this device, or just a freshly-created save. "
        f"Which version do you want to keep?"
    )
    keep_local = box.addButton("Keep This Device's Save", QMessageBox.AcceptRole)
    keep_remote = box.addButton("Keep Cloud Save", QMessageBox.DestructiveRole)
    decide_later = box.addButton("Sync Without These", QMessageBox.ActionRole)
    box.addButton("Cancel", QMessageBox.RejectRole)
    box.exec()

    clicked = box.clickedButton()
    if clicked == keep_local:
        return "prefer_local"
    if clicked == keep_remote:
        return "prefer_remote"
    if clicked == decide_later:
        return "defer"
    return "cancel"