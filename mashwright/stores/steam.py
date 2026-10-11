"""Steam detector: every Steam library on the host and the games installed in it.

Library roots: Windows (registry SteamPath, default Program Files), Linux (~/.steam, ~/.local/share,
Flatpak, Snap) and macOS. Each root's ``steamapps/libraryfolders.vdf`` lists the other libraries;
each library's ``appmanifest_<appid>.acf`` describes one installed app.

On Linux a game is marked as running through Proton when it has a ``compatdata/<appid>/pfx`` prefix
or its folder holds only Windows binaries.
"""

import logging
import os
from pathlib import Path
from typing import Dict, List

from .. import vdf
from ..model import Game
from ..platforms import HostEnv

log = logging.getLogger(__name__)

STORE = "steam"

# Steam's own tools and runtimes (Proton, Steam Linux Runtime, Steamworks redistributables).
TOOL_APPIDS = {"228980", "1070560", "1391110", "1628350", "1493710", "1826330", "2180100", "2348590",
               "1161040", "1887720", "2805730", "3658110"}
TOOL_PREFIXES = ("proton", "steam linux runtime", "steamworks", "steamvr")
FULLY_INSTALLED = 4  # StateFlags bit


def roots(env: HostEnv) -> List[Path]:
    """Steam installation folders (each has steamapps/libraryfolders.vdf)."""
    out: List[Path] = []
    if env.os == "windows":
        if env.reg:
            p = env.reg("HKCU", r"Software\Valve\Steam", "SteamPath")
            if p:
                out.append(Path(p))
        pf86 = env.env("ProgramFiles(x86)", "C:\\Program Files (x86)")
        out.append(Path(pf86) / "Steam")
    elif env.os == "macos":
        out.append(env.home / "Library" / "Application Support" / "Steam")
    else:
        h = env.home
        out += [h / ".steam" / "steam", h / ".steam" / "root", h / ".local" / "share" / "Steam",
                h / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam",
                h / ".var" / "app" / "com.valvesoftware.Steam" / "data" / "Steam",
                h / "snap" / "steam" / "common" / ".local" / "share" / "Steam"]
    return _unique_existing(out)


def _unique_existing(paths: List[Path]) -> List[Path]:
    seen, out = set(), []
    for p in paths:
        try:
            if not p.is_dir():
                continue
            key = os.path.normcase(str(p.resolve()))
        except OSError:
            continue
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def libraries(env: HostEnv) -> List[Path]:
    """Every library folder (the folder that contains steamapps/)."""
    libs: List[Path] = []
    for root in roots(env):
        libs.append(root)
        lf = root / "steamapps" / "libraryfolders.vdf"
        if not lf.is_file():
            continue
        try:
            data = vdf.load_file(lf)
        except OSError:
            continue
        folders = vdf.get_ci(data, "libraryfolders") or vdf.get_ci(data, "LibraryFolders") or {}
        if not isinstance(folders, dict):
            continue
        for key, val in folders.items():
            if isinstance(val, dict):          # new format: "0" { "path" "..." }
                p = vdf.get_ci(val, "path")
                if p:
                    path = Path(p)
                    if not path.is_dir():
                        # The drive may be mounted somewhere else now (Linux mount points change).
                        path = _find_moved_library(env, str(vdf.get_ci(val, "contentid") or ""), path) or path
                    libs.append(path)
            elif key.isdigit() and val:         # old format: "1" "D:\\Games"
                libs.append(Path(val))
    return _unique_existing(libs)


def _find_moved_library(env: HostEnv, contentid: str, old: Path):
    """A library listed at a path that no longer exists, found on another mount by its contentid."""
    if not contentid or env.os == "windows":
        return None
    from ..platforms import removable_volumes
    bases = list(removable_volumes(env))
    for extra in (Path("/mnt"), Path("/media"), Path("/run/media") / (env.env("USER") or env.home.name)):
        try:
            bases += [p for p in extra.iterdir() if p.is_dir()] if extra.is_dir() else []
        except OSError:
            pass
    seen = set()
    for base in bases:
        for cand in (base / old.name, base, base / "SteamLibrary"):
            if cand in seen:
                continue
            seen.add(cand)
            f = cand / "libraryfolder.vdf"
            try:
                if f.is_file() and str(vdf.get_ci(vdf.load_file(f), "libraryfolder", "contentid") or "") == contentid:
                    log.info("Steam library %s found at %s", old, cand)
                    return cand
            except OSError:
                continue
    return None


