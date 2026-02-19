import json
import config
from pathlib import Path
from dataclasses import dataclass, field, asdict
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
    coverpath: str = ""
    envvar: Dict[str, str] = field(default_factory=dict)
    dlloverride: Dict[str, str] = field(default_factory=dict)
    gamescope: GameScope = field(default_factory=GameScope)

    @classmethod
    def from_dict(cls, name: str, data: dict):
        temp_data = data.copy()
        
        gs_data = temp_data.pop("gamescope", {})
        gs = GameScope(**gs_data)
        
        temp_data["umu_gameid"] = temp_data.pop("umu-gameid", "umu-default")
        temp_data["umu_store"] = temp_data.pop("umu-store", "none")
        
        if "name" in temp_data:
            temp_data.pop("name")
            
        return cls(name=name, gamescope=gs, **temp_data)

    def to_dict(self):
        data = asdict(self)
        
        data["umu-gameid"] = data.pop("umu_gameid")
        data["umu-store"] = data.pop("umu_store")
        return data