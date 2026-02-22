import json
from dataclasses import dataclass, field, asdict
from typing import List
from datetime import datetime

@dataclass
class Prefix:
    name: str
    path: str
    runner: str
    type: str
    codecs: str = ""
    winetricks: str = ""
    fonts: bool = False
    update_date: str = datetime.today().strftime('%Y-%m-%d %H:%M:%S')

    @classmethod
    def from_dict(cls, name: str, data: dict):
        temp_data = data.copy()
        if "name" in temp_data:
            temp_data.pop("name")
        return cls(name=name, **temp_data)

    def to_dict(self) -> dict:
        data = asdict(self)
        return data