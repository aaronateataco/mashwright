"""Mods for console games played in the player's own emulators: texture packs, graphics packs,
LayeredFS mods and patches go into each emulator's documented user folder. Only mod folders are
written; BIOS files, keys, firmware and game images are never read or touched.

A recipe names the game with  "emulator": {"system": "gamecube", "id": "GALE01", "title": "..."}
and maps files to {emu_mod} (the system's usual mod folder for that game) or {emu_root} (the
emulator's user folder, for anything else it documents).
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

from ..model import Game, MashwrightError
from ..platforms import HostEnv, xdg_config_home

STORE = "emulator"
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{4,24}$")


def _data(env: HostEnv) -> Path:
    return Path(env.env("XDG_DATA_HOME")) if env.env("XDG_DATA_HOME") else env.home / ".local" / "share"


# system -> list of (emulator name, {os: [candidate dirs as functions]}, mod template)
# Mod templates use {root}, {id} (game id) and {mod} (the mashup id).
def _emulators(env: HostEnv) -> Dict[str, List[dict]]:
    h, data, cfg = env.home, _data(env), xdg_config_home(env)
    appdata = Path(env.env("APPDATA", str(h / "AppData" / "Roaming")))
    docs = h / "Documents"
    mac = h / "Library" / "Application Support"
    fp = h / ".var" / "app"
    dolphin = {"name": "Dolphin", "dirs": {
        "linux": [data / "dolphin-emu", fp / "org.DolphinEmu.dolphin-emu" / "data" / "dolphin-emu", h / ".dolphin-emu"],
        "windows": [docs / "Dolphin Emulator", appdata / "Dolphin Emulator"], "macos": [mac / "Dolphin"]},
        "mod": "{root}/Load/Textures/{id}", "exe": ["dolphin-emu", "org.DolphinEmu.dolphin-emu"]}
    three_ds = [{"name": n, "dirs": {"linux": [data / f"{d}-emu", fp / f"org.{d}_emu.{n}" / "data" / f"{d}-emu"],
                                     "windows": [appdata / n], "macos": [mac / n]},
                 "mod": "{root}/load/mods/{id}", "exe": [d, f"org.{d}_emu.{n}"]}
                for n, d in (("Azahar", "azahar"), ("Lime3DS", "lime3ds"), ("Citra", "citra"))]
    return {
        "gamecube": [dolphin], "wii": [dolphin], "3ds": three_ds,
        "wiiu": [{"name": "Cemu", "dirs": {"linux": [data / "Cemu", fp / "info.cemu.Cemu" / "data" / "Cemu"],
                                          "windows": [appdata / "Cemu"], "macos": [mac / "Cemu"]},
                  "mod": "{root}/graphicPacks/{mod}", "exe": ["cemu", "Cemu", "info.cemu.Cemu"]}],
        "psp": [{"name": "PPSSPP", "dirs": {"linux": [cfg / "ppsspp", fp / "org.ppsspp.PPSSPP" / "config" / "ppsspp"],
                                           "windows": [docs / "PPSSPP"], "macos": [cfg / "ppsspp", mac / "PPSSPP"]},
                 "mod": "{root}/PSP/TEXTURES/{id}", "exe": ["PPSSPPSDL", "ppsspp", "org.ppsspp.PPSSPP"]}],
        "ps1": [{"name": "DuckStation", "dirs": {"linux": [data / "duckstation", fp / "org.duckstation.DuckStation" / "data" / "duckstation"],
                                                "windows": [docs / "DuckStation"], "macos": [mac / "DuckStation"]},
                 "mod": "{root}/textures/{id}/replacements", "exe": ["duckstation-qt", "org.duckstation.DuckStation"]}],
        "ps2": [{"name": "PCSX2", "dirs": {"linux": [cfg / "PCSX2", fp / "net.pcsx2.PCSX2" / "config" / "PCSX2"],
                                          "windows": [docs / "PCSX2"], "macos": [mac / "PCSX2"]},
                 "mod": "{root}/textures/{id}/replacements", "exe": ["pcsx2-qt", "pcsx2", "net.pcsx2.PCSX2"]}],
        "ps3": [{"name": "RPCS3", "dirs": {"linux": [cfg / "rpcs3", fp / "net.rpcs3.RPCS3" / "config" / "rpcs3"],
                                          "windows": [], "macos": [mac / "rpcs3"]},
                 "mod": "{root}/patches", "exe": ["rpcs3", "net.rpcs3.RPCS3"]}],
    }


SYSTEM_NAMES = {"gamecube": "GameCube", "wii": "Wii", "3ds": "Nintendo 3DS", "wiiu": "Wii U", "psp": "PSP",
                "ps1": "PlayStation", "ps2": "PlayStation 2", "ps3": "PlayStation 3"}


def installed(env: HostEnv, system: str) -> List[dict]:
    """Installed emulators for a system: [{name, root, mod}] (first match per emulator)."""
    out = []
    for emu in _emulators(env).get(system, []):
        for d in emu["dirs"].get(env.os, []):
            if d.is_dir():
                out.append({"name": emu["name"], "root": str(d), "mod": emu["mod"]})
                break
    return out


def detect(env: HostEnv) -> List[Game]:
    return []   # games are named by recipes (an id per system), see game_for()


def game_for(env: HostEnv, spec: dict) -> Optional[Game]:
    system = str(spec.get("system", "")).lower()
    gid = str(spec.get("id", ""))
    if system not in SYSTEM_NAMES:
        raise MashwrightError(f"Unknown emulated system {system!r} (known: {', '.join(SYSTEM_NAMES)})")
    if not ID_RE.match(gid):
        raise MashwrightError(f"Bad game id for {SYSTEM_NAMES[system]}: {gid!r}")
    emus = installed(env, system)
    if not emus:
        return None
    return Game(key=f"emulator:{system}:{gid}", store=STORE, store_id=gid,
                title=spec.get("title") or f"{SYSTEM_NAMES[system]} game {gid}", install_dir=None,
                platform=system, runner=f"emulator:{emus[0]['name']}", extra={"system": system, "emulators": emus})


def paths(game: Game, mod_name: str, emulator: str = "") -> Dict[str, str]:
    emus = game.extra.get("emulators", [])
    emu = next((e for e in emus if e["name"].lower() == emulator.lower()), emus[0] if emus else None)
    if emu is None:
        raise MashwrightError(f"No emulator found for {game.title}")
    mod = emu["mod"].format(root=emu["root"], id=game.store_id, mod=mod_name)
    return {"emu_root": emu["root"], "emu_mod": str(Path(mod))}


def commands(env: HostEnv, system: str) -> List[List[str]]:
    out = []
    for emu in _emulators(env).get(system, []):
        for exe in emu["exe"]:
            if "." in exe and env.os == "linux" and env.which("flatpak"):
                if (Path("/var/lib/flatpak/app") / exe).is_dir() or (env.home / ".local/share/flatpak/app" / exe).is_dir():
                    out.append(["flatpak", "run", exe])
            elif env.which(exe):
                out.append([env.which(exe)])
    return out
