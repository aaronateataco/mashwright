"""Heroic Games Launcher (Linux, macOS, Windows): Epic (via Legendary), GOG and Amazon (via Nile)
games it installed. Native and Flatpak config folders are both read."""

import json
import logging
from pathlib import Path
from typing import Dict, List

from ..model import Game
from ..platforms import HostEnv, xdg_config_home

log = logging.getLogger(__name__)

STORE = "heroic"


def config_roots(env: HostEnv) -> List[Path]:
    if env.os == "windows":
        roots = [Path(env.env("APPDATA", str(env.home / "AppData" / "Roaming"))) / "heroic"]
    elif env.os == "macos":
        roots = [env.home / "Library" / "Application Support" / "heroic"]
    else:
        roots = [xdg_config_home(env) / "heroic",
                 env.home / ".var" / "app" / "com.heroicgameslauncher.hgl" / "config" / "heroic"]
    return [r for r in roots if r.is_dir()]


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _platform(value: str, host: str) -> str:
    v = (value or "").lower()
    if v in ("windows", "win32", "win"):
        return "windows"
    if v in ("mac", "osx", "macos", "darwin"):
        return "macos"
    if v == "linux":
        return "linux"
    return host


def _game(runner_name: str, app: str, title: str, path: str, platform: str, host: str) -> Game:
    runner = "wine" if platform == "windows" and host != "windows" else "native"
    return Game(key=f"heroic:{runner_name}:{app}", store=STORE, store_id=f"{runner_name}:{app}",
                title=title or app, install_dir=Path(path), platform=platform, runner=runner,
                launch={"url": f"heroic://launch/{runner_name}/{app}"}, extra={"heroic_runner": runner_name})


def detect(env: HostEnv) -> List[Game]:
    out: Dict[str, Game] = {}
    try:
        for root in config_roots(env):
            # Epic via Legendary: { appName: {title, install_path, platform, ...} }
            leg = _load(root / "legendaryConfig" / "legendary" / "installed.json")
            if isinstance(leg, dict):
                for app, e in leg.items():
                    if isinstance(e, dict) and e.get("install_path"):
                        g = _game("legendary", app, e.get("title", ""), e["install_path"],
                                  _platform(e.get("platform", ""), env.os), env.os)
                        out.setdefault(g.key, g)
            # GOG: {"installed": [{appName, install_path, platform}]}, titles in library.json.
            gog = _load(root / "gog_store" / "installed.json")
            titles = {}
            lib = _load(root / "gog_store" / "library.json")
            if isinstance(lib, dict):
                for e in lib.get("games", []) or []:
                    if isinstance(e, dict) and e.get("app_name"):
                        titles[str(e["app_name"])] = e.get("title", "")
            entries = gog.get("installed", []) if isinstance(gog, dict) else (gog if isinstance(gog, list) else [])
            for e in entries:
                if isinstance(e, dict) and e.get("install_path") and e.get("appName"):
                    app = str(e["appName"])
                    g = _game("gog", app, titles.get(app, ""), e["install_path"],
                              _platform(e.get("platform", ""), env.os), env.os)
                    out.setdefault(g.key, g)
            # Amazon via Nile: [{id, path, ...}]
            nile = _load(root / "nile_config" / "nile" / "installed.json")
            if isinstance(nile, list):
                for e in nile:
                    if isinstance(e, dict) and e.get("path") and e.get("id"):
                        g = _game("nile", str(e["id"]), e.get("title", ""), e["path"], "windows", env.os)
                        out.setdefault(g.key, g)
    except Exception as e:
        log.warning("heroic detection failed: %s", e)
    return [g for g in out.values() if g.install_dir and g.install_dir.is_dir()]
