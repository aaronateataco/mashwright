"""Data shared by every Mashwright module."""

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


class MashwrightError(Exception):
    """A problem to show the user as-is (no traceback)."""


@dataclass
class Game:
    key: str                      # "<store>:<store_id>", globally unique
    store: str                    # steam|epic|gog|heroic|lutris|itch|custom|switch|android|ios
    store_id: str
    title: str
    install_dir: Optional[Path]   # PC games; None for device targets
    platform: str                 # binary platform: windows|linux|macos|switch|android|ios
    runner: str = "native"        # native|proton|wine|emulator:<name>|device
    launch: Dict = field(default_factory=dict)
    extra: Dict = field(default_factory=dict)
    slugs: List[str] = field(default_factory=list)
    version: str = ""             # store-reported version/build if known

    def to_json(self) -> Dict:
        d = asdict(self)
        d["install_dir"] = str(self.install_dir) if self.install_dir else None
        return d


@dataclass
class Placement:
    component: str
    source: str        # path inside the component archive ("" = whole archive / the file itself)
    dest: str          # absolute path, or "device:<serial>:<path>", or "afc:<udid>:<bundle>:<path>"
    extract: bool = True
    optional: bool = False


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s or "game"


def is_slug(text: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", text or ""))
