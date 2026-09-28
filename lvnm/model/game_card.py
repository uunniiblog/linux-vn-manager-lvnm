from __future__ import annotations

import json
import config
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, fields, asdict
from typing import Dict, Optional

@dataclass
class GameScope:
    enabled: str = "false"
    parameters: str = ""

@dataclass
class RtUpscaler:
    enabled: str = "false"
    parameters: str = ""

@dataclass
class SavedataFolder:
    path: str = ""
    excluded: list[str] = field(default_factory=list)
    source_id: str = "primary"

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            path=str(data.get("path", "")),
            excluded=[str(path) for path in data.get("excluded", [])],
            source_id=str(data.get("source_id", "primary")),
        )

@dataclass
class SavedataFileGroup:
    root: str = ""
    files: list[str] = field(default_factory=list)
    source_id: str = "primary"

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            root=str(data.get("root", "")),
            files=[str(path) for path in data.get("files", [])],
            source_id=str(data.get("source_id", "primary")),
        )

@dataclass
class SavedataConfig:
    version: int = 1
    mode: str = "folders"
    folders: list[SavedataFolder] = field(default_factory=list)
    file_groups: list[SavedataFileGroup] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict | None, legacy_path: str = ""):
        if not data:
            folders = [SavedataFolder(path=legacy_path)] if legacy_path else []
            return cls(folders=folders)

        mode = str(data.get("mode", "folders"))
        return cls(
            version=int(data.get("version", 1)),
            mode=mode if mode in {"folders", "files"} else "folders",
            folders=[SavedataFolder.from_dict(item) for item in data.get("folders", [])],
            file_groups=[SavedataFileGroup.from_dict(item) for item in data.get("file_groups", [])],
        )

    def primary_path(self) -> str:
        if self.mode == "files":
            return self.file_groups[0].root if self.file_groups else ""
        return self.folders[0].path if self.folders else ""

@dataclass
class GameCard:
    name: str
    path: str
    prefix: str
    vndb: str
    umu_gameid: str = "umu-default"
    umu_store: str = "none"
    cover_path: str = ""
    layout_path: str = ""
    cover_source_url: str = ""
    layout_source_url: str = ""
    last_played: str = ""
    ogtitle: str = ""
    envvar: Dict[str, str] = field(default_factory=dict)
    dlloverride: Dict[str, str] = field(default_factory=dict)
    gamescope: GameScope = field(default_factory=GameScope)
    rtUpscaler: RtUpscaler = field(default_factory=RtUpscaler)
    update_date: str = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
    label: str = ""
    pre_launch_args: str = ""
    pre_launch_script: str = ""
    pre_launch_script_wait: bool = False
    exit_script: str = ""
    registry_path: str = ""
    arguments: str = ""
    savedata_path: str = ""
    savedata: SavedataConfig = field(default_factory=SavedataConfig)
    gdrive: bool = False

    @classmethod
    def from_dict(cls, name: str, data: dict):
        temp_data = data.copy()
        
        gs_data = temp_data.pop("gamescope", {})
        gs = GameScope(**gs_data)

        upsaler_data = temp_data.pop("rtUpscaler", {})
        upscaler = RtUpscaler(**upsaler_data)

        legacy_savedata_path = str(temp_data.get("savedata_path", ""))
        savedata = SavedataConfig.from_dict(temp_data.pop("savedata", None), legacy_savedata_path)
        
        temp_data["umu_gameid"] = temp_data.pop("umu-gameid", "umu-default")
        temp_data["umu_store"] = temp_data.pop("umu-store", "none")
        
        if "name" in temp_data:
            temp_data.pop("name")

        # Drop unused keys to avoid error
        valid_fields = {f.name for f in fields(cls)}
        temp_data = {k: v for k, v in temp_data.items() if k in valid_fields}
                
        card = cls(name=name, gamescope=gs, rtUpscaler=upscaler, savedata=savedata, **temp_data)
        card.savedata_path = savedata.primary_path() or legacy_savedata_path
        return card

    def to_dict(self):
        # Keep the legacy field synchronized during the schema transition.
        if not self.savedata.folders and not self.savedata.file_groups and self.savedata_path:
            self.savedata = SavedataConfig.from_dict(None, self.savedata_path)
        self.savedata_path = self.savedata.primary_path()
        data = asdict(self)
        
        data["umu-gameid"] = data.pop("umu_gameid")
        data["umu-store"] = data.pop("umu_store")
        return data
