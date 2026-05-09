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
class GameCard:
    name: str
    path: str
    prefix: str
    vndb: str
    umu_gameid: str = "umu-default"
    umu_store: str = "none"
    cover_path: str = ""
    layout_path: str = ""
    last_played: str = ""
    ogtitle: str = ""
    envvar: Dict[str, str] = field(default_factory=dict)
    dlloverride: Dict[str, str] = field(default_factory=dict)
    gamescope: GameScope = field(default_factory=GameScope)
    update_date: str = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
    label: str = ""
    pre_launch_args: str = ""
    pre_launch_script: str = ""
    pre_launch_script_wait: bool = False
    exit_script: str = ""
    arguments: str = ""

    @classmethod
    def from_dict(cls, name: str, data: dict):
        temp_data = data.copy()
        
        gs_data = temp_data.pop("gamescope", {})
        gs = GameScope(**gs_data)
        
        temp_data["umu_gameid"] = temp_data.pop("umu-gameid", "umu-default")
        temp_data["umu_store"] = temp_data.pop("umu-store", "none")
        
        if "name" in temp_data:
            temp_data.pop("name")

        # Drop unused keys to avoid error
        valid_fields = {f.name for f in fields(cls)}
        temp_data = {k: v for k, v in temp_data.items() if k in valid_fields}
                
        return cls(name=name, gamescope=gs, **temp_data)

    def to_dict(self):
        data = asdict(self)
        
        data["umu-gameid"] = data.pop("umu_gameid")
        data["umu-store"] = data.pop("umu_store")
        return data