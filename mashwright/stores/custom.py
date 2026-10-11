"""Game folders the player added by hand (any store, DRM-free copies, emulated PC games...).

Stored in <config_dir>/custom_games.json as a list of {title, slug, install_dir, platform, exe}.
"""

import json
import logging
from pathlib import Path
from typing import List

from ..model import Game, MashwrightError, is_slug, slugify
from ..platforms import HostEnv, config_dir

log = logging.getLogger(__name__)

STORE = "custom"
PLATFORMS = ("windows", "linux", "macos")


def _file(env: HostEnv) -> Path:
    return config_dir(env) / "custom_games.json"


def load(env: HostEnv) -> List[dict]:
    try:
        data = json.loads(_file(env).read_text(encoding="utf-8"))
        return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save(env: HostEnv, entries: List[dict]) -> None:
    f = _file(env)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    tmp.replace(f)


def add_custom_game(env: HostEnv, title: str, install_dir: str, platform: str = "", exe: str = "",
                    slug: str = "") -> Game:
    path = Path(install_dir).expanduser()
    if not path.is_dir():
        raise MashwrightError(f"Folder not found: {path}")
    platform = platform or env.os
    if platform not in PLATFORMS:
        raise MashwrightError(f"Platform must be one of {', '.join(PLATFORMS)}")
    slug = slug or slugify(title or path.name)
    if not is_slug(slug):
        raise MashwrightError("Slug may only use a-z, 0-9 and dashes")
    if exe and not (path / exe).is_file():
        raise MashwrightError(f"{exe} not found in {path}")
    entries = [e for e in load(env) if e.get("slug") != slug]
    entries.append({"title": title or path.name, "slug": slug, "install_dir": str(path),
                    "platform": platform, "exe": exe})
    save(env, entries)
    return _game(env, entries[-1])


def remove_custom_game(env: HostEnv, slug: str) -> None:
    save(env, [e for e in load(env) if e.get("slug") != slug])


def _game(env: HostEnv, e: dict) -> Game:
    platform = e.get("platform") or env.os
    runner = "wine" if platform == "windows" and env.os != "windows" else "native"
    launch = {"exe": e["exe"]} if e.get("exe") else {}
    return Game(key=f"custom:{e['slug']}", store=STORE, store_id=e["slug"], title=e.get("title") or e["slug"],
                install_dir=Path(e["install_dir"]), platform=platform, runner=runner, launch=launch,
                slugs=[e["slug"]])


def detect(env: HostEnv) -> List[Game]:
    out = []
    for e in load(env):
        try:
            if e.get("slug") and e.get("install_dir") and Path(e["install_dir"]).is_dir():
                out.append(_game(env, e))
        except Exception as ex:
            log.warning("custom game entry skipped: %s", ex)
    return out
