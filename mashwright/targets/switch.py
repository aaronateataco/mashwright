"""Nintendo Switch mods for the player's own setup: Ryujinx-family and yuzu-family emulators' mod
folders, and Atmosphère's LayeredFS folder on a mounted SD card. Titles are identified by their
16-hex-digit title id. Only mod folders are written; keys, firmware and game dumps are never read.

Layouts:
  Ryujinx:    <data>/mods/contents/<titleid>/<mod>/{romfs,exefs}
  yuzu-family <data>/load/<titleid>/<mod>/{romfs,exefs}
  Atmosphère: <sd>/atmosphere/contents/<titleid>/{romfs,exefs}
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from ..model import Game, MashwrightError
from ..platforms import HostEnv, removable_volumes, xdg_config_home

log = logging.getLogger(__name__)

STORE = "switch"
TITLE_RE = re.compile(r"^[0-9A-Fa-f]{16}$")
RYUJINX = {"Ryujinx": "org.ryujinx.Ryujinx", "Ryubing": "io.github.ryubing.Ryujinx"}
YUZU_FAMILY = {"yuzu": "org.yuzu_emu.yuzu", "suyu": "org.suyu_emu.suyu", "sudachi": "org.sudachi_emu.sudachi",
               "citron": "org.citron_emu.citron", "eden": "dev.eden_emu.eden"}


def _data_dirs(env: HostEnv, name: str, flatpak_id: str, config: bool) -> List[Path]:
    if env.os == "windows":
        return [Path(env.env("APPDATA", str(env.home / "AppData" / "Roaming"))) / name]
    if env.os == "macos":
        return [env.home / "Library" / "Application Support" / name]
    base = xdg_config_home(env) if config else (Path(env.env("XDG_DATA_HOME")) if env.env("XDG_DATA_HOME")
                                                else env.home / ".local" / "share")
    sub = "config" if config else "data"
    return [base / name, env.home / ".var" / "app" / flatpak_id / sub / name]


def backends(env: HostEnv) -> List[Dict]:
    """Every installed emulator data folder and Atmosphère card: {kind, name, path}."""
    out: List[Dict] = []
    # Ryujinx and its Ryubing continuation share the "Ryujinx" data folder name.
    for name, fid in RYUJINX.items():
        for d in _data_dirs(env, "Ryujinx", fid, True):
            if d.is_dir() and not any(o["path"] == str(d) for o in out):
                out.append({"kind": "ryujinx", "name": name, "path": str(d)})
    for name, fid in YUZU_FAMILY.items():
        for d in _data_dirs(env, name, fid, False):
            if d.is_dir():
                out.append({"kind": "yuzu", "name": name, "path": str(d)})
    for vol in removable_volumes(env):
        if (vol / "atmosphere").is_dir():
            out.append({"kind": "atmosphere", "name": f"SD card {vol}", "path": str(vol)})
    return out


def _titles(b: Dict) -> List[str]:
    p = Path(b["path"])
    cands: List[Path] = []
    if b["kind"] == "ryujinx":
        cands = [p / "games", p / "mods" / "contents"]
    elif b["kind"] == "yuzu":
        cands = [p / "load", p / "cache" / "game_list"]
    else:
        cands = [p / "atmosphere" / "contents"]
    ids = set()
    for c in cands:
        if c.is_dir():
            for e in c.iterdir():
                tid = e.stem if e.is_file() else e.name
                if TITLE_RE.match(tid):
                    ids.add(tid.upper())
    return sorted(ids)


def detect(env: HostEnv) -> List[Game]:
    by_title: Dict[str, Game] = {}
    for b in backends(env):
        for tid in _titles(b):
            g = by_title.get(tid)
            if g is None:
                g = by_title[tid] = Game(key=f"switch:{tid}", store=STORE, store_id=tid, title=tid,
                                         install_dir=None, platform="switch", runner="emulator",
                                         extra={"mod_roots": []})
            g.extra["mod_roots"].append(b)
    return list(by_title.values())


def game_for_title(env: HostEnv, title_id: str, title: str = "") -> Optional[Game]:
    """A Game for a title id even if no emulator has listed it yet (any backend can host its mods)."""
    tid = title_id.upper()
    if not TITLE_RE.match(tid):
        raise MashwrightError(f"Not a Switch title id: {title_id}")
    for g in detect(env):
        if g.store_id == tid:
            if title:
                g.title = title
            return g
    roots = backends(env)
    if not roots:
        return None
    return Game(key=f"switch:{tid}", store=STORE, store_id=tid, title=title or tid, install_dir=None,
                platform="switch", runner="emulator", extra={"mod_roots": roots})


def mod_root(game: Game, backend_kind: str, mod_name: str) -> Path:
    """Folder the {switch_mod} placeholder points at for the chosen backend."""
    for b in game.extra.get("mod_roots", []):
        if b["kind"] == backend_kind or b.get("name") == backend_kind:
            p, tid = Path(b["path"]), game.store_id
            if b["kind"] == "ryujinx":
                return p / "mods" / "contents" / tid / mod_name
            if b["kind"] == "yuzu":
                return p / "load" / tid / mod_name
            return p / "atmosphere" / "contents" / tid
    raise MashwrightError(f"No {backend_kind} found for {game.title}")


def emulator_commands(env: HostEnv) -> List[List[str]]:
    """Commands that start an installed emulator (PATH binaries, Flatpaks, standard app paths)."""
    out: List[List[str]] = []
    for exe in ("ryujinx", "Ryujinx", "yuzu", "suyu", "sudachi", "citron", "eden"):
        p = env.which(exe)
        if p:
            out.append([p])
    if env.os == "linux" and env.which("flatpak"):
        code, text = env.run(["flatpak", "list", "--app", "--columns=application"], 10.0)
        if code == 0:
            ids = set(text.split())
            for fid in list(RYUJINX.values()) + list(YUZU_FAMILY.values()):
                if fid in ids:
                    out.append(["flatpak", "run", fid])
    if env.os == "macos":
        for app in ("Ryujinx", "yuzu"):
            if Path(f"/Applications/{app}.app").is_dir():
                out.append(["open", "-a", app])
    return out