def _is_tool(appid: str, name: str) -> bool:
    return appid in TOOL_APPIDS or name.lower().startswith(TOOL_PREFIXES)


def _windows_only(install_dir: Path) -> bool:
    """True when the folder has Windows executables and no Linux ones (top two levels)."""
    has_exe = has_linux = False
    try:
        for p in list(install_dir.iterdir())[:400]:
            names = [p] if p.is_file() else (list(p.iterdir())[:200] if p.is_dir() else [])
            for f in names:
                n = f.name.lower()
                if n.endswith(".exe"):
                    has_exe = True
                elif n.endswith((".x86_64", ".x86", ".sh", ".so")) or _is_elf(f):
                    has_linux = True
    except OSError:
        return False
    return has_exe and not has_linux


def _is_elf(f: Path) -> bool:
    try:
        if not f.is_file() or f.stat().st_size < 64:
            return False
        with open(f, "rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False


def detect(env: HostEnv) -> List[Game]:
    games: List[Game] = []
    try:
        for lib in libraries(env):
            apps = lib / "steamapps"
            for acf in sorted(apps.glob("appmanifest_*.acf")):
                g = _game_from_manifest(env, lib, acf)
                if g:
                    games.append(g)
    except Exception as e:  # detectors never raise
        log.warning("steam detection failed: %s", e)
    return games


def _game_from_manifest(env: HostEnv, lib: Path, acf: Path):
    try:
        data = vdf.load_file(acf)
    except OSError:
        return None
    state = vdf.get_ci(data, "AppState") or {}
    if not isinstance(state, dict):
        return None
    appid = str(vdf.get_ci(state, "appid") or acf.stem.split("_", 1)[-1])
    name = str(vdf.get_ci(state, "name") or appid)
    installdir = vdf.get_ci(state, "installdir")
    if not installdir or _is_tool(appid, name):
        return None
    try:
        flags = int(vdf.get_ci(state, "StateFlags") or 0)
    except ValueError:
        flags = 0
    if not flags & FULLY_INSTALLED:
        return None
    install = lib / "steamapps" / "common" / str(installdir)
    if not install.is_dir():
        return None
    platform, runner, extra = env.os, "native", {"library": str(lib)}
    if env.os in ("linux", "macos"):
        pfx = lib / "steamapps" / "compatdata" / appid / "pfx"
        if _windows_only(install) or (env.os == "linux" and pfx.is_dir() and not _has_native(install)):
            platform, runner = "windows", "proton"
            extra["prefix"] = str(pfx)
    extra["art"] = artwork(env, appid)
    return Game(key=f"steam:{appid}", store=STORE, store_id=appid, title=name, install_dir=install,
                platform=platform, runner=runner, launch={"url": f"steam://rungameid/{appid}"},
                extra={**extra, "buildid": str(vdf.get_ci(state, "buildid") or "")})


def _has_native(install: Path) -> bool:
    try:
        for f in install.iterdir():
            n = f.name.lower()
            if n.endswith((".x86_64", ".x86", ".sh")) or _is_elf(f):
                return True
    except OSError:
        pass
    return False


def artwork(env: HostEnv, appid: str) -> Dict[str, str]:
    """Steam's locally cached artwork for an app: icon, capsule, hero, header, logo (paths)."""
    art: Dict[str, str] = {}
    names = {"library_600x900.jpg": "capsule", "library_hero.jpg": "hero", "library_header.jpg": "header",
             "logo.png": "logo"}
    for root in roots(env):
        cache = root / "appcache" / "librarycache"
        folder = cache / appid
        if folder.is_dir():
            for p in folder.rglob("*"):
                if p.name in names and names[p.name] not in art:
                    art[names[p.name]] = str(p)
                elif p.parent == folder and p.suffix == ".jpg" and len(p.stem) == 40 and "icon" not in art:
                    art["icon"] = str(p)
        for kind, flat in (("capsule", f"{appid}_library_600x900.jpg"), ("hero", f"{appid}_library_hero.jpg"),
                           ("header", f"{appid}_header.jpg"), ("logo", f"{appid}_logo.png"), ("icon", f"{appid}_icon.jpg")):
            if kind not in art and (cache / flat).is_file():
                art[kind] = str(cache / flat)
        if art:
            break
    return art
