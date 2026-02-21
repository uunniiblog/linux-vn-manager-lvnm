import json
from dataclasses import dataclass, field, asdict
from typing import List

@dataclass
class Prefix:
    name: str
    path: str
    runner: str
    type: str
    codecs: str = ""
    winetricks: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, data: dict):
        temp_data = data.copy()
        if "name" in temp_data:
            temp_data.pop("name")
        # Normalize winetricks to always be a list
        winetricks = temp_data.get("winetricks", [])
        if isinstance(winetricks, str):
            winetricks = winetricks.split() if winetricks else []
        temp_data["winetricks"] = winetricks
        return cls(name=name, **temp_data)

    def to_dict(self) -> dict:
        data = asdict(self)
        return data