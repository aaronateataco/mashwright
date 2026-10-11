"""GOG detector: GOG Galaxy installs on Windows (registry, then goggame-*.info files) and macOS app
bundles. On Linux GOG games come through Heroic (heroic.py) or Lutris (lutris.py)."""

import json
import logging
from pathlib import Path
from typing import List, Optional

from ..model import Game
from ..platforms import HostEnv

log = logging.getLogger(__name__)

STORE = "gog"
REG_KEY = r"SOFTWARE\WOW6432Node\GOG.com\Games"


def _info(folder: Path) -> Optional[dict]:
    """The goggame-<id>.info JSON inside a game folder (or a macOS bundle's Resources)."""
    for p in list(folder.glob("goggame-*.info")) + list(folder.glob("Contents/Resources/goggame-*.info")):
        try:
            return json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
    return None


def _game(gid: str, title: str, path: Path, platform: str, exe: str = "") -> Game:
    launch = {"exe": exe} if exe else {}
    if platform == "windows":
        launch["url"] = f"goggalaxy://openGameView/{gid}"
    return Game(key=f"gog:{gid}", store=STORE, store_id=gid, title=title, install_dir=path,
                platform=platform, launch=launch)


def detect(env: HostEnv) -> List[Game]:
    out: List[Game] = []
    try:
        if env.os == "windows":
            out += _windows(env)
        elif env.os == "macos":
            for app in Path("/Applications").glob("*.app"):
                info = _info(app)
                if info and info.get("gameId"):
                    out.append(_game(str(info["gameId"]), info.get("name") or app.stem, app, "macos"))
    except Exception as e:
        log.warning("gog detection failed: %s", e)
    return out


def _windows(env: HostEnv) -> List[Game]:
    out: List[Game] = []
    seen = set()
    if env.reg and env.reg_subkeys:
        for gid in env.reg_subkeys("HKLM", REG_KEY):
            key = REG_KEY + "\\" + gid
            path = env.reg("HKLM", key, "path")
            if not path or not Path(path).is_dir():
                continue
            title = env.reg("HKLM", key, "gameName") or gid
            exe = env.reg("HKLM", key, "exe") or ""
            out.append(_game(gid, title, Path(path), "windows", exe))
            seen.add(gid)
    for base in (Path("C:/GOG Games"), Path("D:/GOG Games"),
                 Path(env.env("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "GOG Galaxy" / "Games"):
        if not base.is_dir():
            continue
        for folder in base.iterdir():
            info = _info(folder) if folder.is_dir() else None
            if info and str(info.get("gameId")) not in seen:
                gid = str(info["gameId"])
                seen.add(gid)
                out.append(_game(gid, info.get("name") or folder.name, folder, "windows"))
    return out
