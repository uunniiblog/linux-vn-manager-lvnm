import logging
from datetime import datetime
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)

def _format_age(mtime: float) -> str:
    """Turns a unix timestamp into a short how long ago string"""
    delta = datetime.now().timestamp() - mtime
    if delta < 60:
        return QCoreApplication.translate("savedata_conflict_prompt", "just now")
    minutes = delta / 60
    if minutes < 60:
        return QCoreApplication.translate("savedata_conflict_prompt", "{} min ago").format(int(minutes))
    hours = minutes / 60
    if hours < 24:
        return QCoreApplication.translate("savedata_conflict_prompt", "{:.1f} hr ago").format(hours)
    return QCoreApplication.translate("savedata_conflict_prompt", "{:.1f} days ago").format(hours / 24)

def prompt_savedata_conflict(parent, game_name: str, conflicts: list[dict]) -> str:
    """
    Shows a conflict-resolution prompt for save files that look newer locally
    than on Google Drive, but have never been synced from this device before.
    Returns one of: "prefer_local", "prefer_remote", "defer", "cancel".
    """
    max_shown = 8
    lines = [
        QCoreApplication.translate("savedata_conflict_prompt", "<b>{rel_path}</b> &nbsp; (this device: {local}, cloud: {remote})").format(rel_path=c['rel_path'], local=_format_age(c['local_mtime']), remote=_format_age(c['remote_mtime']))
        for c in conflicts[:max_shown]
    ]
    if len(conflicts) > max_shown:
        lines.append(QCoreApplication.translate("savedata_conflict_prompt", "...and {} more").format(len(conflicts) - max_shown))
    file_list = "<br>".join(lines)
    logger.info(f"Conflicts for {game_name}: {file_list}")

    box = QMessageBox(parent)
    box.setWindowTitle(QCoreApplication.translate("savedata_conflict_prompt", "Save Conflict Detected"))
    box.setIcon(QMessageBox.Warning)
    box.setTextFormat(Qt.RichText)
    box.setText(
        QCoreApplication.translate("savedata_conflict_prompt", "<b>'{game_name}'</b> has save file(s) that look newer than what's on Google Drive, but this device has never synced them before:<br><br>{file_list}<br><br>This can mean real new progress on this device, or just a freshly-created save. Which version do you want to keep?").format(game_name=game_name, file_list=file_list)
    )
    keep_local = box.addButton(QCoreApplication.translate("savedata_conflict_prompt", "Keep This Device's Save"), QMessageBox.AcceptRole)
    keep_remote = box.addButton(QCoreApplication.translate("savedata_conflict_prompt", "Keep Cloud Save"), QMessageBox.DestructiveRole)
    decide_later = box.addButton(QCoreApplication.translate("savedata_conflict_prompt", "Sync Without These"), QMessageBox.ActionRole)
    box.addButton(QCoreApplication.translate("savedata_conflict_prompt", "Cancel"), QMessageBox.RejectRole)
    box.exec()

    clicked = box.clickedButton()
    if clicked == keep_local:
        return "prefer_local"
    if clicked == keep_remote:
        return "prefer_remote"
    if clicked == decide_later:
        return "defer"
    return "cancel"